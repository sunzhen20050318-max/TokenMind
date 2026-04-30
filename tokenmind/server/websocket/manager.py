"""WebSocket connection manager for TokenMind Web UI."""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger


class ConnectionManager:
    """
    Manages WebSocket connections for the Web UI.

    Maintains a mapping of session_keys to WebSocket connections
    and handles message routing.
    """

    def __init__(self):
        self._connections: dict[str, asyncio.WebSocketServerProtocol] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: Any, session_key: str) -> None:
        """
        Register a new WebSocket connection.

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

        Args:
            session_key: The session identifier.
            message: The message dict to send (will be JSON serialized).

        Returns:
            True if sent successfully, False if session not found.
        """
        async with self._lock:
            websocket = self._connections.get(session_key)
            if not websocket:
                logger.debug("WebSocket not found for session: {}", session_key)
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
