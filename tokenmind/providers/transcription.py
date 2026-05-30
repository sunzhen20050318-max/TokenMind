"""Voice transcription providers (local faster-whisper + Groq cloud)."""

import os
import threading
from pathlib import Path
from typing import Any

import httpx
from loguru import logger


class GroqTranscriptionProvider:
    """
    Voice transcription provider using Groq's Whisper API.

    Groq offers extremely fast transcription with a generous free tier.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.api_url = "https://api.groq.com/openai/v1/audio/transcriptions"

    async def transcribe(self, file_path: str | Path) -> str:
        """
        Transcribe an audio file using Groq.

        Args:
            file_path: Path to the audio file.

        Returns:
            Transcribed text.
        """
        if not self.api_key:
            logger.warning("Groq API key not configured for transcription")
            return ""

        path = Path(file_path)
        if not path.exists():
            logger.error("Audio file not found: {}", file_path)
            return ""

        try:
            async with httpx.AsyncClient() as client:
                with open(path, "rb") as f:
                    files = {
                        "file": (path.name, f),
                        "model": (None, "whisper-large-v3"),
                    }
                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                    }

                    response = await client.post(
                        self.api_url,
                        headers=headers,
                        files=files,
                        timeout=60.0
                    )

                    response.raise_for_status()
                    data = response.json()
                    return data.get("text", "")

        except Exception as e:
            logger.error("Groq transcription error: {}", e)
            return ""


# Loaded faster-whisper models are cached process-wide and reused across
# requests — the first call pays the model-load cost (and the one-time weight
# download), every later call is warm.
_LOCAL_MODELS: dict[tuple[str, str, str], Any] = {}
_LOCAL_MODELS_LOCK = threading.Lock()


class LocalWhisperTranscriptionProvider:
    """Offline transcription via ``faster-whisper`` (CTranslate2 Whisper).

    Runs entirely on the local machine — no API key, no network — which is why
    it is the default backend for the Web UI voice-input button. Model weights
    are downloaded once on first use and cached under the HuggingFace cache dir.
    """

    def __init__(
        self,
        model: str = "base",
        device: str = "auto",
        compute_type: str = "auto",
        language: str = "",
    ):
        self.model = model or "base"
        self.device = device or "auto"
        self.compute_type = compute_type or "auto"
        # Empty language -> auto-detect (Whisper handles this well for zh/en).
        self.language = language.strip() or None

    def _get_model(self) -> Any:
        key = (self.model, self.device, self.compute_type)
        cached = _LOCAL_MODELS.get(key)
        if cached is not None:
            return cached
        with _LOCAL_MODELS_LOCK:
            cached = _LOCAL_MODELS.get(key)
            if cached is not None:
                return cached
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # pragma: no cover - depends on optional extra
                raise RuntimeError(
                    "本地语音转写需要 faster-whisper，请先安装：pip install faster-whisper"
                ) from exc
            logger.info(
                "Loading faster-whisper model '{}' (device={}, compute_type={})",
                self.model,
                self.device,
                self.compute_type,
            )
            model = WhisperModel(
                self.model, device=self.device, compute_type=self.compute_type
            )
            _LOCAL_MODELS[key] = model
            return model

    async def transcribe(self, file_path: str | Path) -> str:
        """Transcribe an audio file, returning the recognised text."""
        path = Path(file_path)
        if not path.exists():
            logger.error("Audio file not found: {}", file_path)
            return ""

        import asyncio

        def _run() -> str:
            model = self._get_model()
            segments, _info = model.transcribe(str(path), language=self.language)
            return "".join(segment.text for segment in segments).strip()

        try:
            # faster-whisper is synchronous and CPU-bound — keep the event loop
            # responsive by running it in the default thread pool.
            return await asyncio.to_thread(_run)
        except Exception as e:
            logger.error("Local whisper transcription error: {}", e)
            raise
