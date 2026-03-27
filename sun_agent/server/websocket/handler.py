"""WebSocket handler for sun_agent Web UI."""

from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from sun_agent.server.websocket.manager import ConnectionManager


async def websocket_handler(
    websocket: WebSocket,
    session_key: str,
    connection_manager: ConnectionManager,
    inbound_queue: Any,  # MessageBus.inbound queue
) -> None:
    """
    Handle a WebSocket connection for chat.

    Args:
        websocket: The WebSocket connection.
        session_key: The session identifier.
        connection_manager: Manager for all WebSocket connections.
        inbound_queue: The MessageBus inbound queue to publish messages.
    """
    await websocket.accept()
    await connection_manager.connect(websocket, session_key)

    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "session_id": session_key,
        })

        while True:
            # Receive message from client
            data = await websocket.receive_text()

            try:
                msg_data = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "content": "Invalid JSON message",
                })
                continue

            msg_type = msg_data.get("type")

            if msg_type == "message":
                content = msg_data.get("content", "").strip()
                attachments = msg_data.get("attachments") or []
                media = [
                    item.get("path")
                    for item in attachments
                    if isinstance(item, dict) and item.get("is_image") and item.get("path")
                ]
                if not content and not attachments:
                    continue

                # Import here to avoid circular imports
                from sun_agent.bus.events import InboundMessage

                msg = InboundMessage(
                    channel="web",
                    sender_id="web_user",
                    chat_id=session_key,
                    content=content,
                    media=media,
                    metadata={"websocket": True, "attachments": attachments},
                    session_key_override=session_key,
                )
                await inbound_queue.put(msg)

            elif msg_type == "stop":
                from sun_agent.bus.events import InboundMessage

                msg = InboundMessage(
                    channel="web",
                    sender_id="web_user",
                    chat_id=session_key,
                    content="/stop",
                    media=[],
                    metadata={"websocket": True, "control": "stop"},
                    session_key_override=session_key,
                )
                await inbound_queue.put(msg)

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            else:
                await websocket.send_json({
                    "type": "error",
                    "content": f"Unknown message type: {msg_type}",
                })

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: session={}", session_key)
    except Exception as e:
        logger.error("WebSocket error: session={}, error={}", session_key, e)
    finally:
        await connection_manager.disconnect(session_key)
