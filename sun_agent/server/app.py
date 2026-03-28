"""FastAPI application for sun_agent Web UI."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import mimetypes
from pathlib import Path
import secrets
import shutil
from typing import Any

from fastapi import HTTPException
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from sun_agent.audit import AuditLogger
from sun_agent.bus.events import InboundMessage, OutboundMessage
from sun_agent.bus.queue import MessageBus
from sun_agent.config.loader import load_config
from sun_agent.config.schema import UploadsConfig
from sun_agent.server.channel.web import WebChannel, WebChannelConfig
from sun_agent.server.dependencies import (
    get_connection_manager,
    set_cron_service,
    get_inbound_queue,
    set_chat_service,
    set_connection_manager,
    set_inbound_queue,
)
from sun_agent.server.routes import (
    chat_router,
    config_router,
    cron_router,
    sessions_router,
    status_router,
    storage_router,
)
from sun_agent.server.websocket.handler import websocket_handler
from sun_agent.server.websocket.manager import ConnectionManager
from sun_agent.utils.helpers import safe_filename


class ChatService:
    """
    Service for handling chat operations via REST API.

    This service wraps the MessageBus and AgentLoop to provide
    synchronous request-response chat functionality.
    """

    default_upload_config = UploadsConfig()

    def __init__(
        self,
        bus: MessageBus,
        agent_loop: Any,
        session_manager: Any,
    ):
        self.bus = bus
        self.agent_loop = agent_loop
        self.session_manager = session_manager
        self.audit = AuditLogger(session_manager.workspace)
        self._response_futures: dict[str, asyncio.Future] = {}
        self._last_upload_cleanup_at: datetime | None = None

    @property
    def uploads_dir(self) -> Path:
        path = self.session_manager.workspace / "uploads" / "web"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _load_upload_config(self) -> UploadsConfig:
        try:
            config = load_config()
            return config.tools.uploads
        except Exception:
            logger.exception("Failed to load upload settings, falling back to defaults")
            return self.default_upload_config.model_copy(deep=True)

    def _upload_policy(self) -> dict[str, int | timedelta]:
        uploads = self._load_upload_config()
        return {
            "max_file_mb": uploads.max_file_mb,
            "max_total_mb": uploads.max_total_mb,
            "retention_days": uploads.retention_days,
            "cleanup_interval_hours": uploads.cleanup_interval_hours,
            "max_file_bytes": uploads.max_file_mb * 1024 * 1024,
            "max_total_bytes": uploads.max_total_mb * 1024 * 1024,
            "retention": timedelta(days=uploads.retention_days),
            "cleanup_interval": timedelta(hours=uploads.cleanup_interval_hours),
        }

    @staticmethod
    def _format_bytes(size: int) -> str:
        if size <= 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB"]
        value = float(size)
        unit = units[0]
        for next_unit in units:
            unit = next_unit
            if value < 1024 or unit == units[-1]:
                break
            value /= 1024
        precision = 0 if value >= 100 or unit == "B" else 1
        return f"{value:.{precision}f} {unit}"

    def _session_upload_dir(self, session_id: str) -> Path:
        return self.uploads_dir / safe_filename(session_id)

    @staticmethod
    def _display_upload_name(path: Path, attachment_name: str | None = None) -> str:
        if attachment_name:
            return attachment_name
        name = path.name
        prefix, separator, suffix = name.partition("_")
        if separator and len(prefix) == 12 and all(ch in "0123456789abcdef" for ch in prefix.lower()):
            return suffix
        return name

    def _iter_upload_files(self) -> list[Path]:
        uploads_root = self.uploads_dir
        if not uploads_root.exists():
            return []
        return [path for path in uploads_root.rglob("*") if path.is_file()]

    def _current_upload_usage_bytes(self) -> int:
        total = 0
        for path in self._iter_upload_files():
            try:
                total += path.stat().st_size
            except OSError:
                continue
        return total

    @staticmethod
    def _extract_first_message_preview(session: Any) -> str | None:
        if not session or not getattr(session, "messages", None):
            return None
        for msg in session.messages:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, str):
                lines = [
                    line.strip()
                    for line in content.splitlines()
                    if line.strip()
                    and not line.startswith("[Attached Files")
                    and line != "Attached files are available in the workspace:"
                    and not line.startswith("- ")
                    and not line.startswith("Use read_file for text-based files when possible.")
                ]
                return "\n".join(lines)[:50] if lines else None
            if isinstance(content, list):
                text_blocks = [
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and isinstance(block.get("text"), str)
                ]
                visible_lines = [
                    line.strip()
                    for text in text_blocks
                    for line in text.splitlines()
                    if line.strip()
                    and not line.startswith("[Attached Files")
                    and line != "Attached files are available in the workspace:"
                    and not line.startswith("- ")
                    and not line.startswith("Use read_file for text-based files when possible.")
                ]
                return "\n".join(visible_lines)[:50] if visible_lines else None
        return None

    def _session_display_label(self, session_key: str, session: Any, metadata: dict[str, Any] | None = None) -> str:
        title = getattr(session, "title", None) or (metadata or {}).get("title")
        if title:
            return title
        preview = self._extract_first_message_preview(session)
        return preview or session_key

    def _build_upload_reference_map(self) -> dict[str, list[dict[str, str]]]:
        references: dict[str, list[dict[str, str]]] = {}
        for item in self.session_manager.list_sessions():
            session_key = item.get("key")
            if not session_key:
                continue
            session = self.session_manager.get_or_create(session_key)
            label = self._session_display_label(session_key, session, item)
            seen_for_session: set[str] = set()
            for message in session.messages:
                attachments = message.get("attachments")
                if not isinstance(attachments, list):
                    continue
                for attachment in attachments:
                    if not isinstance(attachment, dict):
                        continue
                    path = attachment.get("path")
                    if isinstance(path, str) and path:
                        resolved = str(Path(path).resolve())
                        if resolved in seen_for_session:
                            continue
                        references.setdefault(resolved, []).append({
                            "session_id": session_key,
                            "title": label,
                        })
                        seen_for_session.add(resolved)
        return references

    def _referenced_upload_paths(self) -> set[str]:
        return set(self._build_upload_reference_map())

    def cleanup_uploads(self, *, force: bool = False) -> dict[str, int]:
        policy = self._upload_policy()
        now = datetime.now()
        if (
            not force
            and self._last_upload_cleanup_at is not None
            and now - self._last_upload_cleanup_at < policy["cleanup_interval"]
        ):
            return {"deleted_files": 0, "deleted_dirs": 0}

        deleted_files = 0
        deleted_dirs = 0
        referenced = self._referenced_upload_paths()
        cutoff = now - policy["retention"]

        for path in self._iter_upload_files():
            try:
                resolved = str(path.resolve())
                modified_at = datetime.fromtimestamp(path.stat().st_mtime)
            except OSError:
                continue
            if resolved in referenced or modified_at >= cutoff:
                continue
            try:
                path.unlink()
                deleted_files += 1
            except OSError:
                logger.warning("Failed to delete stale upload file {}", path)

        uploads_root = self.uploads_dir
        if uploads_root.exists():
            for directory in sorted((path for path in uploads_root.rglob("*") if path.is_dir()), reverse=True):
                try:
                    next(directory.iterdir())
                except StopIteration:
                    try:
                        directory.rmdir()
                        deleted_dirs += 1
                    except OSError:
                        logger.warning("Failed to delete empty upload directory {}", directory)
                except OSError:
                    continue

        self._last_upload_cleanup_at = now
        if deleted_files or deleted_dirs:
            self.audit.record(
                "storage.cleanup",
                "success",
                actor="system",
                details={
                    "deleted_files": deleted_files,
                    "deleted_dirs": deleted_dirs,
                    "forced": force,
                },
            )
        return {"deleted_files": deleted_files, "deleted_dirs": deleted_dirs}

    @staticmethod
    def _categorize_upload(filename: str, mime_type: str | None) -> tuple[str, bool]:
        suffix = Path(filename).suffix.lower()
        mime = (mime_type or "").lower()
        if mime.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}:
            return "image", True
        if suffix in {".md", ".markdown"}:
            return "markdown", False
        if suffix == ".pdf":
            return "pdf", False
        if suffix in {".ppt", ".pptx", ".key"}:
            return "presentation", False
        if suffix in {".xls", ".xlsx", ".csv"}:
            return "spreadsheet", False
        if suffix in {".txt", ".json", ".yaml", ".yml", ".xml"}:
            return "text", False
        return "document", False

    async def save_uploads(self, session_id: str, files: list[Any]) -> list[dict[str, Any]]:
        """Persist uploaded files into the workspace and return attachment metadata."""
        self.cleanup_uploads()
        policy = self._upload_policy()

        pending_uploads: list[dict[str, Any]] = []
        for upload in files:
            filename = safe_filename(getattr(upload, "filename", "") or "upload")
            if not filename:
                continue
            content = await upload.read()
            if not content:
                continue

            mime_type = getattr(upload, "content_type", None) or mimetypes.guess_type(filename)[0] or ""
            category, is_image = self._categorize_upload(filename, mime_type)
            size = len(content)
            if size > policy["max_file_bytes"]:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"{filename} 超过单文件大小限制。"
                        f" 当前上限为 {self._format_bytes(int(policy['max_file_bytes']))}。"
                    ),
                )
            pending_uploads.append(
                {
                    "filename": filename,
                    "content": content,
                    "mime_type": mime_type,
                    "category": category,
                    "is_image": is_image,
                    "size": size,
                }
            )

        if not pending_uploads:
            return []

        incoming_total = sum(item["size"] for item in pending_uploads)
        current_total = self._current_upload_usage_bytes()
        if current_total + incoming_total > policy["max_total_bytes"]:
            remaining = max(int(policy["max_total_bytes"]) - current_total, 0)
            raise HTTPException(
                status_code=413,
                detail=(
                    "上传空间不足。"
                    f" 当前总配额为 {self._format_bytes(int(policy['max_total_bytes']))}，"
                    f" 剩余可用 {self._format_bytes(remaining)}。"
                ),
            )

        session_dir = self._session_upload_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        attachments: list[dict[str, Any]] = []
        for item in pending_uploads:
            stored_name = f"{secrets.token_hex(6)}_{item['filename']}"
            destination = session_dir / stored_name
            destination.write_bytes(item["content"])
            attachments.append(
                {
                    "name": item["filename"],
                    "path": str(destination),
                    "mime_type": item["mime_type"],
                    "size": item["size"],
                    "category": item["category"],
                    "is_image": item["is_image"],
                }
            )

        self.audit.record(
            "storage.upload.saved",
            "success",
            session_key=session_id,
            channel="web",
            chat_id=session_id,
            actor="web_user",
            details={
                "files": [
                    {
                        "name": item["name"],
                        "path": item["path"],
                        "size": item["size"],
                        "category": item["category"],
                    }
                    for item in attachments
                ],
            },
        )
        return attachments

    def list_upload_files(self) -> list[dict[str, Any]]:
        """List persisted uploads with reference metadata."""
        references = self._build_upload_reference_map()
        files: list[dict[str, Any]] = []
        for path in sorted(self._iter_upload_files(), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                stats = path.stat()
                resolved = str(path.resolve())
            except OSError:
                continue

            session_refs = references.get(resolved, [])
            mime_type = mimetypes.guess_type(path.name)[0] or ""
            category, is_image = self._categorize_upload(path.name, mime_type)
            files.append({
                "name": self._display_upload_name(path),
                "stored_name": path.name,
                "path": str(path),
                "size": stats.st_size,
                "mime_type": mime_type,
                "category": category,
                "is_image": is_image,
                "modified_at": datetime.fromtimestamp(stats.st_mtime).isoformat(),
                "created_at": datetime.fromtimestamp(stats.st_ctime).isoformat(),
                "referenced": bool(session_refs),
                "reference_count": len(session_refs),
                "referenced_by": session_refs,
                "can_delete": not session_refs,
            })
        return files

    def get_storage_overview(self) -> dict[str, Any]:
        """Summarize upload storage usage and file inventory."""
        policy = self._upload_policy()
        files = self.list_upload_files()
        used_bytes = sum(file["size"] for file in files)
        referenced_count = sum(1 for file in files if file["referenced"])
        stale_cutoff = datetime.now() - policy["retention"]
        stale_unreferenced_count = sum(
            1
            for file in files
            if not file["referenced"] and datetime.fromisoformat(file["modified_at"]) < stale_cutoff
        )
        return {
            "summary": {
                "used_bytes": used_bytes,
                "quota_bytes": int(policy["max_total_bytes"]),
                "available_bytes": max(int(policy["max_total_bytes"]) - used_bytes, 0),
                "max_file_bytes": int(policy["max_file_bytes"]),
                "file_count": len(files),
                "referenced_file_count": referenced_count,
                "unreferenced_file_count": len(files) - referenced_count,
                "stale_unreferenced_file_count": stale_unreferenced_count,
                "retention_days": int(policy["retention_days"]),
                "cleanup_interval_hours": int(policy["cleanup_interval_hours"]),
            },
            "files": files,
        }

    def delete_upload_file(self, raw_path: str) -> dict[str, Any]:
        """Delete a single unreferenced upload file."""
        if not raw_path.strip():
            raise HTTPException(status_code=400, detail="File path cannot be empty")

        uploads_root = self.uploads_dir.resolve()
        target = Path(raw_path)
        try:
            resolved = target.resolve()
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid upload path: {exc}") from exc

        if uploads_root != resolved and uploads_root not in resolved.parents:
            raise HTTPException(status_code=400, detail="Only files inside the upload workspace can be deleted")
        if not resolved.exists() or not resolved.is_file():
            raise HTTPException(status_code=404, detail="Upload file not found")

        references = self._build_upload_reference_map().get(str(resolved), [])
        if references:
            raise HTTPException(status_code=409, detail="This file is still referenced by at least one conversation")

        size = resolved.stat().st_size
        resolved.unlink()

        parent = resolved.parent
        while parent != uploads_root and parent.exists():
            try:
                next(parent.iterdir())
                break
            except StopIteration:
                parent.rmdir()
                parent = parent.parent
            except OSError:
                break

        result = {
            "success": True,
            "path": str(resolved),
            "deleted_bytes": size,
        }
        self.audit.record(
            "storage.file.deleted",
            "success",
            actor="web_user",
            details={
                "path": str(resolved),
                "deleted_bytes": size,
            },
        )
        return result

    async def send_message(
        self,
        content: str,
        session_id: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict:
        """
        Send a message and wait for response.

        Args:
            content: The message content.
            session_id: The session identifier.

        Returns:
            Dict with response content, session_id, and tools_used.
        """
        # Create a future to wait for the response
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._response_futures[session_id] = future

        try:
            # Publish message to bus
            attachments = attachments or []
            msg = InboundMessage(
                channel="web",
                sender_id="web_user",
                chat_id=session_id,
                content=content,
                media=[item["path"] for item in attachments if item.get("is_image") and item.get("path")],
                metadata={"sync_response": True, "attachments": attachments},
                session_key_override=session_id,
            )
            await self.bus.publish_inbound(msg)

            # Wait for response with timeout
            try:
                response = await asyncio.wait_for(future, timeout=120.0)
                return response
            except asyncio.TimeoutError:
                return {
                    "response": "Request timed out. Please try again.",
                    "session_id": session_id,
                    "tools_used": [],
                }
        finally:
            self._response_futures.pop(session_id, None)

    def deliver_response(self, session_id: str, response: str, tools_used: list[str] | None = None) -> None:
        """Deliver a response to a waiting request."""
        future = self._response_futures.get(session_id)
        if future and not future.done():
            future.set_result({
                "response": response,
                "session_id": session_id,
                "tools_used": tools_used or [],
            })

    async def get_history(self, session_id: str) -> dict:
        """Get chat history for a session."""
        session = self.session_manager.get_or_create(session_id)
        return {
            "messages": session.messages if session else [],
            "timeline_events": session.timeline_events if session else [],
        }

    async def list_sessions(self) -> list[dict]:
        """List all sessions."""
        sessions = self.session_manager.list_sessions()
        result = []
        for s in sessions:
            session_id = s.get("key", "")
            # Load full session to get first message
            session = self.session_manager.get_or_create(session_id)
            first_message = None
            if session and session.messages:
                for msg in session.messages:
                    if msg.get("role") == "user":
                        content = msg.get("content", "")
                        if isinstance(content, str):
                            lines = [
                                line.strip()
                                for line in content.splitlines()
                                if line.strip()
                                and not line.startswith("[Attached Files")
                                and line != "Attached files are available in the workspace:"
                                and not line.startswith("- ")
                                and not line.startswith("Use read_file for text-based files when possible.")
                            ]
                            first_message = "\n".join(lines)[:50] if lines else None
                        elif isinstance(content, list):
                            text_blocks = [
                                block.get("text", "")
                                for block in content
                                if isinstance(block, dict) and isinstance(block.get("text"), str)
                            ]
                            visible_lines = [
                                line.strip()
                                for text in text_blocks
                                for line in text.splitlines()
                                if line.strip()
                                and not line.startswith("[Attached Files")
                                and line != "Attached files are available in the workspace:"
                                and not line.startswith("- ")
                                and not line.startswith("Use read_file for text-based files when possible.")
                            ]
                            first_message = "\n".join(visible_lines)[:50] if visible_lines else None
                        break
            result.append({
                "session_id": session_id,
                "updated_at": s.get("updated_at"),
                "created_at": session.created_at.isoformat() if session else None,
                "message_count": len(session.messages) if session else 0,
                "first_message": first_message,
                "title": session.title if session else s.get("title"),
            })
        return result

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        # Remove from cache
        self.session_manager.invalidate(session_id)
        # Also delete the session file from disk
        session_path = self.session_manager._get_session_path(session_id)
        if session_path.exists():
            session_path.unlink()
        upload_dir = self._session_upload_dir(session_id)
        uploads_removed = upload_dir.exists()
        if upload_dir.exists():
            shutil.rmtree(upload_dir, ignore_errors=True)
        channel, chat_id = (session_id.split(":", 1) if ":" in session_id else ("web", session_id))
        self.audit.record(
            "session.deleted",
            "success",
            session_key=session_id,
            channel=channel,
            chat_id=chat_id,
            actor="web_user",
            details={"uploads_removed": uploads_removed},
        )
        return True

    async def clear_history(self, session_id: str) -> bool:
        """Clear history for a session."""
        session = self.session_manager.get_or_create(session_id)
        if session:
            session.clear()
            self.session_manager.save(session)
            channel, chat_id = (session_id.split(":", 1) if ":" in session_id else ("web", session_id))
            self.audit.record(
                "session.cleared",
                "success",
                session_key=session_id,
                channel=channel,
                chat_id=chat_id,
                actor="web_user",
            )
            return True
        return False

    async def rename_session(self, session_id: str, title: str | None) -> dict:
        """Rename a session by updating its user-facing title."""
        session = self.session_manager.get_or_create(session_id)
        session.set_title(title)
        self.session_manager.save(session)
        return {
            "session_id": session_id,
            "title": session.title,
        }

    def ensure_session(self, session_id: str, title: str | None = None) -> dict:
        """Create a session if needed and optionally assign a title."""
        session = self.session_manager.get_or_create(session_id)
        if title:
            session.set_title(title)
        self.session_manager.save(session)
        return {
            "session_id": session_id,
            "title": session.title,
        }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI app."""
    # This will be set by the web command before starting the server
    chat_service = getattr(app.state, "chat_service", None)
    if chat_service is not None:
        try:
            cleanup_result = chat_service.cleanup_uploads(force=True)
            if cleanup_result["deleted_files"] or cleanup_result["deleted_dirs"]:
                logger.info(
                    "Upload cleanup finished: {} files, {} directories removed",
                    cleanup_result["deleted_files"],
                    cleanup_result["deleted_dirs"],
                )
        except Exception:
            logger.exception("Failed to clean uploads during startup")
    yield


