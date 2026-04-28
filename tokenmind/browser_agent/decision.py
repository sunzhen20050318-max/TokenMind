"""LLM-driven action decision for the browser agent.

The DecisionMaker is the ReAct "brain": given the task, recent steps and the
current page snapshot, it asks the configured LLM provider for the next
action and returns a parsed :class:`Decision`.

JSON parsing is strict — if the model returns prose, markdown fences, or
malformed JSON we retry up to ``max_retries`` times, feeding the parse error
back so the model self-corrects.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from tokenmind.browser_agent.prompts import (
    ACTION_SCHEMAS,
    SYSTEM_PROMPT,
    build_user_message,
)

logger = logging.getLogger("tokenmind.browser_agent.decision")

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class _Provider(Protocol):
    """Minimal subset of LLMProvider that DecisionMaker depends on."""

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> Any: ...


@dataclass
class Decision:
    """Parsed next-action returned by the LLM."""

    action: str
    args: dict[str, Any] = field(default_factory=dict)
    thinking: Optional[str] = None
    raw: Optional[str] = None

    @property
    def is_finish(self) -> bool:
        return self.action == "finish"


class DecisionParseError(ValueError):
    """Raised when the LLM output cannot be parsed even after retries."""


def _strip_fences(text: str) -> str:
    """Remove ```json ... ``` fences if the model added them anyway."""
    cleaned = _JSON_FENCE_RE.sub("", text.strip())
    return cleaned.strip()


def _extract_first_json_object(text: str) -> Optional[str]:
    """Return the first balanced ``{...}`` substring, or None."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def parse_decision(raw: str) -> Decision:
    """Parse a single LLM response into a :class:`Decision`.

    Tolerates markdown fences and trailing/leading prose by extracting the
    first balanced JSON object. Raises :class:`DecisionParseError` when the
    payload doesn't fit the expected schema.
    """
    cleaned = _strip_fences(raw or "")
    candidate = cleaned if cleaned.startswith("{") else _extract_first_json_object(cleaned)
    if not candidate:
        raise DecisionParseError("响应中找不到 JSON 对象")

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise DecisionParseError(f"JSON 解析失败：{exc.msg}") from exc

    if not isinstance(payload, dict):
        raise DecisionParseError("JSON 顶层必须是对象")

    action = payload.get("action")
    if not isinstance(action, str) or not action:
        raise DecisionParseError("缺少 action 字段或类型错误")
    if action not in ACTION_SCHEMAS:
        raise DecisionParseError(
            f"未知动作 '{action}'，允许的动作：{', '.join(ACTION_SCHEMAS)}"
        )

    args = payload.get("args", {}) or {}
    if not isinstance(args, dict):
        raise DecisionParseError("args 必须是对象")

    # Spot-check required arg keys based on the schema. We only flag *missing*
    # keys — extra keys are tolerated to keep the loop forgiving.
    schema_args = ACTION_SCHEMAS[action]["args"]
    required = {key for key, hint in schema_args.items() if "(optional)" not in hint}
    missing = required - set(args.keys())
    if missing:
        raise DecisionParseError(
            f"动作 '{action}' 缺少参数：{', '.join(sorted(missing))}"
        )

    thinking = payload.get("thinking")
    if thinking is not None and not isinstance(thinking, str):
        thinking = str(thinking)

    return Decision(action=action, args=args, thinking=thinking, raw=raw)


class DecisionMaker:
    """Drives the LLM call for the ReAct loop with JSON-retry semantics."""

    def __init__(
        self,
        provider: _Provider,
        *,
        model: Optional[str] = None,
        max_retries: int = 3,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> None:
        self.provider = provider
        self.model = model
        self.max_retries = max_retries
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def decide(
        self,
        *,
        instruction: str,
        snapshot: str,
        history: list[dict[str, Any]],
    ) -> Decision:
        """Ask the LLM for the next action; retry on malformed output."""
        last_error: Optional[str] = None
        last_raw: Optional[str] = None

        for attempt in range(1, self.max_retries + 1):
            user_message = build_user_message(
                instruction=instruction,
                snapshot=snapshot,
                history=history,
                last_error=last_error,
            )
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]
            try:
                response = await self.provider.chat(
                    messages=messages,
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
            except Exception as exc:  # pragma: no cover - provider error path
                logger.exception("decision LLM call failed: %s", exc)
                raise DecisionParseError(f"LLM 调用失败：{exc}") from exc

            raw = (getattr(response, "content", None) or "").strip()
            last_raw = raw
            if not raw:
                last_error = "上一次响应为空"
                continue

            try:
                decision = parse_decision(raw)
            except DecisionParseError as exc:
                last_error = str(exc)
                logger.warning(
                    "decision parse failed (attempt %d/%d): %s",
                    attempt,
                    self.max_retries,
                    last_error,
                )
                continue

            return decision

        raise DecisionParseError(
            f"LLM 输出在 {self.max_retries} 次重试后仍无法解析。最后错误：{last_error}；"
            f"原始内容片段：{(last_raw or '')[:200]!r}"
        )
