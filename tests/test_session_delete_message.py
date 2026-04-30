"""Tests for Session.delete_message."""

from __future__ import annotations

from pathlib import Path

from tokenmind.session.manager import Session, SessionManager


def _make_session(tmp_path: Path) -> tuple[SessionManager, Session]:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("web:test-1")
    return manager, session


def test_delete_user_drops_following_assistant_reply(tmp_path: Path) -> None:
    """Deleting a user message takes the assistant reply with it — that's
    the contract the chat UI relies on."""
    _, session = _make_session(tmp_path)
    session.messages = [
        {"role": "user", "content": "hi", "timestamp": "t1"},
        {"role": "assistant", "content": "hello", "timestamp": "t2"},
        {"role": "user", "content": "再问", "timestamp": "t3"},
    ]
    assert session.delete_message("t1") is True
    assert [m["content"] for m in session.messages] == ["再问"]


def test_delete_user_drops_full_tool_turn(tmp_path: Path) -> None:
    """A user-initiated turn often produces an assistant tool_calls message,
    one or more tool responses, and a final assistant content message.
    Deleting the user message clears all of them."""
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
        {"role": "user", "content": "下一题", "timestamp": "t5"},
    ]
    assert session.delete_message("t1") is True
    assert [m.get("timestamp") for m in session.messages] == ["t5"]


def test_delete_user_at_tail_drops_remainder(tmp_path: Path) -> None:
    _, session = _make_session(tmp_path)
    session.messages = [
        {"role": "user", "content": "保留", "timestamp": "t1"},
        {"role": "assistant", "content": "好的", "timestamp": "t2"},
        {"role": "user", "content": "撤回的", "timestamp": "t3"},
        {"role": "assistant", "content": "嗯嗯", "timestamp": "t4"},
    ]
    assert session.delete_message("t3") is True
    assert [m.get("timestamp") for m in session.messages] == ["t1", "t2"]


def test_delete_assistant_directly_is_refused(tmp_path: Path) -> None:
    """Assistant messages are removable only via the parent user message."""
    _, session = _make_session(tmp_path)
    session.messages = [
        {"role": "user", "content": "hi", "timestamp": "t1"},
        {"role": "assistant", "content": "hello", "timestamp": "t2"},
    ]
    assert session.delete_message("t2") is False
    assert len(session.messages) == 2


def test_delete_tool_message_directly_is_refused(tmp_path: Path) -> None:
    _, session = _make_session(tmp_path)
    session.messages = [
        {"role": "tool", "content": "x", "timestamp": "t1", "tool_call_id": "call_x"},
    ]
    assert session.delete_message("t1") is False


def test_delete_message_unknown_timestamp(tmp_path: Path) -> None:
    _, session = _make_session(tmp_path)
    session.messages = [{"role": "user", "content": "x", "timestamp": "real"}]
    assert session.delete_message("ghost") is False
    assert len(session.messages) == 1


def test_delete_persists_through_save_load(tmp_path: Path) -> None:
    manager, session = _make_session(tmp_path)
    session.messages = [
        {"role": "user", "content": "hi", "timestamp": "t1"},
        {"role": "assistant", "content": "hello", "timestamp": "t2"},
    ]
    manager.save(session)
    assert session.delete_message("t1") is True
    manager.save(session)

    manager.invalidate("web:test-1")
    reloaded = manager.get_or_create("web:test-1")
    assert reloaded.messages == []


def test_delete_user_with_only_self_drops_self(tmp_path: Path) -> None:
    """Edge case: a user message with nothing after it deletes just itself."""
    _, session = _make_session(tmp_path)
    session.messages = [
        {"role": "user", "content": "刚发的", "timestamp": "t1"},
    ]
    assert session.delete_message("t1") is True
    assert session.messages == []
