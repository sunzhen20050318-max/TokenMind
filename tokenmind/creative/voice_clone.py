"""Voice cloning helpers for creative capabilities.

Integrates MiniMax voice cloning APIs:

- POST /v1/files/upload (purpose=voice_clone) to upload a clone audio sample
- POST /v1/voice_clone to create a voice from the uploaded file
- POST /v1/t2a_v2 to render a preview with the cloned voice_id
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from tokenmind.config.schema import CreativeCapabilityConfig
from tokenmind.providers.registry import find_by_name

_DEFAULT_MINIMAX_API_BASE = "https://api.minimaxi.com/v1"
_DEFAULT_MODEL = "speech-2.8-hd"
_VOICE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{7,255}$")


@dataclass(frozen=True)
class UploadedCloneAudio:
    """Metadata returned after uploading a clone audio sample."""

    file_id: int
    filename: str
    bytes: int
    created_at: int | None


@dataclass(frozen=True)
class ClonedVoiceResult:
    """Result of a successful voice clone request."""

    voice_id: str
    model: str
    provider: str
    demo_audio_url: str | None
    input_sensitive: bool
    input_sensitive_type: int | None
    trace_id: str | None


class VoiceCloneService:
    """Create and manage custom voices via MiniMax's voice cloning APIs."""

    def __init__(self, capability: CreativeCapabilityConfig):
        self._capability = capability

    @property
    def provider(self) -> str:
        return (self._capability.provider or "").strip()

    @property
    def model(self) -> str:
        configured = (self._capability.model or "").strip()
        return configured or _DEFAULT_MODEL

    @property
    def api_base(self) -> str:
        configured = (self._capability.api_base or "").strip()
        if configured:
            return configured.rstrip("/")
        if self.provider == "minimax":
            return _DEFAULT_MINIMAX_API_BASE
        spec = find_by_name(self.provider)
        if spec and spec.default_api_base:
            return spec.default_api_base.rstrip("/")
        return _DEFAULT_MINIMAX_API_BASE

    @property
    def extra_headers(self) -> dict[str, str]:
        return dict(self._capability.extra_headers or {})

    @classmethod
    def is_configured(cls, capability: CreativeCapabilityConfig | None) -> bool:
        """Return True when the voice clone capability has enough data to be used."""
        if capability is None or not capability.enabled:
            return False
        provider = (capability.provider or "").strip()
        api_key = (capability.api_key or "").strip()
        return bool(provider and api_key)

    async def upload_audio(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        content_type: str | None = None,
    ) -> UploadedCloneAudio:
        """Upload an audio sample used as the clone source."""
        if not audio_bytes:
            raise ValueError("Audio file is empty")
        safe_name = filename.strip() or f"clone-{uuid.uuid4().hex[:8]}.mp3"
        if self.provider != "minimax":
            raise ValueError(f"Voice clone provider '{self.provider}' is not supported yet")

        headers = {"Authorization": f"Bearer {self._require_api_key()}"}
        headers.update(self.extra_headers)
        endpoint = self._resolve_endpoint("files/upload")
        files = {
            "file": (safe_name, audio_bytes, content_type or "application/octet-stream"),
        }
        data = {"purpose": "voice_clone"}

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(endpoint, headers=headers, data=data, files=files)
            response.raise_for_status()
            payload = response.json()

        _raise_for_minimax_error(payload, "MiniMax voice clone upload returned an error")
        file_info = payload.get("file") or {}
        file_id = file_info.get("file_id")
        if not isinstance(file_id, int):
            raise RuntimeError("MiniMax voice clone upload did not return a file_id")
        return UploadedCloneAudio(
            file_id=file_id,
            filename=str(file_info.get("filename") or safe_name),
            bytes=int(file_info.get("bytes") or len(audio_bytes)),
            created_at=file_info.get("created_at"),
        )

    async def keep_alive_voice(
        self,
        *,
        voice_id: str,
        text: str = "你好",
    ) -> None:
        """Ping MiniMax with a short TTS call to reset the 7-day inactivity clock.

        The response audio is discarded — we only care that the request succeeds.
        """
        if not voice_id.strip():
            raise ValueError("voice_id is required for keep-alive")
        if self.provider != "minimax":
            raise ValueError(f"Voice clone provider '{self.provider}' is not supported yet")

        headers = {
            "Authorization": f"Bearer {self._require_api_key()}",
            "Content-Type": "application/json",
        }
        headers.update(self.extra_headers)
        endpoint = self._resolve_endpoint("t2a_v2")
        payload: dict[str, Any] = {
            "model": self.model,
            "text": text[:32] or "你好",
            "voice_setting": {"voice_id": voice_id.strip()},
            "audio_setting": {"sample_rate": 16000, "format": "mp3"},
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        _raise_for_minimax_error(data, "MiniMax keep-alive synthesize returned an error")

    @staticmethod
    async def download_demo_audio(url: str) -> tuple[bytes, str]:
        """Fetch a MiniMax CDN demo audio URL and return (bytes, mime_type)."""
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "audio/mpeg").split(";")[0].strip()
            return response.content, content_type or "audio/mpeg"

    async def clone_voice(
        self,
        *,
        file_id: int,
        voice_id: str | None = None,
        preview_text: str | None = None,
        need_noise_reduction: bool = False,
        need_volume_normalization: bool = False,
        language_boost: str | None = None,
    ) -> ClonedVoiceResult:
        """Clone a voice from an uploaded audio sample."""
        if not isinstance(file_id, int) or file_id <= 0:
            raise ValueError("file_id must be a positive integer")
        if self.provider != "minimax":
            raise ValueError(f"Voice clone provider '{self.provider}' is not supported yet")

        final_voice_id = (voice_id or "").strip() or self._generate_voice_id()
        if not _VOICE_ID_PATTERN.match(final_voice_id):
            raise ValueError(
                "voice_id must start with a letter and be 8-256 characters long; "
                "only letters, digits, '-' and '_' are allowed"
            )

        headers = {
            "Authorization": f"Bearer {self._require_api_key()}",
            "Content-Type": "application/json",
        }
        headers.update(self.extra_headers)
        endpoint = self._resolve_endpoint("voice_clone")
        payload: dict[str, Any] = {
            "file_id": file_id,
            "voice_id": final_voice_id,
            "need_noise_reduction": bool(need_noise_reduction),
            "need_volume_normalization": bool(need_volume_normalization),
        }
        cleaned_preview = (preview_text or "").strip()
        if cleaned_preview:
            payload["text"] = cleaned_preview[:1000]
            payload["model"] = self.model
        boost = (language_boost or "").strip()
        if boost:
            payload["language_boost"] = boost

        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        _raise_for_minimax_error(data, "MiniMax voice_clone returned an error")
        sensitive_type = data.get("input_sensitive_type") or data.get("input_sensitive")
        return ClonedVoiceResult(
            voice_id=final_voice_id,
            model=self.model,
            provider=self.provider,
            demo_audio_url=_extract_demo_audio(data),
            input_sensitive=bool(data.get("input_sensitive")) and bool(sensitive_type),
            input_sensitive_type=sensitive_type if isinstance(sensitive_type, int) else None,
            trace_id=data.get("trace_id"),
        )

    def _require_api_key(self) -> str:
        key = (self._capability.api_key or "").strip()
        if not key:
            raise ValueError("Voice clone capability is missing api_key")
        return key

    def _resolve_endpoint(self, path: str) -> str:
        base = self.api_base.rstrip("/")
        suffix = path.lstrip("/")
        return f"{base}/{suffix}"

    @staticmethod
    def _generate_voice_id() -> str:
        return f"clone_{uuid.uuid4().hex[:12]}"


def _raise_for_minimax_error(data: dict[str, Any], fallback: str) -> None:
    base_resp = data.get("base_resp") or {}
    status_code = base_resp.get("status_code")
    if status_code not in (None, 0):
        raise RuntimeError(base_resp.get("status_msg") or fallback)


def _extract_demo_audio(data: dict[str, Any]) -> str | None:
    demo = data.get("demo_audio")
    if isinstance(demo, str) and demo.strip():
        return demo.strip()
    return None
