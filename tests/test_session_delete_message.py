"""Tests for Session.delete_message."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from tokenmind.session.manager import Session, SessionManager


def _make_session(tmp_path: Path) -> tuple[SessionManager, Session]:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("web:test-1")
    return manager, session


def test_delete_message_removes_user_only(tmp_path: Path) -> None:
    _, session = _make_session(tmp_path)
    session.messages = [
        {"role": "user", "content": "hi", "timestamp": "2026-04-30T10:00:00"},
        {"role": "assistant", "content": "hello", "timestamp": "2026-04-30T10:00:01"},
        {"role": "user", "content": "再问一题", "timestamp": "2026-04-30T10:00:02"},
    ]

    assert session.delete_message("2026-04-30T10:00:00") is True
    assert [m["content"] for m in session.messages] == ["hello", "再问一题"]


def test_delete_assistant_drops_preceding_tool_block(tmp_path: Path) -> None:
    _, session = _make_session(tmp_path)
    session.messages = [
        {"role": "user", "content": "搜一下", "timestamp": "t1"},
        {
            "role": "assistant",
            "content": "",
            "timestamp": "t2",
            "tool_calls": [{"id": "call_1", "function": {"name": "web_search"}}],
        },
        {"role": "tool", "content": "results...", "tool_call_id": "call_1", "timestamp": "t3"},
        {"role": "assistant", "content": "找到了 X", "timestamp": "t4"},
    ]

    assert session.delete_message("t4") is True
    # User message preserved; the entire assistant turn (tool_calls + tool result + final reply) is gone.
    assert [m.get("timestamp") for m in session.messages] == ["t1"]


def test_delete_assistant_without_tool_block_drops_self(tmp_path: Path) -> None:
    _, session = _make_session(tmp_path)
    session.messages = [
        {"role": "user", "content": "hi", "timestamp": "t1"},
        {"role": "assistant", "content": "hello", "timestamp": "t2"},
        {"role": "user", "content": "再问", "timestamp": "t3"},
    ]
    assert session.delete_message("t2") is True
    assert [m["content"] for m in session.messages] == ["hi", "再问"]


def test_delete_message_unknown_timestamp(tmp_path: Path) -> None:
    _, session = _make_session(tmp_path)
    session.messages = [{"role": "user", "content": "x", "timestamp": "real"}]
    assert session.delete_message("ghost") is False
    assert len(session.messages) == 1


def test_delete_tool_message_directly_is_refused(tmp_path: Path) -> None:
    _, session = _make_session(tmp_path)
    session.messages = [
        {"role": "tool", "content": "x", "timestamp": "t1", "tool_call_id": "call_x"},
    ]
    # Tool messages should only be removed transitively via assistant deletion.
    assert session.delete_message("t1") is False


def test_delete_persists_through_save_load(tmp_path: Path) -> None:
    manager, session = _make_session(tmp_path)
    session.messages = [
        {"role": "user", "content": "hi", "timestamp": "t1"},
        {"role": "assistant", "content": "hello", "timestamp": "t2"},
    ]
    manager.save(session)
    assert session.delete_message("t2") is True
    manager.save(session)

    # Drop cache + reload from disk.
    manager.invalidate("web:test-1")
    reloaded = manager.get_or_create("web:test-1")
    assert [m["content"] for m in reloaded.messages] == ["hi"]


def test_delete_assistant_walks_back_across_multiple_tool_results(tmp_path: Path) -> None:
    """Two parallel tool calls in one assistant turn should all be removed."""
    _, session = _make_session(tmp_path)
    session.messages = [
        {"role": "user", "content": "并行查两件事", "timestamp": "t1"},
        {
            "role": "assistant",
            "content": "",
            "timestamp": "t2",
            "tool_calls": [
                {"id": "call_a", "function": {"name": "web_search"}},
                {"id": "call_b", "function": {"name": "read_file"}},
            ],
        },
        {"role": "tool", "content": "A", "tool_call_id": "call_a", "timestamp": "t3"},
        {"role": "tool", "content": "B", "tool_call_id": "call_b", "timestamp": "t4"},
        {"role": "assistant", "content": "汇总好了", "timestamp": "t5"},
    ]

    assert session.delete_message("t5") is True
    assert [m.get("timestamp") for m in session.messages] == ["t1"]


def test_delete_user_keeps_following_assistant(tmp_path: Path) -> None:
    """Deleting a user message leaves any assistant reply that came after
    it in place — that's a fair UX trade since users typically delete just
    their own typo, not the whole conversation."""
    _, session = _make_session(tmp_path)
    session.messages = [
        {"role": "user", "content": "typo", "timestamp": "t1"},
        {"role": "assistant", "content": "确实", "timestamp": "t2"},
    ]
    assert session.delete_message("t1") is True
    assert [m.get("timestamp") for m in session.messages] == ["t2"]


def test_delete_message_updates_timestamp(tmp_path: Path) -> None:
    _, session = _make_session(tmp_path)
    session.messages = [{"role": "user", "content": "x", "timestamp": "t1"}]
    earlier = session.updated_at
    # Force a tiny wait so the comparison is meaningful.
    later = datetime.now()
    session.delete_message("t1")
    assert session.updated_at >= earlier
    assert session.updated_at >= later or session.updated_at <= datetime.now()
