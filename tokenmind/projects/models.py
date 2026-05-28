from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now().isoformat()


class ProjectRecord(BaseModel):
    id: str
    name: str
    # Id of the project's owned wiki knowledge base. Lazily created on the
    # first document upload; until then the project has no KB and its
    # sessions simply have no active wiki.
    knowledge_base_id: str | None = None
    # Free-text custom instructions injected into the system prompt of every
    # session that belongs to this project.
    instructions: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
