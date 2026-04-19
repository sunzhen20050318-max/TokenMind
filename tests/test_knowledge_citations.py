from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tokenmind.agent.loop import AgentLoop
from tokenmind.bus.events import InboundMessage
from tokenmind.bus.queue import MessageBus
from tokenmind.providers.base import LLMResponse


def _make_loop(tmp_path: Path, responses: list[LLMResponse]) -> AgentLoop:
    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.chat_with_retry = AsyncMock(side_effect=responses)
    loop = AgentLoop(bus=bus, provider=provider, workspace=tmp_path)
    loop.memory_consolidator.maybe_consolidate_by_tokens = AsyncMock(return_value=None)
    return loop


@pytest.mark.asyncio
async def test_process_message_attaches_knowledge_citations_to_response_and_session(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, [LLMResponse(content="这是基于知识库的回答。")])
    loop.knowledge.retrieve_for_session = MagicMock(
        return_value=[
            {
                "id": "chunk_1",
                "knowledge_base_id": "kb_test",
                "knowledge_base_name": "测试知识库",
                "document_id": "doc_1",
                "document_name": "产品手册.pdf",
                "content": "TokenMind 支持知识库检索，并会把相关资料作为补充上下文提供给模型。",
                "score": 0.93,
            }
        ]
    )

    msg = InboundMessage(
        channel="web",
        sender_id="web_user",
        chat_id="session-1",
        content="知识库可以怎么帮助回答问题？",
        session_key_override="web:session-1",
    )

    response = await loop._process_message(msg)

    assert response is not None
    assert response.metadata["_citations"][0]["knowledge_base_name"] == "测试知识库"
    assert response.metadata["_citations"][0]["document_name"] == "产品手册.pdf"

    session = loop.sessions.get_or_create("web:session-1")
    assistant_message = next(message for message in reversed(session.messages) if message["role"] == "assistant")
    assert assistant_message["citations"][0]["knowledge_base_name"] == "测试知识库"
    assert assistant_message["citations"][0]["document_name"] == "产品手册.pdf"
