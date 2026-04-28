"""Pydantic models for browser tasks, steps, and artifacts."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_USER = "awaiting_user"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepPhase(str, Enum):
    THINKING = "thinking"
    ACTION = "action"
    OBSERVATION = "observation"
    INTERVENTION = "intervention"


class ArtifactKind(str, Enum):
    SCREENSHOT = "screenshot"
    PAGE_TEXT = "page_text"
    DOWNLOAD = "download"
    PDF = "pdf"
    EXTRACT_JSON = "extract_json"
    LOG = "log"


class BrowserTask(BaseModel):
    """A user-instructed browser automation task."""

    id: str
    project_id: str
    session_id: Optional[str] = None
    instruction: str
    start_url: Optional[str] = None
    status: TaskStatus
    result_summary: Optional[str] = None
    error_detail: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    step_count: int = 0
    max_steps: int = 50
    timeout_seconds: int = 1800
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrowserStep(BaseModel):
    id: str
    task_id: str
    step_index: int
    phase: StepPhase
    action_name: Optional[str] = None
    action_args: Optional[dict[str, Any]] = None
    thinking: Optional[str] = None
    observation: Optional[str] = None
    screenshot_artifact_id: Optional[str] = None
    success: bool
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    timestamp: datetime


class BrowserArtifact(BaseModel):
    id: str
    task_id: str
    step_index: Optional[int] = None
    kind: ArtifactKind
    file_path: str
    source_url: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: int = 0
    created_at: datetime
    knowledge_doc_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateTaskRequest(BaseModel):
    """Payload for POST /api/browser-tasks."""

    project_id: str
    instruction: str
    start_url: Optional[str] = None
    session_id: Optional[str] = None
    max_steps: int = 50
    timeout_seconds: int = 1800
    # Optional override for the LLM model used to drive the ReAct loop.
    # When None, falls back to ``config.agents.defaults.model``.
    model_override: Optional[str] = None


class TaskListItem(BaseModel):
    """Compact task entry returned by GET /api/browser-tasks."""

    id: str
    project_id: str
    session_id: Optional[str] = None
    instruction: str
    status: TaskStatus
    created_at: datetime
    finished_at: Optional[datetime] = None
    step_count: int
    artifact_count: int


class TaskDetailResponse(BaseModel):
    """Full task payload returned by GET /api/browser-tasks/{id}."""

    task: BrowserTask
    steps: list[BrowserStep]
    artifacts: list[BrowserArtifact]


class EnvCheckResponse(BaseModel):
    """Result of GET /api/browser-agent/env-check."""

    cli_installed: bool
    chrome_installed: bool
    is_ready: bool
    version: Optional[str] = None
    issues: list[str] = Field(default_factory=list)
