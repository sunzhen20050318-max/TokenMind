from __future__ import annotations

from typing import Any

import pytest

from tokenmind.config.schema import Config
from tokenmind.creative.voice_clone import VoiceCloneService


def _voice_clone_capability(**overrides: Any):
    payload = {
        "creative": {
            "voice_clone": {
                "enabled": True,
                "provider": "minimax",
                "apiKey": "minimax-key",
                "model": "speech-2.8-hd",
            }
        }
    }
    payload["creative"]["voice_clone"].update(overrides)
    return Config.model_validate(payload).creative.voice_clone


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.mark.asyncio
async def test_upload_audio_sends_multipart_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            seen["client_kwargs"] = kwargs

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            data: dict[str, Any],
            files: dict[str, Any],
        ) -> _FakeResponse:
            seen["url"] = url
            seen["headers"] = headers
            seen["data"] = data
            seen["files"] = files
            return _FakeResponse(
                {
                    "file": {
                        "file_id": 12345,
                        "filename": "sample.mp3",
                        "bytes": 1024,
                        "created_at": 1_700_000_000,
                    },
                    "base_resp": {"status_code": 0, "status_msg": "success"},
                }
            )

    monkeypatch.setattr("tokenmind.creative.voice_clone.httpx.AsyncClient", _FakeAsyncClient)
    service = VoiceCloneService(_voice_clone_capability())

    uploaded = await service.upload_audio(
        audio_bytes=b"audio-bytes",
        filename="my-voice.mp3",
        content_type="audio/mpeg",
    )

    assert uploaded.file_id == 12345
    assert uploaded.filename == "sample.mp3"
    assert uploaded.bytes == 1024
    assert seen["url"] == "https://api.minimaxi.com/v1/files/upload"
    assert seen["headers"]["Authorization"] == "Bearer minimax-key"
    assert seen["data"] == {"purpose": "voice_clone"}
    filename_in_upload, bytes_in_upload, mime = seen["files"]["file"]
    assert filename_in_upload == "my-voice.mp3"
    assert bytes_in_upload == b"audio-bytes"
    assert mime == "audio/mpeg"


@pytest.mark.asyncio
async def test_upload_audio_rejects_empty_file() -> None:
    service = VoiceCloneService(_voice_clone_capability())
    with pytest.raises(ValueError, match="Audio file is empty"):
        await service.upload_audio(audio_bytes=b"", filename="empty.mp3", content_type=None)


@pytest.mark.asyncio
async def test_upload_audio_rejects_unsupported_provider() -> None:
    service = VoiceCloneService(
        _voice_clone_capability(provider="openai")  # non-minimax provider
    )
    with pytest.raises(ValueError, match="not supported yet"):
        await service.upload_audio(
            audio_bytes=b"x", filename="x.mp3", content_type="audio/mpeg"
        )


@pytest.mark.asyncio
async def test_clone_voice_uses_custom_id_and_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            seen["client_kwargs"] = kwargs

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
        ) -> _FakeResponse:
            seen["url"] = url
            seen["headers"] = headers
            seen["json"] = json
            return _FakeResponse(
                {
                    "base_resp": {"status_code": 0, "status_msg": "success"},
                    "demo_audio": "https://cdn.example.com/demo.mp3",
                    "input_sensitive": False,
                    "trace_id": "trace-clone-1",
                }
            )

    monkeypatch.setattr("tokenmind.creative.voice_clone.httpx.AsyncClient", _FakeAsyncClient)
    service = VoiceCloneService(_voice_clone_capability())

    result = await service.clone_voice(
        file_id=12345,
        voice_id="clone_testVoice01",
        preview_text="Hello TokenMind",
        need_noise_reduction=True,
    )

    assert result.voice_id == "clone_testVoice01"
    assert result.model == "speech-2.8-hd"
    assert result.demo_audio_url == "https://cdn.example.com/demo.mp3"
    assert result.trace_id == "trace-clone-1"
    assert seen["url"] == "https://api.minimaxi.com/v1/voice_clone"
    assert seen["json"]["file_id"] == 12345
    assert seen["json"]["voice_id"] == "clone_testVoice01"
    assert seen["json"]["text"] == "Hello TokenMind"
    assert seen["json"]["model"] == "speech-2.8-hd"
    assert seen["json"]["need_noise_reduction"] is True
    assert seen["json"]["need_volume_normalization"] is False


