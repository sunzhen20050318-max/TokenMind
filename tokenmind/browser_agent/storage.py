"""SQLite-backed persistence for browser tasks, steps, and artifacts.

Lives in ``<workspace>/browser_tasks.sqlite3`` — kept separate from the
knowledge base SQLite so each module owns its own schema lifecycle.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from tokenmind.browser_agent.models import (
    ArtifactKind,
    BrowserArtifact,
    BrowserStep,
    BrowserTask,
    StepPhase,
    TaskListItem,
    TaskStatus,
)

logger = logging.getLogger("tokenmind.browser_agent.storage")

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS browser_tasks (
        id              TEXT PRIMARY KEY,
        project_id      TEXT NOT NULL,
        session_id      TEXT,
        instruction     TEXT NOT NULL,
        start_url       TEXT,
        status          TEXT NOT NULL,
        result_summary  TEXT,
        error_detail    TEXT,
        created_at      INTEGER NOT NULL,
        started_at      INTEGER,
        finished_at     INTEGER,
        step_count      INTEGER NOT NULL DEFAULT 0,
        max_steps       INTEGER NOT NULL DEFAULT 50,
        timeout_seconds INTEGER NOT NULL DEFAULT 1800,
        metadata        TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_browser_tasks_project_status
        ON browser_tasks(project_id, status)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_browser_tasks_created
        ON browser_tasks(created_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS browser_steps (
        id                      TEXT PRIMARY KEY,
        task_id                 TEXT NOT NULL,
        step_index              INTEGER NOT NULL,
        phase                   TEXT NOT NULL,
        action_name             TEXT,
        action_args             TEXT,
        thinking                TEXT,
        observation             TEXT,
        screenshot_artifact_id  TEXT,
        success                 INTEGER NOT NULL,
        error                   TEXT,
        duration_ms             INTEGER,
        timestamp               INTEGER NOT NULL,
        FOREIGN KEY (task_id) REFERENCES browser_tasks(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_browser_steps_task
        ON browser_steps(task_id, step_index)
    """,
    """
    CREATE TABLE IF NOT EXISTS browser_artifacts (
        id                  TEXT PRIMARY KEY,
        task_id             TEXT NOT NULL,
        step_index          INTEGER,
        kind                TEXT NOT NULL,
        file_path           TEXT NOT NULL,
        source_url          TEXT,
        mime_type           TEXT,
        size_bytes          INTEGER NOT NULL DEFAULT 0,
        created_at          INTEGER NOT NULL,
        knowledge_doc_id    TEXT,
        metadata            TEXT,
        FOREIGN KEY (task_id) REFERENCES browser_tasks(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_browser_artifacts_task
        ON browser_artifacts(task_id)
    """,
]


def _ms(value: Optional[datetime]) -> Optional[int]:
    if value is None:
        return None
    return int(value.timestamp() * 1000)


def _datetime_from_ms(value: Optional[int]) -> Optional[datetime]:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000)


