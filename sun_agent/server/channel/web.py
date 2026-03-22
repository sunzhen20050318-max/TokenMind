"""Web channel implementation for WebSocket-based chat UI."""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from sun_agent.bus.events import InboundMessage, OutboundMessage
from sun_agent.bus.queue import MessageBus
from sun_agent.channels.base import BaseChannel


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

        # Handle progress messages - tool events
        if msg.metadata.get("_progress"):
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
            return

        # Forward to WebSocket manager
        logger.info("Sending RESP: {}", msg.content[:50] if msg.content else "")
        await self._ws_manager.send_to_session(
            session_key=msg.chat_id,
            message={
                "type": "response",
                "content": msg.content,
                "channel": msg.channel,
            },
        )

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
