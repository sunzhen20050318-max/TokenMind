"""Provider-agnostic token usage normalization.

Different providers expose token counts in incompatible shapes:

- **Anthropic** returns four additive fields: `input_tokens`,
  `cache_read_input_tokens`, `cache_creation_input_tokens`, `output_tokens`.
- **OpenAI / OpenAI-compatible** returns two summed fields plus optional
  detail subsets (`prompt_tokens_details.cached_tokens`,
  `completion_tokens_details.reasoning_tokens`). Cache hits are a subset of
  `prompt_tokens` rather than a separate count.
- **DeepSeek** returns `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`
  alongside the OpenAI-style fields.

`build_usage` normalizes all of these into a single dict where:

- `input_tokens` is the *uncached* billable input.
- `cached_input_tokens` is the cache-read count (cheap or free).
- `cache_write_tokens` is the cache-creation count (Anthropic only).
- `output_tokens` is the total output, including any reasoning tokens.
- `reasoning_tokens` is a *subset* of `output_tokens` — informational, not
  added into `total_tokens`.

The legacy keys `prompt_tokens` / `completion_tokens` / `total_tokens` are
preserved for backward compatibility with anything that read the old shape.
"""

from __future__ import annotations


def build_usage(
    *,
    input_tokens: int = 0,
    cached_input_tokens: int = 0,
    cache_write_tokens: int = 0,
    output_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> dict[str, int]:
    """Return a unified usage dict from per-dimension counts.

    All counts are coerced to non-negative integers. Reasoning tokens are
    intentionally excluded from `total_tokens` because providers bill them
    inside `output_tokens` already.
    """
    input_tokens = max(0, int(input_tokens or 0))
    cached_input_tokens = max(0, int(cached_input_tokens or 0))
    cache_write_tokens = max(0, int(cache_write_tokens or 0))
    output_tokens = max(0, int(output_tokens or 0))
    reasoning_tokens = max(0, int(reasoning_tokens or 0))

    total_input = input_tokens + cached_input_tokens + cache_write_tokens
    total = total_input + output_tokens

    return {
        # Backward-compatible flat fields
        "prompt_tokens": total_input,
        "completion_tokens": output_tokens,
        "total_tokens": total,
        # Extended fields used by the usage recorder
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "cache_write_tokens": cache_write_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
    }
