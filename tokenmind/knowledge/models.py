from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class KnowledgeBaseRecord(BaseModel):
    id: str
    name: str
    description: str = ""
    type: Literal["rag", "wiki"] = "rag"
    status: str = "ready"
    enabled: bool = True
    # RAG 字段
    document_count: int = 0
    # Wiki 字段（rag 类型保持默认值）
    language: str = "zh"
    root_path: str = ""
    source_count: int = 0
    page_count: int = 0
    entity_count: int = 0
    topic_count: int = 0
    link_count: int = 0
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
