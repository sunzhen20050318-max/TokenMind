from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tokenmind.config.loader import load_config, save_config
from tokenmind.server.routes import skills as skills_routes


@pytest.fixture
def temp_config_path(tmp_path: Path):
    from tokenmind.config.loader import get_config_path, set_config_path

    previous = get_config_path()
    path = tmp_path / "config.json"
    set_config_path(path)
    try:
        yield path
    finally:
        set_config_path(previous)


@pytest.fixture
def fake_skills(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "workspace"
    builtin = tmp_path / "builtin"
    workspace.mkdir()
    builtin.mkdir()

    def _write(root: Path, name: str, description: str, metadata: str | None = None) -> None:
        skill_dir = root / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        meta_line = f'metadata: \'{metadata}\'\n' if metadata else ""
        (skill_dir / "SKILL.md").write_text(
            f"""---
name: {name}
description: "{description}"
{meta_line}---
""",
            encoding="utf-8",
        )

    _write(workspace / "skills", "local", "Workspace local skill")
    _write(
        builtin,
        "github",
        "GitHub CLI skill",
        metadata='{"tokenmind":{"emoji":"🐙","requires":{"bins":["nonexistent-cli"]}}}',
    )
    _write(
        builtin,
        "cron",
        "Cron scheduler",
        metadata='{"tokenmind":{"always":true}}',
    )

    # Make load_config see our test workspace path.
    def fake_load_config(*args, **kwargs):
        real = load_config(*args, **kwargs)
        real.agents.defaults.workspace = str(workspace)
        return real

    monkeypatch.setattr("tokenmind.server.routes.skills.load_config", fake_load_config)
    monkeypatch.setattr("tokenmind.server.routes.skills.BUILTIN_SKILLS_DIR", builtin, raising=False)
    monkeypatch.setattr("tokenmind.agent.skills.BUILTIN_SKILLS_DIR", builtin)
    return {"workspace": workspace, "builtin": builtin}


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(skills_routes.router)
    return TestClient(app)


def test_list_skills_returns_workspace_and_builtin(temp_config_path: Path, fake_skills) -> None:
    client = build_client()
    response = client.get("/api/skills/list")
    assert response.status_code == 200
    items = response.json()["items"]
    names = [item["name"] for item in items]
    assert "local" in names
    assert "github" in names
    assert "cron" in names

    github = next(item for item in items if item["name"] == "github")
    assert github["available"] is False
    assert "nonexistent-cli" in (github["missing_requirements"] or "")
    assert github["emoji"] == "🐙"

    cron = next(item for item in items if item["name"] == "cron")
    assert cron["always"] is True
    assert cron["enabled"] is True


def test_toggle_skill_persists_disabled_list(temp_config_path: Path, fake_skills) -> None:
    client = build_client()
    response = client.put(
        "/api/skills/cron/enabled",
        json={"enabled": False},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "cron"
    assert payload["enabled"] is False

    # Config file should now contain the disabled entry.
    config = load_config(temp_config_path)
    assert "cron" in config.skills.disabled

    # Re-enabling removes it from the disabled list.
    re_enable = client.put("/api/skills/cron/enabled", json={"enabled": True})
    assert re_enable.status_code == 200
    assert re_enable.json()["enabled"] is True
    config_after = load_config(temp_config_path)
    assert "cron" not in config_after.skills.disabled


def test_toggle_unknown_skill_returns_404(temp_config_path: Path, fake_skills) -> None:
    client = build_client()
    response = client.put(
        "/api/skills/does-not-exist/enabled",
        json={"enabled": False},
    )
    assert response.status_code == 404


def test_seeded_disabled_skill_reflected_in_list(temp_config_path: Path, fake_skills) -> None:
    config = load_config(temp_config_path)
    config.skills.disabled = ["github"]
    save_config(config, temp_config_path)

    client = build_client()
    response = client.get("/api/skills/list")
    assert response.status_code == 200
    items = response.json()["items"]
    github = next(item for item in items if item["name"] == "github")
    assert github["enabled"] is False


def test_skill_suggestion_routes_approve_and_reject(
    temp_config_path: Path,
    fake_skills,
) -> None:
    from tokenmind.agent.skill_suggestions import SkillSuggestionStore

    store = SkillSuggestionStore(fake_skills["workspace"])
    first = store.create(name="new workflow", description="New workflow", body="Do it safely.")
    second = store.create(name="reject me", description="Reject me", body="Nope.")

    client = build_client()

    listed = client.get("/api/skills/suggestions")
    assert listed.status_code == 200
    listed_items = listed.json()["items"]
    assert {item["id"] for item in listed_items} == {first.id, second.id}
    first_payload = next(item for item in listed_items if item["id"] == first.id)
    assert first_payload["preview_markdown"].startswith("---\n")
    assert "Do it safely." in first_payload["preview_markdown"]

    approved = client.post(f"/api/skills/suggestions/{first.id}/approve")
    assert approved.status_code == 200
    assert approved.json()["name"] == "new-workflow"
    assert (fake_skills["workspace"] / "skills" / "new-workflow" / "SKILL.md").exists()

    rejected = client.delete(f"/api/skills/suggestions/{second.id}")
    assert rejected.status_code == 200
    assert rejected.json()["deleted"] is True
    assert SkillSuggestionStore(fake_skills["workspace"]).list_pending() == []


def test_skill_update_suggestion_route_exposes_diff_and_approves(
    temp_config_path: Path,
    fake_skills,
) -> None:
    from tokenmind.agent.skill_suggestions import SkillSuggestionStore

    skill_dir = fake_skills["workspace"] / "skills" / "local"
    skill_dir.mkdir(parents=True, exist_ok=True)
    old = """---
name: local
description: "Old local skill"
---

# local
"""
    (skill_dir / "SKILL.md").write_text(old, encoding="utf-8")
    new = """---
name: local
description: "Updated local skill"
---

# local

## Procedure

1. Use the updated flow.
"""
    store = SkillSuggestionStore(fake_skills["workspace"])
    suggestion = store.create_update(
        target_skill="local",
        description="Updated local skill",
        markdown=new,
        previous_markdown=old,
    )

    client = build_client()
    listed = client.get("/api/skills/suggestions")
    payload = next(item for item in listed.json()["items"] if item["id"] == suggestion.id)

    assert payload["kind"] == "update"
    assert payload["target_skill"] == "local"
    assert "+1. Use the updated flow." in payload["diff_markdown"]

    approved = client.post(f"/api/skills/suggestions/{suggestion.id}/approve")

    assert approved.status_code == 200
    assert "Updated local skill" in (skill_dir / "SKILL.md").read_text(encoding="utf-8")
