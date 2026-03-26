"""Helpers for persisting cron job results into chat sessions."""

from __future__ import annotations

from datetime import datetime

from sun_agent.cron.constants import TASK_RESULTS_SESSION_ID, TASK_RESULTS_SESSION_TITLE
from sun_agent.session.manager import SessionManager


def build_task_trigger_message(job_name: str, instruction: str, triggered_at: datetime | None = None) -> str:
    """Create the user-visible trigger note stored before a cron response."""
    moment = triggered_at or datetime.now()
    return (
        f"[定时任务] {job_name}\n\n"
        f"触发时间：{moment.strftime('%m-%d %H:%M')}\n"
        f"任务说明：{instruction}"
    )


def persist_task_result(
    session_manager: SessionManager,
    session_id: str,
    job_name: str,
    instruction: str,
    response: str,
) -> None:
    """Persist a cron trigger note and its response into the target session."""
    session = session_manager.get_or_create(session_id)
    if session_id == TASK_RESULTS_SESSION_ID:
        session.set_title(TASK_RESULTS_SESSION_TITLE)

    session.add_message("user", build_task_trigger_message(job_name, instruction))
    session.add_message("assistant", response)
    session_manager.save(session)
