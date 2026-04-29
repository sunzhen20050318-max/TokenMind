"""Browser task lifecycle: create, execute (LLM-driven ReAct), persist artifacts.

The execution loop is the ReAct pattern:

1. (optional) open the start URL
2. snapshot the page → record as observation
3. ask the LLM for the next action
4. execute the action via AgentBrowserCLI
5. snapshot again as observation
6. repeat until LLM emits ``finish`` / max_steps reached / cancellation

Each LLM action is recorded as a step (phase=ACTION) and each snapshot as a
step (phase=OBSERVATION). The browser runs headed so users can take over the
real local window; screenshots are only created when explicitly requested.
"""

from __future__ import annotations

import asyncio
import logging
import re
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
    ContinueTaskRequest,
    CreateTaskRequest,
    StepPhase,
    TaskStatus,
)
from tokenmind.browser_agent.storage import BrowserTaskStorage
from tokenmind.browser_agent.stuck_detector import StuckDetector, StuckEvent, StuckReason

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


_REF_SELECTOR_RE = re.compile(r"^(?:@?e|ref\s*=\s*e?)(\d+)$", re.IGNORECASE)

_CAPTCHA_GUARD_PATTERNS = (
    "验证码",
    "安全验证",
    "人机验证",
    "滑块",
    "拖动",
    "拖拽",
    "captcha",
    "recaptcha",
    "verify you are human",
    "security verification",
    "robot check",
)

_LOGIN_GUARD_PATTERNS = (
    "登录",
    "登陆",
    "sign in",
    "log in",
    "login",
    "账号",
    "未登录",
)

_LOGIN_SIGNAL_PATTERNS = (
    "手机号",
    "手机号码",
    "验证码",
    "密码",
    "扫码",
    "二维码",
    "注册",
    "第三方登录",
    "password",
    "phone",
    "verification code",
    "qr code",
    "register",
)


def _normalize_agent_selector(selector: str) -> str:
    """Convert snapshot refs like ``ref=e43`` / ``e43`` into agent-browser refs."""
    text = str(selector).strip()
    match = _REF_SELECTOR_RE.match(text)
    if match:
        return f"@e{match.group(1)}"
    return text


def _is_agent_ref_selector(selector: str) -> bool:
    return _REF_SELECTOR_RE.match(str(selector).strip()) is not None


