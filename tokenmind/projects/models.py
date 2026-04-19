from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now().isoformat()


class ProjectRecord(BaseModel):
    id: str
    name: str
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
