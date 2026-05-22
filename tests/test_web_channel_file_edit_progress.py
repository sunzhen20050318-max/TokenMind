"""Tests for WebChannel routing of ``_file_edit_progress`` meta into the
dedicated ``file_edit_progress`` WS frame.
"""

from __future__ import annotations

import pytest

from tokenmind.bus.events import OutboundMessage
from tokenmind.bus.queue import MessageBus
from tokenmind.server.channel.web import WebChannel, WebChannelConfig


class _FakeWsManager:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def send_to_session(self, *, session_key: str, message: dict) -> None:
        self.events.append({"session_key": session_key, "message": message})


@pytest.mark.asyncio
async def test_file_edit_progress_emits_dedicated_frame() -> None:
    bus = MessageBus()
    channel = WebChannel(WebChannelConfig(), bus)
    manager = _FakeWsManager()
    channel.set_ws_manager(manager)

    event = {
        "version": 1,
        "call_id": "call_abc",
        "tool": "edit_file",
        "path": "src/foo.py",
        "phase": "start",
        "added": 12,
        "deleted": 3,
        "approximate": True,
        "status": "editing",
    }
    await channel.send(
        OutboundMessage(
            channel="web",
            chat_id="web:s1",
            content="",
            metadata={
                "_progress": True,
                "_file_edit_progress": event,
            },
        )
    )

    assert len(manager.events) == 1
    frame = manager.events[0]
    assert frame["session_key"] == "web:s1"
    assert frame["message"]["type"] == "file_edit_progress"
    assert frame["message"]["event"] == event
    assert frame["message"]["channel"] == "web"


@pytest.mark.asyncio
async def test_file_edit_progress_takes_priority_over_other_progress_branches() -> None:
    """If a single outbound message accidentally sets both _file_edit_progress
    and a _tool_start flag, the file_edit_progress branch wins — that's the
    more specific event and we'd rather only one frame leave the server."""
    bus = MessageBus()
    channel = WebChannel(WebChannelConfig(), bus)
    manager = _FakeWsManager()
    channel.set_ws_manager(manager)

    await channel.send(
        OutboundMessage(
            channel="web",
            chat_id="web:s1",
            content="",
            metadata={
                "_progress": True,
                "_file_edit_progress": {"phase": "end", "added": 1, "deleted": 1},
                "_tool_start": True,  # would have produced a tool_start frame
                "_tool_id": "call_abc",
                "_tool_name": "edit_file",
            },
        )
    )

    types = [e["message"]["type"] for e in manager.events]
    assert types == ["file_edit_progress"]
