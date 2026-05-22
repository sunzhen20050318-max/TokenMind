"""Test message tool suppress logic for final replies."""

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


class TestMessageToolSuppressLogic:
    """Final reply suppressed only when message tool sends to the same target."""

    @pytest.mark.asyncio
    async def test_suppress_when_sent_to_same_target(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        tool_call = ToolCallRequest(
            id="call1", name="message",
            arguments={"content": "Hello", "channel": "feishu", "chat_id": "chat123"},
        )
        calls = iter([
            LLMResponse(content="", tool_calls=[tool_call]),
            LLMResponse(content="Done", tool_calls=[]),
        ])
        loop.provider.chat_with_retry = AsyncMock(side_effect=lambda *a, **kw: next(calls))
        loop.tools.get_definitions = MagicMock(return_value=[])

        sent: list[OutboundMessage] = []
        mt = loop.tools.get("message")
        if isinstance(mt, MessageTool):
            mt.set_send_callback(AsyncMock(side_effect=lambda m: sent.append(m)))

        msg = InboundMessage(channel="feishu", sender_id="user1", chat_id="chat123", content="Send")
        result = await loop._process_message(msg)

        assert len(sent) == 1
        assert result is None  # suppressed

    @pytest.mark.asyncio
    async def test_not_suppress_when_sent_to_different_target(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        tool_call = ToolCallRequest(
            id="call1", name="message",
            arguments={"content": "Email content", "channel": "email", "chat_id": "user@example.com"},
        )
        calls = iter([
            LLMResponse(content="", tool_calls=[tool_call]),
            LLMResponse(content="I've sent the email.", tool_calls=[]),
        ])
        loop.provider.chat_with_retry = AsyncMock(side_effect=lambda *a, **kw: next(calls))
        loop.tools.get_definitions = MagicMock(return_value=[])

        sent: list[OutboundMessage] = []
        mt = loop.tools.get("message")
        if isinstance(mt, MessageTool):
            mt.set_send_callback(AsyncMock(side_effect=lambda m: sent.append(m)))

        msg = InboundMessage(channel="feishu", sender_id="user1", chat_id="chat123", content="Send email")
        result = await loop._process_message(msg)

        assert len(sent) == 1
        assert sent[0].channel == "email"
        assert result is not None  # not suppressed
        assert result.channel == "feishu"

    @pytest.mark.asyncio
    async def test_not_suppress_when_no_message_tool_used(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop.provider.chat_with_retry = AsyncMock(return_value=LLMResponse(content="Hello!", tool_calls=[]))
        loop.tools.get_definitions = MagicMock(return_value=[])

        msg = InboundMessage(channel="feishu", sender_id="user1", chat_id="chat123", content="Hi")
        result = await loop._process_message(msg)

        assert result is not None
        assert "Hello" in result.content

    @pytest.mark.asyncio
    async def test_web_message_tool_text_becomes_current_reply(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        tool_call = ToolCallRequest(
            id="call1",
            name="message",
            arguments={"content": "Scheduled result", "channel": "web", "chat_id": "web"},
        )
        calls = iter([
            LLMResponse(content="", tool_calls=[tool_call]),
            LLMResponse(content="Sent.", tool_calls=[]),
        ])
        loop.provider.chat_with_retry = AsyncMock(side_effect=lambda *a, **kw: next(calls))
        loop.tools.get_definitions = MagicMock(return_value=[])

        msg = InboundMessage(
            channel="web",
            sender_id="user1",
            chat_id="web:task-results",
            content="Run scheduled task",
        )
        result = await loop._process_message(msg, session_key="web:task-results")

        assert result is not None
        assert result.content == "Scheduled result"
        session = loop.sessions.get_or_create("web:task-results")
        assert session.messages[-1]["role"] == "assistant"
        assert session.messages[-1]["content"] == "Scheduled result"

    async def test_progress_hides_inline_think_tags_but_surfaces_reasoning(
        self, tmp_path: Path
    ) -> None:
        loop = _make_loop(tmp_path)
        tool_call = ToolCallRequest(id="call1", name="read_file", arguments={"path": "foo.txt"})
        calls = iter([
            LLMResponse(
                content="Visible<think>hidden</think>",
                tool_calls=[tool_call],
                reasoning_content="secret reasoning",
                thinking_blocks=[{"signature": "sig", "thought": "secret thought"}],
            ),
            LLMResponse(content="Done", tool_calls=[]),
        ])
        loop.provider.chat_with_retry = AsyncMock(side_effect=lambda *a, **kw: next(calls))
        loop.tools.get_definitions = MagicMock(return_value=[])
        loop.tools.execute = AsyncMock(return_value="ok")

        progress: list[tuple[str, bool, bool]] = []

        async def on_progress(
            content: str,
            *,
            tool_hint: bool = False,
            reasoning: bool = False,
            **kwargs,
        ) -> None:
            progress.append((content, tool_hint, reasoning))

        final_content, _, _ = await loop._run_agent_loop([], on_progress=on_progress)

        assert final_content == "Done"
        # reasoning_content is now surfaced as its own timeline event (rendered
        # as a 💭 row in the UI). The inline <think>…</think> portion of the
        # content stays stripped from the visible answer.
        assert progress == [
            ("secret reasoning", False, True),
            ("Visible", False, False),
            ('read_file({"path": "foo.txt"})', False, False),
            ("read_file completed", False, False),
        ]


class TestMessageToolTurnTracking:

    def test_sent_in_turn_tracks_same_target(self) -> None:
        tool = MessageTool()
        tool.set_context("feishu", "chat1")
        assert not tool._sent_in_turn
        tool._sent_in_turn = True
        assert tool._sent_in_turn

    def test_start_turn_resets(self) -> None:
        tool = MessageTool()
        tool._sent_in_turn = True
        tool.start_turn()
        assert not tool._sent_in_turn
