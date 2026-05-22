"""Tests for FileEditTracker — live file-edit progress events driven by
streaming tool-call deltas.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tokenmind.agent.file_edit_tracker import (
    FileEditTracker,
    _extract_complete_json_string,
    _line_diff_stats,
    _read_snapshot,
    _scan_string_lines,
)

# ─── string scanners ─────────────────────────────────────────────────────


def test_extract_complete_returns_none_when_unclosed() -> None:
    assert _extract_complete_json_string('{"path": "incompl', "path") is None


def test_extract_complete_decodes_escapes() -> None:
    src = '{"path": "a\\nb"}'
    assert _extract_complete_json_string(src, "path") == "a\nb"


def test_extract_complete_decodes_unicode_escape() -> None:
    src = r'{"path": "aAb"}'
    assert _extract_complete_json_string(src, "path") == "aAb"


def test_extract_complete_missing_key_returns_none() -> None:
    assert _extract_complete_json_string('{"foo": "bar"}', "path") is None


def test_scan_lines_empty_string() -> None:
    assert _scan_string_lines('{"content": ""}', "content") == 0


def test_scan_lines_single_line_no_newline() -> None:
    assert _scan_string_lines('{"content": "abc"}', "content") == 1


def test_scan_lines_escaped_newlines_in_streaming_chunk() -> None:
    # Three escape sequences \n → three newlines → 4 lines (assuming trailing content).
    src = '{"content": "a\\nb\\nc\\nd'  # truncated mid-stream, no closing "
    assert _scan_string_lines(src, "content") == 4


def test_scan_lines_trailing_newline_does_not_overcount() -> None:
    src = '{"content": "a\\nb\\n'  # ends in newline, no closing quote yet
    assert _scan_string_lines(src, "content") == 2


def test_scan_lines_missing_key_returns_zero() -> None:
    assert _scan_string_lines('{"other": "abc"}', "content") == 0


# ─── diff helper ─────────────────────────────────────────────────────────


def test_line_diff_stats_pure_insert() -> None:
    assert _line_diff_stats("a\nb\n", "a\nb\nc\n") == (1, 0)


def test_line_diff_stats_pure_delete() -> None:
    assert _line_diff_stats("a\nb\nc\n", "a\n") == (0, 2)


def test_line_diff_stats_replace() -> None:
    added, deleted = _line_diff_stats("hello\n", "world\n")
    assert added == 1 and deleted == 1


# ─── snapshot ────────────────────────────────────────────────────────────


def test_snapshot_of_nonexistent_file(tmp_path: Path) -> None:
    snap = _read_snapshot(tmp_path / "nope.txt")
    assert snap.exists is False
    assert snap.text == ""
    assert snap.line_count == 0


def test_snapshot_of_text_file(tmp_path: Path) -> None:
    f = tmp_path / "hi.txt"
    f.write_text("a\nb\nc\n")
    snap = _read_snapshot(f)
    assert snap.exists is True
    assert snap.text == "a\nb\nc\n"
    assert snap.line_count == 3


def test_snapshot_of_binary_file(tmp_path: Path) -> None:
    f = tmp_path / "blob.bin"
    f.write_bytes(b"\x00\x01\x02")
    snap = _read_snapshot(f)
    assert snap.exists is True
    assert snap.text is None  # binary detected


# ─── tracker live events ─────────────────────────────────────────────────


def _events_sink() -> tuple[list[dict[str, Any]], Any]:
    events: list[dict[str, Any]] = []

    async def emit(e: dict[str, Any]) -> None:
        events.append(e)

    return events, emit


@pytest.mark.asyncio
async def test_untracked_tool_emits_nothing(tmp_path: Path) -> None:
    events, emit = _events_sink()
    tracker = FileEditTracker(workspace=tmp_path, emit=emit)
    await tracker.on_delta({
        "index": 0, "call_id": "c1", "name": "read_file",
        "arguments_delta": '{"path": "a.txt"}',
        "arguments": '{"path": "a.txt"}',
    })
    assert events == []


@pytest.mark.asyncio
async def test_write_file_emits_start_once_path_known(tmp_path: Path) -> None:
    events, emit = _events_sink()
    tracker = FileEditTracker(workspace=tmp_path, emit=emit)
    # Streaming arrives in chunks; only the second has a full path.
    await tracker.on_delta({
        "index": 0, "call_id": "c1", "name": "write_file",
        "arguments_delta": '{"path"', "arguments": '{"path"',
    })
    assert events == []  # path not closed yet
    await tracker.on_delta({
        "index": 0, "call_id": "c1", "name": "write_file",
        "arguments_delta": ': "new.txt", "content": "abc',
        "arguments": '{"path": "new.txt", "content": "abc',
    })
    assert len(events) == 1
    e = events[0]
    assert e["tool"] == "write_file"
    assert e["path"] == "new.txt"
    assert e["phase"] == "start"
    assert e["added"] == 1
    assert e["deleted"] == 0
    assert e["approximate"] is True


@pytest.mark.asyncio
async def test_edit_file_counts_old_and_new(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("alpha\nbravo\n")

    events, emit = _events_sink()
    tracker = FileEditTracker(workspace=tmp_path, emit=emit)
    await tracker.on_delta({
        "index": 0, "call_id": "c2", "name": "edit_file",
        "arguments_delta": "",
        "arguments": '{"path": "a.txt", "old_text": "alpha\\nbravo", "new_text": "alpha\\nBRAVO\\nCHARLIE"',
    })
    assert len(events) == 1
    assert events[0]["added"] == 3
    assert events[0]["deleted"] == 2


@pytest.mark.asyncio
async def test_throttle_collapses_rapid_no_change_deltas(tmp_path: Path) -> None:
    events, emit = _events_sink()
    tracker = FileEditTracker(workspace=tmp_path, emit=emit)
    payload = {
        "index": 0, "call_id": "c", "name": "write_file",
        "arguments_delta": "", "arguments": '{"path": "x.txt", "content": "a',
    }
    await tracker.on_delta(payload)
    # Repeating an identical delta should not emit again.
    await tracker.on_delta(payload)
    await tracker.on_delta(payload)
    assert len(events) == 1


@pytest.mark.asyncio
async def test_big_line_jump_forces_emit_even_within_interval(tmp_path: Path) -> None:
    events, emit = _events_sink()
    tracker = FileEditTracker(workspace=tmp_path, emit=emit)
    await tracker.on_delta({
        "index": 0, "call_id": "c", "name": "write_file",
        "arguments_delta": "",
        "arguments": '{"path": "y.txt", "content": "a',
    })
    assert len(events) == 1
    # Bump well past the line-step threshold.
    big_content = '{"path": "y.txt", "content": "' + ("a\\n" * 40)
    await tracker.on_delta({
        "index": 0, "call_id": "c", "name": "write_file",
        "arguments_delta": "",
        "arguments": big_content,
    })
    assert len(events) == 2
    assert events[1]["added"] >= 24


@pytest.mark.asyncio
async def test_finalize_emits_exact_diff(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("hello\n")

    events, emit = _events_sink()
    tracker = FileEditTracker(workspace=tmp_path, emit=emit)
    # Stream the call.
    await tracker.on_delta({
        "index": 0, "call_id": "c1", "name": "edit_file",
        "arguments_delta": "",
        "arguments": '{"path": "a.txt", "old_text": "hello", "new_text": "world"}',
    })
    # Simulate the tool actually running.
    f.write_text("world\n")
    await tracker.finalize("c1", status="done")

    assert events[-1]["phase"] == "end"
    assert events[-1]["status"] == "done"
    assert events[-1]["added"] == 1
    assert events[-1]["deleted"] == 1
    assert events[-1]["approximate"] is False


@pytest.mark.asyncio
async def test_finalize_error_passes_through_message(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("hi\n")

    events, emit = _events_sink()
    tracker = FileEditTracker(workspace=tmp_path, emit=emit)
    await tracker.on_delta({
        "index": 0, "call_id": "c1", "name": "edit_file",
        "arguments_delta": "",
        "arguments": '{"path": "a.txt", "old_text": "hi", "new_text": "bye"}',
    })
    await tracker.finalize("c1", status="error", error="Error: read_file required first")

    final = events[-1]
    assert final["phase"] == "error"
    assert final["status"] == "error"
    assert "read_file" in final["error"]


@pytest.mark.asyncio
async def test_finalize_unknown_call_id_is_silent(tmp_path: Path) -> None:
    events, emit = _events_sink()
    tracker = FileEditTracker(workspace=tmp_path, emit=emit)
    # Never called on_delta for this id.
    await tracker.finalize("ghost", status="done")
    assert events == []


@pytest.mark.asyncio
async def test_path_is_relative_to_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    nested = workspace / "src"
    nested.mkdir()

    events, emit = _events_sink()
    tracker = FileEditTracker(workspace=workspace, emit=emit)
    await tracker.on_delta({
        "index": 0, "call_id": "c1", "name": "write_file",
        "arguments_delta": "",
        "arguments": '{"path": "src/x.txt", "content": "abc',
    })
    assert events[0]["path"] == "src/x.txt"


@pytest.mark.asyncio
async def test_parallel_calls_tracked_independently(tmp_path: Path) -> None:
    events, emit = _events_sink()
    tracker = FileEditTracker(workspace=tmp_path, emit=emit)
    await tracker.on_delta({
        "index": 0, "call_id": "ca", "name": "write_file",
        "arguments_delta": "",
        "arguments": '{"path": "a.txt", "content": "x\\ny',
    })
    await tracker.on_delta({
        "index": 1, "call_id": "cb", "name": "write_file",
        "arguments_delta": "",
        "arguments": '{"path": "b.txt", "content": "z',
    })
    # Two distinct start events, one per call.
    starts = [e for e in events if e["phase"] == "start"]
    assert len(starts) == 2
    paths = {e["path"]: e for e in starts}
    assert "a.txt" in paths
    assert "b.txt" in paths
    assert paths["a.txt"]["added"] == 2
    assert paths["b.txt"]["added"] == 1


@pytest.mark.asyncio
async def test_call_id_arrives_late_still_finds_state(tmp_path: Path) -> None:
    """Some providers send call_id only on the first chunk; subsequent
    chunks only carry index. The tracker should still attribute them
    correctly."""
    events, emit = _events_sink()
    tracker = FileEditTracker(workspace=tmp_path, emit=emit)
    # First chunk has no id, only index.
    await tracker.on_delta({
        "index": 0, "call_id": None, "name": "write_file",
        "arguments_delta": "", "arguments": '{"path": "a.txt", "content": "x',
    })
    # Second chunk introduces the id.
    await tracker.on_delta({
        "index": 0, "call_id": "late_id", "name": "write_file",
        "arguments_delta": "", "arguments": '{"path": "a.txt", "content": "x\\ny',
    })
    # finalize() called with the late id should find the state.
    await tracker.finalize("late_id", status="done")
    end_events = [e for e in events if e["phase"] == "end"]
    assert len(end_events) == 1


@pytest.mark.asyncio
async def test_streaming_handler_integration_emits_through_on_progress(
    tmp_path: Path,
) -> None:
    """End-to-end: AgentStreamingHandler routes file-edit events through
    the on_progress callback with the _file_edit_progress meta key."""
    from tokenmind.agent.streaming import AgentStreamingHandler

    captured: list[tuple[str, dict[str, Any]]] = []

    async def on_progress(content: str, **meta: Any) -> None:
        captured.append((content, meta))

    handler = AgentStreamingHandler(on_progress=on_progress, workspace=tmp_path)
    await handler.on_tool_call_delta({
        "index": 0, "call_id": "c1", "name": "write_file",
        "arguments_delta": "",
        "arguments": '{"path": "x.txt", "content": "hi',
    })
    assert len(captured) == 1
    text, meta = captured[0]
    assert text == ""
    assert "_file_edit_progress" in meta
    event = meta["_file_edit_progress"]
    assert event["tool"] == "write_file"
    assert event["path"] == "x.txt"
    assert event["added"] == 1
