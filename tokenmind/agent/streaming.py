"""Per-iteration handler for streaming tool-call deltas in the agent loop.

The provider layer (see :mod:`tokenmind.providers.base`) fires a callback
for every tool-call argument chunk as the model streams. This module
exposes :class:`AgentStreamingHandler`, the seam where the agent loop
collects those deltas and routes them onward.

Stage 3 hooks a :class:`FileEditTracker` into the delta stream, so that
``write_file`` / ``edit_file`` invocations surface live diff counts to
the WebUI before the tool has actually run.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from loguru import logger

from tokenmind.agent.file_edit_tracker import FileEditTracker
from tokenmind.providers.base import ToolCallDelta

ProgressCallback = Callable[..., Awaitable[None]]


class AgentStreamingHandler:
    """Coordinates streaming-time hooks for a single chat iteration.

    One instance is created per call to :meth:`AgentLoop._run_agent_loop`'s
    inner chat invocation. Responsibilities:

    - record each tool-call delta payload (one snapshot per slot) so the
      agent loop can introspect what was streamed;
    - feed deltas into a :class:`FileEditTracker` so live ``+N/-M`` events
      flow to the WebUI as the model assembles its arguments;
    - expose :meth:`finalize_edit` so the agent loop can announce the
      exact diff once the tool has actually executed.
    """

    def __init__(
        self,
        *,
        on_progress: ProgressCallback | None = None,
        workspace: Path | None = None,
    ) -> None:
        self._on_progress = on_progress
        self._states: dict[int, ToolCallDelta] = {}
        self._file_edit_tracker = FileEditTracker(
            workspace=workspace,
            emit=self._emit_file_edit_event,
        )

    async def on_tool_call_delta(self, payload: ToolCallDelta) -> None:
        """Provider-facing callback. See ``ToolCallDeltaCallback``.

        Wrapped in a broad except so a misbehaving tracker / progress sink
        (e.g. a WebSocket that disconnected mid-stream) can't tear down
        the entire chat call. The chat itself still completes; the worst
        case is the WebUI not seeing live file-edit progress for the
        remainder of this iteration.
        """
        index = payload.get("index", 0)
        self._states[index] = payload
        try:
            await self._file_edit_tracker.on_delta(payload)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Streaming handler: file-edit tracker raised on delta "
                "(index={}, call_id={!r}) — continuing chat without live "
                "progress for this iteration",
                index, payload.get("call_id"),
            )

    @property
    def latest_states(self) -> dict[int, ToolCallDelta]:
        """Per-slot latest payload. Mostly useful for tests for now."""
        return dict(self._states)

    def latest_for(self, index: int) -> ToolCallDelta | None:
        """Return the most-recent payload for the given tool-call slot."""
        return self._states.get(index)

    async def finalize_edit(
        self,
        call_id: str,
        *,
        status: str = "done",
        error: str | None = None,
    ) -> None:
        """Tell the file-edit tracker that a tool call has finished.

        Triggers the final exact-diff ``end`` (or ``error``) event for
        ``write_file`` / ``edit_file`` calls. No-op for other tools.
        Errors here are logged but never raised — the caller is the
        agent loop's tool-execution path, which we don't want to crash
        on a UI-side glitch.
        """
        try:
            await self._file_edit_tracker.finalize(
                call_id, status=status, error=error,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Streaming handler: file-edit tracker raised on finalize "
                "(call_id={!r}, status={})",
                call_id, status,
            )

    async def abandon_open_edits(self) -> None:
        """Mark any in-flight file edits as errored after a chat failure.

        Called when ``chat_with_retry`` returns ``finish_reason='error'``
        and we never reach the tool-execution loop: without this, any
        ``start`` event already on the WebUI would sit forever in
        "正在写入..." state. Sweeps every call_id the tracker knows about
        that hasn't been finalised, emits an error event for each.
        """
        try:
            await self._file_edit_tracker.abandon_open()
        except Exception:  # noqa: BLE001
            logger.exception("Streaming handler: failed to abandon open edits")

    async def emit_progress(self, content: str, **meta: Any) -> None:
        """Helper that forwards arbitrary progress events to the WebUI.

        No-ops when no ``on_progress`` callback was provided (e.g. CLI
        invocations that don't render a live timeline).
        """
        if self._on_progress is None:
            return
        await self._on_progress(content, **meta)

    async def _emit_file_edit_event(self, event: dict[str, Any]) -> None:
        """Route a file-edit progress event through the on_progress channel.

        Calls ``on_progress(content, file_edit_event=event)`` — the agent
        loop's ``_bus_progress`` understands this kwarg and converts it
        into an ``_file_edit_progress`` metadata key on the outbound
        message; the WebChannel then forwards a dedicated WS frame.
        Silently dropped on paths without an on_progress callback (CLI,
        subagents).
        """
        if self._on_progress is None:
            return
        await self._on_progress("", file_edit_event=event)
