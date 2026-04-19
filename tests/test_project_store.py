from __future__ import annotations

from pathlib import Path

from tokenmind.projects.store import ProjectStore


def test_create_project_persists_workspace_metadata(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)

    project = store.create_project("Product Refresh")

    assert project.name == "Product Refresh"
    assert (tmp_path / "projects" / "projects.json").exists()


def test_duplicate_project_name_is_rejected(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    store.create_project("Release Plan")

    try:
        store.create_project("Release Plan")
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("Expected duplicate project name to fail")


def test_list_projects_returns_most_recent_first(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    first = store.create_project("A")
    second = store.create_project("B")

    items = store.list_projects()

    assert items[0].id == second.id
    assert items[1].id == first.id


def test_delete_project_removes_record(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create_project("Cleanup")

    deleted = store.delete_project(project.id)

    assert deleted.id == project.id
    assert store.get_project(project.id) is None
    assert store.list_projects() == []
