from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_list_projects_route_returns_service_payload() -> None:
    routes = importlib.import_module("tokenmind.server.routes.projects")
    service = SimpleNamespace(list_projects=lambda: {"items": [{"id": "proj_1", "name": "Release Plan"}]})

    response = await routes.list_projects(service=service)

    assert response["items"][0]["name"] == "Release Plan"


@pytest.mark.asyncio
async def test_delete_project_route_returns_service_payload() -> None:
    routes = importlib.import_module("tokenmind.server.routes.projects")
    service = SimpleNamespace(
        delete_project=lambda project_id: {"success": True, "project_id": project_id, "deleted_session_count": 2}
    )

    response = await routes.delete_project("proj_1", service=service)

    assert response == {"success": True, "project_id": "proj_1", "deleted_session_count": 2}
