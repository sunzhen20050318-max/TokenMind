"""Fallback transparency: the response must identify which model actually answered.

Without this, a turn served by a backup model is silently attributed to the
primary in usage accounting and in the /status card the user sees.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tokenmind.providers.base import GenerationSettings, LLMResponse
from tokenmind.providers.fallback import FallbackProvider


def _make_provider(model: str, response: LLMResponse) -> MagicMock:
    provider = MagicMock()
    provider.get_default_model.return_value = model
    provider.generation = GenerationSettings()
    provider.chat = AsyncMock(return_value=response)
    return provider


def _factory_from_map(mapping: dict[str, MagicMock]):
    def factory(model: str) -> MagicMock:
        if model not in mapping:
            raise KeyError(f"unexpected fallback request: {model}")
        return mapping[model]

    return factory


def test_llm_response_has_model_field() -> None:
    """LLMResponse must be able to carry the answering model name."""
    assert LLMResponse(content="x").model is None
    assert LLMResponse(content="x", model="deepseek/deepseek-chat").model == "deepseek/deepseek-chat"


@pytest.mark.asyncio
async def test_backup_response_carries_actual_model() -> None:
    """When a backup answers, the response identifies the backup, not the primary."""
    primary = _make_provider(
        "anthropic/claude-opus-4-5",
        LLMResponse(content="boom", finish_reason="error"),
    )
    backup = _make_provider(
        "deepseek/deepseek-chat",
        LLMResponse(content="from backup", finish_reason="stop"),
    )
    wrapped = FallbackProvider(
        primary=primary,
        fallback_models=["deepseek/deepseek-chat"],
        provider_factory=_factory_from_map({"deepseek/deepseek-chat": backup}),
    )

    result = await wrapped.chat(
        messages=[{"role": "user", "content": "hi"}],
        model="anthropic/claude-opus-4-5",
    )

    assert result.content == "from backup"
    assert result.model == "deepseek/deepseek-chat"


@pytest.mark.asyncio
async def test_primary_success_response_carries_primary_model() -> None:
    """A primary-served turn is attributed to the primary model."""
    primary = _make_provider(
        "anthropic/claude-opus-4-5",
        LLMResponse(content="ok", finish_reason="stop"),
    )
    backup = _make_provider(
        "deepseek/deepseek-chat",
        LLMResponse(content="never", finish_reason="stop"),
    )
    wrapped = FallbackProvider(
        primary=primary,
        fallback_models=["deepseek/deepseek-chat"],
        provider_factory=_factory_from_map({"deepseek/deepseek-chat": backup}),
    )

    result = await wrapped.chat(
        messages=[{"role": "user", "content": "hi"}],
        model="anthropic/claude-opus-4-5",
    )

    assert result.model == "anthropic/claude-opus-4-5"
