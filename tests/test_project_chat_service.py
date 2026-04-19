from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from tokenmind.agent.memory import MemoryStore
from tokenmind.server.app import ChatService
from tokenmind.session.manager import SessionManager


def make_service(tmp_path: Path) -> ChatService:
    session_manager = SessionManager(tmp_path)
    memory_store = MemoryStore(tmp_path)
    agent_loop = SimpleNamespace(
        memory_consolidator=SimpleNamespace(
            store=memory_store,
            templates_config=SimpleNamespace(memory_system="", memory_prompt=""),
        )
    )
    return ChatService(
        bus=SimpleNamespace(),
        agent_loop=agent_loop,
        session_manager=session_manager,
    )


def test_list_sessions_excludes_project_sessions(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    normal = service.session_manager.get_or_create("web:normal")
    normal.add_message("user", "Normal chat")
    service.session_manager.save(normal)

    project = service.session_manager.get_or_create("web:project")
    project.metadata["project_id"] = "proj_1"
    project.add_message("user", "Project chat")
    service.session_manager.save(project)

    sessions = asyncio.run(service.list_sessions())

    assert [item["session_id"] for item in sessions] == ["web:normal"]


def test_move_session_to_project_preserves_history(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    created = service.create_project("Release Plan")
    session = service.session_manager.get_or_create("web:existing")
    session.add_message("user", "First note")
    session.add_message("assistant", "Keep the history")
    service.session_manager.save(session)

    result = service.move_session_to_project(created["id"], "web:existing")
    moved = service.session_manager.get_or_create("web:existing")

    assert result["session"]["project_id"] == created["id"]
    assert moved.messages[0]["content"] == "First note"
    assert moved.messages[1]["content"] == "Keep the history"


def test_delete_project_removes_project_and_its_sessions(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    created = service.create_project("Cleanup")

    project_session = service.session_manager.get_or_create("web:project-chat")
    project_session.set_project_id(created["id"])
    project_session.add_message("user", "Delete with project")
    service.session_manager.save(project_session)

    global_session = service.session_manager.get_or_create("web:global-chat")
    global_session.add_message("user", "Keep me")
    service.session_manager.save(global_session)

    result = service.delete_project(created["id"])

    assert result == {
        "success": True,
        "project_id": created["id"],
        "deleted_session_count": 1,
    }
    assert service.projects.get_project(created["id"]) is None
    assert not service.session_manager._get_session_path("web:project-chat").exists()
    assert service.session_manager._get_session_path("web:global-chat").exists()
