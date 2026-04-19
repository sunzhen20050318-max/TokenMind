"""Projects API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from tokenmind.server.dependencies import get_chat_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str


class RenameProjectRequest(BaseModel):
    name: str


class CreateProjectSessionRequest(BaseModel):
    session_id: str
    title: str | None = None


class LinkProjectSessionRequest(BaseModel):
    session_id: str


@router.get("")
async def list_projects(service=Depends(get_chat_service)) -> dict:
    return service.list_projects()


@router.post("")
async def create_project(request: CreateProjectRequest, service=Depends(get_chat_service)) -> dict:
    return service.create_project(request.name)


@router.get("/{project_id}")
async def get_project(project_id: str, service=Depends(get_chat_service)) -> dict:
    return service.get_project_detail(project_id)


@router.put("/{project_id}")
async def rename_project(project_id: str, request: RenameProjectRequest, service=Depends(get_chat_service)) -> dict:
    return service.rename_project(project_id, request.name)


@router.delete("/{project_id}")
async def delete_project(project_id: str, service=Depends(get_chat_service)) -> dict:
    return service.delete_project(project_id)


@router.post("/{project_id}/sessions")
async def create_project_session(
    project_id: str,
    request: CreateProjectSessionRequest,
    service=Depends(get_chat_service),
) -> dict:
    return service.create_project_session(project_id, request.session_id, request.title)


@router.post("/{project_id}/sessions/link")
async def link_session_to_project(
    project_id: str,
    request: LinkProjectSessionRequest,
    service=Depends(get_chat_service),
) -> dict:
    return service.move_session_to_project(project_id, request.session_id)
