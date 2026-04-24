"""Text-to-speech helpers backed by MiniMax Speech 2.8 (`/v1/t2a_v2`).

The Token Plan subscription covers Speech 2.8 with a daily character quota, so
synthesizing with a cloned or system ``voice_id`` only consumes that quota.

Response ``usage_characters`` is returned alongside the audio so the UI can
show how many characters were charged for the call.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from tokenmind.config.schema import CreativeCapabilityConfig
from tokenmind.providers.registry import find_by_name

_DEFAULT_MINIMAX_API_BASE = "https://api.minimaxi.com/v1"
_DEFAULT_MODEL = "speech-2.8-hd"

TTS_TEXT_MAX = 10000

SUPPORTED_MODELS: tuple[str, ...] = (
    "speech-2.8-hd",
    "speech-2.8-turbo",
    "speech-2.6-hd",
    "speech-2.6-turbo",
    "speech-02-hd",
    "speech-02-turbo",
    "speech-01-hd",
    "speech-01-turbo",
)

SUPPORTED_EMOTIONS: tuple[str, ...] = (
    "happy",
    "sad",
    "angry",
    "fearful",
    "disgusted",
    "surprised",
    "calm",
    "fluent",
    "whisper",
)

_MODEL_UNSUPPORTED_EMOTIONS: dict[str, frozenset[str]] = {
    "speech-2.8-hd": frozenset({"whisper"}),
    "speech-2.8-turbo": frozenset({"whisper"}),
}


@dataclass(frozen=True)
class SystemVoice:
    """A built-in MiniMax voice that users can pick without cloning."""

    voice_id: str
    label: str
    gender: str  # "male" / "female" / "neutral"
    description: str


# A reasonable starter set of MiniMax preset voices. Users can paste any other
# system voice id by hand if they know one. The list is conservative on purpose.
SYSTEM_VOICES: tuple[SystemVoice, ...] = (
    SystemVoice("male-qn-qingse", "青涩青年", "male", "清爽年轻的男声"),
    SystemVoice("male-qn-jingying", "精英青年", "male", "沉稳干练的男声"),
    SystemVoice("male-qn-badao", "霸道总裁", "male", "强势有气场的男声"),
    SystemVoice("female-shaonv", "少女", "female", "甜美温柔的少女音"),
    SystemVoice("female-yujie", "御姐", "female", "知性有磁性的女声"),
    SystemVoice("female-chengshu", "成熟女性", "female", "稳重温和的女声"),
    SystemVoice("audiobook_male_1", "有声书 · 男声", "male", "适合朗读的低沉男声"),
    SystemVoice("audiobook_female_1", "有声书 · 女声", "female", "适合朗读的轻柔女声"),
    SystemVoice("presenter_male", "主持人 · 男", "male", "清晰稳健的主持风格"),
    SystemVoice("presenter_female", "主持人 · 女", "female", "亲切专业的主持风格"),
)


@dataclass(frozen=True)
class GeneratedSpeechResult:
    """One synthesis result returned by :class:`TtsService`."""

    filename: str
    mime_type: str
    data: bytes
    model: str
    provider: str
    voice_id: str
    usage_characters: int | None = None
    trace_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class TtsService:
    """Synthesize text into speech using MiniMax Speech 2.8."""

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
        """Return True when the TTS capability has enough data to be used."""
        if capability is None or not capability.enabled:
            return False
        provider = (capability.provider or "").strip()
        api_key = (capability.api_key or "").strip()
        return bool(provider and api_key)

    async def synthesize(
        self,
        *,
        text: str,
        voice_id: str,
        model: str | None = None,
        speed: float = 1.0,
        volume: float = 1.0,
        pitch: int = 0,
        emotion: str | None = None,
        sample_rate: int = 32000,
        bitrate: int = 128000,
        audio_format: str = "mp3",
    ) -> GeneratedSpeechResult:
        """Call MiniMax /v1/t2a_v2 and return the generated audio."""
        if not self.is_configured(self._capability):
            raise ValueError("TTS is not configured or enabled")
        cleaned_text = text.strip()
        if not cleaned_text:
            raise ValueError("Text cannot be empty")
        if len(cleaned_text) > TTS_TEXT_MAX:
            raise ValueError(f"Text exceeds the {TTS_TEXT_MAX}-character limit")
        cleaned_voice_id = voice_id.strip()
        if not cleaned_voice_id:
            raise ValueError("voice_id is required")
        if self.provider != "minimax":
            raise ValueError(f"TTS provider '{self.provider}' is not supported yet")

        requested_model = (model or self.model).strip() or _DEFAULT_MODEL
        normalized_emotion = (emotion or "").strip().lower()
        if normalized_emotion and normalized_emotion not in SUPPORTED_EMOTIONS:
            raise ValueError(f"Unsupported emotion: {emotion}")
        if normalized_emotion and not _is_emotion_supported_by_model(
            requested_model, normalized_emotion
        ):
            raise ValueError(
                f"Model {requested_model} does not support emotion: {normalized_emotion}"
            )

        voice_setting: dict[str, Any] = {
            "voice_id": cleaned_voice_id,
            "speed": max(0.5, min(2.0, float(speed))),
            "vol": max(0.01, min(10.0, float(volume))),
            "pitch": max(-12, min(12, int(pitch))),
        }
        if normalized_emotion:
            voice_setting["emotion"] = normalized_emotion

        payload: dict[str, Any] = {
            "model": requested_model,
            "text": cleaned_text,
            "output_format": "hex",
            "voice_setting": voice_setting,
            "audio_setting": {
                "sample_rate": sample_rate,
                "bitrate": bitrate,
                "format": audio_format,
            },
        }
        headers = {
            "Authorization": f"Bearer {self._require_api_key()}",
            "Content-Type": "application/json",
        }
        headers.update(self.extra_headers)
        endpoint = self._resolve_endpoint("t2a_v2")

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        _raise_for_minimax_error(data, "MiniMax TTS returned an error")
        audio_hex = _extract_audio_hex(data)
        if not audio_hex:
            raise RuntimeError("MiniMax TTS returned no audio")

        mime_type = "audio/mpeg" if audio_format.lower() == "mp3" else f"audio/{audio_format.lower()}"
        extra_info = data.get("extra_info") if isinstance(data.get("extra_info"), dict) else {}
        usage = _extract_usage_characters(data, extra_info)

        return GeneratedSpeechResult(
            filename=f"tts-{uuid.uuid4().hex[:8]}.{audio_format.lower()}",
            mime_type=mime_type,
            data=bytes.fromhex(audio_hex),
            model=requested_model,
            provider=self.provider,
            voice_id=cleaned_voice_id,
            usage_characters=usage,
            trace_id=data.get("trace_id"),
            extra=extra_info,
        )

    def _require_api_key(self) -> str:
        key = (self._capability.api_key or "").strip()
        if not key:
            raise ValueError("TTS capability is missing api_key")
        return key

    def _resolve_endpoint(self, path: str) -> str:
        base = self.api_base.rstrip("/")
        suffix = path.lstrip("/")
        return f"{base}/{suffix}"


def _raise_for_minimax_error(data: dict[str, Any], fallback: str) -> None:
    base_resp = data.get("base_resp") or {}
    status_code = base_resp.get("status_code")
    if status_code not in (None, 0):
        raise RuntimeError(base_resp.get("status_msg") or fallback)


def _is_emotion_supported_by_model(model: str, emotion: str) -> bool:
    normalized_model = (model or "").strip().lower()
    normalized_emotion = (emotion or "").strip().lower()
    if not normalized_emotion:
        return True
    unsupported = _MODEL_UNSUPPORTED_EMOTIONS.get(normalized_model, frozenset())
    return normalized_emotion not in unsupported


def _extract_audio_hex(data: dict[str, Any]) -> str | None:
    payload = data.get("data")
    if isinstance(payload, dict):
        audio = payload.get("audio")
        if isinstance(audio, str):
            return audio
    audio = data.get("audio")
    return audio if isinstance(audio, str) else None


def _extract_usage_characters(
    data: dict[str, Any], extra_info: dict[str, Any]
) -> int | None:
    candidates = (
        extra_info.get("usage_characters"),
        extra_info.get("character_count"),
        data.get("usage_characters"),
    )
    for candidate in candidates:
        if isinstance(candidate, int):
            return candidate
        if isinstance(candidate, str) and candidate.isdigit():
            return int(candidate)
    return None
