"""Voice transcription endpoint backing the Web UI mic button.

Accepts a short audio clip recorded in the browser and returns the recognised
text so the frontend can drop it into the chat composer. The default backend
is local faster-whisper (no API key); the ``groq`` backend reuses the cloud
Whisper provider when ``transcription.backend`` is set to ``groq``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from loguru import logger
from pydantic import BaseModel

from tokenmind.config.loader import load_config

router = APIRouter(prefix="/api/transcribe", tags=["transcription"])

# Guard against oversized uploads — voice-input clips are seconds long, so a
# few tens of MB is plenty and keeps a stray large file from blocking a worker.
_MAX_AUDIO_BYTES = 25 * 1024 * 1024


class TranscriptionResponse(BaseModel):
    text: str


@router.post("", response_model=TranscriptionResponse)
async def transcribe_audio(file: UploadFile = File(...)) -> TranscriptionResponse:
    """Transcribe a recorded audio clip to text."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="音频为空")
    if len(data) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="音频过大，请缩短录音")

    config = load_config()
    cfg = config.transcription

    suffix = Path(file.filename or "audio.webm").suffix or ".webm"
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)

        if cfg.backend == "groq":
            from tokenmind.providers.transcription import GroqTranscriptionProvider

            # Groq isn't a registered LLM provider, so its key lives outside
            # ProvidersConfig — read it defensively, falling back to the
            # GROQ_API_KEY environment variable (handled by the provider).
            groq_cfg = getattr(config.providers, "groq", None)
            api_key = getattr(groq_cfg, "api_key", "") or None
            provider = GroqTranscriptionProvider(api_key=api_key)
            if not provider.api_key:
                raise HTTPException(
                    status_code=400,
                    detail="Groq 转写需要配置 GROQ_API_KEY 环境变量",
                )
            text = await provider.transcribe(tmp_path)
        else:
            from tokenmind.providers.transcription import (
                LocalWhisperTranscriptionProvider,
            )

            provider = LocalWhisperTranscriptionProvider(
                model=cfg.model,
                device=cfg.device,
                compute_type=cfg.compute_type,
                language=cfg.language,
            )
            text = await provider.transcribe(tmp_path)

        return TranscriptionResponse(text=text.strip())
    except HTTPException:
        raise
    except RuntimeError as e:
        # Missing optional dependency (faster-whisper) — surface the install hint.
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.error("Transcription failed: {}", e)
        raise HTTPException(status_code=500, detail="语音转写失败，请重试") from e
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
