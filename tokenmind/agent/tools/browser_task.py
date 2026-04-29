"""Bridge between the main agent and the Web Agent module.

Lets the chat agent kick off a browser-task with one tool call, wait for it
to finish (with a configurable timeout), and surface the result + artifact
references back into the conversation.

Per-asyncio-task ContextVars carry the calling session id so the tool can
attribute every task it creates to the right chat — same pattern used by
DeliverAttachmentTool.
"""

from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Optional

from tokenmind.agent.tools.base import Tool
from tokenmind.browser_agent.models import (
    ArtifactKind,
    BrowserArtifact,
    CreateTaskRequest,
    TaskStatus,
)

if TYPE_CHECKING:  # avoid hard import cycle at runtime
    from tokenmind.browser_agent.task_service import BrowserTaskService
    from tokenmind.server.attachments import AttachmentStore

logger = logging.getLogger("tokenmind.agent.tools.browser_task")


# Per-turn context. The chat session id and project id flow in from the
# AgentLoop call site so each tool invocation can attribute its task to the
# right conversation.
_session_ctx: ContextVar[str] = ContextVar("browser_task_session", default="")
_project_ctx: ContextVar[str] = ContextVar("browser_task_project", default="")
_message_id_ctx: ContextVar[Optional[str]] = ContextVar(
    "browser_task_message_id", default=None
)
_keep_open_ctx: ContextVar[bool] = ContextVar("browser_task_keep_open", default=False)


# How long browser-task attachments are kept by the AttachmentStore. Same
# default as DeliverAttachmentTool so users see one consistent retention.
_ATTACHMENT_RETENTION = timedelta(days=30)

# Only certain artifact kinds get auto-attached. Screenshots are opt-in: the
# browser task only creates them when the user asks for one.
_ATTACH_ALL_KINDS = {
    ArtifactKind.PAGE_TEXT,
    ArtifactKind.EXTRACT_JSON,
    ArtifactKind.PDF,
    ArtifactKind.DOWNLOAD,
}


# Polling interval while waiting for the task to leave a transient state.
_POLL_INTERVAL_S = 0.5

DEFAULT_TIMEOUT_S = 300
MAX_TIMEOUT_S = 1800

# How much of the result summary we let through. The agent doesn't need a wall
# of text — long captures should be surfaced via artifacts instead.
_MAX_SUMMARY_CHARS = 1500


