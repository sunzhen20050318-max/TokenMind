"""Memory system for persistent agent memory."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import weakref
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from loguru import logger

from tokenmind.config.schema import MemoryConfig, TemplatesConfig
from tokenmind.templates_engine import TemplateRenderer
from tokenmind.utils.helpers import (
    ensure_dir,
    estimate_message_tokens,
    estimate_prompt_tokens_chain,
    estimate_text_tokens,
)

if TYPE_CHECKING:
    from tokenmind.providers.base import LLMProvider
    from tokenmind.session.manager import Session, SessionManager


def _save_memory_tool(summary_max_tokens: int) -> list[dict[str, Any]]:
    """Build the save_memory tool schema with the configured summary cap baked in."""
    return [
        {
            "type": "function",
            "function": {
                "name": "save_memory",
                "description": "Save the memory consolidation result to persistent storage.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "history_entry": {
                            "type": "string",
                            "description": "A paragraph summarizing key events/decisions/topics. "
                            "Start with [YYYY-MM-DD HH:MM]. Include detail useful for grep search.",
                        },
                        "memory_update": {
                            "type": "string",
                            "description": "Full updated long-term memory as markdown. Include all existing "
                            "facts plus new ones. Return unchanged if nothing new.",
                        },
                        "memory_summary": {
                            "type": "string",
                            "description": (
                                "A compressed summary of the FULL updated long-term memory "
                                f"(memory_update), at most ~{summary_max_tokens} tokens. THIS is what "
                                "gets injected into the system prompt every turn — MEMORY.md itself is "
                                "not. Keep only the most important, durable facts: who the user is, "
                                "stable preferences, active projects, key decisions. Drop one-off "
                                "details and anything stale. If memory_update is already shorter than "
                                "the cap, this may equal it."
                            ),
                        },
                    },
                    "required": ["history_entry", "memory_update", "memory_summary"],
                },
            },
        }
    ]


def _purify_memory_tool(purify_max_tokens: int, summary_max_tokens: int) -> list[dict[str, Any]]:
    """Build the purify_memory tool schema for the periodic MEMORY.md compaction pass."""
    return [
        {
            "type": "function",
            "function": {
                "name": "purify_memory",
                "description": "Rewrite the long-term memory file to be smaller and cleaner.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "purified_memory": {
                            "type": "string",
                            "description": (
                                "The rewritten full long-term memory as markdown, at most "
                                f"~{purify_max_tokens} tokens. Merge duplicates, drop stale or "
                                "superseded facts, and tighten wording — but PRESERVE every durable "
                                "fact (identity, preferences, ongoing projects, important decisions). "
                                "This replaces MEMORY.md wholesale, so do not lose anything important."
                            ),
                        },
                        "memory_summary": {
                            "type": "string",
                            "description": (
                                "A compressed summary of purified_memory, at most "
                                f"~{summary_max_tokens} tokens — the version injected into the system "
                                "prompt every turn."
                            ),
                        },
                    },
                    "required": ["purified_memory", "memory_summary"],
                },
            },
        }
    ]


def _ensure_text(value: Any) -> str:
    """Normalize tool-call payload values to text for file storage."""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _normalize_save_memory_args(args: Any) -> dict[str, Any] | None:
    """Normalize provider tool-call arguments to the expected dict shape."""
    if isinstance(args, str):
        args = json.loads(args)
    if isinstance(args, list):
        return args[0] if args and isinstance(args[0], dict) else None
    return args if isinstance(args, dict) else None

_TOOL_CHOICE_ERROR_MARKERS = (
    "tool_choice",
    "toolchoice",
    "does not support",
    'should be ["none", "auto"]',
)


def _is_tool_choice_unsupported(content: str | None) -> bool:
    """Detect provider errors caused by forced tool_choice being unsupported."""
    text = (content or "").lower()
    return any(m in text for m in _TOOL_CHOICE_ERROR_MARKERS)


class MemoryStore:
    """Two-layer memory: MEMORY.md (long-term facts) + HISTORY.md (grep-searchable log)."""

    _MAX_FAILURES_BEFORE_RAW_ARCHIVE = 3
    _DEFAULT_SYSTEM_PROMPT = (
        "You are a memory consolidation agent. Call the save_memory tool with your consolidation of the conversation."
    )
    _DEFAULT_PROMPT_TEMPLATE = """Process this conversation and call the save_memory tool with your consolidation.

