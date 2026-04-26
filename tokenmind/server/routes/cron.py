"""Cron task center API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tokenmind.audit import AuditLogger
from tokenmind.config.loader import load_config
from tokenmind.cron.constants import TASK_RESULTS_SESSION_ID, TASK_RESULTS_SESSION_TITLE
from tokenmind.cron.types import CronJob, CronSchedule
from tokenmind.server.dependencies import get_chat_service, get_cron_service

router = APIRouter(prefix="/api/cron", tags=["cron"])


class CronJobStateResponse(BaseModel):
    next_run_at_ms: int | None = None
    last_run_at_ms: int | None = None
    last_status: str | None = None
    last_error: str | None = None


class CronScheduleResponse(BaseModel):
    kind: Literal["every", "cron", "at"]
    every_ms: int | None = None
    expr: str | None = None
    tz: str | None = None
    at_ms: int | None = None
    label: str


class CronJobResponse(BaseModel):
    id: str
    name: str
    enabled: bool
    message: str
    deliver: bool
    channel: str | None = None
    to: str | None = None
    schedule: CronScheduleResponse
    state: CronJobStateResponse
    created_at_ms: int
    updated_at_ms: int
    delete_after_run: bool


class CronStatusResponse(BaseModel):
    enabled: bool
    jobs: int
    next_wake_at_ms: int | None = None


class CronJobCreateRequest(BaseModel):
    name: str
    message: str
    schedule_kind: Literal["every", "cron", "at"]
    every_seconds: int | None = None
    cron_expr: str | None = None
    tz: str | None = None
    at: str | None = None
    deliver: bool = True
    session_id: str | None = None


class CronJobToggleRequest(BaseModel):
    enabled: bool


def _require_cron_service(service=Depends(get_cron_service)):
    if service is None:
        raise HTTPException(status_code=503, detail="Cron service is not available")
    return service


def _audit() -> AuditLogger:
    return AuditLogger(load_config().workspace_path)


def _format_schedule(schedule: CronSchedule) -> str:
    def _hhmm(hour: int, minute: int) -> str:
        return f"{hour:02d}:{minute:02d}"

    if schedule.kind == "every" and schedule.every_ms:
        ms = schedule.every_ms
        if ms % 3_600_000 == 0:
            return f"每 {ms // 3_600_000} 小时"
        if ms % 60_000 == 0:
            return f"每 {ms // 60_000} 分钟"
        if ms % 1000 == 0:
            return f"每 {ms // 1000} 秒"
        return f"每 {ms} 毫秒"

    if schedule.kind == "cron" and schedule.expr:
        parts = schedule.expr.split()
        tz_suffix = f" ({schedule.tz})" if schedule.tz else ""
        if len(parts) == 5:
            minute, hour, day, month, weekday = parts
            if minute.isdigit() and hour.isdigit() and day == "*" and month == "*":
                minute_num = int(minute)
                hour_num = int(hour)
                if weekday == "*":
                    return f"每天 {_hhmm(hour_num, minute_num)}{tz_suffix}"
                if weekday == "1-5":
                    return f"工作日 {_hhmm(hour_num, minute_num)}{tz_suffix}"
                weekday_labels = {
                    "0": "每周日",
                    "1": "每周一",
                    "2": "每周二",
                    "3": "每周三",
                    "4": "每周四",
                    "5": "每周五",
                    "6": "每周六",
                    "7": "每周日",
                }
                if weekday in weekday_labels:
                    return f"{weekday_labels[weekday]} {_hhmm(hour_num, minute_num)}{tz_suffix}"
        tz = f" ({schedule.tz})" if schedule.tz else ""
        return f"cron: {schedule.expr}{tz}"

    if schedule.kind == "at" and schedule.at_ms:
        dt = datetime.fromtimestamp(schedule.at_ms / 1000, tz=timezone.utc)
        return f"单次: {dt.isoformat()}"

    return schedule.kind


def _serialize_job(job: CronJob) -> CronJobResponse:
    return CronJobResponse(
        id=job.id,
        name=job.name,
        enabled=job.enabled,
        message=job.payload.message,
        deliver=job.payload.deliver,
        channel=job.payload.channel,
        to=job.payload.to,
        schedule=CronScheduleResponse(
            kind=job.schedule.kind,
            every_ms=job.schedule.every_ms,
            expr=job.schedule.expr,
            tz=job.schedule.tz,
            at_ms=job.schedule.at_ms,
            label=_format_schedule(job.schedule),
        ),
        state=CronJobStateResponse(
            next_run_at_ms=job.state.next_run_at_ms,
            last_run_at_ms=job.state.last_run_at_ms,
            last_status=job.state.last_status,
            last_error=job.state.last_error,
        ),
        created_at_ms=job.created_at_ms,
        updated_at_ms=job.updated_at_ms,
        delete_after_run=job.delete_after_run,
    )


def _build_schedule(payload: CronJobCreateRequest) -> tuple[CronSchedule, bool]:
    if payload.schedule_kind == "every":
        if not payload.every_seconds or payload.every_seconds <= 0:
            raise HTTPException(status_code=400, detail="every_seconds must be greater than 0")
        return CronSchedule(kind="every", every_ms=payload.every_seconds * 1000), False

    if payload.schedule_kind == "cron":
        if not payload.cron_expr:
            raise HTTPException(status_code=400, detail="cron_expr is required")
        return CronSchedule(kind="cron", expr=payload.cron_expr, tz=payload.tz), False

    if payload.schedule_kind == "at":
        if not payload.at:
            raise HTTPException(status_code=400, detail="at is required")
        try:
            dt = datetime.fromisoformat(payload.at)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="Invalid datetime format. Expected YYYY-MM-DDTHH:MM:SS",
            ) from exc
        return CronSchedule(kind="at", at_ms=int(dt.timestamp() * 1000)), False

    raise HTTPException(status_code=400, detail="Unsupported schedule type")


@router.get("/status", response_model=CronStatusResponse)
async def get_cron_status(service=Depends(_require_cron_service)):
    """Get cron runtime status."""
    return service.status()


@router.get("/jobs", response_model=list[CronJobResponse])
async def list_cron_jobs(include_disabled: bool = True, service=Depends(_require_cron_service)):
    """List cron jobs for the task center."""
    return [_serialize_job(job) for job in service.list_jobs(include_disabled=include_disabled)]


@router.post("/jobs", response_model=CronJobResponse)
async def create_cron_job(payload: CronJobCreateRequest, service=Depends(_require_cron_service)):
    """Create a cron job."""
    name = payload.name.strip()
    message = payload.message.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    schedule, delete_after_run = _build_schedule(payload)
    target_session_id = payload.session_id
    if payload.deliver and not target_session_id:
        target_session_id = TASK_RESULTS_SESSION_ID

    try:
        job = service.add_job(
            name=name,
            schedule=schedule,
            message=message,
            deliver=payload.deliver and bool(target_session_id),
            channel="web" if payload.deliver and target_session_id else None,
            to=target_session_id if payload.deliver else None,
            delete_after_run=delete_after_run,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if job.payload.deliver and job.payload.to == TASK_RESULTS_SESSION_ID:
        chat_service = get_chat_service()
        if chat_service is not None:
            chat_service.ensure_session(TASK_RESULTS_SESSION_ID, TASK_RESULTS_SESSION_TITLE)

    _audit().record(
        "cron.job.created",
        "success",
        actor="web_user",
        details={
            "job_id": job.id,
            "name": job.name,
            "schedule_kind": job.schedule.kind,
            "deliver": job.payload.deliver,
            "target_session": job.payload.to,
        },
    )
    return _serialize_job(job)


@router.post("/jobs/{job_id}/toggle", response_model=CronJobResponse)
async def toggle_cron_job(
    job_id: str,
    payload: CronJobToggleRequest,
    service=Depends(_require_cron_service),
):
    """Enable or disable a cron job."""
    job = service.enable_job(job_id, enabled=payload.enabled)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    _audit().record(
        "cron.job.toggled",
        "success",
        actor="web_user",
        details={"job_id": job_id, "enabled": payload.enabled},
    )
    return _serialize_job(job)


@router.post("/jobs/{job_id}/run")
async def run_cron_job(job_id: str, service=Depends(_require_cron_service)):
    """Run a cron job immediately."""
    ok = await service.run_job(job_id, force=True)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    _audit().record(
        "cron.job.run",
        "success",
        actor="web_user",
        details={"job_id": job_id, "forced": True},
    )
    return {"success": True, "job_id": job_id}


@router.delete("/jobs/{job_id}")
async def delete_cron_job(job_id: str, service=Depends(_require_cron_service)):
    """Delete a cron job."""
    removed = service.remove_job(job_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    _audit().record(
        "cron.job.deleted",
        "success",
        actor="web_user",
        details={"job_id": job_id},
    )
    return {"success": True, "job_id": job_id}
