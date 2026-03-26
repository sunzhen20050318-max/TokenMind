"""Tests for persisting cron results into chat sessions."""

from __future__ import annotations

from sun_agent.cron.constants import TASK_RESULTS_SESSION_ID, TASK_RESULTS_SESSION_TITLE
from sun_agent.cron.delivery import persist_task_result
from sun_agent.session.manager import SessionManager


def test_persist_task_result_creates_task_results_session(tmp_path):
    """Cron delivery should create and label the dedicated task results session."""
    manager = SessionManager(tmp_path)

    persist_task_result(
        session_manager=manager,
        session_id=TASK_RESULTS_SESSION_ID,
        job_name="daily digest",
        instruction="summarize today's updates",
        response="Here is today's summary.",
    )

    session = manager.get_or_create(TASK_RESULTS_SESSION_ID)
    assert session.title == TASK_RESULTS_SESSION_TITLE
    assert len(session.messages) == 2
    assert session.messages[0]["role"] == "user"
    assert "daily digest" in session.messages[0]["content"]
    assert session.messages[1]["role"] == "assistant"
    assert session.messages[1]["content"] == "Here is today's summary."
