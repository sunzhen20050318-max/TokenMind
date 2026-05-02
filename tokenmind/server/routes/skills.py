"""Skills management API."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
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
