"""Tests for agent-browser environment detection."""

from __future__ import annotations

import pytest

import tokenmind.browser_agent.env_check as env_check


class _FakeProc:
    def __init__(self, stdout: bytes, stderr: bytes = b"", returncode: int = 0) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


@pytest.mark.asyncio
async def test_check_environment_uses_resolved_windows_cmd_shim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, tuple[str, ...]] = {}

    async def fake_exec(*cmd: str, stdout=None, stderr=None) -> _FakeProc:
        captured["cmd"] = cmd
        return _FakeProc(b"agent-browser 0.26.0\n")

    monkeypatch.setattr(
        env_check,
        "resolve_agent_browser_binary",
        lambda: r"C:\Users\me\AppData\Roaming\npm\agent-browser.cmd",
    )
    monkeypatch.setattr(env_check.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(env_check, "_has_chrome_for_testing", lambda: True)

    result = await env_check.check_environment()

    assert captured["cmd"][:2] == (
        r"C:\Users\me\AppData\Roaming\npm\agent-browser.cmd",
        "--version",
    )
    assert result.is_ready is True
    assert result.version == "0.26.0"


@pytest.mark.asyncio
async def test_check_environment_does_not_run_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[tuple[str, ...]] = []

    async def fake_exec(*cmd: str, stdout=None, stderr=None) -> _FakeProc:
        commands.append(cmd)
        return _FakeProc(b"agent-browser 0.26.0\n")

    monkeypatch.setattr(env_check, "resolve_agent_browser_binary", lambda: "agent-browser.cmd")
    monkeypatch.setattr(env_check.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(env_check, "_has_chrome_for_testing", lambda: True)

    result = await env_check.check_environment()

    assert result.is_ready is True
    assert commands == [("agent-browser.cmd", "--version")]


@pytest.mark.asyncio
async def test_check_environment_reports_missing_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(env_check, "resolve_agent_browser_binary", lambda: "agent-browser")
    monkeypatch.setattr(env_check.shutil, "which", lambda _candidate: None)

    result = await env_check.check_environment()

    assert result.cli_installed is False
    assert result.chrome_installed is False
    assert result.is_ready is False
