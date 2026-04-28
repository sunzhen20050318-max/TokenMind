"""Unit tests for the agent-browser CLI subprocess wrapper.

We mock asyncio.create_subprocess_exec so the tests don't depend on the
real ``agent-browser`` binary being installed.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from tokenmind.browser_agent.cli import AgentBrowserCLI, AgentBrowserError


class _FakeProc:
    def __init__(self, stdout: bytes, stderr: bytes = b"", returncode: int = 0) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr

    def kill(self) -> None:
        return None


def _patch_subprocess(stdout: dict | list, *, returncode: int = 0, stderr: str = ""):
    payload = json.dumps(stdout).encode("utf-8")
    fake_proc = _FakeProc(payload, stderr.encode("utf-8"), returncode)
    return patch(
        "tokenmind.browser_agent.cli.asyncio.create_subprocess_exec",
        AsyncMock(return_value=fake_proc),
    )


@pytest.mark.asyncio
async def test_run_returns_dict_envelope() -> None:
    cli = AgentBrowserCLI()
    with _patch_subprocess({"success": True, "data": {"url": "https://x"}, "error": None}):
        result = await cli.run("proj_a", "snapshot")
    assert result["success"] is True
    assert result["data"]["url"] == "https://x"


@pytest.mark.asyncio
async def test_run_raises_on_success_false() -> None:
    cli = AgentBrowserCLI()
    with _patch_subprocess({"success": False, "data": None, "error": "boom"}):
        with pytest.raises(AgentBrowserError, match="boom"):
            await cli.run("proj_a", "open", "https://x")


@pytest.mark.asyncio
async def test_run_raises_on_nonzero_exit() -> None:
    cli = AgentBrowserCLI()
    with _patch_subprocess({}, returncode=1, stderr="missing chrome"):
        with pytest.raises(AgentBrowserError, match="missing chrome"):
            await cli.run("proj_a", "open", "https://x")


@pytest.mark.asyncio
async def test_batch_response_wrapped_as_success() -> None:
    cli = AgentBrowserCLI()
    with _patch_subprocess([{"success": True, "data": {"i": 1}}, {"success": True, "data": {"i": 2}}]):
        result = await cli.run("proj_a", "batch")
    assert result["success"] is True
    assert isinstance(result["data"], list)
    assert len(result["data"]) == 2


@pytest.mark.asyncio
async def test_run_raises_on_invalid_json() -> None:
    cli = AgentBrowserCLI()
    fake_proc = _FakeProc(b"not-json", b"", 0)
    with patch(
        "tokenmind.browser_agent.cli.asyncio.create_subprocess_exec",
        AsyncMock(return_value=fake_proc),
    ):
        with pytest.raises(AgentBrowserError, match="invalid JSON"):
            await cli.run("proj_a", "snapshot")


@pytest.mark.asyncio
async def test_helper_methods_pass_session_and_args() -> None:
    cli = AgentBrowserCLI()
    captured: dict[str, list[str]] = {}

    async def fake_exec(*cmd: str, stdout=None, stderr=None) -> _FakeProc:
        captured["cmd"] = list(cmd)
        return _FakeProc(json.dumps({"success": True, "data": {}, "error": None}).encode())

    with patch("tokenmind.browser_agent.cli.asyncio.create_subprocess_exec", side_effect=fake_exec):
        await cli.open_url("proj_a", "https://example.com")

    assert captured["cmd"][:5] == ["agent-browser", "--session", "proj_a", "--json", "open"]
    assert captured["cmd"][-1] == "https://example.com"
