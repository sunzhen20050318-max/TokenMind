"""OpenAI-compatible provider for direct and gateway-style backends."""

from __future__ import annotations

import uuid
from typing import Any

import json_repair
from openai import AsyncOpenAI

from sun_agent.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from sun_agent.providers.registry import ProviderSpec

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
