"""WebSocket handler for TokenMind Web UI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from tokenmind.server.websocket.manager import ConnectionManager


def _path_within(path: str, root: Path | None) -> bool:
    """True if ``path`` resolves to a location inside ``root``.

    Clients send back server-issued upload paths over the WebSocket; without
    this check a client could pass an arbitrary path (e.g. /etc/…) which the
    context builder would read and base64-encode into the LLM prompt.
    """
    if root is None:
        return False
    try:
        resolved = Path(path).resolve()
        return resolved == root.resolve() or root.resolve() in resolved.parents
    except OSError:
        return False


async def websocket_handler(
    websocket: WebSocket,
    session_key: str,
    connection_manager: ConnectionManager,
    inbound_queue: Any,  # MessageBus.inbound queue
    uploads_root: Path | None = None,
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
                    if isinstance(item, dict)
                    and item.get("is_image")
                    and item.get("path")
                    and _path_within(item["path"], uploads_root)
                ]
                if not content and not attachments:
                    continue

                # Import here to avoid circular imports
                from tokenmind.bus.events import InboundMessage

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
                from tokenmind.bus.events import InboundMessage

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

            elif msg_type == "tool_approval":
                from tokenmind.bus.events import InboundMessage

                approval_id = str(msg_data.get("approval_id") or "").strip()
                approved = bool(msg_data.get("approved"))
                if not approval_id:
                    await websocket.send_json({
                        "type": "error",
                        "content": "Missing approval_id",
                    })
                    continue

                msg = InboundMessage(
                    channel="web",
                    sender_id="web_user",
                    chat_id=session_key,
                    content="/tool-approval",
                    media=[],
                    metadata={
                        "websocket": True,
                        "control": "tool_approval",
                        "approval_id": approval_id,
                        "approved": approved,
                    },
                    session_key_override=session_key,
                )
                await inbound_queue.put(msg)

            elif msg_type == "browser_handoff":
                from tokenmind.bus.events import InboundMessage

                handoff_id = str(msg_data.get("handoff_id") or "").strip()
                completed = bool(msg_data.get("completed"))
                if not handoff_id:
                    await websocket.send_json({
                        "type": "error",
                        "content": "Missing handoff_id",
                    })
                    continue

                msg = InboundMessage(
                    channel="web",
                    sender_id="web_user",
                    chat_id=session_key,
                    content="/browser-handoff",
                    media=[],
                    metadata={
                        "websocket": True,
                        "control": "browser_handoff",
                        "handoff_id": handoff_id,
                        "completed": completed,
                    },
                    session_key_override=session_key,
                )
                await inbound_queue.put(msg)

            elif msg_type == "user_question_response":
                from tokenmind.bus.events import InboundMessage

                question_id = str(msg_data.get("question_id") or "").strip()
                answers = msg_data.get("answers") or {}
                if not question_id:
                    await websocket.send_json({
                        "type": "error",
                        "content": "Missing question_id",
                    })
                    continue
                if not isinstance(answers, dict):
                    answers = {}

                msg = InboundMessage(
                    channel="web",
                    sender_id="web_user",
                    chat_id=session_key,
                    content="/user-question-response",
                    media=[],
                    metadata={
                        "websocket": True,
                        "control": "user_question_response",
                        "question_id": question_id,
                        "answers": answers,
                    },
                    session_key_override=session_key,
                )
                await inbound_queue.put(msg)

            elif msg_type == "guidance":
                from tokenmind.bus.events import InboundMessage

                content = str(msg_data.get("content") or "").strip()
                if not content:
                    await websocket.send_json({
                        "type": "error",
                        "content": "Missing guidance content",
                    })
                    continue

                msg = InboundMessage(
                    channel="web",
                    sender_id="web_user",
                    chat_id=session_key,
                    content=content,
                    media=[],
                    metadata={
                        "websocket": True,
                        "control": "guidance",
                    },
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
