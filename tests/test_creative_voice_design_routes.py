from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tokenmind.config.loader import save_config
from tokenmind.config.schema import Config
from tokenmind.creative.voice_design import DesignedVoiceResult
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


def _configure_design(temp_config_path: Path) -> None:
    config = Config()
    config.creative.voice_design.enabled = True
    config.creative.voice_design.provider = "minimax"
    config.creative.voice_design.api_key = "minimax-key"
    config.creative.voice_design.model = "speech-2.8-hd"
    save_config(config, temp_config_path)


def test_design_route_creates_record_and_archives_audio(
    tmp_path: Path,
    temp_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_design(temp_config_path)
    service = make_service(tmp_path)

    async def fake_design(self, **kwargs: Any) -> DesignedVoiceResult:
        assert kwargs["prompt"].startswith("低沉")
        return DesignedVoiceResult(
            voice_id="design_fromroute01",
            model="speech-2.8-hd",
            provider="minimax",
            trial_audio=b"fake-mp3-bytes",
            mime_type="audio/mpeg",
            trace_id="trace-design-route-1",
        )

    monkeypatch.setattr(
        "tokenmind.creative.voice_design.VoiceDesignService.design_voice",
        fake_design,
    )

    client = build_client(service)
    response = client.post(
        "/api/creative/voice/design/create",
        json={
            "prompt": "低沉男声，带点磁性，语速从容",
            "preview_text": "你好，TokenMind",
            "display_name": "主持风格",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["voice_id"] == "design_fromroute01"
    assert body["source"] == "design"
    assert body["display_name"] == "主持风格"
    assert body["trace_id"] == "trace-design-route-1"
    assert body["demo_attachment_id"]

    # Records appear in the list endpoint filterable by source.
    all_voices = client.get("/api/creative/voice/clone/list").json()["items"]
    assert any(item["voice_id"] == "design_fromroute01" for item in all_voices)
    designed = client.get(
        "/api/creative/voice/clone/list", params={"source": "design"}
    ).json()["items"]
    assert [item["voice_id"] for item in designed] == ["design_fromroute01"]
    cloned = client.get(
        "/api/creative/voice/clone/list", params={"source": "clone"}
    ).json()["items"]
    assert cloned == []


def test_design_route_returns_400_when_not_configured(
    tmp_path: Path,
    temp_config_path: Path,
) -> None:
    # No creative capability enabled.
    config = Config()
    save_config(config, temp_config_path)
    service = make_service(tmp_path)

    client = build_client(service)
    response = client.post(
        "/api/creative/voice/design/create",
        json={"prompt": "warm voice with a soft tone", "preview_text": "hello"},
    )
    assert response.status_code == 400
    assert "not configured" in response.json()["detail"].lower()


def test_design_route_rejects_short_prompt(
    tmp_path: Path,
    temp_config_path: Path,
) -> None:
    _configure_design(temp_config_path)
    service = make_service(tmp_path)

    client = build_client(service)
    response = client.post(
        "/api/creative/voice/design/create",
        json={"prompt": "hi", "preview_text": "hello"},
    )
    assert response.status_code == 422  # Pydantic length validation
