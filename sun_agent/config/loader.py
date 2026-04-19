"""Configuration loading utilities."""

import json
import shutil
from pathlib import Path

import pydantic
from loguru import logger

from sun_agent.config.schema import Config

# Global variable to store current config path (for multi-instance support)
_current_config_path: Path | None = None
APP_DIR_NAME = ".tokenmind"
LEGACY_APP_DIR_NAME = ".sun_agent"


def get_app_dir() -> Path:
    """Return the default TokenMind app directory."""
    return Path.home() / APP_DIR_NAME


def get_legacy_app_dir() -> Path:
    """Return the legacy sun_agent app directory."""
    return Path.home() / LEGACY_APP_DIR_NAME


def _migrate_legacy_config(new_path: Path, legacy_path: Path) -> Path:
    """Copy the legacy config into the new location if needed."""
    if new_path.exists() or not legacy_path.exists():
        return new_path if new_path.exists() else legacy_path
    try:
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy_path, new_path)
        logger.info("Migrated legacy config from {} to {}", legacy_path, new_path)
        return new_path
    except Exception:
        logger.exception("Failed to migrate legacy config from {} to {}", legacy_path, new_path)
        return legacy_path


def set_config_path(path: Path) -> None:
    """Set the current config path (used to derive data directory)."""
    global _current_config_path
    _current_config_path = path


def get_config_path() -> Path:
    """Get the configuration file path."""
    if _current_config_path:
        return _current_config_path
    new_path = get_app_dir() / "config.json"
    legacy_path = get_legacy_app_dir() / "config.json"
    if new_path.exists():
        return new_path
    if legacy_path.exists():
        return _migrate_legacy_config(new_path, legacy_path)
    return new_path


def load_config(config_path: Path | None = None) -> Config:
    """
    Load configuration from file or create default.

    Args:
        config_path: Optional path to config file. Uses default if not provided.

    Returns:
        Loaded configuration object.
    """
    path = config_path or get_config_path()

    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data = _migrate_config(data)
            return Config.model_validate(data)
        except (json.JSONDecodeError, ValueError, pydantic.ValidationError) as e:
            logger.warning(f"Failed to load config from {path}: {e}")
            logger.warning("Using default configuration.")

    return Config()


def save_config(config: Config, config_path: Path | None = None) -> None:
    """
    Save configuration to file.

    Args:
        config: Configuration to save.
        config_path: Optional path to save to. Uses default if not provided.
    """
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(mode="json", by_alias=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _migrate_config(data: dict) -> dict:
    """Migrate old config formats to current."""
    # Move tools.exec.restrictToWorkspace → tools.restrictToWorkspace
    tools = data.get("tools", {})
    exec_cfg = tools.get("exec", {})
    if "restrictToWorkspace" in exec_cfg and "restrictToWorkspace" not in tools:
        tools["restrictToWorkspace"] = exec_cfg.pop("restrictToWorkspace")
    return data
