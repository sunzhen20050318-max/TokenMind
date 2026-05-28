"""Project-level wiki knowledge base + instructions — step A units.

Covers the model/store fields, the global-list filtering of project-owned
KBs, and the system-prompt instructions injection.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tokenmind.agent.context import ContextBuilder
from tokenmind.knowledge.service import KnowledgeService
from tokenmind.projects.store import ProjectStore
from tokenmind.server.app import ChatService
from tokenmind.session.manager import SessionManager


def _make_service(tmp_path: Path) -> ChatService:
    """A ChatService backed by a real SessionManager + its own
    KnowledgeService (agent_loop has no .knowledge, so one is created)."""
    return ChatService(
        bus=SimpleNamespace(),
        agent_loop=SimpleNamespace(),
        session_manager=SessionManager(tmp_path),
    )


class TestProjectStoreUpdate:
    def test_update_sets_kb_id_and_instructions_independently(self, tmp_path: Path) -> None:
        store = ProjectStore(tmp_path)
        project = store.create_project("Release Plan")
        assert project.knowledge_base_id is None
        assert project.instructions == ""

        updated = store.update_project(project.id, knowledge_base_id="kb_123")
        assert updated.knowledge_base_id == "kb_123"
        assert updated.instructions == ""  # untouched

        updated = store.update_project(project.id, instructions="Always answer in English.")
        assert updated.knowledge_base_id == "kb_123"  # preserved
        assert updated.instructions == "Always answer in English."

    def test_update_bumps_updated_at(self, tmp_path: Path) -> None:
        store = ProjectStore(tmp_path)
        project = store.create_project("P")
        before = project.updated_at
        updated = store.update_project(project.id, instructions="x")
        assert updated.updated_at >= before

    def test_update_unknown_project_raises(self, tmp_path: Path) -> None:
        store = ProjectStore(tmp_path)
        try:
            store.update_project("proj_missing", instructions="x")
        except KeyError:
            return
        raise AssertionError("expected KeyError for unknown project")


class TestGlobalListExcludesProjectKbs:
    def test_overview_hides_project_owned_kb(self, tmp_path: Path) -> None:
        service = KnowledgeService(tmp_path)
        public = service.create_knowledge_base("公共资料", "")
        owned = service.create_knowledge_base(
            "项目库", "", type="wiki", project_id="proj_1"
        )

        overview_ids = {item["id"] for item in service.get_knowledge_overview()["items"]}
        assert public.id in overview_ids
        assert owned.id not in overview_ids

    def test_project_kb_still_directly_fetchable(self, tmp_path: Path) -> None:
        service = KnowledgeService(tmp_path)
        owned = service.create_knowledge_base("项目库", "", type="wiki", project_id="proj_1")
        # Hidden from the list but still addressable by id (the agent + project
        # page reach it directly).
        assert service.get_knowledge_base(owned.id).project_id == "proj_1"


class TestInstructionsInjection:
    def test_instructions_block_present_when_provided(self, tmp_path: Path) -> None:
        builder = ContextBuilder(tmp_path)
        prompt = builder.build_system_prompt(instructions="始终用中文回答。")
        assert "# Project Instructions" in prompt
        assert "始终用中文回答。" in prompt

    def test_no_block_when_instructions_empty_or_blank(self, tmp_path: Path) -> None:
        builder = ContextBuilder(tmp_path)
        assert "# Project Instructions" not in builder.build_system_prompt(instructions="")
        assert "# Project Instructions" not in builder.build_system_prompt(instructions="   ")
        assert "# Project Instructions" not in builder.build_system_prompt()


class TestEnsureProjectWiki:
    def test_lazily_creates_wiki_kb_and_stores_id(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        project = service.projects.create_project("Alpha")
        assert project.knowledge_base_id is None

        kb_id = service.ensure_project_wiki(project.id)

        kb = service.knowledge.get_knowledge_base(kb_id)
        assert kb.type == "wiki"
        assert kb.project_id == project.id
        # Stored back on the project.
        assert service.projects.get_project(project.id).knowledge_base_id == kb_id

    def test_idempotent_returns_same_kb(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        project = service.projects.create_project("Beta")
        first = service.ensure_project_wiki(project.id)
        second = service.ensure_project_wiki(project.id)
        assert first == second

    def test_recreates_when_stored_kb_deleted(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        project = service.projects.create_project("Gamma")
        first = service.ensure_project_wiki(project.id)
        service.knowledge.delete_knowledge_base(first)
        second = service.ensure_project_wiki(project.id)
        assert second != first
        assert service.knowledge.get_knowledge_base(second).project_id == project.id


class TestProjectDetailAndInstructions:
    def test_detail_includes_kb_and_documents_keys(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        project = service.projects.create_project("Delta")
        # No KB yet → keys present but empty/None.
        detail = service.get_project_detail(project.id)
        assert detail["knowledge_base"] is None
        assert detail["documents"] == []

        service.ensure_project_wiki(project.id)
        detail = service.get_project_detail(project.id)
        assert detail["knowledge_base"] is not None
        assert detail["knowledge_base"]["type"] == "wiki"
        assert detail["documents"] == []

    def test_update_instructions_persists(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        project = service.projects.create_project("Epsilon")
        service.update_project_instructions(project.id, "用中文回答")
        assert service.projects.get_project(project.id).instructions == "用中文回答"

    def test_list_documents_empty_without_kb(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        project = service.projects.create_project("Zeta")
        assert service.list_project_documents(project.id) == {"documents": []}

    def test_add_url_source_ensures_kb_and_delegates(self, tmp_path: Path) -> None:
        import asyncio

        service = _make_service(tmp_path)
        project = service.projects.create_project("Eta")

        captured: dict[str, str] = {}

        async def fake_add_url_source(kb_id: str, url: str) -> dict:
            captured["kb_id"] = kb_id
            captured["url"] = url
            return {"document": {"id": "doc_1"}}

        service.add_url_source = fake_add_url_source  # type: ignore[method-assign]
        result = asyncio.run(
            service.add_project_url_source(project.id, "https://mp.weixin.qq.com/s/abc")
        )

        # The project's wiki KB was lazily created and used as the target.
        kb_id = service.projects.get_project(project.id).knowledge_base_id
        assert kb_id is not None
        assert captured["kb_id"] == kb_id
        assert captured["url"] == "https://mp.weixin.qq.com/s/abc"
        assert result["document"]["id"] == "doc_1"


def _make_loop(tmp_path: Path):
    from tokenmind.agent.loop import AgentLoop
    from tokenmind.bus.queue import MessageBus

    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    with patch("tokenmind.agent.loop.SubagentManager"):
        return AgentLoop(bus=MessageBus(), provider=provider, workspace=tmp_path)


class TestAgentProjectWikiFallback:
    def test_active_wiki_defaults_to_project_kb(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        project = loop.projects.create_project("Proj")
        kb = loop.knowledge.create_knowledge_base(
            "项目库", "", type="wiki", project_id=project.id
        )
        loop.projects.update_project(project.id, knowledge_base_id=kb.id)

        session = loop.sessions.get_or_create("web:proj-sess")
        session.set_project_id(project.id)
        loop.sessions.save(session)

        token = loop._current_session_key.set("web:proj-sess")
        try:
            active = loop._get_active_wiki_kb()
        finally:
            loop._current_session_key.reset(token)
        assert active is not None
        assert active["kb_id"] == kb.id

    def test_explicit_active_wiki_overrides_project_default(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        project = loop.projects.create_project("Proj2")
        proj_kb = loop.knowledge.create_knowledge_base(
            "项目库", "", type="wiki", project_id=project.id
        )
        loop.projects.update_project(project.id, knowledge_base_id=proj_kb.id)
        other_kb = loop.knowledge.create_knowledge_base("别的库", "", type="wiki")

        session = loop.sessions.get_or_create("web:proj-sess2")
        session.set_project_id(project.id)
        session.set_active_wiki_kb_id(other_kb.id)
        loop.sessions.save(session)

        token = loop._current_session_key.set("web:proj-sess2")
        try:
            active = loop._get_active_wiki_kb()
        finally:
            loop._current_session_key.reset(token)
        assert active["kb_id"] == other_kb.id

    def test_no_active_wiki_when_no_project_and_no_explicit(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop.sessions.get_or_create("web:plain")
        token = loop._current_session_key.set("web:plain")
        try:
            assert loop._get_active_wiki_kb() is None
        finally:
            loop._current_session_key.reset(token)

    def test_project_instructions_resolved(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        project = loop.projects.create_project("Proj3")
        loop.projects.update_project(project.id, instructions="always concise")
        assert loop._project_instructions(project.id) == "always concise"
        assert loop._project_instructions(None) is None