class RunBrowserTaskTool(Tool):
    """Run a browser automation task end-to-end and return the result."""

    def __init__(
        self,
        service: "BrowserTaskService",
        attachment_store: Optional["AttachmentStore"] = None,
    ) -> None:
        self._service = service
        self._attachments = attachment_store

    @property
    def name(self) -> str:
        return "run_browser_task"

    @property
    def description(self) -> str:
        return (
            "Drive a visible local Chrome browser to complete a multi-step web task: "
            "navigate, search, click links, fill forms, extract data, and create "
            "screenshots only when requested. Browser state is isolated per project "
            "or chat. Returns the final summary plus IDs of any artifacts (page text, "
            "screenshots, extracted JSON) that were captured. Use this whenever the user "
            "asks you to look something up online, fill out a form, or save "
            "content from a page."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": (
                        "Natural-language task description. Be specific about "
                        "what success looks like (e.g. 'open baidu.com, search "
                        "for TokenMind, save the first result title')."
                    ),
                    "minLength": 1,
                },
                "start_url": {
                    "type": "string",
                    "description": (
                        "Optional URL to open before the loop starts. If omitted, "
                        "the LLM has to navigate from a blank tab."
                    ),
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": (
                        f"Max time (in seconds) to wait for the task to finish. "
                        f"Default {DEFAULT_TIMEOUT_S}, max {MAX_TIMEOUT_S}."
                    ),
                    "minimum": 30,
                    "maximum": MAX_TIMEOUT_S,
                },
                "max_steps": {
                    "type": "integer",
                    "description": (
                        "Max number of LLM decisions the browser loop may make. "
                        "Defaults to 50."
                    ),
                    "minimum": 1,
                    "maximum": 200,
                },
            },
            "required": ["instruction"],
        }

    def set_context(
        self,
        channel: str,
        chat_id: str,
        message_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """AgentLoop calls this before each tool turn.

        We piggyback on the per-turn ContextVar pattern from
        DeliverAttachmentTool — channel + chat_id together identify the chat
        session that triggered the tool call.
        """
        # Project chats reuse a project-level browser profile. Normal chats
        # fall back to their chat id and can be closed after the task ends.
        _session_ctx.set(chat_id or "")
        _project_ctx.set(project_id or chat_id or "default")
        _message_id_ctx.set(message_id)
        _keep_open_ctx.set(bool(project_id))

    async def execute(
        self,
        instruction: str,
        start_url: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        max_steps: Optional[int] = None,
        **_: Any,
    ) -> str:
        chat_id = _session_ctx.get()
        project_id = _project_ctx.get() or "default"
        if not chat_id:
            return "Error: run_browser_task requires an active chat session."

        timeout = min(int(timeout_seconds or DEFAULT_TIMEOUT_S), MAX_TIMEOUT_S)
        steps = int(max_steps) if max_steps else 50

        try:
            task = self._service.create_task(
                CreateTaskRequest(
                    project_id=project_id,
                    instruction=instruction,
                    start_url=start_url,
                    session_id=chat_id,
                    max_steps=steps,
                    timeout_seconds=timeout,
                    keep_browser_open=_keep_open_ctx.get(),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("failed to create browser task")
            return f"Error: 创建浏览器任务失败：{exc}"

        self._service.schedule(task)

        try:
            final = await asyncio.wait_for(self._wait_for_terminal(task.id), timeout=timeout)
        except asyncio.TimeoutError:
            self._service.request_cancel(task.id)
            return (
                f"⚠️ 浏览器任务 {task.id} 超过 {timeout}s 仍未完成，已请求取消。"
                "可以让用户在 Web Agent 页面查看完整执行情况。"
            )

        # Promote select artifacts to chat attachments so the user sees them
        # in the conversation, not only on the Web Agent page.
        attachment_refs = self._deliver_artifacts(
            chat_id, self._service.storage.list_artifacts(task.id)
        )
        return self._format_result(final, attachment_refs)

    async def _wait_for_terminal(self, task_id: str) -> Any:
        """Poll storage until the task reaches a terminal status."""
        while True:
            current = self._service.storage.get_task(task_id)
            if current and current.status in (
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
                TaskStatus.AWAITING_USER,
            ):
                return current
            await asyncio.sleep(_POLL_INTERVAL_S)

    def _deliver_artifacts(
        self, chat_id: str, artifacts: list[BrowserArtifact]
    ) -> list[dict[str, Any]]:
        """Copy each interesting artifact into the chat AttachmentStore.

        Returns the resulting attachment refs ({id, name, ...}) so the agent
        can mention them in its reply. Failures are non-fatal — we log and
        keep going so a single bad file doesn't fail the whole tool call.
        """
        if self._attachments is None or not chat_id:
            return []

        message_id = _message_id_ctx.get()
        delivered: list[dict[str, Any]] = []

        # For screenshots we only attach the latest requested capture to avoid
        # spamming the chat. Everything else (text, JSON, PDF, downloads) goes
        # through.
        screenshots = [a for a in artifacts if a.kind is ArtifactKind.SCREENSHOT]
        last_screenshot = screenshots[-1] if screenshots else None

        for art in artifacts:
            if art.kind is ArtifactKind.SCREENSHOT:
                if art is not last_screenshot:
                    continue
            elif art.kind not in _ATTACH_ALL_KINDS:
                continue
            try:
                ref = self._attachments.create_local(
                    chat_id,
                    source_path=art.file_path,
                    retention=_ATTACHMENT_RETENTION,
                    message_id=message_id,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "failed to deliver browser artifact %s as chat attachment", art.id
                )
                continue
            delivered.append({**ref, "kind": art.kind.value, "browser_artifact_id": art.id})
        return delivered

    def _format_result(
        self, task: Any, attachment_refs: list[dict[str, Any]] | None = None
    ) -> str:
        artifacts = self._service.storage.list_artifacts(task.id)

        # Group artifact IDs by kind for compact reporting.
        by_kind: dict[str, list[str]] = {}
        for art in artifacts:
            by_kind.setdefault(art.kind.value, []).append(art.id)

        if task.status is TaskStatus.COMPLETED:
            header = f"✅ 浏览器任务 {task.id} 完成。"
        elif task.status is TaskStatus.FAILED:
            header = f"❌ 浏览器任务 {task.id} 失败。"
        elif task.status is TaskStatus.CANCELLED:
            header = f"⏹ 浏览器任务 {task.id} 已取消。"
        elif task.status is TaskStatus.AWAITING_USER:
            header = (
                f"⏸ 浏览器任务 {task.id} 已暂停等待用户接管。"
                "请在 Web Agent 页面手动操作并恢复 AI。"
            )
        else:
            header = f"浏览器任务 {task.id} 当前状态：{task.status.value}"

        lines = [header]
        if task.result_summary:
            summary = task.result_summary[:_MAX_SUMMARY_CHARS]
            if len(task.result_summary) > _MAX_SUMMARY_CHARS:
                summary += "...(已截断)"
            lines.append(f"结果摘要：{summary}")
        if task.error_detail and task.status is TaskStatus.FAILED:
            lines.append(f"错误详情：{task.error_detail}")
        if by_kind:
            artifact_summary = ", ".join(
                f"{kind}×{len(ids)}" for kind, ids in sorted(by_kind.items())
            )
            lines.append(f"产生 {len(artifacts)} 个产物（{artifact_summary}）。")
            # Surface the IDs so the agent can hand them to deliver_attachment.
            screenshot_ids = by_kind.get("screenshot", [])
            if screenshot_ids:
                lines.append(f"截图 ID（最新优先）：{', '.join(screenshot_ids[-5:])}")
            text_ids = by_kind.get("page_text", [])
            if text_ids:
                lines.append(f"页面文本 artifact id：{', '.join(text_ids)}")
            json_ids = by_kind.get("extract_json", [])
            if json_ids:
                lines.append(f"提取 JSON artifact id：{', '.join(json_ids)}")

        if attachment_refs:
            attached = ", ".join(
                f"{ref.get('name') or ref.get('id', '?')}"
                for ref in attachment_refs
            )
            lines.append(f"已自动添加为聊天附件：{attached}。")
        lines.append(
            f"任务步数 {task.step_count}，详情见 Web Agent 页面（任务 ID {task.id}）。"
        )
        return "\n".join(lines)
