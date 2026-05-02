"""Pending skill suggestions created by the agent and approved by the user."""

from __future__ import annotations

import difflib
import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field


class SkillSuggestion(BaseModel):
    """A reusable skill draft waiting for user confirmation."""

    id: str
    kind: str = "create"
    name: str
    description: str
    body: str
    markdown: str | None = None
    target_skill: str | None = None
    previous_markdown: str | None = None
    triggers: list[str] = Field(default_factory=list)
    source_session_id: str | None = None
    source_message: str | None = None
    created_at: str
    path: str | None = None


class SkillSuggestionStore:
    """Persist pending skill drafts under ``workspace/skills/.suggestions``."""

    def __init__(self, workspace: Path | str):
        self.workspace = Path(workspace).expanduser()
        self.skills_root = self.workspace / "skills"
        self.pending_root = self.skills_root / ".suggestions"

    def create(
        self,
        name: str,
        description: str,
        body: str,
        triggers: list[str] | None = None,
        source_session_id: str | None = None,
        source_message: str | None = None,
    ) -> SkillSuggestion:
        """Create and persist a pending skill suggestion."""

        self.pending_root.mkdir(parents=True, exist_ok=True)
        safe_name = self._sanitize_name(name)
        suggestion = SkillSuggestion(
            id=self._new_id(),
            kind="create",
            name=safe_name,
            description=description.strip() or safe_name,
            body=body.strip(),
            triggers=[item.strip() for item in (triggers or []) if item and item.strip()],
            source_session_id=source_session_id,
            source_message=source_message,
            created_at=datetime.now(UTC).isoformat(),
            path=str(self._skill_file_for(safe_name)),
        )
        self._suggestion_file(suggestion.id).write_text(
            suggestion.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return suggestion

    def create_update(
        self,
        target_skill: str,
        description: str,
        markdown: str,
        previous_markdown: str,
        triggers: list[str] | None = None,
        source_session_id: str | None = None,
        source_message: str | None = None,
    ) -> SkillSuggestion:
        """Create and persist a pending update for an existing skill."""

        self.pending_root.mkdir(parents=True, exist_ok=True)
        safe_name = self._sanitize_name(target_skill)
        normalized_markdown = self._normalize_skill_markdown(
            name=safe_name,
            description=description.strip() or safe_name,
            markdown=markdown,
            triggers=triggers or [],
            source_session_id=source_session_id,
        )
        suggestion = SkillSuggestion(
            id=self._new_id(),
            kind="update",
            name=safe_name,
            description=description.strip() or safe_name,
            body=self._extract_body_from_markdown(normalized_markdown),
            markdown=normalized_markdown,
            target_skill=safe_name,
            previous_markdown=previous_markdown,
            triggers=[item.strip() for item in (triggers or []) if item and item.strip()],
            source_session_id=source_session_id,
            source_message=source_message,
            created_at=datetime.now(UTC).isoformat(),
            path=str(self._skill_file_for(safe_name)),
        )
        self._suggestion_file(suggestion.id).write_text(
            suggestion.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return suggestion

    def list_pending(self) -> list[SkillSuggestion]:
        """Return all pending suggestions sorted by creation time."""

        if not self.pending_root.exists():
            return []
        items: list[SkillSuggestion] = []
        for path in self.pending_root.glob("*.json"):
            suggestion = self._read(path)
            if suggestion is not None:
                items.append(suggestion)
        return sorted(items, key=lambda item: item.created_at)

    def get(self, suggestion_id: str) -> SkillSuggestion | None:
        """Load a pending suggestion by id."""

        path = self._suggestion_file(suggestion_id)
        if not path.exists():
            return None
        return self._read(path)

    def approve(self, suggestion_id: str, overwrite: bool = False) -> SkillSuggestion:
        """Write the suggestion as a workspace skill and remove the pending draft."""

        suggestion = self.get(suggestion_id)
        if suggestion is None:
            raise KeyError(suggestion_id)

        target_name = suggestion.target_skill if suggestion.kind == "update" else suggestion.name
        target = self._skill_file_for(target_name or suggestion.name)
        self._ensure_inside_skills(target)
        if suggestion.kind != "update" and target.exists() and not overwrite:
            raise FileExistsError(str(target))

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.render_preview(suggestion), encoding="utf-8")
        self._suggestion_file(suggestion_id).unlink(missing_ok=True)
        return suggestion.model_copy(update={"path": str(target)})

    def render_preview(self, suggestion: SkillSuggestion) -> str:
        """Render exactly what will be written to ``SKILL.md`` after approval."""

        if suggestion.markdown:
            return suggestion.markdown.strip() + "\n"
        return self._render_skill_md(suggestion)

    def render_diff(self, suggestion: SkillSuggestion) -> str:
        """Render a unified diff for update suggestions."""

        if suggestion.kind != "update" or not suggestion.previous_markdown:
            return ""
        before = suggestion.previous_markdown.splitlines(keepends=True)
        after = self.render_preview(suggestion).splitlines(keepends=True)
        return "".join(
            difflib.unified_diff(
                before,
                after,
                fromfile=f"{suggestion.target_skill or suggestion.name}/SKILL.md (current)",
                tofile=f"{suggestion.target_skill or suggestion.name}/SKILL.md (proposed)",
            )
        )

    def reject(self, suggestion_id: str) -> bool:
        """Delete a pending suggestion without installing it."""

        path = self._suggestion_file(suggestion_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _read(self, path: Path) -> SkillSuggestion | None:
        try:
            return SkillSuggestion.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _suggestion_file(self, suggestion_id: str) -> Path:
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "", suggestion_id)
        return self.pending_root / f"{safe_id}.json"

    def _skill_file_for(self, name: str) -> Path:
        return self.skills_root / self._sanitize_name(name) / "SKILL.md"

    def _ensure_inside_skills(self, target: Path) -> None:
        skills_root = self.skills_root.resolve()
        resolved = target.resolve()
        try:
            resolved.relative_to(skills_root)
        except ValueError as exc:
            raise ValueError("Skill path escapes workspace skills directory") from exc

    @staticmethod
    def _new_id() -> str:
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        return f"sug_{stamp}_{secrets.token_hex(4)}"

    @staticmethod
    def _sanitize_name(name: str) -> str:
        raw = str(name or "").replace("\\", "/").split("/")[-1].strip().lower()
        raw = re.sub(r"[^a-z0-9_\-\s]+", "-", raw)
        raw = re.sub(r"[\s_-]+", "-", raw).strip("-")
        return raw or f"skill-{secrets.token_hex(4)}"

    @classmethod
    def _normalize_skill_markdown(
        cls,
        name: str,
        description: str,
        markdown: str,
        triggers: list[str],
        source_session_id: str | None,
    ) -> str:
        text = (markdown or "").strip()
        if text.startswith("---"):
            return text + "\n"
        suggestion = SkillSuggestion(
            id="preview",
            kind="update",
            name=name,
            description=description,
            body=text,
            triggers=triggers,
            source_session_id=source_session_id,
            created_at=datetime.now(UTC).isoformat(),
        )
        return cls._render_skill_md(suggestion)

    @staticmethod
    def _extract_body_from_markdown(markdown: str) -> str:
        text = markdown.strip()
        if text.startswith("---"):
            match = re.match(r"^---\n.*?\n---\n?", text, re.DOTALL)
            if match:
                return text[match.end() :].strip()
        return text

    @staticmethod
    def _render_skill_md(suggestion: SkillSuggestion) -> str:
        description = suggestion.description.replace("\\", "\\\\").replace('"', '\\"')
        metadata = {
            "tokenmind": {
                "source": "suggestion",
                "triggers": suggestion.triggers,
                "source_session_id": suggestion.source_session_id,
            }
        }
        metadata_json = json.dumps(metadata, ensure_ascii=False).replace("'", "''")
        trigger_lines = "\n".join(f"- {trigger}" for trigger in suggestion.triggers) or "- 手动启用"
        return (
            "---\n"
            f"name: {suggestion.name}\n"
            f"description: \"{description}\"\n"
            f"metadata: '{metadata_json}'\n"
            "---\n\n"
            f"# {suggestion.name}\n\n"
            "## When To Use\n\n"
            f"{trigger_lines}\n\n"
            "## Procedure\n\n"
            f"{suggestion.body.strip()}\n"
        )
