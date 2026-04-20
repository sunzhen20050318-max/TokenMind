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
async def test_web_channel_response_end_includes_attachment_refs() -> None:
    bus = MessageBus()
    channel = WebChannel(WebChannelConfig(), bus)
    manager = _FakeWsManager()
    channel.set_ws_manager(manager)

    await channel.send(
        OutboundMessage(
            channel="web",
            chat_id="web:test-session",
            content="已生成文件。",
            metadata={
                "_attachments": [
                    {
                        "id": "att_123",
                        "name": "summary.md",
                        "category": "markdown",
                        "origin": "assistant_generated",
                        "status": "temporary",
                        "is_image": False,
                    }
                ]
            },
        )
    )

    assert [event["message"]["type"] for event in manager.events] == [
        "response_start",
        "response_delta",
        "response_end",
    ]
    assert manager.events[-1]["message"]["attachments"][0]["id"] == "att_123"
