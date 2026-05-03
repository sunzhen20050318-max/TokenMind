"""SQLite-backed token usage recorder.

Captures one row per LLM call. Aggregation is delegated to SQL `GROUP BY`
so the storage layer stays simple and the query layer stays declarative.

The recorder writes synchronously (SQLite handles concurrent writers via
BEGIN IMMEDIATE). Calls happen off the request hot path — the AgentLoop
records after the LLM response has already been streamed to the user.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

GroupBy = Literal["day", "month", "year", "model", "session", "provider"]

_VALID_GROUP_BY: frozenset[str] = frozenset(
    {"day", "month", "year", "model", "session", "provider"}
)

_GROUP_BY_SQL: dict[str, str] = {
    "day": "substr(ts, 1, 10)",
    "month": "substr(ts, 1, 7)",
    "year": "substr(ts, 1, 4)",
    "model": "model",
    "session": "session_id",
    "provider": "provider",
}


@dataclass(frozen=True)
class UsageRecord:
    """One LLM call's token usage.

    All token fields default to 0 so providers that don't expose a particular
    dimension (e.g. Ollama has no caching) record clean zeros.
    """

    session_id: str
    provider: str
    model: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    project_id: str | None = None
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.cached_input_tokens
            + self.cache_write_tokens
            + self.output_tokens
        )


@dataclass(frozen=True)
class UsageAggregateRow:
    """One row of an aggregation result, keyed by the group_by dimension."""

    bucket: str
    input_tokens: int
    cached_input_tokens: int
    cache_write_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    call_count: int


class UsageRecorder:
    """Append-only SQLite store for token usage records."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS token_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    project_id TEXT,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    cached_input_tokens INTEGER NOT NULL DEFAULT 0,
                    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_token_usage_ts
                    ON token_usage(ts);
                CREATE INDEX IF NOT EXISTS idx_token_usage_session
                    ON token_usage(session_id);
                CREATE INDEX IF NOT EXISTS idx_token_usage_model
                    ON token_usage(model);
                """
            )

    def record(self, record: UsageRecord) -> None:
        """Persist one usage row. No-op if total_tokens is zero."""
        if record.total_tokens <= 0:
            return
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO token_usage (
                    ts, session_id, project_id, provider, model,
                    input_tokens, cached_input_tokens, cache_write_tokens,
                    output_tokens, reasoning_tokens, total_tokens
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.ts.astimezone(timezone.utc).isoformat(),
                    record.session_id,
                    record.project_id,
                    record.provider,
                    record.model,
                    record.input_tokens,
                    record.cached_input_tokens,
                    record.cache_write_tokens,
                    record.output_tokens,
                    record.reasoning_tokens,
                    record.total_tokens,
                ),
            )

    def aggregate(
        self,
        *,
        group_by: GroupBy,
        start: datetime | None = None,
        end: datetime | None = None,
        provider: str | None = None,
        model: str | None = None,
        session_id: str | None = None,
        limit: int | None = None,
    ) -> list[UsageAggregateRow]:
        """Aggregate token usage along one dimension.

        Buckets are returned in descending order — most recent date or
        highest total — so the UI can render top-N without re-sorting.
        """
        if group_by not in _VALID_GROUP_BY:
            raise ValueError(f"invalid group_by: {group_by!r}")

        bucket_expr = _GROUP_BY_SQL[group_by]
        where: list[str] = []
        params: list[object] = []
        if start is not None:
            where.append("ts >= ?")
            params.append(start.astimezone(timezone.utc).isoformat())
        if end is not None:
            where.append("ts < ?")
            params.append(end.astimezone(timezone.utc).isoformat())
        if provider is not None:
            where.append("provider = ?")
            params.append(provider)
        if model is not None:
            where.append("model = ?")
            params.append(model)
        if session_id is not None:
            where.append("session_id = ?")
            params.append(session_id)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        order_sql = (
            "ORDER BY bucket DESC"
            if group_by in {"day", "month", "year"}
            else "ORDER BY total_tokens DESC"
        )
        limit_sql = f"LIMIT {int(limit)}" if limit else ""

        sql = f"""
            SELECT
                {bucket_expr} AS bucket,
                COALESCE(SUM(input_tokens), 0),
                COALESCE(SUM(cached_input_tokens), 0),
                COALESCE(SUM(cache_write_tokens), 0),
                COALESCE(SUM(output_tokens), 0),
                COALESCE(SUM(reasoning_tokens), 0),
                COALESCE(SUM(total_tokens), 0),
                COUNT(*)
            FROM token_usage
            {where_sql}
            GROUP BY bucket
            {order_sql}
            {limit_sql}
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            UsageAggregateRow(
                bucket=str(row[0]),
                input_tokens=int(row[1]),
                cached_input_tokens=int(row[2]),
                cache_write_tokens=int(row[3]),
                output_tokens=int(row[4]),
                reasoning_tokens=int(row[5]),
                total_tokens=int(row[6]),
                call_count=int(row[7]),
            )
            for row in rows
        ]

    def totals(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        provider: str | None = None,
        model: str | None = None,
        session_id: str | None = None,
    ) -> UsageAggregateRow:
        """Single-row summary scoped by the same filters as :meth:`aggregate`."""
        where: list[str] = []
        params: list[object] = []
        if start is not None:
            where.append("ts >= ?")
            params.append(start.astimezone(timezone.utc).isoformat())
        if end is not None:
            where.append("ts < ?")
            params.append(end.astimezone(timezone.utc).isoformat())
        if provider is not None:
            where.append("provider = ?")
            params.append(provider)
        if model is not None:
            where.append("model = ?")
            params.append(model)
        if session_id is not None:
            where.append("session_id = ?")
            params.append(session_id)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        sql = f"""
            SELECT
                COALESCE(SUM(input_tokens), 0),
                COALESCE(SUM(cached_input_tokens), 0),
                COALESCE(SUM(cache_write_tokens), 0),
                COALESCE(SUM(output_tokens), 0),
                COALESCE(SUM(reasoning_tokens), 0),
                COALESCE(SUM(total_tokens), 0),
                COUNT(*)
            FROM token_usage
            {where_sql}
        """
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return UsageAggregateRow(
            bucket="total",
            input_tokens=int(row[0]),
            cached_input_tokens=int(row[1]),
            cache_write_tokens=int(row[2]),
            output_tokens=int(row[3]),
            reasoning_tokens=int(row[4]),
            total_tokens=int(row[5]),
            call_count=int(row[6]),
        )
