"""Browser Agent REST + WebSocket API endpoints.

REST:
- ``POST   /api/browser-tasks``        — create + schedule a scripted task
- ``GET    /api/browser-tasks``        — list tasks (optionally by project)
- ``GET    /api/browser-tasks/{id}``   — task detail (task + steps + artifacts)
- ``POST   /api/browser-tasks/{id}/cancel`` — request cancellation
- ``GET    /api/browser-tasks/artifacts/{id}/file`` — download artifact bytes
- ``GET    /api/browser-agent/env-check`` — driver/CLI/Chrome readiness

WebSocket:
- ``WS     /api/browser-tasks/{id}/stream`` — live step / artifact / status
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from tokenmind.browser_agent.env_check import check_environment
from tokenmind.browser_agent.models import (
    CreateTaskRequest,
    EnvCheckResponse,
    TaskDetailResponse,
)
from tokenmind.browser_agent.stream import default_hub
from tokenmind.server.dependencies import get_browser_task_service

logger = logging.getLogger("tokenmind.server.routes.browser_tasks")

router = APIRouter(prefix="/api", tags=["browser-agent"])


def _service_or_503():
    service = get_browser_task_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Browser task service is not available")
    return service


@router.get("/browser-agent/env-check", response_model=EnvCheckResponse)
async def get_env_check() -> EnvCheckResponse:
    result = await check_environment()
    return EnvCheckResponse(
        cli_installed=result.cli_installed,
        chrome_installed=result.chrome_installed,
        is_ready=result.is_ready,
        version=result.version,
        issues=result.issues,
    )


@router.post("/browser-tasks")
async def create_browser_task(payload: CreateTaskRequest) -> dict:
    service = _service_or_503()
    task = service.create_task(payload)
    service.schedule(task)
    return {"task": task.model_dump()}


@router.get("/browser-tasks")
async def list_browser_tasks(
    project_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    service = _service_or_503()
    items = service.storage.list_tasks(project_id=project_id, limit=limit)
    payload = []
    for task in items:
        artifacts = service.storage.list_artifacts(task.id)
        payload.append(
            {
                "id": task.id,
                "project_id": task.project_id,
                "instruction": task.instruction,
                "status": task.status.value,
                "created_at": task.created_at.isoformat(),
                "finished_at": task.finished_at.isoformat() if task.finished_at else None,
                "step_count": task.step_count,
                "artifact_count": len(artifacts),
            }
        )
    return {"items": payload}


@router.get("/browser-tasks/{task_id}", response_model=TaskDetailResponse)
async def get_browser_task(task_id: str) -> TaskDetailResponse:
    service = _service_or_503()
    task = service.storage.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskDetailResponse(
        task=task,
        steps=service.storage.list_steps(task_id),
        artifacts=service.storage.list_artifacts(task_id),
    )


@router.post("/browser-tasks/{task_id}/cancel")
async def cancel_browser_task(task_id: str) -> dict:
    service = _service_or_503()
    task = service.storage.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    cancelled = service.request_cancel(task_id)
    return {"task_id": task_id, "cancelled": cancelled}


@router.get("/browser-tasks/artifacts/{artifact_id}/file")
async def download_browser_artifact(artifact_id: str) -> FileResponse:
    service = _service_or_503()
    artifact = service.storage.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    file_path = Path(artifact.file_path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=410, detail="Artifact file no longer exists on disk")
    media_type = artifact.mime_type or (mimetypes.guess_type(file_path.name)[0] or "application/octet-stream")
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=file_path.name,
    )


@router.websocket("/browser-tasks/{task_id}/stream")
async def stream_browser_task(websocket: WebSocket, task_id: str) -> None:
    """Live event stream for a single browser task.

    On connect we flush the replay buffer (previous steps + artifacts that
    happened before the client subscribed), then forward any new events as
    they're emitted by the TaskService until the WS closes.
    """
    await websocket.accept()
    queue, buffered = await default_hub.subscribe(task_id)
    try:
        for event in buffered:
            await websocket.send_json(event)
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("browser-task stream WS for %s crashed", task_id)
    finally:
        await default_hub.unsubscribe(task_id, queue)
