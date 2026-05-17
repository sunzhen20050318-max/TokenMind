"""Knowledge base API endpoints."""

from __future__ import annotations

import inspect
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from tokenmind.server.dependencies import get_chat_service

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class CreateKnowledgeBasePayload(BaseModel):
    name: str
    description: str = ""
    type: str = "rag"
    language: str = "zh"


class SessionKnowledgePayload(BaseModel):
    session_id: str
    knowledge_base_ids: list[str]


class UpdateKnowledgeBasePayload(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None


@router.get("")
async def list_knowledge_bases(service: Any = Depends(get_chat_service)) -> dict:
    try:
        return service.get_knowledge_overview()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load knowledge bases: {exc}") from exc


@router.post("")
async def create_knowledge_base(
    payload: CreateKnowledgeBasePayload,
    service: Any = Depends(get_chat_service),
) -> dict:
    try:
        return service.create_knowledge_base(
            payload.name,
            payload.description,
            type=payload.type,
            language=payload.language,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create knowledge base: {exc}") from exc


@router.get("/{knowledge_base_id}")
async def get_knowledge_base_detail(
    knowledge_base_id: str,
    service: Any = Depends(get_chat_service),
) -> dict:
    try:
        return service.get_knowledge_base_detail(knowledge_base_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load knowledge base detail: {exc}") from exc


@router.put("/{knowledge_base_id}")
async def update_knowledge_base(
    knowledge_base_id: str,
    payload: UpdateKnowledgeBasePayload,
    service: Any = Depends(get_chat_service),
) -> dict:
    try:
        updated = service.update_knowledge_base(
            knowledge_base_id,
            name=payload.name,
            description=payload.description,
            enabled=payload.enabled,
        )
        return {"knowledge_base": updated.model_dump()}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update knowledge base: {exc}") from exc


@router.delete("/{knowledge_base_id}")
async def delete_knowledge_base(
    knowledge_base_id: str,
    service: Any = Depends(get_chat_service),
) -> dict:
    try:
        return service.delete_knowledge_base(knowledge_base_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete knowledge base: {exc}") from exc


@router.get("/links/{session_id}")
async def get_session_knowledge_links(
    session_id: str,
    service: Any = Depends(get_chat_service),
) -> dict:
    try:
        return {
            "session_id": session_id,
            "knowledge_base_ids": service.get_session_knowledge_links(session_id),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load session knowledge links: {exc}") from exc


@router.put("/links/{session_id}")
async def update_session_knowledge_links(
    session_id: str,
    payload: SessionKnowledgePayload,
    service: Any = Depends(get_chat_service),
) -> dict:
    try:
        service.set_session_knowledge_links(session_id, payload.knowledge_base_ids)
        return {
            "session_id": session_id,
            "knowledge_base_ids": payload.knowledge_base_ids,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update session knowledge links: {exc}") from exc


@router.post("/{knowledge_base_id}/documents")
async def upload_knowledge_documents(
    knowledge_base_id: str,
    files: list[UploadFile] = File(...),
    service: Any = Depends(get_chat_service),
) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    try:
        result = service.upload_knowledge_documents(knowledge_base_id, files)
        if inspect.isawaitable(result):
            result = await result
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to upload knowledge documents: {exc}") from exc


@router.delete("/{knowledge_base_id}/documents/{document_id}")
async def delete_knowledge_document(
    knowledge_base_id: str,
    document_id: str,
    service: Any = Depends(get_chat_service),
) -> dict:
    try:
        return service.delete_knowledge_document(knowledge_base_id, document_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete knowledge document: {exc}") from exc


@router.get("/{knowledge_base_id}/graph")
async def get_kb_graph(
    knowledge_base_id: str,
    service: Any = Depends(get_chat_service),
) -> dict:
    try:
        return service.get_wiki_graph(knowledge_base_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{knowledge_base_id}/graph/rebuild")
async def rebuild_kb_graph(
    knowledge_base_id: str,
    service: Any = Depends(get_chat_service),
) -> dict:
    try:
        return service.rebuild_wiki_graph(knowledge_base_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{knowledge_base_id}/recompile")
async def recompile_wiki_sources(
    knowledge_base_id: str,
    service: Any = Depends(get_chat_service),
) -> dict:
    """Re-run wiki LLM compile for every source already uploaded to this KB.

    Useful when the wiki LLM was not wired at the time of upload (entities and
    topics ended up empty) or when the provider has been changed.
    """
    try:
        return await service.recompile_wiki_sources(knowledge_base_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{knowledge_base_id}/pages")
async def list_wiki_pages(
    knowledge_base_id: str,
    service: Any = Depends(get_chat_service),
) -> dict:
    try:
        return {"pages": service.list_wiki_pages(knowledge_base_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{knowledge_base_id}/pages/raw")
async def read_wiki_page(
    knowledge_base_id: str,
    path: str,
    service: Any = Depends(get_chat_service),
) -> dict:
    try:
        return service.read_wiki_page(knowledge_base_id, path)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
