"""Runtime path helpers derived from the active config context."""

from __future__ import annotations

import shutil
from pathlib import Path

from loguru import logger

from tokenmind.config.loader import get_app_dir, get_config_path, get_legacy_app_dir
from tokenmind.utils.helpers import ensure_dir


def get_data_dir() -> Path:
    """Return the instance-level runtime data directory."""
    return ensure_dir(get_config_path().parent)


def get_runtime_subdir(name: str) -> Path:
    """Return a named runtime subdirectory under the instance data dir."""
    return ensure_dir(get_data_dir() / name)


def get_media_dir(channel: str | None = None) -> Path:
    """Return the media directory, optionally namespaced per channel."""
    base = get_runtime_subdir("media")
    return ensure_dir(base / channel) if channel else base


def get_cron_dir() -> Path:
    """Return the cron storage directory."""
    return get_runtime_subdir("cron")


def get_logs_dir() -> Path:
    """Return the logs directory."""
    return get_runtime_subdir("logs")


def get_workspace_path(workspace: str | None = None) -> Path:
    """Resolve and ensure the agent workspace path."""
    path = Path(workspace).expanduser() if workspace else get_data_dir() / "workspace"
    default_tokenmind_workspace = get_app_dir() / "workspace"
    legacy_workspace = get_legacy_app_dir() / "workspace"
    if path == default_tokenmind_workspace and not path.exists() and legacy_workspace.exists():
        try:
            shutil.copytree(legacy_workspace, path)
            logger.info("Migrated legacy workspace from {} to {}", legacy_workspace, path)
        except Exception:
            logger.exception("Failed to migrate legacy workspace from {} to {}", legacy_workspace, path)
    return ensure_dir(path)


def get_cli_history_path() -> Path:
    """Return the shared CLI history file path."""
    return ensure_dir(get_data_dir() / "history") / "cli_history"


def get_bridge_install_dir() -> Path:
    """Return the shared WhatsApp bridge installation directory."""
    return get_data_dir() / "bridge"


def get_legacy_sessions_dir() -> Path:
    """Return the legacy global session directory used for migration fallback."""
    return get_legacy_app_dir() / "sessions"
