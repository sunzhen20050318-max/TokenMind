"""Model information helpers for the onboard wizard.

The project keeps a lightweight local model catalog that covers the built-in
providers and common defaults without relying on a large external model DB.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

_MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "anthropic/claude-opus-4-5": {"max_input_tokens": 200_000},
    "anthropic/claude-sonnet-4-5": {"max_input_tokens": 200_000},
    "openai/gpt-4o": {"max_input_tokens": 128_000},
    "openai/gpt-4o-mini": {"max_input_tokens": 128_000},
    "gpt-4o": {"max_input_tokens": 128_000},
    "gpt-4o-mini": {"max_input_tokens": 128_000},
    "gpt-5.2-chat": {"max_input_tokens": 400_000},
    "deepseek-chat": {"max_input_tokens": 128_000},
    "deepseek-reasoner": {"max_input_tokens": 128_000},
    "gemini-2.0-flash": {"max_input_tokens": 1_000_000},
    "gemini-2.5-flash": {"max_input_tokens": 1_000_000},
    "glm-4": {"max_input_tokens": 128_000},
    "qwen-max": {"max_input_tokens": 128_000},
    "qwen-plus": {"max_input_tokens": 128_000},
    "kimi-k2.5": {"max_input_tokens": 128_000},
    "MiniMax-M2.7": {"max_input_tokens": 128_000},
    "llama3.2": {"max_input_tokens": 128_000},
    "llama-3.1-8b-instruct": {"max_input_tokens": 128_000},
    "Qwen/Qwen2.5-7B-Instruct": {"max_input_tokens": 128_000},
    "doubao-1-5-pro-32k": {"max_input_tokens": 32_000},
    "doubao-seed-1-6": {"max_input_tokens": 256_000},
    "github-copilot/gpt-5.3-codex": {"max_input_tokens": 200_000},
    "openai-codex/gpt-5.1-codex": {"max_input_tokens": 200_000},
}


def _normalize_model_name(model: str) -> str:
    return model.lower().replace("-", "_").replace(".", "")


@lru_cache(maxsize=1)
def get_all_models() -> list[str]:
    return sorted(_MODEL_CATALOG)


def find_model_info(model_name: str) -> dict[str, Any] | None:
    if model_name in _MODEL_CATALOG:
        return _MODEL_CATALOG[model_name]

    base_name = model_name.split("/")[-1] if "/" in model_name else model_name
    base_normalized = _normalize_model_name(base_name)
    candidates: list[tuple[int, str, dict[str, Any]]] = []

    for key, info in _MODEL_CATALOG.items():
        key_base = key.split("/")[-1] if "/" in key else key
        key_base_normalized = _normalize_model_name(key_base)
        score = 0
        if base_normalized == key_base_normalized:
            score = 100
        elif base_normalized in key_base_normalized:
            score = 80
        elif key_base_normalized in base_normalized:
            score = 70
        elif base_normalized[:10] and base_normalized[:10] in key_base_normalized:
            score = 50
        if score > 0:
            candidates.append((score, key, info))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def get_model_context_limit(model: str, provider: str = "auto") -> int | None:
    del provider
    info = find_model_info(model)
    if not info:
        return None
    max_input = info.get("max_input_tokens")
    return int(max_input) if isinstance(max_input, int) else None


@lru_cache(maxsize=1)
def _get_provider_keywords() -> dict[str, list[str]]:
    try:
        from tokenmind.providers.registry import PROVIDERS

        mapping = {}
        for spec in PROVIDERS:
            if spec.keywords:
                mapping[spec.name] = list(spec.keywords)
        return mapping
    except ImportError:
        return {}


def get_model_suggestions(partial: str, provider: str = "auto", limit: int = 20) -> list[str]:
    all_models = get_all_models()
    partial_lower = partial.lower()
    partial_normalized = _normalize_model_name(partial)
    provider_keywords = _get_provider_keywords()
    allowed_keywords = None if provider in ("", "auto") else provider_keywords.get(provider.lower())

    matches: list[str] | list[tuple[int, str]] = []
    for model in all_models:
        model_lower = model.lower()
        if allowed_keywords and not any(keyword in model_lower for keyword in allowed_keywords):
            continue
        if not partial:
            matches.append(model)
            continue
        if partial_lower in model_lower:
            matches.append((100 - model_lower.find(partial_lower), model))
        elif partial_normalized in _normalize_model_name(model):
            matches.append((50, model))

    if matches and isinstance(matches[0], tuple):
        scored = matches  # type: ignore[assignment]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [item[1] for item in scored[:limit]]

    plain = matches  # type: ignore[assignment]
    plain.sort()
    return plain[:limit]


def format_token_count(tokens: int) -> str:
    return f"{tokens:,}"
