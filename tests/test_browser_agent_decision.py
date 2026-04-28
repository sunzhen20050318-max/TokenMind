"""Tests for the LLM decision parser + retry loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pytest

from tokenmind.browser_agent.decision import (
    Decision,
    DecisionMaker,
    DecisionParseError,
    parse_decision,
)


# ── parse_decision ──────────────────────────────────────────────────────────


def test_parse_clean_json() -> None:
    raw = '{"thinking":"看到搜索框","action":"fill","args":{"selector":"@e1","text":"hi"}}'
    decision = parse_decision(raw)
    assert decision.action == "fill"
    assert decision.args == {"selector": "@e1", "text": "hi"}
    assert decision.thinking == "看到搜索框"
    assert not decision.is_finish


def test_parse_strips_markdown_fence() -> None:
    raw = '```json\n{"action":"finish","args":{"summary":"done"}}\n```'
    decision = parse_decision(raw)
    assert decision.is_finish
    assert decision.args == {"summary": "done"}


def test_parse_extracts_object_amid_prose() -> None:
    raw = '思考：先点开链接。\n{"action":"click","args":{"selector":"@e3"}}\n'
    decision = parse_decision(raw)
    assert decision.action == "click"
    assert decision.args == {"selector": "@e3"}


def test_parse_rejects_unknown_action() -> None:
    raw = '{"action":"teleport","args":{}}'
    with pytest.raises(DecisionParseError, match="未知动作"):
        parse_decision(raw)


def test_parse_rejects_missing_required_arg() -> None:
    raw = '{"action":"fill","args":{"selector":"@e1"}}'
    with pytest.raises(DecisionParseError, match="缺少参数"):
        parse_decision(raw)


def test_parse_allows_extra_args() -> None:
    raw = '{"action":"click","args":{"selector":"@e1","extra":"ignored"}}'
    decision = parse_decision(raw)
    assert decision.args["selector"] == "@e1"
    assert decision.args["extra"] == "ignored"


def test_parse_rejects_when_no_json_present() -> None:
    with pytest.raises(DecisionParseError, match="找不到 JSON"):
        parse_decision("just prose, no json here")


def test_parse_rejects_malformed_json() -> None:
    with pytest.raises(DecisionParseError, match="JSON 解析失败"):
        parse_decision('{"action":"click", "args":{')


def test_parse_no_args_action_works_without_args_key() -> None:
    decision = parse_decision('{"action":"reload"}')
    assert decision.action == "reload"
    assert decision.args == {}


# ── DecisionMaker (with fake provider) ──────────────────────────────────────


@dataclass
class _FakeResponse:
    content: Optional[str]


class _ScriptedProvider:
    """Returns a queued list of LLM responses, in order."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict[str, Any]]] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> _FakeResponse:
        self.calls.append(messages)
        if not self.responses:
            return _FakeResponse(content="")
        return _FakeResponse(content=self.responses.pop(0))


@pytest.mark.asyncio
async def test_decide_returns_first_valid_response() -> None:
    provider = _ScriptedProvider([
        '{"action":"fill","args":{"selector":"@e1","text":"hi"}}',
    ])
    maker = DecisionMaker(provider)
    decision = await maker.decide(instruction="搜索 hi", snapshot="...", history=[])
    assert decision.action == "fill"
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_decide_retries_on_parse_failure() -> None:
    provider = _ScriptedProvider([
        "完全不是 JSON",
        "```json\nnot quite\n```",
        '{"action":"click","args":{"selector":"@e2"}}',
    ])
    maker = DecisionMaker(provider, max_retries=3)
    decision = await maker.decide(instruction="x", snapshot="s", history=[])
    assert decision.action == "click"
    assert len(provider.calls) == 3
    # Third attempt's user message should mention the prior error.
    third_user = provider.calls[-1][-1]["content"]
    assert "上一次输出格式错误" in third_user


@pytest.mark.asyncio
async def test_decide_raises_after_exhausting_retries() -> None:
    provider = _ScriptedProvider(["bad", "still bad", "really bad"])
    maker = DecisionMaker(provider, max_retries=3)
    with pytest.raises(DecisionParseError, match="3 次重试"):
        await maker.decide(instruction="x", snapshot="s", history=[])
    assert len(provider.calls) == 3


@pytest.mark.asyncio
async def test_decide_includes_history_in_prompt() -> None:
    provider = _ScriptedProvider([
        '{"action":"finish","args":{"summary":"completed"}}',
    ])
    maker = DecisionMaker(provider)
    history = [
        {"action": "open", "args": {"url": "https://x"}, "observation": "loaded", "success": True},
        {"action": "click", "args": {"selector": "@e1"}, "observation": "navigated", "success": True},
    ]
    await maker.decide(instruction="x", snapshot="s", history=history)
    user_msg = provider.calls[0][-1]["content"]
    assert "已执行的步骤" in user_msg
    assert "open" in user_msg and "click" in user_msg


@pytest.mark.asyncio
async def test_decide_passes_model_override_to_provider() -> None:
    provider = _ScriptedProvider(['{"action":"reload"}'])
    maker = DecisionMaker(provider, model="anthropic/claude-haiku-4-5")

    captured = {}

    async def spy_chat(messages, tools=None, model=None, max_tokens=4096,
                       temperature=0.7, reasoning_effort=None, tool_choice=None):
        captured["model"] = model
        captured["temperature"] = temperature
        return _FakeResponse(content='{"action":"reload"}')

    provider.chat = spy_chat  # type: ignore[assignment]
    await maker.decide(instruction="x", snapshot="s", history=[])
    assert captured["model"] == "anthropic/claude-haiku-4-5"
    assert captured["temperature"] == 0.2  # decision uses low temp by default