def create_app(
    bus: MessageBus,
    agent_loop: Any,
    session_manager: Any,
    connection_manager: ConnectionManager,
    web_channel: WebChannel,
) -> FastAPI:
    """Create and configure the FastAPI application."""

    # Create chat service
    chat_service = ChatService(
        bus=bus,
        agent_loop=agent_loop,
        session_manager=session_manager,
    )
    set_chat_service(chat_service)
    set_connection_manager(connection_manager)
    set_inbound_queue(bus.inbound)
    set_cron_service(getattr(agent_loop, "cron_service", None))

    # Create FastAPI app
    app = FastAPI(
        title="sun_agent Web UI",
        description="Web UI for sun_agent AI assistant",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.chat_service = chat_service

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(chat_router)
    app.include_router(config_router)
    app.include_router(cron_router)
    app.include_router(sessions_router)
    app.include_router(status_router)
    app.include_router(storage_router)

    # WebSocket endpoint
    @app.websocket("/ws/chat")
    async def ws_chat(websocket: WebSocket, session_id: str | None = None):
        """WebSocket endpoint for real-time chat."""
        if session_id is None:
            # Generate a random session ID for anonymous users
            import uuid
            session_id = f"web:{uuid.uuid4().hex[:12]}"

        await websocket_handler(
            websocket=websocket,
            session_key=session_id,
            connection_manager=connection_manager,
            inbound_queue=bus.inbound,
        )

    # Set WebChannel's ws manager
    web_channel.set_ws_manager(connection_manager)

    # Return app without starting dispatcher - it will be started via lifespan
    return app
