"""OpenAI-compatible provider for direct and gateway-style backends."""

from __future__ import annotations

import re
import uuid
from typing import Any

import json_repair
from loguru import logger
from openai import AsyncOpenAI

from tokenmind.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from tokenmind.providers.registry import ProviderSpec


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
# The patterns below recover those calls so the agent loop can still execute
# them. Compiled once at import; no runtime cost on the (typical) standard path.
_XML_TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*(?P<body>.*?)\s*</tool_call>",
    re.DOTALL | re.IGNORECASE,
)
_XML_FUNCTION_RE = re.compile(
    r"<function\s*=\s*(?P<name>[A-Za-z0-9_.\-]+)\s*>\s*(?P<args>.*?)\s*</function>",
    re.DOTALL | re.IGNORECASE,
)
_XML_PARAMETER_RE = re.compile(
    r"<parameter\s*=\s*(?P<key>[A-Za-z0-9_.\-]+)\s*>\s*(?P<value>.*?)\s*</parameter>",
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


def _extract_xml_tool_calls(content: str) -> tuple[list[ToolCallRequest], str]:
    """Pull XML-style tool calls out of ``content``.

    Returns the parsed :class:`ToolCallRequest` list and the residual text
    with all matched ``<tool_call>`` blocks stripped. Empty list when
    nothing matches — caller can treat as "no fallback needed".
    """
    if not content or "<tool_call" not in content.lower():
        return [], content

    parsed: list[ToolCallRequest] = []
    cleaned = content

    for tool_call_match in _XML_TOOL_CALL_RE.finditer(content):
        body = tool_call_match.group("body")
        for fn_match in _XML_FUNCTION_RE.finditer(body):
            name = fn_match.group("name").strip()
            arg_text = fn_match.group("args")
            arguments: dict[str, Any] = {}
            for param_match in _XML_PARAMETER_RE.finditer(arg_text):
                key = param_match.group("key").strip()
                arguments[key] = _coerce_param_value(param_match.group("value"))
            parsed.append(
                ToolCallRequest(
                    id=f"call_{uuid.uuid4().hex[:12]}",
                    name=name,
                    arguments=arguments,
                )
            )
        cleaned = cleaned.replace(tool_call_match.group(0), "", 1)

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


class OpenAICompatProvider(LLMProvider):
    """Provider for OpenAI-compatible APIs and gateways."""

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

    def _requires_reasoning_echo(self, resolved_model: str) -> bool:
        if not self.spec or self.spec.name != "deepseek":
            return False
        model_lower = resolved_model.lower()
        return any(marker in model_lower for marker in ("reasoner", "thinking", "v4"))

    @staticmethod
    def _drop_legacy_tool_turns_without_reasoning(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove old assistant/tool turns that DeepSeek thinking mode cannot replay."""
        repaired: list[dict[str, Any]] = []
        skip_tool_ids: set[str] = set()
        dropped = 0

        for msg in messages:
            if msg.get("role") == "tool" and msg.get("tool_call_id") in skip_tool_ids:
                dropped += 1
                continue

            if msg.get("role") == "assistant" and msg.get("tool_calls") and not msg.get("reasoning_content"):
                for tool_call in msg.get("tool_calls") or []:
                    if isinstance(tool_call, dict) and tool_call.get("id"):
                        skip_tool_ids.add(str(tool_call["id"]))
                dropped += 1
                continue

            repaired.append(msg)

        if dropped:
            logger.warning(
                "Dropped {} legacy DeepSeek thinking message(s) without reasoning_content",
                dropped,
            )
        return repaired

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
            messages = self._drop_legacy_tool_turns_without_reasoning(messages)

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
        usage = {}
        if usage_obj:
            usage = {
                "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0),
                "completion_tokens": getattr(usage_obj, "completion_tokens", 0),
                "total_tokens": getattr(usage_obj, "total_tokens", 0),
            }

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
