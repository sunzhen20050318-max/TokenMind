from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tokenmind.agent.loop import AgentLoop
from tokenmind.agent.tools.message import MessageTool
from tokenmind.bus.events import InboundMessage, OutboundMessage
from tokenmind.bus.queue import MessageBus
from tokenmind.providers.base import LLMResponse, ToolCallRequest


def _make_loop(tmp_path: Path) -> AgentLoop:
    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    return AgentLoop(bus=bus, provider=provider, workspace=tmp_path, model="test-model")


@pytest.mark.asyncio
async def test_deliver_attachment_tool_attaches_generated_file_to_final_reply(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    tool_call = ToolCallRequest(
        id="call1",
        name="deliver_attachment",
        arguments={
            "source_type": "inline_content",
            "filename": "summary.md",
            "content": "# report",
            "mime_type": "text/markdown",
        },
    )
    calls = iter(
        [
            LLMResponse(content="", tool_calls=[tool_call]),
            LLMResponse(content="I created the report.", tool_calls=[]),
        ]
    )
    loop.provider.chat_with_retry = AsyncMock(side_effect=lambda *args, **kwargs: next(calls))
    loop.tools.get_definitions = MagicMock(return_value=[])

    msg = InboundMessage(
        channel="web",
        sender_id="web_user",
        chat_id="web:test-session",
        content="Generate a report",
    )
    result = await loop._process_message(msg)

    assert result is not None
    attachments = result.metadata.get("_attachments") or []
    assert len(attachments) == 1
    assert attachments[0]["origin"] == "assistant_generated"
    # Auto-save: assistant attachments default to "saved" so they aren't swept.
    assert attachments[0]["status"] == "saved"

    saved_session = loop.sessions.get_or_create(msg.session_key)
    assistant_messages = [item for item in saved_session.messages if item.get("role") == "assistant"]
    assert assistant_messages
    assert assistant_messages[-1]["attachments"][0]["id"] == attachments[0]["id"]


@pytest.mark.asyncio
async def test_message_tool_media_is_bridged_into_web_attachments(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    chart = tmp_path / "exports" / "chart.png"
    chart.parent.mkdir(parents=True, exist_ok=True)
    chart.write_bytes(b"\x89PNG\r\n\x1a\nchart")

    tool_call = ToolCallRequest(
        id="call2",
        name="message",
        arguments={
            "content": "Here is the chart.",
            "media": [str(chart)],
        },
    )
    calls = iter(
        [
            LLMResponse(content="", tool_calls=[tool_call]),
            LLMResponse(content="Done", tool_calls=[]),
        ]
    )
    loop.provider.chat_with_retry = AsyncMock(side_effect=lambda *args, **kwargs: next(calls))
    loop.tools.get_definitions = MagicMock(return_value=[])

    sent: list[OutboundMessage] = []
    message_tool = loop.tools.get("message")
    if isinstance(message_tool, MessageTool):
        message_tool.set_send_callback(AsyncMock(side_effect=lambda outbound: sent.append(outbound)))

    msg = InboundMessage(
        channel="web",
        sender_id="web_user",
        chat_id="web:test-session",
        content="Send the chart",
    )
    result = await loop._process_message(msg)

    assert sent == []
    assert result is not None
    assert result.content == "Here is the chart."
    attachments = result.metadata.get("_attachments") or []
    assert len(attachments) == 1
    assert attachments[0]["origin"] == "assistant_local"

    saved_session = loop.sessions.get_or_create(msg.session_key)
    assistant_messages = [item for item in saved_session.messages if item.get("role") == "assistant"]
    assert assistant_messages
    assert assistant_messages[-1]["content"] == "Here is the chart."
    assert assistant_messages[-1]["attachments"][0]["origin"] == "assistant_local"


@pytest.mark.asyncio
async def test_invalid_deliver_attachment_call_persists_tool_error(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    tool_call = ToolCallRequest(
        id="call3",
        name="deliver_attachment",
        arguments={"source_type": "local_file", "path": None, "filename": None},
    )
    calls = iter(
        [
            LLMResponse(content="", tool_calls=[tool_call]),
            LLMResponse(content="I need a file path before I can attach it.", tool_calls=[]),
        ]
    )
    loop.provider.chat_with_retry = AsyncMock(side_effect=lambda *args, **kwargs: next(calls))
    loop.tools.get_definitions = MagicMock(return_value=[])

    msg = InboundMessage(
        channel="web",
        sender_id="web_user",
        chat_id="web:test-session",
        content="Send the file",
    )
    result = await loop._process_message(msg)

    assert result is not None
    saved_session = loop.sessions.get_or_create(msg.session_key)
    assert any(event["type"] == "tool_error" for event in saved_session.timeline_events)
    assert not any(event["type"] == "tool_end" for event in saved_session.timeline_events)


@pytest.mark.asyncio
async def test_repeated_invalid_deliver_attachment_call_stops_tool_loop(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    loop.max_iterations = 10
    tool_call = ToolCallRequest(
        id="call4",
        name="deliver_attachment",
        arguments={"source_type": "inline_content", "filename": None, "content": None},
    )
    loop.provider.chat_with_retry = AsyncMock(
        return_value=LLMResponse(content="", tool_calls=[tool_call])
    )
    loop.tools.get_definitions = MagicMock(return_value=[])

    msg = InboundMessage(
        channel="web",
        sender_id="web_user",
        chat_id="web:test-session",
        content="Send SOUL.md",
    )
    result = await loop._process_message(msg)

    assert result is not None
    assert "deliver_attachment was called repeatedly with invalid parameters" in result.content
    assert loop.provider.chat_with_retry.await_count == 2


@pytest.mark.asyncio
async def test_deliver_attachment_isolates_state_across_concurrent_sessions(tmp_path: Path) -> None:
    """Two sessions delivering attachments concurrently must not see each other's files."""
    import asyncio

    from datetime import timedelta

    from tokenmind.agent.tools.deliver_attachment import (
        DeliverAttachmentTool,
        _delivered_ctx,
    )
    from tokenmind.server.attachments import AttachmentStore

    store = AttachmentStore(tmp_path)
    tool = DeliverAttachmentTool(store, retention=timedelta(hours=1))

    async def run_session(chat_id: str, filename: str) -> list[dict]:
        # Each session would normally run inside its own AgentLoop task, which
        # gives the ContextVar a fresh, isolated value automatically.
        tool.set_context("web", chat_id, message_id=None)
        tool.start_turn()
        # Yield once so the scheduler can interleave with the other session.
        await asyncio.sleep(0)
        await tool.execute(
            source_type="inline_content",
            filename=filename,
            content=f"payload-{filename}",
            mime_type="text/plain",
        )
        await asyncio.sleep(0)
        return tool.delivered

    task_a = asyncio.create_task(run_session("web:session-1", "male.txt"))
    task_b = asyncio.create_task(run_session("web:session-2", "female.txt"))
    delivered_a, delivered_b = await asyncio.gather(task_a, task_b)

    # Each session must only see its own attachment — no cross-pollination.
    assert [item["name"] for item in delivered_a] == ["male.txt"]
    assert [item["name"] for item in delivered_b] == ["female.txt"]

    # ContextVar from outside the tasks remains the default (None list).
    assert _delivered_ctx.get() is None or _delivered_ctx.get() == []
