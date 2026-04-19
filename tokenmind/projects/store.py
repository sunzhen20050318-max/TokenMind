from __future__ import annotations

import json
import uuid
from pathlib import Path

from tokenmind.projects.models import ProjectRecord, now_iso


class ProjectStore:
    def __init__(self, workspace: Path):
        self.root = workspace / "projects"
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "projects.json"

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, items: list[dict]) -> None:
        self.path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_projects(self) -> list[ProjectRecord]:
        items = [ProjectRecord(**item) for item in self._load()]
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def create_project(self, name: str) -> ProjectRecord:
        normalized = name.strip()
        if not normalized:
            raise ValueError("Project name cannot be empty")
        items = self._load()
        if any(str(item.get("name", "")).strip().lower() == normalized.lower() for item in items):
            raise ValueError(f"Project '{normalized}' already exists")
        project = ProjectRecord(id=f"proj_{uuid.uuid4().hex[:10]}", name=normalized)
        items.append(project.model_dump())
        self._save(items)
        return project

    def get_project(self, project_id: str) -> ProjectRecord | None:
        for item in self._load():
            if item.get("id") == project_id:
                return ProjectRecord(**item)
        return None

    def rename_project(self, project_id: str, name: str) -> ProjectRecord:
        normalized = name.strip()
        if not normalized:
            raise ValueError("Project name cannot be empty")
        items = self._load()
        for item in items:
            if item.get("id") != project_id and str(item.get("name", "")).strip().lower() == normalized.lower():
                raise ValueError(f"Project '{normalized}' already exists")
        for item in items:
            if item.get("id") == project_id:
                item["name"] = normalized
                item["updated_at"] = now_iso()
                self._save(items)
                return ProjectRecord(**item)
        raise KeyError(project_id)

    def delete_project(self, project_id: str) -> ProjectRecord:
        items = self._load()
        for index, item in enumerate(items):
            if item.get("id") == project_id:
                removed = ProjectRecord(**item)
                del items[index]
                self._save(items)
                return removed
        raise KeyError(project_id)
