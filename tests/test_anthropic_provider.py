from unittest.mock import AsyncMock, Mock, patch

import pytest

from tokenmind.providers.anthropic_provider import AnthropicProvider
from tokenmind.providers.base import LLMResponse


def test_anthropic_provider_init_requires_api_key() -> None:
    with pytest.raises(ValueError, match="Anthropic api_key is required"):
        AnthropicProvider(api_key="")


def test_anthropic_provider_normalizes_explicit_prefix() -> None:
    provider = AnthropicProvider(api_key="test-key")
    assert provider._normalize_model("anthropic/claude-sonnet-4-5") == "claude-sonnet-4-5"
    assert provider._normalize_model("claude-sonnet-4-5") == "claude-sonnet-4-5"


def test_anthropic_provider_converts_history_messages() -> None:
    provider = AnthropicProvider(api_key="test-key")
    system, messages = provider._convert_messages(
        [
            {"role": "system", "content": "You are helpful."},
            {
                "role": "assistant",
                "content": "Let me check.",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path": "todo.md"}',
                        },
                    }
                ],
                "thinking_blocks": [{"type": "thinking", "thinking": "internal"}],
            },
            {"role": "tool", "tool_call_id": "call_123", "name": "read_file", "content": "hello"},
        ]
    )

    assert system == "You are helpful."
    assert messages[0]["role"] == "assistant"
    assert messages[0]["content"][0]["type"] == "thinking"
    assert messages[0]["content"][1]["type"] == "text"
    assert messages[0]["content"][2]["type"] == "tool_use"
    assert messages[1] == {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "call_123", "content": "hello"}],
    }


@pytest.mark.asyncio
async def test_anthropic_chat_success_maps_response() -> None:
    provider = AnthropicProvider(api_key="test-key", default_model="anthropic/claude-sonnet-4-5")
    response_data = {
        "content": [
            {"type": "thinking", "thinking": "internal", "signature": "sig"},
            {"type": "text", "text": "Hello from Claude"},
            {"type": "tool_use", "id": "toolu_1", "name": "read_file", "input": {"path": "todo.md"}},
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 12, "output_tokens": 18},
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value=response_data)
        mock_context = AsyncMock()
        mock_context.post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value = mock_context

        result = await provider.chat(messages=[{"role": "user", "content": "Hello"}])

    assert isinstance(result, LLMResponse)
    assert result.content == "Hello from Claude"
    assert result.finish_reason == "tool_calls"
    assert result.usage["prompt_tokens"] == 12
    assert result.usage["completion_tokens"] == 18
    assert result.usage["total_tokens"] == 30
    assert result.usage["input_tokens"] == 12
    assert result.usage["output_tokens"] == 18
    assert result.thinking_blocks == [{"type": "thinking", "thinking": "internal", "signature": "sig"}]
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].arguments == {"path": "todo.md"}
