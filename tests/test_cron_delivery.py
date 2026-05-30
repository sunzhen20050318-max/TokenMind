"""Tests for persisting cron results into chat sessions."""

from __future__ import annotations

from tokenmind.cron.constants import TASK_RESULTS_SESSION_ID, TASK_RESULTS_SESSION_TITLE
from tokenmind.cron.delivery import persist_task_result
from tokenmind.cron.types import CronJob, CronPayload, CronSchedule
from tokenmind.session.manager import SessionManager


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


async def test_process_direct_session_key_does_not_double_prefix():
    """When cron runs a turn in an already-prefixed session ("web:xyz"), the
    derived msg.session_key must equal that key — not "web:web:xyz". The double
    prefix used to spawn a phantom session and waste a title-gen LLM call on
    every cron delivery (title-gen and usage key off msg.session_key)."""
    from types import SimpleNamespace

    from tokenmind.agent.loop import AgentLoop

    captured: dict[str, object] = {}

    class _Shim:
        async def _connect_mcp(self) -> None:
            return None

        async def _process_message(self, msg, session_key=None, on_progress=None):
            captured["msg"] = msg
            captured["session_key"] = session_key
            return SimpleNamespace(content="ok")

        process_direct = AgentLoop.process_direct

    out = await _Shim().process_direct(
        "hello",
        session_key="web:cron-test",
        channel="web",
        chat_id="web:cron-test",
    )

    assert out == "ok"
    assert captured["session_key"] == "web:cron-test"
    # The bug: f"{channel}:{chat_id}" == "web:web:cron-test".
    assert captured["msg"].session_key == "web:cron-test"


def test_web_cron_uses_target_session_for_execution():
    """Web cron jobs should keep tool timelines in the visible delivery session."""
    from tokenmind.cli.commands import _cron_execution_session_key

    job = CronJob(
        id="abc123",
        name="reminder",
        schedule=CronSchedule(kind="at", at_ms=1770000000000),
        payload=CronPayload(
            message="send a reminder",
            deliver=True,
            channel="web",
            to=TASK_RESULTS_SESSION_ID,
        ),
    )

    assert _cron_execution_session_key(job) == TASK_RESULTS_SESSION_ID


def test_non_web_cron_keeps_internal_execution_session():
    """External channel cron jobs should not use their destination id as a session key."""
    from tokenmind.cli.commands import _cron_execution_session_key

    job = CronJob(
        id="abc123",
        name="reminder",
        schedule=CronSchedule(kind="at", at_ms=1770000000000),
        payload=CronPayload(
            message="send a reminder",
            deliver=True,
            channel="feishu",
            to="ou_user",
        ),
    )

    assert _cron_execution_session_key(job) == "cron:abc123"


def test_cron_prompt_does_not_expose_internal_delivery_instructions():
    """The stored cron trigger message should not leak scheduler-only guidance."""
    from tokenmind.cli.commands import _build_cron_prompt

    job = CronJob(
        id="abc123",
        name="test",
        schedule=CronSchedule(kind="at", at_ms=1770000000000),
        payload=CronPayload(
            message="say something encouraging",
            deliver=True,
            channel="web",
            to=TASK_RESULTS_SESSION_ID,
        ),
    )

    prompt = _build_cron_prompt(job)

    assert "say something encouraging" in prompt
    assert "请直接完成这条定时任务" not in prompt
    assert "message 工具" not in prompt
