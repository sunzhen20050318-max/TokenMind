"""Tests for the FallbackProvider wrapper."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from tokenmind.providers.base import GenerationSettings, LLMResponse
from tokenmind.providers.fallback import (
    _PRIMARY_COOLDOWN_S,
    _PRIMARY_FAILURE_THRESHOLD,
    FallbackProvider,
)


def _make_provider(model: str, response: LLMResponse) -> MagicMock:
    """Build a MagicMock provider that returns the given response from chat()."""
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


@pytest.mark.asyncio
async def test_primary_success_returns_immediately() -> None:
    """When the primary succeeds, no fallback should be consulted."""
    primary = _make_provider("anthropic/claude-opus-4-5", LLMResponse(content="ok", finish_reason="stop"))
    backup = _make_provider("deepseek/deepseek-chat", LLMResponse(content="never", finish_reason="stop"))
    wrapped = FallbackProvider(
        primary=primary,
        fallback_models=["deepseek/deepseek-chat"],
        provider_factory=_factory_from_map({"deepseek/deepseek-chat": backup}),
    )

    result = await wrapped.chat(messages=[{"role": "user", "content": "hi"}])

    assert result.content == "ok"
    assert primary.chat.await_count == 1
    backup.chat.assert_not_called()


@pytest.mark.asyncio
async def test_primary_error_falls_over_to_backup() -> None:
    """A primary returning finish_reason='error' should trigger the backup."""
    primary = _make_provider(
        "anthropic/claude-opus-4-5",
        LLMResponse(content="HTTP 429: rate limit", finish_reason="error"),
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

    result = await wrapped.chat(messages=[{"role": "user", "content": "hi"}])

    assert result.content == "from backup"
    assert primary.chat.await_count == 1
    assert backup.chat.await_count == 1
    # The model kwarg should have been swapped to the backup's name.
    call = backup.chat.await_args
    assert call.kwargs["model"] == "deepseek/deepseek-chat"


@pytest.mark.asyncio
async def test_walks_multiple_fallbacks_in_order() -> None:
    """Each consecutive failure advances to the next backup."""
    primary = _make_provider(
        "anthropic/claude-opus-4-5",
        LLMResponse(content="boom", finish_reason="error"),
    )
    backup_a = _make_provider(
        "moonshot/kimi", LLMResponse(content="a-fail", finish_reason="error"),
    )
    backup_b = _make_provider(
        "deepseek/deepseek-chat", LLMResponse(content="b-ok", finish_reason="stop"),
    )
    wrapped = FallbackProvider(
        primary=primary,
        fallback_models=["moonshot/kimi", "deepseek/deepseek-chat"],
        provider_factory=_factory_from_map({
            "moonshot/kimi": backup_a,
            "deepseek/deepseek-chat": backup_b,
        }),
    )

    result = await wrapped.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.content == "b-ok"
    assert backup_a.chat.await_count == 1
    assert backup_b.chat.await_count == 1


@pytest.mark.asyncio
async def test_all_failures_returns_last_error() -> None:
    """When every model errors, the user gets the most recent error."""
    primary = _make_provider("anthropic/p", LLMResponse(content="p-fail", finish_reason="error"))
    backup = _make_provider("deepseek/b", LLMResponse(content="b-fail", finish_reason="error"))
    wrapped = FallbackProvider(
        primary=primary,
        fallback_models=["deepseek/b"],
        provider_factory=_factory_from_map({"deepseek/b": backup}),
    )

    result = await wrapped.chat(messages=[{"role": "user", "content": "hi"}])

    assert result.finish_reason == "error"
    assert result.content == "b-fail"


@pytest.mark.asyncio
async def test_no_fallbacks_means_no_wrapping_overhead() -> None:
    """Empty fallback_models is a passthrough."""
    primary = _make_provider("p", LLMResponse(content="p-ok", finish_reason="stop"))
    wrapped = FallbackProvider(
        primary=primary, fallback_models=[], provider_factory=lambda m: None  # noqa: ARG005
    )

    result = await wrapped.chat(messages=[])
    assert result.content == "p-ok"


@pytest.mark.asyncio
async def test_factory_exception_skips_that_backup() -> None:
    """A provider_factory exception shouldn't crash the chain — try the next backup."""
    primary = _make_provider("p", LLMResponse(content="primary-fail", finish_reason="error"))
    good = _make_provider("good/model", LLMResponse(content="recovered", finish_reason="stop"))

    def factory(model: str):
        if model == "bad/model":
            raise RuntimeError("no api key")
        return good

    wrapped = FallbackProvider(
        primary=primary,
        fallback_models=["bad/model", "good/model"],
        provider_factory=factory,
    )

    result = await wrapped.chat(messages=[])
    assert result.content == "recovered"


@pytest.mark.asyncio
async def test_circuit_breaker_trips_after_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """After N consecutive primary failures the primary should be skipped."""
    primary = _make_provider("p", LLMResponse(content="p-fail", finish_reason="error"))
    backup = _make_provider("b", LLMResponse(content="b-ok", finish_reason="stop"))
    wrapped = FallbackProvider(
        primary=primary,
        fallback_models=["b"],
        provider_factory=_factory_from_map({"b": backup}),
    )

    for _ in range(_PRIMARY_FAILURE_THRESHOLD):
        result = await wrapped.chat(messages=[])
        assert result.content == "b-ok"

    assert primary.chat.await_count == _PRIMARY_FAILURE_THRESHOLD

    # Next call should skip the primary entirely.
    result = await wrapped.chat(messages=[])
    assert result.content == "b-ok"
    # Primary call count did NOT advance.
    assert primary.chat.await_count == _PRIMARY_FAILURE_THRESHOLD


@pytest.mark.asyncio
async def test_circuit_breaker_recovers_after_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Once the cooldown elapses the primary should be probed again."""
    primary = _make_provider("p", LLMResponse(content="p-fail", finish_reason="error"))
    backup = _make_provider("b", LLMResponse(content="b-ok", finish_reason="stop"))
    wrapped = FallbackProvider(
        primary=primary,
        fallback_models=["b"],
        provider_factory=_factory_from_map({"b": backup}),
    )

    # Trip the breaker.
    for _ in range(_PRIMARY_FAILURE_THRESHOLD):
        await wrapped.chat(messages=[])
    primary_calls_after_trip = primary.chat.await_count

    # Fast-forward time past the cooldown by patching monotonic.
    base = time.monotonic()
    monkeypatch.setattr(
        "tokenmind.providers.fallback.time.monotonic",
        lambda: base + _PRIMARY_COOLDOWN_S + 1,
    )

    await wrapped.chat(messages=[])
    # Primary should have been probed once more.
    assert primary.chat.await_count == primary_calls_after_trip + 1
