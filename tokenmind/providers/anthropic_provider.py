"""Native Anthropic Messages API provider."""

from __future__ import annotations

import json
import uuid
from typing import Any
from urllib.parse import urljoin

import httpx
import json_repair

from tokenmind.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from tokenmind.providers.usage import build_usage

_ANTHROPIC_VERSION = "2023-06-01"
_INTERLEAVED_THINKING_BETA = "interleaved-thinking-2025-05-14"
_REASONING_BUDGETS = {
    "low": 1024,
    "medium": 4096,
    "high": 8192,
}


class AnthropicProvider(LLMProvider):
    """Anthropic provider using the native Messages API."""

    def __init__(
        self,
        api_key: str = "",
        api_base: str = "https://api.anthropic.com/v1/",
        default_model: str = "anthropic/claude-opus-4-5",
        extra_headers: dict[str, str] | None = None,
    ):
        if not api_key:
            raise ValueError("Anthropic api_key is required")

        resolved_base = api_base or "https://api.anthropic.com/v1/"
        if not resolved_base.endswith("/"):
            resolved_base += "/"

        super().__init__(api_key, resolved_base)
        self.default_model = default_model
        self.extra_headers = extra_headers or {}

    def _normalize_model(self, model: str) -> str:
        if "/" not in model:
            return model
        prefix, remainder = model.split("/", 1)
        if prefix.lower().replace("-", "_") == "anthropic":
            return remainder
        return model

    def _build_headers(self, enable_thinking: bool = False) -> dict[str, str]:
        headers = {
            "content-type": "application/json",
            "x-api-key": self.api_key or "",
            "anthropic-version": _ANTHROPIC_VERSION,
            "x-session-affinity": uuid.uuid4().hex,
            **self.extra_headers,
        }
        if enable_thinking:
            headers["anthropic-beta"] = _INTERLEAVED_THINKING_BETA
        return headers

    def _messages_url(self) -> str:
        return urljoin(self.api_base or "https://api.anthropic.com/v1/", "messages")

    @staticmethod
    def _thinking_enabled(messages: list[dict[str, Any]], reasoning_effort: str | None) -> bool:
        if reasoning_effort:
            return True
        return any(msg.get("thinking_blocks") for msg in messages)

    @staticmethod
    def _thinking_config(reasoning_effort: str | None, max_tokens: int) -> dict[str, Any] | None:
        if not reasoning_effort:
            return None
        if max_tokens <= 1024:
            return None
        budget = _REASONING_BUDGETS.get(reasoning_effort.lower())
        if not budget:
            return None
        budget = max(1024, min(budget, max_tokens - 512))
        if budget >= max_tokens:
            return None
        return {"type": "enabled", "budget_tokens": budget}

    @staticmethod
    def _apply_cache_control(
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
        """Return copies of messages/tools with Anthropic cache_control hints."""
        new_messages: list[dict[str, Any]] = []
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

    @staticmethod
    def _build_text_block(text: str) -> dict[str, Any]:
        return {"type": "text", "text": text}

    @staticmethod
    def _coerce_text(value: Any) -> str:
        if isinstance(value, str):
            return value
        if value is None:
            return ""
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _parse_data_url(url: str) -> tuple[str, str] | None:
        if not url.startswith("data:") or ";base64," not in url:
            return None
        prefix, encoded = url.split(";base64,", 1)
        media_type = prefix[5:] or "application/octet-stream"
        return media_type, encoded

    def _convert_content_block(self, block: dict[str, Any]) -> dict[str, Any] | None:
        block_type = block.get("type")
        if block_type in {"text", "input_text", "output_text"}:
            text = block.get("text")
            if text:
                return {"type": "text", "text": text}
            return None
        if block_type == "image_url":
            image_data = block.get("image_url", {})
            url = image_data.get("url")
            if not isinstance(url, str):
                return None
            parsed = self._parse_data_url(url)
            if not parsed:
                return {
                    "type": "text",
                    "text": "[image omitted: only data URLs are supported for Anthropic history]",
                }
            media_type, encoded = parsed
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": encoded,
                },
            }
        return None

    def _convert_user_content(self, content: Any) -> str | list[dict[str, Any]]:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            blocks = [
                converted
                for item in content
                if isinstance(item, dict)
                for converted in [self._convert_content_block(item)]
                if converted is not None
            ]
            return blocks or ""
        if content is None:
            return ""
        return self._coerce_text(content)

    def _convert_assistant_content(self, message: dict[str, Any]) -> str | list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for thinking in message.get("thinking_blocks") or []:
            if isinstance(thinking, dict):
                blocks.append(dict(thinking))

        content = message.get("content")
        if isinstance(content, str):
            if content:
                blocks.append(self._build_text_block(content))
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    converted = self._convert_content_block(item)
                    if converted is not None:
                        blocks.append(converted)
        elif content is not None:
            blocks.append(self._build_text_block(self._coerce_text(content)))

        for tool_call in message.get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function") or {}
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                arguments = json_repair.loads(arguments)
            blocks.append(
                {
                    "type": "tool_use",
                    "id": tool_call.get("id"),
                    "name": function.get("name"),
                    "input": arguments or {},
                }
            )

        return blocks or ""

    def _extract_system(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str | list[dict[str, Any]] | None, list[dict[str, Any]]]:
        system_blocks: list[dict[str, Any]] = []
        runtime_messages: list[dict[str, Any]] = []

        for message in messages:
            if message.get("role") != "system":
                runtime_messages.append(message)
                continue
            content = message.get("content")
            if isinstance(content, str):
                system_blocks.append(self._build_text_block(content))
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        converted = self._convert_content_block(item)
                        if converted is not None:
                            if "cache_control" in item:
                                converted["cache_control"] = item["cache_control"]
                            system_blocks.append(converted)

        if not system_blocks:
            return None, runtime_messages
        if all(set(block.keys()) == {"type", "text"} for block in system_blocks):
            return "\n\n".join(block["text"] for block in system_blocks if block.get("text")), runtime_messages
        return system_blocks, runtime_messages

    def _convert_messages(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str | list[dict[str, Any]] | None, list[dict[str, Any]]]:
        system, runtime_messages = self._extract_system(self._sanitize_empty_content(messages))
        anthropic_messages: list[dict[str, Any]] = []
        pending_tool_results: list[dict[str, Any]] = []

        def flush_tool_results() -> None:
            nonlocal pending_tool_results
            if pending_tool_results:
                anthropic_messages.append({"role": "user", "content": pending_tool_results})
                pending_tool_results = []

        for message in runtime_messages:
            role = message.get("role")
            if role == "tool":
                pending_tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": message.get("tool_call_id"),
                        "content": self._coerce_text(message.get("content")),
                    }
                )
                continue

            flush_tool_results()
            if role == "user":
                anthropic_messages.append(
                    {"role": "user", "content": self._convert_user_content(message.get("content"))}
                )
            elif role == "assistant":
                anthropic_messages.append(
                    {"role": "assistant", "content": self._convert_assistant_content(message)}
                )

        flush_tool_results()
        return system, anthropic_messages

    @staticmethod
    def _convert_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        converted_tools: list[dict[str, Any]] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            function = tool.get("function") or {}
            converted = {
                "name": function.get("name"),
                "input_schema": function.get("parameters") or {"type": "object", "properties": {}},
            }
            description = function.get("description")
            if description:
                converted["description"] = description
            if "cache_control" in tool:
                converted["cache_control"] = tool["cache_control"]
            converted_tools.append(converted)
        return converted_tools or None

    @staticmethod
    def _convert_tool_choice(tool_choice: str | dict[str, Any] | None) -> dict[str, Any] | None:
        if tool_choice in (None, "auto"):
            return None
        if tool_choice == "required":
            return {"type": "any"}
        if tool_choice == "none":
            return {"type": "none"}
        if isinstance(tool_choice, dict):
            function = tool_choice.get("function") or {}
            name = function.get("name")
            if name:
                return {"type": "tool", "name": name}
        return None

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
        normalized_model = self._normalize_model(model or self.default_model)
        messages, tools = self._apply_cache_control(messages, tools)
        system, anthropic_messages = self._convert_messages(messages)
        converted_tools = self._convert_tools(tools)
        tool_choice_payload = self._convert_tool_choice(tool_choice)
        thinking = self._thinking_config(reasoning_effort, max_tokens)
        enable_thinking = self._thinking_enabled(messages, reasoning_effort)

        payload: dict[str, Any] = {
            "model": normalized_model,
            "max_tokens": max(1, max_tokens),
            "messages": anthropic_messages,
        }
        if system:
            payload["system"] = system
        if converted_tools:
            payload["tools"] = converted_tools
        if tool_choice_payload:
            payload["tool_choice"] = tool_choice_payload
        if thinking:
            payload["thinking"] = thinking
        else:
            payload["temperature"] = temperature

        try:
            async with httpx.AsyncClient(timeout=60.0, verify=True) as client:
                response = await client.post(
                    self._messages_url(),
                    headers=self._build_headers(enable_thinking=enable_thinking),
                    json=payload,
                )
                if response.status_code != 200:
                    return LLMResponse(
                        content=f"Anthropic API Error {response.status_code}: {response.text}",
                        finish_reason="error",
                    )
                return self._parse_response(response.json())
        except Exception as exc:
            return LLMResponse(
                content=f"Error calling Anthropic: {repr(exc)}",
                finish_reason="error",
            )

    def _parse_response(self, response: dict[str, Any]) -> LLMResponse:
        content_blocks = response.get("content") or []
        if not isinstance(content_blocks, list):
            return LLMResponse(
                content="Error parsing Anthropic response: invalid content blocks",
                finish_reason="error",
            )

        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        thinking_blocks: list[dict[str, Any]] = []

        for block in content_blocks:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text":
                text = block.get("text")
                if isinstance(text, str) and text:
                    text_parts.append(text)
            elif block_type in {"thinking", "redacted_thinking"}:
                thinking_blocks.append(block)
            elif block_type == "tool_use":
                tool_calls.append(
                    ToolCallRequest(
                        id=block.get("id"),
                        name=block.get("name"),
                        arguments=block.get("input") or {},
                    )
                )

        usage_obj = response.get("usage") or {}
        usage = build_usage(
            input_tokens=usage_obj.get("input_tokens", 0),
            cached_input_tokens=usage_obj.get("cache_read_input_tokens", 0),
            cache_write_tokens=usage_obj.get("cache_creation_input_tokens", 0),
            output_tokens=usage_obj.get("output_tokens", 0),
        )

        stop_reason = response.get("stop_reason") or "end_turn"
        finish_reason = "tool_calls" if stop_reason == "tool_use" else "stop"

        return LLMResponse(
            content="\n".join(text_parts).strip() or None,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            thinking_blocks=thinking_blocks or None,
        )

    def get_default_model(self) -> str:
        return self.default_model
