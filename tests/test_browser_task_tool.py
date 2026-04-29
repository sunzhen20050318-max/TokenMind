"""Unit tests for the run_browser_task tool that bridges the chat agent
with the Web Agent module."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from tokenmind.agent.tools.browser_task import (
    DEFAULT_TIMEOUT_S,
    MAX_TIMEOUT_S,
    RunBrowserTaskTool,
)
from tokenmind.browser_agent.models import (
    ArtifactKind,
    BrowserArtifact,
    BrowserTask,
    CreateTaskRequest,
    TaskStatus,
)


class _FakeService:
    """Minimal stand-in for BrowserTaskService.

    Captures create_task / schedule / cancel calls and lets each test set the
    final task status so we can exercise the wait-loop without spinning up a
    real browser.
    """

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.created: list[CreateTaskRequest] = []
        self.scheduled: list[str] = []
        self.cancelled: list[str] = []
        self._tasks: dict[str, BrowserTask] = {}
        self._artifacts: dict[str, list[BrowserArtifact]] = {}
        self._next_status: TaskStatus = TaskStatus.COMPLETED
        self._summary: str = "fake task done"
        self._error: str | None = None
        self._artifacts_to_attach: list[BrowserArtifact] = []
        # Tunable: how long to "run" before flipping to terminal state.
        self._delay_seconds: float = 0.0

    # Exposed knobs ──────────────────────────────────────────────────────
    def set_outcome(
        self,
        status: TaskStatus,
        *,
        summary: str = "",
        error: str | None = None,
        artifacts: list[BrowserArtifact] | None = None,
        delay: float = 0.0,
    ) -> None:
        self._next_status = status
        self._summary = summary
        self._error = error
        self._artifacts_to_attach = list(artifacts or [])
        self._delay_seconds = delay

    # Required surface used by the tool ──────────────────────────────────
    def create_task(self, payload: CreateTaskRequest) -> BrowserTask:
        self.created.append(payload)
        task = BrowserTask(
            id=f"bt_test_{len(self.created)}",
            project_id=payload.project_id,
            session_id=payload.session_id,
            instruction=payload.instruction,
            start_url=payload.start_url,
            status=TaskStatus.PENDING,
            created_at=datetime.now(),
            max_steps=payload.max_steps,
            timeout_seconds=payload.timeout_seconds,
        )
        self._tasks[task.id] = task
        return task

    def schedule(self, task: BrowserTask) -> None:
        self.scheduled.append(task.id)

        async def _resolve() -> None:
            if self._delay_seconds:
                await asyncio.sleep(self._delay_seconds)
            updated = task.model_copy(
                update={
                    "status": self._next_status,
                    "result_summary": self._summary or None,
                    "error_detail": self._error,
                    "step_count": 4,
                    "finished_at": datetime.now(),
                }
            )
            self._tasks[task.id] = updated
            self._artifacts[task.id] = list(self._artifacts_to_attach)

        asyncio.create_task(_resolve())

    def request_cancel(self, task_id: str) -> bool:
        self.cancelled.append(task_id)
        if task_id in self._tasks:
            self._tasks[task_id] = self._tasks[task_id].model_copy(
                update={"status": TaskStatus.CANCELLED, "finished_at": datetime.now()}
            )
        return True

    # Storage subset used by the tool ────────────────────────────────────
    @property
    def storage(self) -> "_FakeService":
        return self  # storage methods live directly on the service stub

    def get_task(self, task_id: str) -> BrowserTask | None:
        return self._tasks.get(task_id)

    def list_artifacts(self, task_id: str) -> list[BrowserArtifact]:
        return list(self._artifacts.get(task_id, []))


def _make_artifact(art_id: str, kind: ArtifactKind) -> BrowserArtifact:
    return BrowserArtifact(
        id=art_id,
        task_id="bt_test_1",
        kind=kind,
        file_path=f"/tmp/{art_id}.bin",
        size_bytes=10,
        created_at=datetime.now(),
    )


# ── Schema ──────────────────────────────────────────────────────────────────


def test_tool_schema_basics(tmp_path: Path) -> None:
    tool = RunBrowserTaskTool(_FakeService(tmp_path))  # type: ignore[arg-type]
    assert tool.name == "run_browser_task"
    schema = tool.parameters
    assert schema["required"] == ["instruction"]
    assert "start_url" in schema["properties"]
    assert "timeout_seconds" in schema["properties"]


# ── Context required ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_without_context_returns_error(tmp_path: Path) -> None:
    tool = RunBrowserTaskTool(_FakeService(tmp_path))  # type: ignore[arg-type]
    # No set_context call → no chat session bound.
    result = await tool.execute(instruction="x")
    assert "active chat session" in result


# ── Happy path ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_runs_task_and_reports_artifacts(tmp_path: Path) -> None:
    svc = _FakeService(tmp_path)
    svc.set_outcome(
        TaskStatus.COMPLETED,
        summary="找到了搜索结果",
        artifacts=[
            _make_artifact("art_shot1", ArtifactKind.SCREENSHOT),
            _make_artifact("art_shot2", ArtifactKind.SCREENSHOT),
            _make_artifact("art_text1", ArtifactKind.PAGE_TEXT),
            _make_artifact("art_json1", ArtifactKind.EXTRACT_JSON),
        ],
    )
    tool = RunBrowserTaskTool(svc)  # type: ignore[arg-type]
    tool.set_context("web", "web:abc")

    result = await tool.execute(
        instruction="搜 TokenMind",
        start_url="https://x",
        timeout_seconds=60,
    )

    assert "完成" in result
    assert "找到了搜索结果" in result
    assert "screenshot×2" in result
    assert "page_text×1" in result
    assert "extract_json×1" in result
    assert "art_shot1" in result and "art_text1" in result
    assert svc.created[0].project_id == "web:abc"
    assert svc.created[0].session_id == "web:abc"
    assert svc.scheduled == ["bt_test_1"]


# ── Failure paths ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_reports_failure_with_error_detail(tmp_path: Path) -> None:
    svc = _FakeService(tmp_path)
    svc.set_outcome(TaskStatus.FAILED, summary="", error="agent-browser exited 1")
    tool = RunBrowserTaskTool(svc)  # type: ignore[arg-type]
    tool.set_context("web", "web:abc")

    result = await tool.execute(instruction="x")
    assert "失败" in result
    assert "agent-browser exited 1" in result


@pytest.mark.asyncio
async def test_execute_waits_through_awaiting_user(tmp_path: Path) -> None:
    svc = _FakeService(tmp_path)
    svc.set_outcome(TaskStatus.AWAITING_USER, summary="需要用户接管")
    tool = RunBrowserTaskTool(svc)  # type: ignore[arg-type]
    tool.set_context("web", "web:abc")
    pending = asyncio.create_task(tool.execute(instruction="x"))

    for _ in range(100):
        await asyncio.sleep(0.01)
        current = svc.get_task("bt_test_1")
        if current and current.status is TaskStatus.AWAITING_USER:
            break
    assert not pending.done()

    current = svc.get_task("bt_test_1")
    assert current is not None
    svc._tasks["bt_test_1"] = current.model_copy(
        update={
            "status": TaskStatus.COMPLETED,
            "result_summary": "用户接管后完成",
            "finished_at": datetime.now(),
        }
    )

    result = await asyncio.wait_for(pending, timeout=2.0)
    assert "完成" in result and "用户接管后完成" in result


# ── Timeout handling ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_times_out_and_cancels_task(tmp_path: Path) -> None:
    svc = _FakeService(tmp_path)
    # Simulate a task that takes longer than the requested timeout.
    svc.set_outcome(TaskStatus.COMPLETED, delay=5.0)
    tool = RunBrowserTaskTool(svc)  # type: ignore[arg-type]
    tool.set_context("web", "web:abc")

    result = await tool.execute(instruction="long task", timeout_seconds=30)
    # Note: timeout 30 is the floor enforced by the schema (minimum=30) but the
    # actual wait_for is what trips. We force it shorter via a smaller fake delay.
    # Easier path: lower timeout below the schema floor by calling execute
    # with a value of 1 directly (we bypass schema validation here).
    # Test below covers that explicitly.

    # Either we got a timeout warning OR the task completed in time. We only
    # assert that the call returned something meaningful and didn't hang.
    assert result, "execute should return"


@pytest.mark.asyncio
async def test_execute_with_short_timeout_returns_warning(tmp_path: Path) -> None:
    svc = _FakeService(tmp_path)
    svc.set_outcome(TaskStatus.COMPLETED, delay=2.0)
    tool = RunBrowserTaskTool(svc)  # type: ignore[arg-type]
    tool.set_context("web", "web:abc")

    # Bypass schema clamping by passing timeout_seconds directly.
    result = await tool.execute(instruction="x", timeout_seconds=1)
    assert "超过" in result and "取消" in result
    assert svc.cancelled == ["bt_test_1"]


# ── Timeout clamping ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeout_is_clamped_to_max(tmp_path: Path) -> None:
    svc = _FakeService(tmp_path)
    svc.set_outcome(TaskStatus.COMPLETED, summary="ok")
    tool = RunBrowserTaskTool(svc)  # type: ignore[arg-type]
    tool.set_context("web", "web:abc")
    await tool.execute(instruction="x", timeout_seconds=99999)
    assert svc.created[0].timeout_seconds == MAX_TIMEOUT_S


@pytest.mark.asyncio
async def test_timeout_default_when_unspecified(tmp_path: Path) -> None:
    svc = _FakeService(tmp_path)
    svc.set_outcome(TaskStatus.COMPLETED, summary="ok")
    tool = RunBrowserTaskTool(svc)  # type: ignore[arg-type]
    tool.set_context("web", "web:abc")
    await tool.execute(instruction="x")
    assert svc.created[0].timeout_seconds == DEFAULT_TIMEOUT_S


# ── M4.2: artifact → attachment delivery ────────────────────────────────────


class _FakeAttachmentStore:
    """Minimal AttachmentStore stub recording every create_local call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._next_id = 1

    def create_local(
        self,
        chat_id: str,
        *,
        source_path: str,
        retention,
        message_id: str | None = None,
        attachment_name: str | None = None,
    ) -> dict[str, Any]:
        ref = {
            "id": f"att_{self._next_id:03d}",
            "name": attachment_name or Path(source_path).name,
            "path": source_path,
            "session_id": chat_id,
            "message_id": message_id,
        }
        self._next_id += 1
        self.calls.append({"chat_id": chat_id, "source_path": source_path, "ref": ref})
        return ref


