"""Per-iteration handler for streaming tool-call deltas in the agent loop.

The provider layer (see :mod:`tokenmind.providers.base`) fires a callback
for every tool-call argument chunk as the model streams. This module
exposes :class:`AgentStreamingHandler`, the seam where the agent loop
collects those deltas and routes them onward — currently just a thin
state-keeper, but Stage 3 will plug a file-edit progress tracker into
``on_tool_call_delta`` and forward derived events through ``on_progress``
so the WebUI can render live diffs.

Kept deliberately small in this stage so the wiring can land and be
tested before the heavier tracking logic arrives.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from tokenmind.providers.base import ToolCallDelta

ProgressCallback = Callable[..., Awaitable[None]]


class AgentStreamingHandler:
    """Collects streaming tool-call deltas during a single chat iteration.

    One instance is created per call to :meth:`AgentLoop._run_agent_loop`'s
    inner chat invocation. The handler is intentionally side-effect-free
    for now: it just records the most-recent payload per tool-call slot
    so callers (and tests) can inspect what was streamed. Stage 3 will
    extend the ``on_tool_call_delta`` hook to drive a file-edit tracker
    and emit ``file_edit_progress`` events through ``on_progress``.
    """

    def __init__(self, *, on_progress: ProgressCallback | None = None) -> None:
        self._on_progress = on_progress
        # index → latest delta payload. Used by Stage 3 to compare against
        # the previous snapshot when computing diff stats.
        self._states: dict[int, ToolCallDelta] = {}

    async def on_tool_call_delta(self, payload: ToolCallDelta) -> None:
        """Provider-facing callback. See ``ToolCallDeltaCallback``."""
        index = payload.get("index", 0)
        self._states[index] = payload

    @property
    def latest_states(self) -> dict[int, ToolCallDelta]:
        """Per-slot latest payload. Mostly useful for tests for now."""
        return dict(self._states)

    def latest_for(self, index: int) -> ToolCallDelta | None:
        """Return the most-recent payload for the given tool-call slot."""
        return self._states.get(index)

    async def emit_progress(self, content: str, **meta: Any) -> None:
        """Helper that forwards arbitrary progress events to the WebUI.

        No-ops when no ``on_progress`` callback was provided (e.g. CLI
        invocations that don't render a live timeline).
        """
        if self._on_progress is None:
            return
        await self._on_progress(content, **meta)
