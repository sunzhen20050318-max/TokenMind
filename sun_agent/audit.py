"""Structured audit logging for high-signal runtime actions."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

from loguru import logger

from sun_agent.config.loader import load_config
from sun_agent.utils.helpers import ensure_dir


class AuditLogger:
    """Append structured audit events to the workspace audit log."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self._lock = Lock()

    @property
    def log_path(self) -> Path:
        return ensure_dir(self.workspace / "logs") / "audit.jsonl"

    def is_enabled(self) -> bool:
        """Check the current config toggle, defaulting to enabled."""
        try:
            return bool(load_config().tools.audit_enabled)
        except Exception:
            logger.exception("Failed to load audit setting, defaulting to enabled")
            return True

    def record(
        self,
        action: str,
        outcome: str,
        *,
        session_key: str | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
        actor: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Persist one audit event."""
        if not self.is_enabled():
            return

        event: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "outcome": outcome,
        }
        if session_key:
            event["session_key"] = session_key
        if channel:
            event["channel"] = channel
        if chat_id:
            event["chat_id"] = chat_id
        if actor:
            event["actor"] = actor
        if details:
            event["details"] = details

        try:
            with self._lock:
                with self.log_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("Failed to write audit event: {}", action)
