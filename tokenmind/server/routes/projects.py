"""Projects API endpoints."""

from __future__ import annotations

import inspect
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from loguru import logger
from pydantic import BaseModel

from tokenmind.server.dependencies import get_chat_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str


class RenameProjectRequest(BaseModel):
    name: str


class UpdateProjectRequest(BaseModel):
    instructions: str | None = None


class AddUrlSourceRequest(BaseModel):
    url: str


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


@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    request: UpdateProjectRequest,
    service=Depends(get_chat_service),
) -> dict:
    """Patch mutable project fields. Currently only custom instructions."""
    if request.instructions is None:
        return service.get_project_detail(project_id)
    return service.update_project_instructions(project_id, request.instructions)


@router.delete("/{project_id}")
async def delete_project(project_id: str, service=Depends(get_chat_service)) -> dict:
    return service.delete_project(project_id)


@router.get("/{project_id}/documents")
async def list_project_documents(project_id: str, service=Depends(get_chat_service)) -> dict:
    return service.list_project_documents(project_id)


@router.post("/{project_id}/documents")
async def upload_project_documents(
    project_id: str,
    files: list[UploadFile] = File(...),
    service: Any = Depends(get_chat_service),
) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    try:
        result = service.upload_project_documents(project_id, files)
        if inspect.isawaitable(result):
            result = await result
        return result
    except HTTPException:
        raise
    except Exception as exc:
        # Log the detail server-side; return a generic message so internal
        # paths/state don't leak to the client.
        logger.exception("Failed to upload project documents for {}", project_id)
        raise HTTPException(status_code=500, detail="Failed to upload project documents") from exc


@router.post("/{project_id}/sources/url")
async def add_project_url_source(
    project_id: str,
    request: AddUrlSourceRequest,
    service=Depends(get_chat_service),
) -> dict:
    """Fetch a public URL (currently: mp.weixin.qq.com) and register it as a
    wiki source on the project's knowledge base."""
    try:
        return await service.add_project_url_source(project_id, request.url)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{project_id}/documents/{document_id}")
async def delete_project_document(
    project_id: str,
    document_id: str,
    service=Depends(get_chat_service),
) -> dict:
    try:
        return service.delete_project_document(project_id, document_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/recompile")
async def recompile_project_wiki(project_id: str, service=Depends(get_chat_service)) -> dict:
    try:
        return await service.recompile_project_wiki(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
