"""Tests for FileStates and read-before-edit enforcement in filesystem tools."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from tokenmind.agent.tools.file_state import FileStates
from tokenmind.agent.tools.filesystem import EditFileTool, ReadFileTool

# ---------------------------------------------------------------------------
# FileStates unit tests
# ---------------------------------------------------------------------------


def test_check_without_record_returns_warning(tmp_path: Path) -> None:
    fs = FileStates()
    fp = tmp_path / "a.txt"
    fp.write_text("hi")
    warn = fs.check_before_edit("s1", fp)
    assert warn is not None
    assert "read_file" in warn


def test_record_then_check_passes(tmp_path: Path) -> None:
    fs = FileStates()
    fp = tmp_path / "a.txt"
    fp.write_text("hi")
    fs.record_read("s1", fp)
    assert fs.check_before_edit("s1", fp) is None


def test_external_modification_detected(tmp_path: Path) -> None:
    fs = FileStates()
    fp = tmp_path / "a.txt"
    fp.write_text("hi")
    fs.record_read("s1", fp)
    # Bump the mtime forward, simulating an external edit.
    new_mtime = fp.stat().st_mtime + 5.0
    os.utime(fp, (new_mtime, new_mtime))
    warn = fs.check_before_edit("s1", fp)
    assert warn is not None
    assert "modified" in warn


def test_records_are_session_scoped(tmp_path: Path) -> None:
    fs = FileStates()
    fp = tmp_path / "a.txt"
    fp.write_text("hi")
    fs.record_read("session-a", fp)
    assert fs.check_before_edit("session-a", fp) is None
    assert fs.check_before_edit("session-b", fp) is not None


def test_clear_session_drops_records(tmp_path: Path) -> None:
    fs = FileStates()
    fp = tmp_path / "a.txt"
    fp.write_text("hi")
    fs.record_read("s1", fp)
    fs.clear_session("s1")
    assert fs.check_before_edit("s1", fp) is not None


# ---------------------------------------------------------------------------
# Tool integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_without_prior_read_is_refused(tmp_path: Path) -> None:
    fs = FileStates()
    fp = tmp_path / "a.txt"
    fp.write_text("hello world")

    edit = EditFileTool(
        workspace=tmp_path,
        file_states=fs,
        get_session_key=lambda: "s1",
    )
    result = await edit.execute(path="a.txt", old_text="hello", new_text="hi")
    assert result.startswith("Error:")
    assert "read_file" in result
    # File untouched.
    assert fp.read_text() == "hello world"


@pytest.mark.asyncio
async def test_read_then_edit_succeeds(tmp_path: Path) -> None:
    fs = FileStates()
    fp = tmp_path / "a.txt"
    fp.write_text("hello world")

    sk = lambda: "s1"  # noqa: E731
    read = ReadFileTool(workspace=tmp_path, file_states=fs, get_session_key=sk)
    edit = EditFileTool(workspace=tmp_path, file_states=fs, get_session_key=sk)

    await read.execute(path="a.txt")
    result = await edit.execute(path="a.txt", old_text="hello", new_text="hi")
    assert result.startswith("Successfully")
    assert fp.read_text() == "hi world"


@pytest.mark.asyncio
async def test_external_modification_blocks_edit(tmp_path: Path) -> None:
    fs = FileStates()
    fp = tmp_path / "a.txt"
    fp.write_text("hello world")

    sk = lambda: "s1"  # noqa: E731
    read = ReadFileTool(workspace=tmp_path, file_states=fs, get_session_key=sk)
    edit = EditFileTool(workspace=tmp_path, file_states=fs, get_session_key=sk)

    await read.execute(path="a.txt")
    # Simulate external edit.
    new_mtime = fp.stat().st_mtime + 5.0
    os.utime(fp, (new_mtime, new_mtime))

    result = await edit.execute(path="a.txt", old_text="hello", new_text="hi")
    assert result.startswith("Error:")
    assert "modified" in result
    assert fp.read_text() == "hello world"


@pytest.mark.asyncio
async def test_back_to_back_edits_work_without_rereading(tmp_path: Path) -> None:
    """After an edit, the tool re-records the new state so the next edit
    on the same file doesn't require an explicit read_file in between."""
    fs = FileStates()
    fp = tmp_path / "a.txt"
    fp.write_text("alpha bravo charlie")

    sk = lambda: "s1"  # noqa: E731
    read = ReadFileTool(workspace=tmp_path, file_states=fs, get_session_key=sk)
    edit = EditFileTool(workspace=tmp_path, file_states=fs, get_session_key=sk)

    await read.execute(path="a.txt")
    # Many filesystems have 1s mtime resolution — sleep so the post-edit
    # mtime is strictly greater than the post-read mtime.
    time.sleep(1.05)
    r1 = await edit.execute(path="a.txt", old_text="alpha", new_text="A")
    assert r1.startswith("Successfully")
    r2 = await edit.execute(path="a.txt", old_text="bravo", new_text="B")
    assert r2.startswith("Successfully")
    assert fp.read_text() == "A B charlie"


@pytest.mark.asyncio
async def test_tools_without_file_states_are_unchanged(tmp_path: Path) -> None:
    """wiki_compile and similar non-session callers don't pass file_states —
    they should retain the original behavior (no guard)."""
    fp = tmp_path / "a.txt"
    fp.write_text("hello world")
    edit = EditFileTool(workspace=tmp_path)  # no file_states, no session
    result = await edit.execute(path="a.txt", old_text="hello", new_text="hi")
    assert result.startswith("Successfully")
    assert fp.read_text() == "hi world"


@pytest.mark.asyncio
async def test_read_without_session_key_does_not_crash(tmp_path: Path) -> None:
    """If get_session_key returns None (e.g. no active session), the read
    should still succeed but simply not record anything."""
    fs = FileStates()
    fp = tmp_path / "a.txt"
    fp.write_text("hello")
    read = ReadFileTool(
        workspace=tmp_path, file_states=fs, get_session_key=lambda: None
    )
    result = await read.execute(path="a.txt")
    assert "1| hello" in result
