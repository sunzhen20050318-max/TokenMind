from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
from fastapi import UploadFile


@pytest.mark.asyncio
async def test_list_knowledge_bases_returns_service_payload() -> None:
    route_module = importlib.import_module("sun_agent.server.routes.knowledge")
    service = SimpleNamespace(get_knowledge_overview=lambda: {"items": [{"id": "kb_1", "name": "测试库"}]})

    response = await route_module.list_knowledge_bases(service=service)

    assert response["items"][0]["name"] == "测试库"


@pytest.mark.asyncio
async def test_get_knowledge_base_detail_returns_service_payload() -> None:
    route_module = importlib.import_module("sun_agent.server.routes.knowledge")
    service = SimpleNamespace(
        get_knowledge_base_detail=lambda knowledge_base_id: {
            "knowledge_base": {"id": knowledge_base_id, "name": "产品库", "enabled": True},
            "documents": [],
        }
    )

    response = await route_module.get_knowledge_base_detail("kb_1", service=service)

    assert response["knowledge_base"]["name"] == "产品库"


@pytest.mark.asyncio
async def test_update_knowledge_base_returns_updated_payload() -> None:
    route_module = importlib.import_module("sun_agent.server.routes.knowledge")
    service = SimpleNamespace(
        update_knowledge_base=lambda knowledge_base_id, **kwargs: SimpleNamespace(
            model_dump=lambda: {
                "id": knowledge_base_id,
                "name": "产品库",
                "enabled": kwargs["enabled"],
            }
        )
    )

    payload = route_module.UpdateKnowledgeBasePayload(enabled=False)
    response = await route_module.update_knowledge_base("kb_1", payload, service=service)

    assert response["knowledge_base"]["enabled"] is False


@pytest.mark.asyncio
async def test_delete_knowledge_base_returns_success_payload() -> None:
    route_module = importlib.import_module("sun_agent.server.routes.knowledge")
    service = SimpleNamespace(
        delete_knowledge_base=lambda knowledge_base_id: {
            "success": True,
            "knowledge_base_id": knowledge_base_id,
        }
    )

    response = await route_module.delete_knowledge_base("kb_1", service=service)

    assert response["success"] is True
    assert response["knowledge_base_id"] == "kb_1"


def test_chat_service_exposes_update_knowledge_base(tmp_path) -> None:
    from sun_agent.server.app import ChatService

    service = ChatService(
        bus=None,
        agent_loop=None,
        session_manager=SimpleNamespace(workspace=tmp_path),
    )

    created = service.create_knowledge_base("测试库", "")
    updated = service.update_knowledge_base(created["id"], enabled=False)

    assert updated.enabled is False


def test_chat_service_exposes_delete_knowledge_base(tmp_path) -> None:
    from sun_agent.server.app import ChatService

    service = ChatService(
        bus=None,
        agent_loop=None,
        session_manager=SimpleNamespace(workspace=tmp_path),
    )

    created = service.create_knowledge_base("测试库", "")
    result = service.delete_knowledge_base(created["id"])

    assert result["success"] is True
    assert result["knowledge_base_id"] == created["id"]


@pytest.mark.asyncio
async def test_upload_knowledge_documents_returns_service_payload(tmp_path) -> None:
    route_module = importlib.import_module("sun_agent.server.routes.knowledge")
    source = tmp_path / "faq.txt"
    source.write_text("知识库文档", encoding="utf-8")
    service = SimpleNamespace(
        upload_knowledge_documents=lambda knowledge_base_id, files: {
            "documents": [{"id": "doc_1", "knowledge_base_id": knowledge_base_id, "name": files[0].filename}]
        }
    )

    upload = UploadFile(filename="faq.txt", file=source.open("rb"))
    try:
        response = await route_module.upload_knowledge_documents("kb_1", [upload], service=service)
    finally:
        await upload.close()

    assert response["documents"][0]["name"] == "faq.txt"


@pytest.mark.asyncio
async def test_delete_knowledge_document_returns_success_payload() -> None:
    route_module = importlib.import_module("sun_agent.server.routes.knowledge")
    service = SimpleNamespace(
        delete_knowledge_document=lambda knowledge_base_id, document_id: {
            "success": True,
            "knowledge_base_id": knowledge_base_id,
            "document_id": document_id,
        }
    )

    response = await route_module.delete_knowledge_document("kb_1", "doc_1", service=service)

    assert response["success"] is True
