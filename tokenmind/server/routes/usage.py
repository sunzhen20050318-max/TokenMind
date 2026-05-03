"""Token usage statistics API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from tokenmind.server.dependencies import get_usage_recorder
from tokenmind.usage import UsageRecorder

router = APIRouter(prefix="/api/usage", tags=["usage"])

GroupBy = Literal["day", "month", "year", "model", "session", "provider"]


class _Base(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class UsageRow(_Base):
    bucket: str
    input_tokens: int
    cached_input_tokens: int
    cache_write_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    call_count: int


class UsageAggregateResponse(_Base):
    group_by: str
    items: list[UsageRow]
    summary: UsageRow


def _require_recorder() -> UsageRecorder:
    recorder = get_usage_recorder()
    if recorder is None:
        raise HTTPException(status_code=503, detail="Usage recorder not initialized")
    return recorder


@router.get("/aggregate", response_model=UsageAggregateResponse)
def get_usage_aggregate(
    group_by: GroupBy = Query("day", alias="groupBy"),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    provider: str | None = Query(None),
    model: str | None = Query(None),
    session_id: str | None = Query(None, alias="sessionId"),
    limit: int = Query(100, ge=1, le=1000),
    recorder: UsageRecorder = Depends(_require_recorder),
) -> UsageAggregateResponse:
    """Return token usage grouped by the chosen dimension plus a totals summary.

    Date filters use UTC; the SQLite store always writes ISO-8601 UTC, so a
    date-only `start=2026-05-01` matches everything from that day's 00:00 UTC
    onwards. Pass `end` exclusive to scope to a half-open range.
    """
    rows = recorder.aggregate(
        group_by=group_by,
        start=start,
        end=end,
        provider=provider,
        model=model,
        session_id=session_id,
        limit=limit,
    )
    summary = recorder.totals(
        start=start,
        end=end,
        provider=provider,
        model=model,
        session_id=session_id,
    )
    return UsageAggregateResponse(
        group_by=group_by,
        items=[
            UsageRow(
                bucket=row.bucket,
                input_tokens=row.input_tokens,
                cached_input_tokens=row.cached_input_tokens,
                cache_write_tokens=row.cache_write_tokens,
                output_tokens=row.output_tokens,
                reasoning_tokens=row.reasoning_tokens,
                total_tokens=row.total_tokens,
                call_count=row.call_count,
            )
            for row in rows
        ],
        summary=UsageRow(
            bucket=summary.bucket,
            input_tokens=summary.input_tokens,
            cached_input_tokens=summary.cached_input_tokens,
            cache_write_tokens=summary.cache_write_tokens,
            output_tokens=summary.output_tokens,
            reasoning_tokens=summary.reasoning_tokens,
            total_tokens=summary.total_tokens,
            call_count=summary.call_count,
        ),
    )
