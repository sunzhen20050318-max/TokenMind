from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tokenmind.config.loader import save_config
from tokenmind.config.schema import Config
from tokenmind.creative.tts import GeneratedSpeechResult
from tokenmind.creative.voice_clone_store import VoiceCloneRecord
from tokenmind.server.app import ChatService
from tokenmind.server.routes import creative as creative_routes
from tokenmind.session.manager import SessionManager


@pytest.fixture
def temp_config_path(tmp_path: Path):
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


def build_client(service: ChatService) -> TestClient:
    app = FastAPI()
    app.include_router(creative_routes.router)
    app.dependency_overrides[creative_routes.get_chat_service] = lambda: service
    return TestClient(app)


def _configure_tts(temp_config_path: Path) -> None:
    config = Config()
    config.creative.tts.enabled = True
    config.creative.tts.provider = "minimax"
    config.creative.tts.api_key = "minimax-key"
    config.creative.tts.model = "speech-2.8-hd"
    save_config(config, temp_config_path)


def test_synthesize_route_returns_attachment(
    tmp_path: Path,
    temp_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_tts(temp_config_path)
    service = make_service(tmp_path)

    async def fake_synth(self, **kwargs: Any) -> GeneratedSpeechResult:
        assert kwargs["text"] == "你好"
        assert kwargs["voice_id"] == "clone_abcdefgh"
        return GeneratedSpeechResult(
            filename="tts-abc123.mp3",
            mime_type="audio/mpeg",
            data=b"fake-mp3-bytes",
            model="speech-2.8-hd",
            provider="minimax",
            voice_id=kwargs["voice_id"],
            usage_characters=2,
            trace_id="trace-tts-1",
        )

    monkeypatch.setattr("tokenmind.creative.tts.TtsService.synthesize", fake_synth)

    client = build_client(service)
    response = client.post(
        "/api/creative/voice/tts/synthesize",
        json={
            "text": "你好",
            "voice_id": "clone_abcdefgh",
            "speed": 1.0,
            "volume": 1.0,
            "pitch": 0,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["voice_id"] == "clone_abcdefgh"
    assert body["usage_characters"] == 2
    assert body["trace_id"] == "trace-tts-1"
    assert body["attachment_id"]
    assert body["attachment"]["name"] == "tts-abc123.mp3"


def test_synthesize_route_returns_400_when_not_configured(
    tmp_path: Path,
    temp_config_path: Path,
) -> None:
    # Neither tts nor voice_clone capability is enabled.
    config = Config()
    save_config(config, temp_config_path)
    service = make_service(tmp_path)

    client = build_client(service)
    response = client.post(
        "/api/creative/voice/tts/synthesize",
        json={"text": "hi", "voice_id": "clone_abcdefgh"},
    )
    assert response.status_code == 400
    assert "not configured" in response.json()["detail"].lower()


def test_list_voices_returns_cloned_and_system(
    tmp_path: Path,
    temp_config_path: Path,
) -> None:
    _configure_tts(temp_config_path)
    service = make_service(tmp_path)
    service.voice_clones.upsert(
        VoiceCloneRecord(
            voice_id="clone_fromlist1",
            model="speech-2.8-hd",
            provider="minimax",
            created_at="2026-04-24T09:00:00Z",
        )
    )

    client = build_client(service)
    response = client.get("/api/creative/voice/tts/voices")
    assert response.status_code == 200
    body = response.json()
    assert any(item["voice_id"] == "clone_fromlist1" for item in body["cloned"])
    assert len(body["system"]) > 0
    # System voices should have a label and gender set.
    sample = body["system"][0]
    assert sample["label"]
    assert sample["gender"] in {"male", "female", "neutral"}


def test_synthesize_route_falls_back_to_voice_clone_capability(
    tmp_path: Path,
    temp_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Only voice_clone is configured, tts is not — should still work.
    config = Config()
    config.creative.voice_clone.enabled = True
    config.creative.voice_clone.provider = "minimax"
    config.creative.voice_clone.api_key = "minimax-key"
    config.creative.voice_clone.model = "speech-2.8-hd"
    save_config(config, temp_config_path)
    service = make_service(tmp_path)

    async def fake_synth(self, **kwargs: Any) -> GeneratedSpeechResult:
        return GeneratedSpeechResult(
            filename="tts-fall.mp3",
            mime_type="audio/mpeg",
            data=b"x",
            model="speech-2.8-hd",
            provider="minimax",
            voice_id=kwargs["voice_id"],
            usage_characters=1,
        )

    monkeypatch.setattr("tokenmind.creative.tts.TtsService.synthesize", fake_synth)

    client = build_client(service)
    response = client.post(
        "/api/creative/voice/tts/synthesize",
        json={"text": "a", "voice_id": "clone_anythingx"},
    )
    assert response.status_code == 200
