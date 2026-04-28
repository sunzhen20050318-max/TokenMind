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


async def _capture_cmd(coro_factory, cli: AgentBrowserCLI) -> list[str]:
    """Helper: call the wrapper method and capture the argv it would launch."""
    captured: dict[str, list[str]] = {}

    async def fake_exec(*cmd: str, stdout=None, stderr=None) -> _FakeProc:
        captured["cmd"] = list(cmd)
        return _FakeProc(json.dumps({"success": True, "data": {}, "error": None}).encode())

    with patch("tokenmind.browser_agent.cli.asyncio.create_subprocess_exec", side_effect=fake_exec):
        await coro_factory(cli)
    return captured["cmd"]


@pytest.mark.asyncio
async def test_helper_methods_pass_session_and_args() -> None:
    cli = AgentBrowserCLI()
    cmd = await _capture_cmd(lambda c: c.open_url("proj_a", "https://example.com"), cli)
    assert cmd[:5] == ["agent-browser", "--session", "proj_a", "--json", "open"]
    assert cmd[-1] == "https://example.com"


@pytest.mark.asyncio
async def test_type_text_passes_text_as_separate_arg() -> None:
    """Free-text args go through argv, never a shell — no injection risk."""
    cli = AgentBrowserCLI()
    cmd = await _capture_cmd(
        lambda c: c.type_text("p", "@e1", "hello; rm -rf /"),
        cli,
    )
    assert cmd[-3:] == ["type", "@e1", "hello; rm -rf /"]


@pytest.mark.asyncio
async def test_fill_press_and_select_helpers() -> None:
    cli = AgentBrowserCLI()
    fill_cmd = await _capture_cmd(lambda c: c.fill("p", "@e2", "Alice"), cli)
    assert fill_cmd[-3:] == ["fill", "@e2", "Alice"]

    press_cmd = await _capture_cmd(lambda c: c.press("p", "Enter"), cli)
    assert press_cmd[-2:] == ["press", "Enter"]

    select_cmd = await _capture_cmd(lambda c: c.select("p", "@e3", ["red", "blue"]), cli)
    assert select_cmd[-4:] == ["select", "@e3", "red", "blue"]


@pytest.mark.asyncio
async def test_scroll_validates_direction() -> None:
    cli = AgentBrowserCLI()
    with pytest.raises(ValueError, match="invalid scroll direction"):
        await cli.scroll("p", "diagonal")


@pytest.mark.asyncio
async def test_scroll_with_pixels() -> None:
    cli = AgentBrowserCLI()
    cmd = await _capture_cmd(lambda c: c.scroll("p", "down", 800), cli)
    assert cmd[-3:] == ["scroll", "down", "800"]


@pytest.mark.asyncio
async def test_snapshot_options_propagate() -> None:
    cli = AgentBrowserCLI()
    cmd = await _capture_cmd(
        lambda c: c.snapshot("p", interactive_only=True, compact=True, depth=4, selector="main"),
        cli,
    )
    # Order matters: -i, -c, -d 4, -s main
    assert cmd[-6:] == ["-i", "-c", "-d", "4", "-s", "main"]


@pytest.mark.asyncio
async def test_get_and_is_state_helpers() -> None:
    cli = AgentBrowserCLI()
    text_cmd = await _capture_cmd(lambda c: c.get("p", "text", "@e1"), cli)
    assert text_cmd[-3:] == ["get", "text", "@e1"]

    visible_cmd = await _capture_cmd(lambda c: c.is_state("p", "visible", "@e1"), cli)
    assert visible_cmd[-3:] == ["is", "visible", "@e1"]


@pytest.mark.asyncio
async def test_navigation_helpers() -> None:
    cli = AgentBrowserCLI()
    for name in ("back", "forward", "reload"):
        cmd = await _capture_cmd(lambda c, n=name: getattr(c, n)("p"), cli)
        assert cmd[-1] == name


@pytest.mark.asyncio
async def test_eval_js_passes_expression_as_one_arg() -> None:
    cli = AgentBrowserCLI()
    expression = "document.querySelectorAll('a').length"
    cmd = await _capture_cmd(lambda c: c.eval_js("p", expression), cli)
    assert cmd[-2:] == ["eval", expression]