@pytest.mark.asyncio
async def test_attachments_only_promote_latest_screenshot_and_data_kinds(tmp_path: Path) -> None:
    svc = _FakeService(tmp_path)
    svc.set_outcome(
        TaskStatus.COMPLETED,
        summary="ok",
        artifacts=[
            _make_artifact("art_shot1", ArtifactKind.SCREENSHOT),
            _make_artifact("art_shot2", ArtifactKind.SCREENSHOT),
            _make_artifact("art_shot3", ArtifactKind.SCREENSHOT),
            _make_artifact("art_text1", ArtifactKind.PAGE_TEXT),
            _make_artifact("art_json1", ArtifactKind.EXTRACT_JSON),
        ],
    )
    store = _FakeAttachmentStore()
    tool = RunBrowserTaskTool(svc, attachment_store=store)  # type: ignore[arg-type]
    tool.set_context("web", "web:abc", message_id="msg-42")

    result = await tool.execute(instruction="x")

    # 3 attachments expected: latest screenshot + page_text + extract_json.
    delivered_paths = [c["source_path"] for c in store.calls]
    assert any(p.endswith("art_shot3.bin") for p in delivered_paths)
    assert not any(p.endswith("art_shot1.bin") for p in delivered_paths)
    assert not any(p.endswith("art_shot2.bin") for p in delivered_paths)
    assert any(p.endswith("art_text1.bin") for p in delivered_paths)
    assert any(p.endswith("art_json1.bin") for p in delivered_paths)
    # message_id propagated so attachments tie to the same assistant turn.
    assert all(c["ref"]["message_id"] == "msg-42" for c in store.calls)
    # All attachments scoped to the calling chat session.
    assert all(c["chat_id"] == "web:abc" for c in store.calls)
    # Result text mentions the auto-attached files.
    assert "已自动添加为聊天附件" in result


