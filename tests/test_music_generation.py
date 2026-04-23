from __future__ import annotations

import base64

import pytest

from tokenmind.config.schema import Config
from tokenmind.creative.music_generation import MusicGenerationService


def _music_capability(**overrides):
    payload = {
        "creative": {
            "music": {
                "enabled": True,
                "provider": "minimax",
                "apiKey": "minimax-key",
                "model": "music-2.6",
            }
        }
    }
    payload["creative"]["music"].update(overrides)
    return Config.model_validate(payload).creative.music


@pytest.mark.asyncio
async def test_minimax_music_service_generates_song_from_prompt_and_lyrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "base_resp": {"status_code": 0, "status_msg": "success"},
                "data": {
                    "audio": "66616b652d6d7033",
                    "duration": 128000,
                },
                "trace_id": "trace-music-1",
            }

    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            seen["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
            seen["url"] = url
            seen["headers"] = headers
            seen["json"] = json
            return _FakeResponse()

    monkeypatch.setattr("tokenmind.creative.music_generation.httpx.AsyncClient", _FakeAsyncClient)
    service = MusicGenerationService(_music_capability())

    result = await service.generate(
        prompt="Bright electropop, 120 BPM, uplifting chorus",
        lyrics="[Verse]\nHello TokenMind\n[Chorus]\nWe build the future",
        lyrics_optimizer=False,
    )

    assert result.data == b"fake-mp3"
    assert result.mime_type == "audio/mpeg"
    assert result.model == "music-2.6"
    assert result.provider == "minimax"
    assert result.duration_ms == 128000
    assert result.trace_id == "trace-music-1"
    assert seen["url"] == "https://api.minimaxi.com/v1/music_generation"
    assert seen["headers"]["Authorization"] == "Bearer minimax-key"
    assert seen["json"] == {
        "model": "music-2.6",
        "prompt": "Bright electropop, 120 BPM, uplifting chorus",
        "lyrics": "[Verse]\nHello TokenMind\n[Chorus]\nWe build the future",
        "lyrics_optimizer": False,
        "output_format": "hex",
        "audio_setting": {
            "sample_rate": 44100,
            "bitrate": 256000,
            "format": "mp3",
        },
    }


@pytest.mark.asyncio
async def test_minimax_music_service_generates_instrumental_without_lyrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "base_resp": {"status_code": 0, "status_msg": "success"},
                "data": {"audio": "00ff"},
            }

    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            seen["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
            seen["json"] = json
            return _FakeResponse()

    monkeypatch.setattr("tokenmind.creative.music_generation.httpx.AsyncClient", _FakeAsyncClient)
    service = MusicGenerationService(_music_capability(apiBase="https://api.minimaxi.com/v1"))

    result = await service.generate(
        prompt="Cinematic ambient score for a rain-soaked city",
        is_instrumental=True,
    )

    assert result.data == b"\x00\xff"
    assert seen["json"]["is_instrumental"] is True
    assert "lyrics" not in seen["json"]
    assert "lyrics_optimizer" not in seen["json"]


@pytest.mark.asyncio
async def test_minimax_music_service_uses_cover_model_for_reference_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {"calls": []}

    class _FakeResponse:
        def __init__(self, payload: dict[str, object]):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            seen["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
            seen["calls"].append({"url": url, "headers": headers, "json": json})
            if url.endswith("/music_cover_preprocess"):
                return _FakeResponse(
                    {
                        "base_resp": {"status_code": 0, "status_msg": "success"},
                        "cover_feature_id": "cover-feature-1",
                        "formatted_lyrics": "[Verse]\nReference melody",
                    }
                )
            return _FakeResponse(
                {
                    "base_resp": {"status_code": 0, "status_msg": "success"},
                    "data": {"audio": "66616b652d636f766572"},
                }
            )

    monkeypatch.setattr("tokenmind.creative.music_generation.httpx.AsyncClient", _FakeAsyncClient)
    service = MusicGenerationService(_music_capability())
    reference = base64.b64encode(b"reference-audio").decode("ascii")

    result = await service.generate(
        prompt="Turn this into a clean Mandarin pop arrangement",
        reference_audio_base64=reference,
    )

    assert result.data == b"fake-cover"
    assert result.model == "music-cover"
    calls = seen["calls"]
    assert calls[0]["url"] == "https://api.minimaxi.com/v1/music_cover_preprocess"
    assert calls[0]["json"]["model"] == "music-cover"
    assert calls[0]["json"]["audio_base64"] == reference
    assert calls[1]["url"] == "https://api.minimaxi.com/v1/music_generation"
    assert calls[1]["json"]["model"] == "music-cover"
    assert calls[1]["json"]["cover_feature_id"] == "cover-feature-1"
    assert calls[1]["json"]["lyrics"] == "[Verse]\nReference melody"
    assert "lyrics_optimizer" not in calls[1]["json"]
    assert "is_instrumental" not in calls[1]["json"]


@pytest.mark.asyncio
async def test_music_service_requires_configured_enabled_capability() -> None:
    disabled = _music_capability(enabled=False)
    service = MusicGenerationService(disabled)

    with pytest.raises(ValueError, match="Music generation is not configured"):
        await service.generate(prompt="ambient", lyrics="words")


@pytest.mark.asyncio
async def test_music_service_requires_lyrics_or_auto_lyrics_for_song() -> None:
    service = MusicGenerationService(_music_capability())

    with pytest.raises(ValueError, match="Lyrics are required"):
        await service.generate(prompt="pop song")
