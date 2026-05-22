"""Tests for the title-summarizer retry behavior.

Previously the title task fired only on the very first user message and
gave up silently on failure (timeout, empty content, LLM refusal). Now
every user message in an untitled session re-triggers the task; the
source text is always pulled from the first stored user message so the
title still reflects the conversation's opening even when generated on
attempt #2 or #3.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from tokenmind.agent.loop import AgentLoop
from tokenmind.bus.events import InboundMessage
from tokenmind.bus.queue import MessageBus
from tokenmind.providers.base import LLMResponse


def _make_loop(tmp_path: Path) -> AgentLoop:
    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.chat = AsyncMock(return_value=LLMResponse(content="标题待定", finish_reason="stop"))
    return AgentLoop(bus=bus, provider=provider, workspace=tmp_path, model="test-model")


# ─── _first_user_message_text ────────────────────────────────────────────


def test_first_user_message_text_empty_session(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    session = SimpleNamespace(messages=[])
    assert loop._first_user_message_text(session) == ""


def test_first_user_message_text_plain_string(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    session = SimpleNamespace(messages=[
        {"role": "system", "content": "you are X"},
        {"role": "user", "content": "  你好啊，能帮我吗？  "},
        {"role": "assistant", "content": "好的"},
    ])
    assert loop._first_user_message_text(session) == "你好啊，能帮我吗？"


def test_first_user_message_text_multimodal_blocks(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    session = SimpleNamespace(messages=[
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "..."}},
            {"type": "text", "text": "请看这张图"},
        ]},
    ])
    assert loop._first_user_message_text(session) == "请看这张图"


def test_first_user_message_text_skips_non_user(tmp_path: Path) -> None:
    """Only ``user`` role counts — assistants / tools / system are skipped."""
    loop = _make_loop(tmp_path)
    session = SimpleNamespace(messages=[
        {"role": "tool", "content": "tool output"},
        {"role": "assistant", "content": "answer"},
        {"role": "user", "content": "first user msg"},
        {"role": "user", "content": "later user msg"},
    ])
    # First user wins, not "later user msg".
    assert loop._first_user_message_text(session) == "first user msg"


# ─── _summarize_session_title retry path ────────────────────────────────


@pytest.mark.asyncio
async def test_title_retry_uses_first_user_message_from_session(tmp_path: Path) -> None:
    """When the title task fires on message #2 (because attempt #1 failed
    silently), it should still summarize the original first user message,
    not the current one."""
    loop = _make_loop(tmp_path)
    session = loop.sessions.get_or_create("web:test-retry")
    # Simulate state mid-conversation: first user msg + assistant reply
    # already in place, user about to send message #2.
    session.messages = [
        {"role": "user", "content": "帮我写一首关于秋天的诗"},
        {"role": "assistant", "content": "好的，这是一首..."},
    ]
    loop.sessions.save(session)

    # message #2 — title task is now retrying.
    msg = InboundMessage(
        channel="web", sender_id="user1", chat_id="test-retry",
        content="再来一首关于春天的", session_key_override="web:test-retry",
    )

    captured: list[str] = []

    async def fake_call(first_message: str, *, session_key: str | None = None) -> str | None:
        captured.append(first_message)
        return "秋天主题诗歌"

    loop._call_title_summarizer = fake_call  # type: ignore[method-assign]

    await loop._summarize_session_title(msg)

    # Source text must be the FIRST user message, not message #2.
    assert captured == ["帮我写一首关于秋天的诗"]
    refetched = loop.sessions.get_or_create("web:test-retry")
    assert refetched.title == "秋天主题诗歌"
    assert refetched.metadata.get("auto_titled") is True


@pytest.mark.asyncio
async def test_title_failure_leaves_auto_titled_false_so_next_message_retries(
    tmp_path: Path,
) -> None:
    """If the LLM returns empty, ``auto_titled`` must NOT be set —
    otherwise the next message wouldn't retry."""
    loop = _make_loop(tmp_path)
    session = loop.sessions.get_or_create("web:test-fail")
    session.messages = [{"role": "user", "content": "你好"}]
    loop.sessions.save(session)

    msg = InboundMessage(
        channel="web", sender_id="user1", chat_id="test-fail",
        content="你好", session_key_override="web:test-fail",
    )

    async def fake_call_returning_empty(first_message: str, **_: object) -> str | None:
        return None  # simulate timeout / refusal / empty content

    loop._call_title_summarizer = fake_call_returning_empty  # type: ignore[method-assign]

    await loop._summarize_session_title(msg)

    refetched = loop.sessions.get_or_create("web:test-fail")
    assert refetched.metadata.get("auto_titled") is not True
    # _title_in_flight must be cleared even on failure, otherwise the next
    # retry would short-circuit out.
    assert "web:test-fail" not in loop._title_in_flight


