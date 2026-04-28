"""Browser task lifecycle: create, execute (LLM-driven ReAct), persist artifacts.

The execution loop is the ReAct pattern:

1. (optional) open the start URL
2. snapshot the page → record as observation
3. ask the LLM for the next action
4. execute the action via AgentBrowserCLI
5. snapshot again as observation
6. repeat until LLM emits ``finish`` / max_steps reached / cancellation

Each LLM action is recorded as a step (phase=ACTION) and each snapshot as a
step (phase=OBSERVATION). Screenshots are taken automatically at every action
so the UI has visual frames to play back.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from tokenmind.browser_agent.cli import AgentBrowserCLI, AgentBrowserError
from tokenmind.browser_agent.decision import (
    Decision,
    DecisionMaker,
    DecisionParseError,
)
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


# Type alias for the optional LLM provider factory. The TaskService doesn't
# import config or providers directly (keeping the package decoupled from the
# main agent runtime); instead callers inject either a DecisionMaker or a
# zero-arg factory that returns one. When neither is supplied the service
# falls back to the M1 scripted loop.
DecisionMakerFactory = Callable[[BrowserTask], Awaitable[DecisionMaker] | DecisionMaker]

# Optional WebSocket emitter. Each call should be awaitable so route layers
# can fan out to many subscribers. None disables streaming.
EventEmitter = Callable[[str, dict[str, Any]], Awaitable[None]]


# How much snapshot text we keep in storage / feed to the LLM. Real-world
# pages can produce >50KB; we cap to avoid token blowup. The LLM gets the
# trimmed version so its decisions are deterministic w.r.t. what we stored.
_MAX_SNAPSHOT_CHARS = 6000

# Cap the structured "observation" (e.g. extracted text) likewise.
_MAX_OBSERVATION_CHARS = 4000


class BrowserTaskService:
    """Coordinates task creation, execution, and artifact persistence."""

    def __init__(
        self,
        workspace: Path,
        *,
        cli: Optional[AgentBrowserCLI] = None,
        storage: Optional[BrowserTaskStorage] = None,
        decision_factory: Optional[DecisionMakerFactory] = None,
        event_emitter: Optional[EventEmitter] = None,
    ) -> None:
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.cli = cli or AgentBrowserCLI()
        self.storage = storage or BrowserTaskStorage(self.workspace)
        self.decision_factory = decision_factory
        self.event_emitter = event_emitter
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
            metadata=(
                {"model_override": payload.model_override} if payload.model_override else {}
            ),
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

    # ── execution loop ──────────────────────────────────────────────────

    async def _run(self, task: BrowserTask) -> None:
        cancel = asyncio.Event()
        self._cancellation[task.id] = cancel
        try:
            await self._execute(task, cancel)
        finally:
            self._cancellation.pop(task.id, None)

    async def _resolve_decision_maker(self, task: BrowserTask) -> Optional[DecisionMaker]:
        if self.decision_factory is None:
            return None
        result = self.decision_factory(task)
        if asyncio.iscoroutine(result) or isinstance(result, Awaitable):
            result = await result  # type: ignore[assignment]
        return result  # type: ignore[return-value]

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
        await self._emit(task.id, {"type": "status", "status": "running"})

        # Resolve the LLM decision maker once per task. None falls back to the
        # M1 scripted loop so existing tests / setups keep working.
        try:
            decision_maker = await self._resolve_decision_maker(task)
        except Exception as exc:  # noqa: BLE001
            logger.exception("decision maker init failed")
            self._mark_failed(task, f"无法初始化 LLM 决策器：{exc}")
            return

        step_counter = _StepCounter()

        try:
            # Step: open the start URL if present.
            if task.start_url:
                if cancel.is_set():
                    self._mark_cancelled(task)
                    return
                ok = await self._execute_open(task, step_counter, task.start_url)
                if not ok:
                    return

            if decision_maker is None:
                await self._run_scripted_tail(task, cancel, step_counter)
            else:
                await self._run_react_loop(task, cancel, step_counter, decision_maker)
        finally:
            await self.cli.close_session(task.project_id)

    # ── scripted M1 fallback (kept for tests / no-LLM setups) ───────────

    async def _run_scripted_tail(
        self,
        task: BrowserTask,
        cancel: asyncio.Event,
        step_counter: "_StepCounter",
    ) -> None:
        if cancel.is_set():
            self._mark_cancelled(task)
            return
        snapshot_text = await self._execute_snapshot(task, step_counter)
        if snapshot_text is None:
            return

        if cancel.is_set():
            self._mark_cancelled(task)
            return
        ok = await self._execute_screenshot(task, step_counter)
        if not ok:
            return

        self.storage.update_task(
            task.id,
            status=TaskStatus.COMPLETED,
            finished_at=datetime.now(),
            step_count=step_counter.value,
            result_summary=f"已打开 {task.start_url or '起始页'} 并完成截图。",
        )
        self._schedule_emit(task.id, {"type": "status", "status": "completed"})

    # ── ReAct loop (M2) ─────────────────────────────────────────────────

    async def _run_react_loop(
        self,
        task: BrowserTask,
        cancel: asyncio.Event,
        step_counter: "_StepCounter",
        decision_maker: DecisionMaker,
    ) -> None:
        history: list[dict[str, Any]] = []
        last_snapshot: Optional[str] = None
        result_summary: Optional[str] = None
        same_observation_streak = 0

        # Always have an initial observation so the LLM has something to look at.
        if cancel.is_set():
            self._mark_cancelled(task)
            return
        last_snapshot = await self._execute_snapshot(task, step_counter)
        if last_snapshot is None:
            return

        loop_iteration = 0
        max_iterations = max(1, task.max_steps)
        while loop_iteration < max_iterations:
            loop_iteration += 1
            if cancel.is_set():
                self._mark_cancelled(task)
                return

            # 1) Ask LLM for next action
            try:
                decision = await decision_maker.decide(
                    instruction=task.instruction,
                    snapshot=last_snapshot or "",
                    history=history,
                )
            except DecisionParseError as exc:
                self._record_step(
                    task,
                    step_counter.next(),
                    StepPhase.THINKING,
                    action_name="llm_decide",
                    success=False,
                    error=str(exc),
                )
                self._mark_failed(task, f"LLM 决策失败：{exc}")
                return

            # 2) Record the thinking step (for replay UI)
            self._record_step(
                task,
                step_counter.next(),
                StepPhase.THINKING,
                action_name="llm_decide",
                action_args={"action": decision.action, "args": decision.args},
                thinking=decision.thinking,
                success=True,
            )

            # 3) Finish?
            if decision.is_finish:
                result_summary = (decision.args.get("summary") or "").strip() or "任务完成。"
                break

            # 4) Execute the chosen action
            if cancel.is_set():
                self._mark_cancelled(task)
                return
            action_outcome = await self._execute_decision(task, step_counter, decision)
            if action_outcome.fatal:
                # _execute_decision already marked the task failed.
                return

            # 5) Take a screenshot frame (cheap visual milestone for UI)
            if cancel.is_set():
                self._mark_cancelled(task)
                return
            await self._execute_screenshot(task, step_counter)

            # 6) Re-snapshot and feed into history
            if cancel.is_set():
                self._mark_cancelled(task)
                return
            new_snapshot = await self._execute_snapshot(task, step_counter)
            if new_snapshot is None:
                return

            history.append(
                {
                    "action": decision.action,
                    "args": decision.args,
                    "observation": (action_outcome.observation or "")[:_MAX_OBSERVATION_CHARS],
                    "success": action_outcome.success,
                }
            )

            # Detect "stuck" loops: 3 identical snapshots in a row → bail.
            if new_snapshot == last_snapshot:
                same_observation_streak += 1
            else:
                same_observation_streak = 0
            last_snapshot = new_snapshot
            if same_observation_streak >= 3:
                result_summary = "连续 3 步页面没有变化，自动终止以避免死循环。"
                break
        else:
            result_summary = f"达到最大步数 {task.max_steps}，未收到 finish 信号，自动结束。"

        self.storage.update_task(
            task.id,
            status=TaskStatus.COMPLETED,
            finished_at=datetime.now(),
            step_count=step_counter.value,
            result_summary=result_summary,
        )
        self._schedule_emit(
            task.id,
            {"type": "status", "status": "completed", "result_summary": result_summary},
        )

    # ── per-action helpers ──────────────────────────────────────────────

    async def _execute_open(
        self,
        task: BrowserTask,
        step_counter: "_StepCounter",
        url: str,
    ) -> bool:
        idx = step_counter.next()
        try:
            await self.cli.open_url(task.project_id, url)
            self._record_step(
                task,
                idx,
                StepPhase.ACTION,
                action_name="open",
                action_args={"url": url},
                success=True,
            )
            return True
        except AgentBrowserError as exc:
            self._record_step(
                task,
                idx,
                StepPhase.ACTION,
                action_name="open",
                action_args={"url": url},
                success=False,
                error=str(exc),
            )
            self._mark_failed(task, f"打开起始页失败：{exc}")
            return False

    async def _execute_snapshot(
        self,
        task: BrowserTask,
        step_counter: "_StepCounter",
    ) -> Optional[str]:
        idx = step_counter.next()
        try:
            snap = await self.cli.snapshot(task.project_id)
            observation = (snap.get("data", {}) or {}).get("snapshot") or ""
            trimmed = observation[:_MAX_SNAPSHOT_CHARS]
            self._record_step(
                task,
                idx,
                StepPhase.OBSERVATION,
                action_name="snapshot",
                action_args={"interactive": True},
                observation=trimmed,
                success=True,
            )
            return trimmed
        except AgentBrowserError as exc:
            self._record_step(
                task,
                idx,
                StepPhase.OBSERVATION,
                action_name="snapshot",
                success=False,
                error=str(exc),
            )
            self._mark_failed(task, f"snapshot 失败：{exc}")
            return None

    async def _execute_screenshot(
        self,
        task: BrowserTask,
        step_counter: "_StepCounter",
    ) -> bool:
        idx = step_counter.next()
        screenshot_path = self._artifact_path(task, idx, "screenshots", ".png")
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            shot = await self.cli.screenshot(task.project_id, str(screenshot_path))
            artifact = self._record_artifact(
                task,
                idx,
                ArtifactKind.SCREENSHOT,
                file_path=screenshot_path,
                mime_type="image/png",
                metadata={"agent_browser": shot.get("data", {})},
            )
            self._record_step(
                task,
                idx,
                StepPhase.ACTION,
                action_name="screenshot",
                success=True,
                screenshot_artifact_id=artifact.id,
            )
            return True
        except AgentBrowserError as exc:
            self._record_step(
                task,
                idx,
                StepPhase.ACTION,
                action_name="screenshot",
                success=False,
                error=str(exc),
            )
            # Screenshot failures are non-fatal in the ReAct loop — log a step
            # and continue. The next snapshot will still drive the next decision.
            logger.warning("screenshot for task %s failed: %s", task.id, exc)
            return False

    async def _execute_decision(
        self,
        task: BrowserTask,
        step_counter: "_StepCounter",
        decision: Decision,
    ) -> "_ActionOutcome":
        """Dispatch a parsed Decision to the matching CLI helper."""
        action = decision.action
        args = decision.args
        idx = step_counter.next()

        try:
            observation, artifact_id = await self._dispatch_action(
                task, idx, action, args
            )
            self._record_step(
                task,
                idx,
                StepPhase.ACTION,
                action_name=action,
                action_args=args,
                observation=(observation or "")[:_MAX_OBSERVATION_CHARS],
                success=True,
                screenshot_artifact_id=artifact_id,
            )
            return _ActionOutcome(success=True, observation=observation)
        except AgentBrowserError as exc:
            self._record_step(
                task,
                idx,
                StepPhase.ACTION,
                action_name=action,
                action_args=args,
                success=False,
                error=str(exc),
            )
            return _ActionOutcome(success=False, observation=str(exc))
        except ValueError as exc:
            # Bad args from the LLM — record and let it self-correct next turn.
            self._record_step(
                task,
                idx,
                StepPhase.ACTION,
                action_name=action,
                action_args=args,
                success=False,
                error=str(exc),
            )
            return _ActionOutcome(success=False, observation=str(exc))

    async def _dispatch_action(
        self,
        task: BrowserTask,
        step_index: int,
        action: str,
        args: dict[str, Any],
    ) -> tuple[Optional[str], Optional[str]]:
        """Map a Decision to an AgentBrowserCLI call.

        Returns ``(observation_text, artifact_id_or_None)``. The artifact id
        is set when the action produced a persisted file (text / json / pdf).
        """
        cli = self.cli
        project_id = task.project_id

        if action == "open":
            await cli.open_url(project_id, _require(args, "url"))
            return None, None
        if action == "click":
            await cli.click(project_id, _require(args, "selector"))
            return None, None
        if action == "type":
            await cli.type_text(project_id, _require(args, "selector"), _require(args, "text"))
            return None, None
        if action == "fill":
            await cli.fill(project_id, _require(args, "selector"), _require(args, "text"))
            return None, None
        if action == "press":
            await cli.press(project_id, _require(args, "key"))
            return None, None
        if action == "scroll":
            pixels_raw = args.get("pixels")
            pixels = int(pixels_raw) if pixels_raw is not None else None
            await cli.scroll(project_id, _require(args, "direction"), pixels=pixels)
            return None, None
        if action == "wait":
            await cli.wait(project_id, str(_require(args, "target")))
            return None, None
        if action == "back":
            await cli.back(project_id)
            return None, None
        if action == "forward":
            await cli.forward(project_id)
            return None, None
        if action == "reload":
            await cli.reload(project_id)
            return None, None
        if action == "get_text":
            response = await cli.get(project_id, "text", _require(args, "selector"))
            data = response.get("data") if isinstance(response, dict) else None
            if isinstance(data, dict):
                return str(data.get("text") or data), None
            return str(data), None
        if action == "screenshot":
            # Step counter handled by caller via _execute_screenshot in the loop.
            await cli.screenshot(project_id)
            return "已截图", None
        if action == "save_page_text":
            text, artifact_id = await self._save_page_text_artifact(
                task, step_index, label=args.get("label")
            )
            preview = (text or "")[:200]
            return f"已保存 {len(text)} 字符的页面文本：{preview}…", artifact_id
        if action == "extract":
            fields = args.get("fields")
            if not isinstance(fields, dict) or not fields:
                raise ValueError("extract 需要非空 fields 对象，例如 {\"title\":\".h1\"}")
            data, artifact_id = await self._save_extract_artifact(
                task, step_index, fields=fields, label=args.get("label")
            )
            return f"已提取 {len(data)} 个字段：{list(data.keys())}", artifact_id

        raise ValueError(f"未知动作 '{action}' 无法分发")

    async def _save_page_text_artifact(
        self,
        task: BrowserTask,
        step_index: int,
        *,
        label: Optional[str],
    ) -> tuple[str, str]:
        """Capture document.body.innerText and persist as a .txt artifact."""
        # Use eval to dump the visible text; truncate at 200KB so a malicious
        # page can't bloat the workspace.
        response = await self.cli.eval_js(
            task.project_id,
            "document.body && document.body.innerText ? document.body.innerText : ''",
        )
        data = response.get("data") if isinstance(response, dict) else None
        if isinstance(data, dict):
            text = str(data.get("result") or data.get("text") or "")
        else:
            text = str(data or "")
        text = text[:200_000]

        path = self._artifact_path(task, step_index, "page_text", ".txt")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        artifact = self._record_artifact(
            task,
            step_index,
            ArtifactKind.PAGE_TEXT,
            file_path=path,
            mime_type="text/plain",
            metadata={"label": label} if label else None,
        )
        return text, artifact.id

    async def _save_extract_artifact(
        self,
        task: BrowserTask,
        step_index: int,
        *,
        fields: dict[str, Any],
        label: Optional[str],
    ) -> tuple[dict[str, Any], str]:
        """Run document.querySelector for each selector and persist as JSON."""
        # Build a single eval expression that returns a JSON-encoded mapping.
        # Each selector is JSON-stringified so user input can't break out of
        # the JS string.
        import json as _json

        pairs = []
        for key, selector in fields.items():
            if not isinstance(selector, str):
                raise ValueError(f"字段 '{key}' 的 selector 必须是字符串")
            pairs.append(
                f"[{_json.dumps(str(key))}, document.querySelector({_json.dumps(selector)})]"
            )
        expression = (
            "JSON.stringify(Object.fromEntries("
            f"[{','.join(pairs)}]"
            ".map(([k,el])=>[k, el ? (el.innerText||el.value||el.textContent||'').trim() : null])"
            "))"
        )
        response = await self.cli.eval_js(task.project_id, expression)
        data_field = response.get("data") if isinstance(response, dict) else None
        raw_value = (
            data_field.get("result") if isinstance(data_field, dict) else data_field
        )
        try:
            extracted = _json.loads(raw_value) if isinstance(raw_value, str) else dict(raw_value or {})
        except (TypeError, ValueError):
            extracted = {key: None for key in fields}

        path = self._artifact_path(task, step_index, "extracts", ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf-8")
        artifact = self._record_artifact(
            task,
            step_index,
            ArtifactKind.EXTRACT_JSON,
            file_path=path,
            mime_type="application/json",
            metadata={"label": label, "fields": list(fields)} if label else {"fields": list(fields)},
        )
        return extracted, artifact.id

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
        # Fire-and-forget event emission. Schedule on the running loop so
        # _record_step stays sync-callable.
        self._schedule_emit(task.id, {"type": "step", "step": step.model_dump(mode="json")})

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
        self._schedule_emit(
            task.id,
            {"type": "artifact", "artifact": artifact.model_dump(mode="json")},
        )
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
        self._schedule_emit(
            task.id, {"type": "status", "status": "failed", "error": error}
        )

    def _mark_cancelled(self, task: BrowserTask) -> None:
        self.storage.update_task(
            task.id,
            status=TaskStatus.CANCELLED,
            finished_at=datetime.now(),
        )
        self._schedule_emit(task.id, {"type": "status", "status": "cancelled"})

    # ── event emission ──────────────────────────────────────────────────

    async def _emit(self, task_id: str, event: dict[str, Any]) -> None:
        """Async event emission — call from coroutine contexts."""
        if self.event_emitter is None:
            return
        try:
            await self.event_emitter(task_id, event)
        except Exception:  # noqa: BLE001
            logger.warning("event emitter failed for task %s", task_id, exc_info=True)

    def _schedule_emit(self, task_id: str, event: dict[str, Any]) -> None:
        """Sync helper that schedules an emit on the running loop without awaiting."""
        if self.event_emitter is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No loop — happens in synchronous unit tests; just drop the event.
            return
        loop.create_task(self._emit(task_id, event))


def _require(args: dict[str, Any], key: str) -> Any:
    if key not in args or args[key] in (None, ""):
        raise ValueError(f"缺少必填参数 '{key}'")
    return args[key]


class _StepCounter:
    """Monotonic step index counter (1-based)."""

    def __init__(self) -> None:
        self.value = 0

    def next(self) -> int:
        self.value += 1
        return self.value


@dataclass
class _ActionOutcome:
    success: bool
    observation: Optional[str]
    fatal: bool = False
