"""Web channel implementation for WebSocket-based chat UI."""

from __future__ import annotations

import asyncio
from textwrap import wrap
from typing import Any

from loguru import logger

from tokenmind.bus.events import InboundMessage, OutboundMessage
from tokenmind.bus.queue import MessageBus
from tokenmind.channels.base import BaseChannel


class WebChannelConfig:
    """Configuration for WebChannel."""

    def __init__(self, allow_from: list[str] | None = None):
        self.allow_from = allow_from or ["*"]


class WebChannel(BaseChannel):
    """
    Web UI channel for real-time chat via WebSocket.

    This channel handles messages from the Web UI by publishing them
    to the message bus and forwarding responses back via WebSocket.
    """

    name = "web"
    display_name = "Web UI"

    def __init__(self, config: WebChannelConfig, bus: MessageBus):
        super().__init__(config, bus)
        self._ws_manager: Any = None
        self._outbound_task: asyncio.Task | None = None

    def set_ws_manager(self, manager: Any) -> None:
        """Set the WebSocket connection manager."""
        self._ws_manager = manager

    async def start(self) -> None:
        """Start the channel."""
        self._running = True
        logger.info("{}: WebChannel started", self.name)

    async def stop(self) -> None:
        """Stop the channel."""
        self._running = False
        if self._outbound_task:
            self._outbound_task.cancel()
            try:
                await self._outbound_task
            except asyncio.CancelledError:
                pass
        logger.info("{}: WebChannel stopped", self.name)

    async def send(self, msg: OutboundMessage) -> None:
        """
        Send a message to the Web UI via WebSocket.

        Args:
            msg: The outbound message to send.
        """
        if not self._ws_manager:
            logger.warning("{}: WebSocket manager not set", self.name)
            return

        if msg.metadata.get("_approval_required"):
            await self._ws_manager.send_to_session(
                session_key=msg.chat_id,
                message={
                    "type": "approval_required",
                    "approval_id": msg.metadata.get("_approval_id"),
                    "tool_id": msg.metadata.get("_tool_id"),
                    "tool_name": msg.metadata.get("_tool_name"),
                    "command": msg.content,
                    "risk_reason": msg.metadata.get("_risk_reason"),
                    "working_dir": msg.metadata.get("_working_dir"),
                    "timeout_s": msg.metadata.get("_approval_timeout_s"),
                    "channel": msg.channel,
                },
            )
            return

        if msg.metadata.get("_approval_error"):
            await self._ws_manager.send_to_session(
                session_key=msg.chat_id,
                message={
                    "type": "error",
                    "content": msg.content,
                    "channel": msg.channel,
                },
            )
            return

        if msg.metadata.get("_session_title_updated"):
            await self._ws_manager.send_to_session(
                session_key=msg.chat_id,
                message={
                    "type": "session_title_updated",
                    "session_id": msg.metadata.get("_session_id") or msg.chat_id,
                    "title": msg.metadata.get("_session_title") or msg.content,
                    "channel": msg.channel,
                },
            )
            return

        if msg.metadata.get("_guidance_received"):
            # Real-time user guidance — echo back so the chat UI can
            # render an inline "💡 引导" bubble without waiting for the
            # next assistant turn.
            await self._ws_manager.send_to_session(
                session_key=msg.chat_id,
                message={
                    "type": "guidance_received",
                    "content": msg.content,
                    "channel": msg.channel,
                },
            )
            return

        # Handle progress messages - tool events
        if msg.metadata.get("_progress"):
            if msg.metadata.get("_file_edit_progress"):
                # Live write_file / edit_file diff stats while the model
                # streams its arguments — the WebUI's ToolIndicator uses
                # these to show a rolling +N/-M counter inside the
                # in-progress tool row.
                await self._ws_manager.send_to_session(
                    session_key=msg.chat_id,
                    message={
                        "type": "file_edit_progress",
                        "event": msg.metadata["_file_edit_progress"],
                        "channel": msg.channel,
                    },
                )
                return
            if msg.metadata.get("_reasoning_content"):
                # Reasoning (model thinking from DeepSeek-R1 / Qwen Thinking /
                # Kimi Thinking etc.) rides the same progress pipeline as
                # tool events but renders as its own kind in the timeline.
                await self._ws_manager.send_to_session(
                    session_key=msg.chat_id,
                    message={
                        "type": "reasoning",
                        "content": msg.content,
                        "channel": msg.channel,
                    },
                )
                return
            if msg.metadata.get("_browser_task"):
                await self._ws_manager.send_to_session(
                    session_key=msg.chat_id,
                    message={
                        "type": "browser_task",
                        "event": msg.metadata.get("_browser_task_event") or "started",
                        "task_id": msg.metadata.get("_browser_task_id") or msg.content,
                        "content": msg.content,
                        "channel": msg.channel,
                    },
                )
                return
            if msg.metadata.get("_tool_start"):
                # Individual tool start event
                logger.info("Sending TOOL_START: {} ({})", msg.content[:80], msg.metadata.get("_tool_id"))
                await self._ws_manager.send_to_session(
                    session_key=msg.chat_id,
                    message={
                        "type": "tool_start",
                        "content": msg.content,
                        "tool_id": msg.metadata.get("_tool_id"),
                        "tool_name": msg.metadata.get("_tool_name"),
                        "channel": msg.channel,
                    },
                )
                return
            if msg.metadata.get("_tool_end"):
                # Individual tool end event
                logger.info(
                    "Sending TOOL_END: {} ({}) duration={}",
                    msg.content[:80],
                    msg.metadata.get("_tool_id"),
                    msg.metadata.get("_tool_duration"),
                )
                await self._ws_manager.send_to_session(
                    session_key=msg.chat_id,
                    message={
                        "type": "tool_end",
                        "content": msg.content,
                        "tool_id": msg.metadata.get("_tool_id"),
                        "tool_name": msg.metadata.get("_tool_name"),
                        "duration": msg.metadata.get("_tool_duration"),
                        "channel": msg.channel,
                    },
                )
                return
            if msg.metadata.get("_tool_error"):
                logger.info("Sending TOOL_ERROR: {} ({})", msg.content[:80], msg.metadata.get("_tool_id"))
                await self._ws_manager.send_to_session(
                    session_key=msg.chat_id,
                    message={
                        "type": "tool_error",
                        "content": msg.content,
                        "tool_id": msg.metadata.get("_tool_id"),
                        "tool_name": msg.metadata.get("_tool_name"),
                        "detail": msg.metadata.get("_tool_detail"),
                        "channel": msg.channel,
                    },
                )
                return
            if msg.metadata.get("_tool_hint"):
                # Tool call hint - initial aggregate event (deprecated in favor of tool_start)
                logger.info("Sending TOOL: {}", msg.content[:80])
                await self._ws_manager.send_to_session(
                    session_key=msg.chat_id,
                    message={
                        "type": "tool",
                        "content": msg.content,
                        "channel": msg.channel,
                    },
                )
                return
            # Skip regular progress messages
            await self._ws_manager.send_to_session(
                session_key=msg.chat_id,
                message={
                    "type": "progress",
                    "content": msg.content,
                    "channel": msg.channel,
                },
            )
            return

        # Forward to WebSocket manager as chunked response events so the
        # frontend can render a streaming-style reply incrementally.
        logger.info("Sending RESP: {}", msg.content[:50] if msg.content else "")
        citations = msg.metadata.get("_citations")
        attachments = msg.metadata.get("_attachments")
        await self._ws_manager.send_to_session(
            session_key=msg.chat_id,
            message={
                "type": "response_start",
                "channel": msg.channel,
            },
        )
        for chunk in self._iter_response_chunks(msg.content):
            await self._ws_manager.send_to_session(
                session_key=msg.chat_id,
                message={
                    "type": "response_delta",
                    "content": chunk,
                    "channel": msg.channel,
                },
            )
        await self._ws_manager.send_to_session(
            session_key=msg.chat_id,
            message={
                "type": "response_end",
                "content": msg.content,
                "channel": msg.channel,
                "citations": citations,
                "attachments": attachments,
            },
        )

    @staticmethod
    def _iter_response_chunks(content: str, chunk_size: int = 48) -> list[str]:
        """Split a final response into UI-friendly chunks."""
        if not content:
            return [""]
        chunks: list[str] = []
        for line in content.splitlines(keepends=True):
            if len(line) <= chunk_size:
                chunks.append(line)
                continue
            chunks.extend(wrap(line, width=chunk_size, replace_whitespace=False, drop_whitespace=False))
        return chunks or [content]

    async def handle_inbound(
        self,
        sender_id: str,
        chat_id: str,
        content: str,
        session_key: str | None = None,
    ) -> None:
        """
        Handle an inbound message from WebSocket.

        Publishes the message to the message bus for agent processing.

        Args:
            sender_id: The sender's identifier.
            chat_id: The chat/session identifier.
            content: Message text content.
            session_key: Optional session key override.
        """
        if not self.is_allowed(sender_id):
            logger.warning(
                "{}: Access denied for sender {}", self.name, sender_id,
            )
            return

        msg = InboundMessage(
            channel=self.name,
            sender_id=str(sender_id),
            chat_id=str(chat_id),
            content=content,
            media=[],
            metadata={},
            session_key_override=session_key,
        )

        await self.bus.publish_inbound(msg)

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        """Return default config for WebChannel."""
        return {"enabled": False, "allow_from": ["*"]}
