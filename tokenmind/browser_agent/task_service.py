"""Browser task lifecycle: create, execute (M1 = scripted), persist artifacts.

In M1 the execution loop is **scripted** — it always runs:
``open(start_url) → snapshot → screenshot``. This proves the full pipeline
(CLI subprocess → JSON → file artifact → DB record → REST response) works
end-to-end before we wire LLM-driven decisions in M2.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional

from tokenmind.browser_agent.cli import AgentBrowserCLI, AgentBrowserError
from tokenmind.browser_agent.env_check import check_environment
from tokenmind.browser_agent.models import (
    ArtifactKind,
    BrowserArtifact,
    BrowserStep,
    BrowserTask,
    CreateTaskRequest,
    StepPhase,
    TaskStatus,
)
from tokenmind.browser_agent.storage import BrowserTaskStorage

logger = logging.getLogger("tokenmind.browser_agent.task_service")


class BrowserTaskService:
    """Coordinates task creation, execution, and artifact persistence."""

    def __init__(
        self,
        workspace: Path,
        *,
        cli: Optional[AgentBrowserCLI] = None,
        storage: Optional[BrowserTaskStorage] = None,
    ) -> None:
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.cli = cli or AgentBrowserCLI()
        self.storage = storage or BrowserTaskStorage(self.workspace)
        self.artifacts_root = self.workspace / "browser"
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        self._cancellation: dict[str, asyncio.Event] = {}
        self._running_tasks: set[asyncio.Task[None]] = set()

    @staticmethod
    def _new_id(prefix: str) -> str:
        suffix = secrets.token_hex(4)
        return f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}_{suffix}"

    # ── public API ──────────────────────────────────────────────────────

    def create_task(self, payload: CreateTaskRequest) -> BrowserTask:
        task = BrowserTask(
            id=self._new_id("bt"),
            project_id=payload.project_id,
            session_id=payload.session_id,
            instruction=payload.instruction,
            start_url=payload.start_url,
            status=TaskStatus.PENDING,
            created_at=datetime.now(),
            max_steps=payload.max_steps,
            timeout_seconds=payload.timeout_seconds,
        )
        self.storage.insert_task(task)
        return task

    def schedule(self, task: BrowserTask) -> None:
        """Kick off background execution. Safe to call from a sync context."""
        loop_task = asyncio.create_task(self._run(task))
        self._running_tasks.add(loop_task)
        loop_task.add_done_callback(self._running_tasks.discard)

    def request_cancel(self, task_id: str) -> bool:
        """Signal cancellation. Returns False when the task isn't running."""
        event = self._cancellation.get(task_id)
        if event is None:
            return False
        event.set()
        return True

    # ── execution loop (M1 = scripted) ──────────────────────────────────

    async def _run(self, task: BrowserTask) -> None:
        cancel = asyncio.Event()
        self._cancellation[task.id] = cancel
        try:
            await self._execute(task, cancel)
        finally:
            self._cancellation.pop(task.id, None)

    async def _execute(self, task: BrowserTask, cancel: asyncio.Event) -> None:
        env = await check_environment()
        if not env.is_ready:
            self._mark_failed(task, "环境未就绪：" + "；".join(env.issues))
            return

        self.storage.update_task(
            task.id,
            status=TaskStatus.RUNNING,
            started_at=datetime.now(),
        )

        step_index = 0
        try:
            # Step 1: open the start URL.
            if task.start_url:
                if cancel.is_set():
                    self._mark_cancelled(task)
                    return
                step_index += 1
                self._record_step(
                    task,
                    step_index,
                    StepPhase.ACTION,
                    action_name="open",
                    action_args={"url": task.start_url},
                    success=True,
                )
                try:
                    await self.cli.open_url(task.project_id, task.start_url)
                except AgentBrowserError as exc:
                    self._record_step(
                        task,
                        step_index,
                        StepPhase.ACTION,
                        action_name="open",
                        action_args={"url": task.start_url},
                        success=False,
                        error=str(exc),
                    )
                    self._mark_failed(task, f"打开起始页失败：{exc}")
                    return

            # Step 2: snapshot the page so the user can verify reachability.
            if cancel.is_set():
                self._mark_cancelled(task)
                return
            step_index += 1
            try:
                snap = await self.cli.snapshot(task.project_id)
                snap_data = snap.get("data", {})
                observation = snap_data.get("snapshot") or ""
                self._record_step(
                    task,
                    step_index,
                    StepPhase.OBSERVATION,
                    action_name="snapshot",
                    action_args={"interactive": True},
                    observation=observation[:4000],
                    success=True,
                )
            except AgentBrowserError as exc:
                self._record_step(
                    task,
                    step_index,
                    StepPhase.OBSERVATION,
                    action_name="snapshot",
                    success=False,
                    error=str(exc),
                )
                self._mark_failed(task, f"snapshot 失败：{exc}")
                return

            # Step 3: take a screenshot artifact so the UI has something to show.
            if cancel.is_set():
                self._mark_cancelled(task)
                return
            step_index += 1
            screenshot_path = self._artifact_path(task, step_index, "screenshots", ".png")
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                shot = await self.cli.screenshot(task.project_id, str(screenshot_path))
                artifact = self._record_artifact(
                    task,
                    step_index,
                    ArtifactKind.SCREENSHOT,
                    file_path=screenshot_path,
                    mime_type="image/png",
                    metadata={"agent_browser": shot.get("data", {})},
                )
                self._record_step(
                    task,
                    step_index,
                    StepPhase.ACTION,
                    action_name="screenshot",
                    success=True,
                    screenshot_artifact_id=artifact.id,
                )
            except AgentBrowserError as exc:
                self._record_step(
                    task,
                    step_index,
                    StepPhase.ACTION,
                    action_name="screenshot",
                    success=False,
                    error=str(exc),
                )
                self._mark_failed(task, f"截图失败：{exc}")
                return

            # Done — task complete.
            self.storage.update_task(
                task.id,
                status=TaskStatus.COMPLETED,
                finished_at=datetime.now(),
                step_count=step_index,
                result_summary=f"已打开 {task.start_url or '起始页'} 并完成截图。",
            )
        finally:
            # Always close the session so subsequent runs get a fresh tab.
            await self.cli.close_session(task.project_id)

    # ── persistence helpers ─────────────────────────────────────────────

    def _record_step(
        self,
        task: BrowserTask,
        step_index: int,
        phase: StepPhase,
        *,
        action_name: Optional[str] = None,
        action_args: Optional[dict] = None,
        observation: Optional[str] = None,
        thinking: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
        screenshot_artifact_id: Optional[str] = None,
    ) -> None:
        step = BrowserStep(
            id=self._new_id("st"),
            task_id=task.id,
            step_index=step_index,
            phase=phase,
            action_name=action_name,
            action_args=action_args,
            thinking=thinking,
            observation=observation,
            screenshot_artifact_id=screenshot_artifact_id,
            success=success,
            error=error,
            timestamp=datetime.now(),
        )
        self.storage.insert_step(step)
        self.storage.update_task(task.id, step_count=step_index)

    def _record_artifact(
        self,
        task: BrowserTask,
        step_index: int,
        kind: ArtifactKind,
        *,
        file_path: Path,
        mime_type: Optional[str] = None,
        source_url: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> BrowserArtifact:
        size = file_path.stat().st_size if file_path.exists() else 0
        artifact = BrowserArtifact(
            id=self._new_id("art"),
            task_id=task.id,
            step_index=step_index,
            kind=kind,
            file_path=str(file_path.resolve()),
            source_url=source_url,
            mime_type=mime_type,
            size_bytes=size,
            created_at=datetime.now(),
            metadata=metadata or {},
        )
        self.storage.insert_artifact(artifact)
        return artifact

    def _artifact_path(
        self,
        task: BrowserTask,
        step_index: int,
        subdir: str,
        suffix: str,
    ) -> Path:
        return (
            self.artifacts_root
            / subdir
            / f"{task.id}_step_{step_index:03d}{suffix}"
        )

    def _mark_failed(self, task: BrowserTask, error: str) -> None:
        logger.warning("Task %s failed: %s", task.id, error)
        self.storage.update_task(
            task.id,
            status=TaskStatus.FAILED,
            error_detail=error,
            finished_at=datetime.now(),
        )

    def _mark_cancelled(self, task: BrowserTask) -> None:
        self.storage.update_task(
            task.id,
            status=TaskStatus.CANCELLED,
            finished_at=datetime.now(),
        )
