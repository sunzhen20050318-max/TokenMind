"""Chat API endpoints."""

from __future__ import annotations

from pathlib import Path
from pydantic import BaseModel
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from tokenmind.server.attachments import (
    MissingSofficeError,
    OfficeConversionError,
    convert_office_to_pdf,
    is_office_file,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


class SendMessageRequest(BaseModel):
    """Request model for sending a message."""

    message: str
    session_id: str | None = None
    attachments: list[dict[str, Any]] = []


class SendMessageResponse(BaseModel):
    """Response model for sending a message."""

    response: str
    session_id: str
    tools_used: list[str] = []


class ChatHistoryResponse(BaseModel):
    """Response model for chat history."""

    session_id: str
    messages: list[dict[str, Any]]
    timeline_events: list[dict[str, Any]] = []
    consolidated_offset: int = 0
    personality: str | None = None
    plan_mode: bool = False
    # TokenMind's *soft* threshold for auto /compact, not the model's
    # hard context limit. Sourced from ``agents.defaults.context_window_tokens``.
    compaction_threshold_tokens: int = 0
    # The actual prompt-token count from the most recent LLM call
    # (input + cached input). ``None`` until the first call lands.
    last_prompt_tokens: int | None = None
    last_prompt_at: str | None = None
    last_prompt_model: str | None = None


class UploadFilesResponse(BaseModel):
    """Response model for uploaded files."""

    session_id: str
    attachments: list[dict[str, Any]]


class RetainAttachmentResponse(BaseModel):
    """Response model for retaining an assistant attachment."""

    attachment: dict[str, Any]


def get_chat_service():
    """Get chat service dependency."""
    # This will be injected via FastAPI dependency
    from tokenmind.server.dependencies import get_chat_service
    return get_chat_service()


@router.post("/send", response_model=SendMessageResponse)
async def send_message(
    request: SendMessageRequest,
    service=Depends(get_chat_service),
):
    """
    Send a message and get the agent's response.

    This is a synchronous request-response endpoint.
    For real-time streaming, use the WebSocket endpoint instead.
    """
    if not request.message.strip() and not request.attachments:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        result = await service.send_message(
            content=request.message,
            session_id=request.session_id or f"web:auto_{id(request)}",
            attachments=request.attachments,
        )
        return SendMessageResponse(
            response=result["response"],
            session_id=result["session_id"],
            tools_used=result.get("tools_used", []),
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/upload", response_model=UploadFilesResponse)
async def upload_files(
    session_id: str = Form(...),
    files: list[UploadFile] = File(...),
    service=Depends(get_chat_service),
):
    """Upload files for a chat session and return workspace-backed attachment metadata."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    attachments = await service.save_uploads(session_id, files)
    if not attachments:
        raise HTTPException(status_code=400, detail="No valid files uploaded")
    return UploadFilesResponse(session_id=session_id, attachments=attachments)


@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: str,
    service=Depends(get_chat_service),
):
    """Get the conversation history for a session."""
    try:
        history = await service.get_history(session_id)
        return ChatHistoryResponse(
            session_id=session_id,
            messages=history.get("messages", []),
            timeline_events=history.get("timeline_events", []),
            consolidated_offset=history.get("consolidated_offset", 0),
            personality=history.get("personality"),
            plan_mode=bool(history.get("plan_mode", False)),
            compaction_threshold_tokens=int(history.get("compaction_threshold_tokens", 0)),
            last_prompt_tokens=history.get("last_prompt_tokens"),
            last_prompt_at=history.get("last_prompt_at"),
            last_prompt_model=history.get("last_prompt_model"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/attachments/{attachment_id}")
async def download_attachment(
    attachment_id: str,
    disposition: str = "attachment",
    service=Depends(get_chat_service),
):
    """Download or preview a stored chat attachment.

    ``disposition=inline`` serves the file for in-browser preview (PDF viewer,
    <img>, <audio>, etc.). The default ``attachment`` triggers a browser
    download via ``Content-Disposition: attachment``.
    """
    try:
        attachment = service.resolve_attachment(attachment_id)
        mime = attachment.get("mime_type") or "application/octet-stream"
        if disposition == "inline":
            # Omit filename so Starlette does not emit an "attachment" Content-Disposition.
            # Browsers will render the file inline based on the Content-Type header.
            return FileResponse(attachment["storage_path"], media_type=mime)
        return FileResponse(
            attachment["storage_path"],
            media_type=mime,
            filename=attachment.get("name"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.api_route("/attachments/{attachment_id}/preview", methods=["GET", "HEAD"])
async def preview_attachment(
    attachment_id: str,
    service=Depends(get_chat_service),
):
    """Preview-friendly variant of attachment download.

    For native preview formats (PDF, image, audio, video, text) this serves
    the original file inline — same effect as ``?disposition=inline`` on the
    download endpoint.

    For Office formats (.docx / .xlsx / .pptx and friends) this lazily
    converts the file to PDF via soffice on first call, caches the result
    next to the source, and returns the PDF. The frontend's PDF viewer
    handles both the original-PDF case and the converted-from-Office case
    identically.

    Errors:
      * ``503`` — soffice not installed (helpful message in ``detail``)
      * ``502`` — soffice ran but failed to produce a PDF
      * ``504`` — conversion timed out
    """
    try:
        attachment = service.resolve_attachment(attachment_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    source_path = Path(attachment["storage_path"])
    name = attachment.get("name") or source_path.name

    if not is_office_file(name):
        # Non-office: serve as-is for inline preview.
        mime = attachment.get("mime_type") or "application/octet-stream"
        return FileResponse(source_path, media_type=mime)

    try:
        pdf_path = convert_office_to_pdf(source_path)
    except MissingSofficeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except OfficeConversionError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Attachment file missing on disk")

    return FileResponse(pdf_path, media_type="application/pdf")


@router.post("/attachments/{attachment_id}/retain", response_model=RetainAttachmentResponse)
async def retain_attachment(
    attachment_id: str,
    service=Depends(get_chat_service),
):
    """Promote a temporary assistant attachment into saved storage."""
    try:
        attachment = service.retain_attachment(attachment_id)
        return RetainAttachmentResponse(attachment=attachment)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
