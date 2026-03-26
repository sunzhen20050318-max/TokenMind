"""Tests for cron task center route helpers."""

from __future__ import annotations

import pytest


@pytest.fixture
def temp_cron_service(tmp_path):
    """Bind route globals to a temporary cron service."""
    from sun_agent.cron.service import CronService
    from sun_agent.server.dependencies import get_cron_service, set_cron_service

    previous = get_cron_service()
    service = CronService(tmp_path / "cron" / "jobs.json")
    set_cron_service(service)
    try:
        yield service
    finally:
        set_cron_service(previous)


@pytest.mark.asyncio
async def test_create_list_toggle_run_and_delete_cron_jobs(temp_cron_service):
    """Cron routes should support the task center lifecycle."""
    from sun_agent.server.routes.cron import (
        CronJobCreateRequest,
        CronJobToggleRequest,
        create_cron_job,
        delete_cron_job,
        get_cron_status,
        list_cron_jobs,
        run_cron_job,
        toggle_cron_job,
    )

    created = await create_cron_job(
        CronJobCreateRequest(
            name="晨间简报",
            message="每天早上整理今天的重要事项",
            schedule_kind="cron",
            cron_expr="0 9 * * 1-5",
            tz="Asia/Shanghai",
            deliver=True,
            session_id="web:test-session",
        ),
        temp_cron_service,
    )

    assert created.name == "晨间简报"
    assert created.deliver is True
    assert created.schedule.kind == "cron"

    jobs = await list_cron_jobs(True, temp_cron_service)
    assert len(jobs) == 1
    assert jobs[0].schedule.label == "工作日 09:00 (Asia/Shanghai)"

    toggled = await toggle_cron_job(
        created.id,
        CronJobToggleRequest(enabled=False),
        temp_cron_service,
    )
    assert toggled.enabled is False

    ran = await run_cron_job(created.id, temp_cron_service)
    assert ran["success"] is True

    status = await get_cron_status(temp_cron_service)
    assert status["jobs"] == 1

    deleted = await delete_cron_job(created.id, temp_cron_service)
    assert deleted["success"] is True
    assert await list_cron_jobs(True, temp_cron_service) == []


@pytest.mark.asyncio
async def test_create_cron_job_validates_payload(temp_cron_service):
    """Cron routes should reject invalid schedule payloads."""
    from fastapi import HTTPException

    from sun_agent.server.routes.cron import CronJobCreateRequest, create_cron_job

    with pytest.raises(HTTPException, match="every_seconds must be greater than 0"):
        await create_cron_job(
            CronJobCreateRequest(
                name="bad",
                message="hello",
                schedule_kind="every",
                every_seconds=0,
            ),
            temp_cron_service,
        )


@pytest.mark.asyncio
async def test_create_cron_job_defaults_to_task_results_session(temp_cron_service):
    """Deliverable jobs without an explicit session should target the task results session."""
    from sun_agent.cron.constants import TASK_RESULTS_SESSION_ID
    from sun_agent.server.routes.cron import CronJobCreateRequest, create_cron_job

    created = await create_cron_job(
        CronJobCreateRequest(
            name="digest",
            message="summarize today's updates",
            schedule_kind="every",
            every_seconds=3600,
            deliver=True,
        ),
        temp_cron_service,
    )

    assert created.deliver is True
    assert created.to == TASK_RESULTS_SESSION_ID
