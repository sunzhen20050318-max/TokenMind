"""Tests for tokenmind.usage.recorder."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tokenmind.usage import UsageRecord, UsageRecorder


@pytest.fixture
def recorder(tmp_path: Path) -> UsageRecorder:
    return UsageRecorder(tmp_path / "usage.sqlite3")


def _make_record(
    *,
    ts: datetime,
    session_id: str = "sess_a",
    provider: str = "anthropic",
    model: str = "claude-opus-4-5",
    input_tokens: int = 100,
    cached_input_tokens: int = 0,
    cache_write_tokens: int = 0,
    output_tokens: int = 50,
    reasoning_tokens: int = 0,
    project_id: str | None = None,
) -> UsageRecord:
    return UsageRecord(
        session_id=session_id,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        cache_write_tokens=cache_write_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        project_id=project_id,
        ts=ts,
    )


def test_record_roundtrip(recorder: UsageRecorder) -> None:
    ts = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    recorder.record(_make_record(ts=ts, input_tokens=200, output_tokens=80))
    rows = recorder.aggregate(group_by="day")
    assert len(rows) == 1
    assert rows[0].input_tokens == 200
    assert rows[0].output_tokens == 80
    assert rows[0].total_tokens == 280
    assert rows[0].call_count == 1


def test_record_zero_total_is_skipped(recorder: UsageRecorder) -> None:
    ts = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    recorder.record(
        _make_record(ts=ts, input_tokens=0, output_tokens=0)
    )
    assert recorder.aggregate(group_by="day") == []


def test_aggregate_by_day_groups_correctly(recorder: UsageRecorder) -> None:
    base = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
    recorder.record(_make_record(ts=base, input_tokens=100))
    recorder.record(_make_record(ts=base + timedelta(hours=3), input_tokens=200))
    recorder.record(_make_record(ts=base + timedelta(days=1), input_tokens=50))

    rows = recorder.aggregate(group_by="day")
    assert len(rows) == 2
    # Most recent first
    assert rows[0].bucket == "2026-05-02"
    assert rows[0].input_tokens == 50
    assert rows[1].bucket == "2026-05-01"
    assert rows[1].input_tokens == 300


def test_aggregate_by_month(recorder: UsageRecorder) -> None:
    recorder.record(_make_record(ts=datetime(2026, 4, 15, tzinfo=timezone.utc)))
    recorder.record(_make_record(ts=datetime(2026, 5, 1, tzinfo=timezone.utc)))
    recorder.record(_make_record(ts=datetime(2026, 5, 20, tzinfo=timezone.utc)))

    rows = recorder.aggregate(group_by="month")
    buckets = [row.bucket for row in rows]
    assert buckets == ["2026-05", "2026-04"]
    by_bucket = {row.bucket: row.call_count for row in rows}
    assert by_bucket["2026-05"] == 2
    assert by_bucket["2026-04"] == 1


def test_aggregate_by_year(recorder: UsageRecorder) -> None:
    recorder.record(_make_record(ts=datetime(2025, 6, 1, tzinfo=timezone.utc)))
    recorder.record(_make_record(ts=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    rows = recorder.aggregate(group_by="year")
    assert [row.bucket for row in rows] == ["2026", "2025"]


def test_aggregate_by_model_orders_by_usage(recorder: UsageRecorder) -> None:
    ts = datetime(2026, 5, 1, tzinfo=timezone.utc)
    recorder.record(_make_record(ts=ts, model="claude-haiku", input_tokens=100, output_tokens=10))
    recorder.record(_make_record(ts=ts, model="claude-opus", input_tokens=1000, output_tokens=100))
    rows = recorder.aggregate(group_by="model")
    assert rows[0].bucket == "claude-opus"
    assert rows[1].bucket == "claude-haiku"


def test_aggregate_by_session(recorder: UsageRecorder) -> None:
    ts = datetime(2026, 5, 1, tzinfo=timezone.utc)
    recorder.record(_make_record(ts=ts, session_id="s1", input_tokens=300))
    recorder.record(_make_record(ts=ts, session_id="s2", input_tokens=100))
    rows = recorder.aggregate(group_by="session")
    assert rows[0].bucket == "s1"
    assert rows[1].bucket == "s2"


def test_aggregate_by_provider(recorder: UsageRecorder) -> None:
    ts = datetime(2026, 5, 1, tzinfo=timezone.utc)
    recorder.record(_make_record(ts=ts, provider="anthropic", input_tokens=500))
    recorder.record(_make_record(ts=ts, provider="openai", input_tokens=300))
    rows = recorder.aggregate(group_by="provider")
    assert {row.bucket for row in rows} == {"anthropic", "openai"}


def test_date_range_filter(recorder: UsageRecorder) -> None:
    recorder.record(_make_record(ts=datetime(2026, 4, 30, tzinfo=timezone.utc)))
    recorder.record(_make_record(ts=datetime(2026, 5, 1, tzinfo=timezone.utc)))
    recorder.record(_make_record(ts=datetime(2026, 5, 5, tzinfo=timezone.utc)))

    rows = recorder.aggregate(
        group_by="day",
        start=datetime(2026, 5, 1, tzinfo=timezone.utc),
        end=datetime(2026, 5, 3, tzinfo=timezone.utc),
    )
    assert len(rows) == 1
    assert rows[0].bucket == "2026-05-01"


def test_filter_combination(recorder: UsageRecorder) -> None:
    ts = datetime(2026, 5, 1, tzinfo=timezone.utc)
    recorder.record(_make_record(ts=ts, model="m1", provider="p1", input_tokens=100))
    recorder.record(_make_record(ts=ts, model="m1", provider="p2", input_tokens=200))
    recorder.record(_make_record(ts=ts, model="m2", provider="p1", input_tokens=300))
    rows = recorder.aggregate(group_by="day", model="m1", provider="p1")
    assert len(rows) == 1
    assert rows[0].input_tokens == 100


def test_cache_fields_persist_through_aggregation(recorder: UsageRecorder) -> None:
    ts = datetime(2026, 5, 1, tzinfo=timezone.utc)
    recorder.record(
        _make_record(
            ts=ts,
            input_tokens=100,
            cached_input_tokens=900,
            cache_write_tokens=400,
            output_tokens=50,
            reasoning_tokens=200,
        )
    )
    rows = recorder.aggregate(group_by="day")
    assert rows[0].cached_input_tokens == 900
    assert rows[0].cache_write_tokens == 400
    assert rows[0].reasoning_tokens == 200
    assert rows[0].total_tokens == 100 + 900 + 400 + 50


def test_totals_summary(recorder: UsageRecorder) -> None:
    ts = datetime(2026, 5, 1, tzinfo=timezone.utc)
    recorder.record(_make_record(ts=ts, input_tokens=100, output_tokens=20))
    recorder.record(_make_record(ts=ts, input_tokens=300, output_tokens=80))
    summary = recorder.totals()
    assert summary.input_tokens == 400
    assert summary.output_tokens == 100
    assert summary.call_count == 2


def test_invalid_group_by_raises(recorder: UsageRecorder) -> None:
    with pytest.raises(ValueError):
        recorder.aggregate(group_by="hour")  # type: ignore[arg-type]


def test_limit_caps_result_set(recorder: UsageRecorder) -> None:
    base = datetime(2026, 5, 1, tzinfo=timezone.utc)
    for i in range(5):
        recorder.record(
            _make_record(
                ts=base + timedelta(days=i),
                session_id=f"s{i}",
                input_tokens=100 * (i + 1),
            )
        )
    rows = recorder.aggregate(group_by="session", limit=3)
    assert len(rows) == 3
    # Top 3 by usage, descending
    assert rows[0].bucket == "s4"
    assert rows[2].bucket == "s2"
