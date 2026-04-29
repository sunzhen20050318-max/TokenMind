"""Tests for the M3.3 takeover / resume / intervene REST endpoints."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from tokenmind.browser_agent.models import (
    BrowserTask,
    CreateTaskRequest,
    TaskStatus,
)
from tokenmind.browser_agent.task_service import BrowserTaskService
from tokenmind.server.dependencies import set_browser_task_service
from tokenmind.server.routes.browser_tasks import router as browser_tasks_router


class _FakeCLI:
    """Minimal CLI stub that records every call so we can assert on them."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def _record(self, name: str, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    async def click_xy(self, project_id, x, y, *, button="left", timeout=30.0):
        self._record("click_xy", project_id, x, y, button=button)
        return {"success": True, "data": {}, "error": None}

    async def keyboard_type(self, project_id, text, *, timeout=30.0):
        self._record("keyboard_type", project_id, text)
        return {"success": True, "data": {}, "error": None}

    async def press(self, project_id, key, timeout=30.0):
        self._record("press", project_id, key)
        return {"success": True, "data": {}, "error": None}

    async def scroll(self, project_id, direction, pixels=None, timeout=15.0):
        self._record("scroll", project_id, direction, pixels=pixels)
        return {"success": True, "data": {}, "error": None}

    async def open_url(self, project_id, url, timeout=60.0):
        self._record("open_url", project_id, url)
        return {"success": True, "data": {}, "error": None}

    async def back(self, project_id, timeout=30.0):
        self._record("back", project_id)
        return {"success": True, "data": {}, "error": None}

    async def forward(self, project_id, timeout=30.0):
        self._record("forward", project_id)
        return {"success": True, "data": {}, "error": None}

    async def reload(self, project_id, timeout=30.0):
        self._record("reload", project_id)
        return {"success": True, "data": {}, "error": None}

    async def wait(self, project_id, target, timeout=30.0):
        self._record("wait", project_id, target)
        return {"success": True, "data": {}, "error": None}

    async def close_session(self, project_id):
        self._record("close_session", project_id)


def _make_task_in_status(svc: BrowserTaskService, status: TaskStatus) -> BrowserTask:
    """Insert a task directly in storage so we don't need to run the loop."""
    task = svc.create_task(
        CreateTaskRequest(project_id="proj_a", instruction="x", start_url="https://x")
    )
    svc.storage.update_task(task.id, status=status)
    refreshed = svc.storage.get_task(task.id)
    assert refreshed is not None
    # Some endpoints peek at the cancellation map to decide whether to accept
    # takeover. Simulate a "live" task by registering an event.
    if status in (TaskStatus.RUNNING, TaskStatus.AWAITING_USER):
        svc._cancellation[refreshed.id] = asyncio.Event()
        svc._resume[refreshed.id] = asyncio.Event()
    return refreshed


@pytest.fixture
def app_and_svc(tmp_path: Path):
    cli = _FakeCLI()
    svc = BrowserTaskService(tmp_path, cli=cli)
    set_browser_task_service(svc)
    app = FastAPI()
    app.include_router(browser_tasks_router)
    return app, svc, cli


@pytest.mark.asyncio
async def test_takeover_accepts_running_task(app_and_svc) -> None:
    app, svc, _ = app_and_svc
    task = _make_task_in_status(svc, TaskStatus.RUNNING)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/api/browser-tasks/{task.id}/takeover",
            json={"reason": "我来"},
        )
    assert r.status_code == 200
    assert r.json()["accepted"] is True


@pytest.mark.asyncio
async def test_takeover_rejects_completed_task(app_and_svc) -> None:
    app, svc, _ = app_and_svc
    task = _make_task_in_status(svc, TaskStatus.COMPLETED)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/api/browser-tasks/{task.id}/takeover",
            json={"reason": "x"},
        )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_resume_only_works_in_awaiting_user(app_and_svc) -> None:
    app, svc, _ = app_and_svc
    running = _make_task_in_status(svc, TaskStatus.RUNNING)
    awaiting = _make_task_in_status(svc, TaskStatus.AWAITING_USER)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post(f"/api/browser-tasks/{running.id}/resume")
        r2 = await client.post(f"/api/browser-tasks/{awaiting.id}/resume")
    assert r1.status_code == 409
    assert r2.status_code == 200
    assert r2.json()["resumed"] is True


@pytest.mark.asyncio
async def test_resume_accepts_user_note(app_and_svc) -> None:
    app, svc, _ = app_and_svc
    awaiting = _make_task_in_status(svc, TaskStatus.AWAITING_USER)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/api/browser-tasks/{awaiting.id}/resume",
            json={"note": "我已经完成登录"},
        )
    assert r.status_code == 200
    assert r.json()["resumed"] is True
    assert svc._resume_notes[awaiting.id] == "我已经完成登录"


