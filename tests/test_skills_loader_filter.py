from __future__ import annotations

from pathlib import Path

from tokenmind.agent.skills import SkillsLoader


def _write_skill(root: Path, name: str, description: str, metadata: str | None = None) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    metadata_line = f'metadata: \'{metadata}\'\n' if metadata else ""
    (skill_dir / "SKILL.md").write_text(
        f"""---
name: {name}
description: "{description}"
{metadata_line}---

# {name}
""",
        encoding="utf-8",
    )


def test_list_all_skills_returns_every_skill(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    builtin = tmp_path / "builtin"
    _write_skill(workspace / "skills", "alpha", "Workspace alpha")
    _write_skill(builtin, "beta", "Built-in beta")

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin, disabled_skills=["alpha"])

    all_skills = {s["name"] for s in loader.list_all_skills()}
    assert all_skills == {"alpha", "beta"}


def test_list_skills_excludes_disabled(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    builtin = tmp_path / "builtin"
    _write_skill(workspace / "skills", "alpha", "Workspace alpha")
    _write_skill(builtin, "beta", "Built-in beta")

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin, disabled_skills=["alpha"])

    visible = {s["name"] for s in loader.list_skills(filter_unavailable=False)}
    assert visible == {"beta"}


def test_build_skills_summary_excludes_disabled(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    builtin = tmp_path / "builtin"
    _write_skill(builtin, "alpha", "Alpha skill")
    _write_skill(builtin, "beta", "Beta skill")

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin, disabled_skills=["alpha"])
    summary = loader.build_skills_summary()

    assert "beta" in summary
    assert "alpha" not in summary


def test_build_skill_route_index_is_compact_and_includes_triggers(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    builtin = tmp_path / "builtin"
    _write_skill(
        workspace / "skills",
        "pypi-release",
        "Publish Python packages",
        metadata='{"tokenmind":{"triggers":["twine upload","pip install"],"capabilities":["wheel build"]}}',
    )

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin)
    index = loader.build_skill_route_index()

    assert "pypi-release: Publish Python packages" in index
    assert "twine" in index
    assert "wheel" in index
    assert "<skill" not in index


def test_get_always_skills_honors_disabled(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    builtin = tmp_path / "builtin"
    _write_skill(
        builtin,
        "alpha",
        "Alpha",
        metadata='{"tokenmind":{"always":true}}',
    )
    _write_skill(
        builtin,
        "beta",
        "Beta",
        metadata='{"tokenmind":{"always":true}}',
    )

    enabled_loader = SkillsLoader(workspace, builtin_skills_dir=builtin, disabled_skills=[])
    assert set(enabled_loader.get_always_skills()) == {"alpha", "beta"}

    disabled_loader = SkillsLoader(
        workspace, builtin_skills_dir=builtin, disabled_skills=["alpha"]
    )
    assert disabled_loader.get_always_skills() == ["beta"]


def test_disabled_default_is_empty(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    builtin = tmp_path / "builtin"
    _write_skill(builtin, "alpha", "Alpha")

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin)
    assert {s["name"] for s in loader.list_skills(filter_unavailable=False)} == {"alpha"}


def test_office_artifact_skills_are_builtin_and_discoverable(tmp_path: Path) -> None:
    loader = SkillsLoader(tmp_path / "workspace")

    names = {skill["name"] for skill in loader.list_all_skills()}

    assert {"documents", "presentations", "spreadsheets"} <= names
    assert "Create, edit, redline" in (loader.get_skill_metadata("documents") or {}).get("description", "")
    assert ".pptx" in (loader.get_skill_metadata("presentations") or {}).get("description", "").lower()
    assert "spreadsheet files" in (loader.get_skill_metadata("spreadsheets") or {}).get("description", "")
