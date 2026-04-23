from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tokenmind.config.loader import save_config
from tokenmind.config.schema import Config
from tokenmind.creative.music_generation import GeneratedMusicResult
from tokenmind.server.app import ChatService
from tokenmind.server.routes import chat as chat_routes
from tokenmind.server.routes import creative as creative_routes
from tokenmind.session.manager import SessionManager


@pytest.fixture
def temp_config_path(tmp_path):
    from tokenmind.config.loader import get_config_path, set_config_path

    previous = get_config_path()
    path = tmp_path / "config.json"
    set_config_path(path)
    try:
        yield path
    finally:
        set_config_path(previous)


def make_service(tmp_path: Path) -> ChatService:
    session_manager = SessionManager(tmp_path)
    return ChatService(
        bus=SimpleNamespace(),
        agent_loop=SimpleNamespace(),
        session_manager=session_manager,
    )


def build_creative_test_client(service: ChatService) -> TestClient:
    app = FastAPI()
    app.include_router(creative_routes.router)
    app.include_router(chat_routes.router)
    app.dependency_overrides[creative_routes.get_chat_service] = lambda: service
    app.dependency_overrides[chat_routes.get_chat_service] = lambda: service
    return TestClient(app)


def test_generate_music_route_returns_playable_attachment(
    tmp_path: Path,
    temp_config_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Config()
    config.creative.music.enabled = True
    config.creative.music.provider = "minimax"
    config.creative.music.api_key = "minimax-key"
    config.creative.music.model = "music-2.6"
    save_config(config, temp_config_path)
    service = make_service(tmp_path)

    async def fake_generate(self, **kwargs):
        assert kwargs["prompt"] == "City pop intro"
        assert kwargs["lyrics"] == "[Verse]\nTokenMind"
        assert kwargs["lyrics_optimizer"] is False
        assert kwargs["is_instrumental"] is False
        assert kwargs["reference_audio_base64"] is None
        return GeneratedMusicResult(
            filename="generated-music-test.mp3",
            mime_type="audio/mpeg",
            data=b"mp3-data",
            model="music-2.6",
            provider="minimax",
            duration_ms=99000,
            trace_id="trace-route",
        )

    monkeypatch.setattr("tokenmind.creative.music_generation.MusicGenerationService.generate", fake_generate)
    client = build_creative_test_client(service)

    response = client.post(
        "/api/creative/music/generate",
        json={
            "prompt": "City pop intro",
            "lyrics": "[Verse]\nTokenMind",
            "lyrics_optimizer": False,
            "is_instrumental": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["attachment"]["id"].startswith("att_")
    assert payload["attachment"]["name"] == "generated-music-test.mp3"
    assert payload["attachment"]["category"] == "audio"
    assert payload["result"]["duration_ms"] == 99000
    assert payload["result"]["trace_id"] == "trace-route"

    audio = client.get(f"/api/chat/attachments/{payload['attachment']['id']}")
    assert audio.status_code == 200
    assert audio.content == b"mp3-data"


def test_generate_music_route_requires_music_cover_config_for_reference_audio(
    tmp_path: Path,
    temp_config_path,
) -> None:
    config = Config()
    config.creative.music.enabled = True
    config.creative.music.provider = "minimax"
    config.creative.music.api_key = "minimax-key"
    config.creative.music.model = "music-2.6"
    save_config(config, temp_config_path)
    service = make_service(tmp_path)
    client = build_creative_test_client(service)

    response = client.post(
        "/api/creative/music/generate",
        json={
            "prompt": "ambient score with reference audio",
            "lyrics": "[Verse]\nnone",
            "reference_audio_base64": "cmVmZXJlbmNl",
            "reference_audio_name": "demo.mp3",
        },
    )

    assert response.status_code == 400
    assert "cover generation is not configured" in response.json()["detail"]


def test_generate_music_route_returns_400_when_music_is_not_configured(
    tmp_path: Path,
    temp_config_path,
) -> None:
    save_config(Config(), temp_config_path)
    service = make_service(tmp_path)
    client = build_creative_test_client(service)

    response = client.post(
        "/api/creative/music/generate",
        json={
            "prompt": "ambient score",
            "lyrics": "[Verse]\nnone",
        },
    )

    assert response.status_code == 400
    assert "not configured" in response.json()["detail"]
