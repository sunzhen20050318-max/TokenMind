"""SQLite roundtrip tests for the browser-agent storage layer."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from tokenmind.browser_agent.models import (
    ArtifactKind,
    BrowserArtifact,
    BrowserStep,
    BrowserTask,
    StepPhase,
    TaskStatus,
)
from tokenmind.browser_agent.storage import BrowserTaskStorage


@pytest.fixture
def storage(tmp_path: Path) -> BrowserTaskStorage:
    return BrowserTaskStorage(tmp_path)


def _make_task(task_id: str = "bt_test_1", status: TaskStatus = TaskStatus.PENDING) -> BrowserTask:
    return BrowserTask(
        id=task_id,
        project_id="proj_a",
        session_id="web:demo",
        instruction="open example.com",
        start_url="https://example.com",
        status=status,
        created_at=datetime.now(),
        max_steps=20,
        timeout_seconds=600,
        metadata={"source": "ui"},
    )


def test_insert_and_get_task_roundtrip(storage: BrowserTaskStorage) -> None:
    task = _make_task()
    storage.insert_task(task)
    fetched = storage.get_task(task.id)
    assert fetched is not None
    assert fetched.id == task.id
    assert fetched.status is TaskStatus.PENDING
    assert fetched.metadata == {"source": "ui"}
    assert fetched.start_url == "https://example.com"


def test_update_task_partial(storage: BrowserTaskStorage) -> None:
    task = _make_task()
    storage.insert_task(task)
    storage.update_task(
        task.id,
        status=TaskStatus.RUNNING,
        started_at=datetime.now(),
        step_count=3,
    )
    updated = storage.get_task(task.id)
    assert updated is not None
    assert updated.status is TaskStatus.RUNNING
    assert updated.step_count == 3
    assert updated.started_at is not None


def test_list_tasks_filters_by_project(storage: BrowserTaskStorage) -> None:
    storage.insert_task(_make_task("bt_a", TaskStatus.PENDING))
    other = _make_task("bt_b", TaskStatus.COMPLETED)
    other = other.model_copy(update={"project_id": "proj_b"})
    storage.insert_task(other)

    items_a = storage.list_tasks(project_id="proj_a")
    items_b = storage.list_tasks(project_id="proj_b")
    assert {item.id for item in items_a} == {"bt_a"}
    assert {item.id for item in items_b} == {"bt_b"}


def test_steps_and_artifacts_roundtrip(storage: BrowserTaskStorage) -> None:
    task = _make_task()
    storage.insert_task(task)

    step = BrowserStep(
        id="st_1",
        task_id=task.id,
        step_index=1,
        phase=StepPhase.OBSERVATION,
        action_name="snapshot",
        action_args={"interactive": True},
        observation="page text...",
        success=True,
        timestamp=datetime.now(),
    )
    storage.insert_step(step)

    artifact = BrowserArtifact(
        id="art_1",
        task_id=task.id,
        step_index=1,
        kind=ArtifactKind.SCREENSHOT,
        file_path="/tmp/foo.png",
        mime_type="image/png",
        size_bytes=4096,
        created_at=datetime.now(),
        metadata={"shot_id": "shot-1"},
    )
    storage.insert_artifact(artifact)

    steps = storage.list_steps(task.id)
    assert len(steps) == 1
    assert steps[0].action_args == {"interactive": True}

    artifacts = storage.list_artifacts(task.id)
    assert len(artifacts) == 1
    assert artifacts[0].kind is ArtifactKind.SCREENSHOT

    fetched_artifact = storage.get_artifact("art_1")
    assert fetched_artifact is not None
    assert fetched_artifact.metadata == {"shot_id": "shot-1"}


def test_artifact_count_exposed_in_list(storage: BrowserTaskStorage) -> None:
    task = _make_task()
    storage.insert_task(task)
    storage.insert_artifact(
        BrowserArtifact(
            id="art_1",
            task_id=task.id,
            kind=ArtifactKind.SCREENSHOT,
            file_path="/tmp/a.png",
            size_bytes=10,
            created_at=datetime.now(),
        )
    )
    storage.insert_artifact(
        BrowserArtifact(
            id="art_2",
            task_id=task.id,
            kind=ArtifactKind.PAGE_TEXT,
            file_path="/tmp/b.txt",
            size_bytes=20,
            created_at=datetime.now(),
        )
    )

    items = storage.list_tasks(project_id="proj_a")
    assert len(items) == 1
    assert items[0].artifact_count == 2


def test_delete_task_cascades(storage: BrowserTaskStorage) -> None:
    task = _make_task()
    storage.insert_task(task)
    storage.insert_step(
        BrowserStep(
            id="st_1",
            task_id=task.id,
            step_index=1,
            phase=StepPhase.ACTION,
            action_name="open",
            success=True,
            timestamp=datetime.now(),
        )
    )
    storage.insert_artifact(
        BrowserArtifact(
            id="art_1",
            task_id=task.id,
            kind=ArtifactKind.SCREENSHOT,
            file_path="/tmp/x.png",
            size_bytes=10,
            created_at=datetime.now(),
        )
    )

    storage.delete_task(task.id)
    assert storage.get_task(task.id) is None
    assert storage.list_steps(task.id) == []
    assert storage.list_artifacts(task.id) == []