## Current Long-term Memory
{{ current_memory or "(empty)" }}

## Conversation to Process
{{ conversation }}"""

    def __init__(
        self,
        workspace: Path,
        templates_config: TemplatesConfig | None = None,
        template_renderer: TemplateRenderer | None = None,
        project_id: str | None = None,
        memory_config: MemoryConfig | None = None,
    ):
        # Project-scoped memory lives under workspace/projects/<id>/memory
        # so each project has its own isolated MEMORY.md + HISTORY.md. The
        # global workspace/memory/ still exists for non-project sessions
        # — pre-existing user memory there is untouched.
        if project_id:
            self.memory_dir = ensure_dir(workspace / "projects" / project_id / "memory")
        else:
            self.memory_dir = ensure_dir(workspace / "memory")
        self.workspace = workspace
        self.project_id = project_id
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "HISTORY.md"
        # Compressed summary that actually gets injected into the system
        # prompt (the full MEMORY.md no longer is). ``.memory_meta.json``
        # tracks which MEMORY.md state the summary was built from + the last
        # purification time.
        self.summary_file = self.memory_dir / "MEMORY_SUMMARY.md"
        self.meta_file = self.memory_dir / ".memory_meta.json"
        self._consecutive_failures = 0
        self.templates_config = templates_config or TemplatesConfig()
        self.template_renderer = template_renderer or TemplateRenderer()
        self.memory_config = memory_config or MemoryConfig()
        # Hash of the MEMORY.md state we last *attempted* a standalone summary
        # refresh for. Gates the out-of-band refresh so a failed/in-flight
        # attempt isn't re-fired every turn for the same content.
        self._summary_attempt_hash: str | None = None

    def read_long_term(self) -> str:
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def write_long_term(self, content: str) -> None:
        self.memory_file.write_text(content, encoding="utf-8")

    def read_summary(self) -> str:
        if self.summary_file.exists():
            return self.summary_file.read_text(encoding="utf-8")
        return ""

    def write_summary(self, content: str) -> None:
        self.summary_file.write_text(content, encoding="utf-8")

    def read_meta(self) -> dict[str, Any]:
        if self.meta_file.exists():
            try:
                data = json.loads(self.meta_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _update_meta(self, **fields: Any) -> None:
        meta = self.read_meta()
        meta.update(fields)
        try:
            self.meta_file.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            logger.warning("Failed to write memory meta at {}", self.meta_file)

    @staticmethod
    def _content_hash(text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

    @staticmethod
    def _truncate_to_tokens(text: str, max_tokens: int) -> str:
        """Best-effort head truncation to a token budget (stopgap injection)."""
        if max_tokens <= 0 or estimate_text_tokens(text) <= max_tokens:
            return text
        # tokens ≈ chars/4 for mixed text; bias low then trim by line.
        approx_chars = max_tokens * 4
        head = text[:approx_chars]
        while head and estimate_text_tokens(head) > max_tokens:
            head = head[: int(len(head) * 0.9)]
        return head.rstrip()

    def read_archive(self) -> str:
        if self.history_file.exists():
            return self.history_file.read_text(encoding="utf-8")
        return ""

    def append_history(self, entry: str) -> None:
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    def get_memory_context(self) -> str:
        """Return the long-term memory block injected into the system prompt.

        When summaries are enabled we inject the compressed summary (capped at
        ``summary_max_tokens``), NOT the full MEMORY.md. Fallbacks, in order:
          1. fresh summary (its source hash matches current MEMORY.md) → use it
          2. MEMORY.md already under the cap → inject it directly (current and
             accurate beats a summary; summaries only earn their keep once
             memory grows large)
          3. stale summary present (MEMORY.md was edited out-of-band) → keep
             serving that last-known-good summary until the background refresh
             replaces it — better than a truncated head, and bounded in size
          4. no summary at all (big memory, never summarized) → bounded head of
             MEMORY.md as a last-resort stopgap
        """
        long_term = self.read_long_term()
        if not long_term.strip():
            return ""
        if not self.memory_config.summary_enabled:
            return f"## Long-term Memory\n{long_term}"

        cap = self.memory_config.summary_max_tokens
        summary = self.read_summary()
        meta = self.read_meta()
        summary_fresh = (
            bool(summary.strip())
            and meta.get("summary_source_hash") == self._content_hash(long_term)
        )
        if summary_fresh:
            return f"## Long-term Memory\n{summary}"
        if estimate_text_tokens(long_term) <= cap:
            return f"## Long-term Memory\n{long_term}"
        if summary.strip():
            # Last-known-good summary from before the edit. The background
            # refresh (scheduled via summary_refresh_target) will replace it.
            return f"## Long-term Memory\n{summary}"
        return (
            f"## Long-term Memory\n{self._truncate_to_tokens(long_term, cap)}\n\n"
            "[memory summary pending — showing a truncated head]"
        )

    @staticmethod
    def _format_messages(messages: list[dict]) -> str:
        lines = []
        for message in messages:
            if not message.get("content"):
                continue
            tools = f" [tools: {', '.join(message['tools_used'])}]" if message.get("tools_used") else ""
            lines.append(
                f"[{message.get('timestamp', '?')[:16]}] {message['role'].upper()}{tools}: {message['content']}"
            )
        return "\n".join(lines)

    async def consolidate(
        self,
        messages: list[dict],
        provider: LLMProvider,
        model: str,
    ) -> bool:
        """Consolidate the provided message chunk into MEMORY.md + HISTORY.md."""
        if not messages:
            return True

        current_memory = self.read_long_term()
        conversation = self._format_messages(messages)
        system_prompt = self.template_renderer.render(
            self.templates_config.memory_system,
            role_name="memory consolidation agent",
            current_memory=current_memory,
            conversation=conversation,
            message_count=len(messages),
            model=model,
        ) or self._DEFAULT_SYSTEM_PROMPT
        prompt = self.template_renderer.render(
            self.templates_config.memory_prompt or self._DEFAULT_PROMPT_TEMPLATE,
            current_memory=current_memory,
            conversation=conversation,
            message_count=len(messages),
            model=model,
        ) or self._DEFAULT_PROMPT_TEMPLATE.replace("{{ current_memory or \"(empty)\" }}", current_memory or "(empty)").replace("{{ conversation }}", conversation)

        chat_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        save_tool = _save_memory_tool(self.memory_config.summary_max_tokens)
        try:
            forced = {"type": "function", "function": {"name": "save_memory"}}
            response = await provider.chat_with_retry(
                messages=chat_messages,
                tools=save_tool,
                model=model,
                tool_choice=forced,
            )

            if response.finish_reason == "error" and _is_tool_choice_unsupported(
                response.content
            ):
                logger.warning("Forced tool_choice unsupported, retrying with auto")
                response = await provider.chat_with_retry(
                    messages=chat_messages,
                    tools=save_tool,
                    model=model,
                    tool_choice="auto",
                )

            if not response.has_tool_calls:
                logger.warning(
                    "Memory consolidation: LLM did not call save_memory "
                    "(finish_reason={}, content_len={}, content_preview={})",
                    response.finish_reason,
                    len(response.content or ""),
                    (response.content or "")[:200],
                )
                return self._fail_or_raw_archive(messages)

            args = _normalize_save_memory_args(response.tool_calls[0].arguments)
            if args is None:
                logger.warning("Memory consolidation: unexpected save_memory arguments")
                return self._fail_or_raw_archive(messages)

            if "history_entry" not in args or "memory_update" not in args:
                logger.warning("Memory consolidation: save_memory payload missing required fields")
                return self._fail_or_raw_archive(messages)

            entry = args["history_entry"]
            update = args["memory_update"]

            if entry is None or update is None:
                logger.warning("Memory consolidation: save_memory payload contains null required fields")
                return self._fail_or_raw_archive(messages)

            entry = _ensure_text(entry).strip()
            if not entry:
                logger.warning("Memory consolidation: history_entry is empty after normalization")
                return self._fail_or_raw_archive(messages)

            self.append_history(entry)
            update = _ensure_text(update)
            memory_changed = update != current_memory
            if memory_changed:
                self.write_long_term(update)

            # Summary is folded into this same call (no extra LLM round-trip).
            # Refresh it whenever the model returns one, or when memory changed
            # but the model omitted it (fall back to a bounded head so the
            # injected block stays under the cap).
            if self.memory_config.summary_enabled:
                summary = args.get("memory_summary")
                summary_text = _ensure_text(summary).strip() if summary is not None else ""
                if not summary_text and memory_changed:
                    summary_text = self._truncate_to_tokens(
                        update, self.memory_config.summary_max_tokens
                    )
                if summary_text:
                    self.write_summary(summary_text)
                    self._update_meta(summary_source_hash=self._content_hash(update))

            self._consecutive_failures = 0
            logger.info("Memory consolidation done for {} messages", len(messages))
            return True
        except Exception:
            logger.exception("Memory consolidation failed")
            return self._fail_or_raw_archive(messages)

    async def maybe_purify(self, provider: LLMProvider, model: str) -> bool:
        """Periodically compress MEMORY.md back under ``purify_max_tokens``.

        Time-gated by ``purify_interval_days`` so the (heavy, full-file) LLM
        pass runs at most that often. Returns True iff a purification ran.
        Cheap no-op otherwise: a meta read + a token estimate.
        """
        cfg = self.memory_config
        if cfg.purify_interval_days <= 0 or cfg.purify_max_tokens <= 0:
            return False

        meta = self.read_meta()
        last = float(meta.get("last_purified_at") or 0)
        if time.time() - last < cfg.purify_interval_days * 86400:
            return False

        long_term = self.read_long_term()
        if estimate_text_tokens(long_term) <= cfg.purify_max_tokens:
            # Under the cap — nothing to do, but stamp the timer so we don't
            # re-estimate every consolidation until the interval elapses again.
            self._update_meta(last_purified_at=time.time())
            return False

        tools = _purify_memory_tool(cfg.purify_max_tokens, cfg.summary_max_tokens)
        chat_messages = [
            {
                "role": "system",
                "content": (
                    "You compress a long-term memory file. Call purify_memory with a "
                    "tighter rewrite that preserves every durable fact but removes "
                    "duplication and stale entries."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Current MEMORY.md is too large (target < {cfg.purify_max_tokens} "
                    "tokens). Rewrite it and produce a summary.\n\n"
                    f"## Current MEMORY.md\n{long_term}"
                ),
            },
        ]
        try:
            forced = {"type": "function", "function": {"name": "purify_memory"}}
            response = await provider.chat_with_retry(
                messages=chat_messages, tools=tools, model=model, tool_choice=forced
            )
            if response.finish_reason == "error" and _is_tool_choice_unsupported(
                response.content
            ):
                response = await provider.chat_with_retry(
                    messages=chat_messages, tools=tools, model=model, tool_choice="auto"
                )
            if not response.has_tool_calls:
                logger.warning("Memory purify: LLM did not call purify_memory")
                return False
            args = _normalize_save_memory_args(response.tool_calls[0].arguments)
            if not args or not args.get("purified_memory"):
                logger.warning("Memory purify: missing purified_memory")
                return False

            purified = _ensure_text(args["purified_memory"]).strip()
            if not purified:
                return False
            self.write_long_term(purified)

            summary = args.get("memory_summary")
            summary_text = _ensure_text(summary).strip() if summary is not None else ""
            if not summary_text:
                summary_text = self._truncate_to_tokens(purified, cfg.summary_max_tokens)
            if cfg.summary_enabled and summary_text:
                self.write_summary(summary_text)
            self._update_meta(
                last_purified_at=time.time(),
                summary_source_hash=self._content_hash(purified),
            )
            logger.info(
                "Memory purified: {} -> {} tokens",
                estimate_text_tokens(long_term),
                estimate_text_tokens(purified),
            )
            return True
        except Exception:
            logger.exception("Memory purify failed")
            return False

    def summary_refresh_target(self) -> str | None:
        """Return the MEMORY.md hash needing a standalone summary, else None.

        Fires only when the file was changed out-of-band (e.g. hand-edited) so
        the on-disk summary is stale, AND the file is large enough to warrant a
        summary (small files are injected raw). Hash-gated against
        ``_summary_attempt_hash`` so a single edit triggers at most one attempt.
        """
        if not self.memory_config.summary_enabled:
            return None
        long_term = self.read_long_term()
        if not long_term.strip():
            return None
        if estimate_text_tokens(long_term) <= self.memory_config.summary_max_tokens:
            return None
        current_hash = self._content_hash(long_term)
        if self._summary_attempt_hash == current_hash:
            return None  # already attempted / in-flight for this exact content
        meta = self.read_meta()
        if meta.get("summary_source_hash") == current_hash and self.read_summary().strip():
            return None  # summary already fresh
        return current_hash

    async def regenerate_summary(self, provider: LLMProvider, model: str) -> bool:
        """Standalone summary-only LLM pass over the current MEMORY.md.

        Used to refresh the injected summary after an out-of-band edit, without
        waiting for the next consolidation. Marks the attempt hash up front so a
        transient failure doesn't get retried every turn for the same content.
        """
        if not self.memory_config.summary_enabled:
            return False
        long_term = self.read_long_term()
        if not long_term.strip():
            return False
        current_hash = self._content_hash(long_term)
        self._summary_attempt_hash = current_hash
        cap = self.memory_config.summary_max_tokens
        chat_messages = [
            {
                "role": "system",
                "content": (
                    "You compress a user's long-term memory file into a concise summary "
                    "that an AI assistant reads in its system prompt every turn."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Summarize the long-term memory below into at most ~{cap} tokens. "
                    "Keep ONLY durable, important facts: who the user is, stable "
                    "preferences, active projects, key decisions, recurring context. Drop "
                    "one-off details and anything stale. Preserve the user's language. "
                    "Output ONLY the summary as markdown — no preamble.\n\n"
                    f"## MEMORY.md\n{long_term}"
                ),
            },
        ]
        try:
            response = await provider.chat_with_retry(messages=chat_messages, model=model)
            summary = (response.content or "").strip()
            if not summary:
                logger.warning("Summary refresh: empty response from provider")
                return False
            self.write_summary(summary)
            self._update_meta(summary_source_hash=current_hash)
            logger.info(
                "Summary refreshed: {} -> {} tokens",
                estimate_text_tokens(long_term),
                estimate_text_tokens(summary),
            )
            return True
        except Exception:
            logger.exception("Summary refresh failed")
            return False

    def _fail_or_raw_archive(self, messages: list[dict]) -> bool:
        """Increment failure count; after threshold, raw-archive messages and return True."""
        self._consecutive_failures += 1
        if self._consecutive_failures < self._MAX_FAILURES_BEFORE_RAW_ARCHIVE:
            return False
        self._raw_archive(messages)
        self._consecutive_failures = 0
        return True

    def _raw_archive(self, messages: list[dict]) -> None:
        """Fallback: dump raw messages to HISTORY.md without LLM summarization."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.append_history(
            f"[{ts}] [RAW] {len(messages)} messages\n"
            f"{self._format_messages(messages)}"
        )
        logger.warning(
            "Memory consolidation degraded: raw-archived {} messages", len(messages)
        )


