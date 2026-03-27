"""Backward-compatible wrapper for custom OpenAI-compatible endpoints."""

from __future__ import annotations

from sun_agent.providers.openai_compat_provider import OpenAICompatProvider
from sun_agent.providers.registry import find_by_name


class CustomProvider(OpenAICompatProvider):
    """Alias around OpenAICompatProvider for existing imports/tests."""

    def __init__(
        self,
        api_key: str = "no-key",
        api_base: str = "http://localhost:8000/v1",
        default_model: str = "default",
        extra_headers: dict[str, str] | None = None,
    ):
        super().__init__(
            api_key=api_key,
            api_base=api_base,
            default_model=default_model,
            extra_headers=extra_headers,
            spec=find_by_name("custom"),
        )