def _detect_browser_guard(snapshot: str) -> Optional[StuckEvent]:
    """Detect states where the user must intervene before the LLM continues.

    Some sites keep the underlying page in the accessibility tree even while a
    login/captcha overlay is blocking interactions. This guard intentionally
    runs outside the LLM so those overlays pause the task reliably.
    """
    text = (snapshot or "").lower()
    if not text.strip():
        return None

    if any(pattern in text for pattern in _CAPTCHA_GUARD_PATTERNS):
        return StuckEvent(
            reason=StuckReason.BROWSER_GUARD,
            detail=(
                "Browser Guard 检测到验证码、滑块或安全验证。请你在右侧浏览器窗口中"
                "手动完成验证，然后点击“我已完成”。"
            ),
        )

    has_login_word = any(pattern in text for pattern in _LOGIN_GUARD_PATTERNS)
    has_login_signal = any(pattern in text for pattern in _LOGIN_SIGNAL_PATTERNS)
    if has_login_word and has_login_signal:
        return StuckEvent(
            reason=StuckReason.BROWSER_GUARD,
            detail=(
                "Browser Guard 检测到登录/注册弹窗或账号验证。请你在右侧浏览器窗口中"
                "完成登录或关闭弹窗，然后点击“我已完成”。"
            ),
        )

    return None


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
        self.storage = storage or BrowserTaskStorage(self.workspace)
        self.decision_factory = decision_factory
        self.event_emitter = event_emitter
        self.artifacts_root = self.workspace / "browser"
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        self.cli = cli or AgentBrowserCLI(
            profile_root=self.artifacts_root / "profiles",
            download_root=self.artifacts_root / "downloads",
        )
        self._cancellation: dict[str, asyncio.Event] = {}
        self._resume: dict[str, asyncio.Event] = {}
        self._resume_notes: dict[str, str] = {}
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
            metadata={
                **({"model_override": payload.model_override} if payload.model_override else {}),
                "keep_browser_open": payload.keep_browser_open,
            },
        )
        self.storage.insert_task(task)
        return task

    def continue_task(self, task_id: str, payload: ContinueTaskRequest) -> BrowserTask:
        """Append a new user instruction to an existing browser task.

        Completed browser tasks keep their browser profile/session alive by
        default. Continuing reuses that same task id and project session, adds a
        visible "user instruction" step to the timeline, and schedules another
        ReAct pass against the current browser page unless a new start URL is
        supplied.
        """
        task = self.storage.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        if task.status in (
            TaskStatus.PENDING,
            TaskStatus.RUNNING,
            TaskStatus.AWAITING_USER,
        ):
            raise ValueError(f"Task is in status '{task.status.value}', cannot continue")

        now = datetime.now()
        metadata = dict(task.metadata or {})
        turns = list(metadata.get("turns") or [])
        if not turns:
            turns.append(
                {
                    "role": "user",
                    "content": task.instruction,
                    "at": task.created_at.isoformat(),
                }
            )
        turns.append(
            {
                "role": "user",
                "content": payload.instruction,
                "at": now.isoformat(),
            }
        )
        metadata["turns"] = turns[-30:]
        metadata["last_continued_at"] = now.isoformat()

        self.storage.prepare_task_continue(
            task_id,
            instruction=payload.instruction,
            start_url=payload.start_url,
            max_steps=payload.max_steps,
            timeout_seconds=payload.timeout_seconds,
            metadata=metadata,
        )

        refreshed = self.storage.get_task(task_id)
        if refreshed is None:
            raise KeyError(task_id)

        step_index = (task.step_count or 0) + 1
        self._record_step(
            refreshed,
            step_index,
            StepPhase.INTERVENTION,
            action_name="user_instruction",
            thinking=payload.instruction,
            action_args={"start_url": payload.start_url} if payload.start_url else None,
            success=True,
        )

        final_task = self.storage.get_task(task_id)
        if final_task is None:
            raise KeyError(task_id)
        self._schedule_emit(task_id, {"type": "status", "status": "pending"})
        return final_task

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

    def request_takeover(self, task_id: str, reason: str = "用户主动接管") -> bool:
        """Force the task into ``awaiting_user`` even when not stuck.

        Returns False when the task isn't running. The ReAct loop will pause
        at its next checkpoint and wait for ``request_resume``.
        """
        if task_id not in self._cancellation:
            return False
        # Reuse the resume event slot — the loop polls it at every checkpoint.
        self._resume.setdefault(task_id, asyncio.Event())
        # We mark via a side-channel attribute that the user wants takeover.
        # The loop checks this each iteration before calling decide().
        flag_attr = f"_takeover_{task_id}"
        setattr(self, flag_attr, reason)
        return True

    def _takeover_requested(self, task_id: str) -> Optional[str]:
        return getattr(self, f"_takeover_{task_id}", None)

    def _clear_takeover_flag(self, task_id: str) -> None:
        attr = f"_takeover_{task_id}"
        if hasattr(self, attr):
            delattr(self, attr)

    def request_resume(self, task_id: str, note: Optional[str] = None) -> bool:
        """Signal that the user has finished interacting; resume the AI loop."""
        event = self._resume.get(task_id)
        if event is None:
            return False
        if note:
            self._resume_notes[task_id] = str(note).strip()[:2000]
        event.set()
        return True

    # ── execution loop ──────────────────────────────────────────────────

    async def _run(self, task: BrowserTask) -> None:
        cancel = asyncio.Event()
        resume = asyncio.Event()
        self._cancellation[task.id] = cancel
        self._resume[task.id] = resume
        try:
            await self._execute(task, cancel)
        finally:
            self._cancellation.pop(task.id, None)
            self._resume.pop(task.id, None)
            self._resume_notes.pop(task.id, None)
            self._clear_takeover_flag(task.id)

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

        step_counter = _StepCounter(task.step_count or 0)

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
            if not task.metadata.get("keep_browser_open", True):
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

        self.storage.update_task(
            task.id,
            status=TaskStatus.COMPLETED,
            finished_at=datetime.now(),
            step_count=step_counter.value,
            result_summary=f"已打开 {task.start_url or '起始页'} 并完成页面快照。",
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
        detector = StuckDetector()
        resume_event = self._resume.get(task.id) or asyncio.Event()

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

            # User-initiated takeover — pause before consulting the LLM.
            takeover_reason = self._takeover_requested(task.id)
            if takeover_reason:
                self._clear_takeover_flag(task.id)
                paused = await self._await_resume(
                    task,
                    step_counter,
                    cancel,
                    resume_event,
                    StuckEvent(reason=StuckReason.NO_CHANGE, detail=takeover_reason),
                    history=history,
                )
                if paused == "cancelled":
                    return
                # Refresh snapshot after the user finished interacting.
                last_snapshot = await self._execute_snapshot(task, step_counter)
                if last_snapshot is None:
                    return
                detector.reset()
                continue

            guard = _detect_browser_guard(last_snapshot or "")
            if guard:
                paused = await self._await_resume(
                    task,
                    step_counter,
                    cancel,
                    resume_event,
                    guard,
                    history=history,
                )
                if paused == "cancelled":
                    return
                last_snapshot = await self._execute_snapshot(task, step_counter)
                if last_snapshot is None:
                    return
                detector.reset()
                continue

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

            stuck = detector.observe_action(
                action=decision.action,
                args=decision.args,
                success=action_outcome.success,
            )
            if stuck:
                paused = await self._await_resume(
                    task, step_counter, cancel, resume_event, stuck, history=history
                )
                if paused == "cancelled":
                    return
                last_snapshot = await self._execute_snapshot(task, step_counter)
                if last_snapshot is None:
                    return
                detector.reset()
                continue

            # 5) Re-snapshot and feed into history. We intentionally do not
            # auto-capture screenshots here; the real headed browser window is
            # the visual surface, and screenshots are only created on request.
            if cancel.is_set():
                self._mark_cancelled(task)
                return
            new_snapshot = await self._execute_snapshot(task, step_counter)
            if new_snapshot is None:
                return

            if (
                decision.action == "click"
                and action_outcome.success
                and new_snapshot == last_snapshot
            ):
                retried = await self._execute_click_center_fallback(
                    task,
                    step_counter,
                    selector=str(decision.args.get("selector") or ""),
                )
                if retried:
                    action_outcome = _ActionOutcome(
                        success=True,
                        observation="普通点击后页面未变化，已使用元素中心坐标进行兜底点击。",
                    )
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

            # Hand control to the user when the page hasn't changed enough times.
            stuck = detector.observe_snapshot(new_snapshot)
            if stuck:
                paused = await self._await_resume(
                    task, step_counter, cancel, resume_event, stuck, history=history
                )
                if paused == "cancelled":
                    return
                last_snapshot = await self._execute_snapshot(task, step_counter)
                if last_snapshot is None:
                    return
                detector.reset()
                continue

            last_snapshot = new_snapshot
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

    async def _await_resume(
        self,
        task: BrowserTask,
        step_counter: "_StepCounter",
        cancel: asyncio.Event,
        resume_event: asyncio.Event,
        stuck: StuckEvent,
        *,
        history: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        """Park the loop in ``awaiting_user`` until resume/cancel arrives.

        While parked the user controls the visible local browser window
        directly, then calls resume when they are done.

        Returns ``"resumed"`` or ``"cancelled"``.
        """
        logger.info("Task %s awaiting user takeover: %s", task.id, stuck.detail)
        self.storage.update_task(task.id, status=TaskStatus.AWAITING_USER)
        # Persist a step so the timeline shows why we paused.
        self._record_step(
            task,
            step_counter.next(),
            StepPhase.INTERVENTION,
            action_name="await_user",
            action_args={"reason": stuck.reason.value},
            thinking=stuck.detail,
            success=True,
        )
        await self._emit(
            task.id,
            {
                "type": "status",
                "status": "awaiting_user",
                "reason": stuck.reason.value,
                "detail": stuck.detail,
            },
        )
        # Make sure the resume event is fresh — clear stale signal from prior pauses.
        resume_event.clear()

        cancel_task = asyncio.create_task(cancel.wait())
        resume_task = asyncio.create_task(resume_event.wait())
        try:
            done, pending = await asyncio.wait(
                {cancel_task, resume_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for p in pending:
                p.cancel()
        finally:
            for t in (cancel_task, resume_task):
                if not t.done():
                    t.cancel()
        if cancel.is_set():
            self._mark_cancelled(task)
            return "cancelled"

        # Resumed: bring the task back to RUNNING and let the loop re-snapshot.
        resume_note = self._resume_notes.pop(task.id, "").strip()
        resume_observation = (
            f"用户完成接管：{resume_note}"
            if resume_note
            else "用户完成接管，恢复 AI。"
        )
        self.storage.update_task(task.id, status=TaskStatus.RUNNING)
        await self._emit(task.id, {"type": "status", "status": "running"})
        self._record_step(
            task,
            step_counter.next(),
            StepPhase.INTERVENTION,
            action_name="resume",
            action_args={"note": resume_note} if resume_note else None,
            observation=resume_observation,
            success=True,
        )
        if history is not None:
            history.append(
                {
                    "action": "user_resume",
                    "args": {"note": resume_note} if resume_note else {},
                    "observation": resume_observation,
                    "success": True,
                }
            )
        return "resumed"

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
            await self.cli.close_session(task.project_id)
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
        try:
            artifact_id = await self._capture_screenshot_artifact(task, idx)
            self._record_step(
                task,
                idx,
                StepPhase.ACTION,
                action_name="screenshot",
                success=True,
                screenshot_artifact_id=artifact_id,
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

    async def _capture_screenshot_artifact(
        self,
        task: BrowserTask,
        step_index: int,
    ) -> str:
        screenshot_path = self._artifact_path(task, step_index, "screenshots", ".png")
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        shot = await self.cli.screenshot(task.project_id, str(screenshot_path))
        artifact = self._record_artifact(
            task,
            step_index,
            ArtifactKind.SCREENSHOT,
            file_path=screenshot_path,
            mime_type="image/png",
            metadata={"agent_browser": shot.get("data", {})},
        )
        return artifact.id

    async def _execute_click_center_fallback(
        self,
        task: BrowserTask,
        step_counter: "_StepCounter",
        *,
        selector: str,
    ) -> bool:
        """Retry a no-op link click by sending real mouse events at its center.

        Some SPA pages expose a text/link node in the accessibility tree while
        the real click handler lives on the visual card around it. The normal
        ref click can report success without advancing the page; a coordinate
        click mirrors what the user would do in the visible browser window.
        """
        if not selector:
            return False
        selector = _normalize_agent_selector(selector)

        idx: Optional[int] = None
        try:
            # Only retry elements that look link-like. This avoids double
            # activating generic buttons that intentionally update in-place.
            href_response = await self.cli.get_attr(task.project_id, selector, "href")
            href_data = href_response.get("data") if isinstance(href_response, dict) else None
            href_value = (
                href_data.get("value")
                if isinstance(href_data, dict)
                else href_data
            )
            if not href_value:
                return False

            box_response = await self.cli.get_box(task.project_id, selector)
            box = box_response.get("data") if isinstance(box_response, dict) else None
            if not isinstance(box, dict):
                return False
            x = float(box.get("x", 0)) + float(box.get("width", 0)) / 2
            y = float(box.get("y", 0)) + float(box.get("height", 0)) / 2
            if x <= 0 or y <= 0:
                return False

            await self.cli.click_xy(task.project_id, int(x), int(y))
            idx = step_counter.next()
            self._record_step(
                task,
                idx,
                StepPhase.ACTION,
                action_name="click_xy_fallback",
                action_args={
                    "selector": selector,
                    "x": int(x),
                    "y": int(y),
                    "href": str(href_value),
                },
                observation="普通 ref 点击未推动页面，已改用真实鼠标坐标点击。",
                success=True,
            )
            return True
        except (AgentBrowserError, ValueError, TypeError) as exc:
            idx = idx or step_counter.next()
            self._record_step(
                task,
                idx,
                StepPhase.ACTION,
                action_name="click_xy_fallback",
                action_args={"selector": selector},
                success=False,
                error=str(exc),
            )
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
            await cli.click(project_id, _normalize_agent_selector(_require(args, "selector")))
            return None, None
        if action == "type":
            await cli.type_text(
                project_id,
                _normalize_agent_selector(_require(args, "selector")),
                _require(args, "text"),
            )
            return None, None
        if action == "fill":
            await cli.fill(
                project_id,
                _normalize_agent_selector(_require(args, "selector")),
                _require(args, "text"),
            )
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
            await cli.wait(project_id, _normalize_agent_selector(str(_require(args, "target"))))
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
            response = await cli.get(
                project_id,
                "text",
                _normalize_agent_selector(_require(args, "selector")),
            )
            data = response.get("data") if isinstance(response, dict) else None
            if isinstance(data, dict):
                return str(data.get("text") or data), None
            return str(data), None
        if action == "screenshot":
            artifact_id = await self._capture_screenshot_artifact(task, step_index)
            return "已截图并保存为产物。", artifact_id
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
        """Extract selector/ref values and persist them as JSON."""
        import json as _json

        extracted: dict[str, Any] = {}
        css_pairs = []
        for key, selector in fields.items():
            if not isinstance(selector, str):
                raise ValueError(f"字段 '{key}' 的 selector 必须是字符串")
            if _is_agent_ref_selector(selector):
                normalized = _normalize_agent_selector(selector)
                try:
                    response = await self.cli.get(task.project_id, "text", normalized)
                    data = response.get("data") if isinstance(response, dict) else None
                    if isinstance(data, dict):
                        extracted[str(key)] = str(data.get("text") or "").strip()
                    else:
                        extracted[str(key)] = str(data or "").strip()
                except AgentBrowserError as exc:
                    logger.warning(
                        "extract ref %s for field %s failed: %s",
                        normalized,
                        key,
                        exc,
                    )
                    extracted[str(key)] = None
                continue
            css_pairs.append(
                f"[{_json.dumps(str(key))}, document.querySelector({_json.dumps(selector)})]"
            )

        if css_pairs:
            expression = (
                "JSON.stringify(Object.fromEntries("
                f"[{','.join(css_pairs)}]"
                ".map(([k,el])=>[k, el ? (el.innerText||el.value||el.textContent||'').trim() : null])"
                "))"
            )
            response = await self.cli.eval_js(task.project_id, expression)
            data_field = response.get("data") if isinstance(response, dict) else None
            raw_value = (
                data_field.get("result") if isinstance(data_field, dict) else data_field
            )
            try:
                css_extracted = (
                    _json.loads(raw_value)
                    if isinstance(raw_value, str)
                    else dict(raw_value or {})
                )
            except (TypeError, ValueError):
                css_extracted = {
                    key: None
                    for key, selector in fields.items()
                    if isinstance(selector, str) and not _is_agent_ref_selector(selector)
                }
            extracted.update(css_extracted)

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

    def __init__(self, value: int = 0) -> None:
        self.value = value

    def next(self) -> int:
        self.value += 1
        return self.value


@dataclass
class _ActionOutcome:
    success: bool
    observation: Optional[str]
    fatal: bool = False
