"""Browser automation (OpenCLI) API."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tokenmind.integrations.opencli import (
    PINNED_OPENCLI_VERSION,
    OpenCLIService,
    SiteEntry,
    SiteRegistry,
    install_opencli,
    installation_to_dict,
)
from tokenmind.server.dependencies import get_opencli_service, get_site_registry

router = APIRouter(prefix="/api/browser", tags=["browser"])


def _require_service(service: Any = Depends(get_opencli_service)) -> OpenCLIService:
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="OpenCLI service is not available",
        )
    return service


def _require_registry(registry: Any = Depends(get_site_registry)) -> SiteRegistry:
    if registry is None:
        raise HTTPException(
            status_code=503,
            detail="Site registry is not available",
        )
    return registry


class SiteRegistryEntry(BaseModel):
    id: str
    name: str
    url: str
    hostname: str
    logged_in: bool
    is_preset: bool
    adapter: str | None = None
    updated_at: float


class SiteRegistryListResponse(BaseModel):
    items: list[SiteRegistryEntry]


class SiteRegistryAddRequest(BaseModel):
    name: str
    url: str
    adapter: str | None = None


class SiteRegistryUpdateRequest(BaseModel):
    name: str | None = None
    url: str | None = None
    logged_in: bool | None = None


def _entry_to_model(entry: SiteEntry) -> SiteRegistryEntry:
    return SiteRegistryEntry(
        id=entry.id,
        name=entry.name,
        url=entry.url,
        hostname=entry.hostname,
        logged_in=entry.logged_in,
        is_preset=entry.is_preset,
        adapter=entry.adapter,
        updated_at=entry.updated_at,
    )


class SiteCommandResponse(BaseModel):
    name: str
    description: str | None = None


class SiteResponse(BaseModel):
    site: str
    commands: list[SiteCommandResponse]
    featured: bool


class SiteListResponse(BaseModel):
    items: list[SiteResponse]
    featured_count: int


class ProfileResponse(BaseModel):
    context_id: str
    alias: str | None = None
    is_default: bool = False


class ProfileListResponse(BaseModel):
    items: list[ProfileResponse]


class SetDefaultProfileRequest(BaseModel):
    alias_or_id: str


class RunRequest(BaseModel):
    mode: Literal["site", "primitive"]
    site: str | None = None
    command: str | None = None
    args: dict[str, Any] | None = None
    session: str | None = None
    action: str | None = None
    options: dict[str, Any] | None = None
    profile: str | None = None
    timeout_s: int | None = None


class RunResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    command: list[str]


@router.get("/status")
async def get_browser_status(
    refresh: bool = False,
    service: OpenCLIService = Depends(_require_service),
):
    install = await service.detect(force=refresh)
    return installation_to_dict(install)


class InstallResponse(BaseModel):
    success: bool
    message: str
    version: str
    status: dict[str, Any]


@router.post("/install", response_model=InstallResponse)
async def install_browser_cli(
    service: OpenCLIService = Depends(_require_service),
):
    """One-click install of the pinned OpenCLI npm package.

    Only the npm package is automatable here. Node and the Chrome extension
    are surfaced as guided steps via the refreshed status (the wizard polls
    ``/status`` and ticks them off as the user completes them).
    """
    ok, message = await install_opencli()
    install = await service.detect(force=True)
    return InstallResponse(
        success=ok,
        message=message,
        version=PINNED_OPENCLI_VERSION,
        status=installation_to_dict(install),
    )


@router.get("/sites", response_model=SiteListResponse)
async def list_sites(
    refresh: bool = False,
    service: OpenCLIService = Depends(_require_service),
):
    sites = await service.list_sites(force=refresh)
    items = [
        SiteResponse(
            site=s.site,
            commands=[SiteCommandResponse(name=c.name, description=c.description) for c in s.commands],
            featured=s.featured,
        )
        for s in sites
    ]
    return SiteListResponse(
        items=items,
        featured_count=sum(1 for s in items if s.featured),
    )


@router.get("/profiles", response_model=ProfileListResponse)
async def list_profiles(
    refresh: bool = False,
    service: OpenCLIService = Depends(_require_service),
):
    profiles = await service.list_profiles(force=refresh)
    return ProfileListResponse(
        items=[
            ProfileResponse(
                context_id=p.context_id,
                alias=p.alias,
                is_default=p.is_default,
            )
            for p in profiles
        ]
    )


@router.post("/profiles/use", response_model=RunResponse)
async def set_default_profile(
    payload: SetDefaultProfileRequest,
    service: OpenCLIService = Depends(_require_service),
):
    target = payload.alias_or_id.strip()
    if not target:
        raise HTTPException(status_code=400, detail="alias_or_id is required")
    result = await service.set_default_profile(target)
    return RunResponse(
        success=result.success,
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        duration_ms=result.duration_ms,
        command=result.command,
    )


@router.post("/run", response_model=RunResponse)
async def run_browser_command(
    payload: RunRequest,
    service: OpenCLIService = Depends(_require_service),
):
    install = await service.detect()
    if not install.ready:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "OpenCLI is not ready",
                "missing_steps": [
                    {"key": s.key, "title": s.title, "command": s.command, "url": s.url}
                    for s in install.missing_steps
                ],
            },
        )

    if payload.mode == "site":
        if not payload.site or not payload.command:
            raise HTTPException(
                status_code=400, detail="site and command are required for mode=site"
            )
        result = await service.run_site_command(
            payload.site,
            payload.command,
            payload.args or {},
            profile=payload.profile,
            timeout=float(payload.timeout_s) if payload.timeout_s else None,
        )
    else:
        if not payload.action:
            raise HTTPException(
                status_code=400, detail="action is required for mode=primitive"
            )
        result = await service.run_browser_primitive(
            (payload.session or "tokenmind").strip() or "tokenmind",
            payload.action,
            payload.options or {},
            profile=payload.profile,
            timeout=float(payload.timeout_s) if payload.timeout_s else None,
        )
    return RunResponse(
        success=result.success,
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        duration_ms=result.duration_ms,
        command=result.command,
    )


@router.get("/sites_registry", response_model=SiteRegistryListResponse)
async def list_site_registry(
    registry: SiteRegistry = Depends(_require_registry),
):
    return SiteRegistryListResponse(items=[_entry_to_model(e) for e in registry.list()])


@router.post(
    "/sites_registry",
    response_model=SiteRegistryEntry,
    status_code=201,
)
async def add_site_registry(
    payload: SiteRegistryAddRequest,
    registry: SiteRegistry = Depends(_require_registry),
):
    try:
        entry = registry.add(
            name=payload.name,
            url=payload.url,
            adapter=payload.adapter,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return _entry_to_model(entry)


@router.patch("/sites_registry/{entry_id}", response_model=SiteRegistryEntry)
async def update_site_registry(
    entry_id: str,
    payload: SiteRegistryUpdateRequest,
    registry: SiteRegistry = Depends(_require_registry),
):
    try:
        entry = registry.update(
            entry_id,
            name=payload.name,
            url=payload.url,
            logged_in=payload.logged_in,
        )
    except KeyError as err:
        raise HTTPException(status_code=404, detail="site not found") from err
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return _entry_to_model(entry)


@router.delete("/sites_registry/{entry_id}", status_code=204)
async def delete_site_registry(
    entry_id: str,
    registry: SiteRegistry = Depends(_require_registry),
):
    try:
        registry.remove(entry_id)
    except KeyError as err:
        raise HTTPException(status_code=404, detail="site not found") from err
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return None


@router.post("/sites_registry/{entry_id}/open", response_model=RunResponse)
async def open_site_for_login(
    entry_id: str,
    registry: SiteRegistry = Depends(_require_registry),
    service: OpenCLIService = Depends(_require_service),
):
    """Open the site's URL in the user's Chrome so they can sign in.

    Uses ``mode=primitive open`` against a shared ``tokenmind-registry``
    browser session so the page lands in the user's existing Chrome
    window. The user then manually toggles "已登录" when finished.
    """
    entry = registry.get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="site not found")
    install = await service.detect()
    if not install.ready:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "OpenCLI is not ready",
                "missing_steps": [
                    {"key": s.key, "title": s.title, "command": s.command, "url": s.url}
                    for s in install.missing_steps
                ],
            },
        )
    result = await service.run_browser_primitive(
        "tokenmind-registry",
        "open",
        {},
        positional=[entry.url],
        timeout=30.0,
    )
    return RunResponse(
        success=result.success,
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        duration_ms=result.duration_ms,
        command=result.command,
    )
