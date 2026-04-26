import pytest

from tokenmind.agent.tools.message import MessageTool
from tokenmind.bus.events import OutboundMessage


@pytest.mark.asyncio
async def test_message_tool_returns_error_when_no_target_context() -> None:
    tool = MessageTool()
    result = await tool.execute(content="test")
    assert result == "Error: No target channel/chat specified"


@pytest.mark.asyncio
async def test_message_tool_treats_web_chat_id_as_current_web_session() -> None:
    sent: list[OutboundMessage] = []

    async def capture(message: OutboundMessage) -> None:
        sent.append(message)

    tool = MessageTool(send_callback=capture)
    tool.set_context("web", "web:task-results")

    result = await tool.execute(content="hello", channel="web", chat_id="web")

    assert result == "Message prepared for current web chat"
    assert sent == []
    assert tool._sent_in_turn is True
    assert tool._sent_content == "hello"
