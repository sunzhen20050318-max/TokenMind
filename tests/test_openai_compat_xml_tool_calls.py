"""Tests for the XML tool-call fallback parser used with non-OpenAI-strict
gateways like Xiaomi MiMo."""

from __future__ import annotations

from tokenmind.providers.openai_compat_provider import (
    _coerce_param_value,
    _extract_xml_tool_calls,
)


def test_extract_returns_empty_when_no_tool_call_block() -> None:
    calls, residual = _extract_xml_tool_calls("just a plain reply")
    assert calls == []
    assert residual == "just a plain reply"


def test_extracts_single_function_call() -> None:
    raw = (
        "<tool_call>\n"
        "<function=generate_image>\n"
        "<parameter=prompt>A cat</parameter>\n"
        "<parameter=size>1024x1024</parameter>\n"
        "</function>\n"
        "</tool_call>"
    )
    calls, residual = _extract_xml_tool_calls(raw)
    assert len(calls) == 1
    call = calls[0]
    assert call.name == "generate_image"
    assert call.arguments == {"prompt": "A cat", "size": "1024x1024"}
    assert residual == ""


def test_residual_keeps_surrounding_text() -> None:
    raw = (
        "好的，我来帮你生成。\n"
        "<tool_call>\n"
        "<function=generate_image>\n"
        "<parameter=prompt>A dog</parameter>\n"
        "</function>\n"
        "</tool_call>\n"
        "请稍等。"
    )
    calls, residual = _extract_xml_tool_calls(raw)
    assert len(calls) == 1
    assert "好的" in residual
    assert "请稍等" in residual
    assert "<tool_call>" not in residual


def test_extracts_multiple_tool_calls() -> None:
    raw = (
        "<tool_call>\n"
        "<function=web_search>\n"
        "<parameter=query>foo</parameter>\n"
        "</function>\n"
        "</tool_call>\n"
        "<tool_call>\n"
        "<function=read_file>\n"
        "<parameter=path>/tmp/x</parameter>\n"
        "</function>\n"
        "</tool_call>"
    )
    calls, _ = _extract_xml_tool_calls(raw)
    assert [c.name for c in calls] == ["web_search", "read_file"]
    assert calls[0].arguments == {"query": "foo"}
    assert calls[1].arguments == {"path": "/tmp/x"}


def test_coerces_numeric_and_boolean_params() -> None:
    raw = (
        "<tool_call>\n"
        "<function=run>\n"
        "<parameter=count>5</parameter>\n"
        "<parameter=ratio>0.75</parameter>\n"
        "<parameter=enabled>true</parameter>\n"
        "<parameter=skip>false</parameter>\n"
        "<parameter=note>null</parameter>\n"
        "</function>\n"
        "</tool_call>"
    )
    calls, _ = _extract_xml_tool_calls(raw)
    assert calls[0].arguments == {
        "count": 5,
        "ratio": 0.75,
        "enabled": True,
        "skip": False,
        "note": None,
    }


def test_param_value_falls_back_to_string_for_non_numeric() -> None:
    assert _coerce_param_value("hello world") == "hello world"
    assert _coerce_param_value("  trimmed  ") == "trimmed"


def test_extracts_json_object_param() -> None:
    raw = (
        "<tool_call>\n"
        "<function=update>\n"
        "<parameter=payload>{\"key\":\"value\",\"n\":3}</parameter>\n"
        "</function>\n"
        "</tool_call>"
    )
    calls, _ = _extract_xml_tool_calls(raw)
    assert calls[0].arguments == {"payload": {"key": "value", "n": 3}}


def test_each_call_gets_unique_id() -> None:
    raw = (
        "<tool_call><function=a><parameter=x>1</parameter></function></tool_call>"
        "<tool_call><function=a><parameter=x>2</parameter></function></tool_call>"
    )
    calls, _ = _extract_xml_tool_calls(raw)
    assert calls[0].id != calls[1].id
    assert all(c.id.startswith("call_") for c in calls)
