"""Tests for lazy provider exports from tokenmind.providers."""

from __future__ import annotations

import importlib
import sys


def test_importing_providers_package_is_lazy(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "tokenmind.providers", raising=False)
    monkeypatch.delitem(sys.modules, "tokenmind.providers.anthropic_provider", raising=False)
    monkeypatch.delitem(sys.modules, "tokenmind.providers.openai_compat_provider", raising=False)
    monkeypatch.delitem(sys.modules, "tokenmind.providers.custom_provider", raising=False)
    monkeypatch.delitem(sys.modules, "tokenmind.providers.openai_codex_provider", raising=False)
    monkeypatch.delitem(sys.modules, "tokenmind.providers.azure_openai_provider", raising=False)

    providers = importlib.import_module("tokenmind.providers")

    assert "tokenmind.providers.anthropic_provider" not in sys.modules
    assert "tokenmind.providers.openai_compat_provider" not in sys.modules
    assert "tokenmind.providers.custom_provider" not in sys.modules
    assert "tokenmind.providers.openai_codex_provider" not in sys.modules
    assert "tokenmind.providers.azure_openai_provider" not in sys.modules
    assert providers.__all__ == [
        "LLMProvider",
        "LLMResponse",
        "AnthropicProvider",
        "OpenAICompatProvider",
        "CustomProvider",
        "OpenAICodexProvider",
        "AzureOpenAIProvider",
    ]


def test_explicit_provider_import_still_works(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "tokenmind.providers", raising=False)
    monkeypatch.delitem(sys.modules, "tokenmind.providers.openai_compat_provider", raising=False)

    namespace: dict[str, object] = {}
    exec("from tokenmind.providers import OpenAICompatProvider", namespace)

    assert namespace["OpenAICompatProvider"].__name__ == "OpenAICompatProvider"
    assert "tokenmind.providers.openai_compat_provider" in sys.modules
