"""Skills management API."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from tokenmind.agent.skill_suggestions import SkillSuggestion, SkillSuggestionStore
from tokenmind.agent.skills import SkillsLoader
from tokenmind.config.loader import load_config, save_config

router = APIRouter(prefix="/api/skills", tags=["skills"])


class SkillSummary(BaseModel):
    """Skill metadata + enabled state exposed to the Settings UI."""

    name: str
    description: str
    source: str  # "workspace" or "builtin"
    path: str
    enabled: bool
    available: bool
    missing_requirements: str | None = None
    always: bool = False
    emoji: str | None = None


class SkillListResponse(BaseModel):
    items: list[SkillSummary]


class SkillSuggestionResponse(SkillSuggestion):
    preview_markdown: str
    diff_markdown: str = ""


class SkillSuggestionListResponse(BaseModel):
    items: list[SkillSuggestionResponse]


class SkillSuggestionApproveRequest(BaseModel):
    overwrite: bool = False


class SkillSuggestionDeleteResponse(BaseModel):
    deleted: bool


class SkillToggleRequest(BaseModel):
    enabled: bool = Field(..., description="Whether the skill should be enabled")


class SlashSkillSummary(BaseModel):
    """Skill exposed as a ``/<name>`` slash command in the chat composer."""

    name: str
    description: str
    source: str


class SlashSkillListResponse(BaseModel):
    items: list[SlashSkillSummary]


class SkillBodyResponse(BaseModel):
    name: str
    body: str


def _loader() -> SkillsLoader:
    config = load_config()
    workspace = Path(config.agents.defaults.workspace).expanduser()
    return SkillsLoader(workspace, disabled_skills=list(config.skills.disabled))


def _suggestion_store() -> SkillSuggestionStore:
    config = load_config()
    workspace = Path(config.agents.defaults.workspace).expanduser()
    return SkillSuggestionStore(workspace)


def _suggestion_response(
    store: SkillSuggestionStore,
    suggestion: SkillSuggestion,
) -> SkillSuggestionResponse:
    return SkillSuggestionResponse(
        **suggestion.model_dump(),
        preview_markdown=store.render_preview(suggestion),
        diff_markdown=store.render_diff(suggestion),
    )


def _summaries(loader: SkillsLoader, disabled: set[str]) -> list[SkillSummary]:
    items: list[SkillSummary] = []
    for skill in loader.list_all_skills():
        name = skill["name"]
        skill_meta = loader._get_skill_meta(name)
        metadata = loader.get_skill_metadata(name) or {}
        available = loader._check_requirements(skill_meta)
        missing = loader._get_missing_requirements(skill_meta) if not available else None
        emoji = skill_meta.get("emoji") if isinstance(skill_meta, dict) else None
        always = bool(skill_meta.get("always")) if isinstance(skill_meta, dict) else False
        description = metadata.get("description") or loader._get_skill_description(name)
        items.append(
            SkillSummary(
                name=name,
                description=description or name,
                source=skill["source"],
                path=skill["path"],
                enabled=name not in disabled,
                available=available,
                missing_requirements=missing,
                always=always,
                emoji=emoji if isinstance(emoji, str) else None,
            )
        )
    items.sort(key=lambda item: (0 if item.source == "workspace" else 1, item.name))
    return items


@router.get("/list", response_model=SkillListResponse)
async def list_skills() -> SkillListResponse:
    config = load_config()
    disabled = set(config.skills.disabled)
    loader = _loader()
    return SkillListResponse(items=_summaries(loader, disabled))


@router.get("/slash", response_model=SlashSkillListResponse)
async def list_slash_skills() -> SlashSkillListResponse:
    """Skills opted-in to the slash menu (``slash: true`` frontmatter).

    Slash skills are user-triggered shortcuts: typing ``/<name>`` in the
    composer dispatches the skill's body as the user prompt (with optional
    ``$ARGS`` substitution). Disabled skills and skills whose
    ``requires:`` are unmet are excluded so the menu never offers broken
    commands.
    """
    loader = _loader()
    items = [
        SlashSkillSummary(
            name=item["name"],
            description=item["description"],
            source=item["source"],
        )
        for item in loader.list_slash_skills()
    ]
    return SlashSkillListResponse(items=items)


@router.get("/{name}/body", response_model=SkillBodyResponse)
async def get_skill_body(name: str) -> SkillBodyResponse:
    """Return the markdown body of a skill (frontmatter stripped).

    The frontend uses this when dispatching ``/<skill-name>`` so it can
    perform ``$ARGS`` substitution client-side and ship the rendered
    prompt as a normal user message.
    """
    if not name.strip():
        raise HTTPException(status_code=400, detail="Skill name cannot be empty")
    loader = _loader()
    body = loader.load_skill_body(name)
    if body is None:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return SkillBodyResponse(name=name, body=body)


@router.get("/suggestions", response_model=SkillSuggestionListResponse)
async def list_skill_suggestions() -> SkillSuggestionListResponse:
    store = _suggestion_store()
    return SkillSuggestionListResponse(
        items=[_suggestion_response(store, suggestion) for suggestion in store.list_pending()]
    )


@router.post("/suggestions/{suggestion_id}/approve", response_model=SkillSuggestionResponse)
async def approve_skill_suggestion(
    suggestion_id: str,
    request: SkillSuggestionApproveRequest | None = None,
) -> SkillSuggestionResponse:
    store = _suggestion_store()
    try:
        approved = store.approve(
            suggestion_id,
            overwrite=bool(request.overwrite) if request else False,
        )
        return _suggestion_response(store, approved)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skill suggestion not found") from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="Skill already exists") from exc


@router.delete("/suggestions/{suggestion_id}", response_model=SkillSuggestionDeleteResponse)
async def reject_skill_suggestion(suggestion_id: str) -> SkillSuggestionDeleteResponse:
    return SkillSuggestionDeleteResponse(deleted=_suggestion_store().reject(suggestion_id))


@router.put("/{name}/enabled", response_model=SkillSummary)
async def set_skill_enabled(name: str, request: SkillToggleRequest) -> SkillSummary:
    if not name.strip():
        raise HTTPException(status_code=400, detail="Skill name cannot be empty")

    config = load_config()
    loader = _loader()
    known = {skill["name"] for skill in loader.list_all_skills()}
    if name not in known:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    disabled = set(config.skills.disabled)
    if request.enabled:
        disabled.discard(name)
    else:
        disabled.add(name)
    config.skills.disabled = sorted(disabled)
    save_config(config)

    refreshed = _loader()
    summaries = _summaries(refreshed, set(config.skills.disabled))
    for summary in summaries:
        if summary.name == name:
            return summary
    raise HTTPException(status_code=500, detail="Failed to reload skill after update")


class SkillDeleteResponse(BaseModel):
    deleted: bool
    name: str


@router.delete("/{name}", response_model=SkillDeleteResponse)
async def delete_skill(name: str) -> SkillDeleteResponse:
    """Delete a user-installed skill from the workspace.

    Only ``source='workspace'`` skills can be removed — built-in skills
    that ship inside the tokenmind package are read-only and return 403.
    The directory is removed recursively and any ``disabled`` flag for
    this skill is cleared from the config so the same name can later be
    reused for a different skill.
    """
    if not name.strip():
        raise HTTPException(status_code=400, detail="Skill name cannot be empty")

    loader = _loader()
    target = None
    for skill in loader.list_all_skills():
        if skill["name"] == name:
            target = skill
            break
    if target is None:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    if target.get("source") != "workspace":
        raise HTTPException(
            status_code=403,
            detail="Built-in skills can't be deleted — disable them in Settings instead.",
        )

    # ``target['path']`` points at SKILL.md; the actual skill is the
    # parent directory we need to remove recursively.
    raw_path = Path(target["path"]).resolve()
    skill_dir = raw_path.parent if raw_path.is_file() else raw_path
    # Belt-and-braces: refuse to rmtree anything outside the workspace
    # skills/ dir, even if loader somehow handed us a wrong path.
    config = load_config()
    workspace_skills = (Path(config.agents.defaults.workspace).expanduser() / "skills").resolve()
    try:
        skill_dir.relative_to(workspace_skills)
    except ValueError as exc:
        raise HTTPException(
            status_code=403,
            detail="Refusing to delete a skill outside the workspace skills directory.",
        ) from exc

    try:
        shutil.rmtree(skill_dir)
    except OSError as exc:
        logger.exception("Failed to delete skill {} at {}", name, skill_dir)
        raise HTTPException(status_code=500, detail=f"Failed to delete skill: {exc}") from exc

    # Clean up the disabled-list entry if any so the name is fully gone.
    disabled = set(config.skills.disabled)
    if name in disabled:
        disabled.discard(name)
        config.skills.disabled = sorted(disabled)
        save_config(config)

    logger.info("Skill deleted: {} ({})", name, skill_dir)
    return SkillDeleteResponse(deleted=True, name=name)