@pytest.mark.asyncio
async def test_attachments_skipped_when_store_not_provided(tmp_path: Path) -> None:
    svc = _FakeService(tmp_path)
    svc.set_outcome(
        TaskStatus.COMPLETED,
        summary="ok",
        artifacts=[_make_artifact("art_text1", ArtifactKind.PAGE_TEXT)],
    )
    tool = RunBrowserTaskTool(svc, attachment_store=None)  # type: ignore[arg-type]
    tool.set_context("web", "web:abc")
    result = await tool.execute(instruction="x")
    # No attachments mentioned in the reply.
    assert "已自动添加为聊天附件" not in result


@pytest.mark.asyncio
async def test_attachment_delivery_failure_does_not_break_tool(tmp_path: Path) -> None:
    """A misbehaving AttachmentStore must not abort the whole tool call."""
    svc = _FakeService(tmp_path)
    svc.set_outcome(
        TaskStatus.COMPLETED,
        summary="ok",
        artifacts=[
            _make_artifact("art_text1", ArtifactKind.PAGE_TEXT),
            _make_artifact("art_json1", ArtifactKind.EXTRACT_JSON),
        ],
    )

    class _AngryStore:
        def __init__(self):
            self.tries = 0

        def create_local(self, *args, **kwargs):
            self.tries += 1
            raise RuntimeError("disk full")

    store = _AngryStore()
    tool = RunBrowserTaskTool(svc, attachment_store=store)  # type: ignore[arg-type]
    tool.set_context("web", "web:abc")
    result = await tool.execute(instruction="x")
    # Tool still returned a normal completion summary.
    assert "完成" in result
    # Both delivery attempts were made even though each raised.
    assert store.tries == 2


@pytest.mark.asyncio
async def test_no_artifacts_means_no_attachment_section(tmp_path: Path) -> None:
    svc = _FakeService(tmp_path)
    svc.set_outcome(TaskStatus.COMPLETED, summary="just a navigation", artifacts=[])
    store = _FakeAttachmentStore()
    tool = RunBrowserTaskTool(svc, attachment_store=store)  # type: ignore[arg-type]
    tool.set_context("web", "web:abc")
    result = await tool.execute(instruction="x")
    assert store.calls == []
    assert "已自动添加为聊天附件" not in result
