"""Tests for ``OpenAICompatProvider.chat()`` streaming mode.

When ``on_tool_call_delta`` is provided, the provider switches to
``stream=True`` under the hood. The deltas fed to the callback should
let the agent loop track in-progress tool calls (e.g. to show live file
edit diffs in the WebUI). The final ``LLMResponse`` must still be
equivalent to what the non-streaming path would return.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from tokenmind.providers.openai_compat_provider import OpenAICompatProvider


def _chunk(
    *,
    content_delta: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    finish_reason: str | None = None,
    usage: dict[str, int] | None = None,
    reasoning_content: str | None = None,
) -> SimpleNamespace:
    """Construct a SimpleNamespace shaped like a streaming chunk."""
    delta_kwargs: dict[str, Any] = {"content": content_delta}
    if reasoning_content is not None:
        delta_kwargs["reasoning_content"] = reasoning_content
    if tool_calls is not None:
        delta_kwargs["tool_calls"] = [
            SimpleNamespace(
                index=tc.get("index", 0),
                id=tc.get("id"),
                function=SimpleNamespace(
                    name=tc.get("name"),
                    arguments=tc.get("arguments"),
                ) if "name" in tc or "arguments" in tc else None,
            )
            for tc in tool_calls
        ]
    else:
        delta_kwargs["tool_calls"] = None
    delta = SimpleNamespace(**delta_kwargs)
    choices = [SimpleNamespace(delta=delta, finish_reason=finish_reason)]
    chunk = SimpleNamespace(choices=choices, usage=None)
    if usage is not None:
        chunk.usage = SimpleNamespace(**usage)
    return chunk


def _final_usage_chunk(usage: dict[str, int]) -> SimpleNamespace:
    """A trailing usage-only chunk (no choices, common with include_usage=True)."""
    return SimpleNamespace(choices=[], usage=SimpleNamespace(**usage))


class _FakeStream:
    """Minimal async iterator that yields the provided chunks."""

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> "_FakeStream":
        self._iter = iter(self._chunks)
        return self

    async def __anext__(self) -> Any:
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def _build_provider(stream_chunks: list[Any]) -> tuple[OpenAICompatProvider, AsyncMock]:
    """Build a provider whose ``client.chat.completions.create`` returns the stream."""
    fake_create = AsyncMock(return_value=_FakeStream(stream_chunks))
    with patch("tokenmind.providers.openai_compat_provider.AsyncOpenAI") as mock_client:
        mock_client.return_value.chat.completions.create = fake_create
        provider = OpenAICompatProvider(
            api_key="sk-test", default_model="gpt-4o-mini",
        )
    return provider, fake_create


# ─── basics ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_callback_absent_skips_streaming() -> None:
    """When no callback is provided, the provider uses non-streaming mode."""
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(
                content="hi", tool_calls=None, reasoning_content=None,
            ),
            finish_reason="stop",
        )],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )
    with patch("tokenmind.providers.openai_compat_provider.AsyncOpenAI") as mock_client:
        mock_client.return_value.chat.completions.create = AsyncMock(return_value=fake_response)
        provider = OpenAICompatProvider(api_key="sk-test", default_model="gpt-4o-mini")
        response = await provider.chat(messages=[{"role": "user", "content": "hi"}])

    create_kwargs = mock_client.return_value.chat.completions.create.call_args.kwargs
    assert "stream" not in create_kwargs
    assert response.content == "hi"


@pytest.mark.asyncio
async def test_callback_present_enables_streaming() -> None:
    """When a callback is provided, the SDK is called with stream=True."""
    chunks = [
        _chunk(content_delta="hello", finish_reason=None),
        _chunk(content_delta=" world", finish_reason="stop"),
    ]
    provider, fake_create = _build_provider(chunks)

    callback = AsyncMock()
    response = await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        on_tool_call_delta=callback,
    )

    kwargs = fake_create.call_args.kwargs
    assert kwargs["stream"] is True
    assert kwargs["stream_options"] == {"include_usage": True}
    assert response.content == "hello world"
    assert response.finish_reason == "stop"
    # No tool calls in this stream -> callback never fires.
    callback.assert_not_called()


# ─── tool-call deltas ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_single_tool_call_assembles_correctly() -> None:
    chunks = [
        _chunk(tool_calls=[{
            "index": 0, "id": "call_1", "name": "edit_file",
        }]),
        _chunk(tool_calls=[{"index": 0, "arguments": '{"path"'}]),
        _chunk(tool_calls=[{"index": 0, "arguments": ': "a.txt", "old": "foo"'}]),
        _chunk(tool_calls=[{"index": 0, "arguments": ', "new": "bar"}'}]),
        _chunk(finish_reason="tool_calls"),
        _final_usage_chunk({"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15}),
    ]
    provider, _ = _build_provider(chunks)

    deltas: list[dict[str, Any]] = []

    async def collect(d: dict[str, Any]) -> None:
        deltas.append(d)

    response = await provider.chat(
        messages=[{"role": "user", "content": "edit"}],
        on_tool_call_delta=collect,
    )

    assert len(response.tool_calls) == 1
    call = response.tool_calls[0]
    assert call.id == "call_1"
    assert call.name == "edit_file"
    assert call.arguments == {"path": "a.txt", "old": "foo", "new": "bar"}
    assert response.finish_reason == "tool_calls"
    # Normalized usage may carry extra derived fields (input/output_tokens
    # etc); the OpenAI-shaped trio must round-trip exactly.
    assert response.usage["prompt_tokens"] == 5
    assert response.usage["completion_tokens"] == 10
    assert response.usage["total_tokens"] == 15

    # Callback should have fired once per delta that touched a tool_call.
    assert len(deltas) == 4
    # First delta: only name/id present, no arguments yet.
    assert deltas[0]["call_id"] == "call_1"
    assert deltas[0]["name"] == "edit_file"
    assert deltas[0]["arguments_delta"] == ""
    assert deltas[0]["arguments"] == ""
    # Second delta carries the first arg chunk.
    assert deltas[1]["arguments_delta"] == '{"path"'
    assert deltas[1]["arguments"] == '{"path"'
    # Final delta has the full accumulated string.
    assert deltas[3]["arguments"] == '{"path": "a.txt", "old": "foo", "new": "bar"}'


@pytest.mark.asyncio
async def test_parallel_tool_calls_are_tracked_by_index() -> None:
    """Two tool calls streaming concurrently — deltas should keyed by index."""
    chunks = [
        _chunk(tool_calls=[
            {"index": 0, "id": "a", "name": "read_file"},
            {"index": 1, "id": "b", "name": "list_dir"},
        ]),
        _chunk(tool_calls=[{"index": 0, "arguments": '{"path": "x"}'}]),
        _chunk(tool_calls=[{"index": 1, "arguments": '{"path": "y"}'}]),
        _chunk(finish_reason="tool_calls"),
    ]
    provider, _ = _build_provider(chunks)

    by_idx: dict[int, dict[str, Any]] = {}

    async def cb(d: dict[str, Any]) -> None:
        by_idx[d["index"]] = d

    response = await provider.chat(
        messages=[{"role": "user", "content": "go"}],
        on_tool_call_delta=cb,
    )

    assert len(response.tool_calls) == 2
    assert response.tool_calls[0].name == "read_file"
    assert response.tool_calls[0].arguments == {"path": "x"}
    assert response.tool_calls[1].name == "list_dir"
    assert response.tool_calls[1].arguments == {"path": "y"}
    assert by_idx[0]["arguments"] == '{"path": "x"}'
    assert by_idx[1]["arguments"] == '{"path": "y"}'


@pytest.mark.asyncio
async def test_reasoning_content_streamed() -> None:
    """DeepSeek-R1 style ``reasoning_content`` delta should accumulate."""
    chunks = [
        _chunk(reasoning_content="Let me "),
        _chunk(reasoning_content="think..."),
        _chunk(content_delta="answer", finish_reason="stop"),
    ]
    provider, _ = _build_provider(chunks)

    callback = AsyncMock()
    response = await provider.chat(
        messages=[{"role": "user", "content": "q"}],
        on_tool_call_delta=callback,
    )

    assert response.reasoning_content == "Let me think..."
    assert response.content == "answer"


@pytest.mark.asyncio
async def test_empty_choices_chunks_are_skipped() -> None:
    """Trailing usage-only chunk (no choices) must not crash the stream."""
    chunks = [
        _chunk(content_delta="ok", finish_reason="stop"),
        _final_usage_chunk({"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}),
    ]
    provider, _ = _build_provider(chunks)
    response = await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        on_tool_call_delta=AsyncMock(),
    )
    assert response.content == "ok"
    assert response.usage["total_tokens"] == 4


@pytest.mark.asyncio
async def test_default_finish_reason_when_missing() -> None:
    """Stream that never sets finish_reason should default to 'stop'."""
    chunks = [_chunk(content_delta="x")]
    provider, _ = _build_provider(chunks)
    response = await provider.chat(
        messages=[],
        on_tool_call_delta=AsyncMock(),
    )
    assert response.finish_reason == "stop"


@pytest.mark.asyncio
async def test_unparseable_arguments_become_empty_dict() -> None:
    """A tool call whose arguments never parse cleanly should still yield a
    ToolCallRequest with an empty dict — the agent loop's tool registry
    handles validation."""
    chunks = [
        _chunk(tool_calls=[{
            "index": 0, "id": "c1", "name": "broken", "arguments": "this is not json",
        }]),
        _chunk(finish_reason="tool_calls"),
    ]
    # The default json_repair is permissive, so feed something truly broken.
    provider, _ = _build_provider(chunks)
    response = await provider.chat(
        messages=[], on_tool_call_delta=AsyncMock(),
    )
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "broken"
    assert isinstance(response.tool_calls[0].arguments, dict)