def _json_dump(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _json_load(value: Optional[str]) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


class BrowserTaskStorage:
    """Thin SQLite wrapper for browser task persistence."""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.db_path = self.workspace / "browser_tasks.sqlite3"
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            for stmt in _SCHEMA:
                conn.execute(stmt)
            conn.commit()

    # ── tasks ───────────────────────────────────────────────────────────

    def insert_task(self, task: BrowserTask) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO browser_tasks (
                    id, project_id, session_id, instruction, start_url, status,
                    result_summary, error_detail, created_at, started_at, finished_at,
                    step_count, max_steps, timeout_seconds, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.project_id,
                    task.session_id,
                    task.instruction,
                    task.start_url,
                    task.status.value,
                    task.result_summary,
                    task.error_detail,
                    _ms(task.created_at),
                    _ms(task.started_at),
                    _ms(task.finished_at),
                    task.step_count,
                    task.max_steps,
                    task.timeout_seconds,
                    _json_dump(task.metadata),
                ),
            )
            conn.commit()

    def update_task(
        self,
        task_id: str,
        *,
        status: Optional[TaskStatus] = None,
        result_summary: Optional[str] = None,
        error_detail: Optional[str] = None,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
        step_count: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        sets: list[str] = []
        params: list[Any] = []

        if status is not None:
            sets.append("status = ?")
            params.append(status.value)
        if result_summary is not None:
            sets.append("result_summary = ?")
            params.append(result_summary)
        if error_detail is not None:
            sets.append("error_detail = ?")
            params.append(error_detail)
        if started_at is not None:
            sets.append("started_at = ?")
            params.append(_ms(started_at))
        if finished_at is not None:
            sets.append("finished_at = ?")
            params.append(_ms(finished_at))
        if step_count is not None:
            sets.append("step_count = ?")
            params.append(step_count)
        if metadata is not None:
            sets.append("metadata = ?")
            params.append(_json_dump(metadata))

        if not sets:
            return

        params.append(task_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE browser_tasks SET {', '.join(sets)} WHERE id = ?",
                params,
            )
            conn.commit()

    def get_task(self, task_id: str) -> Optional[BrowserTask]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM browser_tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return self._row_to_task(row) if row else None

    def list_tasks(
        self,
        *,
        project_id: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TaskListItem]:
        sql = (
            "SELECT t.*, "
            "       (SELECT COUNT(*) FROM browser_artifacts a WHERE a.task_id = t.id) AS artifact_count "
            "FROM browser_tasks t WHERE 1=1"
        )
        params: list[Any] = []
        if project_id is not None:
            sql += " AND t.project_id = ?"
            params.append(project_id)
        if status is not None:
            sql += " AND t.status = ?"
            params.append(status.value)
        sql += " ORDER BY t.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_list_item(row) for row in rows]

    def delete_task(self, task_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM browser_tasks WHERE id = ?", (task_id,))
            conn.commit()

    # ── steps ───────────────────────────────────────────────────────────

    def insert_step(self, step: BrowserStep) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO browser_steps (
                    id, task_id, step_index, phase, action_name, action_args,
                    thinking, observation, screenshot_artifact_id, success, error,
                    duration_ms, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    step.id,
                    step.task_id,
                    step.step_index,
                    step.phase.value,
                    step.action_name,
                    _json_dump(step.action_args),
                    step.thinking,
                    step.observation,
                    step.screenshot_artifact_id,
                    1 if step.success else 0,
                    step.error,
                    step.duration_ms,
                    _ms(step.timestamp) or 0,
                ),
            )
            conn.commit()

    def list_steps(self, task_id: str) -> list[BrowserStep]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM browser_steps WHERE task_id = ? ORDER BY step_index ASC",
                (task_id,),
            ).fetchall()
        return [self._row_to_step(row) for row in rows]

    # ── artifacts ───────────────────────────────────────────────────────

    def insert_artifact(self, artifact: BrowserArtifact) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO browser_artifacts (
                    id, task_id, step_index, kind, file_path, source_url,
                    mime_type, size_bytes, created_at, knowledge_doc_id, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.id,
                    artifact.task_id,
                    artifact.step_index,
                    artifact.kind.value,
                    artifact.file_path,
                    artifact.source_url,
                    artifact.mime_type,
                    artifact.size_bytes,
                    _ms(artifact.created_at) or 0,
                    artifact.knowledge_doc_id,
                    _json_dump(artifact.metadata),
                ),
            )
            conn.commit()

    def list_artifacts(self, task_id: str) -> list[BrowserArtifact]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM browser_artifacts WHERE task_id = ? ORDER BY created_at ASC",
                (task_id,),
            ).fetchall()
        return [self._row_to_artifact(row) for row in rows]

    def get_artifact(self, artifact_id: str) -> Optional[BrowserArtifact]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM browser_artifacts WHERE id = ?", (artifact_id,)
            ).fetchone()
        return self._row_to_artifact(row) if row else None

    # ── row helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> BrowserTask:
        return BrowserTask(
            id=row["id"],
            project_id=row["project_id"],
            session_id=row["session_id"],
            instruction=row["instruction"],
            start_url=row["start_url"],
            status=TaskStatus(row["status"]),
            result_summary=row["result_summary"],
            error_detail=row["error_detail"],
            created_at=_datetime_from_ms(row["created_at"]) or datetime.now(),
            started_at=_datetime_from_ms(row["started_at"]),
            finished_at=_datetime_from_ms(row["finished_at"]),
            step_count=row["step_count"],
            max_steps=row["max_steps"],
            timeout_seconds=row["timeout_seconds"],
            metadata=_json_load(row["metadata"]) or {},
        )

    @staticmethod
    def _row_to_list_item(row: sqlite3.Row) -> TaskListItem:
        return TaskListItem(
            id=row["id"],
            project_id=row["project_id"],
            instruction=row["instruction"],
            status=TaskStatus(row["status"]),
            created_at=_datetime_from_ms(row["created_at"]) or datetime.now(),
            finished_at=_datetime_from_ms(row["finished_at"]),
            step_count=row["step_count"],
            artifact_count=row["artifact_count"],
        )

    @staticmethod
    def _row_to_step(row: sqlite3.Row) -> BrowserStep:
        return BrowserStep(
            id=row["id"],
            task_id=row["task_id"],
            step_index=row["step_index"],
            phase=StepPhase(row["phase"]),
            action_name=row["action_name"],
            action_args=_json_load(row["action_args"]),
            thinking=row["thinking"],
            observation=row["observation"],
            screenshot_artifact_id=row["screenshot_artifact_id"],
            success=bool(row["success"]),
            error=row["error"],
            duration_ms=row["duration_ms"],
            timestamp=_datetime_from_ms(row["timestamp"]) or datetime.now(),
        )

    @staticmethod
    def _row_to_artifact(row: sqlite3.Row) -> BrowserArtifact:
        return BrowserArtifact(
            id=row["id"],
            task_id=row["task_id"],
            step_index=row["step_index"],
            kind=ArtifactKind(row["kind"]),
            file_path=row["file_path"],
            source_url=row["source_url"],
            mime_type=row["mime_type"],
            size_bytes=row["size_bytes"],
            created_at=_datetime_from_ms(row["created_at"]) or datetime.now(),
            knowledge_doc_id=row["knowledge_doc_id"],
            metadata=_json_load(row["metadata"]) or {},
        )


# Re-export iterable type for callers that batch.
__all__ = ["BrowserTaskStorage", "Iterable"]
