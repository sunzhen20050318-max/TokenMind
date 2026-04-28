"""Tests for the BrowserStreamHub pub/sub layer."""

from __future__ import annotations

import asyncio

import pytest

from tokenmind.browser_agent.stream import BrowserStreamHub


@pytest.mark.asyncio
async def test_subscribe_replays_buffered_events() -> None:
    hub = BrowserStreamHub()
    await hub.emit("t1", {"type": "step", "step_index": 1})
    await hub.emit("t1", {"type": "step", "step_index": 2})

    queue, buffered = await hub.subscribe("t1")
    assert [e["step_index"] for e in buffered] == [1, 2]
    assert queue.empty()

    # New events after subscription land in the queue.
    await hub.emit("t1", {"type": "step", "step_index": 3})
    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event["step_index"] == 3

    await hub.unsubscribe("t1", queue)


@pytest.mark.asyncio
async def test_emit_broadcasts_to_all_subscribers() -> None:
    hub = BrowserStreamHub()
    q1, _ = await hub.subscribe("t1")
    q2, _ = await hub.subscribe("t1")

    await hub.emit("t1", {"type": "status", "status": "running"})

    e1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    e2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert e1 == {"type": "status", "status": "running"}
    assert e2 == {"type": "status", "status": "running"}


@pytest.mark.asyncio
async def test_emit_isolates_tasks() -> None:
    hub = BrowserStreamHub()
    q_a, _ = await hub.subscribe("task_a")
    q_b, _ = await hub.subscribe("task_b")

    await hub.emit("task_a", {"type": "step", "tag": "A"})
    await hub.emit("task_b", {"type": "step", "tag": "B"})

    a = await asyncio.wait_for(q_a.get(), timeout=1.0)
    b = await asyncio.wait_for(q_b.get(), timeout=1.0)
    assert a["tag"] == "A"
    assert b["tag"] == "B"
    assert q_a.empty() and q_b.empty()


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery() -> None:
    hub = BrowserStreamHub()
    queue, _ = await hub.subscribe("t1")
    await hub.unsubscribe("t1", queue)

    await hub.emit("t1", {"type": "step"})
    # Queue should not receive — it was unsubscribed.
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(queue.get(), timeout=0.05)


@pytest.mark.asyncio
async def test_buffer_caps_at_max_size() -> None:
    """Buffer keeps only the most recent _BUFFER_SIZE events."""
    hub = BrowserStreamHub()
    for i in range(250):
        await hub.emit("t1", {"type": "step", "step_index": i})

    _, buffered = await hub.subscribe("t1")
    # Default buffer is 200; first 50 should have been evicted.
    assert len(buffered) == 200
    assert buffered[0]["step_index"] == 50
    assert buffered[-1]["step_index"] == 249


@pytest.mark.asyncio
async def test_discard_task_clears_buffers_and_subscribers() -> None:
    hub = BrowserStreamHub()
    queue, _ = await hub.subscribe("t1")
    await hub.emit("t1", {"type": "step", "tag": "before"})
    # Drain the in-flight event so we test what happens *after* discard.
    await asyncio.wait_for(queue.get(), timeout=1.0)

    await hub.discard_task("t1")

    # A brand-new subscriber should see an empty replay buffer.
    _, buffered = await hub.subscribe("t1")
    assert buffered == []

    # The original orphaned queue should not receive anything emitted after discard.
    await hub.emit("t1", {"type": "step", "tag": "after"})
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(queue.get(), timeout=0.05)
