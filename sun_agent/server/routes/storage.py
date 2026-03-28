"""Storage API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/storage", tags=["storage"])


class StorageReferenceResponse(BaseModel):
    """Session reference for an uploaded file."""

    session_id: str
    title: str


class StorageFileResponse(BaseModel):
    """Single uploaded file item."""

    name: str
    stored_name: str
    path: str
    size: int
    mime_type: str | None = None
    category: str
    is_image: bool = False
    modified_at: str
    created_at: str
    referenced: bool = False
    reference_count: int = 0
    referenced_by: list[StorageReferenceResponse] = []
    can_delete: bool = False


class StorageSummaryResponse(BaseModel):
    """Upload storage summary."""

    used_bytes: int
    quota_bytes: int
    available_bytes: int
    max_file_bytes: int
    file_count: int
    referenced_file_count: int
    unreferenced_file_count: int
    stale_unreferenced_file_count: int
    retention_days: int
    cleanup_interval_hours: int


class StorageOverviewResponse(BaseModel):
    """Storage center payload."""

    summary: StorageSummaryResponse
    files: list[StorageFileResponse]


class StorageCleanupResponse(BaseModel):
    """Manual cleanup result."""

    success: bool
    deleted_files: int
    deleted_dirs: int


class DeleteStorageFileRequest(BaseModel):
    """Delete one upload file by absolute path."""

    path: str


class DeleteStorageFileResponse(BaseModel):
    """Delete one upload file result."""

    success: bool
    path: str
    deleted_bytes: int


def get_chat_service():
    """Get chat service dependency."""
    from sun_agent.server.dependencies import get_chat_service

    return get_chat_service()


@router.get("", response_model=StorageOverviewResponse)
async def get_storage_overview(service=Depends(get_chat_service)):
    """Return current upload usage and file list."""
    try:
        return service.get_storage_overview()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load storage overview: {exc}") from exc


@router.post("/cleanup", response_model=StorageCleanupResponse)
async def cleanup_storage(service=Depends(get_chat_service)):
    """Run upload cleanup immediately using the configured retention policy."""
    try:
        result = service.cleanup_uploads(force=True)
        return {
            "success": True,
            "deleted_files": result["deleted_files"],
            "deleted_dirs": result["deleted_dirs"],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to cleanup storage: {exc}") from exc


@router.post("/delete", response_model=DeleteStorageFileResponse)
async def delete_storage_file(
    request: DeleteStorageFileRequest,
    service=Depends(get_chat_service),
):
    """Delete one unreferenced upload file."""
    try:
        return service.delete_upload_file(request.path)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete upload file: {exc}") from exc
