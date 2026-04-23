from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from tokenmind.agent.loop import AgentLoop
from tokenmind.agent.tools.generate_image import GenerateImageTool
from tokenmind.bus.events import InboundMessage
from tokenmind.bus.queue import MessageBus
from tokenmind.config.schema import Config
from tokenmind.creative.image_generation import ImageGenerationService
from tokenmind.providers.base import LLMResponse, ToolCallRequest


@pytest.mark.asyncio
async def test_openai_compat_image_service_decodes_base64(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    class _FakeImages:
        async def generate(self, **kwargs):
            seen["request"] = kwargs
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(b"fake-png").decode("ascii"),
                        revised_prompt="refined prompt",
                    )
                ],
                output_format="png",
            )

    class _FakeClient:
        def __init__(self, **kwargs):
            seen["client_kwargs"] = kwargs
            self.images = _FakeImages()

    monkeypatch.setattr("tokenmind.creative.image_generation.AsyncOpenAI", _FakeClient)
    service = ImageGenerationService(
        Config.model_validate(
            {
                "creative": {
                    "image": {
                        "enabled": True,
                        "provider": "openai",
                        "apiKey": "openai-key",
                        "model": "gpt-image-1",
                    }
                }
            }
        ).creative.image
    )

    result = await service.generate("draw a mountain cabin", size="1024x1024", quality="hd")

    assert result.data == b"fake-png"
    assert result.mime_type == "image/png"
    assert result.revised_prompt == "refined prompt"
    assert seen["request"] == {
        "model": "gpt-image-1",
        "prompt": "draw a mountain cabin",
        "response_format": "b64_json",
        "size": "1024x1024",
        "quality": "hd",
    }


@pytest.mark.asyncio
async def test_minimax_image_service_uses_native_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "data": {
                    "image_base64": [base64.b64encode(b"fake-jpeg").decode("ascii")],
                }
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

    monkeypatch.setattr("tokenmind.creative.image_generation.httpx.AsyncClient", _FakeAsyncClient)
    service = ImageGenerationService(
        Config.model_validate(
            {
                "creative": {
                    "image": {
                        "enabled": True,
                        "provider": "minimax",
                        "apiKey": "minimax-key",
                        "model": "image-01",
                    }
                }
            }
        ).creative.image
    )

    result = await service.generate("海边的白色灯塔", size="1536x1024")

    assert result.data == b"fake-jpeg"
    assert result.mime_type == "image/jpeg"
    assert seen["url"] == "https://api.minimax.io/v1/image_generation"
    assert seen["headers"]["Authorization"] == "Bearer minimax-key"
    assert seen["json"] == {
        "model": "image-01",
        "prompt": "海边的白色灯塔",
        "response_format": "base64",
        "aspect_ratio": "3:2",
    }


def _make_loop(tmp_path: Path) -> AgentLoop:
    config = Config.model_validate(
        {
            "creative": {
                "image": {
                    "enabled": True,
                    "provider": "openai",
                    "apiKey": "openai-key",
                    "model": "gpt-image-1",
                }
            }
        }
    )
    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    return AgentLoop(
        bus=bus,
        provider=provider,
        workspace=tmp_path,
        model="test-model",
        creative_config=config.creative,
    )


@pytest.mark.asyncio
async def test_generate_image_tool_attaches_image_to_web_reply(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    image_tool = loop.tools.get("generate_image")
    assert isinstance(image_tool, GenerateImageTool)
    image_tool._service.generate = AsyncMock(
        return_value=SimpleNamespace(
            filename="poster.png",
            mime_type="image/png",
            data=b"\x89PNG\r\n\x1a\nposter",
            model="gpt-image-1",
            provider="openai",
            revised_prompt=None,
        )
    )

    tool_call = ToolCallRequest(
        id="call-image",
        name="generate_image",
        arguments={
            "prompt": "生成一张赛博朋克风格海报",
            "size": "1024x1024",
        },
    )
    calls = iter(
        [
            LLMResponse(content="", tool_calls=[tool_call]),
            LLMResponse(content="海报已经生成好了。", tool_calls=[]),
        ]
    )
    loop.provider.chat_with_retry = AsyncMock(side_effect=lambda *args, **kwargs: next(calls))
    loop.tools.get_definitions = MagicMock(return_value=[image_tool.to_schema()])

    msg = InboundMessage(
        channel="web",
        sender_id="web_user",
        chat_id="web:test-session",
        content="帮我生成一张海报",
    )

    result = await loop._process_message(msg)

    assert result is not None
    attachments = result.metadata.get("_attachments") or []
    assert len(attachments) == 1
    assert attachments[0]["name"] == "poster.png"
    assert attachments[0]["is_image"] is True
    assert attachments[0]["origin"] == "assistant_generated"

    saved_session = loop.sessions.get_or_create(msg.session_key)
    assistant_messages = [item for item in saved_session.messages if item.get("role") == "assistant"]
    assert assistant_messages
    assert assistant_messages[-1]["attachments"][0]["name"] == "poster.png"


@pytest.mark.asyncio
async def test_minimax_image_service_adds_subject_reference_for_local_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"\x89PNG\r\n\x1a\nreference")

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "data": {
                    "image_base64": [base64.b64encode(b"fake-jpeg").decode("ascii")],
                }
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

    monkeypatch.setattr("tokenmind.creative.image_generation.httpx.AsyncClient", _FakeAsyncClient)
    service = ImageGenerationService(
        Config.model_validate(
            {
                "creative": {
                    "image": {
                        "enabled": True,
                        "provider": "minimax",
                        "apiKey": "minimax-key",
                        "model": "image-01",
                    }
                }
            }
        ).creative.image
    )

    await service.generate(
        "reference this image to create a new poster",
        size="1024x1024",
        reference_image_paths=[str(reference)],
    )

    payload = seen["json"]
    assert isinstance(payload, dict)
    assert payload["subject_reference"] == [
        {
            "type": "character",
            "image_file": "data:image/png;base64,iVBORw0KGgpyZWZlcmVuY2U=",
        }
    ]


