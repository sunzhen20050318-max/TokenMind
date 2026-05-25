"""Sessions API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tokenmind.server.dependencies import get_chat_service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionInfo(BaseModel):
    """Information about a session."""

    session_id: str
    updated_at: str | None = None
    created_at: str | None = None
    message_count: int = 0
    first_message: str | None = None
    title: str | None = None


class SessionListResponse(BaseModel):
    """Response model for listing sessions."""

    sessions: list[SessionInfo]


class ClearHistoryResponse(BaseModel):
    """Response model for clearing session history."""

    session_id: str
    success: bool


class RenameSessionRequest(BaseModel):
    """Request model for renaming a session."""

    title: str | None = None


class RenameSessionResponse(BaseModel):
    """Response model for renaming a session."""

    session_id: str
    title: str | None = None


class SessionPatchPayload(BaseModel):
    """Patch payload for partially updating a session.

    All fields are optional; ``model_dump(exclude_unset=True)`` makes
    omission distinguishable from explicit ``None`` so callers can
    selectively clear preferences (e.g. ``personality: null``).
    """

    active_wiki_kb_id: str | None = None
    # Per-session slash-command preferences:
    personality: str | None = None  # "warm" | "pragmatic" | None (clear)
    plan_mode: bool | None = None    # True / False / None (no change)


class CompactSessionResponse(BaseModel):
    """Response model for the /compact slash command."""

    session_id: str
    previous_offset: int
    consolidated_offset: int
    messages_compacted: int


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    service=Depends(get_chat_service),
):
    """List all sessions."""
    try:
        sessions = await service.list_sessions()
        return SessionListResponse(sessions=sessions)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    service=Depends(get_chat_service),
):
    """Delete a session."""
    try:
        success = await service.delete_session(session_id)
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{session_id}/clear", response_model=ClearHistoryResponse)
async def clear_session_history(
    session_id: str,
    service=Depends(get_chat_service),
):
    """Clear the history of a session without deleting it."""
    try:
        success = await service.clear_history(session_id)
        return ClearHistoryResponse(session_id=session_id, success=success)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{session_id}/messages")
async def delete_session_message(
    session_id: str,
    timestamp: str,
    service=Depends(get_chat_service),
) -> dict:
    """Remove a single message (identified by its timestamp) from a session.

    Deleting an assistant reply also removes the immediately preceding
    tool-call/tool-response messages so the LLM context stays consistent
    on the next turn.
    """
    try:
        removed = await service.delete_message(session_id, timestamp)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    if not removed:
        raise HTTPException(status_code=404, detail="message not found")
    return {"session_id": session_id, "removed": True}


@router.put("/{session_id}", response_model=RenameSessionResponse)
async def rename_session(
    session_id: str,
    request: RenameSessionRequest,
    service=Depends(get_chat_service),
):
    """Rename a session."""
    try:
        result = await service.rename_session(session_id, request.title)
        return RenameSessionResponse(**result)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{session_id}/compact", response_model=CompactSessionResponse)
async def compact_session(
    session_id: str,
    service: Any = Depends(get_chat_service),
) -> CompactSessionResponse:
    """Force-compact session history into HISTORY.md/MEMORY.md.

    Triggered by the user-initiated ``/compact`` slash command. Returns
    the new ``consolidated_offset`` so the frontend can fold the
    archived portion of the chat.
    """
    try:
        result = await service.compact_session(session_id)
        return CompactSessionResponse(**result)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.patch("/{session_id}")
async def patch_session(
    session_id: str,
    payload: SessionPatchPayload,
    service: Any = Depends(get_chat_service),
) -> dict:
    """Partially update session attributes (e.g. active_wiki_kb_id)."""
    try:
        return service.patch_session(session_id, payload.model_dump(exclude_unset=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
