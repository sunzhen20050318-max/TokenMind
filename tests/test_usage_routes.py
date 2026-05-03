"""Integration tests for the /api/usage routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tokenmind.server.dependencies import set_usage_recorder
from tokenmind.server.routes.usage import router as usage_router
from tokenmind.usage import UsageRecord, UsageRecorder


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    recorder = UsageRecorder(tmp_path / "usage.sqlite3")
    base = datetime(2026, 5, 1, tzinfo=timezone.utc)

    def add(**overrides: object) -> None:
        defaults = dict(
            session_id="s1",
            provider="anthropic",
            model="claude-opus-4-5",
            input_tokens=100,
            output_tokens=50,
            ts=base,
        )
        defaults.update(overrides)
        recorder.record(UsageRecord(**defaults))

    add(input_tokens=200, output_tokens=80)
    add(input_tokens=300, output_tokens=120, model="claude-haiku")
    add(input_tokens=150, output_tokens=40, provider="openai", model="gpt-4o")
    add(
        input_tokens=400,
        cached_input_tokens=100,
        cache_write_tokens=50,
        output_tokens=200,
        ts=base + timedelta(days=1),
    )

    set_usage_recorder(recorder)
    app = FastAPI()
    app.include_router(usage_router)
    yield TestClient(app)
    set_usage_recorder(None)


def test_aggregate_by_day(client: TestClient) -> None:
    r = client.get("/api/usage/aggregate?groupBy=day")
    assert r.status_code == 200
    body = r.json()
    assert body["groupBy"] == "day"
    buckets = [row["bucket"] for row in body["items"]]
    assert buckets == ["2026-05-02", "2026-05-01"]
    assert body["summary"]["callCount"] == 4


def test_aggregate_by_model(client: TestClient) -> None:
    body = client.get("/api/usage/aggregate?groupBy=model").json()
    by_model = {row["bucket"]: row for row in body["items"]}
    assert "claude-opus-4-5" in by_model
    assert "claude-haiku" in by_model
    assert "gpt-4o" in by_model


def test_aggregate_by_provider(client: TestClient) -> None:
    body = client.get("/api/usage/aggregate?groupBy=provider").json()
    by_provider = {row["bucket"]: row["totalTokens"] for row in body["items"]}
    assert by_provider["anthropic"] > by_provider["openai"]


def test_aggregate_by_session(client: TestClient) -> None:
    body = client.get("/api/usage/aggregate?groupBy=session").json()
    assert body["items"][0]["bucket"] == "s1"


def test_aggregate_filters_by_provider(client: TestClient) -> None:
    body = client.get("/api/usage/aggregate?groupBy=day&provider=openai").json()
    assert body["summary"]["callCount"] == 1
    assert body["summary"]["totalTokens"] == 190


def test_aggregate_filters_by_model(client: TestClient) -> None:
    body = client.get(
        "/api/usage/aggregate?groupBy=day&model=claude-haiku"
    ).json()
    assert body["summary"]["callCount"] == 1
    assert body["summary"]["inputTokens"] == 300


def test_aggregate_date_range(client: TestClient) -> None:
    body = client.get(
        "/api/usage/aggregate"
        "?groupBy=day&start=2026-05-02T00:00:00Z&end=2026-05-03T00:00:00Z"
    ).json()
    assert body["summary"]["callCount"] == 1
    assert body["items"][0]["cachedInputTokens"] == 100
    assert body["items"][0]["cacheWriteTokens"] == 50


def test_invalid_group_by_returns_422(client: TestClient) -> None:
    r = client.get("/api/usage/aggregate?groupBy=hour")
    assert r.status_code == 422


def test_503_when_recorder_not_initialized() -> None:
    set_usage_recorder(None)
    app = FastAPI()
    app.include_router(usage_router)
    r = TestClient(app).get("/api/usage/aggregate?groupBy=day")
    assert r.status_code == 503
