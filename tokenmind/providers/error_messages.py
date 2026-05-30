"""Map raw provider errors into friendly, actionable Chinese messages.

Providers populate ``LLMResponse`` with ``content`` (the raw error string),
``error_status_code``, ``error_code`` and ``retry_after_s`` but the agent loop
used to surface that raw English text straight to the user. This module turns
those structured fields into a short Chinese message that tells the user what
went wrong and what to do next, while keeping a compact technical tail for the
truly-unknown case so power users can still debug.
"""

from __future__ import annotations

from typing import Any

# Markers checked against the lowercased error content / error_code. Status
# codes are checked first where they're authoritative.
_AUTH_MARKERS = (
    "invalid api key",
    "unauthorized",
    "authentication",
    "api key",
    "api_key",
    "permission",
    "forbidden",
    "no auth",
)
_RATE_LIMIT_MARKERS = (
    "rate limit",
    "ratelimit",
    "rate_limit",
    "too many requests",
    "quota",
    "限流",
    "exceeded your current quota",
)
_CONTEXT_MARKERS = (
    "context length",
    "maximum context",
    "context_length_exceeded",
    "context window",
    "reduce the length",
    "too many tokens",
    "prompt is too long",
    "string too long",
)
_TIMEOUT_MARKERS = ("timeout", "timed out")
_CONNECTION_MARKERS = (
    "connection",
    "connect error",
    "name resolution",
    "dns",
    "ssl",
    "unreachable",
    "network",
)
_SERVER_MARKERS = (
    "overloaded",
    "server error",
    "internal server error",
    "temporarily unavailable",
    "service unavailable",
    "bad gateway",
    "502",
    "503",
    "504",
    "529",
)


def classify_provider_error(
    *,
    content: str | None = None,
    status_code: int | None = None,
    error_code: str | None = None,
    retry_after_s: float | None = None,
) -> str:
    """Return a friendly Chinese message for a provider error.

    Resolution order: authoritative status codes first, then keyword markers
    in the error content / code. Falls back to a generic message that keeps a
    trimmed copy of the raw detail.
    """
    text = (content or "").lower()
    code = (error_code or "").lower()

    def has(*markers: str) -> bool:
        return any(m in text or m in code for m in markers)

    # Authentication / authorization
    if status_code in (401, 403) or has(*_AUTH_MARKERS):
        return (
            "模型调用未授权：API 密钥无效、过期或没有访问权限。"
            "请在「设置 → 模型服务」检查该 Provider 的密钥配置。"
        )

    # Rate limit / quota
    if status_code == 429 or has(*_RATE_LIMIT_MARKERS):
        msg = "请求过于频繁或额度不足，已被服务方限流。"
        if retry_after_s:
            msg += f"约 {retry_after_s:g}s 后可重试。"
        else:
            msg += "请稍后重试，或在设置里配置备用模型（fallback）以自动切换。"
        return msg

    # Context length exceeded
    if has(*_CONTEXT_MARKERS):
        return (
            "对话内容超出了模型的上下文上限。"
            "请精简历史、移除大附件，或开启一个新会话后重试。"
        )

    # Timeout
    if has(*_TIMEOUT_MARKERS):
        return "调用模型超时，可能是网络不稳定或模型服务繁忙。请稍后重试。"

    # Connection / network
    if has(*_CONNECTION_MARKERS):
        return "无法连接到模型服务。请检查网络，以及该 Provider 的 API 地址是否正确。"

    # Server-side errors
    if (status_code is not None and status_code >= 500) or has(*_SERVER_MARKERS):
        return "模型服务暂时不可用（服务端繁忙或过载）。请稍后重试。"

    # Unknown — keep a compact technical tail for debugging.
    base = "调用模型时出错。请稍后重试；若反复出现，请检查模型与 Provider 配置。"
    detail = (content or "").strip()
    if detail:
        detail = detail.replace("\n", " ")[:160]
        base += f"\n（详情：{detail}）"
    return base


def friendly_error_message(response: Any) -> str:
    """Classify an ``LLMResponse``-like object's error into Chinese."""
    return classify_provider_error(
        content=getattr(response, "content", None),
        status_code=getattr(response, "error_status_code", None),
        error_code=getattr(response, "error_code", None),
        retry_after_s=getattr(response, "retry_after_s", None),
    )
