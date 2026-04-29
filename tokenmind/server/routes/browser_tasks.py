"""Browser Agent REST + WebSocket API endpoints.

REST:
- ``POST   /api/browser-tasks``        — create + schedule a scripted task
- ``GET    /api/browser-tasks``        — list tasks (optionally by project)
- ``GET    /api/browser-tasks/{id}``   — task detail (task + steps + artifacts)
- ``POST   /api/browser-tasks/{id}/continue`` — append another instruction
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
from typing import Any, Literal, Optional

from fastapi import APIRouter, Body, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from tokenmind.browser_agent.cli import AgentBrowserError
from tokenmind.browser_agent.env_check import check_environment
from tokenmind.browser_agent.models import (
    ContinueTaskRequest,
    CreateTaskRequest,
    EnvCheckResponse,
    TaskDetailResponse,
    TaskStatus,
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
    session_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    service = _service_or_503()
    items = service.storage.list_tasks(project_id=project_id, limit=limit)
    if session_id:
        # session_id filter is post-storage because the SQLite query already
        # filters by project_id; tasks created via the chat tool tag the
        # session id directly so this stays cheap (≤ limit rows).
        items = [t for t in items if (t.session_id or "") == session_id]
    payload = []
    for task in items:
        artifacts = service.storage.list_artifacts(task.id)
        payload.append(
            {
                "id": task.id,
                "project_id": task.project_id,
                "session_id": task.session_id,
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


@router.post("/browser-tasks/{task_id}/continue")
async def continue_browser_task(task_id: str, payload: ContinueTaskRequest) -> dict:
    service = _service_or_503()
    try:
        task = service.continue_task(task_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    service.schedule(task)
    return {"task": task.model_dump()}


@router.post("/browser-tasks/{task_id}/cancel")
async def cancel_browser_task(task_id: str) -> dict:
    service = _service_or_503()
    task = service.storage.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    cancelled = service.request_cancel(task_id)
    return {"task_id": task_id, "cancelled": cancelled}


# ── M3.3: takeover / resume / intervene ────────────────────────────────────


class TakeoverRequest(BaseModel):
    reason: str = "用户主动接管"


class ResumeRequest(BaseModel):
    note: Optional[str] = None


@router.post("/browser-tasks/{task_id}/takeover")
async def takeover_browser_task(task_id: str, payload: TakeoverRequest) -> dict:
    """User asks to pause the AI loop and intervene manually."""
    service = _service_or_503()
    task = service.storage.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in (TaskStatus.RUNNING, TaskStatus.AWAITING_USER):
        raise HTTPException(
            status_code=409,
            detail=f"Task is in status '{task.status.value}', cannot take over",
        )
    accepted = service.request_takeover(task_id, payload.reason)
    return {"task_id": task_id, "accepted": accepted}


@router.post("/browser-tasks/{task_id}/resume")
async def resume_browser_task(
    task_id: str,
    payload: Optional[ResumeRequest] = Body(default=None),
) -> dict:
    """Hand control back to the AI after a user takeover."""
    service = _service_or_503()
    task = service.storage.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status is not TaskStatus.AWAITING_USER:
        raise HTTPException(
            status_code=409,
            detail=f"Task is in status '{task.status.value}', not awaiting user",
        )
    accepted = service.request_resume(task_id, note=payload.note if payload else None)
    return {"task_id": task_id, "resumed": accepted}


class InterveneRequest(BaseModel):
    """User-initiated browser action while the task is in awaiting_user.

    The frontend can post fallback keyboard/navigation actions while the user
    directly controls the visible local browser window. ``action`` selects which
    CLI primitive to invoke;
    extra keys are forwarded as positional/keyword args.
    """

    action: Literal[
        "click_xy",
        "type",
        "press",
        "scroll",
        "open",
        "back",
        "forward",
        "reload",
        "wait",
    ]
    args: dict[str, Any] = Field(default_factory=dict)


@router.post("/browser-tasks/{task_id}/intervene")
async def intervene_browser_task(task_id: str, payload: InterveneRequest) -> dict:
    """Forward a single user action to the underlying agent-browser session.

    Only valid while the task is ``awaiting_user`` — that's the contract:
    AI is paused, the user owns the browser.
    """
    service = _service_or_503()
    task = service.storage.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status is not TaskStatus.AWAITING_USER:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot intervene while task is '{task.status.value}'",
        )

    cli = service.cli
    project_id = task.project_id
    args = payload.args
    try:
        if payload.action == "click_xy":
            await cli.click_xy(
                project_id,
                int(_require_arg(args, "x")),
                int(_require_arg(args, "y")),
                button=str(args.get("button", "left")),
            )
        elif payload.action == "type":
            # Empty-text typing is allowed (clear focus + no input). Use
            # keyboard_type because the user may not have a selector.
            text = str(args.get("text", ""))
            await cli.keyboard_type(project_id, text)
        elif payload.action == "press":
            await cli.press(project_id, str(_require_arg(args, "key")))
        elif payload.action == "scroll":
            direction = str(_require_arg(args, "direction"))
            pixels_raw = args.get("pixels")
            pixels = int(pixels_raw) if pixels_raw is not None else None
            await cli.scroll(project_id, direction, pixels=pixels)
        elif payload.action == "open":
            await cli.open_url(project_id, str(_require_arg(args, "url")))
        elif payload.action == "back":
            await cli.back(project_id)
        elif payload.action == "forward":
            await cli.forward(project_id)
        elif payload.action == "reload":
            await cli.reload(project_id)
        elif payload.action == "wait":
            await cli.wait(project_id, str(_require_arg(args, "target")))
    except AgentBrowserError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Mirror the action into the task timeline so the UI step list shows the
    # user's input alongside the AI's prior steps.
    from datetime import datetime as _dt

    from tokenmind.browser_agent.models import BrowserStep, StepPhase

    step_index = (task.step_count or 0) + 1
    step = BrowserStep(
        id=service._new_id("st"),
        task_id=task_id,
        step_index=step_index,
        phase=StepPhase.INTERVENTION,
        action_name=f"user:{payload.action}",
        action_args=args,
        success=True,
        timestamp=_dt.now(),
    )
    service.storage.insert_step(step)
    service.storage.update_task(task_id, step_count=step_index)
    await default_hub.emit(
        task_id, {"type": "step", "step": step.model_dump(mode="json")}
    )

    return {"task_id": task_id, "action": payload.action, "ok": True}


def _require_arg(args: dict[str, Any], key: str) -> Any:
    if key not in args or args[key] in (None, ""):
        raise ValueError(f"intervene 缺少必填参数 '{key}'")
    return args[key]


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
