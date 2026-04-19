from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

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


def test_chat_service_memory_overview_returns_empty_states_without_session(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    overview = service.get_memory_overview()

    assert overview["long_term"]["content"] == ""
    assert overview["long_term"]["editable"] is True
    assert overview["current_context"]["session_id"] is None
    assert overview["current_context"]["items"] == []
    assert overview["archive"]["items"] == []
    assert overview["settings"]["editable_long_term"] is True


def test_chat_service_memory_overview_returns_current_context_for_active_session(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    session = service.session_manager.get_or_create("web:test-memory")
    session.set_title("记忆测试会话")
    session.add_message("user", "第一条消息")
    session.add_message("assistant", "第一条回复")
    service.session_manager.save(session)

    overview = service.get_memory_overview(session_id="web:test-memory")

    assert overview["current_context"]["session_id"] == "web:test-memory"
    assert overview["current_context"]["session_label"] == "记忆测试会话"
    assert overview["current_context"]["items"][0]["role"] == "user"
    assert overview["current_context"]["items"][0]["content"] == "第一条消息"


def test_chat_service_update_long_term_memory_persists_content(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    result = service.update_long_term_memory("# 偏好\n- 喜欢简洁回答")

    assert result["content"] == "# 偏好\n- 喜欢简洁回答"
    assert (tmp_path / "memory" / "MEMORY.md").read_text(encoding="utf-8") == "# 偏好\n- 喜欢简洁回答"


def test_chat_service_memory_overview_filters_archive_search(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    history_file = tmp_path / "memory" / "HISTORY.md"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text(
        "[2026-04-14 09:00] 讨论了上传策略\n\n[2026-04-14 10:00] 讨论了定时任务\n",
        encoding="utf-8",
    )

    overview = service.get_memory_overview(archive_query="上传")

    assert overview["archive"]["query"] == "上传"
    assert len(overview["archive"]["items"]) == 1
    assert "上传策略" in overview["archive"]["items"][0]["content"]


@pytest.mark.asyncio
async def test_memory_route_returns_service_payload(tmp_path: Path) -> None:
    expected = {
        "long_term": {"content": "", "updated_at": None, "character_count": 0, "editable": True},
        "current_context": {"session_id": None, "session_label": None, "items": []},
        "archive": {"query": "", "total": 0, "items": []},
        "settings": {
            "auto_consolidation": True,
            "template_enabled": False,
            "editable_long_term": True,
            "summary": "test",
        },
    }

    memory_routes = importlib.import_module("tokenmind.server.routes.memory")
    service = SimpleNamespace(get_memory_overview=lambda session_id=None, archive_query=None: expected)

    response = await memory_routes.get_memory_overview(service=service)

    assert response == expected
