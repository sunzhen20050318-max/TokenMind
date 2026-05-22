"""OpenAI-compatible provider for direct and gateway-style backends."""

from __future__ import annotations

import os
import re
import uuid
from typing import Any

import json_repair
from loguru import logger
from openai import AsyncOpenAI

from tokenmind.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from tokenmind.providers.registry import ProviderSpec
from tokenmind.providers.usage import build_usage

# Default request timeout for every OpenAI-compatible call. The OpenAI SDK
# defaults to 600s, which is far too long for typical chat completions — a
# stalled domestic provider would wedge the agent for ten minutes. 120s
# accommodates long thinking-mode responses while still failing fast on a
# genuinely dead connection. Override via ``TOKENMIND_OPENAI_COMPAT_TIMEOUT_S``.
_OPENAI_COMPAT_REQUEST_TIMEOUT_S = 120.0


def _openai_compat_timeout_s() -> float:
    raw = os.environ.get("TOKENMIND_OPENAI_COMPAT_TIMEOUT_S")
    if not raw or not raw.strip():
        return _OPENAI_COMPAT_REQUEST_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "Ignoring invalid TOKENMIND_OPENAI_COMPAT_TIMEOUT_S={!r}; using {}s",
            raw, _OPENAI_COMPAT_REQUEST_TIMEOUT_S,
        )
        return _OPENAI_COMPAT_REQUEST_TIMEOUT_S
    if value <= 0:
        logger.warning(
            "Ignoring non-positive TOKENMIND_OPENAI_COMPAT_TIMEOUT_S={!r}; using {}s",
            raw, _OPENAI_COMPAT_REQUEST_TIMEOUT_S,
        )
        return _OPENAI_COMPAT_REQUEST_TIMEOUT_S
    return value


# Some "OpenAI-compatible" gateways (notably Xiaomi MiMo) advertise tool
# calling but actually emit it as XML embedded in `content` instead of the
# OpenAI-standard structured `tool_calls` field. Example:
#
#   <tool_call>
#   <function=generate_image>
#   <parameter=prompt>...</parameter>
#   <parameter=size>1024x1024</parameter>
#   </function>
#   </tool_call>
#
# Across MiMo regions/tiers the tag names and attribute syntax vary
# (``<tool_use>``/``<function_call>`` wrappers; ``<function name="x">``
# instead of ``<function=x>``; sometimes the wrapper is dropped entirely
# and only ``<function...>`` survives; truncated responses may omit the
# closing ``</tool_call>``). The patterns below cover all observed
# variants — compiled once at import so the standard structured-tool_calls
# path stays free of runtime cost.
_XML_TOOL_CALL_OPEN_RE = re.compile(
    r"<(?:tool_call|tool_use|function_call|tool)(?:\s[^>]*)?>",
    re.IGNORECASE,
)
_XML_TOOL_CALL_BLOCK_RE = re.compile(
    r"<(?P<tag>tool_call|tool_use|function_call|tool)(?:\s[^>]*)?>"
    r"\s*(?P<body>.*?)\s*"
    r"(?:</(?P=tag)>|\Z)",
    re.DOTALL | re.IGNORECASE,
)
# Two function-name syntaxes seen in the wild:
#   <function=name>...</function>
#   <function name="name">...</function>
_XML_FUNCTION_RE = re.compile(
    r"<function"
    r"(?:\s*=\s*(?P<name_eq>[A-Za-z0-9_.\-]+)"
    r"|\s+name\s*=\s*[\"'](?P<name_attr>[A-Za-z0-9_.\-]+)[\"'])"
    r"\s*>\s*(?P<args>.*?)\s*(?:</function>|\Z)",
    re.DOTALL | re.IGNORECASE,
)
# Parameter name syntaxes:
#   <parameter=key>value</parameter>
#   <parameter name="key">value</parameter>
_XML_PARAMETER_RE = re.compile(
    r"<parameter"
    r"(?:\s*=\s*(?P<key_eq>[A-Za-z0-9_.\-]+)"
    r"|\s+name\s*=\s*[\"'](?P<key_attr>[A-Za-z0-9_.\-]+)[\"'])"
    r"\s*>\s*(?P<value>.*?)\s*(?:</parameter>|\Z)",
    re.DOTALL | re.IGNORECASE,
)


