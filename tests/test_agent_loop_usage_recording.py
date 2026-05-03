"""Verify AgentLoop._record_usage persists records to the SQLite store."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from tokenmind.usage import UsageRecorder


class _StubProvider:
    provider_name = "stub-provider"


class _StubSessions:
    def __init__(self, project_id: str | None = None) -> None:
        self._project_id = project_id

    def get_or_create(self, session_key: str) -> SimpleNamespace:
        return SimpleNamespace(key=session_key, project_id=self._project_id)


class _LoopShim:
    """Minimal AgentLoop shim that hosts only the bits _record_usage needs."""

    def __init__(self, recorder: UsageRecorder, project_id: str | None = None) -> None:
        self.usage_recorder = recorder
        self.provider = _StubProvider()
        self.model = "claude-opus-4-5"
        self.sessions = _StubSessions(project_id=project_id)

    # Bind the real method so we exercise the production code path
    from tokenmind.agent.loop import AgentLoop

    _record_usage = AgentLoop._record_usage  # type: ignore[assignment]


@pytest.fixture
def recorder(tmp_path: Path) -> UsageRecorder:
    return UsageRecorder(tmp_path / "usage.sqlite3")


def test_record_usage_persists_full_breakdown(recorder: UsageRecorder) -> None:
    loop = _LoopShim(recorder, project_id="proj_a")
    response = SimpleNamespace(
        usage={
            "input_tokens": 500,
            "cached_input_tokens": 200,
            "cache_write_tokens": 100,
            "output_tokens": 80,
            "reasoning_tokens": 30,
        }
    )
    loop._record_usage(response, session_key="web:abc")

    rows = recorder.aggregate(group_by="session")
    assert len(rows) == 1
    assert rows[0].bucket == "web:abc"
    assert rows[0].input_tokens == 500
    assert rows[0].cached_input_tokens == 200
    assert rows[0].cache_write_tokens == 100
    assert rows[0].output_tokens == 80
    assert rows[0].reasoning_tokens == 30


def test_record_usage_skips_when_response_has_no_usage(recorder: UsageRecorder) -> None:
    loop = _LoopShim(recorder)
    loop._record_usage(SimpleNamespace(usage={}), session_key="web:abc")
    loop._record_usage(SimpleNamespace(usage=None), session_key="web:abc")
    loop._record_usage(SimpleNamespace(), session_key="web:abc")
    assert recorder.aggregate(group_by="session") == []


def test_record_usage_uses_provider_name_for_provider_dimension(recorder: UsageRecorder) -> None:
    loop = _LoopShim(recorder)
    loop._record_usage(
        SimpleNamespace(usage={"input_tokens": 100, "output_tokens": 50}),
        session_key="s1",
    )
    rows = recorder.aggregate(group_by="provider")
    assert rows[0].bucket == "stub-provider"


def test_record_usage_falls_back_to_unknown_session_id(recorder: UsageRecorder) -> None:
    loop = _LoopShim(recorder)
    loop._record_usage(
        SimpleNamespace(usage={"input_tokens": 100, "output_tokens": 50}),
        session_key=None,
    )
    rows = recorder.aggregate(group_by="session")
    assert rows[0].bucket == "unknown"


def test_record_usage_swallows_recorder_errors(recorder: UsageRecorder, monkeypatch: pytest.MonkeyPatch) -> None:
    """Recording must never crash a chat response."""
    loop = _LoopShim(recorder)

    def boom(_record):  # noqa: ANN001
        raise RuntimeError("disk full")

    monkeypatch.setattr(loop.usage_recorder, "record", boom)
    # Should not raise
    loop._record_usage(
        SimpleNamespace(usage={"input_tokens": 10, "output_tokens": 5}),
        session_key="s1",
    )
