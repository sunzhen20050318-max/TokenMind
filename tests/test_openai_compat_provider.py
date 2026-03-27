"""Tests for OpenAICompatProvider spec-driven behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from sun_agent.providers.openai_compat_provider import OpenAICompatProvider
from sun_agent.providers.registry import find_by_name


def _fake_chat_response(content: str = "ok") -> SimpleNamespace:
    message = SimpleNamespace(
        content=content,
        tool_calls=None,
        reasoning_content=None,
    )
    choice = SimpleNamespace(message=message, finish_reason="stop")
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    return SimpleNamespace(choices=[choice], usage=usage)


def test_openrouter_spec_is_gateway() -> None:
    spec = find_by_name("openrouter")
    assert spec is not None
    assert spec.is_gateway is True
    assert spec.default_api_base == "https://openrouter.ai/api/v1"


@pytest.mark.asyncio
async def test_openrouter_keeps_model_name_intact() -> None:
    mock_create = AsyncMock(return_value=_fake_chat_response())
    spec = find_by_name("openrouter")

    with patch("sun_agent.providers.openai_compat_provider.AsyncOpenAI") as mock_client:
        client_instance = mock_client.return_value
        client_instance.chat.completions.create = mock_create

        provider = OpenAICompatProvider(
            api_key="sk-or-test-key",
            api_base="https://openrouter.ai/api/v1",
            default_model="anthropic/claude-sonnet-4-5",
            spec=spec,
        )
        await provider.chat(
            messages=[{"role": "user", "content": "hello"}],
            model="anthropic/claude-sonnet-4-5",
        )

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["model"] == "anthropic/claude-sonnet-4-5"


@pytest.mark.asyncio
async def test_aihubmix_strips_model_prefix() -> None:
    mock_create = AsyncMock(return_value=_fake_chat_response())
    spec = find_by_name("aihubmix")

    with patch("sun_agent.providers.openai_compat_provider.AsyncOpenAI") as mock_client:
        client_instance = mock_client.return_value
        client_instance.chat.completions.create = mock_create

        provider = OpenAICompatProvider(
            api_key="sk-aihub-test-key",
            api_base="https://aihubmix.com/v1",
            default_model="claude-sonnet-4-5",
            spec=spec,
        )
        await provider.chat(
            messages=[{"role": "user", "content": "hello"}],
            model="anthropic/claude-sonnet-4-5",
        )

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-5"


@pytest.mark.asyncio
async def test_standard_provider_strips_explicit_provider_prefix() -> None:
    mock_create = AsyncMock(return_value=_fake_chat_response())
    spec = find_by_name("deepseek")

    with patch("sun_agent.providers.openai_compat_provider.AsyncOpenAI") as mock_client:
        client_instance = mock_client.return_value
        client_instance.chat.completions.create = mock_create

        provider = OpenAICompatProvider(
            api_key="sk-deepseek-test-key",
            default_model="deepseek/deepseek-chat",
            spec=spec,
        )
        await provider.chat(
            messages=[{"role": "user", "content": "hello"}],
            model="deepseek/deepseek-chat",
        )

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["model"] == "deepseek-chat"


def test_openai_model_passthrough() -> None:
    spec = find_by_name("openai")
    with patch("sun_agent.providers.openai_compat_provider.AsyncOpenAI"):
        provider = OpenAICompatProvider(
            api_key="sk-test-key",
            default_model="gpt-4o",
            spec=spec,
        )
    assert provider.get_default_model() == "gpt-4o"
