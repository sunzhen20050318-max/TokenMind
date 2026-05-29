from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path

from tokenmind.projects.models import ProjectRecord, now_iso

# Process-wide lock guarding all projects.json read-modify-write cycles. Module
# level (not per-instance) on purpose: ChatService and AgentLoop each hold a
# separate ProjectStore over the same file, so a per-instance lock wouldn't
# serialize them. Coarse but correct for a low-traffic local app.
_STORE_LOCK = threading.RLock()


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
        # Atomic write: serialize to a temp file in the same directory, then
        # os.replace (atomic on POSIX/Windows) so a crash or concurrent reader
        # never sees a half-written / truncated projects.json.
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    def list_projects(self) -> list[ProjectRecord]:
        items = [ProjectRecord(**item) for item in self._load()]
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def create_project(self, name: str) -> ProjectRecord:
        normalized = name.strip()
        if not normalized:
            raise ValueError("Project name cannot be empty")
        with _STORE_LOCK:
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
        with _STORE_LOCK:
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

    def update_project(
        self,
        project_id: str,
        *,
        knowledge_base_id: str | None = None,
        instructions: str | None = None,
    ) -> ProjectRecord:
        """Patch mutable project fields. Only arguments that are not ``None``
        are applied, so callers can update instructions and KB id
        independently. Always bumps ``updated_at``."""
        with _STORE_LOCK:
            items = self._load()
            for item in items:
                if item.get("id") == project_id:
                    if knowledge_base_id is not None:
                        item["knowledge_base_id"] = knowledge_base_id
                    if instructions is not None:
                        item["instructions"] = instructions
                    item["updated_at"] = now_iso()
                    self._save(items)
                    return ProjectRecord(**item)
            raise KeyError(project_id)

    def delete_project(self, project_id: str) -> ProjectRecord:
        with _STORE_LOCK:
            items = self._load()
            for index, item in enumerate(items):
                if item.get("id") == project_id:
                    removed = ProjectRecord(**item)
                    del items[index]
                    self._save(items)
                    return removed
            raise KeyError(project_id)
