"""Provider error → friendly Chinese message classification.

Raw English provider errors (``Anthropic API Error 401: ...``,
``Error calling LLM: Timeout(...)``) used to leak straight to the user.
``classify_provider_error`` maps the structured error fields the providers
already populate into an actionable Chinese message.
"""

from __future__ import annotations

from types import SimpleNamespace

from tokenmind.providers.error_messages import (
    classify_provider_error,
    friendly_error_message,
)


def test_auth_error_by_status_code() -> None:
    msg = classify_provider_error(content="Unauthorized", status_code=401)
    assert "密钥" in msg and "未授权" in msg


def test_auth_error_by_marker_without_status() -> None:
    msg = classify_provider_error(content="Error: invalid api key provided")
    assert "密钥" in msg


def test_rate_limit_includes_retry_after() -> None:
    msg = classify_provider_error(content="rate limit", status_code=429, retry_after_s=12)
    assert "限流" in msg
    assert "12" in msg


def test_rate_limit_without_retry_after_suggests_fallback() -> None:
    msg = classify_provider_error(content="429 Too Many Requests", status_code=429)
    assert "限流" in msg
    assert "fallback" in msg or "备用" in msg


def test_context_length_error() -> None:
    msg = classify_provider_error(content="This model's maximum context length is 200000 tokens")
    assert "上下文" in msg


def test_timeout_error() -> None:
    msg = classify_provider_error(content="Error calling LLM: Request timed out")
    assert "超时" in msg


def test_connection_error() -> None:
    msg = classify_provider_error(content="Connection error.")
    assert "连接" in msg


def test_server_error_by_status_code() -> None:
    msg = classify_provider_error(content="overloaded_error", status_code=503)
    assert "暂时不可用" in msg


def test_overloaded_marker_without_status() -> None:
    msg = classify_provider_error(content="Anthropic API Error 529: overloaded")
    assert "暂时不可用" in msg


def test_unknown_error_keeps_compact_detail() -> None:
    msg = classify_provider_error(content="something weird happened xyz")
    assert "出错" in msg
    assert "something weird happened xyz" in msg


def test_empty_content_still_returns_chinese() -> None:
    msg = classify_provider_error(content="")
    assert "出错" in msg
    # No raw detail tail when there's nothing to show
    assert "详情" not in msg


def test_friendly_error_message_reads_response_fields() -> None:
    response = SimpleNamespace(
        content="rate limit exceeded",
        error_status_code=429,
        error_code="rate_limit_exceeded",
        retry_after_s=5,
    )
    msg = friendly_error_message(response)
    assert "限流" in msg
    assert "5" in msg
