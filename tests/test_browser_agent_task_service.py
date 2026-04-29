"""End-to-end TaskService tests with a fake CLI + env-check.

These tests exercise the browser task loop without spawning a real browser:
the CLI is replaced with a stub that returns canned JSON envelopes.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest

from tokenmind.browser_agent.cli import AgentBrowserError
from tokenmind.browser_agent.decision import Decision, DecisionParseError
from tokenmind.browser_agent.env_check import EnvCheckResult
from tokenmind.browser_agent.models import (
    ContinueTaskRequest,
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
    assert final.step_count == 2
    assert "https://example.com" in (final.result_summary or "")

    steps = svc.storage.list_steps(task.id)
    assert [s.action_name for s in steps] == ["open", "snapshot"]
    assert any(s.phase is StepPhase.OBSERVATION for s in steps)

    artifacts = svc.storage.list_artifacts(task.id)
    assert artifacts == []
    assert "close" not in cli.calls


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
    assert "close" in cli.calls


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


# ── ReAct loop tests (M2.3) ────────────────────────────────────────────────


class _ReactFakeCLI(_FakeCLI):
    """Extended fake CLI that records every dispatched method + lets snapshot
    return scripted texts so we can drive the ReAct loop deterministically."""

    def __init__(self, snapshots: list[str]) -> None:
        super().__init__()
        self._snapshots = list(snapshots)
        self._snapshot_idx = 0

    async def snapshot(self, project_id: str, *, interactive_only: bool = True,
                       compact: bool = False, depth=None, selector=None,
                       timeout: float = 30.0) -> dict:
        self.calls.append("snapshot")
        text = self._snapshots[min(self._snapshot_idx, len(self._snapshots) - 1)]
        self._snapshot_idx += 1
        return {"success": True, "data": {"snapshot": text}, "error": None}

    async def fill(self, project_id: str, selector: str, text: str, timeout: float = 30.0) -> dict:
        self.calls.append(f"fill({selector},{text})")
        return {"success": True, "data": {}, "error": None}

    async def press(self, project_id: str, key: str, timeout: float = 30.0) -> dict:
        self.calls.append(f"press({key})")
        return {"success": True, "data": {}, "error": None}

    async def click(self, project_id: str, selector: str, timeout: float = 30.0) -> dict:
        self.calls.append(f"click({selector})")
        return {"success": True, "data": {}, "error": None}

    async def click_xy(self, project_id: str, x: int, y: int, timeout: float = 30.0) -> dict:
        self.calls.append(f"click_xy({x},{y})")
        return {"success": True, "data": {}, "error": None}

    async def get_attr(
        self,
        project_id: str,
        selector: str,
        name: str,
        timeout: float = 15.0,
    ) -> dict:
        self.calls.append(f"get_attr({selector},{name})")
        return {"success": True, "data": {"value": "/explore/demo"}, "error": None}

    async def get_box(self, project_id: str, selector: str, timeout: float = 15.0) -> dict:
        self.calls.append(f"get_box({selector})")
        return {"success": True, "data": {"x": 10, "y": 20, "width": 100, "height": 40}, "error": None}

    async def scroll(self, project_id: str, direction: str, pixels=None, timeout: float = 15.0) -> dict:
        self.calls.append(f"scroll({direction},{pixels})")
        return {"success": True, "data": {}, "error": None}


class _ScriptedDecisionMaker:
    """Returns a queued list of Decision objects, in order."""

    def __init__(self, decisions: list[Decision]) -> None:
        self._queue = list(decisions)
        self.calls: list[dict] = []

    async def decide(self, *, instruction: str, snapshot: str, history) -> Decision:
        self.calls.append({"snapshot": snapshot, "history_len": len(history)})
        if not self._queue:
            raise DecisionParseError("no more scripted decisions")
        return self._queue.pop(0)


@pytest.mark.asyncio
async def test_react_loop_runs_decisions_until_finish(tmp_path: Path, env_ready) -> None:
    cli = _ReactFakeCLI([
        "snap1: textbox @e1",
        "snap2: textbox filled",
        "snap3: results loaded",
    ])
    decisions = [
        Decision(action="fill", args={"selector": "@e1", "text": "TokenMind"}, thinking="填关键词"),
        Decision(action="press", args={"key": "Enter"}, thinking="提交"),
        Decision(action="finish", args={"summary": "找到了搜索结果"}, thinking="完成"),
    ]
    maker = _ScriptedDecisionMaker(decisions)
    svc = BrowserTaskService(tmp_path, cli=cli, decision_factory=lambda task: maker)

    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="搜 TokenMind", start_url="https://x")
    )
    svc.schedule(task)
    await _wait_until(svc, task.id, timeout=10.0)

    final = svc.storage.get_task(task.id)
    assert final is not None
    assert final.status is TaskStatus.COMPLETED
    assert final.result_summary == "找到了搜索结果"

    # Verify the three planned actions actually hit the CLI in order.
    assert "fill(@e1,TokenMind)" in cli.calls
    assert "press(Enter)" in cli.calls

    # Decision maker was called once per non-finish iteration plus the finish call (3 total).
    assert len(maker.calls) == 3
    # History grows with each completed action (open + fill + press = 2 history entries
    # observed by the time of the finish call, since open is recorded as a step but not
    # added to history — only LLM-driven actions are).
    assert maker.calls[2]["history_len"] == 2


@pytest.mark.asyncio
async def test_react_loop_stops_when_decision_parse_fails(tmp_path: Path, env_ready) -> None:
    cli = _ReactFakeCLI(["snap"])

    class _AlwaysFailMaker:
        async def decide(self, *, instruction: str, snapshot: str, history) -> Decision:
            raise DecisionParseError("bad output")

    svc = BrowserTaskService(tmp_path, cli=cli, decision_factory=lambda task: _AlwaysFailMaker())
    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="x", start_url="https://x")
    )
    svc.schedule(task)
    await _wait_until(svc, task.id, timeout=5.0)

    final = svc.storage.get_task(task.id)
    assert final is not None
    assert final.status is TaskStatus.FAILED
    assert "LLM 决策失败" in (final.error_detail or "")


@pytest.mark.asyncio
async def test_react_loop_pauses_on_stuck_observation(tmp_path: Path, env_ready) -> None:
    """Identical snapshots beyond the threshold pause the loop for user takeover.

    Replaces the M2 behaviour (auto-complete) with M3's AWAITING_USER.
    """
    cli = _ReactFakeCLI(["same"] * 12)
    # Vary the actions so DECISION_INSTABILITY doesn't fire before NO_CHANGE.
    decisions = [
        Decision(action="click", args={"selector": f"@e{i}"}) for i in range(10)
    ]
    maker = _ScriptedDecisionMaker(decisions)
    svc = BrowserTaskService(tmp_path, cli=cli, decision_factory=lambda task: maker)

    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="x", start_url="https://x", max_steps=20)
    )
    svc.schedule(task)

    # Wait until the loop hits AWAITING_USER.
    for _ in range(200):
        await asyncio.sleep(0.02)
        current = svc.storage.get_task(task.id)
        if current and current.status is TaskStatus.AWAITING_USER:
            break
    final = svc.storage.get_task(task.id)
    assert final is not None
    assert final.status is TaskStatus.AWAITING_USER

    # Cancel to clean up the running task fixture.
    svc.request_cancel(task.id)
    await _wait_until(svc, task.id, timeout=5.0)


@pytest.mark.asyncio
async def test_react_loop_uses_coordinate_click_when_ref_click_does_not_change_page(
    tmp_path: Path,
    env_ready,
) -> None:
    cli = _ReactFakeCLI([
        "search results with link @e34",
        "search results with link @e34",
        "post detail page",
    ])
    decisions = [
        Decision(action="click", args={"selector": "@e34"}),
        Decision(action="finish", args={"summary": "opened"}),
    ]
    maker = _ScriptedDecisionMaker(decisions)
    svc = BrowserTaskService(tmp_path, cli=cli, decision_factory=lambda task: maker)

    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="open post", start_url="https://x")
    )
    svc.schedule(task)
    await _wait_until(svc, task.id, timeout=10.0)

    final = svc.storage.get_task(task.id)
    assert final is not None
    assert final.status is TaskStatus.COMPLETED
    assert "click(@e34)" in cli.calls
    assert "get_box(@e34)" in cli.calls
    assert "click_xy(60,40)" in cli.calls
    steps = svc.storage.list_steps(task.id)
    assert any(step.action_name == "click_xy_fallback" for step in steps)


@pytest.mark.asyncio
async def test_react_loop_respects_max_steps(tmp_path: Path, env_ready) -> None:
    """When LLM never says finish and snapshots vary, max_steps caps the loop."""
    cli = _ReactFakeCLI([f"snap-{i}" for i in range(50)])
    decisions = [Decision(action="click", args={"selector": "@e1"}) for _ in range(50)]
    maker = _ScriptedDecisionMaker(decisions)
    svc = BrowserTaskService(tmp_path, cli=cli, decision_factory=lambda task: maker)

    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="x", start_url="https://x", max_steps=3)
    )
    svc.schedule(task)
    await _wait_until(svc, task.id, timeout=10.0)

    final = svc.storage.get_task(task.id)
    assert final is not None
    assert final.status is TaskStatus.COMPLETED
    assert "达到最大步数" in (final.result_summary or "")


@pytest.mark.asyncio
async def test_decision_factory_can_be_async(tmp_path: Path, env_ready) -> None:
    cli = _ReactFakeCLI(["snap"])
    decisions = [Decision(action="finish", args={"summary": "ok"})]
    maker = _ScriptedDecisionMaker(decisions)

    async def async_factory(task):
        return maker

    svc = BrowserTaskService(tmp_path, cli=cli, decision_factory=async_factory)
    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="x", start_url="https://x")
    )
    svc.schedule(task)
    await _wait_until(svc, task.id, timeout=5.0)

    final = svc.storage.get_task(task.id)
    assert final is not None
    assert final.status is TaskStatus.COMPLETED


# ── Artifact landing tests (M2.4) ──────────────────────────────────────────


class _ArtifactCLI(_ReactFakeCLI):
    """Fake CLI that returns canned eval/get responses for artifact tests."""

    def __init__(
        self,
        snapshots: list[str],
        eval_responses: dict[str, str],
        get_responses: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(snapshots)
        self._eval_responses = eval_responses
        self._get_responses = get_responses or {}

    async def eval_js(self, project_id: str, expression: str, *, timeout: float = 30.0) -> dict:
        self.calls.append(f"eval({expression[:40]}...)")
        # Return whatever the test queued for the matching key (matched by
        # whether the key string appears in the expression).
        for key, value in self._eval_responses.items():
            if key in expression:
                return {"success": True, "data": {"result": value}, "error": None}
        return {"success": True, "data": {"result": ""}, "error": None}

    async def get(self, project_id: str, what: str, selector: str, timeout: float = 15.0) -> dict:
        self.calls.append(f"get({what},{selector})")
        return {
            "success": True,
            "data": {"text": self._get_responses.get(selector, "")},
            "error": None,
        }


@pytest.mark.asyncio
async def test_save_page_text_persists_artifact(tmp_path: Path, env_ready) -> None:
    cli = _ArtifactCLI(
        snapshots=["snap1", "snap2"],
        eval_responses={"document.body": "Hello world\n这是页面正文"},
    )
    decisions = [
        Decision(action="save_page_text", args={"label": "首页正文"}),
        Decision(action="finish", args={"summary": "ok"}),
    ]
    maker = _ScriptedDecisionMaker(decisions)
    svc = BrowserTaskService(tmp_path, cli=cli, decision_factory=lambda task: maker)

    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="x", start_url="https://x")
    )
    svc.schedule(task)
    await _wait_until(svc, task.id, timeout=10.0)

    final = svc.storage.get_task(task.id)
    assert final is not None
    assert final.status is TaskStatus.COMPLETED

    artifacts = svc.storage.list_artifacts(task.id)
    text_artifacts = [a for a in artifacts if a.kind.value == "page_text"]
    assert len(text_artifacts) == 1
    art = text_artifacts[0]
    assert art.metadata.get("label") == "首页正文"
    saved = Path(art.file_path).read_text(encoding="utf-8")
    assert "Hello world" in saved
    assert "页面正文" in saved


@pytest.mark.asyncio
async def test_extract_persists_json_artifact(tmp_path: Path, env_ready) -> None:
    cli = _ArtifactCLI(
        snapshots=["snap1", "snap2"],
        eval_responses={
            "JSON.stringify": '{"title":"TokenMind","author":"作者X"}',
        },
    )
    decisions = [
        Decision(
            action="extract",
            args={
                "fields": {"title": ".h1", "author": ".byline"},
                "label": "GitHub README",
            },
        ),
        Decision(action="finish", args={"summary": "ok"}),
    ]
    maker = _ScriptedDecisionMaker(decisions)
    svc = BrowserTaskService(tmp_path, cli=cli, decision_factory=lambda task: maker)

    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="x", start_url="https://x")
    )
    svc.schedule(task)
    await _wait_until(svc, task.id, timeout=10.0)

    artifacts = svc.storage.list_artifacts(task.id)
    json_artifacts = [a for a in artifacts if a.kind.value == "extract_json"]
    assert len(json_artifacts) == 1
    art = json_artifacts[0]
    assert art.metadata.get("label") == "GitHub README"
    assert art.metadata.get("fields") == ["title", "author"]
    saved = json.loads(Path(art.file_path).read_text(encoding="utf-8"))
    assert saved == {"title": "TokenMind", "author": "作者X"}


@pytest.mark.asyncio
async def test_extract_accepts_agent_browser_refs(tmp_path: Path, env_ready) -> None:
    cli = _ArtifactCLI(
        snapshots=["snap1", "snap2"],
        eval_responses={},
        get_responses={"@e43": "第一篇标题", "@e44": "作者A"},
    )
    decisions = [
        Decision(
            action="extract",
            args={
                "fields": {"标题1": "ref=e43", "作者1": "e44"},
                "label": "小红书搜索结果",
            },
        ),
        Decision(action="finish", args={"summary": "ok"}),
    ]
    maker = _ScriptedDecisionMaker(decisions)
    svc = BrowserTaskService(tmp_path, cli=cli, decision_factory=lambda task: maker)

    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="x", start_url="https://x")
    )
    svc.schedule(task)
    await _wait_until(svc, task.id, timeout=10.0)

    assert "get(text,@e43)" in cli.calls
    assert "get(text,@e44)" in cli.calls
    artifacts = svc.storage.list_artifacts(task.id)
    art = [a for a in artifacts if a.kind.value == "extract_json"][0]
    saved = json.loads(Path(art.file_path).read_text(encoding="utf-8"))
    assert saved == {"标题1": "第一篇标题", "作者1": "作者A"}


@pytest.mark.asyncio
async def test_extract_rejects_empty_fields(tmp_path: Path, env_ready) -> None:
    cli = _ArtifactCLI(snapshots=["snap"] * 5, eval_responses={})
    # First decision: extract with empty fields → ValueError captured as
    # action error. Loop should keep going (not fatal).
    decisions = [
        Decision(action="extract", args={"fields": {}}),
        Decision(action="finish", args={"summary": "give up"}),
    ]
    maker = _ScriptedDecisionMaker(decisions)
    svc = BrowserTaskService(tmp_path, cli=cli, decision_factory=lambda task: maker)

    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="x", start_url="https://x")
    )
    svc.schedule(task)
    await _wait_until(svc, task.id, timeout=10.0)

    final = svc.storage.get_task(task.id)
    assert final is not None
    assert final.status is TaskStatus.COMPLETED  # graceful finish via second decision
    steps = svc.storage.list_steps(task.id)
    extract_steps = [s for s in steps if s.action_name == "extract"]
    assert len(extract_steps) == 1
    assert extract_steps[0].success is False
    assert "fields" in (extract_steps[0].error or "")


# ── Takeover / resume (M3.2) ───────────────────────────────────────────────


class _BlockingDecisionMaker:
    """Decision maker whose decide() blocks on an event so tests can race it."""

    def __init__(self, decisions: list[Decision]) -> None:
        self._queue = list(decisions)
        self.unblock = asyncio.Event()
        self.entered = asyncio.Event()
        self.calls = 0

    async def decide(self, *, instruction, snapshot, history) -> Decision:
        self.calls += 1
        self.entered.set()
        await self.unblock.wait()
        self.unblock.clear()
        return self._queue.pop(0)


@pytest.mark.asyncio
async def test_user_initiated_takeover_pauses_until_resume(tmp_path: Path, env_ready) -> None:
    """request_takeover pauses before LLM decide; request_resume continues."""
    cli = _ReactFakeCLI(["snap1", "snap2", "snap3"])
    maker = _BlockingDecisionMaker([
        Decision(action="click", args={"selector": "@e1"}),
        Decision(action="finish", args={"summary": "ok"}),
    ])
    svc = BrowserTaskService(tmp_path, cli=cli, decision_factory=lambda task: maker)

    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="x", start_url="https://x")
    )
    svc.schedule(task)

    # Wait until the loop is blocked inside the first decide() call.
    await asyncio.wait_for(maker.entered.wait(), timeout=2.0)
    # Issue takeover NOW — loop will see it on the next iteration after we unblock.
    assert svc.request_takeover(task.id, "用户测试接管") is True
    # Let the first decision finish so the loop reaches the takeover checkpoint.
    maker.entered.clear()
    maker.unblock.set()

    # Wait for AWAITING_USER (loop's next-iter checkpoint will catch it).
    for _ in range(200):
        await asyncio.sleep(0.02)
        current = svc.storage.get_task(task.id)
        if current and current.status is TaskStatus.AWAITING_USER:
            break
    current = svc.storage.get_task(task.id)
    assert current.status is TaskStatus.AWAITING_USER

    # Resume → should re-enter decide() for second decision.
    assert svc.request_resume(task.id) is True
    await asyncio.wait_for(maker.entered.wait(), timeout=2.0)
    maker.unblock.set()  # release the finish decision
    await _wait_until(svc, task.id, timeout=5.0)
    final = svc.storage.get_task(task.id)
    assert final.status is TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_browser_guard_pauses_before_llm_and_resume_note_reaches_history(
    tmp_path: Path,
    env_ready,
) -> None:
    cli = _ReactFakeCLI([
        "登录 手机号 验证码 安全验证",
        "搜索结果列表 @e1",
        "搜索结果列表 @e1",
    ])
    decisions = [Decision(action="finish", args={"summary": "done"})]
    maker = _ScriptedDecisionMaker(decisions)
    svc = BrowserTaskService(tmp_path, cli=cli, decision_factory=lambda task: maker)

    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="x", start_url="https://x")
    )
    svc.schedule(task)

    for _ in range(200):
        await asyncio.sleep(0.02)
        current = svc.storage.get_task(task.id)
        if current and current.status is TaskStatus.AWAITING_USER:
            break

    current = svc.storage.get_task(task.id)
    assert current is not None
    assert current.status is TaskStatus.AWAITING_USER
    assert maker.calls == []

    assert svc.request_resume(task.id, note="我已完成登录并停在搜索结果页") is True
    await _wait_until(svc, task.id, timeout=5.0)
    final = svc.storage.get_task(task.id)
    assert final is not None
    assert final.status is TaskStatus.COMPLETED
    assert maker.calls[0]["history_len"] == 1

    steps = svc.storage.list_steps(task.id)
    await_steps = [s for s in steps if s.action_name == "await_user"]
    resume_steps = [s for s in steps if s.action_name == "resume"]
    assert await_steps[0].action_args == {"reason": "browser_guard"}
    assert "完成登录" in (resume_steps[0].observation or "")


@pytest.mark.asyncio
async def test_stuck_detector_triggers_awaiting_user(tmp_path: Path, env_ready) -> None:
    """When snapshots stop changing, the loop should auto-pause for user help."""
    # Same snapshot 6+ times — detector default threshold is 4 unchanged.
    cli = _ReactFakeCLI(["same"] * 12)
    # LLM keeps proposing different actions (so REPEATED_FAILURE doesn't trip first).
    decisions = [
        Decision(action="click", args={"selector": "@e1"}),
        Decision(action="scroll", args={"direction": "down"}),
        Decision(action="click", args={"selector": "@e2"}),
        Decision(action="scroll", args={"direction": "up"}),
        Decision(action="click", args={"selector": "@e3"}),
        Decision(action="finish", args={"summary": "after resume"}),
    ]
    maker = _ScriptedDecisionMaker(decisions)
    svc = BrowserTaskService(tmp_path, cli=cli, decision_factory=lambda task: maker)

    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="x", start_url="https://x", max_steps=20)
    )
    svc.schedule(task)

    # Wait for AWAITING_USER.
    for _ in range(200):
        await asyncio.sleep(0.02)
        current = svc.storage.get_task(task.id)
        if current and current.status is TaskStatus.AWAITING_USER:
            break
    current = svc.storage.get_task(task.id)
    assert current is not None
    assert current.status is TaskStatus.AWAITING_USER, f"expected AWAITING_USER, got {current.status}"

    # Resume → loop continues to finish.
    assert svc.request_resume(task.id) is True
    await _wait_until(svc, task.id, timeout=5.0)
    final = svc.storage.get_task(task.id)
    assert final.status is TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_cancel_during_awaiting_user_marks_cancelled(tmp_path: Path, env_ready) -> None:
    cli = _ReactFakeCLI(["same"] * 12)
    decisions = [Decision(action="click", args={"selector": "@e1"}) for _ in range(10)]
    maker = _ScriptedDecisionMaker(decisions)
    svc = BrowserTaskService(tmp_path, cli=cli, decision_factory=lambda task: maker)

    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="x", start_url="https://x")
    )
    svc.schedule(task)
    svc.request_takeover(task.id)
    for _ in range(100):
        await asyncio.sleep(0.02)
        current = svc.storage.get_task(task.id)
        if current and current.status is TaskStatus.AWAITING_USER:
            break

    assert svc.request_cancel(task.id) is True
    # Need to also unblock the resume wait — request_cancel does that via the cancel event.
    await _wait_until(svc, task.id, timeout=5.0)
    final = svc.storage.get_task(task.id)
    assert final.status is TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_request_takeover_returns_false_when_task_not_running(tmp_path: Path) -> None:
    svc = BrowserTaskService(tmp_path)
    assert svc.request_takeover("nonexistent") is False
    assert svc.request_resume("nonexistent") is False


@pytest.mark.asyncio
async def test_takeover_does_not_stream_screenshot_frames(tmp_path: Path, env_ready) -> None:
    """Awaiting-user mode relies on the visible browser, not screenshot streaming."""
    cli = _ReactFakeCLI(["snap1", "snap2"])
    maker = _BlockingDecisionMaker([
        Decision(action="click", args={"selector": "@e1"}),
        Decision(action="finish", args={"summary": "ok"}),
    ])
    svc = BrowserTaskService(tmp_path, cli=cli, decision_factory=lambda task: maker)
    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="x", start_url="https://x")
    )
    svc.schedule(task)

    await asyncio.wait_for(maker.entered.wait(), timeout=2.0)
    svc.request_takeover(task.id)
    maker.entered.clear()
    maker.unblock.set()

    # Wait for awaiting_user.
    for _ in range(200):
        await asyncio.sleep(0.02)
        current = svc.storage.get_task(task.id)
        if current and current.status is TaskStatus.AWAITING_USER:
            break

    artifacts_before = len(svc.storage.list_artifacts(task.id))
    # Sit in awaiting_user for ~1.5 seconds; no fake video frames should appear.
    await asyncio.sleep(1.5)
    artifacts_after = len(svc.storage.list_artifacts(task.id))
    assert artifacts_after == artifacts_before

    # Resume and let the task complete cleanly.
    svc.request_resume(task.id)
    await asyncio.wait_for(maker.entered.wait(), timeout=2.0)
    maker.unblock.set()
    await _wait_until(svc, task.id, timeout=5.0)


@pytest.mark.asyncio
async def test_no_screenshot_frames_after_resume(tmp_path: Path, env_ready) -> None:
    """Resuming keeps the task free of implicit screenshot artifacts."""
    cli = _ReactFakeCLI(["snap"] * 4)
    maker = _BlockingDecisionMaker([
        Decision(action="click", args={"selector": "@e1"}),
        Decision(action="finish", args={"summary": "ok"}),
    ])
    svc = BrowserTaskService(tmp_path, cli=cli, decision_factory=lambda task: maker)
    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="x", start_url="https://x")
    )
    svc.schedule(task)
    await asyncio.wait_for(maker.entered.wait(), timeout=2.0)
    svc.request_takeover(task.id)
    maker.entered.clear()
    maker.unblock.set()

    for _ in range(200):
        await asyncio.sleep(0.02)
        if svc.storage.get_task(task.id).status is TaskStatus.AWAITING_USER:
            break

    # Resume immediately and wait for next decide() to fire.
    svc.request_resume(task.id)
    await asyncio.wait_for(maker.entered.wait(), timeout=2.0)

    # Snapshot artifact count, wait, snapshot again; it should not grow because
    # the loop no longer records implicit visual frames.
    count_before = len(svc.storage.list_artifacts(task.id))
    await asyncio.sleep(1.2)
    count_after = len(svc.storage.list_artifacts(task.id))
    assert count_after == count_before, (
        f"got {count_after - count_before} implicit screenshot artifacts"
    )

    # Let the task wrap up.
    maker.unblock.set()
    await _wait_until(svc, task.id, timeout=5.0)


# ── Event emitter integration (M2.5) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_task_emits_status_step_and_artifact_events(tmp_path: Path, env_ready) -> None:
    cli = _ArtifactCLI(
        snapshots=["snap1", "snap2", "snap3"],
        eval_responses={"document.body": "captured text"},
    )
    # Explicit save_page_text emits an artifact; normal actions no longer
    # create implicit screenshot frames.
    decisions = [
        Decision(action="save_page_text", args={"label": "page"}),
        Decision(action="finish", args={"summary": "ok"}),
    ]
    maker = _ScriptedDecisionMaker(decisions)

    received: list[dict] = []

    async def emitter(task_id: str, event: dict) -> None:
        received.append({"task": task_id, **event})

    svc = BrowserTaskService(
        tmp_path,
        cli=cli,
        decision_factory=lambda task: maker,
        event_emitter=emitter,
    )
    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="x", start_url="https://x")
    )
    svc.schedule(task)
    await _wait_until(svc, task.id, timeout=10.0)
    # Allow the loop to drain queued create_task callbacks for emit.
    await asyncio.sleep(0.1)

    types = [e["type"] for e in received]
    assert "status" in types  # running + completed
    assert "step" in types
    assert "artifact" in types
    statuses = [e["status"] for e in received if e["type"] == "status"]
    assert statuses[0] == "running"
    assert statuses[-1] == "completed"


@pytest.mark.asyncio
async def test_emit_swallows_subscriber_errors(tmp_path: Path, env_ready) -> None:
    """A failing emitter must not crash the task loop."""
    cli = _ReactFakeCLI(["snap"])
    decisions = [Decision(action="finish", args={"summary": "ok"})]
    maker = _ScriptedDecisionMaker(decisions)

    async def angry_emitter(task_id: str, event: dict) -> None:
        raise RuntimeError("subscriber blew up")

    svc = BrowserTaskService(
        tmp_path,
        cli=cli,
        decision_factory=lambda task: maker,
        event_emitter=angry_emitter,
    )
    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="x", start_url="https://x")
    )
    svc.schedule(task)
    await _wait_until(svc, task.id, timeout=10.0)
    await asyncio.sleep(0.1)

    final = svc.storage.get_task(task.id)
    assert final is not None
    assert final.status is TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_model_override_persisted_in_metadata(tmp_path: Path, env_ready) -> None:
    cli = _FakeCLI()
    svc = BrowserTaskService(tmp_path, cli=cli)
    task = svc.create_task(
        CreateTaskRequest(
            project_id="p",
            instruction="x",
            start_url="https://x",
            model_override="anthropic/claude-haiku-4-5",
        )
    )
    fetched = svc.storage.get_task(task.id)
    assert fetched is not None
    assert fetched.metadata.get("model_override") == "anthropic/claude-haiku-4-5"


def test_continue_task_reuses_task_and_records_user_turn(tmp_path: Path) -> None:
    svc = BrowserTaskService(tmp_path, cli=_FakeCLI())
    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="打开小红书", start_url="https://x")
    )
    svc.storage.update_task(
        task.id,
        status=TaskStatus.COMPLETED,
        result_summary="完成",
        step_count=2,
        finished_at=datetime.now(),
    )

    continued = svc.continue_task(
        task.id,
        ContinueTaskRequest(instruction="继续点赞第二个帖子"),
    )

    assert continued.id == task.id
    assert continued.status is TaskStatus.PENDING
    assert continued.instruction == "继续点赞第二个帖子"
    assert continued.start_url is None
    assert continued.result_summary is None
    assert continued.error_detail is None
    assert continued.step_count == 3
    assert continued.metadata["turns"][0]["content"] == "打开小红书"
    assert continued.metadata["turns"][-1]["content"] == "继续点赞第二个帖子"

    steps = svc.storage.list_steps(task.id)
    assert steps[-1].phase is StepPhase.INTERVENTION
    assert steps[-1].action_name == "user_instruction"
    assert steps[-1].thinking == "继续点赞第二个帖子"


def test_continue_task_rejects_running_task(tmp_path: Path) -> None:
    svc = BrowserTaskService(tmp_path, cli=_FakeCLI())
    task = svc.create_task(
        CreateTaskRequest(project_id="p", instruction="x", start_url="https://x")
    )
    svc.storage.update_task(task.id, status=TaskStatus.RUNNING)

    with pytest.raises(ValueError):
        svc.continue_task(task.id, ContinueTaskRequest(instruction="继续"))
