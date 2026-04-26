"""Configuration loading utilities."""

import json
import shutil
from pathlib import Path

import pydantic
from loguru import logger

from tokenmind.config.schema import AgentDefaults, Config, ProvidersConfig

# Global variable to store current config path (for multi-instance support)
_current_config_path: Path | None = None
APP_DIR_NAME = ".tokenmind"
LEGACY_APP_DIR_NAME = ".tokenmind"


def get_app_dir() -> Path:
    """Return the default TokenMind app directory."""
    return Path.home() / APP_DIR_NAME


def get_legacy_app_dir() -> Path:
    """Return the legacy tokenmind app directory."""
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
            with open(path, encoding="utf-8-sig") as f:
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
    migrated = json.loads(json.dumps(data))
    # Move tools.exec.restrictToWorkspace → tools.restrictToWorkspace
    tools = migrated.get("tools", {})
    exec_cfg = tools.get("exec", {})
    if "restrictToWorkspace" in exec_cfg and "restrictToWorkspace" not in tools:
        tools["restrictToWorkspace"] = exec_cfg.pop("restrictToWorkspace")
    defaults = migrated.get("agents", {}).get("defaults", {})
    workspace = defaults.get("workspace")
    legacy_workspace = Path.home() / ".tokenmind" / "workspace"
    if workspace in {"~/.tokenmind/workspace", str(legacy_workspace)}:
        defaults["workspace"] = "~/.tokenmind/workspace"
    _adopt_first_configured_provider_for_initial_defaults(migrated)
    _repair_removed_default_provider(migrated)
    return migrated


def _pick(data: dict, *keys: str) -> object:
    for key in keys:
        if key in data:
            return data[key]
    return None


def _provider_has_connection(provider_data: dict) -> bool:
    api_key = _pick(provider_data, "apiKey", "api_key")
    api_base = _pick(provider_data, "apiBase", "api_base")
    return bool(str(api_key or "").strip() or str(api_base or "").strip())


def _adopt_first_configured_provider_for_initial_defaults(data: dict) -> None:
    """Replace the initial auto/Claude default once a real provider is configured."""
    initial = AgentDefaults()
    defaults = data.setdefault("agents", {}).setdefault("defaults", {})
    current_provider = defaults.get("provider", initial.provider)
    current_model = defaults.get("model", initial.model)
    if current_provider != initial.provider or current_model != initial.model:
        return

    providers = data.get("providers", {})
    if not isinstance(providers, dict):
        return

    for provider_name in ProvidersConfig.model_fields:
        provider_data = providers.get(provider_name)
        if not isinstance(provider_data, dict) or not _provider_has_connection(provider_data):
            continue
        default_model = _pick(provider_data, "defaultModel", "default_model")
        if not str(default_model or "").strip():
            continue
        defaults["provider"] = provider_name
        defaults["model"] = str(default_model).strip()
        return


def _repair_removed_default_provider(data: dict) -> None:
    """Move stale default providers to the first configured supported provider."""
    defaults = data.setdefault("agents", {}).setdefault("defaults", {})
    current_provider = defaults.get("provider", AgentDefaults().provider)
    if current_provider == "auto" or current_provider in ProvidersConfig.model_fields:
        return

    providers = data.get("providers", {})
    if not isinstance(providers, dict):
        defaults["provider"] = "auto"
        return

    for provider_name in ProvidersConfig.model_fields:
        provider_data = providers.get(provider_name)
        if not isinstance(provider_data, dict) or not _provider_has_connection(provider_data):
            continue
        defaults["provider"] = provider_name
        default_model = _pick(provider_data, "defaultModel", "default_model")
        if str(default_model or "").strip():
            defaults["model"] = str(default_model).strip()
        return

    defaults["provider"] = "auto"
