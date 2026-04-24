"""Creative capability API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
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


class VoiceCloneUploadResponse(BaseModel):
    """Response after uploading a clone source audio."""

    file_id: int
    filename: str
    bytes: int
    created_at: int | None = None


class VoiceCloneCreateRequest(BaseModel):
    """Request body for creating a voice clone."""

    file_id: int = Field(..., gt=0, description="File id returned by upload endpoint")
    voice_id: str | None = Field(
        default=None,
        description="Optional custom voice id (letters/digits/_-, 8-256 chars, starts with letter)",
    )
    preview_text: str | None = Field(
        default=None, max_length=1000, description="Optional preview text to synthesize"
    )
    need_noise_reduction: bool = False
    need_volume_normalization: bool = False
    language_boost: str | None = Field(default=None, max_length=32)
    source_filename: str | None = Field(default=None, max_length=255)


class VoiceCloneRecordModel(BaseModel):
    """Persisted record for a cloned or designed voice."""

    voice_id: str
    model: str
    provider: str
    created_at: str
    preview_text: str | None = None
    source_filename: str | None = None
    demo_audio_url: str | None = None
    demo_attachment_id: str | None = None
    last_kept_alive_at: str | None = None
    notes: str | None = None
    source: str = "clone"
    display_name: str | None = None


class VoiceDesignCreateRequest(BaseModel):
    """Request body for designing a new voice from a prompt."""

    prompt: str = Field(..., min_length=5, max_length=500)
    preview_text: str = Field(..., min_length=1, max_length=500)
    voice_id: str | None = Field(default=None, max_length=256)
    display_name: str | None = Field(default=None, max_length=64)


class VoiceDesignCreateResponse(VoiceCloneRecordModel):
    trace_id: str | None = None


class VoiceCloneCreateResponse(VoiceCloneRecordModel):
    """Response returned after a successful clone request."""

    input_sensitive: bool = False
    input_sensitive_type: int | None = None
    trace_id: str | None = None


class VoiceCloneListResponse(BaseModel):
    items: list[VoiceCloneRecordModel]


class TtsSynthesizeRequest(BaseModel):
    """Request body for synthesizing speech."""

    text: str = Field(..., min_length=1, max_length=10000)
    voice_id: str = Field(..., min_length=1, max_length=256)
    model: str | None = Field(default=None, max_length=64)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    volume: float = Field(default=1.0, ge=0.01, le=10.0)
    pitch: int = Field(default=0, ge=-12, le=12)
    emotion: str | None = Field(default=None, max_length=32)


class TtsSynthesizeResponse(BaseModel):
    voice_id: str
    model: str
    provider: str
    filename: str
    mime_type: str
    usage_characters: int | None = None
    trace_id: str | None = None
    attachment_id: str
    attachment: dict[str, Any]


class TtsVoiceOption(BaseModel):
    kind: str  # "cloned" or "system"
    voice_id: str
    label: str
    gender: str | None = None
    description: str | None = None
    created_at: str | None = None
    model: str | None = None
    provider: str | None = None
    last_kept_alive_at: str | None = None
    demo_attachment_id: str | None = None
    demo_audio_url: str | None = None
    source_filename: str | None = None
    source: str | None = None
    display_name: str | None = None


class TtsVoiceListResponse(BaseModel):
    cloned: list[TtsVoiceOption]
    system: list[TtsVoiceOption]


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


@router.post("/voice/clone/upload", response_model=VoiceCloneUploadResponse)
async def upload_voice_clone_audio(
    file: UploadFile = File(..., description="Clone source audio (MP3/M4A/WAV, 10s-5min, <=20MB)"),
    purpose: str = Form("voice_clone"),  # noqa: ARG001 (kept for multipart compatibility)
    service=Depends(get_chat_service),
) -> VoiceCloneUploadResponse:
    """Upload a voice clone source audio sample."""
    try:
        data = await file.read()
        filename = file.filename or "clone-sample.mp3"
        content_type = file.content_type
        payload = await service.upload_voice_clone_audio(
            audio_bytes=data,
            filename=filename,
            content_type=content_type,
        )
        return VoiceCloneUploadResponse(**payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to upload voice clone audio: {exc}"
        ) from exc


@router.post("/voice/clone/create", response_model=VoiceCloneCreateResponse)
async def create_voice_clone(
    request: VoiceCloneCreateRequest,
    service=Depends(get_chat_service),
) -> VoiceCloneCreateResponse:
    """Create a cloned voice from an uploaded audio sample."""
    try:
        payload = await service.create_voice_clone(
            file_id=request.file_id,
            voice_id=request.voice_id,
            preview_text=request.preview_text,
            need_noise_reduction=request.need_noise_reduction,
            need_volume_normalization=request.need_volume_normalization,
            language_boost=request.language_boost,
            source_filename=request.source_filename,
        )
        return VoiceCloneCreateResponse(**payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to create voice clone: {exc}"
        ) from exc


@router.get("/voice/clone/list", response_model=VoiceCloneListResponse)
async def list_voice_clones(
    source: str | None = None,
    service=Depends(get_chat_service),
) -> VoiceCloneListResponse:
    """Return persisted voice records. ``source`` filters by 'clone' or 'design'."""
    records = service.list_voice_clones()
    if source:
        records = [record for record in records if record.get("source") == source]
    items = [VoiceCloneRecordModel(**record) for record in records]
    return VoiceCloneListResponse(items=items)


@router.post(
    "/voice/clone/{voice_id}/keep-alive",
    response_model=VoiceCloneRecordModel,
)
async def keep_alive_voice_clone(
    voice_id: str,
    service=Depends(get_chat_service),
) -> VoiceCloneRecordModel:
    """Ping MiniMax with a short TTS call to reset the 7-day inactivity timer."""
    try:
        payload = await service.keep_alive_voice_clone(voice_id)
        return VoiceCloneRecordModel(**payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to keep voice clone alive: {exc}"
        ) from exc


@router.delete("/voice/clone/{voice_id}", response_model=VoiceCloneRecordModel)
async def delete_voice_clone(
    voice_id: str,
    service=Depends(get_chat_service),
) -> VoiceCloneRecordModel:
    """Remove a voice clone record (and its demo attachment) from the workspace."""
    removed = service.delete_voice_clone(voice_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="Voice clone not found")
    return VoiceCloneRecordModel(**removed)


@router.post("/voice/design/create", response_model=VoiceDesignCreateResponse)
async def design_voice(
    request: VoiceDesignCreateRequest,
    service=Depends(get_chat_service),
) -> VoiceDesignCreateResponse:
    """Design a new voice from a text prompt via MiniMax voice_design."""
    try:
        payload = await service.design_voice(
            prompt=request.prompt,
            preview_text=request.preview_text,
            voice_id=request.voice_id,
            display_name=request.display_name,
        )
        return VoiceDesignCreateResponse(**payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to design voice: {exc}"
        ) from exc


@router.post("/voice/tts/synthesize", response_model=TtsSynthesizeResponse)
async def synthesize_voice(
    request: TtsSynthesizeRequest,
    service=Depends(get_chat_service),
) -> TtsSynthesizeResponse:
    """Synthesize ``text`` using the given ``voice_id`` via MiniMax Speech 2.8."""
    try:
        payload = await service.synthesize_voice(
            text=request.text,
            voice_id=request.voice_id,
            model=request.model,
            speed=request.speed,
            volume=request.volume,
            pitch=request.pitch,
            emotion=request.emotion,
        )
        return TtsSynthesizeResponse(**payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to synthesize speech: {exc}"
        ) from exc


@router.get("/voice/tts/voices", response_model=TtsVoiceListResponse)
async def list_tts_voices(service=Depends(get_chat_service)) -> TtsVoiceListResponse:
    """Return available voices for the TTS picker (cloned + system)."""
    payload = service.list_tts_voices()
    return TtsVoiceListResponse(
        cloned=[TtsVoiceOption(**item) for item in payload.get("cloned", [])],
        system=[TtsVoiceOption(**item) for item in payload.get("system", [])],
    )
