from __future__ import annotations

from pathlib import Path

import pytest

from sun_agent.knowledge.service import KnowledgeService


def test_session_can_link_multiple_knowledge_bases(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path)
    kb_a = service.create_knowledge_base("产品资料", "")
    kb_b = service.create_knowledge_base("合同模板", "")

    service.set_session_links("web:test", [kb_a.id, kb_b.id])

    assert service.get_session_links("web:test") == [kb_a.id, kb_b.id]


def test_disabled_knowledge_base_is_removed_from_session_links(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path)
    kb_enabled = service.create_knowledge_base("产品资料", "")
    kb_disabled = service.create_knowledge_base("内部归档", "")

    service.set_session_links("web:test", [kb_enabled.id, kb_disabled.id])
    service.update_knowledge_base(kb_disabled.id, enabled=False)

    assert service.get_session_links("web:test") == [kb_enabled.id]


@pytest.mark.asyncio
async def test_route_can_update_session_knowledge_links() -> None:
    from sun_agent.server.routes import knowledge as knowledge_routes

    stored: list[str] = []

    class FakeService:
        def get_session_knowledge_links(self, session_id: str) -> list[str]:
            assert session_id == "web:test"
            return stored

        def set_session_knowledge_links(self, session_id: str, knowledge_base_ids: list[str]) -> None:
            assert session_id == "web:test"
            stored[:] = knowledge_base_ids

    payload = knowledge_routes.SessionKnowledgePayload(
        session_id="web:test",
        knowledge_base_ids=["kb_a", "kb_b"],
    )

    response = await knowledge_routes.update_session_knowledge_links(
        "web:test",
        payload,
        service=FakeService(),
    )

    assert response["knowledge_base_ids"] == ["kb_a", "kb_b"]


@pytest.mark.asyncio
async def test_route_can_read_session_knowledge_links() -> None:
    from sun_agent.server.routes import knowledge as knowledge_routes

    class FakeService:
        def get_session_knowledge_links(self, session_id: str) -> list[str]:
            assert session_id == "web:test"
            return ["kb_a"]

    response = await knowledge_routes.get_session_knowledge_links("web:test", service=FakeService())

    assert response["knowledge_base_ids"] == ["kb_a"]
