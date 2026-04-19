"""Memory Center API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/memory", tags=["memory"])


class MemoryContextItemResponse(BaseModel):
    """One message preview item in the current short-term context."""

    role: str
    content: str
    timestamp: str | None = None


class MemoryArchiveItemResponse(BaseModel):
    """One visible block from the history archive."""

    id: str
    content: str
    timestamp: str | None = None


class LongTermMemoryResponse(BaseModel):
    """Editable long-term memory payload."""

    content: str
    updated_at: str | None = None
    character_count: int
    editable: bool = True


class CurrentContextResponse(BaseModel):
    """Read-only active session context preview."""

    session_id: str | None = None
    session_label: str | None = None
    items: list[MemoryContextItemResponse] = []


class ArchivePreviewResponse(BaseModel):
    """Recent archive preview surface."""

    query: str = ""
    total: int
    items: list[MemoryArchiveItemResponse] = []


class MemorySettingsResponse(BaseModel):
    """Small memory settings/status summary for the Memory Center."""

    auto_consolidation: bool = True
    template_enabled: bool = False
    editable_long_term: bool = True
    summary: str


class MemoryOverviewResponse(BaseModel):
    """Memory Center response payload."""

    long_term: LongTermMemoryResponse
    current_context: CurrentContextResponse
    archive: ArchivePreviewResponse
    settings: MemorySettingsResponse


class UpdateLongTermMemoryRequest(BaseModel):
    """Update request for long-term memory."""

    content: str


def get_chat_service():
    """Get chat service dependency."""
    from sun_agent.server.dependencies import get_chat_service

    return get_chat_service()


@router.get("", response_model=MemoryOverviewResponse)
async def get_memory_overview(
    session_id: str | None = None,
    archive_query: str | None = None,
    service=Depends(get_chat_service),
):
    """Return Memory Center payload for the current workspace."""
    try:
        return service.get_memory_overview(session_id=session_id, archive_query=archive_query)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load memory overview: {exc}") from exc


@router.put("/long-term", response_model=LongTermMemoryResponse)
async def update_long_term_memory(
    request: UpdateLongTermMemoryRequest,
    service=Depends(get_chat_service),
):
    """Persist long-term memory content from the Memory Center editor."""
    try:
        return service.update_long_term_memory(request.content)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update long-term memory: {exc}") from exc