@pytest.mark.asyncio
async def test_clone_voice_auto_generates_id_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
            return _FakeResponse({"base_resp": {"status_code": 0}})

    monkeypatch.setattr("tokenmind.creative.voice_clone.httpx.AsyncClient", _FakeAsyncClient)
    service = VoiceCloneService(_voice_clone_capability())

    result = await service.clone_voice(file_id=99, voice_id=None)

    assert result.voice_id.startswith("clone_")
    assert len(result.voice_id) >= 8
    assert captured["json"]["voice_id"] == result.voice_id
    # No preview text -> no `text`/`model` fields should be set
    assert "text" not in captured["json"]
    assert "model" not in captured["json"]


@pytest.mark.asyncio
async def test_clone_voice_rejects_invalid_voice_id() -> None:
    service = VoiceCloneService(_voice_clone_capability())
    with pytest.raises(ValueError, match="voice_id"):
        await service.clone_voice(file_id=1, voice_id="1short")  # starts with digit, too short


@pytest.mark.asyncio
async def test_clone_voice_propagates_minimax_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def post(self, url: str, *, headers, json) -> _FakeResponse:
            return _FakeResponse(
                {"base_resp": {"status_code": 1001, "status_msg": "voice_id exists"}}
            )

    monkeypatch.setattr("tokenmind.creative.voice_clone.httpx.AsyncClient", _FakeAsyncClient)
    service = VoiceCloneService(_voice_clone_capability())

    with pytest.raises(RuntimeError, match="voice_id exists"):
        await service.clone_voice(file_id=1, voice_id="clone_abcdefgh")


@pytest.mark.asyncio
async def test_keep_alive_voice_posts_to_t2a_v2(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def post(self, url: str, *, headers, json) -> _FakeResponse:
            captured["url"] = url
            captured["json"] = json
            return _FakeResponse({"base_resp": {"status_code": 0}})

    monkeypatch.setattr("tokenmind.creative.voice_clone.httpx.AsyncClient", _FakeAsyncClient)
    service = VoiceCloneService(_voice_clone_capability())

    await service.keep_alive_voice(voice_id="clone_alive01a")

    assert captured["url"] == "https://api.minimaxi.com/v1/t2a_v2"
    assert captured["json"]["voice_setting"] == {"voice_id": "clone_alive01a"}
    assert captured["json"]["model"] == "speech-2.8-hd"
    assert captured["json"]["text"]


@pytest.mark.asyncio
async def test_download_demo_audio_returns_bytes_and_mime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeResponseWithContent:
        content = b"demo-mp3-bytes"
        headers = {"content-type": "audio/mpeg"}

        def raise_for_status(self) -> None:
            return None

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str) -> _FakeResponseWithContent:
            return _FakeResponseWithContent()

    monkeypatch.setattr("tokenmind.creative.voice_clone.httpx.AsyncClient", _FakeAsyncClient)
    data, mime = await VoiceCloneService.download_demo_audio("https://cdn/x.mp3")
    assert data == b"demo-mp3-bytes"
    assert mime == "audio/mpeg"


def test_is_configured_requires_enabled_provider_and_api_key() -> None:
    disabled = _voice_clone_capability(enabled=False)
    assert VoiceCloneService.is_configured(disabled) is False

    no_key = _voice_clone_capability(apiKey="")
    assert VoiceCloneService.is_configured(no_key) is False

    ok = _voice_clone_capability()
    assert VoiceCloneService.is_configured(ok) is True
