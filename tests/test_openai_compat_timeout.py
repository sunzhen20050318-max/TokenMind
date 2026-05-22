"""Tests for the OpenAI-compatible provider request timeout cap."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tokenmind.providers import openai_compat_provider as ocp
from tokenmind.providers.openai_compat_provider import (
    _OPENAI_COMPAT_REQUEST_TIMEOUT_S,
    OpenAICompatProvider,
    _openai_compat_timeout_s,
)


def test_default_timeout_is_120s() -> None:
    assert _OPENAI_COMPAT_REQUEST_TIMEOUT_S == 120.0


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKENMIND_OPENAI_COMPAT_TIMEOUT_S", "45")
    assert _openai_compat_timeout_s() == 45.0


def test_env_override_invalid_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKENMIND_OPENAI_COMPAT_TIMEOUT_S", "not-a-number")
    assert _openai_compat_timeout_s() == _OPENAI_COMPAT_REQUEST_TIMEOUT_S


def test_env_override_non_positive_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKENMIND_OPENAI_COMPAT_TIMEOUT_S", "0")
    assert _openai_compat_timeout_s() == _OPENAI_COMPAT_REQUEST_TIMEOUT_S
    monkeypatch.setenv("TOKENMIND_OPENAI_COMPAT_TIMEOUT_S", "-5")
    assert _openai_compat_timeout_s() == _OPENAI_COMPAT_REQUEST_TIMEOUT_S


def test_env_empty_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKENMIND_OPENAI_COMPAT_TIMEOUT_S", "  ")
    assert _openai_compat_timeout_s() == _OPENAI_COMPAT_REQUEST_TIMEOUT_S


def test_provider_passes_timeout_to_sdk() -> None:
    with patch.object(ocp, "AsyncOpenAI") as mock_async_openai:
        OpenAICompatProvider(
            api_key="test-key",
            api_base="https://example.com/v1",
        )
    kwargs = mock_async_openai.call_args.kwargs
    assert kwargs["timeout"] == _OPENAI_COMPAT_REQUEST_TIMEOUT_S


def test_provider_honors_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKENMIND_OPENAI_COMPAT_TIMEOUT_S", "30")
    with patch.object(ocp, "AsyncOpenAI") as mock_async_openai:
        OpenAICompatProvider(
            api_key="test-key",
            api_base="https://example.com/v1",
        )
    assert mock_async_openai.call_args.kwargs["timeout"] == 30.0