@pytest.mark.asyncio
async def test_intervene_click_xy_forwards_to_cli(app_and_svc) -> None:
    app, svc, cli = app_and_svc
    task = _make_task_in_status(svc, TaskStatus.AWAITING_USER)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/api/browser-tasks/{task.id}/intervene",
            json={"action": "click_xy", "args": {"x": 100, "y": 200}},
        )
    assert r.status_code == 200, r.text
    names = [c[0] for c in cli.calls]
    assert names == ["click_xy"]
    assert cli.calls[0][1] == ("proj_a", 100, 200)
    # Step recorded with phase=intervention.
    steps = svc.storage.list_steps(task.id)
    assert any(s.action_name == "user:click_xy" for s in steps)


@pytest.mark.asyncio
async def test_intervene_type_uses_keyboard_type(app_and_svc) -> None:
    app, svc, cli = app_and_svc
    task = _make_task_in_status(svc, TaskStatus.AWAITING_USER)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/api/browser-tasks/{task.id}/intervene",
            json={"action": "type", "args": {"text": "Hello, 世界"}},
        )
    assert r.status_code == 200
    assert cli.calls[0][0] == "keyboard_type"
    assert cli.calls[0][1] == ("proj_a", "Hello, 世界")


@pytest.mark.asyncio
async def test_intervene_rejects_when_not_awaiting_user(app_and_svc) -> None:
    app, svc, _ = app_and_svc
    task = _make_task_in_status(svc, TaskStatus.RUNNING)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/api/browser-tasks/{task.id}/intervene",
            json={"action": "click_xy", "args": {"x": 1, "y": 1}},
        )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_intervene_validates_required_args(app_and_svc) -> None:
    app, svc, _ = app_and_svc
    task = _make_task_in_status(svc, TaskStatus.AWAITING_USER)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/api/browser-tasks/{task.id}/intervene",
            json={"action": "click_xy", "args": {"x": 100}},  # missing y
        )
    assert r.status_code == 400
    assert "缺少" in r.json()["detail"]


@pytest.mark.asyncio
async def test_intervene_rejects_unknown_action(app_and_svc) -> None:
    app, svc, _ = app_and_svc
    task = _make_task_in_status(svc, TaskStatus.AWAITING_USER)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/api/browser-tasks/{task.id}/intervene",
            json={"action": "teleport", "args": {}},
        )
    # Pydantic Literal rejection → 422
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_filters_by_session_id(app_and_svc) -> None:
    """Tasks scoped to a chat session are filtered by ?session_id=."""
    app, svc, _ = app_and_svc

    a = svc.create_task(
        CreateTaskRequest(
            project_id="proj_a",
            instruction="task A",
            start_url="https://x",
            session_id="web:abc",
        )
    )
    b = svc.create_task(
        CreateTaskRequest(
            project_id="proj_a",
            instruction="task B",
            start_url="https://x",
            session_id="web:other",
        )
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        all_resp = await client.get("/api/browser-tasks")
        scoped = await client.get("/api/browser-tasks?session_id=web:abc")

    assert {item["id"] for item in all_resp.json()["items"]} == {a.id, b.id}
    scoped_items = scoped.json()["items"]
    assert {item["id"] for item in scoped_items} == {a.id}
    assert scoped_items[0]["session_id"] == "web:abc"


@pytest.mark.asyncio
async def test_continue_completed_task_reuses_same_task(app_and_svc) -> None:
    app, svc, _ = app_and_svc
    task = _make_task_in_status(svc, TaskStatus.COMPLETED)
    scheduled: list[str] = []
    svc.schedule = lambda next_task: scheduled.append(next_task.id)  # type: ignore[method-assign]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/api/browser-tasks/{task.id}/continue",
            json={"instruction": "继续当前页面，保存页面文本"},
        )

    assert r.status_code == 200, r.text
    payload = r.json()["task"]
    assert payload["id"] == task.id
    assert payload["status"] == "pending"
    assert payload["instruction"] == "继续当前页面，保存页面文本"
    assert scheduled == [task.id]


@pytest.mark.asyncio
async def test_continue_rejects_non_terminal_task(app_and_svc) -> None:
    app, svc, _ = app_and_svc
    task = _make_task_in_status(svc, TaskStatus.RUNNING)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/api/browser-tasks/{task.id}/continue",
            json={"instruction": "继续"},
        )

    assert r.status_code == 409


@pytest.mark.asyncio
async def test_intervene_returns_502_on_cli_error(app_and_svc) -> None:
    app, svc, cli = app_and_svc

    async def angry_click(*args, **kwargs):
        from tokenmind.browser_agent.cli import AgentBrowserError
        raise AgentBrowserError("simulated CLI failure")

    cli.click_xy = angry_click  # type: ignore[assignment]
    task = _make_task_in_status(svc, TaskStatus.AWAITING_USER)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/api/browser-tasks/{task.id}/intervene",
            json={"action": "click_xy", "args": {"x": 1, "y": 2}},
        )
    assert r.status_code == 502
