"""FastAPI application for sun_agent Web UI."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from sun_agent.bus.events import InboundMessage, OutboundMessage
from sun_agent.bus.queue import MessageBus
from sun_agent.server.channel.web import WebChannel, WebChannelConfig
from sun_agent.server.dependencies import (
    get_connection_manager,
    set_cron_service,
    get_inbound_queue,
    set_chat_service,
    set_connection_manager,
    set_inbound_queue,
)
from sun_agent.server.routes import chat_router, config_router, cron_router, sessions_router, status_router
from sun_agent.server.websocket.handler import websocket_handler
from sun_agent.server.websocket.manager import ConnectionManager


class ChatService:
    """
    Service for handling chat operations via REST API.

    This service wraps the MessageBus and AgentLoop to provide
    synchronous request-response chat functionality.
    """

    def __init__(
        self,
        bus: MessageBus,
        agent_loop: Any,
        session_manager: Any,
    ):
        self.bus = bus
        self.agent_loop = agent_loop
        self.session_manager = session_manager
        self._response_futures: dict[str, asyncio.Future] = {}

    async def send_message(self, content: str, session_id: str) -> dict:
        """
        Send a message and wait for response.

        Args:
            content: The message content.
            session_id: The session identifier.

        Returns:
            Dict with response content, session_id, and tools_used.
        """
        # Create a future to wait for the response
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._response_futures[session_id] = future

        try:
            # Publish message to bus
            msg = InboundMessage(
                channel="web",
                sender_id="web_user",
                chat_id=session_id,
                content=content,
                media=[],
                metadata={"sync_response": True},
                session_key_override=session_id,
            )
            await self.bus.publish_inbound(msg)

            # Wait for response with timeout
            try:
                response = await asyncio.wait_for(future, timeout=120.0)
                return response
            except asyncio.TimeoutError:
                return {
                    "response": "Request timed out. Please try again.",
                    "session_id": session_id,
                    "tools_used": [],
                }
        finally:
            self._response_futures.pop(session_id, None)

    def deliver_response(self, session_id: str, response: str, tools_used: list[str] | None = None) -> None:
        """Deliver a response to a waiting request."""
        future = self._response_futures.get(session_id)
        if future and not future.done():
            future.set_result({
                "response": response,
                "session_id": session_id,
                "tools_used": tools_used or [],
            })

    async def get_history(self, session_id: str) -> dict:
        """Get chat history for a session."""
        session = self.session_manager.get_or_create(session_id)
        return {
            "messages": session.messages if session else [],
            "timeline_events": session.timeline_events if session else [],
        }

    async def list_sessions(self) -> list[dict]:
        """List all sessions."""
        sessions = self.session_manager.list_sessions()
        result = []
        for s in sessions:
            session_id = s.get("key", "")
            # Load full session to get first message
            session = self.session_manager.get_or_create(session_id)
            first_message = None
            if session and session.messages:
                for msg in session.messages:
                    if msg.get("role") == "user":
                        first_message = msg.get("content", "")[:50]
                        break
            result.append({
                "session_id": session_id,
                "updated_at": s.get("updated_at"),
                "created_at": session.created_at.isoformat() if session else None,
                "message_count": len(session.messages) if session else 0,
                "first_message": first_message,
                "title": session.title if session else s.get("title"),
            })
        return result

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        # Remove from cache
        self.session_manager.invalidate(session_id)
        # Also delete the session file from disk
        session_path = self.session_manager._get_session_path(session_id)
        if session_path.exists():
            session_path.unlink()
        return True

    async def clear_history(self, session_id: str) -> bool:
        """Clear history for a session."""
        session = self.session_manager.get_or_create(session_id)
        if session:
            session.clear()
            self.session_manager.save(session)
            return True
        return False

    async def rename_session(self, session_id: str, title: str | None) -> dict:
        """Rename a session by updating its user-facing title."""
        session = self.session_manager.get_or_create(session_id)
        session.set_title(title)
        self.session_manager.save(session)
        return {
            "session_id": session_id,
            "title": session.title,
        }

    def ensure_session(self, session_id: str, title: str | None = None) -> dict:
        """Create a session if needed and optionally assign a title."""
        session = self.session_manager.get_or_create(session_id)
        if title:
            session.set_title(title)
        self.session_manager.save(session)
        return {
            "session_id": session_id,
            "title": session.title,
        }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI app."""
    # This will be set by the web command before starting the server
    yield


def create_app(
    bus: MessageBus,
    agent_loop: Any,
    session_manager: Any,
    connection_manager: ConnectionManager,
    web_channel: WebChannel,
) -> FastAPI:
    """Create and configure the FastAPI application."""

    # Create chat service
    chat_service = ChatService(
        bus=bus,
        agent_loop=agent_loop,
        session_manager=session_manager,
    )
    set_chat_service(chat_service)
    set_connection_manager(connection_manager)
    set_inbound_queue(bus.inbound)
    set_cron_service(getattr(agent_loop, "cron_service", None))

    # Create FastAPI app
    app = FastAPI(
        title="sun_agent Web UI",
        description="Web UI for sun_agent AI assistant",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(chat_router)
    app.include_router(config_router)
    app.include_router(cron_router)
    app.include_router(sessions_router)
    app.include_router(status_router)

    # WebSocket endpoint
    @app.websocket("/ws/chat")
    async def ws_chat(websocket: WebSocket, session_id: str | None = None):
        """WebSocket endpoint for real-time chat."""
        if session_id is None:
            # Generate a random session ID for anonymous users
            import uuid
            session_id = f"web:{uuid.uuid4().hex[:12]}"

        await websocket_handler(
            websocket=websocket,
            session_key=session_id,
            connection_manager=connection_manager,
            inbound_queue=bus.inbound,
        )

    # Set WebChannel's ws manager
    web_channel.set_ws_manager(connection_manager)

    # Return app without starting dispatcher - it will be started via lifespan
    return app
