"""Session management for conversation history."""

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from tokenmind.agent.context import ContextBuilder
from tokenmind.config.paths import get_legacy_sessions_dir
from tokenmind.utils.helpers import ensure_dir, safe_filename


@dataclass
class Session:
    """
    A conversation session.

    Stores messages in JSONL format for easy reading and persistence.

    Important: Messages are append-only for LLM cache efficiency.
    The consolidation process writes summaries to MEMORY.md/HISTORY.md
    but does NOT modify the messages list or get_history() output.
    """

    key: str  # channel:chat_id
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    timeline_events: list[dict[str, Any]] = field(default_factory=list)
    last_consolidated: int = 0  # Number of messages already consolidated to files

    @property
    def title(self) -> str | None:
        """User-defined session title, if any."""
        title = self.metadata.get("title")
        return title.strip() if isinstance(title, str) and title.strip() else None

    def set_title(self, title: str | None) -> None:
        """Set or clear the session title."""
        if title and title.strip():
            self.metadata["title"] = title.strip()
        else:
            self.metadata.pop("title", None)
        self.updated_at = datetime.now()

    @property
    def project_id(self) -> str | None:
        value = self.metadata.get("project_id")
        return value if isinstance(value, str) and value else None

    def set_project_id(self, project_id: str | None) -> None:
        """Assign or clear the project membership for this session."""
        if project_id:
            self.metadata["project_id"] = project_id
        else:
            self.metadata.pop("project_id", None)
        self.updated_at = datetime.now()

    @property
    def active_wiki_kb_id(self) -> str | None:
        value = self.metadata.get("active_wiki_kb_id")
        return value if isinstance(value, str) and value else None

    def set_active_wiki_kb_id(self, kb_id: str | None) -> None:
        if kb_id:
            self.metadata["active_wiki_kb_id"] = kb_id
        else:
            self.metadata.pop("active_wiki_kb_id", None)
        self.updated_at = datetime.now()

    # ── Per-session preferences set via slash commands ───────────────
    # All optional; absence means "use global default". Kept in
    # ``metadata`` so they round-trip through the existing JSONL
    # persistence without schema migrations.

    @property
    def personality(self) -> str | None:
        """Reply style: ``warm`` (more empathetic, costlier) or
        ``pragmatic`` (terse). ``None`` falls back to the system default."""
        value = self.metadata.get("personality")
        if isinstance(value, str) and value in ("warm", "pragmatic"):
            return value
        return None

    def set_personality(self, personality: str | None) -> None:
        if personality in ("warm", "pragmatic"):
            self.metadata["personality"] = personality
        else:
            self.metadata.pop("personality", None)
        self.updated_at = datetime.now()

    @property
    def plan_mode(self) -> bool:
        """When True, the agent is required to call ``task_list`` before
        taking action. Defaults to off so existing sessions behave the
        same as before this feature."""
        return bool(self.metadata.get("plan_mode", False))

    def set_plan_mode(self, enabled: bool) -> None:
        if enabled:
            self.metadata["plan_mode"] = True
        else:
            self.metadata.pop("plan_mode", None)
        self.updated_at = datetime.now()

    # ── Most recent LLM call usage (populated by AgentLoop._record_usage) ──
    # Used by the /status card to show a *precise* prompt-size figure —
    # this is the actual number the API counted, not the frontend's
    # chars/4 estimate. Absence means "no LLM call has completed yet".

    @property
    def last_prompt_tokens(self) -> int | None:
        value = self.metadata.get("_last_prompt_tokens")
        return int(value) if isinstance(value, (int, float)) and value > 0 else None

    @property
    def last_prompt_at(self) -> str | None:
        value = self.metadata.get("_last_prompt_at")
        return value if isinstance(value, str) and value else None

    @property
    def last_prompt_model(self) -> str | None:
        value = self.metadata.get("_last_prompt_model")
        return value if isinstance(value, str) and value else None

    def record_last_prompt(self, tokens: int, model: str | None) -> None:
        """Cache the prompt-token count from the most recent LLM call.

        Called from ``AgentLoop._record_usage`` so the /status card has an
        authoritative number to show. We don't bump ``updated_at`` for
        this — it's metadata bookkeeping, not user-visible activity.
        """
        if tokens <= 0:
            return
        self.metadata["_last_prompt_tokens"] = int(tokens)
        self.metadata["_last_prompt_at"] = datetime.now().isoformat()
        if model:
            self.metadata["_last_prompt_model"] = model

    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """Add a message to the session."""
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        self.messages.append(msg)
        self.updated_at = datetime.now()

    def delete_message(self, timestamp: str) -> bool:
        """Remove the user message identified by ``timestamp`` along with the
        entire assistant turn it produced (tool calls, tool responses and
        final assistant reply).

        Only ``user`` messages are deletable from the chat UI — deleting
        a user message is the user's way of taking back both the question
        and any answer it triggered, so we drop everything from the user
        message up to (but not including) the next user message.

        Returns ``True`` when at least one message was removed.
        """
        target_idx: int | None = None
        for i, msg in enumerate(self.messages):
            if msg.get("timestamp") == timestamp:
                target_idx = i
                break
        if target_idx is None:
            return False

        target = self.messages[target_idx]
        if target.get("role") != "user":
            # Non-user messages can only be removed transitively (via the
            # parent user-message deletion above).
            return False

        end = target_idx + 1
        while end < len(self.messages):
            if self.messages[end].get("role") == "user":
                break
            end += 1
        del self.messages[target_idx:end]
        self.updated_at = datetime.now()
        return True

    @staticmethod
    def _find_legal_start(messages: list[dict[str, Any]]) -> int:
        """Find first index where every tool result has a matching assistant tool_call."""
        declared: set[str] = set()
        start = 0
        for i, msg in enumerate(messages):
            role = msg.get("role")
            if role == "assistant":
                for tc in msg.get("tool_calls") or []:
                    if isinstance(tc, dict) and tc.get("id"):
                        declared.add(str(tc["id"]))
            elif role == "tool":
                tid = msg.get("tool_call_id")
                if tid and str(tid) not in declared:
                    start = i + 1
                    declared.clear()
                    for prev in messages[start:i + 1]:
                        if prev.get("role") == "assistant":
                            for tc in prev.get("tool_calls") or []:
                                if isinstance(tc, dict) and tc.get("id"):
                                    declared.add(str(tc["id"]))
        return start

    def get_history(self, max_messages: int = 500) -> list[dict[str, Any]]:
        """Return unconsolidated messages for LLM input, aligned to a legal tool-call boundary."""
        unconsolidated = self.messages[self.last_consolidated:]
        sliced = unconsolidated[-max_messages:]

        # Drop leading non-user messages to avoid starting mid-turn when possible.
        for i, message in enumerate(sliced):
            if message.get("role") == "user":
                sliced = sliced[i:]
                break

        # Some providers reject orphan tool results if the matching assistant
        # tool_calls message fell outside the fixed-size history window.
        start = self._find_legal_start(sliced)
        if start:
            sliced = sliced[start:]

        out: list[dict[str, Any]] = []
        for message in sliced:
            entry: dict[str, Any] = {"role": message["role"], "content": message.get("content", "")}
            for key in ("tool_calls", "tool_call_id", "name"):
                if key in message:
                    entry[key] = message[key]
            out.append(entry)
        return out

    def clear(self) -> None:
        """Clear all messages and reset session to initial state."""
        self.messages = []
        self.timeline_events = []
        self.last_consolidated = 0
        self.updated_at = datetime.now()