@pytest.mark.asyncio
async def test_batch_quotes_arguments() -> None:
    cli = AgentBrowserCLI()
    cmd = await _capture_cmd(
        lambda c: c.batch(
            "p",
            [("snapshot", "-i"), ("type", "@e1", "hello world"), ("screenshot",)],
            bail=True,
        ),
        cli,
    )
    # batch + --bail + 3 quoted command strings
    assert cmd[-5] == "batch"
    assert cmd[-4] == "--bail"
    assert cmd[-3] == "snapshot -i"
    assert cmd[-2] == "type @e1 'hello world'"
    assert cmd[-1] == "screenshot"


@pytest.mark.asyncio
async def test_batch_rejects_empty_commands() -> None:
    cli = AgentBrowserCLI()
    with pytest.raises(ValueError, match="at least one"):
        await cli.batch("p", [])


# ── M3.1: takeover (mouse / keyboard / viewport) ────────────────────────────


@pytest.mark.asyncio
async def test_mouse_move_passes_integer_coords() -> None:
    cli = AgentBrowserCLI()
    cmd = await _capture_cmd(lambda c: c.mouse_move("p", 123, 456), cli)
    assert cmd[-4:] == ["mouse", "move", "123", "456"]


@pytest.mark.asyncio
async def test_mouse_move_truncates_floats_to_int() -> None:
    cli = AgentBrowserCLI()
    cmd = await _capture_cmd(lambda c: c.mouse_move("p", 100.7, 200.3), cli)
    assert cmd[-4:] == ["mouse", "move", "100", "200"]


@pytest.mark.asyncio
async def test_mouse_down_up_default_left_button() -> None:
    cli = AgentBrowserCLI()
    down = await _capture_cmd(lambda c: c.mouse_down("p"), cli)
    up = await _capture_cmd(lambda c: c.mouse_up("p"), cli)
    assert down[-3:] == ["mouse", "down", "left"]
    assert up[-3:] == ["mouse", "up", "left"]


@pytest.mark.asyncio
async def test_mouse_down_validates_button() -> None:
    cli = AgentBrowserCLI()
    with pytest.raises(ValueError, match="invalid mouse button"):
        await cli.mouse_down("p", "foot")


@pytest.mark.asyncio
async def test_mouse_wheel_passes_dy_then_dx() -> None:
    cli = AgentBrowserCLI()
    cmd = await _capture_cmd(lambda c: c.mouse_wheel("p", -120, 30), cli)
    assert cmd[-4:] == ["mouse", "wheel", "-120", "30"]


@pytest.mark.asyncio
async def test_click_xy_uses_batched_move_down_up() -> None:
    cli = AgentBrowserCLI()
    cmd = await _capture_cmd(lambda c: c.click_xy("p", 50, 75), cli)
    # Last 5 args: batch + --bail + 3 quoted command strings
    assert cmd[-5:] == [
        "batch",
        "--bail",
        "mouse move 50 75",
        "mouse down left",
        "mouse up left",
    ]


@pytest.mark.asyncio
async def test_click_xy_validates_button() -> None:
    cli = AgentBrowserCLI()
    with pytest.raises(ValueError, match="invalid mouse button"):
        await cli.click_xy("p", 1, 2, button="foot")


@pytest.mark.asyncio
async def test_keyboard_type_passes_raw_text() -> None:
    cli = AgentBrowserCLI()
    cmd = await _capture_cmd(lambda c: c.keyboard_type("p", "hello world"), cli)
    assert cmd[-3:] == ["keyboard", "type", "hello world"]


@pytest.mark.asyncio
async def test_keyboard_insert_uses_inserttext_subcommand() -> None:
    cli = AgentBrowserCLI()
    cmd = await _capture_cmd(lambda c: c.keyboard_insert("p", "abc"), cli)
    assert cmd[-3:] == ["keyboard", "inserttext", "abc"]


@pytest.mark.asyncio
async def test_set_viewport_basic_and_with_scale() -> None:
    cli = AgentBrowserCLI()
    plain = await _capture_cmd(lambda c: c.set_viewport("p", 1280, 800), cli)
    assert plain[-4:] == ["set", "viewport", "1280", "800"]

    scaled = await _capture_cmd(lambda c: c.set_viewport("p", 1280, 800, scale=2), cli)
    assert scaled[-5:] == ["set", "viewport", "1280", "800", "2"]


@pytest.mark.asyncio
async def test_set_viewport_validates_size_and_scale() -> None:
    cli = AgentBrowserCLI()
    with pytest.raises(ValueError, match="invalid viewport size"):
        await cli.set_viewport("p", 0, 100)
    with pytest.raises(ValueError, match="invalid device scale"):
        await cli.set_viewport("p", 100, 100, scale=0)
