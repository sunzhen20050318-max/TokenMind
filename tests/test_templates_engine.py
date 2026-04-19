from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from sun_agent.agent.loop import AgentLoop
from sun_agent.bus.queue import MessageBus
from sun_agent.config.schema import TemplatesConfig
from sun_agent.providers.base import LLMResponse
from sun_agent.templates_engine import TemplateRenderer


def test_template_renderer_renders_known_context() -> None:
    renderer = TemplateRenderer()

    rendered = renderer.render("{{ content }} via {{ model }}", content="hello", model="claude")

    assert rendered == "hello via claude"


def test_template_renderer_returns_none_for_blank_template() -> None:
    renderer = TemplateRenderer()

    assert renderer.render("", content="hello") is None


@pytest.mark.asyncio
async def test_agent_loop_applies_response_template(tmp_path) -> None:
    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "anthropic/claude-sonnet-4-5"
    provider.chat_with_retry = AsyncMock(return_value=LLMResponse(content="hello"))

    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=tmp_path,
        model="anthropic/claude-sonnet-4-5",
        templates_config=TemplatesConfig(
            response="{{ content }} [{{ model }}|{{ channel }}|{{ session_key }}]"
        ),
    )

    response = await loop.process_direct(
        "say hi",
        session_key="web:test-session",
        channel="web",
        chat_id="test-chat",
    )

    assert response == "hello [anthropic/claude-sonnet-4-5|web|web:test-session]"