@pytest.mark.asyncio
async def test_generate_image_tool_auto_uses_uploaded_reference_image_on_explicit_reference_prompt(
    tmp_path: Path,
) -> None:
    loop = _make_loop(tmp_path)
    image_tool = loop.tools.get("generate_image")
    assert isinstance(image_tool, GenerateImageTool)
    image_tool._service.generate = AsyncMock(
        return_value=SimpleNamespace(
            filename="poster.png",
            mime_type="image/png",
            data=b"\x89PNG\r\n\x1a\nposter",
            model="gpt-image-1",
            provider="openai",
            revised_prompt=None,
        )
    )

    uploaded = tmp_path / "uploads" / "ref.png"
    uploaded.parent.mkdir(parents=True, exist_ok=True)
    uploaded.write_bytes(b"\x89PNG\r\n\x1a\nreference")

    tool_call = ToolCallRequest(
        id="call-image",
        name="generate_image",
        arguments={
            "prompt": "参考这张图生成一张新海报",
            "size": "1024x1024",
        },
    )
    calls = iter(
        [
            LLMResponse(content="", tool_calls=[tool_call]),
            LLMResponse(content="好了，已经基于参考图生成。", tool_calls=[]),
        ]
    )
    loop.provider.chat_with_retry = AsyncMock(side_effect=lambda *args, **kwargs: next(calls))
    loop.tools.get_definitions = MagicMock(return_value=[image_tool.to_schema()])

    msg = InboundMessage(
        channel="web",
        sender_id="web_user",
        chat_id="web:test-session",
        content="参考这张图生成一张新海报",
        metadata={
            "attachments": [
                {
                    "name": "ref.png",
                    "path": str(uploaded),
                    "mime_type": "image/png",
                    "size": uploaded.stat().st_size,
                    "category": "image",
                    "is_image": True,
                }
            ]
        },
    )

    await loop._process_message(msg)

    image_tool._service.generate.assert_awaited_once_with(
        "参考这张图生成一张新海报",
        size="1024x1024",
        quality=None,
        background=None,
        reference_image_paths=[str(uploaded)],
        reference_type="character",
    )


@pytest.mark.asyncio
async def test_generate_image_tool_does_not_auto_use_uploaded_image_without_explicit_reference_prompt(
    tmp_path: Path,
) -> None:
    loop = _make_loop(tmp_path)
    image_tool = loop.tools.get("generate_image")
    assert isinstance(image_tool, GenerateImageTool)
    image_tool._service.generate = AsyncMock(
        return_value=SimpleNamespace(
            filename="poster.png",
            mime_type="image/png",
            data=b"\x89PNG\r\n\x1a\nposter",
            model="gpt-image-1",
            provider="openai",
            revised_prompt=None,
        )
    )

    uploaded = tmp_path / "uploads" / "ref.png"
    uploaded.parent.mkdir(parents=True, exist_ok=True)
    uploaded.write_bytes(b"\x89PNG\r\n\x1a\nreference")

    tool_call = ToolCallRequest(
        id="call-image",
        name="generate_image",
        arguments={
            "prompt": "帮我生成一张国潮海报",
            "size": "1024x1024",
        },
    )
    calls = iter(
        [
            LLMResponse(content="", tool_calls=[tool_call]),
            LLMResponse(content="好的，海报已生成。", tool_calls=[]),
        ]
    )
    loop.provider.chat_with_retry = AsyncMock(side_effect=lambda *args, **kwargs: next(calls))
    loop.tools.get_definitions = MagicMock(return_value=[image_tool.to_schema()])

    msg = InboundMessage(
        channel="web",
        sender_id="web_user",
        chat_id="web:test-session",
        content="帮我生成一张国潮海报",
        metadata={
            "attachments": [
                {
                    "name": "ref.png",
                    "path": str(uploaded),
                    "mime_type": "image/png",
                    "size": uploaded.stat().st_size,
                    "category": "image",
                    "is_image": True,
                }
            ]
        },
    )

    await loop._process_message(msg)

    image_tool._service.generate.assert_awaited_once_with(
        "帮我生成一张国潮海报",
        size="1024x1024",
        quality=None,
        background=None,
        reference_image_paths=None,
        reference_type="character",
    )
