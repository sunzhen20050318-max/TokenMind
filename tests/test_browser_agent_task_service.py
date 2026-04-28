"""End-to-end TaskService tests with a fake CLI + env-check.

These tests exercise the scripted M1 loop without spawning a real browser:
the CLI is replaced with a stub that returns canned JSON envelopes and
the screenshot path is written with placeholder PNG bytes so artifact
persistence is validated.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest

from tokenmind.browser_agent.cli import AgentBrowserError
from tokenmind.browser_agent.env_check import EnvCheckResult
from tokenmind.browser_agent.models import (
    ArtifactKind,
    CreateTaskRequest,
    StepPhase,
    TaskStatus,
)
from tokenmind.browser_agent.task_service import BrowserTaskService

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@dataclass
class _FakeCLIBehavior:
    open_should_fail: bool = False
    snapshot_should_fail: bool = False


class _FakeCLI:
    def __init__(self, behavior: Optional[_FakeCLIBehavior] = None) -> None:
        self.behavior = behavior or _FakeCLIBehavior()
        self.calls: list[str] = []

    async def open_url(self, project_id: str, url: str, timeout: float = 60.0) -> dict:
        self.calls.append("open")
        if self.behavior.open_should_fail:
            raise AgentBrowserError("simulated open failure")
        return {"success": True, "data": {"url": url}, "error": None}

    async def snapshot(self, project_id: str, *, interactive_only: bool = True, timeout: float = 30.0) -> dict:
        self.calls.append("snapshot")
        if self.behavior.snapshot_should_fail:
            raise AgentBrowserError("simulated snapshot failure")
        return {
            "success": True,
            "data": {"snapshot": "[role=button] Search"},
            "error": None,
        }

    async def screenshot(self, project_id: str, path: Optional[str] = None, *, timeout: float = 30.0) -> dict:
        self.calls.append("screenshot")
        if path:
            Path(path).write_bytes(_PNG_BYTES)
        return {"success": True, "data": {"path": path}, "error": None}

    async def close_session(self, project_id: str) -> None:
        self.calls.append("close")


async def _wait_until(svc: BrowserTaskService, task_id: str, *, timeout: float = 5.0) -> None:
    """Poll storage until the task reaches a terminal status."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        current = svc.storage.get_task(task_id)
        if current and current.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"Task {task_id} did not reach terminal state within {timeout}s")


@pytest.fixture
def env_ready():
    with patch(
        "tokenmind.browser_agent.task_service.check_environment",
        return_value=EnvCheckResult(cli_installed=True, chrome_installed=True, version="0.26.0"),
    ) as mocked:
        yield mocked


@pytest.mark.asyncio
async def test_scripted_loop_reaches_completed(tmp_path: Path, env_ready) -> None:
    cli = _FakeCLI()
    svc = BrowserTaskService(tmp_path, cli=cli)

    task = svc.create_task(
        CreateTaskRequest(
            project_id="proj_x",
            instruction="open and screenshot",
            start_url="https://example.com",
        )
    )
    svc.schedule(task)
    await _wait_until(svc, task.id)

    final = svc.storage.get_task(task.id)
    assert final is not None
    assert final.status is TaskStatus.COMPLETED
    assert final.step_count == 3
    assert "https://example.com" in (final.result_summary or "")

    steps = svc.storage.list_steps(task.id)
    assert [s.action_name for s in steps] == ["open", "snapshot", "screenshot"]
    assert any(s.phase is StepPhase.OBSERVATION for s in steps)

    artifacts = svc.storage.list_artifacts(task.id)
    assert len(artifacts) == 1
    assert artifacts[0].kind is ArtifactKind.SCREENSHOT
    assert Path(artifacts[0].file_path).exists()
    assert artifacts[0].size_bytes == len(_PNG_BYTES)
    assert cli.calls[-1] == "close"


@pytest.mark.asyncio
async def test_open_failure_marks_task_failed(tmp_path: Path, env_ready) -> None:
    cli = _FakeCLI(_FakeCLIBehavior(open_should_fail=True))
    svc = BrowserTaskService(tmp_path, cli=cli)

    task = svc.create_task(
        CreateTaskRequest(
            project_id="proj_x",
            instruction="open and screenshot",
            start_url="https://broken.example",
        )
    )
    svc.schedule(task)
    await _wait_until(svc, task.id)

    final = svc.storage.get_task(task.id)
    assert final is not None
    assert final.status is TaskStatus.FAILED
    assert final.error_detail and "simulated open failure" in final.error_detail
    assert cli.calls[-1] == "close"


@pytest.mark.asyncio
async def test_env_not_ready_marks_task_failed(tmp_path: Path) -> None:
    with patch(
        "tokenmind.browser_agent.task_service.check_environment",
        return_value=EnvCheckResult(
            cli_installed=False,
            chrome_installed=False,
            issues=["agent-browser not installed"],
        ),
    ):
        cli = _FakeCLI()
        svc = BrowserTaskService(tmp_path, cli=cli)
        task = svc.create_task(
            CreateTaskRequest(project_id="p", instruction="x", start_url="https://x")
        )
        svc.schedule(task)
        await _wait_until(svc, task.id)

    final = svc.storage.get_task(task.id)
    assert final is not None
    assert final.status is TaskStatus.FAILED
    assert "agent-browser not installed" in (final.error_detail or "")
    # Env failure short-circuits before opening a session, so no CLI commands
    # (not even close) are issued.
    assert cli.calls == []


class _BlockingFakeCLI(_FakeCLI):
    """Fake CLI whose ``open_url`` blocks on an event so cancel races have a window."""

    def __init__(self) -> None:
        super().__init__()
        self.open_started = asyncio.Event()
        self.open_release = asyncio.Event()

    async def open_url(self, project_id: str, url: str, timeout: float = 60.0) -> dict:
        self.calls.append("open")
        self.open_started.set()
        await self.open_release.wait()
        return {"success": True, "data": {"url": url}, "error": None}


@pytest.mark.asyncio
async def test_request_cancel_marks_task_cancelled(tmp_path: Path, env_ready) -> None:
    """Cancellation signalled mid-run is observed at the next checkpoint."""
    cli = _BlockingFakeCLI()
    svc = BrowserTaskService(tmp_path, cli=cli)

    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="x", start_url="https://x")
    )
    svc.schedule(task)

    await asyncio.wait_for(cli.open_started.wait(), timeout=2.0)
    assert svc.request_cancel(task.id) is True
    cli.open_release.set()

    await _wait_until(svc, task.id)
    final = svc.storage.get_task(task.id)
    assert final is not None
    # Cancel is checked between steps; the snapshot stage will observe the
    # event and short-circuit to CANCELLED before issuing a snapshot call.
    assert final.status is TaskStatus.CANCELLED
    assert "snapshot" not in cli.calls
