"""Tests for project-scoped memory isolation.

A session that belongs to a project must read/write its consolidated
memory from ``workspace/projects/<project_id>/memory/``, independent of
the global ``workspace/memory/`` used by sessions without a project. The
isolation goes both ways:

- A project's memory is not visible to other projects or to global
  sessions.
- The global memory is not visible to project sessions.

This file covers ``MemoryStore`` (paths), ``ContextBuilder.memory_for``
(routing), and ``MemoryConsolidator._store_for_session`` (writes).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tokenmind.agent.context import ContextBuilder
from tokenmind.agent.memory import MemoryConsolidator, MemoryStore
from tokenmind.providers.base import LLMProvider
from tokenmind.session.manager import Session

# ─── MemoryStore path resolution ─────────────────────────────────────────


def test_memory_store_global_path(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    assert store.memory_dir == tmp_path / "memory"
    assert store.project_id is None


def test_memory_store_project_path(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path, project_id="proj-A")
    assert store.memory_dir == tmp_path / "projects" / "proj-A" / "memory"
    assert store.project_id == "proj-A"


def test_two_project_stores_have_distinct_paths(tmp_path: Path) -> None:
    a = MemoryStore(tmp_path, project_id="A")
    b = MemoryStore(tmp_path, project_id="B")
    assert a.memory_dir != b.memory_dir
    assert a.memory_dir.parent.name == "A"
    assert b.memory_dir.parent.name == "B"


def test_global_and_project_stores_are_independent(tmp_path: Path) -> None:
    global_store = MemoryStore(tmp_path)
    project_store = MemoryStore(tmp_path, project_id="X")
    assert global_store.memory_file != project_store.memory_file
    # Writing one doesn't affect the other.
    global_store.memory_file.write_text("global fact\n", encoding="utf-8")
    project_store.memory_file.write_text("project fact\n", encoding="utf-8")
    assert global_store.memory_file.read_text(encoding="utf-8") == "global fact\n"
    assert project_store.memory_file.read_text(encoding="utf-8") == "project fact\n"


# ─── ContextBuilder.memory_for ────────────────────────────────────────────


def test_context_builder_memory_for_returns_global_when_no_project(tmp_path: Path) -> None:
    builder = ContextBuilder(tmp_path)
    assert builder.memory_for(None) is builder.memory
    assert builder.memory_for("") is builder.memory


def test_context_builder_memory_for_returns_project_store(tmp_path: Path) -> None:
    builder = ContextBuilder(tmp_path)
    store = builder.memory_for("proj-A")
    assert store is not builder.memory
    assert store.project_id == "proj-A"


def test_context_builder_memory_for_caches_per_project(tmp_path: Path) -> None:
    """Two lookups for the same project_id should return the same instance —
    avoids re-creating the store on every turn."""
    builder = ContextBuilder(tmp_path)
    s1 = builder.memory_for("proj-A")
    s2 = builder.memory_for("proj-A")
    assert s1 is s2


def test_context_builder_loads_project_memory_in_system_prompt(tmp_path: Path) -> None:
    """The system prompt for a project session must surface the
    project's MEMORY.md, not the global one."""
    # Seed both global and project memory with distinguishable content.
    (tmp_path / "memory").mkdir(parents=True, exist_ok=True)
    (tmp_path / "memory" / "MEMORY.md").write_text(
        "GLOBAL_MEMORY_MARKER\n", encoding="utf-8",
    )
    (tmp_path / "projects" / "proj-A" / "memory").mkdir(parents=True, exist_ok=True)
    (tmp_path / "projects" / "proj-A" / "memory" / "MEMORY.md").write_text(
        "PROJECT_A_MEMORY_MARKER\n", encoding="utf-8",
    )

    builder = ContextBuilder(tmp_path)

    global_prompt = builder.build_system_prompt(project_id=None)
    project_prompt = builder.build_system_prompt(project_id="proj-A")

    assert "GLOBAL_MEMORY_MARKER" in global_prompt
    assert "PROJECT_A_MEMORY_MARKER" not in global_prompt

    assert "PROJECT_A_MEMORY_MARKER" in project_prompt
    assert "GLOBAL_MEMORY_MARKER" not in project_prompt


# ─── MemoryConsolidator routing ──────────────────────────────────────────


def _make_consolidator(tmp_path: Path) -> MemoryConsolidator:
    sessions = MagicMock()
    return MemoryConsolidator(
        workspace=tmp_path,
        provider=MagicMock(spec=LLMProvider),
        model="test-model",
        sessions=sessions,
        context_window_tokens=8192,
        build_messages=lambda **kw: [],
        get_tool_definitions=lambda: [],
    )


def _make_session(key: str, project_id: str | None = None) -> Session:
    session = Session(key=key)
    if project_id:
        session.metadata["project_id"] = project_id
    return session


def test_consolidator_store_for_session_without_project_is_global(tmp_path: Path) -> None:
    consolidator = _make_consolidator(tmp_path)
    session = _make_session("cli:s1")
    assert consolidator._store_for_session(session) is consolidator.store


def test_consolidator_store_for_session_with_project_is_isolated(tmp_path: Path) -> None:
    consolidator = _make_consolidator(tmp_path)
    session = _make_session("web:s2", project_id="proj-X")
    store = consolidator._store_for_session(session)
    assert store is not consolidator.store
    assert store.project_id == "proj-X"
    assert store.memory_dir == tmp_path / "projects" / "proj-X" / "memory"


def test_consolidator_caches_project_store(tmp_path: Path) -> None:
    consolidator = _make_consolidator(tmp_path)
    s1 = _make_session("a", project_id="proj-X")
    s2 = _make_session("b", project_id="proj-X")
    assert consolidator._store_for_session(s1) is consolidator._store_for_session(s2)


@pytest.mark.asyncio
async def test_consolidator_writes_to_project_memory_when_session_has_project_id(
    tmp_path: Path,
) -> None:
    """End-to-end: archive_messages on a project session must persist
    into the project's HISTORY.md, not the global one."""
    consolidator = _make_consolidator(tmp_path)
    session = _make_session("web:s3", project_id="proj-Y")

    messages = [
        {"role": "user", "content": "hello in project Y"},
        {"role": "assistant", "content": "hi from agent"},
    ]
    # archive_messages eventually retries 3x via consolidate_messages →
    # store.consolidate. We drive the raw-archive fallback (no LLM mock
    # needed). The store's
    # consolidate() returns False on LLM failure → archive_messages
    # eventually flips to raw archival, which writes to HISTORY.md.
    from tokenmind.providers.base import LLMResponse

    async def fake_chat(*args, **kwargs):
        return LLMResponse(content="", finish_reason="error")
    consolidator.provider.chat_with_retry = fake_chat  # type: ignore[attr-defined]

    await consolidator.archive_messages(messages, session=session)

    project_history = tmp_path / "projects" / "proj-Y" / "memory" / "HISTORY.md"
    global_history = tmp_path / "memory" / "HISTORY.md"
    # Project history exists; global does not.
    assert project_history.exists()
    content = project_history.read_text(encoding="utf-8")
    assert "hello in project Y" in content
    assert not global_history.exists() or "hello in project Y" not in global_history.read_text(encoding="utf-8")
