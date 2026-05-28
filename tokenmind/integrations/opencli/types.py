"""Data types for the OpenCLI integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class InstallStep:
    """One actionable step a user can take to fix a missing dependency."""

    key: str
    title: str
    detail: str
    command: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class ProfileInfo:
    context_id: str
    alias: str | None = None
    is_default: bool = False


@dataclass(frozen=True)
class SiteCommand:
    name: str
    description: str | None = None


@dataclass(frozen=True)
class SiteInfo:
    site: str
    commands: list[SiteCommand]
    featured: bool = False


@dataclass(frozen=True)
class OpencliInstallation:
    opencli_installed: bool
    opencli_version: str | None
    opencli_path: str | None
    node_installed: bool
    node_version: str | None
    node_ok: bool
    daemon_port: int
    daemon_running: bool
    profiles: list[ProfileInfo] = field(default_factory=list)
    missing_steps: list[InstallStep] = field(default_factory=list)
    ready: bool = False
    last_error: str | None = None


@dataclass(frozen=True)
class RunResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    command: list[str]


RiskLevel = Literal["low", "medium", "high"]
