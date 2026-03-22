"""Tests for lazy provider exports from sun_agent.providers."""

from __future__ import annotations

import importlib
import sys


def test_importing_providers_package_is_lazy(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "sun_agent.providers", raising=False)
    monkeypatch.delitem(sys.modules, "sun_agent.providers.litellm_provider", raising=False)
    monkeypatch.delitem(sys.modules, "sun_agent.providers.openai_codex_provider", raising=False)
    monkeypatch.delitem(sys.modules, "sun_agent.providers.azure_openai_provider", raising=False)

    providers = importlib.import_module("sun_agent.providers")

    assert "sun_agent.providers.litellm_provider" not in sys.modules
    assert "sun_agent.providers.openai_codex_provider" not in sys.modules
    assert "sun_agent.providers.azure_openai_provider" not in sys.modules
    assert providers.__all__ == [
        "LLMProvider",
        "LLMResponse",
        "LiteLLMProvider",
        "OpenAICodexProvider",
        "AzureOpenAIProvider",
    ]


def test_explicit_provider_import_still_works(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "sun_agent.providers", raising=False)
    monkeypatch.delitem(sys.modules, "sun_agent.providers.litellm_provider", raising=False)

    namespace: dict[str, object] = {}
    exec("from sun_agent.providers import LiteLLMProvider", namespace)

    assert namespace["LiteLLMProvider"].__name__ == "LiteLLMProvider"
    assert "sun_agent.providers.litellm_provider" in sys.modules
