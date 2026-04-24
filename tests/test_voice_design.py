from __future__ import annotations

from typing import Any

import pytest

from tokenmind.config.schema import Config
from tokenmind.creative.voice_design import VoiceDesignService


def _capability(**overrides: Any):
    payload = {
        "creative": {
            "voice_design": {
                "enabled": True,
                "provider": "minimax",
                "apiKey": "minimax-key",
                "model": "speech-2.8-hd",
            }
        }
    }
    payload["creative"]["voice_design"].update(overrides)
    return Config.model_validate(payload).creative.voice_design


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.mark.asyncio
async def test_design_voice_sends_expected_payload(monkeypatch: pytest.MonkeyPatch) -> None:
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
                    "voice_id": "design_provided01",
                    "trial_audio": "66616b652d6d7033",
                    "trace_id": "trace-design-1",
                }
            )

    monkeypatch.setattr(
        "tokenmind.creative.voice_design.httpx.AsyncClient", _FakeAsyncClient
    )
    service = VoiceDesignService(_capability())

    result = await service.design_voice(
        prompt="悬疑风格的男声，低沉有磁性，节奏变化多",
        preview_text="你好，TokenMind",
        voice_id="design_provided01",
    )

    assert result.voice_id == "design_provided01"
    assert result.model == "speech-2.8-hd"
    assert result.trial_audio == b"fake-mp3"
    assert result.mime_type == "audio/mpeg"
    assert result.trace_id == "trace-design-1"

    assert seen["url"] == "https://api.minimaxi.com/v1/voice_design"
    assert seen["headers"]["Authorization"] == "Bearer minimax-key"
    payload = seen["json"]
    assert payload["prompt"].startswith("悬疑风格")
    assert payload["preview_text"] == "你好，TokenMind"
    assert payload["voice_id"] == "design_provided01"
    assert payload["aigc_watermark"] is False


@pytest.mark.asyncio
async def test_design_voice_autogenerates_id_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def post(self, url: str, *, headers, json) -> _FakeResponse:
            assert json["voice_id"].startswith("design_")
            return _FakeResponse(
                {
                    "base_resp": {"status_code": 0},
                    "voice_id": json["voice_id"],
                    "trial_audio": "aa",
                }
            )

    monkeypatch.setattr(
        "tokenmind.creative.voice_design.httpx.AsyncClient", _FakeAsyncClient
    )
    service = VoiceDesignService(_capability())
    result = await service.design_voice(
        prompt="A friendly cheerful voice",
        preview_text="Hello",
    )
    assert result.voice_id.startswith("design_")


@pytest.mark.asyncio
async def test_design_voice_rejects_too_short_prompt() -> None:
    service = VoiceDesignService(_capability())
    with pytest.raises(ValueError, match="at least 5"):
        await service.design_voice(prompt="hi", preview_text="hello world")


@pytest.mark.asyncio
async def test_design_voice_rejects_too_long_preview_text() -> None:
    service = VoiceDesignService(_capability())
    with pytest.raises(ValueError, match="500"):
        await service.design_voice(
            prompt="friendly warm voice",
            preview_text="x" * 501,
        )


@pytest.mark.asyncio
async def test_design_voice_rejects_empty_preview_text() -> None:
    service = VoiceDesignService(_capability())
    with pytest.raises(ValueError, match="Preview text"):
        await service.design_voice(prompt="friendly warm voice", preview_text="   ")


@pytest.mark.asyncio
async def test_design_voice_rejects_invalid_voice_id() -> None:
    service = VoiceDesignService(_capability())
    with pytest.raises(ValueError, match="voice_id"):
        await service.design_voice(
            prompt="friendly warm voice",
            preview_text="hi",
            voice_id="1short",
        )


@pytest.mark.asyncio
async def test_design_voice_propagates_minimax_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def post(self, url: str, *, headers, json) -> _FakeResponse:
            return _FakeResponse(
                {"base_resp": {"status_code": 1001, "status_msg": "balance too low"}}
            )

    monkeypatch.setattr(
        "tokenmind.creative.voice_design.httpx.AsyncClient", _FakeAsyncClient
    )
    service = VoiceDesignService(_capability())
    with pytest.raises(RuntimeError, match="balance too low"):
        await service.design_voice(
            prompt="warm friendly voice",
            preview_text="hi",
        )
