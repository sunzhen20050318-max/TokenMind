"""Voice design helpers backed by MiniMax ``POST /v1/voice_design``.

Voice design generates a brand new ``voice_id`` from a natural-language prompt —
no audio sample required. Unlike voice cloning, the API returns the trial audio
inline as hex-encoded bytes rather than a CDN URL.

Billing note: voice design creation + trial audio is pay-as-you-go on MiniMax
(Token Plan does not cover it). Once the returned ``voice_id`` exists it can be
used with Speech 2.8 TTS under the normal Token Plan character quota.
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

PREVIEW_TEXT_MAX = 500
PROMPT_MIN = 5
PROMPT_MAX = 500


@dataclass(frozen=True)
class DesignedVoiceResult:
    """Result of a successful voice design request."""

    voice_id: str
    model: str
    provider: str
    trial_audio: bytes
    mime_type: str
    trace_id: str | None


class VoiceDesignService:
    """Generate new voices via MiniMax voice design."""

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
        if capability is None or not capability.enabled:
            return False
        provider = (capability.provider or "").strip()
        api_key = (capability.api_key or "").strip()
        return bool(provider and api_key)

    async def design_voice(
        self,
        *,
        prompt: str,
        preview_text: str,
        voice_id: str | None = None,
        aigc_watermark: bool = False,
    ) -> DesignedVoiceResult:
        """Call ``POST /v1/voice_design`` and return the generated voice."""
        cleaned_prompt = prompt.strip()
        if len(cleaned_prompt) < PROMPT_MIN:
            raise ValueError(f"Prompt must be at least {PROMPT_MIN} characters long")
        if len(cleaned_prompt) > PROMPT_MAX:
            raise ValueError(f"Prompt must be at most {PROMPT_MAX} characters long")
        cleaned_preview = preview_text.strip()
        if not cleaned_preview:
            raise ValueError("Preview text cannot be empty")
        if len(cleaned_preview) > PREVIEW_TEXT_MAX:
            raise ValueError(f"Preview text cannot exceed {PREVIEW_TEXT_MAX} characters")
        if self.provider != "minimax":
            raise ValueError(f"Voice design provider '{self.provider}' is not supported yet")

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
        endpoint = self._resolve_endpoint("voice_design")
        payload: dict[str, Any] = {
            "prompt": cleaned_prompt,
            "preview_text": cleaned_preview,
            "voice_id": final_voice_id,
            "aigc_watermark": bool(aigc_watermark),
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        _raise_for_minimax_error(data, "MiniMax voice_design returned an error")
        audio_hex = _extract_trial_audio_hex(data)
        if not audio_hex:
            raise RuntimeError("MiniMax voice_design returned no trial audio")

        returned_voice_id = data.get("voice_id") if isinstance(data.get("voice_id"), str) else None
        effective_voice_id = (returned_voice_id or "").strip() or final_voice_id

        return DesignedVoiceResult(
            voice_id=effective_voice_id,
            model=self.model,
            provider=self.provider,
            trial_audio=bytes.fromhex(audio_hex),
            mime_type="audio/mpeg",
            trace_id=data.get("trace_id") if isinstance(data.get("trace_id"), str) else None,
        )

    def _require_api_key(self) -> str:
        key = (self._capability.api_key or "").strip()
        if not key:
            raise ValueError("Voice design capability is missing api_key")
        return key

    def _resolve_endpoint(self, path: str) -> str:
        base = self.api_base.rstrip("/")
        suffix = path.lstrip("/")
        return f"{base}/{suffix}"

    @staticmethod
    def _generate_voice_id() -> str:
        return f"design_{uuid.uuid4().hex[:12]}"


def _raise_for_minimax_error(data: dict[str, Any], fallback: str) -> None:
    base_resp = data.get("base_resp") or {}
    status_code = base_resp.get("status_code")
    if status_code not in (None, 0):
        raise RuntimeError(base_resp.get("status_msg") or fallback)


def _extract_trial_audio_hex(data: dict[str, Any]) -> str | None:
    # MiniMax returns the trial audio either at the top level or nested under
    # data → trial_audio. Check both to stay tolerant of small format changes.
    trial = data.get("trial_audio")
    if isinstance(trial, str) and trial.strip():
        return trial
    payload = data.get("data")
    if isinstance(payload, dict):
        nested = payload.get("trial_audio")
        if isinstance(nested, str) and nested.strip():
            return nested
    return None
