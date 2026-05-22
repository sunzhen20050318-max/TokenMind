"""Tests for OpenAICompatProvider spec-driven behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from tokenmind.providers.openai_compat_provider import OpenAICompatProvider
from tokenmind.providers.registry import find_by_name


def _fake_chat_response(content: str = "ok") -> SimpleNamespace:
    message = SimpleNamespace(
        content=content,
        tool_calls=None,
        reasoning_content=None,
    )
    choice = SimpleNamespace(message=message, finish_reason="stop")
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    return SimpleNamespace(choices=[choice], usage=usage)


def test_openrouter_spec_is_gateway() -> None:
    spec = find_by_name("openrouter")
    assert spec is not None
    assert spec.is_gateway is True
    assert spec.default_api_base == "https://openrouter.ai/api/v1"


@pytest.mark.asyncio
async def test_openrouter_keeps_model_name_intact() -> None:
    mock_create = AsyncMock(return_value=_fake_chat_response())
    spec = find_by_name("openrouter")

    with patch("tokenmind.providers.openai_compat_provider.AsyncOpenAI") as mock_client:
        client_instance = mock_client.return_value
        client_instance.chat.completions.create = mock_create

        provider = OpenAICompatProvider(
            api_key="sk-or-test-key",
            api_base="https://openrouter.ai/api/v1",
            default_model="anthropic/claude-sonnet-4-5",
            spec=spec,
        )
        await provider.chat(
            messages=[{"role": "user", "content": "hello"}],
            model="anthropic/claude-sonnet-4-5",
        )

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["model"] == "anthropic/claude-sonnet-4-5"


@pytest.mark.asyncio
async def test_openrouter_claude_models_apply_prompt_caching() -> None:
    mock_create = AsyncMock(return_value=_fake_chat_response())
    spec = find_by_name("openrouter")

    with patch("tokenmind.providers.openai_compat_provider.AsyncOpenAI") as mock_client:
        client_instance = mock_client.return_value
        client_instance.chat.completions.create = mock_create

        provider = OpenAICompatProvider(
            api_key="sk-or-test-key",
            api_base="https://openrouter.ai/api/v1",
            default_model="anthropic/claude-sonnet-4-5",
            spec=spec,
        )
        await provider.chat(
            messages=[{"role": "system", "content": "system prompt"}, {"role": "user", "content": "hello"}],
            tools=[{"type": "function", "function": {"name": "echo", "parameters": {"type": "object"}}}],
            model="anthropic/claude-sonnet-4-5",
        )

    call_kwargs = mock_create.call_args.kwargs
    system_message = call_kwargs["messages"][0]
    assert system_message["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert call_kwargs["tools"][-1]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_openrouter_non_claude_models_skip_prompt_caching() -> None:
    mock_create = AsyncMock(return_value=_fake_chat_response())
    spec = find_by_name("openrouter")

    with patch("tokenmind.providers.openai_compat_provider.AsyncOpenAI") as mock_client:
        client_instance = mock_client.return_value
        client_instance.chat.completions.create = mock_create

        provider = OpenAICompatProvider(
            api_key="sk-or-test-key",
            api_base="https://openrouter.ai/api/v1",
            default_model="openai/gpt-4o-mini",
            spec=spec,
        )
        await provider.chat(
            messages=[{"role": "system", "content": "system prompt"}, {"role": "user", "content": "hello"}],
            tools=[{"type": "function", "function": {"name": "echo", "parameters": {"type": "object"}}}],
            model="openai/gpt-4o-mini",
        )

    call_kwargs = mock_create.call_args.kwargs
    system_message = call_kwargs["messages"][0]
    assert system_message["content"] == "system prompt"
    assert "cache_control" not in call_kwargs["tools"][-1]


@pytest.mark.asyncio
async def test_standard_provider_strips_explicit_provider_prefix() -> None:
    mock_create = AsyncMock(return_value=_fake_chat_response())
    spec = find_by_name("deepseek")

    with patch("tokenmind.providers.openai_compat_provider.AsyncOpenAI") as mock_client:
        client_instance = mock_client.return_value
        client_instance.chat.completions.create = mock_create

        provider = OpenAICompatProvider(
            api_key="sk-deepseek-test-key",
            default_model="deepseek/deepseek-chat",
            spec=spec,
        )
        await provider.chat(
            messages=[{"role": "user", "content": "hello"}],
            model="deepseek/deepseek-chat",
        )

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["model"] == "deepseek-chat"


@pytest.mark.asyncio
async def test_deepseek_thinking_models_backfill_reasoning_content_on_legacy_turns() -> None:
    """A legacy assistant turn without ``reasoning_content`` must be preserved
    (with ``reasoning_content=""`` backfilled), not dropped — this keeps the
    agent's memory of earlier tool calls when the user switches to a thinking
    model mid-session.
    """
    mock_create = AsyncMock(return_value=_fake_chat_response())
    spec = find_by_name("deepseek")
    legacy_tool_call = {
        "id": "call_legacy",
        "type": "function",
        "function": {"name": "read_file", "arguments": "{}"},
    }

    with patch("tokenmind.providers.openai_compat_provider.AsyncOpenAI") as mock_client:
        client_instance = mock_client.return_value
        client_instance.chat.completions.create = mock_create

        provider = OpenAICompatProvider(
            api_key="sk-deepseek-test-key",
            default_model="deepseek-v4-pro",
            spec=spec,
        )
        original_messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "old question"},
            {"role": "assistant", "content": None, "tool_calls": [legacy_tool_call]},
            {"role": "tool", "tool_call_id": "call_legacy", "name": "read_file", "content": "old result"},
            {"role": "assistant", "content": "plain text answer"},
            {"role": "user", "content": "new question"},
        ]
        await provider.chat(messages=original_messages, model="deepseek-v4-pro")

    call_kwargs = mock_create.call_args.kwargs
    sent = call_kwargs["messages"]
    # Every message preserved (no drops).
    assert len(sent) == 6
    # Both assistant messages now carry reasoning_content="".
    assert sent[2]["reasoning_content"] == ""
    assert sent[2]["tool_calls"] == [legacy_tool_call]
    assert sent[4]["reasoning_content"] == ""
    assert sent[4]["content"] == "plain text answer"
    # Caller's original list is not mutated in-place.
    assert "reasoning_content" not in original_messages[2]
    assert "reasoning_content" not in original_messages[4]


@pytest.mark.asyncio
async def test_deepseek_thinking_models_keep_tool_turn_with_reasoning() -> None:
    mock_create = AsyncMock(return_value=_fake_chat_response())
    spec = find_by_name("deepseek")
    tool_call = {
        "id": "call_ok",
        "type": "function",
        "function": {"name": "read_file", "arguments": "{}"},
    }

    with patch("tokenmind.providers.openai_compat_provider.AsyncOpenAI") as mock_client:
        client_instance = mock_client.return_value
        client_instance.chat.completions.create = mock_create

        provider = OpenAICompatProvider(
            api_key="sk-deepseek-test-key",
            default_model="deepseek-v4-pro",
            spec=spec,
        )
        await provider.chat(
            messages=[
                {"role": "user", "content": "old question"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tool_call],
                    "reasoning_content": "needed by DeepSeek",
                },
                {"role": "tool", "tool_call_id": "call_ok", "name": "read_file", "content": "old result"},
                {"role": "user", "content": "new question"},
            ],
            model="deepseek-v4-pro",
        )

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["messages"] == [
        {"role": "user", "content": "old question"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [tool_call],
            "reasoning_content": "needed by DeepSeek",
        },
        {"role": "tool", "tool_call_id": "call_ok", "name": "read_file", "content": "old result"},
        {"role": "user", "content": "new question"},
    ]


@pytest.mark.asyncio
async def test_mimo_backfills_plain_assistant_turns_too() -> None:
    """MiMo rejects mixed histories — every assistant turn must carry
    ``reasoning_content`` (even plain text turns from before the switch).
    Backfill should cover both tool-call and plain-text turns.
    """
    mock_create = AsyncMock(return_value=_fake_chat_response())
    spec = find_by_name("mimo")

    with patch("tokenmind.providers.openai_compat_provider.AsyncOpenAI") as mock_client:
        client_instance = mock_client.return_value
        client_instance.chat.completions.create = mock_create

        provider = OpenAICompatProvider(
            api_key="sk-mimo-test-key",
            default_model="MiMo-VL-RL",
            spec=spec,
        )
        await provider.chat(
            messages=[
                {"role": "user", "content": "old question"},
                {"role": "assistant", "content": "plain answer"},
                {"role": "user", "content": "new question"},
            ],
            model="MiMo-VL-RL",
        )

    sent = mock_create.call_args.kwargs["messages"]
    assert len(sent) == 3
    assert sent[1]["reasoning_content"] == ""
    assert sent[1]["content"] == "plain answer"


@pytest.mark.asyncio
async def test_deepseek_chat_v3_skips_backfill() -> None:
    """``deepseek-chat`` (V3) tolerates mixed history, so no backfill is needed
    — the messages should be passed through unchanged."""
    mock_create = AsyncMock(return_value=_fake_chat_response())
    spec = find_by_name("deepseek")

    with patch("tokenmind.providers.openai_compat_provider.AsyncOpenAI") as mock_client:
        client_instance = mock_client.return_value
        client_instance.chat.completions.create = mock_create

        provider = OpenAICompatProvider(
            api_key="sk-deepseek-test-key",
            default_model="deepseek-chat",
            spec=spec,
        )
        await provider.chat(
            messages=[
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "a"},
                {"role": "user", "content": "q2"},
            ],
            model="deepseek-chat",
        )

    sent = mock_create.call_args.kwargs["messages"]
    assert "reasoning_content" not in sent[1]


def test_openai_model_passthrough() -> None:
    spec = find_by_name("openai")
    with patch("tokenmind.providers.openai_compat_provider.AsyncOpenAI"):
        provider = OpenAICompatProvider(
            api_key="sk-test-key",
            default_model="gpt-4o",
            spec=spec,
        )
    assert provider.get_default_model() == "gpt-4o"
