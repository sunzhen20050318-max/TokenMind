from __future__ import annotations

from typing import Any

import pytest

from tokenmind.config.schema import Config
from tokenmind.creative.tts import TtsService


def _tts_capability(**overrides: Any):
    payload = {
        "creative": {
            "tts": {
                "enabled": True,
                "provider": "minimax",
                "apiKey": "minimax-key",
                "model": "speech-2.8-hd",
            }
        }
    }
    payload["creative"]["tts"].update(overrides)
    return Config.model_validate(payload).creative.tts


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.mark.asyncio
async def test_synthesize_posts_expected_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def post(self, url: str, *, headers, json) -> _FakeResponse:
            seen["url"] = url
            seen["headers"] = headers
            seen["json"] = json
            return _FakeResponse(
                {
                    "base_resp": {"status_code": 0, "status_msg": "success"},
                    "data": {"audio": "66616b652d6d7033"},
                    "extra_info": {"usage_characters": 128},
                    "trace_id": "trace-tts-1",
                }
            )

    monkeypatch.setattr("tokenmind.creative.tts.httpx.AsyncClient", _FakeAsyncClient)
    service = TtsService(_tts_capability())

    result = await service.synthesize(
        text="你好，TokenMind",
        voice_id="clone_friendlyBot",
        speed=1.2,
        emotion="happy",
    )

    assert result.data == b"fake-mp3"
    assert result.mime_type == "audio/mpeg"
    assert result.voice_id == "clone_friendlyBot"
    assert result.model == "speech-2.8-hd"
    assert result.usage_characters == 128
    assert result.trace_id == "trace-tts-1"

    assert seen["url"] == "https://api.minimaxi.com/v1/t2a_v2"
    assert seen["headers"]["Authorization"] == "Bearer minimax-key"
    payload = seen["json"]
    assert payload["text"] == "你好，TokenMind"
    assert payload["model"] == "speech-2.8-hd"
    assert payload["voice_setting"]["voice_id"] == "clone_friendlyBot"
    assert payload["voice_setting"]["speed"] == 1.2
    assert payload["voice_setting"]["emotion"] == "happy"
    assert payload["output_format"] == "hex"
    assert payload["audio_setting"]["format"] == "mp3"


@pytest.mark.asyncio
async def test_synthesize_rejects_empty_text() -> None:
    service = TtsService(_tts_capability())
    with pytest.raises(ValueError, match="Text cannot be empty"):
        await service.synthesize(text="", voice_id="clone_abcdefgh")


@pytest.mark.asyncio
async def test_synthesize_rejects_missing_voice_id() -> None:
    service = TtsService(_tts_capability())
    with pytest.raises(ValueError, match="voice_id is required"):
        await service.synthesize(text="hi", voice_id="")


@pytest.mark.asyncio
async def test_synthesize_rejects_oversized_text() -> None:
    service = TtsService(_tts_capability())
    with pytest.raises(ValueError, match="exceeds"):
        await service.synthesize(text="x" * 10001, voice_id="clone_abcdefgh")


@pytest.mark.asyncio
async def test_synthesize_rejects_unsupported_emotion() -> None:
    service = TtsService(_tts_capability())
    with pytest.raises(ValueError, match="Unsupported emotion"):
        await service.synthesize(
            text="hi",
            voice_id="clone_abcdefgh",
            emotion="giggly",
        )


@pytest.mark.asyncio
async def test_synthesize_propagates_minimax_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def post(self, url: str, *, headers, json) -> _FakeResponse:
            return _FakeResponse(
                {"base_resp": {"status_code": 2013, "status_msg": "invalid voice"}}
            )

    monkeypatch.setattr("tokenmind.creative.tts.httpx.AsyncClient", _FakeAsyncClient)
    service = TtsService(_tts_capability())
    with pytest.raises(RuntimeError, match="invalid voice"):
        await service.synthesize(text="hi", voice_id="clone_unknown1")


def test_is_configured_requires_enabled_provider_and_api_key() -> None:
    disabled = _tts_capability(enabled=False)
    assert TtsService.is_configured(disabled) is False

    no_key = _tts_capability(apiKey="")
    assert TtsService.is_configured(no_key) is False

    ok = _tts_capability()
    assert TtsService.is_configured(ok) is True


@pytest.mark.asyncio
async def test_synthesize_clamps_speed_and_pitch(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def post(self, url: str, *, headers, json) -> _FakeResponse:
            captured["json"] = json
            return _FakeResponse(
                {
                    "base_resp": {"status_code": 0},
                    "data": {"audio": "aa"},
                }
            )

    monkeypatch.setattr("tokenmind.creative.tts.httpx.AsyncClient", _FakeAsyncClient)
    service = TtsService(_tts_capability())
    await service.synthesize(
        text="hello",
        voice_id="clone_abcdefgh",
        speed=10.0,  # will clamp to 2.0
        pitch=99,  # will clamp to 12
        volume=0.001,  # will clamp to 0.01
    )

    voice_setting = captured["json"]["voice_setting"]
    assert voice_setting["speed"] == 2.0
    assert voice_setting["pitch"] == 12
    assert voice_setting["vol"] == 0.01
