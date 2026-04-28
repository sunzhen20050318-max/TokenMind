"""Pub/sub hub for streaming browser-task events to WebSocket subscribers.

Each browser task can have many concurrent subscribers (e.g. the running
panel + a side-by-side replay window). The hub keeps per-task buffers so a
late subscriber catches up on the steps already emitted before they
connected — important because most clients connect *after* the task has
already started.

This module is intentionally framework-agnostic: it just wraps asyncio
queues. The route layer wires it to FastAPI WebSockets.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any

logger = logging.getLogger("tokenmind.browser_agent.stream")

# How many recent events to buffer per task so a late subscriber gets context.
_BUFFER_SIZE = 200


class BrowserStreamHub:
    """In-process pub/sub for browser-task events."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._buffers: dict[str, deque[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def emit(self, task_id: str, event: dict[str, Any]) -> None:
        """Broadcast ``event`` to all subscribers and append to the replay buffer.

        Failures putting into a subscriber queue are swallowed (a slow client
        shouldn't block the task). Events are deep-copied conceptually by
        being JSON-serialisable dicts.
        """
        async with self._lock:
            buffer = self._buffers.setdefault(task_id, deque(maxlen=_BUFFER_SIZE))
            buffer.append(event)
            queues = list(self._subscribers.get(task_id, ()))

        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("stream queue full for task %s; dropping event", task_id)

    async def subscribe(self, task_id: str) -> tuple[asyncio.Queue[dict[str, Any]], list[dict[str, Any]]]:
        """Register a new subscriber. Returns a queue + the replay buffer.

        The replay buffer should be flushed to the client first so the UI
        has the historical timeline before live events start arriving.
        """
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1024)
        async with self._lock:
            self._subscribers.setdefault(task_id, set()).add(queue)
            buffered = list(self._buffers.get(task_id, ()))
        return queue, buffered

    async def unsubscribe(self, task_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            subs = self._subscribers.get(task_id)
            if subs and queue in subs:
                subs.remove(queue)
                if not subs:
                    del self._subscribers[task_id]

    async def discard_task(self, task_id: str) -> None:
        """Drop the replay buffer + close subscriber queues. Call after a task
        finishes if you want to free memory aggressively. The default is to
        keep buffers around so users can re-open the page and still see the
        full history."""
        async with self._lock:
            self._subscribers.pop(task_id, None)
            self._buffers.pop(task_id, None)


# Default singleton used by the FastAPI route + TaskService wiring.
default_hub = BrowserStreamHub()
