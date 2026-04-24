from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tokenmind.config.loader import save_config
from tokenmind.config.schema import Config
from tokenmind.creative.voice_clone import ClonedVoiceResult, UploadedCloneAudio
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


def _configure_voice_clone(temp_config_path: Path) -> None:
    config = Config()
    config.creative.voice_clone.enabled = True
    config.creative.voice_clone.provider = "minimax"
    config.creative.voice_clone.api_key = "minimax-key"
    config.creative.voice_clone.model = "speech-2.8-hd"
    save_config(config, temp_config_path)


def test_upload_voice_clone_audio_route_passes_bytes_through(
    tmp_path: Path,
    temp_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_voice_clone(temp_config_path)
    service = make_service(tmp_path)

    captured: dict[str, Any] = {}

    async def fake_upload(self, **kwargs: Any) -> UploadedCloneAudio:
        captured.update(kwargs)
        return UploadedCloneAudio(
            file_id=42,
            filename=kwargs["filename"],
            bytes=len(kwargs["audio_bytes"]),
            created_at=1_700_000_000,
        )

    monkeypatch.setattr(
        "tokenmind.creative.voice_clone.VoiceCloneService.upload_audio",
        fake_upload,
    )

    client = build_client(service)
    response = client.post(
        "/api/creative/voice/clone/upload",
        files={"file": ("voice.mp3", b"raw-audio", "audio/mpeg")},
        data={"purpose": "voice_clone"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["file_id"] == 42
    assert body["filename"] == "voice.mp3"
    assert body["bytes"] == len(b"raw-audio")
    assert captured["audio_bytes"] == b"raw-audio"
    assert captured["filename"] == "voice.mp3"
    assert captured["content_type"] == "audio/mpeg"


def test_upload_voice_clone_audio_route_returns_400_when_not_configured(
    tmp_path: Path,
    temp_config_path: Path,
) -> None:
    # Config written but capability not enabled
    config = Config()
    save_config(config, temp_config_path)
    service = make_service(tmp_path)

    client = build_client(service)
    response = client.post(
        "/api/creative/voice/clone/upload",
        files={"file": ("voice.mp3", b"raw-audio", "audio/mpeg")},
    )
    assert response.status_code == 400
    assert "not configured" in response.json()["detail"].lower()


def test_create_voice_clone_route_returns_voice_id_and_demo(
    tmp_path: Path,
    temp_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_voice_clone(temp_config_path)
    service = make_service(tmp_path)

    async def fake_clone(self, **kwargs: Any) -> ClonedVoiceResult:
        assert kwargs["file_id"] == 42
        assert kwargs["voice_id"] == "clone_friendlyBot"
        assert kwargs["preview_text"] == "hello TokenMind"
        return ClonedVoiceResult(
            voice_id="clone_friendlyBot",
            model="speech-2.8-hd",
            provider="minimax",
            demo_audio_url="https://cdn.example.com/demo.mp3",
            input_sensitive=False,
            input_sensitive_type=None,
            trace_id="trace-route-1",
        )

    async def fake_download(url: str) -> tuple[bytes, str]:
        assert url == "https://cdn.example.com/demo.mp3"
        return b"fake-mp3", "audio/mpeg"

    monkeypatch.setattr(
        "tokenmind.creative.voice_clone.VoiceCloneService.clone_voice",
        fake_clone,
    )
    monkeypatch.setattr(
        "tokenmind.creative.voice_clone.VoiceCloneService.download_demo_audio",
        staticmethod(fake_download),
    )

    client = build_client(service)
    response = client.post(
        "/api/creative/voice/clone/create",
        json={
            "file_id": 42,
            "voice_id": "clone_friendlyBot",
            "preview_text": "hello TokenMind",
            "need_noise_reduction": False,
            "need_volume_normalization": False,
            "source_filename": "sample.mp3",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["voice_id"] == "clone_friendlyBot"
    assert body["demo_audio_url"] == "https://cdn.example.com/demo.mp3"
    assert body["trace_id"] == "trace-route-1"
    assert body["source_filename"] == "sample.mp3"
    assert body["demo_attachment_id"]  # attachment was persisted locally

    # List endpoint should now return the same record.
    list_response = client.get("/api/creative/voice/clone/list")
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["voice_id"] == "clone_friendlyBot"
    assert items[0]["demo_attachment_id"] == body["demo_attachment_id"]


def test_keep_alive_route_updates_timestamp(
    tmp_path: Path,
    temp_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_voice_clone(temp_config_path)
    service = make_service(tmp_path)
    # Seed a record directly in the store.
    from tokenmind.creative.voice_clone_store import VoiceCloneRecord

    service.voice_clones.upsert(
        VoiceCloneRecord(
            voice_id="clone_keepalive",
            model="speech-2.8-hd",
            provider="minimax",
            created_at="2026-04-24T09:00:00Z",
        )
    )

    async def fake_keep_alive(self, *, voice_id: str, text: str = "你好") -> None:
        assert voice_id == "clone_keepalive"

    monkeypatch.setattr(
        "tokenmind.creative.voice_clone.VoiceCloneService.keep_alive_voice",
        fake_keep_alive,
    )

    client = build_client(service)
    response = client.post("/api/creative/voice/clone/clone_keepalive/keep-alive")
    assert response.status_code == 200
    body = response.json()
    assert body["voice_id"] == "clone_keepalive"
    assert body["last_kept_alive_at"]  # timestamp is set


def test_delete_route_removes_record(
    tmp_path: Path,
    temp_config_path: Path,
) -> None:
    _configure_voice_clone(temp_config_path)
    service = make_service(tmp_path)
    from tokenmind.creative.voice_clone_store import VoiceCloneRecord

    service.voice_clones.upsert(
        VoiceCloneRecord(
            voice_id="clone_deletable",
            model="speech-2.8-hd",
            provider="minimax",
            created_at="2026-04-24T09:00:00Z",
        )
    )

    client = build_client(service)
    response = client.delete("/api/creative/voice/clone/clone_deletable")
    assert response.status_code == 200
    assert response.json()["voice_id"] == "clone_deletable"
    assert service.voice_clones.get("clone_deletable") is None

    # Deleting again yields 404.
    missing = client.delete("/api/creative/voice/clone/clone_deletable")
    assert missing.status_code == 404


def test_create_voice_clone_route_rejects_invalid_file_id(
    tmp_path: Path,
    temp_config_path: Path,
) -> None:
    _configure_voice_clone(temp_config_path)
    service = make_service(tmp_path)

    client = build_client(service)
    response = client.post(
        "/api/creative/voice/clone/create",
        json={"file_id": 0},
    )
    assert response.status_code == 422