def _coerce_param_value(raw: str) -> Any:
    """Try to JSON-decode a parameter value; fall back to the raw string."""
    text = raw.strip()
    if not text:
        return text
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    if text.lower() == "null":
        return None
    # Numeric? — try int then float so 1024 stays int, 0.5 stays float.
    try:
        if "." not in text and "e" not in text.lower():
            return int(text)
        return float(text)
    except ValueError:
        pass
    # Looks like JSON object/array? Repair-parse it.
    if text[:1] in "{[":
        try:
            return json_repair.loads(text)
        except Exception:  # noqa: BLE001
            return text
    return text


def _looks_like_xml_tool_call(content: str) -> bool:
    """Cheap pre-check: does ``content`` carry any of the known wrapper or
    function-call tag prefixes? Anything truthy here means we should try
    the full parse before returning."""
    if not content:
        return False
    lowered = content.lower()
    return (
        "<tool_call" in lowered
        or "<tool_use" in lowered
        or "<function_call" in lowered
        or "<function=" in lowered
        or "<function " in lowered
    )


def _parse_function_call(fn_match: "re.Match[str]") -> ToolCallRequest:
    name = (fn_match.group("name_eq") or fn_match.group("name_attr") or "").strip()
    arg_text = fn_match.group("args") or ""
    arguments: dict[str, Any] = {}
    for param_match in _XML_PARAMETER_RE.finditer(arg_text):
        key = (param_match.group("key_eq") or param_match.group("key_attr") or "").strip()
        if not key:
            continue
        arguments[key] = _coerce_param_value(param_match.group("value") or "")
    return ToolCallRequest(
        id=f"call_{uuid.uuid4().hex[:12]}",
        name=name,
        arguments=arguments,
    )


def _extract_xml_tool_calls(content: str) -> tuple[list[ToolCallRequest], str]:
    """Pull XML-style tool calls out of ``content``.

    Returns the parsed :class:`ToolCallRequest` list and the residual text
    with all matched tool-call blocks stripped. Empty list when nothing
    matches — caller can treat as "no fallback needed".

    Strategy:
    1. Prefer wrapped form (``<tool_call>...</tool_call>`` and aliases).
    2. Fall back to bare ``<function=...>...</function>`` blocks for
       gateways that drop the wrapper.
    3. Tolerate a missing closing tag (truncated MiMo response) so the
       user-facing chat doesn't leak raw XML in that edge case either.
    """
    if not _looks_like_xml_tool_call(content):
        return [], content

    parsed: list[ToolCallRequest] = []
    cleaned = content
    matched_wrapper = False

    for wrapper_match in _XML_TOOL_CALL_BLOCK_RE.finditer(content):
        matched_wrapper = True
        body = wrapper_match.group("body") or ""
        for fn_match in _XML_FUNCTION_RE.finditer(body):
            call = _parse_function_call(fn_match)
            if call.name:
                parsed.append(call)
        cleaned = cleaned.replace(wrapper_match.group(0), "", 1)

    if not matched_wrapper:
        # No wrapper tag — try bare <function=...>...</function> blocks.
        for fn_match in _XML_FUNCTION_RE.finditer(content):
            call = _parse_function_call(fn_match)
            if call.name:
                parsed.append(call)
                cleaned = cleaned.replace(fn_match.group(0), "", 1)

    if not parsed and _looks_like_xml_tool_call(content):
        # Markers were present but parsing failed — log a diagnostic so
        # operators chasing a "tool args got dumped into chat" report can
        # see exactly what shape the gateway produced. Truncate to keep
        # logs sane on huge responses.
        preview = content[:500].replace("\n", "\\n")
        logger.warning(
            "XML tool-call markers detected but no calls extracted "
            "(likely a new gateway dialect). Preview: {}",
            preview,
        )

    return parsed, cleaned.strip()