class SessionManager:
    """
    Manages conversation sessions.

    Sessions are stored as JSONL files in the sessions directory.
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.sessions_dir = ensure_dir(self.workspace / "sessions")
        self.legacy_sessions_dir = get_legacy_sessions_dir()
        self._cache: dict[str, Session] = {}

    def _get_session_path(self, key: str) -> Path:
        """Get the file path for a session."""
        safe_key = safe_filename(key.replace(":", "_"))
        return self.sessions_dir / f"{safe_key}.jsonl"

    def _get_legacy_session_path(self, key: str) -> Path:
        """Legacy global session path (~/.tokenmind/sessions/)."""
        safe_key = safe_filename(key.replace(":", "_"))
        return self.legacy_sessions_dir / f"{safe_key}.jsonl"

    def get_or_create(self, key: str) -> Session:
        """
        Get an existing session or create a new one.

        Args:
            key: Session key (usually channel:chat_id).

        Returns:
            The session.
        """
        if key in self._cache:
            return self._cache[key]

        session = self._load(key)
        if session is None:
            session = Session(key=key)

        self._cache[key] = session
        return session

    def _load(self, key: str) -> Session | None:
        """Load a session from disk."""
        path = self._get_session_path(key)
        if not path.exists():
            legacy_path = self._get_legacy_session_path(key)
            if legacy_path.exists():
                try:
                    shutil.move(str(legacy_path), str(path))
                    logger.info("Migrated session {} from legacy path", key)
                except Exception:
                    logger.exception("Failed to migrate session {}", key)

        if not path.exists():
            return None

        try:
            messages = []
            timeline_events = []
            metadata = {}
            created_at = None
            updated_at = None
            last_consolidated = 0

            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    data = json.loads(line)

                    if data.get("_type") == "metadata":
                        metadata = data.get("metadata", {})
                        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
                        updated_at = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None
                        last_consolidated = data.get("last_consolidated", 0)
                    elif data.get("_type") == "timeline_event":
                        event = data.get("event")
                        if isinstance(event, dict):
                            timeline_events.append(event)
                    else:
                        messages.append(data)

            messages, changed = self._sanitize_loaded_messages(messages)

            session = Session(
                key=key,
                messages=messages,
                created_at=created_at or datetime.now(),
                updated_at=updated_at or created_at or datetime.now(),
                metadata=metadata,
                timeline_events=timeline_events,
                last_consolidated=last_consolidated
            )
            if changed:
                logger.info("Sanitized legacy knowledge metadata from session {}", key)
                self.save(session)
            return session
        except Exception as e:
            logger.warning("Failed to load session {}: {}", key, e)
            return None

    @staticmethod
    def _sanitize_loaded_messages(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
        changed = False
        sanitized_messages: list[dict[str, Any]] = []
        for message in messages:
            next_message = dict(message)
            content = next_message.get("content")
            if isinstance(content, str):
                cleaned = ContextBuilder.strip_metadata_prefix(content)
                if cleaned != content:
                    changed = True
                    next_message["content"] = cleaned
            elif isinstance(content, list):
                sanitized_blocks: list[dict[str, Any]] = []
                block_changed = False
                for block in content:
                    if not isinstance(block, dict):
                        sanitized_blocks.append(block)
                        continue
                    next_block = dict(block)
                    if isinstance(next_block.get("text"), str):
                        cleaned_text = ContextBuilder.strip_metadata_prefix(next_block["text"])
                        if cleaned_text != next_block["text"]:
                            block_changed = True
                            next_block["text"] = cleaned_text
                    sanitized_blocks.append(next_block)
                if block_changed:
                    changed = True
                    next_message["content"] = sanitized_blocks
            sanitized_messages.append(next_message)
        return sanitized_messages, changed

    def save(self, session: Session) -> None:
        """Save a session to disk."""
        path = self._get_session_path(session.key)

        with open(path, "w", encoding="utf-8") as f:
            metadata_line = {
                "_type": "metadata",
                "key": session.key,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "metadata": session.metadata,
                "last_consolidated": session.last_consolidated
            }
            f.write(json.dumps(metadata_line, ensure_ascii=False) + "\n")
            for event in session.timeline_events:
                f.write(json.dumps({
                    "_type": "timeline_event",
                    "event": event,
                }, ensure_ascii=False) + "\n")
            for msg in session.messages:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")

        self._cache[session.key] = session

    def invalidate(self, key: str) -> None:
        """Remove a session from the in-memory cache."""
        self._cache.pop(key, None)

    def list_sessions(self) -> list[dict[str, Any]]:
        """
        List all sessions.

        Returns:
            List of session info dicts.
        """
        sessions = []

        for path in self.sessions_dir.glob("*.jsonl"):
            try:
                # Read just the metadata line
                with open(path, encoding="utf-8") as f:
                    first_line = f.readline().strip()
                    if first_line:
                        data = json.loads(first_line)
                        if data.get("_type") == "metadata":
                            key = data.get("key") or path.stem.replace("_", ":", 1)
                            sessions.append({
                                "key": key,
                                "created_at": data.get("created_at"),
                                "updated_at": data.get("updated_at"),
                                "path": str(path),
                                "title": (data.get("metadata") or {}).get("title"),
                                "project_id": (data.get("metadata") or {}).get("project_id"),
                            })
            except Exception:
                continue

        return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)
