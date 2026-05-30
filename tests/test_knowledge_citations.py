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


def _make_chunks(n: int) -> list[dict]:
    return [
        {
            "id": f"chunk_{i}",
            "knowledge_base_id": "kb",
            "knowledge_base_name": "KB",
            "document_id": f"doc_{i}",
            "document_name": f"doc_{i}.pdf",
            "content": f"第 {i} 段内容。",
            "score": 0.9 - i * 0.01,
        }
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_citations_not_capped_below_top_k(tmp_path: Path) -> None:
    """5 distinct retrieved chunks (under the default top_k of 6) must all
    surface as citations — the old hard cap of 3 hid the rest of the evidence."""
    loop = _make_loop(tmp_path, [LLMResponse(content="回答")])
    # Stable responder so the background title summarizer doesn't exhaust a
    # side_effect list and raise StopAsyncIteration (noise unrelated to citations).
    loop.provider.chat_with_retry = AsyncMock(return_value=LLMResponse(content="回答"))
    loop.knowledge.retrieve_for_session = MagicMock(return_value=_make_chunks(5))
    msg = InboundMessage(
        channel="web",
        sender_id="u",
        chat_id="s5",
        content="问题",
        session_key_override="web:s5",
    )

    response = await loop._process_message(msg)

    assert response is not None
    assert len(response.metadata["_citations"]) == 5


@pytest.mark.asyncio
async def test_citations_capped_at_top_k(tmp_path: Path) -> None:
    """Citations are still bounded — never more than knowledge_config.top_k."""
    loop = _make_loop(tmp_path, [LLMResponse(content="回答")])
    loop.provider.chat_with_retry = AsyncMock(return_value=LLMResponse(content="回答"))
    loop.knowledge.retrieve_for_session = MagicMock(return_value=_make_chunks(10))
    msg = InboundMessage(
        channel="web",
        sender_id="u",
        chat_id="s10",
        content="问题",
        session_key_override="web:s10",
    )

    response = await loop._process_message(msg)

    assert response is not None
    assert len(response.metadata["_citations"]) == loop.knowledge_config.top_k
