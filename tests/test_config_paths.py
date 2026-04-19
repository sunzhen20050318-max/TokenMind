from pathlib import Path

from tokenmind.config.paths import (
    get_bridge_install_dir,
    get_cli_history_path,
    get_cron_dir,
    get_data_dir,
    get_legacy_sessions_dir,
    get_logs_dir,
    get_media_dir,
    get_runtime_subdir,
    get_workspace_path,
)


def test_runtime_dirs_follow_config_path(monkeypatch, tmp_path: Path) -> None:
    config_file = tmp_path / "instance-a" / "config.json"
    monkeypatch.setattr("tokenmind.config.paths.get_config_path", lambda: config_file)

    assert get_data_dir() == config_file.parent
    assert get_runtime_subdir("cron") == config_file.parent / "cron"
    assert get_cron_dir() == config_file.parent / "cron"
    assert get_logs_dir() == config_file.parent / "logs"


def test_media_dir_supports_channel_namespace(monkeypatch, tmp_path: Path) -> None:
    config_file = tmp_path / "instance-b" / "config.json"
    monkeypatch.setattr("tokenmind.config.paths.get_config_path", lambda: config_file)

    assert get_media_dir() == config_file.parent / "media"
    assert get_media_dir("telegram") == config_file.parent / "media" / "telegram"


def test_shared_and_legacy_paths_remain_global() -> None:
    assert get_cli_history_path() == Path.home() / ".tokenmind" / "history" / "cli_history"
    assert get_bridge_install_dir() == Path.home() / ".tokenmind" / "bridge"
    assert get_legacy_sessions_dir() == Path.home() / ".tokenmind" / "sessions"


def test_workspace_path_is_explicitly_resolved() -> None:
    assert get_workspace_path() == Path.home() / ".tokenmind" / "workspace"
    assert get_workspace_path("~/custom-workspace") == Path.home() / "custom-workspace"


def test_default_workspace_migrates_from_legacy_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    legacy_workspace = tmp_path / ".tokenmind" / "workspace"
    legacy_workspace.mkdir(parents=True, exist_ok=True)
    (legacy_workspace / "sessions").mkdir(parents=True, exist_ok=True)
    (legacy_workspace / "sessions" / "demo.jsonl").write_text("{}", encoding="utf-8")

    workspace = get_workspace_path()

    assert workspace == tmp_path / ".tokenmind" / "workspace"
    assert (workspace / "sessions" / "demo.jsonl").exists()