def split_history_entries(content: str) -> list[str]:
    """Split HISTORY.md content into visible archive blocks."""
    return [chunk.strip() for chunk in content.split("\n\n") if chunk.strip()]


class MemoryConsolidator:
    """Owns consolidation policy, locking, and session offset updates."""

    _MAX_CONSOLIDATION_ROUNDS = 5

    def __init__(
        self,
        workspace: Path,
        provider: LLMProvider,
        model: str,
        sessions: SessionManager,
        context_window_tokens: int,
        build_messages: Callable[..., list[dict[str, Any]]],
        get_tool_definitions: Callable[[], list[dict[str, Any]]],
        templates_config: TemplatesConfig | None = None,
        template_renderer: TemplateRenderer | None = None,
        memory_config: MemoryConfig | None = None,
    ):
        self._memory_config = memory_config or MemoryConfig()
        # Default (global) store — used for non-project sessions and as
        # the public ``.store`` attribute existing callers / templates_config
        # accessors hook into.
        self.store = MemoryStore(
            workspace,
            templates_config=templates_config,
            template_renderer=template_renderer,
            memory_config=self._memory_config,
        )
        self.workspace = workspace
        self._templates_config = templates_config
        self._template_renderer = template_renderer
        # Cache project-scoped stores so we don't recreate them on every
        # consolidation pass.
        self._project_stores: dict[str, MemoryStore] = {}
        self.provider = provider
        self.model = model
        self.sessions = sessions
        self.context_window_tokens = context_window_tokens
        self._build_messages = build_messages
        self._get_tool_definitions = get_tool_definitions
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
        # Strong refs to fire-and-forget summary-refresh tasks so they aren't
        # garbage-collected mid-flight; discarded on completion.
        self._summary_tasks: set[asyncio.Task] = set()

    def schedule_summary_refresh_if_needed(self, session: Session | None = None) -> None:
        """Kick off a background summary refresh if MEMORY.md was edited out-of-band.

        Non-blocking: gates synchronously (cheap file reads + hash) and only
        spawns an LLM call when the on-disk summary is stale for a large
        MEMORY.md. Safe to call every turn — it's a no-op in the common case.
        """
        store = self._store_for_session(session) if session is not None else self.store
        target_hash = store.summary_refresh_target()
        if target_hash is None:
            return
        # Mark the attempt now (sync) so a second turn doesn't double-schedule
        # before the task runs.
        store._summary_attempt_hash = target_hash
        key = getattr(session, "key", "global")
        task = asyncio.create_task(self._run_summary_refresh(store, key))
        self._summary_tasks.add(task)
        task.add_done_callback(self._summary_tasks.discard)

    async def _run_summary_refresh(self, store: MemoryStore, key: str) -> None:
        try:
            if await store.regenerate_summary(self.provider, self.model):
                logger.info("Background summary refresh done for {}", key)
        except Exception:
            logger.exception("Background summary refresh failed for {}", key)

    def _store_for_session(self, session: Session) -> MemoryStore:
        """Pick the MemoryStore that owns this session's consolidated memory.

        Sessions with ``metadata['project_id']`` write to a per-project
        store under ``workspace/projects/<id>/memory/``; other sessions
        write to the global ``workspace/memory/`` (legacy behaviour).
        """
        project_id = (session.metadata or {}).get("project_id") if session else None
        if not project_id:
            return self.store
        store = self._project_stores.get(project_id)
        if store is None:
            store = MemoryStore(
                self.workspace,
                templates_config=self._templates_config,
                template_renderer=self._template_renderer,
                project_id=project_id,
                memory_config=self._memory_config,
            )
            self._project_stores[project_id] = store
        return store

    @property
    def templates_config(self) -> TemplatesConfig:
        return self.store.templates_config

    @templates_config.setter
    def templates_config(self, value: TemplatesConfig) -> None:
        self.store.templates_config = value

    def get_lock(self, session_key: str) -> asyncio.Lock:
        """Return the shared consolidation lock for one session."""
        return self._locks.setdefault(session_key, asyncio.Lock())

    async def consolidate_messages(
        self,
        messages: list[dict[str, object]],
        session: Session | None = None,
    ) -> bool:
        """Archive a selected message chunk into persistent memory.

        When ``session`` is provided and it belongs to a project, the
        consolidation lands in that project's isolated memory store
        (``workspace/projects/<id>/memory/``). Otherwise it writes to
        the global ``workspace/memory/`` — same as before.
        """
        store = self._store_for_session(session) if session is not None else self.store
        ok = await store.consolidate(messages, self.provider, self.model)
        if ok:
            # Time-gated; cheap no-op unless the purify interval has elapsed
            # and MEMORY.md is over its cap.
            try:
                await store.maybe_purify(self.provider, self.model)
            except Exception:
                logger.exception("Memory purification check failed")
        return ok

    def pick_consolidation_boundary(
        self,
        session: Session,
        tokens_to_remove: int,
    ) -> tuple[int, int] | None:
        """Pick a user-turn boundary that removes enough old prompt tokens."""
        start = session.last_consolidated
        if start >= len(session.messages) or tokens_to_remove <= 0:
            return None

        removed_tokens = 0
        last_boundary: tuple[int, int] | None = None
        for idx in range(start, len(session.messages)):
            message = session.messages[idx]
            if idx > start and message.get("role") == "user":
                last_boundary = (idx, removed_tokens)
                if removed_tokens >= tokens_to_remove:
                    return last_boundary
            removed_tokens += estimate_message_tokens(message)

        return last_boundary

    def estimate_session_prompt_tokens(self, session: Session) -> tuple[int, str]:
        """Estimate current prompt size for the normal session history view."""
        history = session.get_history(max_messages=0)
        channel, chat_id = (session.key.split(":", 1) if ":" in session.key else (None, None))
        probe_messages = self._build_messages(
            history=history,
            current_message="[token-probe]",
            channel=channel,
            chat_id=chat_id,
            project_id=(session.metadata or {}).get("project_id"),
        )
        return estimate_prompt_tokens_chain(
            self.provider,
            self.model,
            probe_messages,
            self._get_tool_definitions(),
        )

    async def archive_messages(
        self,
        messages: list[dict[str, object]],
        session: Session | None = None,
    ) -> bool:
        """Archive messages with guaranteed persistence (retries until raw-dump fallback)."""
        if not messages:
            return True
        for _ in range(self.store._MAX_FAILURES_BEFORE_RAW_ARCHIVE):
            if await self.consolidate_messages(messages, session=session):
                return True
        return False

    async def force_consolidate(self, session: Session) -> tuple[int, int]:
        """Force-compact session history regardless of token threshold.

        Triggered by the user-initiated ``/compact`` command. Picks the
        latest safe user-turn boundary inside the unconsolidated portion
        and archives everything before it into HISTORY.md/MEMORY.md,
        advancing ``session.last_consolidated`` so the LLM no longer sees
        the compacted chunk. The most recent user turn is preserved for
        conversational continuity.

        Returns ``(previous_offset, new_offset)``. When nothing is
        eligible (e.g. only one turn left, or no message at all) the two
        values are equal and the caller should report "nothing to compact".
        """
        previous_offset = session.last_consolidated
        if not session.messages:
            return (previous_offset, previous_offset)

        lock = self.get_lock(session.key)
        async with lock:
            # Pass a huge token budget so pick_consolidation_boundary
            # returns the *latest* user-msg boundary it can find — i.e.
            # we consolidate as much as legally possible while keeping
            # the most recent user turn intact.
            boundary = self.pick_consolidation_boundary(session, tokens_to_remove=10**12)
            if boundary is None:
                return (previous_offset, session.last_consolidated)
            end_idx = boundary[0]
            chunk = session.messages[session.last_consolidated:end_idx]
            if not chunk:
                return (previous_offset, session.last_consolidated)
            logger.info(
                "Force consolidate {}: {} msgs ({} → {})",
                session.key,
                len(chunk),
                session.last_consolidated,
                end_idx,
            )
            if not await self.consolidate_messages(chunk, session=session):
                return (previous_offset, session.last_consolidated)
            session.last_consolidated = end_idx
            self.sessions.save(session)
            return (previous_offset, end_idx)

    async def maybe_consolidate_by_tokens(self, session: Session) -> None:
        """Loop: archive old messages until prompt fits within half the context window."""
        # Independent of consolidation: refresh the injected summary if the user
        # hand-edited MEMORY.md since it was last summarized. Fire-and-forget.
        self.schedule_summary_refresh_if_needed(session)

        if not session.messages or self.context_window_tokens <= 0:
            return

        lock = self.get_lock(session.key)
        async with lock:
            target = self.context_window_tokens // 2
            estimated, source = self.estimate_session_prompt_tokens(session)
            if estimated <= 0:
                return
            if estimated < self.context_window_tokens:
                logger.debug(
                    "Token consolidation idle {}: {}/{} via {}",
                    session.key,
                    estimated,
                    self.context_window_tokens,
                    source,
                )
                return

            for round_num in range(self._MAX_CONSOLIDATION_ROUNDS):
                if estimated <= target:
                    return

                boundary = self.pick_consolidation_boundary(session, max(1, estimated - target))
                if boundary is None:
                    logger.debug(
                        "Token consolidation: no safe boundary for {} (round {})",
                        session.key,
                        round_num,
                    )
                    return

                end_idx = boundary[0]
                chunk = session.messages[session.last_consolidated:end_idx]
                if not chunk:
                    return

                logger.info(
                    "Token consolidation round {} for {}: {}/{} via {}, chunk={} msgs",
                    round_num,
                    session.key,
                    estimated,
                    self.context_window_tokens,
                    source,
                    len(chunk),
                )
                if not await self.consolidate_messages(chunk, session=session):
                    return
                session.last_consolidated = end_idx
                self.sessions.save(session)

                estimated, source = self.estimate_session_prompt_tokens(session)
                if estimated <= 0:
                    return
