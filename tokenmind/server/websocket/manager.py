"""WebSocket connection manager for TokenMind Web UI."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger


# Buffer caps. The buffer rescues live signals (progress / tool_start /
# turn-complete) when the browser tab loses WS for a few seconds — final
# assistant messages are already persisted to the session JSONL, so the
# rescue is only for the realtime event stream. Caps stop a long-orphaned
# session from leaking memory indefinitely.
_PENDING_MAX_PER_SESSION = 200
_PENDING_TTL_S = 600.0


class ConnectionManager:
    """
    Manages WebSocket connections for the Web UI.

    Maintains a mapping of session_keys to WebSocket connections
    and handles message routing. When a session has no live WebSocket,
    outbound messages are queued and replayed in order on reconnect so
    the frontend never loses a turn-complete signal to a flaky network.
    """

    def __init__(self):
        self._connections: dict[str, asyncio.WebSocketServerProtocol] = {}
        # session_key -> list[(enqueued_at_monotonic, payload)]
        self._pending: dict[str, list[tuple[float, dict[str, Any]]]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: Any, session_key: str) -> None:
        """
        Register a new WebSocket connection and replay any queued messages
        that arrived while the session was disconnected.

        Args:
            websocket: The WebSocket connection.
            session_key: The session identifier.
        """
        async with self._lock:
            # Close existing connection for this session if any
            if session_key in self._connections:
                old_ws = self._connections[session_key]
                try:
                    await old_ws.close()
                except Exception:
                    pass
            self._connections[session_key] = websocket
            logger.info("WebSocket connected: session={}", session_key)

            # Drain pending queue in the same lock-scope so live sends
            # arriving after release can't be interleaved before replays.
            queue = self._pending.pop(session_key, [])
            if queue:
                now = time.monotonic()
                replayed = 0
                expired = 0
                for enqueued_at, payload in queue:
                    if now - enqueued_at > _PENDING_TTL_S:
                        expired += 1
                        continue
                    try:
                        await websocket.send_json(payload)
                        replayed += 1
                    except Exception as e:
                        logger.warning(
                            "Replay aborted for session {} after {} msg(s): {}",
                            session_key,
                            replayed,
                            e,
                        )
                        break
                logger.info(
                    "Replayed {} pending message(s) to session={} (dropped {} expired)",
                    replayed,
                    session_key,
                    expired,
                )

    async def disconnect(self, session_key: str) -> None:
        """
        Unregister a WebSocket connection.

        Args:
            session_key: The session identifier.
        """
        async with self._lock:
            if session_key in self._connections:
                del self._connections[session_key]
                logger.info("WebSocket disconnected: session={}", session_key)

    async def send_to_session(self, session_key: str, message: dict[str, Any]) -> bool:
        """
        Send a message to a specific session's WebSocket.

        If the session has no live WebSocket, the message is queued in a
        bounded buffer and replayed when the session reconnects (see
        ``connect``). Returns ``True`` on direct delivery and ``False``
        when the message was buffered or dropped — callers that need to
        know if the frontend actually saw it should track an ack instead.

        Args:
            session_key: The session identifier.
            message: The message dict to send (will be JSON serialized).
        """
        async with self._lock:
            websocket = self._connections.get(session_key)
            if not websocket:
                # No live WS — buffer for replay on reconnect.
                queue = self._pending.setdefault(session_key, [])
                now = time.monotonic()
                # Prune expired entries before appending so the cap is
                # measured against the *useful* tail.
                if queue:
                    queue[:] = [
                        item for item in queue if now - item[0] <= _PENDING_TTL_S
                    ]
                queue.append((now, message))
                # Drop oldest if over cap. Older signals are usually
                # less useful than the latest "turn complete" / final
                # text — keep the tail.
                overflow = len(queue) - _PENDING_MAX_PER_SESSION
                if overflow > 0:
                    del queue[:overflow]
                    logger.warning(
                        "Pending queue overflow for session={}, dropped {} oldest",
                        session_key,
                        overflow,
                    )
                logger.debug(
                    "Buffered message for disconnected session={} (queue={})",
                    session_key,
                    len(queue),
                )
                return False

            try:
                await websocket.send_json(message)
                return True
            except Exception as e:
                logger.error("Failed to send WebSocket message: {}", e)
                return False

    async def broadcast(self, message: dict[str, Any]) -> None:
        """
        Broadcast a message to all connected sessions.

        Args:
            message: The message dict to send.
        """
        async with self._lock:
            for session_key, websocket in list(self._connections.items()):
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error("Failed to broadcast to session {}: {}", session_key, e)

    def get_session_keys(self) -> list[str]:
        """Get list of all active session keys."""
        return list(self._connections.keys())

    def is_session_connected(self, session_key: str) -> bool:
        """Check if a session has an active WebSocket connection."""
        return session_key in self._connections

    async def close_all(self) -> None:
        """Force-close every active WebSocket and clear the registry.

        Used during server shutdown so uvicorn doesn't sit in
        "Waiting for background tasks" while idle browser tabs hold the
        connections open.
        """
        async with self._lock:
            for session_key, websocket in list(self._connections.items()):
                try:
                    await websocket.close(code=1001, reason="server shutting down")
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "WebSocket close raised during shutdown for {}",
                        session_key,
                        exc_info=True,
                    )
            self._connections.clear()
            self._pending.clear()
