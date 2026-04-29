"""Agent loop: the core processing engine."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import weakref
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from fastapi import HTTPException
from loguru import logger

from tokenmind.agent.context import ContextBuilder
from tokenmind.agent.memory import MemoryConsolidator
from tokenmind.agent.skills import BUILTIN_SKILLS_DIR
from tokenmind.agent.subagent import SubagentManager
from tokenmind.agent.tools.cron import CronTool
from tokenmind.agent.tools.deliver_attachment import DeliverAttachmentTool
from tokenmind.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from tokenmind.agent.tools.generate_image import GenerateImageTool
from tokenmind.agent.tools.message import MessageTool
from tokenmind.agent.tools.registry import ToolRegistry
from tokenmind.agent.tools.shell import ExecTool
from tokenmind.agent.tools.spawn import SpawnTool
from tokenmind.agent.tools.web import WebFetchTool, WebSearchTool
from tokenmind.audit import AuditLogger
from tokenmind.bus.events import InboundMessage, OutboundMessage
from tokenmind.bus.queue import MessageBus
from tokenmind.creative.image_generation import ImageGenerationService
from tokenmind.knowledge import KnowledgeService
from tokenmind.providers.base import LLMProvider
from tokenmind.server.attachments import AttachmentStore
from tokenmind.session.manager import Session, SessionManager

if TYPE_CHECKING:
    from tokenmind.config.schema import (
        ChannelsConfig,
        CreativeConfig,
        ExecToolConfig,
        KnowledgeConfig,
        TemplatesConfig,
        WebSearchConfig,
    )
    from tokenmind.cron.service import CronService


@dataclass
class PendingApproval:
    """One high-risk tool execution waiting for user approval."""

    approval_id: str
    session_key: str
    chat_id: str
    channel: str
    tool_id: str
    tool_name: str
    command: str
    reason: str
    working_dir: str
    requested_at: float
    future: asyncio.Future[bool]


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """

    _TOOL_RESULT_MAX_CHARS = 16_000

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 40,
        context_window_tokens: int = 65_536,
        web_search_config: WebSearchConfig | None = None,
        web_proxy: str | None = None,
        exec_config: ExecToolConfig | None = None,
        knowledge_config: KnowledgeConfig | None = None,
        cron_service: CronService | None = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        mcp_servers: dict | None = None,
        channels_config: ChannelsConfig | None = None,
        templates_config: TemplatesConfig | None = None,
        config_path: Path | None = None,
        creative_config: CreativeConfig | None = None,
    ):
        from tokenmind.config.loader import load_config
        from tokenmind.config.schema import (
            CreativeConfig,
            ExecToolConfig,
            KnowledgeConfig,
            TemplatesConfig,
            WebSearchConfig,
        )
        from tokenmind.templates_engine import TemplateRenderer

        self.bus = bus
        self.channels_config = channels_config
        self.provider = provider
        self._config_path = config_path
        self._config_mtime = config_path.stat().st_mtime_ns if config_path and config_path.exists() else None
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.context_window_tokens = context_window_tokens
        self.web_search_config = web_search_config or WebSearchConfig()
        self.web_proxy = web_proxy
        self.exec_config = exec_config or ExecToolConfig()
        self.knowledge_config = knowledge_config or KnowledgeConfig()
        self.templates_config = templates_config or TemplatesConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace
        if creative_config is not None:
            self.creative_config = creative_config
        elif config_path and config_path.exists():
            try:
                self.creative_config = load_config(config_path).creative
            except Exception:
                self.creative_config = CreativeConfig()
        else:
            self.creative_config = CreativeConfig()

        self.context = ContextBuilder(workspace)
        self.knowledge = KnowledgeService(
            workspace,
            vector_backend=self.knowledge_config.vector_backend,
            chunk_size=self.knowledge_config.chunk_size,
            chunk_overlap=self.knowledge_config.chunk_overlap,
            top_k=self.knowledge_config.top_k,
            embedding_model=self.knowledge_config.embedding_model,
            embedding_api_key=self.knowledge_config.embedding_api_key,
            embedding_api_base=self.knowledge_config.embedding_api_base,
            rerank_model=self.knowledge_config.rerank_model,
            rerank_api_key=self.knowledge_config.rerank_api_key,
            rerank_api_base=self.knowledge_config.rerank_api_base,
            rerank_top_n=self.knowledge_config.rerank_top_n,
        )
        self.template_renderer = TemplateRenderer()
        self.sessions = session_manager or SessionManager(workspace)
        self.attachments = AttachmentStore(workspace)
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            web_search_config=self.web_search_config,
            web_proxy=web_proxy,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
        )

        self._running = False
        self._mcp_servers = mcp_servers or {}
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connecting = False
        self._active_tasks: dict[str, list[asyncio.Task]] = {}  # session_key -> tasks
        self._background_tasks: set[asyncio.Task] = set()
        self._processing_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
        self._pending_approvals: dict[str, PendingApproval] = {}
        self.audit = AuditLogger(workspace)
        self.memory_consolidator = MemoryConsolidator(
            workspace=workspace,
            provider=provider,
            model=self.model,
            sessions=self.sessions,
            context_window_tokens=context_window_tokens,
            build_messages=self.context.build_messages,
            get_tool_definitions=self.tools.get_definitions,
            templates_config=self.templates_config,
            template_renderer=self.template_renderer,
        )
        self._register_default_tools()
        self._sync_creative_tools()

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        extra_read = [BUILTIN_SKILLS_DIR] if allowed_dir else None
        self.tools.register(ReadFileTool(workspace=self.workspace, allowed_dir=allowed_dir, extra_allowed_dirs=extra_read))
        for cls in (WriteFileTool, EditFileTool, ListDirTool):
            self.tools.register(cls(workspace=self.workspace, allowed_dir=allowed_dir))
        self.tools.register(ExecTool(
            working_dir=str(self.workspace),
            timeout=self.exec_config.timeout,
            restrict_to_workspace=self.restrict_to_workspace,
            path_append=self.exec_config.path_append,
        ))
        self.tools.register(WebSearchTool(config=self.web_search_config, proxy=self.web_proxy))
        self.tools.register(WebFetchTool(proxy=self.web_proxy))
        self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))
        self.tools.register(DeliverAttachmentTool(store=self.attachments, retention=timedelta(days=30)))
        self.tools.register(SpawnTool(manager=self.subagents))
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))

    def _sync_creative_tools(self) -> None:
        """Register or remove creative tools based on current config."""
        image_capability = getattr(self.creative_config, "image", None)
        if ImageGenerationService.is_configured(image_capability):
            self.tools.register(
                GenerateImageTool(
                    service=ImageGenerationService(image_capability),
                    store=self.attachments,
                    retention=timedelta(days=30),
                )
            )
            return
        self.tools.unregister("generate_image")

    def _ensure_current_provider(self) -> None:
        """Reload config and recreate provider if the config file changed on disk."""
        if not self._config_path or not self._config_path.exists():
            return
        try:
            current_mtime = self._config_path.stat().st_mtime_ns
        except OSError:
            return
        if current_mtime == self._config_mtime:
            return

        from tokenmind.cli.commands import _make_provider
        from tokenmind.config.loader import load_config

        logger.info("Config file changed, reloading provider...")
        cfg = load_config()
        self._config_mtime = current_mtime

        # Recreate provider with new config
        new_provider = _make_provider(cfg)
        self.provider = new_provider
        self.model = cfg.agents.defaults.model

        # Update subagents and memory_consolidator which also hold provider references
        self.subagents.provider = new_provider
        self.memory_consolidator.provider = new_provider
        self.knowledge_config = cfg.tools.knowledge
        self.creative_config = cfg.creative
        self.knowledge.configure(
            vector_backend=cfg.tools.knowledge.vector_backend,
            chunk_size=cfg.tools.knowledge.chunk_size,
            chunk_overlap=cfg.tools.knowledge.chunk_overlap,
            top_k=cfg.tools.knowledge.top_k,
            embedding_model=cfg.tools.knowledge.embedding_model,
            embedding_api_key=cfg.tools.knowledge.embedding_api_key,
            embedding_api_base=cfg.tools.knowledge.embedding_api_base,
            rerank_model=cfg.tools.knowledge.rerank_model,
            rerank_api_key=cfg.tools.knowledge.rerank_api_key,
            rerank_api_base=cfg.tools.knowledge.rerank_api_base,
            rerank_top_n=cfg.tools.knowledge.rerank_top_n,
        )
        self.templates_config = cfg.templates
        self.memory_consolidator.templates_config = cfg.templates
        self._sync_creative_tools()

        logger.info("Provider reloaded: {} / {}", cfg.agents.defaults.provider, cfg.agents.defaults.model)

    async def _connect_mcp(self) -> None:
        """Connect to configured MCP servers (one-time, lazy)."""
        if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
            return
        self._mcp_connecting = True
        from tokenmind.agent.tools.mcp import connect_mcp_servers
        try:
            self._mcp_stack = AsyncExitStack()
            await self._mcp_stack.__aenter__()
            await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)
            self._mcp_connected = True
        except BaseException as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
            if self._mcp_stack:
                try:
                    await self._mcp_stack.aclose()
                except Exception:
                    pass
                self._mcp_stack = None
        finally:
            self._mcp_connecting = False

    def _set_tool_context(
        self,
        channel: str,
        chat_id: str,
        message_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """Update context for all tools that need routing info."""
        for name in (
            "message",
            "spawn",
            "cron",
            "deliver_attachment",
            "generate_image",
            "run_browser_task",
        ):
            if tool := self.tools.get(name):
                if hasattr(tool, "set_context"):
                    if name == "run_browser_task":
                        tool.set_context(channel, chat_id, message_id, project_id)
                    else:
                        tool.set_context(
                            channel,
                            chat_id,
                            *([message_id] if name in {"message", "deliver_attachment", "generate_image"} else []),
                        )

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """Remove <think>…</think> blocks that some models embed in content."""
        if not text:
            return None
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip() or None

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        """Format tool calls as concise hint, e.g. 'web_search("query")'."""
        def _fmt(tc):
            args = (tc.arguments[0] if isinstance(tc.arguments, list) else tc.arguments) or {}
            val = next(iter(args.values()), None) if isinstance(args, dict) else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'
        return ", ".join(_fmt(tc) for tc in tool_calls)

    def _should_confirm_high_risk_exec(
        self,
        msg: InboundMessage | None,
        tool_name: str,
        args: dict[str, Any],
    ) -> tuple[bool, str | None, str]:
        """Determine whether a tool call should pause for user confirmation."""
        if msg is None:
            return False, None, ""
        if tool_name != "exec" or not self.exec_config.confirm_high_risk:
            return False, None, ""
        if msg.channel != "web":
            return False, None, ""

        command = str(args.get("command") or "").strip()
        if not command:
            return False, None, ""

        working_dir = str(args.get("working_dir") or self.workspace)
        reason = ExecTool.get_high_risk_reason(command) or (
            "Shell commands can modify files, install software, access the network, or change the local environment."
        )
        return True, reason, working_dir

    async def _request_tool_approval(
        self,
        *,
        msg: InboundMessage,
        tool_id: str,
        tool_name: str,
        command: str,
        reason: str,
        working_dir: str,
    ) -> bool:
        """Ask the current web session to approve a high-risk tool call."""
        approval_id = f"{msg.session_key}:{tool_id}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        pending = PendingApproval(
            approval_id=approval_id,
            session_key=msg.session_key,
            chat_id=msg.chat_id,
            channel=msg.channel,
            tool_id=tool_id,
            tool_name=tool_name,
            command=command,
            reason=reason,
            working_dir=working_dir,
            requested_at=time.monotonic(),
            future=future,
        )
        self._pending_approvals[approval_id] = pending

        self.audit.record(
            "tool.exec.approval_requested",
            "pending",
            session_key=msg.session_key,
            channel=msg.channel,
            chat_id=msg.chat_id,
            actor=msg.sender_id,
            details={
                "approval_id": approval_id,
                "tool_id": tool_id,
                "command": command,
                "working_dir": working_dir,
                "reason": reason,
            },
        )
        await self.bus.publish_outbound(OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=command,
            metadata={
                "_approval_required": True,
                "_approval_id": approval_id,
                "_tool_id": tool_id,
                "_tool_name": tool_name,
                "_risk_reason": reason,
                "_working_dir": working_dir,
                "_approval_timeout_s": self.exec_config.approval_timeout_s,
            },
        ))
        try:
            approved = await asyncio.wait_for(
                future,
                timeout=max(1, self.exec_config.approval_timeout_s),
            )
            self.audit.record(
                "tool.exec.approval_resolved",
                "approved" if approved else "rejected",
                session_key=msg.session_key,
                channel=msg.channel,
                chat_id=msg.chat_id,
                actor=msg.sender_id,
                details={
                    "approval_id": approval_id,
                    "tool_id": tool_id,
                    "command": command,
                },
            )
            return approved
        except asyncio.TimeoutError:
            self.audit.record(
                "tool.exec.approval_resolved",
                "timeout",
                session_key=msg.session_key,
                channel=msg.channel,
                chat_id=msg.chat_id,
                actor=msg.sender_id,
                details={
                    "approval_id": approval_id,
                    "tool_id": tool_id,
                    "command": command,
                },
            )
            return False
        finally:
            self._pending_approvals.pop(approval_id, None)

    async def _handle_tool_approval(self, msg: InboundMessage) -> None:
        """Resolve a pending high-risk tool approval from the frontend."""
        approval_id = str((msg.metadata or {}).get("approval_id") or "").strip()
        approved = bool((msg.metadata or {}).get("approved"))
        pending = self._pending_approvals.get(approval_id)
        if not approval_id or not pending:
            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="This approval request has expired.",
                metadata={"_approval_error": True},
            ))
            return
        if pending.session_key != msg.session_key:
            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="This approval request does not belong to the current session.",
                metadata={"_approval_error": True},
            ))
            return
        if not pending.future.done():
            pending.future.set_result(approved)

    def _cancel_pending_approvals(self, session_key: str) -> int:
        """Reject and clear any pending approvals for a session."""
        cancelled = 0
        for approval_id, pending in list(self._pending_approvals.items()):
            if pending.session_key != session_key:
                continue
            if not pending.future.done():
                pending.future.set_result(False)
                cancelled += 1
            self._pending_approvals.pop(approval_id, None)
        return cancelled

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        *,
        msg: InboundMessage | None = None,
        on_progress: Callable[..., Awaitable[None]] | None = None,
    ) -> tuple[str | None, list[str], list[dict]]:
        """Run the agent iteration loop."""
        self._ensure_current_provider()
        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []
        repeated_tool_errors: dict[str, int] = {}

        while iteration < self.max_iterations:
            iteration += 1

            tool_defs = self.tools.get_definitions()

            response = await self.provider.chat_with_retry(
                messages=messages,
                tools=tool_defs,
                model=self.model,
            )

            if response.has_tool_calls:
                if on_progress:
                    thought = self._strip_think(response.content)
                    if thought:
                        await on_progress(thought)
                    # Note: Don't send tool_hint here since we send individual tool_start events below

                tool_call_dicts = [
                    tc.to_openai_tool_call()
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )

                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info("Tool call: {}({})", tool_call.name, args_str[:200])
                    # Build full command string for display
                    full_command = f'{tool_call.name}({args_str})'
                    self.audit.record(
                        f"tool.{tool_call.name}.requested",
                        "pending",
                        session_key=msg.session_key if msg else None,
                        channel=msg.channel if msg else None,
                        chat_id=msg.chat_id if msg else None,
                        actor=msg.sender_id if msg else None,
                        details={
                            "tool_id": tool_call.id,
                            "arguments": tool_call.arguments,
                        },
                    )
                    # Send tool_start event with full command
                    if on_progress:
                        await on_progress(
                            full_command,
                            tool_start=True,
                            tool_id=tool_call.id,
                            tool_name=tool_call.name,
                        )
                    should_confirm, risk_reason, working_dir = self._should_confirm_high_risk_exec(
                        msg, tool_call.name, tool_call.arguments or {}
                    )
                    if should_confirm:
                        if on_progress:
                            await on_progress(
                                f"Waiting for approval: {risk_reason}",
                                tool_id=tool_call.id,
                                tool_name=tool_call.name,
                            )
                        approved = await self._request_tool_approval(
                            msg=msg,
                            tool_id=tool_call.id,
                            tool_name=tool_call.name,
                            command=str((tool_call.arguments or {}).get("command") or full_command),
                            reason=risk_reason or "This command needs confirmation.",
                            working_dir=working_dir,
                        )
                        if not approved:
                            result = "Error: Command execution was not approved by the user."
                            if on_progress:
                                await on_progress(
                                    full_command,
                                    tool_error=True,
                                    tool_id=tool_call.id,
                                    tool_name=tool_call.name,
                                    detail="Execution cancelled because approval was rejected or timed out.",
                                )
                            messages = self.context.add_tool_result(
                                messages, tool_call.id, tool_call.name, result
                            )
                            self.audit.record(
                                "tool.exec.executed",
                                "rejected",
                                session_key=msg.session_key if msg else None,
                                channel=msg.channel if msg else None,
                                chat_id=msg.chat_id if msg else None,
                                actor=msg.sender_id if msg else None,
                                details={
                                    "tool_id": tool_call.id,
                                    "command": (tool_call.arguments or {}).get("command"),
                                    "working_dir": working_dir,
                                    "reason": risk_reason,
                                },
                            )
                            continue
                    logger.info(f"[TOOL] {tool_call.name} START (id={tool_call.id})")
                    start_time = time.monotonic()
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    duration = time.monotonic() - start_time
                    logger.info(f"[TOOL] {tool_call.name} END (id={tool_call.id}, duration={duration:.2f}s)")
                    outcome = "error" if isinstance(result, str) and result.startswith("Error") else "success"
                    self.audit.record(
                        f"tool.{tool_call.name}.executed",
                        outcome,
                        session_key=msg.session_key if msg else None,
                        channel=msg.channel if msg else None,
                        chat_id=msg.chat_id if msg else None,
                        actor=msg.sender_id if msg else None,
                        details={
                            "tool_id": tool_call.id,
                            "arguments": tool_call.arguments,
                            "duration_s": round(duration, 3),
                        },
                    )
                    if on_progress:
                        if outcome == "error":
                            await on_progress(
                                full_command,
                                tool_error=True,
                                tool_id=tool_call.id,
                                tool_name=tool_call.name,
                                detail=result,
                            )
                        else:
                            await on_progress(
                                f"{tool_call.name} completed",
                                tool_end=True,
                                tool_id=tool_call.id,
                                tool_name=tool_call.name,
                                duration=duration,
                            )
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
                    if outcome == "error":
                        error_signature = json.dumps(
                            {
                                "name": tool_call.name,
                                "arguments": tool_call.arguments,
                                "result": result,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                        repeated_tool_errors[error_signature] = repeated_tool_errors.get(error_signature, 0) + 1
                        if repeated_tool_errors[error_signature] >= 2:
                            final_content = (
                                f"{tool_call.name} was called repeatedly with invalid parameters, "
                                "so I stopped this tool loop. For an existing local file, attach it with "
                                'source_type="local_file" and a real path instead of inline null content.'
                            )
                            logger.warning(
                                "Stopping repeated invalid tool loop: {}({})",
                                tool_call.name,
                                args_str[:200],
                            )
                            return final_content, tools_used, messages
            else:
                clean = self._strip_think(response.content)
                # Don't persist error responses to session history — they can
                # poison the context and cause permanent 400 loops (#1303).
                if response.finish_reason == "error":
                    logger.error("LLM returned error: {}", (clean or "")[:200])
                    final_content = clean or "Sorry, I encountered an error calling the AI model."
                    break
                messages = self.context.add_assistant_message(
                    messages, clean, reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )
                final_content = clean
                break

        if final_content is None and iteration >= self.max_iterations:
            logger.warning("Max iterations ({}) reached", self.max_iterations)
            final_content = (
                f"I reached the maximum number of tool call iterations ({self.max_iterations}) "
                "without completing the task. You can try breaking the task into smaller steps."
            )

        return final_content, tools_used, messages

    async def run(self) -> None:
        """Run the agent loop, dispatching messages as tasks to stay responsive to /stop."""
        self._running = True
        await self._connect_mcp()
        logger.info("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                # Preserve real task cancellation so shutdown can complete cleanly.
                # Only ignore non-task CancelledError signals that may leak from integrations.
                if not self._running or asyncio.current_task().cancelling():
                    raise
                continue
            except Exception as e:
                logger.warning("Error consuming inbound message: {}, continuing...", e)
                continue

            cmd = msg.content.strip().lower()
            if cmd == "/stop":
                await self._handle_stop(msg)
            elif cmd == "/restart":
                await self._handle_restart(msg)
            elif (msg.metadata or {}).get("control") == "tool_approval":
                await self._handle_tool_approval(msg)
            else:
                task = asyncio.create_task(self._dispatch(msg))
                self._active_tasks.setdefault(msg.session_key, []).append(task)
                task.add_done_callback(lambda t, k=msg.session_key: self._active_tasks.get(k, []) and self._active_tasks[k].remove(t) if t in self._active_tasks.get(k, []) else None)

    async def _handle_stop(self, msg: InboundMessage) -> None:
        """Cancel all active tasks and subagents for the session."""
        tasks = self._active_tasks.pop(msg.session_key, [])
        approval_cancelled = self._cancel_pending_approvals(msg.session_key)
        cancelled = sum(1 for t in tasks if not t.done() and t.cancel())
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        sub_cancelled = await self.subagents.cancel_by_session(msg.session_key)
        total = cancelled + sub_cancelled + approval_cancelled
        content = f"Stopped {total} task(s)." if total else "No active task to stop."
        await self.bus.publish_outbound(OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=content,
        ))

    async def _handle_restart(self, msg: InboundMessage) -> None:
        """Restart the process in-place via os.execv."""
        await self.bus.publish_outbound(OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content="Restarting...",
        ))

        async def _do_restart():
            await asyncio.sleep(1)
            # Use -m tokenmind instead of sys.argv[0] for Windows compatibility
            # (sys.argv[0] may be just "tokenmind" without full path on Windows)
            os.execv(sys.executable, [sys.executable, "-m", "tokenmind"] + sys.argv[1:])

        asyncio.create_task(_do_restart())

    async def _dispatch(self, msg: InboundMessage) -> None:
        """Process a message under the global lock."""
        lock = self._processing_locks.get(msg.session_key)
        if lock is None:
            lock = asyncio.Lock()
            self._processing_locks[msg.session_key] = lock
        async with lock:
            try:
                response = await self._process_message(msg)
                if response is not None:
                    await self.bus.publish_outbound(response)
                elif msg.channel == "cli":
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel, chat_id=msg.chat_id,
                        content="", metadata=msg.metadata or {},
                    ))
            except asyncio.CancelledError:
                logger.info("Task cancelled for session {}", msg.session_key)
                raise
            except Exception:
                logger.exception("Error processing message for session {}", msg.session_key)
                await self.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content="Sorry, I encountered an error.",
                ))

    async def close_mcp(self) -> None:
        """Drain pending background archives, then close MCP connections."""
        if self._background_tasks:
            await asyncio.gather(*tuple(self._background_tasks), return_exceptions=True)
            self._background_tasks.clear()
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass  # MCP SDK cancel scope cleanup is noisy but harmless
            self._mcp_stack = None

    def _schedule_background(self, coro) -> None:
        """Schedule a coroutine as a tracked background task (drained on shutdown)."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")

    def _render_response_template(
        self,
        content: str,
        *,
        msg: InboundMessage,
        session_key: str,
        tools_used: list[str],
    ) -> str:
        """Render an optional Jinja2 response template around the final assistant text."""
        rendered = self.template_renderer.render(
            self.templates_config.response,
            content=content,
            model=self.model,
            channel=msg.channel,
            chat_id=msg.chat_id,
            session_key=session_key,
            sender_id=msg.sender_id,
            tools_used=tools_used,
        )
        return rendered or content

    @staticmethod
    def _build_knowledge_citations(knowledge_chunks: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Build compact, user-facing citation metadata from retrieved knowledge chunks."""
        if not knowledge_chunks:
            return []

        citations: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for chunk in knowledge_chunks:
            knowledge_base_id = str(chunk.get("knowledge_base_id") or "")
            document_id = str(chunk.get("document_id") or "")
            chunk_id = str(chunk.get("id") or "")
            dedupe_key = (knowledge_base_id, document_id, chunk_id)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            excerpt = str(chunk.get("content") or "").strip()
            if len(excerpt) > 180:
                excerpt = excerpt[:177] + "..."

            citations.append(
                {
                    "id": chunk_id,
                    "knowledge_base_id": knowledge_base_id,
                    "knowledge_base_name": chunk.get("knowledge_base_name") or knowledge_base_id or "知识库",
                    "document_id": document_id,
                    "document_name": chunk.get("document_name") or document_id or "文档",
                    "excerpt": excerpt,
                    "score": chunk.get("score"),
                }
            )
            if len(citations) >= 3:
                break
        return citations

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> OutboundMessage | None:
        """Process a single inbound message and return the response."""
        # System messages: parse origin from chat_id ("channel:chat_id")
        if msg.channel == "system":
            channel, chat_id = (msg.chat_id.split(":", 1) if ":" in msg.chat_id
                                else ("cli", msg.chat_id))
            logger.info("Processing system message from {}", msg.sender_id)
            key = f"{channel}:{chat_id}"
            session = self.sessions.get_or_create(key)
            await self.memory_consolidator.maybe_consolidate_by_tokens(session)
            self._set_tool_context(channel, chat_id, msg.metadata.get("message_id"), session.project_id)
            history = session.get_history(max_messages=0)
            # Subagent results should be assistant role, other system messages use user role
            current_role = "assistant" if msg.sender_id == "subagent" else "user"
            messages = self.context.build_messages(
                history=history,
                current_message=msg.content, channel=channel, chat_id=chat_id,
                current_role=current_role,
            )
            final_content, _, all_msgs = await self._run_agent_loop(messages, msg=msg)
            self._save_turn(session, all_msgs, 1 + len(history))
            self.sessions.save(session)
            self._schedule_background(self.memory_consolidator.maybe_consolidate_by_tokens(session))
            return OutboundMessage(channel=channel, chat_id=chat_id,
                                  content=final_content or "Background task completed.")

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)

        key = session_key or msg.session_key
        session = self.sessions.get_or_create(key)

        # Slash commands
        cmd = msg.content.strip().lower()
        if cmd == "/new":
            snapshot = session.messages[session.last_consolidated:]
            session.clear()
            self.sessions.save(session)
            self.sessions.invalidate(session.key)

            if snapshot:
                self._schedule_background(self.memory_consolidator.archive_messages(snapshot))

            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                  content="New session started.")
        if cmd == "/help":
            lines = [
                "🐈 TokenMind commands:",
                "/new — Start a new conversation",
                "/stop — Stop the current task",
                "/restart — Restart the bot",
                "/help — Show available commands",
            ]
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content="\n".join(lines),
            )
        await self.memory_consolidator.maybe_consolidate_by_tokens(session)

        self._set_tool_context(msg.channel, msg.chat_id, msg.metadata.get("message_id"), session.project_id)
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.start_turn()
        if attachment_tool := self.tools.get("deliver_attachment"):
            if isinstance(attachment_tool, DeliverAttachmentTool):
                attachment_tool.start_turn()
        if image_tool := self.tools.get("generate_image"):
            if isinstance(image_tool, GenerateImageTool):
                image_tool.start_turn()
                image_tool.set_available_attachments(msg.metadata.get("attachments") if msg.metadata else None)

        history = session.get_history(max_messages=0)
        knowledge_chunks = self.knowledge.retrieve_for_session(key, msg.content)
        knowledge_citations = self._build_knowledge_citations(knowledge_chunks)
        initial_messages = self.context.build_messages(
            history=history,
            current_message=msg.content,
            media=msg.media if msg.media else None,
            attachments=msg.metadata.get("attachments") if msg.metadata else None,
            knowledge_chunks=knowledge_chunks,
            channel=msg.channel, chat_id=msg.chat_id,
        )
        raw_timeline_events: list[dict[str, Any]] = []

        async def _bus_progress(
            content: str,
            *,
            tool_hint: bool = False,
            tool_id: str | None = None,
            tool_name: str | None = None,
            tool_start: bool = False,
            tool_end: bool = False,
            tool_error: bool = False,
            duration: float | None = None,
            detail: str | None = None,
        ) -> None:
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            meta["_tool_hint"] = tool_hint
            meta["_tool_id"] = tool_id
            meta["_tool_name"] = tool_name
            meta["_tool_start"] = tool_start
            meta["_tool_end"] = tool_end
            meta["_tool_error"] = tool_error
            if duration is not None:
                meta["_tool_duration"] = duration
            if detail:
                meta["_tool_detail"] = detail
            from datetime import datetime
            raw_timeline_events.append({
                "type": "tool_start" if tool_start else "tool_end" if tool_end else "tool_error" if tool_error else "progress",
                "content": content,
                "timestamp": datetime.now().isoformat(),
                "tool_id": tool_id,
                "tool_name": tool_name,
                "duration": duration,
                "detail": detail,
            })
            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content=content, metadata=meta,
            ))

        final_content, tools_used, all_msgs = await self._run_agent_loop(
            initial_messages, msg=msg, on_progress=on_progress or _bus_progress,
        )
        assistant_attachments: list[dict[str, Any]] = []
        if attachment_tool := self.tools.get("deliver_attachment"):
            if isinstance(attachment_tool, DeliverAttachmentTool):
                assistant_attachments = attachment_tool.delivered
        if image_tool := self.tools.get("generate_image"):
            if isinstance(image_tool, GenerateImageTool) and image_tool.delivered:
                assistant_attachments = [*assistant_attachments, *image_tool.delivered]
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool) and msg.channel == "web" and message_tool._sent_in_turn:
                bridged_attachments: list[dict[str, Any]] = []
                for media_path in message_tool._sent_media:
                    try:
                        bridged_attachments.append(
                            self.attachments.create_local(
                                key,
                                source_path=media_path,
                                retention=timedelta(days=30),
                                message_id=msg.metadata.get("message_id"),
                            )
                        )
                    except HTTPException:
                        logger.warning("Failed to bridge message(media) attachment {}", media_path)
                if bridged_attachments:
                    assistant_attachments = [*assistant_attachments, *bridged_attachments]
                if message_tool._sent_content:
                    final_content = message_tool._sent_content

        if final_content is None:
            final_content = "I've completed processing but have no response to give."
        else:
            final_content = self._render_response_template(
                final_content,
                msg=msg,
                session_key=key,
                tools_used=tools_used,
            )
            if all_msgs and all_msgs[-1].get("role") == "assistant":
                updated_assistant = {**all_msgs[-1], "content": final_content}
                if knowledge_citations:
                    updated_assistant["citations"] = knowledge_citations
                if assistant_attachments:
                    updated_assistant["attachments"] = assistant_attachments
                all_msgs[-1] = updated_assistant

        if assistant_attachments and (not all_msgs or all_msgs[-1].get("role") != "assistant"):
            all_msgs = [
                *all_msgs,
                {
                    "role": "assistant",
                    "content": final_content or "",
                    "attachments": assistant_attachments,
                    **({"citations": knowledge_citations} if knowledge_citations else {}),
                },
            ]

        saved_entries = self._save_turn(session, all_msgs, 1 + len(history))
        self._save_timeline_events(session, saved_entries, raw_timeline_events)
        self.sessions.save(session)
        self._schedule_background(self.memory_consolidator.maybe_consolidate_by_tokens(session))

        if (
            (mt := self.tools.get("message"))
            and isinstance(mt, MessageTool)
            and mt._sent_in_turn
            and msg.channel != "web"
        ):
            return None

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info("Response to {}:{}: {}", msg.channel, msg.sender_id, preview)
        metadata = dict(msg.metadata or {})
        if knowledge_citations:
            metadata["_citations"] = knowledge_citations
        if assistant_attachments:
            metadata["_attachments"] = assistant_attachments
        return OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=final_content,
            metadata=metadata,
        )

    def _save_turn(self, session: Session, messages: list[dict], skip: int) -> list[dict]:
        """Save new-turn messages into session, truncating large tool results."""
        from datetime import datetime
        saved_entries: list[dict] = []
        for m in messages[skip:]:
            entry = dict(m)
            role, content = entry.get("role"), entry.get("content")
            if role == "assistant" and not content and not entry.get("tool_calls") and not entry.get("attachments"):
                continue  # skip empty assistant messages — they poison session context
            if role == "tool" and isinstance(content, str) and len(content) > self._TOOL_RESULT_MAX_CHARS:
                entry["content"] = content[:self._TOOL_RESULT_MAX_CHARS] + "\n... (truncated)"
            elif role == "user":
                if isinstance(content, str):
                    content = ContextBuilder.strip_metadata_prefix(content)
                    if not isinstance(content, str) or not content.strip():
                        continue
                    entry["content"] = content
                if isinstance(content, list):
                    filtered = []
                    for c in content:
                        if c.get("type") == "text" and isinstance(c.get("text"), str):
                            text = ContextBuilder.strip_metadata_prefix(c["text"])
                            if not text.strip():
                                continue
                            c = {**c, "text": text}
                        if (c.get("type") == "image_url"
                                and c.get("image_url", {}).get("url", "").startswith("data:image/")):
                            path = (c.get("_meta") or {}).get("path", "")
                            placeholder = f"[image: {path}]" if path else "[image]"
                            filtered.append({"type": "text", "text": placeholder})
                        else:
                            filtered.append(c)
                    if not filtered:
                        continue
                    entry["content"] = filtered
            entry.setdefault("timestamp", datetime.now().isoformat())
            session.messages.append(entry)
            saved_entries.append(entry)
        session.updated_at = datetime.now()
        return saved_entries

    def _save_timeline_events(
        self,
        session: Session,
        saved_entries: list[dict],
        raw_timeline_events: list[dict[str, Any]],
    ) -> None:
        """Persist execution timeline events separately from chat history."""
        if not raw_timeline_events:
            return

        turn_id = next(
            (
                entry.get("timestamp")
                for entry in saved_entries
                if entry.get("role") == "user" and entry.get("timestamp")
            ),
            None,
        )
        if not turn_id:
            return

        start_content_by_tool_id: dict[str, str] = {}
        for idx, event in enumerate(raw_timeline_events):
            event_type = event.get("type") or "progress"
            tool_id = event.get("tool_id")
            if event_type == "tool_start" and tool_id:
                event_id = f"{tool_id}-start"
                if isinstance(event.get("content"), str) and event.get("content"):
                    start_content_by_tool_id[tool_id] = event["content"]
            elif event_type == "tool_end" and tool_id:
                event_id = f"{tool_id}-end"
            elif event_type == "tool_error" and tool_id:
                event_id = f"{tool_id}-error"
            else:
                event_id = f"{turn_id}-progress-{idx}"

            display_content = event.get("content", "")
            if event_type in {"tool_end", "tool_error"} and tool_id and start_content_by_tool_id.get(tool_id):
                display_content = start_content_by_tool_id[tool_id]

            session.timeline_events.append({
                "id": event_id,
                "type": event_type,
                "content": display_content,
                "timestamp": event.get("timestamp"),
                "turnId": turn_id,
                "toolId": tool_id,
                "toolName": event.get("tool_name"),
                "duration": event.get("duration"),
                "detail": event.get("detail"),
            })

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """Process a message directly (for CLI or cron usage)."""
        await self._connect_mcp()
        msg = InboundMessage(channel=channel, sender_id="user", chat_id=chat_id, content=content)
        response = await self._process_message(msg, session_key=session_key, on_progress=on_progress)
        return response.content if response else ""
