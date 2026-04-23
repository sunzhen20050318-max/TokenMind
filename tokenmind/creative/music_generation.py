"""Music generation helpers for creative capabilities."""

from __future__ import annotations

import base64
import binascii
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from tokenmind.config.schema import CreativeCapabilityConfig
from tokenmind.providers.registry import find_by_name

_DEFAULT_MUSIC_MODELS: dict[str, str] = {
    "minimax": "music-2.6",
}
_DEFAULT_MINIMAX_MUSIC_API_BASE = "https://api.minimaxi.com/v1"


@dataclass(frozen=True)
class GeneratedMusicResult:
    """One generated music payload ready to be attached or downloaded."""

    filename: str
    mime_type: str
    data: bytes
    model: str
    provider: str
    duration_ms: int | None = None
    trace_id: str | None = None


class MusicGenerationService:
    """Generate music using the configured creative music capability."""

    def __init__(self, capability: CreativeCapabilityConfig):
        self._capability = capability

    @property
    def provider(self) -> str:
        return (self._capability.provider or "").strip()

    @property
    def model(self) -> str:
        configured = (self._capability.model or "").strip()
        if configured:
            return configured
        return _DEFAULT_MUSIC_MODELS.get(self.provider, "music-2.6")

    @property
    def api_base(self) -> str | None:
        configured = (self._capability.api_base or "").strip()
        if configured:
            return configured
        if self.provider == "minimax":
            return _DEFAULT_MINIMAX_MUSIC_API_BASE
        spec = find_by_name(self.provider)
        return spec.default_api_base if spec and spec.default_api_base else None

    @property
    def extra_headers(self) -> dict[str, str]:
        return dict(self._capability.extra_headers or {})

    @classmethod
    def is_configured(cls, capability: CreativeCapabilityConfig | None) -> bool:
        """Return True when the music capability has enough data to be used."""
        if capability is None or not capability.enabled:
            return False
        provider = (capability.provider or "").strip()
        api_key = (capability.api_key or "").strip()
        return bool(provider and api_key)

    async def generate(
        self,
        *,
        prompt: str,
        lyrics: str | None = None,
        lyrics_optimizer: bool = False,
        is_instrumental: bool = False,
        reference_audio_base64: str | None = None,
    ) -> GeneratedMusicResult:
        """Generate one music track."""
        if not self.is_configured(self._capability):
            raise ValueError("Music generation is not configured or enabled")
        if not prompt.strip():
            raise ValueError("Prompt cannot be empty")
        has_reference_audio = bool((reference_audio_base64 or "").strip())
        if has_reference_audio and len(prompt.strip()) < 10:
            raise ValueError("Reference-audio generation requires a style prompt of at least 10 characters")
        if not has_reference_audio and not is_instrumental and not lyrics_optimizer and not (lyrics or "").strip():
            raise ValueError("Lyrics are required unless auto lyrics or instrumental mode is enabled")
        if self.provider != "minimax":
            raise ValueError(f"Music provider '{self.provider}' is not supported yet")

        return await self._generate_minimax(
            prompt=prompt,
            lyrics=lyrics,
            lyrics_optimizer=lyrics_optimizer,
            is_instrumental=is_instrumental,
            reference_audio_base64=reference_audio_base64,
        )

    async def _generate_minimax(
        self,
        *,
        prompt: str,
        lyrics: str | None,
        lyrics_optimizer: bool,
        is_instrumental: bool,
        reference_audio_base64: str | None,
    ) -> GeneratedMusicResult:
        endpoint = _resolve_minimax_music_endpoint(self.api_base)
        headers = {"Authorization": f"Bearer {(self._capability.api_key or '').strip()}"}
        headers.update(self.extra_headers)
        has_reference_audio = bool((reference_audio_base64 or "").strip())
        if has_reference_audio:
            return await self._generate_minimax_cover(
                prompt=prompt,
                lyrics=lyrics,
                reference_audio_base64=reference_audio_base64 or "",
            )

        model = _resolve_minimax_model_for_mode(self.model, reference_audio=False)
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt.strip(),
            "output_format": "hex",
            "audio_setting": {
                "sample_rate": 44100,
                "bitrate": 256000,
                "format": "mp3",
            },
        }

        if is_instrumental:
            payload["is_instrumental"] = True
        else:
            if lyrics and lyrics.strip():
                payload["lyrics"] = lyrics.strip()
            payload["lyrics_optimizer"] = bool(lyrics_optimizer)

        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        _raise_for_minimax_error(data, "MiniMax music API returned an error")
        audio_hex = _extract_audio_hex(data)
        if not audio_hex:
            raise RuntimeError("MiniMax music API returned no audio")

        return GeneratedMusicResult(
            filename=f"generated-music-{uuid.uuid4().hex[:8]}.mp3",
            mime_type="audio/mpeg",
            data=bytes.fromhex(audio_hex),
            model=model,
            provider=self.provider,
            duration_ms=_extract_duration_ms(data),
            trace_id=data.get("trace_id"),
        )

    async def _generate_minimax_cover(
        self,
        *,
        prompt: str,
        lyrics: str | None,
        reference_audio_base64: str,
    ) -> GeneratedMusicResult:
        headers = {"Authorization": f"Bearer {(self._capability.api_key or '').strip()}"}
        headers.update(self.extra_headers)
        cover_model = _resolve_minimax_model_for_mode(self.model, reference_audio=True)
        normalized_audio = _normalize_reference_audio_base64(reference_audio_base64)
        preprocess_payload = {
            "model": cover_model,
            "audio_base64": normalized_audio,
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            preprocess_response = await client.post(
                _resolve_minimax_cover_preprocess_endpoint(self.api_base),
                headers=headers,
                json=preprocess_payload,
            )
            preprocess_response.raise_for_status()
            preprocess_data = preprocess_response.json()

            _raise_for_minimax_error(preprocess_data, "MiniMax music cover preprocess returned an error")
            cover_feature_id = preprocess_data.get("cover_feature_id")
            if not isinstance(cover_feature_id, str) or not cover_feature_id.strip():
                raise RuntimeError("MiniMax music cover preprocess returned no cover_feature_id")

            cover_lyrics = _normalize_cover_lyrics(lyrics or preprocess_data.get("formatted_lyrics") or "")
            payload: dict[str, Any] = {
                "model": cover_model,
                "cover_feature_id": cover_feature_id,
                "lyrics": cover_lyrics,
                "prompt": prompt.strip(),
                "output_format": "hex",
                "audio_setting": {
                    "sample_rate": 44100,
                    "bitrate": 256000,
                    "format": "mp3",
                },
            }
            response = await client.post(
                _resolve_minimax_music_endpoint(self.api_base),
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        _raise_for_minimax_error(data, "MiniMax music API returned an error")
        audio_hex = _extract_audio_hex(data)
        if not audio_hex:
            raise RuntimeError("MiniMax music API returned no audio")

        return GeneratedMusicResult(
            filename=f"generated-music-{uuid.uuid4().hex[:8]}.mp3",
            mime_type="audio/mpeg",
            data=bytes.fromhex(audio_hex),
            model=cover_model,
            provider=self.provider,
            duration_ms=_extract_duration_ms(data),
            trace_id=data.get("trace_id"),
        )


def _resolve_minimax_music_endpoint(api_base: str | None) -> str:
    """Resolve the MiniMax native music generation endpoint."""
    base = (api_base or _DEFAULT_MINIMAX_MUSIC_API_BASE).rstrip("/")
    if base.endswith("/music_generation"):
        return base
    return f"{base}/music_generation"


def _resolve_minimax_cover_preprocess_endpoint(api_base: str | None) -> str:
    """Resolve the MiniMax cover preprocess endpoint."""
    base = (api_base or _DEFAULT_MINIMAX_MUSIC_API_BASE).rstrip("/")
    if base.endswith("/music_cover_preprocess"):
        return base
    if base.endswith("/music_generation"):
        base = base.rsplit("/", 1)[0]
    return f"{base}/music_cover_preprocess"


def _resolve_minimax_model_for_mode(configured_model: str, *, reference_audio: bool) -> str:
    """Use MiniMax cover models when a reference audio file is supplied."""
    model = (configured_model or "music-2.6").strip() or "music-2.6"
    if not reference_audio:
        return model
    return "music-cover-free" if model.endswith("-free") else "music-cover"


def _raise_for_minimax_error(data: dict[str, Any], fallback: str) -> None:
    base_resp = data.get("base_resp") or {}
    if base_resp.get("status_code") not in (None, 0):
        raise RuntimeError(base_resp.get("status_msg") or fallback)


def _normalize_reference_audio_base64(value: str) -> str:
    """Strip data-url prefixes and validate that the reference is valid base64."""
    normalized = value.strip()
    if "," in normalized and normalized.lower().startswith("data:"):
        normalized = normalized.split(",", 1)[1].strip()
    try:
        base64.b64decode(normalized, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Reference audio must be valid base64") from exc
    return normalized


def _normalize_cover_lyrics(value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 10:
        raise RuntimeError("MiniMax music cover preprocess returned no usable lyrics")
    return normalized[:1000]


def _extract_audio_hex(data: dict[str, Any]) -> str | None:
    payload = data.get("data")
    if isinstance(payload, dict):
        audio = payload.get("audio")
        if isinstance(audio, str):
            return audio
    audio = data.get("audio")
    return audio if isinstance(audio, str) else None


def _extract_duration_ms(data: dict[str, Any]) -> int | None:
    payload = data.get("data")
    duration = payload.get("duration") if isinstance(payload, dict) else data.get("duration")
    return duration if isinstance(duration, int) else None
