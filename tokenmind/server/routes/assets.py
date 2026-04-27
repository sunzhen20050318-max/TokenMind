"""Asset library API endpoints.

Exposes the assistant attachments index (images / videos / audio studios / files) as a
browsable, paginated, favorite-able catalog backing the ``资产库`` page.
"""

from __future__ import annotations

from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tokenmind.server.attachments import AttachmentRecord, AttachmentStore

router = APIRouter(prefix="/api/assets", tags=["assets"])


# Categories surfaced by the asset library UI.
_IMAGE_CATEGORIES: set[str] = {"image"}
_VIDEO_CATEGORIES: set[str] = {"video"}
_AUDIO_CATEGORIES: set[str] = {"audio"}
_MUSIC_SESSIONS: set[str] = {"creative:music"}
_TTS_SESSIONS: set[str] = {"creative:tts"}
_VOICE_CLONE_SESSIONS: set[str] = {"creative:voice_clone"}
_VOICE_DESIGN_SESSIONS: set[str] = {"creative:voice_design"}
# "file" tab covers everything else that isn't audio (audio is consumed by the
# voice/music studios separately).
_FILE_EXCLUDED: set[str] = {"image", "video", "audio"}

CategoryFilter = Literal[
    "image",
    "video",
    "music",
    "tts",
    "voice_clone",
    "voice_design",
    "audio",
    "file",
]


class AssetItem(BaseModel):
    id: str
    name: str
    category: str
    is_image: bool
    mime_type: str | None = None
    size: int
    session_id: str
    project_id: str | None = None
    created_at: str
    favorite: bool
    storage_path: str
    preview_text: str | None = None


class AssetListResponse(BaseModel):
    items: list[AssetItem]
    next_cursor: int | None
    total: int


class AssetFavoriteRequest(BaseModel):
    favorite: bool


class AssetActionResponse(BaseModel):
    success: bool
    id: str


def _attachment_store() -> AttachmentStore:
    from tokenmind.server.dependencies import get_chat_service

    service = get_chat_service()
    store = getattr(service, "attachments", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Attachment store unavailable")
    return store


def _project_lookup() -> Callable[[str], str | None]:
    """Return a function that maps a session_id to its project_id (if any).

    Reads through ``service.session_manager`` so the asset library can route
    "回到会话" jumps into the correct project workspace on the frontend.
    """
    try:
        from tokenmind.server.dependencies import get_chat_service

        service = get_chat_service()
    except Exception:
        return lambda _session_id: None

    session_manager = getattr(service, "session_manager", None)
    if session_manager is None:
        return lambda _session_id: None

    cache: dict[str, str | None] = {}

    def lookup(session_id: str) -> str | None:
        if session_id in cache:
            return cache[session_id]
        result: str | None = None
        try:
            session: Any = session_manager.get_or_create(session_id)
            value = getattr(session, "project_id", None)
            if isinstance(value, str) and value.strip():
                result = value
        except Exception:
            result = None
        cache[session_id] = result
        return result

    return lookup


def _matches_category(record: AttachmentRecord, category: CategoryFilter) -> bool:
    if record.category in _VIDEO_CATEGORIES and category == "video":
        return True
    if record.category in _IMAGE_CATEGORIES and category == "image":
        return True
    if category == "music":
        return record.category in _AUDIO_CATEGORIES and record.session_id in _MUSIC_SESSIONS
    if category == "tts":
        return record.category in _AUDIO_CATEGORIES and record.session_id in _TTS_SESSIONS
    if category == "voice_clone":
        return record.category in _AUDIO_CATEGORIES and record.session_id in _VOICE_CLONE_SESSIONS
    if category == "voice_design":
        return record.category in _AUDIO_CATEGORIES and record.session_id in _VOICE_DESIGN_SESSIONS
    if record.category in _AUDIO_CATEGORIES and category == "audio":
        return True
    if category == "file":
        return record.category not in _FILE_EXCLUDED
    return False


def _to_item(
    record: AttachmentRecord,
    project_lookup: Callable[[str], str | None] | None = None,
) -> AssetItem:
    project_id: str | None = None
    if project_lookup is not None:
        try:
            project_id = project_lookup(record.session_id)
        except Exception:
            project_id = None
    return AssetItem(
        id=record.id,
        name=record.name,
        category=record.category,
        is_image=record.is_image,
        mime_type=record.mime_type or None,
        size=record.size,
        session_id=record.session_id,
        project_id=project_id,
        created_at=record.created_at,
        favorite=record.favorite,
        storage_path=record.storage_path,
        preview_text=record.preview_text,
    )


@router.get("", response_model=AssetListResponse)
async def list_assets(
    category: CategoryFilter = "image",
    favorite: bool | None = None,
    limit: int = 60,
    cursor: int = 0,
    store: AttachmentStore = Depends(_attachment_store),
    project_lookup: Callable[[str], str | None] = Depends(_project_lookup),
) -> AssetListResponse:
    """Return paginated asset items, newest first.

    ``cursor`` is the offset into the filtered list. When the response includes
    ``next_cursor`` the client can request the next page by passing that value.
    """
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200
    if cursor < 0:
        cursor = 0

    records = [
        record
        for record in store.list_records()
        if record.status != "expired" and _matches_category(record, category)
    ]
    if favorite is True:
        records = [record for record in records if record.favorite]
    elif favorite is False:
        records = [record for record in records if not record.favorite]

    records.sort(key=lambda record: record.created_at, reverse=True)

    total = len(records)
    page = records[cursor : cursor + limit]
    next_cursor = cursor + limit if cursor + limit < total else None

    return AssetListResponse(
        items=[_to_item(record, project_lookup) for record in page],
        next_cursor=next_cursor,
        total=total,
    )


@router.patch("/{asset_id}", response_model=AssetItem)
async def update_asset(
    asset_id: str,
    payload: AssetFavoriteRequest,
    store: AttachmentStore = Depends(_attachment_store),
    project_lookup: Callable[[str], str | None] = Depends(_project_lookup),
) -> AssetItem:
    """Toggle the favorite flag for an asset."""
    record = store.set_favorite(asset_id, payload.favorite)
    return _to_item(record, project_lookup)


@router.delete("/{asset_id}", response_model=AssetActionResponse)
async def delete_asset(
    asset_id: str,
    store: AttachmentStore = Depends(_attachment_store),
) -> AssetActionResponse:
    """Permanently remove an asset (file + index entry)."""
    store.remove(asset_id)
    return AssetActionResponse(success=True, id=asset_id)