_OPENAI_MSG_KEYS = frozenset(
    {"role", "content", "tool_calls", "tool_call_id", "name", "reasoning_content"}
)


def _read_extra(obj: Any, key: str) -> Any:
    """Read a field from SDK objects while preserving unknown provider extras."""
    value = getattr(obj, key, None)
    if value is not None:
        return value
    extra = getattr(obj, "model_extra", None)
    if isinstance(extra, dict):
        return extra.get(key)
    return None


def _normalize_openai_usage(usage_obj: Any) -> dict[str, int]:
    """Convert an OpenAI-style usage object into the unified usage dict.

    Handles three subtly different shapes:
    - Vanilla OpenAI: prompt_tokens / completion_tokens with optional
      `prompt_tokens_details.cached_tokens` and
      `completion_tokens_details.reasoning_tokens`.
    - DeepSeek: extra `prompt_cache_hit_tokens` field; cached count takes
      precedence over OpenAI's nested form when present.
    - Other gateways (Qwen, GLM, Moonshot, OpenRouter, SiliconFlow): may
      omit detail subsets entirely; we degrade gracefully to zero.
    """
    prompt_tokens = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage_obj, "completion_tokens", 0) or 0)

    cached = int(_read_extra(usage_obj, "prompt_cache_hit_tokens") or 0)
    if not cached:
        details = getattr(usage_obj, "prompt_tokens_details", None) or _read_extra(
            usage_obj, "prompt_tokens_details"
        )
        if details is not None:
            cached = int(getattr(details, "cached_tokens", 0) or 0)
            if not cached and isinstance(details, dict):
                cached = int(details.get("cached_tokens") or 0)

    reasoning = 0
    completion_details = getattr(usage_obj, "completion_tokens_details", None) or _read_extra(
        usage_obj, "completion_tokens_details"
    )
    if completion_details is not None:
        reasoning = int(getattr(completion_details, "reasoning_tokens", 0) or 0)
        if not reasoning and isinstance(completion_details, dict):
            reasoning = int(completion_details.get("reasoning_tokens") or 0)

    cached = min(cached, prompt_tokens)
    return build_usage(
        input_tokens=prompt_tokens - cached,
        cached_input_tokens=cached,
        output_tokens=completion_tokens,
        reasoning_tokens=reasoning,
    )