@pytest.mark.asyncio
async def test_title_skip_when_first_message_is_single_char(tmp_path: Path) -> None:
    """Single-char inputs ("?" / "a") are too thin to summarise — the
    task should return early without touching the LLM. Two-char Chinese
    greetings ("你好" / "嗨啊") are fine and DO get summarised."""
    loop = _make_loop(tmp_path)
    msg = InboundMessage(
        channel="web", sender_id="user1", chat_id="too-short",
        content="a", session_key_override="web:too-short",
    )
    call_count = 0

    async def fake_call(first_message: str, **_: object) -> str | None:
        nonlocal call_count
        call_count += 1
        return "ignored"

    loop._call_title_summarizer = fake_call  # type: ignore[method-assign]
    await loop._summarize_session_title(msg)
    assert call_count == 0


@pytest.mark.asyncio
async def test_title_two_char_chinese_greeting_is_summarised(tmp_path: Path) -> None:
    """Regression: 2-char Chinese greetings like '你好' used to be skipped
    because the threshold was len < 3. They're now accepted."""
    loop = _make_loop(tmp_path)
    msg = InboundMessage(
        channel="web", sender_id="user1", chat_id="two-char",
        content="你好", session_key_override="web:two-char",
    )

    captured: list[str] = []

    async def fake_call(first_message: str, **_: object) -> str | None:
        captured.append(first_message)
        return "日常问候"

    loop._call_title_summarizer = fake_call  # type: ignore[method-assign]
    await loop._summarize_session_title(msg)
    assert captured == ["你好"]
    refetched = loop.sessions.get_or_create("web:two-char")
    assert refetched.title == "日常问候"


@pytest.mark.asyncio
async def test_title_idempotent_when_already_titled(tmp_path: Path) -> None:
    """Already-titled sessions short-circuit immediately, even if invoked
    by a retry path."""
    loop = _make_loop(tmp_path)
    session = loop.sessions.get_or_create("web:already")
    session.messages = [{"role": "user", "content": "hello world"}]
    session.metadata["auto_titled"] = True
    loop.sessions.save(session)

    msg = InboundMessage(
        channel="web", sender_id="user1", chat_id="already",
        content="hello world", session_key_override="web:already",
    )

    call_count = 0

    async def fake_call(first_message: str, **_: object) -> str | None:
        nonlocal call_count
        call_count += 1
        return "should not happen"

    loop._call_title_summarizer = fake_call  # type: ignore[method-assign]
    await loop._summarize_session_title(msg)
    assert call_count == 0


@pytest.mark.asyncio
async def test_provider_error_response_does_not_become_title(tmp_path: Path) -> None:
    """When the provider returns finish_reason='error' (network blip, 5xx,
    rate limit), the title summarizer must NOT slice the error message
    into something like "Error call" and save it as the session title.
    """
    loop = _make_loop(tmp_path)
    # Real-world example from the field: MiniMax connection error.
    error_response = LLMResponse(
        content="Error calling LLM: Connection error.",
        finish_reason="error",
    )
    loop.provider.chat_with_retry = AsyncMock(return_value=error_response)

    title = await loop._call_title_summarizer(
        "你好啊", session_key="web:err-test",
    )
    assert title is None, (
        "Provider error response must produce no title (would otherwise "
        "show up in the sidebar as 'Error call' or similar garbage)"
    )


@pytest.mark.asyncio
async def test_error_response_keeps_auto_titled_false(tmp_path: Path) -> None:
    """Defence in depth: even via the full task entry point, an error
    response must not flip auto_titled — otherwise no retry would fire on
    the next user message."""
    loop = _make_loop(tmp_path)
    session = loop.sessions.get_or_create("web:err-full")
    session.messages = [{"role": "user", "content": "你好啊"}]
    loop.sessions.save(session)

    loop.provider.chat_with_retry = AsyncMock(return_value=LLMResponse(
        content="Error calling LLM: Connection error.",
        finish_reason="error",
    ))

    msg = InboundMessage(
        channel="web", sender_id="u", chat_id="err-full",
        content="你好啊", session_key_override="web:err-full",
    )
    await loop._summarize_session_title(msg)

    refetched = loop.sessions.get_or_create("web:err-full")
    assert refetched.metadata.get("auto_titled") is not True
    assert refetched.metadata.get("title") in (None, "")


@pytest.mark.asyncio
async def test_title_concurrent_call_short_circuits(tmp_path: Path) -> None:
    """A second invocation while the first is in-flight should bail out."""
    loop = _make_loop(tmp_path)
    session = loop.sessions.get_or_create("web:dupe")
    session.messages = [{"role": "user", "content": "first message text"}]
    loop.sessions.save(session)
    loop._title_in_flight.add("web:dupe")  # pretend another worker is on it

    msg = InboundMessage(
        channel="web", sender_id="user1", chat_id="dupe",
        content="first message text", session_key_override="web:dupe",
    )

    call_count = 0

    async def fake_call(first_message: str, **_: object) -> str | None:
        nonlocal call_count
        call_count += 1
        return "x"

    loop._call_title_summarizer = fake_call  # type: ignore[method-assign]
    await loop._summarize_session_title(msg)
    assert call_count == 0
