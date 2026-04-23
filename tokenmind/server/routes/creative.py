"""Creative capability API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/creative", tags=["creative"])


class MusicGenerateRequest(BaseModel):
    """Request model for generating music."""

    prompt: str
    lyrics: str | None = None
    lyrics_optimizer: bool = False
    is_instrumental: bool = False
    count: int = Field(default=1, ge=1, le=4)
    reference_audio_base64: str | None = None
    reference_audio_name: str | None = None


class MusicGenerateResponse(BaseModel):
    """Response model for generated music."""

    attachment: dict[str, Any]
    result: dict[str, Any]
    attachments: list[dict[str, Any]]
    results: list[dict[str, Any]]


def get_chat_service():
    """Get chat service dependency."""
    from tokenmind.server.dependencies import get_chat_service

    return get_chat_service()


@router.post("/music/generate", response_model=MusicGenerateResponse)
async def generate_music(
    request: MusicGenerateRequest,
    service=Depends(get_chat_service),
):
    """Generate a music track and return a playable attachment reference."""
    try:
        return await service.generate_music(
            prompt=request.prompt,
            lyrics=request.lyrics,
            lyrics_optimizer=request.lyrics_optimizer,
            is_instrumental=request.is_instrumental,
            count=request.count,
            reference_audio_base64=request.reference_audio_base64,
            reference_audio_name=request.reference_audio_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate music: {exc}") from exc