class OpenAICompatProvider(LLMProvider):
    """Provider for OpenAI-compatible APIs and gateways."""

    @property
    def provider_name(self) -> str:
        return self.spec.name if self.spec else "openai_compat"

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "default",
        extra_headers: dict[str, str] | None = None,
        spec: ProviderSpec | None = None,
    ):
        resolved_base = api_base or (spec.default_api_base if spec and spec.default_api_base else None)
        super().__init__(api_key, resolved_base)
        self.default_model = default_model
        self.spec = spec

        default_headers = {
            "x-session-affinity": uuid.uuid4().hex,
            **(extra_headers or {}),
        }

        client_kwargs: dict[str, Any] = {
            "api_key": api_key or ("dummy" if spec and spec.is_oauth else "no-key"),
            "default_headers": default_headers,
            "timeout": _openai_compat_timeout_s(),
        }
        if resolved_base:
            client_kwargs["base_url"] = resolved_base
        self._client = AsyncOpenAI(**client_kwargs)

    @staticmethod
    def _normalize_prefix(value: str) -> str:
        return value.lower().replace("-", "_")

    def _strip_explicit_provider_prefix(self, model: str) -> str:
        """Strip `provider/model` when the provider is explicit in the model name."""
        if not self.spec or self.spec.is_gateway or "/" not in model:
            return model
        prefix, remainder = model.split("/", 1)
        if self._normalize_prefix(prefix) == self.spec.name:
            return remainder
        return model

    def _resolve_model(self, model: str) -> str:
        resolved = self._strip_explicit_provider_prefix(model)
        if self.spec and self.spec.strip_model_prefix and "/" in resolved:
            resolved = resolved.split("/", 1)[1]
        return resolved

    # DeepSeek thinking-mode model name fragments. The chat model
    # (``deepseek-chat`` / V3) tolerates mixed history, so we only trigger
    # the cleanup for the reasoner variants.
    _DEEPSEEK_THINKING_PATTERNS = ("r1", "reasoner", "v4")

    def _requires_reasoning_echo(self, resolved_model: str) -> bool:
        """True if this provider rejects history that mixes thinking and
        non-thinking turns.

        - **MiMo** (RL / VL-RL): strict — *every* assistant turn must carry
          `reasoning_content`. Trigger cleanup unconditionally. If the user
          had a non-thinking conversation before switching to MiMo, the
          legacy turns get stripped (better than a hard 400).
        - **DeepSeek** (R1 / reasoner / V4): triggers cleanup for the
          reasoner-family models. ``deepseek-chat`` (V3) is unaffected, so
          mixing chat and reasoner models in one session is supported —
          legacy chat-only turns are stripped only when a reasoner model
          is actually being called.
        """
        if not self.spec:
            return False
        if self.spec.name == "mimo":
            return True
        if self.spec.name == "deepseek":
            name = resolved_model.lower()
            return any(p in name for p in self._DEEPSEEK_THINKING_PATTERNS)
        return False

    @staticmethod
    def _backfill_reasoning_content(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Inject ``reasoning_content=""`` on any assistant message missing it.

        Some thinking-mode APIs (DeepSeek R1 / V4 / reasoner, MiMo) reject
        history that contains assistant messages without ``reasoning_content``
        — even on turns that had no tool calls. This happens when a session
        was started with a non-thinking model (or without ``reasoning_effort``)
        and the user later switches to a thinking model mid-session.

        Previously we *dropped* the offending turns, which truncated the
        agent's memory of earlier work. Backfilling an empty string keeps
        the history intact and is semantically equivalent ("no thinking
        happened on this turn") from the API's perspective.

        Returns a new list. Assistant messages needing the backfill are
        shallow-copied so the caller's session storage is not mutated.
        """
        patched = 0
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.get("role") == "assistant" and "reasoning_content" not in msg:
                copy = dict(msg)
                copy["reasoning_content"] = ""
                result.append(copy)
                patched += 1
            else:
                result.append(msg)
        if patched:
            logger.debug(
                "Backfilled reasoning_content='' on {} legacy assistant message(s)",
                patched,
            )
        return result

    def _apply_model_overrides(self, resolved_model: str, kwargs: dict[str, Any]) -> None:
        if not self.spec:
            return
        model_lower = resolved_model.lower()
        for pattern, overrides in self.spec.model_overrides:
            if pattern in model_lower:
                kwargs.update(overrides)
                return

    def _supports_cache_control(self, resolved_model: str) -> bool:
        if not self.spec or not self.spec.supports_prompt_caching:
            return False
        patterns = tuple(p.lower() for p in self.spec.prompt_caching_model_patterns if p)
        if not patterns:
            return True
        model_lower = resolved_model.lower()
        return any(pattern in model_lower for pattern in patterns)

    @staticmethod
    def _apply_cache_control(
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
        new_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                content = msg.get("content")
                if isinstance(content, str):
                    new_content = [
                        {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
                    ]
                elif isinstance(content, list) and content:
                    new_content = list(content)
                    if isinstance(new_content[-1], dict):
                        new_content[-1] = {
                            **new_content[-1],
                            "cache_control": {"type": "ephemeral"},
                        }
                else:
                    new_content = content
                new_messages.append({**msg, "content": new_content})
            else:
                new_messages.append(msg)

        new_tools = tools
        if tools:
            new_tools = list(tools)
            if isinstance(new_tools[-1], dict):
                new_tools[-1] = {
                    **new_tools[-1],
                    "cache_control": {"type": "ephemeral"},
                }

        return new_messages, new_tools

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        resolved_model = self._resolve_model(model or self.default_model)
        if self._supports_cache_control(resolved_model):
            messages, tools = self._apply_cache_control(messages, tools)
        if self._requires_reasoning_echo(resolved_model):
            messages = self._backfill_reasoning_content(messages)

        kwargs: dict[str, Any] = {
            "model": resolved_model,
            "messages": self._sanitize_request_messages(
                self._sanitize_empty_content(messages),
                _OPENAI_MSG_KEYS,
            ),
            "max_tokens": max(1, max_tokens),
            "temperature": temperature,
        }

        self._apply_model_overrides(resolved_model, kwargs)

        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"

        try:
            response = await self._client.chat.completions.create(**kwargs)
            return self._parse_response(response)
        except Exception as exc:
            body = getattr(exc, "doc", None) or getattr(getattr(exc, "response", None), "text", None)
            if body and str(body).strip():
                return LLMResponse(content=f"Error: {str(body).strip()[:500]}", finish_reason="error")
            return LLMResponse(content=f"Error calling LLM: {exc}", finish_reason="error")

    def _parse_response(self, response: Any) -> LLMResponse:
        choices = list(getattr(response, "choices", []) or [])
        if not choices:
            return LLMResponse(
                content=(
                    "Error: API returned empty choices. "
                    "This may indicate a temporary service issue or an invalid model response."
                ),
                finish_reason="error",
            )

        primary = choices[0]
        message = primary.message
        finish_reason = primary.finish_reason or "stop"
        content = getattr(message, "content", None)

        raw_tool_calls: list[Any] = []
        for choice in choices:
            msg = choice.message
            if getattr(msg, "tool_calls", None):
                raw_tool_calls.extend(msg.tool_calls)
                if choice.finish_reason in ("tool_calls", "stop"):
                    finish_reason = choice.finish_reason
            if not content and getattr(msg, "content", None):
                content = msg.content

        tool_calls: list[ToolCallRequest] = []
        for tool_call in raw_tool_calls:
            arguments = tool_call.function.arguments
            if isinstance(arguments, str):
                arguments = json_repair.loads(arguments)
            tool_calls.append(
                ToolCallRequest(
                    id=tool_call.id,
                    name=tool_call.function.name,
                    arguments=arguments,
                    provider_specific_fields=_read_extra(tool_call, "provider_specific_fields") or None,
                    function_provider_specific_fields=(
                        _read_extra(tool_call.function, "provider_specific_fields") or None
                    ),
                )
            )

        # Fallback: gateways like Xiaomi MiMo emit tool calls as XML in the
        # content field instead of the structured `tool_calls`. Only kicks
        # in when the standard field is empty AND content looks like it has
        # a `<tool_call>` block, so the standard path stays untouched.
        if not tool_calls and isinstance(content, str):
            xml_calls, cleaned_content = _extract_xml_tool_calls(content)
            if xml_calls:
                tool_calls = xml_calls
                content = cleaned_content or None
                if finish_reason == "stop":
                    finish_reason = "tool_calls"

        usage_obj = getattr(response, "usage", None)
        usage: dict[str, int] = {}
        if usage_obj:
            usage = _normalize_openai_usage(usage_obj)

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            reasoning_content=_read_extra(message, "reasoning_content") or None,
            thinking_blocks=_read_extra(message, "thinking_blocks") or None,
        )

    def get_default_model(self) -> str:
        return self.default_model
