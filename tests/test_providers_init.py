"""Tests for lazy provider exports from sun_agent.providers."""

from __future__ import annotations

import importlib
import sys


def test_importing_providers_package_is_lazy(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "sun_agent.providers", raising=False)
    monkeypatch.delitem(sys.modules, "sun_agent.providers.anthropic_provider", raising=False)
    monkeypatch.delitem(sys.modules, "sun_agent.providers.openai_compat_provider", raising=False)
    monkeypatch.delitem(sys.modules, "sun_agent.providers.custom_provider", raising=False)
    monkeypatch.delitem(sys.modules, "sun_agent.providers.openai_codex_provider", raising=False)
    monkeypatch.delitem(sys.modules, "sun_agent.providers.azure_openai_provider", raising=False)

    providers = importlib.import_module("sun_agent.providers")

    assert "sun_agent.providers.anthropic_provider" not in sys.modules
    assert "sun_agent.providers.openai_compat_provider" not in sys.modules
    assert "sun_agent.providers.custom_provider" not in sys.modules
    assert "sun_agent.providers.openai_codex_provider" not in sys.modules
    assert "sun_agent.providers.azure_openai_provider" not in sys.modules
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
    monkeypatch.delitem(sys.modules, "sun_agent.providers", raising=False)
    monkeypatch.delitem(sys.modules, "sun_agent.providers.openai_compat_provider", raising=False)

    namespace: dict[str, object] = {}
    exec("from sun_agent.providers import OpenAICompatProvider", namespace)

    assert namespace["OpenAICompatProvider"].__name__ == "OpenAICompatProvider"
    assert "sun_agent.providers.openai_compat_provider" in sys.modules
