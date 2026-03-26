"""Chat API endpoints."""

from __future__ import annotations

from pydantic import BaseModel
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/api/chat", tags=["chat"])


class SendMessageRequest(BaseModel):
    """Request model for sending a message."""

    message: str
    session_id: str | None = None


class SendMessageResponse(BaseModel):
    """Response model for sending a message."""

    response: str
    session_id: str
    tools_used: list[str] = []


class ChatHistoryResponse(BaseModel):
    """Response model for chat history."""

    session_id: str
    messages: list[dict[str, Any]]
    timeline_events: list[dict[str, Any]] = []


def get_chat_service():
    """Get chat service dependency."""
    # This will be injected via FastAPI dependency
    from sun_agent.server.dependencies import get_chat_service
    return get_chat_service()


@router.post("/send", response_model=SendMessageResponse)
async def send_message(
    request: SendMessageRequest,
    service=Depends(get_chat_service),
):
    """
    Send a message and get the agent's response.

    This is a synchronous request-response endpoint.
    For real-time streaming, use the WebSocket endpoint instead.
    """
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        result = await service.send_message(
            content=request.message,
            session_id=request.session_id or f"web:auto_{id(request)}",
        )
        return SendMessageResponse(
            response=result["response"],
            session_id=result["session_id"],
            tools_used=result.get("tools_used", []),
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: str,
    service=Depends(get_chat_service),
):
    """Get the conversation history for a session."""
    try:
        history = await service.get_history(session_id)
        return ChatHistoryResponse(
            session_id=session_id,
            messages=history.get("messages", []),
            timeline_events=history.get("timeline_events", []),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
