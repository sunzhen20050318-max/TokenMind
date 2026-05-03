"""Tests for provider usage field normalization."""

from __future__ import annotations

from types import SimpleNamespace

from tokenmind.providers.openai_compat_provider import _normalize_openai_usage
from tokenmind.providers.usage import build_usage


def test_build_usage_legacy_keys_match_extended_fields() -> None:
    usage = build_usage(
        input_tokens=100,
        cached_input_tokens=50,
        cache_write_tokens=20,
        output_tokens=80,
        reasoning_tokens=30,
    )
    assert usage["prompt_tokens"] == 170  # 100 + 50 + 20
    assert usage["completion_tokens"] == 80
    assert usage["total_tokens"] == 250
    assert usage["input_tokens"] == 100
    assert usage["cached_input_tokens"] == 50
    assert usage["cache_write_tokens"] == 20
    assert usage["output_tokens"] == 80
    assert usage["reasoning_tokens"] == 30


def test_build_usage_handles_none_and_negative() -> None:
    usage = build_usage(
        input_tokens=None,  # type: ignore[arg-type]
        cached_input_tokens=-5,
        output_tokens=10,
    )
    assert usage["input_tokens"] == 0
    assert usage["cached_input_tokens"] == 0
    assert usage["total_tokens"] == 10


def test_build_usage_reasoning_not_added_to_total() -> None:
    """Reasoning is a subset of output; including it in total_tokens would
    double-count what providers already bill inside output_tokens."""
    usage = build_usage(input_tokens=100, output_tokens=200, reasoning_tokens=80)
    assert usage["total_tokens"] == 300


def test_normalize_openai_basic() -> None:
    obj = SimpleNamespace(prompt_tokens=500, completion_tokens=200)
    usage = _normalize_openai_usage(obj)
    assert usage["input_tokens"] == 500
    assert usage["cached_input_tokens"] == 0
    assert usage["output_tokens"] == 200
    assert usage["reasoning_tokens"] == 0


def test_normalize_openai_with_cached_tokens_attr() -> None:
    """Standard OpenAI shape: prompt_tokens_details.cached_tokens as attribute."""
    obj = SimpleNamespace(
        prompt_tokens=1000,
        completion_tokens=300,
        prompt_tokens_details=SimpleNamespace(cached_tokens=400),
    )
    usage = _normalize_openai_usage(obj)
    assert usage["input_tokens"] == 600  # 1000 - 400
    assert usage["cached_input_tokens"] == 400
    assert usage["output_tokens"] == 300


def test_normalize_openai_with_cached_tokens_dict() -> None:
    """Some gateways return prompt_tokens_details as a plain dict."""
    obj = SimpleNamespace(
        prompt_tokens=1000,
        completion_tokens=300,
        prompt_tokens_details={"cached_tokens": 250},
    )
    usage = _normalize_openai_usage(obj)
    assert usage["cached_input_tokens"] == 250
    assert usage["input_tokens"] == 750


def test_normalize_deepseek_cache_hit_field() -> None:
    """DeepSeek exposes prompt_cache_hit_tokens as a top-level extra."""
    obj = SimpleNamespace(
        prompt_tokens=1000,
        completion_tokens=200,
        model_extra={"prompt_cache_hit_tokens": 800},
    )
    usage = _normalize_openai_usage(obj)
    assert usage["cached_input_tokens"] == 800
    assert usage["input_tokens"] == 200


def test_normalize_openai_reasoning_tokens() -> None:
    obj = SimpleNamespace(
        prompt_tokens=500,
        completion_tokens=400,
        completion_tokens_details=SimpleNamespace(reasoning_tokens=300),
    )
    usage = _normalize_openai_usage(obj)
    assert usage["output_tokens"] == 400
    assert usage["reasoning_tokens"] == 300
    # Reasoning is a subset, total_tokens stays 500 + 400 = 900
    assert usage["total_tokens"] == 900


def test_normalize_openai_cached_clamped_to_prompt() -> None:
    """If a misbehaving provider reports cached > prompt, clamp instead of
    going negative on input_tokens."""
    obj = SimpleNamespace(
        prompt_tokens=100,
        completion_tokens=20,
        prompt_tokens_details=SimpleNamespace(cached_tokens=500),
    )
    usage = _normalize_openai_usage(obj)
    assert usage["cached_input_tokens"] == 100
    assert usage["input_tokens"] == 0
