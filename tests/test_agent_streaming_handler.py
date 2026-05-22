"""Tests for ``AgentStreamingHandler`` (Stage 2 of streaming tool-calls).

This stage just plumbs the provider's ``on_tool_call_delta`` callback
through the agent loop into a per-iteration handler. The handler itself
does very little yet — it records the latest payload per tool-call slot
and exposes a helper that forwards progress events when an ``on_progress``
callback is wired (Stage 3 will use that seam to push live file-edit
diffs).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from tokenmind.agent.streaming import AgentStreamingHandler


@pytest.mark.asyncio
async def test_handler_records_latest_delta_per_index() -> None:
    h = AgentStreamingHandler()
    await h.on_tool_call_delta({
        "index": 0, "call_id": "a", "name": "edit_file",
        "arguments_delta": '{"path"', "arguments": '{"path"',
    })
    await h.on_tool_call_delta({
        "index": 0, "call_id": "a", "name": "edit_file",
        "arguments_delta": ': "x.txt"}', "arguments": '{"path": "x.txt"}',
    })

    state = h.latest_for(0)
    assert state is not None
    assert state["arguments"] == '{"path": "x.txt"}'
    assert state["name"] == "edit_file"


@pytest.mark.asyncio
async def test_handler_tracks_parallel_slots_independently() -> None:
    h = AgentStreamingHandler()
    await h.on_tool_call_delta({
        "index": 0, "call_id": "a", "name": "read_file",
        "arguments_delta": "", "arguments": "",
    })
    await h.on_tool_call_delta({
        "index": 1, "call_id": "b", "name": "list_dir",
        "arguments_delta": "", "arguments": "",
    })

    states = h.latest_states
    assert set(states.keys()) == {0, 1}
    assert states[0]["name"] == "read_file"
    assert states[1]["name"] == "list_dir"


@pytest.mark.asyncio
async def test_emit_progress_forwards_to_on_progress() -> None:
    sink: list[tuple[str, dict[str, Any]]] = []

    async def on_progress(text: str, **meta: Any) -> None:
        sink.append((text, meta))

    h = AgentStreamingHandler(on_progress=on_progress)
    await h.emit_progress("hi", kind="test", payload={"x": 1})

    assert sink == [("hi", {"kind": "test", "payload": {"x": 1}})]


@pytest.mark.asyncio
async def test_emit_progress_is_silent_without_callback() -> None:
    """No ``on_progress`` callback → emit_progress should be a no-op (no crash)."""
    h = AgentStreamingHandler()
    # Should not raise.
    await h.emit_progress("dropped", kind="anything")


# ────────────────────────────────────────────────────────────────────────
# Integration: deltas actually reach the handler when provider streams
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handler_receives_deltas_from_streaming_provider() -> None:
    """End-to-end across provider + handler — no AgentLoop involvement
    yet; just confirms the callback contract is honoured.
    """
    from types import SimpleNamespace

    from tokenmind.providers.openai_compat_provider import OpenAICompatProvider

    def _chunk(**delta_kwargs: Any) -> SimpleNamespace:
        delta = SimpleNamespace(
            content=delta_kwargs.get("content"),
            tool_calls=delta_kwargs.get("tool_calls"),
            reasoning_content=delta_kwargs.get("reasoning_content"),
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(
                delta=delta,
                finish_reason=delta_kwargs.get("finish_reason"),
            )],
            usage=None,
        )

    class _FakeStream:
        def __init__(self, chunks):
            self._chunks = chunks

        def __aiter__(self):
            self._iter = iter(self._chunks)
            return self

        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    chunks = [
        _chunk(tool_calls=[SimpleNamespace(
            index=0, id="c1",
            function=SimpleNamespace(name="edit_file", arguments=None),
        )]),
        _chunk(tool_calls=[SimpleNamespace(
            index=0, id=None,
            function=SimpleNamespace(name=None, arguments='{"path": "x.txt"}'),
        )]),
        _chunk(finish_reason="tool_calls"),
    ]

    from unittest.mock import patch
    fake_create = AsyncMock(return_value=_FakeStream(chunks))
    with patch("tokenmind.providers.openai_compat_provider.AsyncOpenAI") as mock_client:
        mock_client.return_value.chat.completions.create = fake_create
        provider = OpenAICompatProvider(api_key="sk-test", default_model="m")

        handler = AgentStreamingHandler()
        response = await provider.chat(
            messages=[{"role": "user", "content": "go"}],
            on_tool_call_delta=handler.on_tool_call_delta,
        )

    assert response.tool_calls[0].name == "edit_file"
    assert response.tool_calls[0].arguments == {"path": "x.txt"}

    state = handler.latest_for(0)
    assert state is not None
    assert state["call_id"] == "c1"
    assert state["name"] == "edit_file"
    assert state["arguments"] == '{"path": "x.txt"}'


# ────────────────────────────────────────────────────────────────────────
# AgentLoop wires on_tool_call_delta into chat_with_retry
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_loop_passes_streaming_callback_to_provider(tmp_path) -> None:
    """When the main agent loop calls the provider, it must include a
    bound ``on_tool_call_delta`` callable — that's the seam Stage 3 will
    exploit to drive the file-edit tracker."""
    from unittest.mock import MagicMock

    from tokenmind.agent.loop import AgentLoop
    from tokenmind.bus.events import InboundMessage
    from tokenmind.bus.queue import MessageBus
    from tokenmind.providers.base import LLMResponse

    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    captured_kwargs: dict[str, Any] = {}

    async def fake_chat(**kwargs: Any) -> LLMResponse:
        captured_kwargs.update(kwargs)
        # Feed a synthetic delta back through the bound callback so we can
        # confirm the loop's handler actually receives it.
        cb = kwargs.get("on_tool_call_delta")
        if cb is not None:
            await cb({
                "index": 0,
                "call_id": "synthetic",
                "name": "noop",
                "arguments_delta": "",
                "arguments": "",
            })
        return LLMResponse(content="ok", finish_reason="stop")

    provider.chat_with_retry = fake_chat

    loop = AgentLoop(bus=bus, provider=provider, workspace=tmp_path, model="test-model")
    msg = InboundMessage(
        channel="cli", sender_id="user", chat_id="s1", content="hi",
    )
    await loop._process_message(msg)

    cb = captured_kwargs.get("on_tool_call_delta")
    assert cb is not None, "loop did not pass on_tool_call_delta to provider"
    assert callable(cb)
    # The callable should be bound to an AgentStreamingHandler — invoke
    # it once and check the state landed on the underlying handler.
    handler = cb.__self__  # type: ignore[attr-defined]
    assert isinstance(handler, AgentStreamingHandler)
    # The fake_chat above already fired one synthetic delta, so the
    # handler should now know about slot 0.
    assert handler.latest_for(0) is not None
    assert handler.latest_for(0)["call_id"] == "synthetic"
