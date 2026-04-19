from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class KnowledgeBaseRecord(BaseModel):
    id: str
    name: str
    description: str = ""
    status: str = "ready"
    enabled: bool = True
    document_count: int = 0
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class KnowledgeDocumentRecord(BaseModel):
    id: str
    knowledge_base_id: str
    name: str
    path: str
    file_type: str
    size: int
    status: str = "ready"
    processing_stage: str = "ready"
    processing_progress: int = 100
    error_message: str | None = None
    chunk_count: int = 0
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class KnowledgeChunkRecord(BaseModel):
    id: str
    document_id: str
    knowledge_base_id: str
    ordinal: int
    content: str
    token_count: int = 0
    embedding: list[float] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)


class SessionKnowledgeLinks(BaseModel):
    session_id: str
    knowledge_base_ids: list[str] = Field(default_factory=list)
