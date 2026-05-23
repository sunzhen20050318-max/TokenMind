"""Tests for the DELETE /api/skills/{name} endpoint.

Only workspace-installed skills can be removed — built-in skills that
ship inside the package are read-only. Trying to delete a path outside
workspace/skills/ is also refused (defence in depth against a malformed
loader result).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from tokenmind.bus.queue import MessageBus
from tokenmind.server.app import create_app
from tokenmind.server.channel.web import WebChannel, WebChannelConfig
from tokenmind.server.websocket.manager import ConnectionManager


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Point the config loader at a tmp workspace so skill writes don't
    touch the developer's ~/.tokenmind."""
    from tokenmind.config.loader import set_config_path

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps({
            "agents": {"defaults": {"workspace": str(tmp_path)}},
            "skills": {"disabled": []},
        }),
        encoding="utf-8",
    )
    set_config_path(cfg_path)
    (tmp_path / "skills").mkdir(parents=True, exist_ok=True)
    yield tmp_path
    set_config_path(None)  # restore default for other tests


def _client() -> TestClient:
    bus = MessageBus()
    web_channel = WebChannel(WebChannelConfig(), bus)
    cm = ConnectionManager()
    agent_loop = MagicMock()
    agent_loop.cron_service = None
    agent_loop.usage_recorder = None
    return TestClient(create_app(
        bus=bus,
        agent_loop=agent_loop,
        session_manager=MagicMock(),
        connection_manager=cm,
        web_channel=web_channel,
        auth_secret="",
    ))


def _seed_skill(workspace: Path, name: str, *, description: str = "test skill") -> Path:
    skill_dir = workspace / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nbody\n",
        encoding="utf-8",
    )
    return skill_dir


def test_delete_workspace_skill_succeeds(workspace: Path) -> None:
    skill_dir = _seed_skill(workspace, "my-test-skill")
    assert skill_dir.exists()

    r = _client().delete("/api/skills/my-test-skill")
    assert r.status_code == 200
    body = r.json()
    assert body == {"deleted": True, "name": "my-test-skill"}
    assert not skill_dir.exists()


def test_delete_missing_skill_404(workspace: Path) -> None:
    r = _client().delete("/api/skills/never-existed")
    assert r.status_code == 404


def test_delete_empty_name_400(workspace: Path) -> None:
    # FastAPI strips trailing slashes; explicit empty path doesn't match
    # the {name} route at all → 404 from the router, not a 400 from us.
    # The 400 path is exercised when the segment is whitespace only.
    r = _client().delete("/api/skills/%20")  # urlencoded space
    assert r.status_code == 400


def test_delete_clears_disabled_list_entry(workspace: Path) -> None:
    """If the skill was disabled, deleting it must also drop the
    ``disabled`` flag so the same name can be reused later."""
    from tokenmind.config.loader import load_config, save_config

    _seed_skill(workspace, "to-remove")
    config = load_config()
    config.skills.disabled = ["to-remove"]
    save_config(config)

    r = _client().delete("/api/skills/to-remove")
    assert r.status_code == 200

    refreshed = load_config()
    assert "to-remove" not in refreshed.skills.disabled
