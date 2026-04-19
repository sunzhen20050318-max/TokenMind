"""FastAPI application for TokenMind Web UI."""

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

from tokenmind.audit import AuditLogger
from tokenmind.bus.events import InboundMessage, OutboundMessage
from tokenmind.bus.queue import MessageBus
from tokenmind.knowledge import KnowledgeService
from tokenmind.projects import ProjectStore
from tokenmind.config.loader import load_config
from tokenmind.config.schema import KnowledgeConfig, UploadsConfig
from tokenmind.agent.memory import split_history_entries
from tokenmind.agent.context import ContextBuilder
from tokenmind.server.channel.web import WebChannel, WebChannelConfig
from tokenmind.server.dependencies import (
    get_connection_manager,
    set_cron_service,
    get_inbound_queue,
    set_chat_service,
    set_connection_manager,
    set_inbound_queue,
)
from tokenmind.server.routes import (
    chat_router,
    config_router,
    cron_router,
    knowledge_router,
    memory_router,
    projects_router,
    sessions_router,
    status_router,
    storage_router,
)
from tokenmind.server.websocket.handler import websocket_handler
from tokenmind.server.websocket.manager import ConnectionManager
from tokenmind.utils.helpers import safe_filename


class ChatService:
    """
    Service for handling chat operations via REST API.

    This service wraps the MessageBus and AgentLoop to provide
    synchronous request-response chat functionality.
    """

    default_upload_config = UploadsConfig()
    default_knowledge_config = KnowledgeConfig()

    def __init__(
        self,
        bus: MessageBus,
        agent_loop: Any,
        session_manager: Any,
    ):
        self.bus = bus
        self.agent_loop = agent_loop
        self.session_manager = session_manager
        knowledge = self._load_knowledge_config()
        self.knowledge = KnowledgeService(
            session_manager.workspace,
            vector_backend=knowledge.vector_backend,
            chunk_size=knowledge.chunk_size,
            chunk_overlap=knowledge.chunk_overlap,
            top_k=knowledge.top_k,
            embedding_model=knowledge.embedding_model,
            embedding_api_key=knowledge.embedding_api_key,
            embedding_api_base=knowledge.embedding_api_base,
            rerank_model=knowledge.rerank_model,
            rerank_api_key=knowledge.rerank_api_key,
            rerank_api_base=knowledge.rerank_api_base,
            rerank_top_n=knowledge.rerank_top_n,
        )
        self.projects = ProjectStore(session_manager.workspace)
        self.audit = AuditLogger(session_manager.workspace)
        self._response_futures: dict[str, asyncio.Future] = {}
        self._last_upload_cleanup_at: datetime | None = None
        self._knowledge_tasks: set[asyncio.Task[Any]] = set()

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

    def _load_knowledge_config(self) -> KnowledgeConfig:
        try:
            config = load_config()
            return config.tools.knowledge
        except Exception:
            logger.exception("Failed to load knowledge settings, falling back to defaults")
            return self.default_knowledge_config.model_copy(deep=True)

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

    def _sync_knowledge_config(self) -> None:
        config = self._load_knowledge_config()
        self.knowledge.configure(
            vector_backend=config.vector_backend,
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            top_k=config.top_k,
            embedding_model=config.embedding_model,
            embedding_api_key=config.embedding_api_key,
            embedding_api_base=config.embedding_api_base,
            rerank_model=config.rerank_model,
            rerank_api_key=config.rerank_api_key,
            rerank_api_base=config.rerank_api_base,
            rerank_top_n=config.rerank_top_n,
        )

    def _schedule_knowledge_task(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._knowledge_tasks.add(task)
        task.add_done_callback(self._knowledge_tasks.discard)

    async def _process_knowledge_document(self, document_id: str) -> None:
        try:
            await asyncio.to_thread(self.knowledge.process_document, document_id)
        except Exception:
            logger.exception("Failed background processing for knowledge document {}", document_id)

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
            sanitized = ChatService._sanitize_message_content(msg.get("content", ""))
            if isinstance(sanitized, str):
                visible = sanitized.strip()
                return visible[:50] if visible else None
            if isinstance(sanitized, list):
                text_blocks = [
                    block.get("text", "").strip()
                    for block in sanitized
                    if isinstance(block, dict) and isinstance(block.get("text"), str) and block.get("text", "").strip()
                ]
                if text_blocks:
                    return "\n".join(text_blocks)[:50]
        return None

    @staticmethod
    def _session_last_activity_iso(session: Any, fallback: str | None = None) -> str | None:
        latest: datetime | None = None

        for message in getattr(session, "messages", []) or []:
            timestamp = message.get("timestamp")
            if not isinstance(timestamp, str) or not timestamp:
                continue
            try:
                parsed = datetime.fromisoformat(timestamp)
            except ValueError:
                continue
            if latest is None or parsed > latest:
                latest = parsed

        for event in getattr(session, "timeline_events", []) or []:
            timestamp = event.get("timestamp") if isinstance(event, dict) else None
            if not isinstance(timestamp, str) or not timestamp:
                continue
            try:
                parsed = datetime.fromisoformat(timestamp)
            except ValueError:
                continue
            if latest is None or parsed > latest:
                latest = parsed

        if latest is not None:
            return latest.isoformat()
        return fallback

    @staticmethod
    def _sanitize_message_content(content: Any) -> Any:
        """Strip runtime/attachment/knowledge metadata from history-facing content."""
        if isinstance(content, str):
            return ContextBuilder.strip_metadata_prefix(content)
        if isinstance(content, list):
            sanitized_items: list[dict[str, Any]] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                next_item = dict(item)
                if isinstance(next_item.get("text"), str):
                    next_item["text"] = ContextBuilder.strip_metadata_prefix(next_item["text"])
                    if not next_item["text"].strip() and next_item.get("type") == "text":
                        continue
                sanitized_items.append(next_item)
            return sanitized_items
        return content

    @classmethod
    def _serialize_history_message(cls, message: dict[str, Any]) -> dict[str, Any]:
        """Return a UI-facing copy of a stored message with metadata stripped."""
        serialized = dict(message)
        if "content" in serialized:
            serialized["content"] = cls._sanitize_message_content(serialized["content"])
        return serialized

    def _session_display_label(self, session_key: str, session: Any, metadata: dict[str, Any] | None = None) -> str:
        title = getattr(session, "title", None) or (metadata or {}).get("title")
        if title:
            return title
        preview = self._extract_first_message_preview(session)
        return preview or session_key

    def _serialize_session_summary(self, session_id: str, session: Any, summary: dict[str, Any]) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "updated_at": self._session_last_activity_iso(session, summary.get("updated_at")),
            "created_at": session.created_at.isoformat() if session else None,
            "message_count": len(session.messages) if session else 0,
            "first_message": self._extract_first_message_preview(session),
            "title": session.title if session else summary.get("title"),
            "project_id": getattr(session, "project_id", None) or summary.get("project_id"),
        }

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

    def _memory_store(self) -> Any | None:
        consolidator = getattr(self.agent_loop, "memory_consolidator", None)
        return getattr(consolidator, "store", None)

    def _memory_templates_enabled(self) -> bool:
        templates = getattr(load_config(), "templates", None)
        if templates is None:
            return False
        return bool(getattr(templates, "memory_system", None) or getattr(templates, "memory_prompt", None))

    def _summarize_memory_settings(self) -> dict[str, Any]:
        template_enabled = self._memory_templates_enabled()
        return {
            "auto_consolidation": self._memory_store() is not None,
            "template_enabled": template_enabled,
            "editable_long_term": True,
            "summary": (
                "长期记忆会跨会话保留，当前上下文展示正在参与推理的近期内容，近期归档保存已经从主上下文移出的历史片段。"
            ),
        }

    def _build_current_context(self, session_id: str | None) -> dict[str, Any]:
        if not session_id:
            return {
                "session_id": None,
                "session_label": None,
                "items": [],
            }

        session = self.session_manager.get_or_create(session_id)
        visible_messages = session.messages[session.last_consolidated:]
        items: list[dict[str, Any]] = []
        for message in visible_messages:
            content = self._sanitize_message_content(message.get("content"))
            if not isinstance(content, str) or not content.strip():
                continue
            items.append(
                {
                    "role": message.get("role", "unknown"),
                    "content": content,
                    "timestamp": message.get("timestamp"),
                }
            )

        return {
            "session_id": session_id,
            "session_label": self._session_display_label(session_id, session),
            "items": items,
        }

    @staticmethod
    def _archive_item_timestamp(content: str) -> str | None:
        if content.startswith("[") and "]" in content:
            return content[1 : content.index("]")]
        return None

    def _build_archive_items(self, archive_text: str, archive_query: str | None = None) -> dict[str, Any]:
        query = (archive_query or "").strip()
        query_lower = query.lower()
        items = []
        for index, block in enumerate(reversed(split_history_entries(archive_text))):
            if query_lower and query_lower not in block.lower():
                continue
            items.append(
                {
                    "id": f"archive-{index}",
                    "content": block,
                    "timestamp": self._archive_item_timestamp(block),
                }
            )
        return {
            "query": query,
            "total": len(items),
            "items": items,
        }

    def get_memory_overview(self, session_id: str | None = None, archive_query: str | None = None) -> dict[str, Any]:
        """Return Memory Center payload for the current workspace."""
        store = self._memory_store()
        long_term_content = store.read_long_term() if store else ""
        archive_text = store.read_archive() if store else ""
        updated_at = None
        if store and store.memory_file.exists():
            updated_at = datetime.fromtimestamp(store.memory_file.stat().st_mtime).isoformat()
        return {
            "long_term": {
                "content": long_term_content,
                "updated_at": updated_at,
                "character_count": len(long_term_content),
                "editable": True,
            },
            "current_context": self._build_current_context(session_id),
            "archive": self._build_archive_items(archive_text, archive_query),
            "settings": self._summarize_memory_settings(),
        }

    def update_long_term_memory(self, content: str) -> dict[str, Any]:
        """Persist long-term memory content from the Memory Center."""
        store = self._memory_store()
        if store is None:
            raise HTTPException(status_code=503, detail="Memory store is not available")
        normalized = content.rstrip()
        store.write_long_term(normalized)
        updated_at = datetime.fromtimestamp(store.memory_file.stat().st_mtime).isoformat()
        self.audit.record(
            "memory.long_term.updated",
            "success",
            actor="web_user",
            details={"character_count": len(normalized)},
        )
        return {
            "content": normalized,
            "updated_at": updated_at,
            "character_count": len(normalized),
            "editable": True,
        }

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

    def get_knowledge_overview(self) -> dict[str, Any]:
        self._sync_knowledge_config()
        return self.knowledge.get_knowledge_overview()

    def create_knowledge_base(self, name: str, description: str) -> dict[str, Any]:
        self._sync_knowledge_config()
        return self.knowledge.create_knowledge_base(name, description).model_dump()

    def get_knowledge_base_detail(self, knowledge_base_id: str) -> dict[str, Any]:
        self._sync_knowledge_config()
        return self.knowledge.get_knowledge_base_detail(knowledge_base_id)

    def update_knowledge_base(
        self,
        knowledge_base_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
    ) -> Any:
        self._sync_knowledge_config()
        return self.knowledge.update_knowledge_base(
            knowledge_base_id,
            name=name,
            description=description,
            enabled=enabled,
        )

    def delete_knowledge_base(self, knowledge_base_id: str) -> dict[str, Any]:
        self._sync_knowledge_config()
        result = self.knowledge.delete_knowledge_base(knowledge_base_id)
        self.audit.record(
            "knowledge.base.deleted",
            "success",
            actor="web_user",
            details={"knowledge_base_id": knowledge_base_id},
        )
        return result

    def get_session_knowledge_links(self, session_id: str) -> list[str]:
        self._sync_knowledge_config()
        return self.knowledge.get_session_links(session_id)

    def set_session_knowledge_links(self, session_id: str, knowledge_base_ids: list[str]) -> None:
        self._sync_knowledge_config()
        self.knowledge.set_session_links(session_id, knowledge_base_ids)

    async def upload_knowledge_documents(self, knowledge_base_id: str, files: list[Any]) -> dict[str, Any]:
        self._sync_knowledge_config()
        uploaded: list[dict[str, Any]] = []
        temp_dir = self.session_manager.workspace / "tmp-knowledge"
        temp_dir.mkdir(parents=True, exist_ok=True)

        for file in files:
            filename = safe_filename(getattr(file, "filename", "") or "upload.bin")
            temp_path = temp_dir / filename
            temp_path.write_bytes(await file.read())
            document = self.knowledge.register_document_upload(
                knowledge_base_id,
                temp_path,
                getattr(file, "filename", filename),
            )
            uploaded.append(document.model_dump())
            self._schedule_knowledge_task(self._process_knowledge_document(document.id))
            try:
                temp_path.unlink()
            except OSError:
                logger.warning("Failed to remove temporary knowledge upload {}", temp_path)

        return {"documents": uploaded}

    def delete_knowledge_document(self, knowledge_base_id: str, document_id: str) -> dict[str, Any]:
        self._sync_knowledge_config()
        self.knowledge.delete_document(knowledge_base_id, document_id)
        return {
            "success": True,
            "knowledge_base_id": knowledge_base_id,
            "document_id": document_id,
        }

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
            "messages": [self._serialize_history_message(message) for message in session.messages] if session else [],
            "timeline_events": session.timeline_events if session else [],
        }

    async def list_sessions(self) -> list[dict]:
        """List all sessions."""
        result = []
        for summary in self.session_manager.list_sessions():
            if summary.get("project_id"):
                continue
            session_id = summary.get("key", "")
            session = self.session_manager.get_or_create(session_id)
            if getattr(session, "project_id", None):
                continue
            result.append(self._serialize_session_summary(session_id, session, summary))
        return sorted(result, key=lambda item: item.get("updated_at") or "", reverse=True)

    def list_project_sessions(self, project_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for summary in self.session_manager.list_sessions():
            session_id = summary.get("key", "")
            session = self.session_manager.get_or_create(session_id)
            if getattr(session, "project_id", None) != project_id:
                continue
            items.append(self._serialize_session_summary(session_id, session, summary))
        return sorted(items, key=lambda item: item.get("updated_at") or "", reverse=True)

    def list_projects(self) -> dict[str, Any]:
        items = []
        for project in self.projects.list_projects():
            items.append({**project.model_dump(), "session_count": len(self.list_project_sessions(project.id))})
        return {"items": items}

    def create_project(self, name: str) -> dict[str, Any]:
        try:
            project = self.projects.create_project(name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {**project.model_dump(), "session_count": 0}

    def get_project_detail(self, project_id: str) -> dict[str, Any]:
        project = self.projects.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return {
            "project": project.model_dump(),
            "sessions": self.list_project_sessions(project_id),
        }

    def rename_project(self, project_id: str, name: str) -> dict[str, Any]:
        try:
            project = self.projects.rename_project(project_id, name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc
        return {"project": project.model_dump()}

    def create_project_session(self, project_id: str, session_id: str, title: str | None = None) -> dict[str, Any]:
        if self.projects.get_project(project_id) is None:
            raise HTTPException(status_code=404, detail="Project not found")
        session = self.session_manager.get_or_create(session_id)
        session.set_project_id(project_id)
        if title:
            session.set_title(title)
        self.session_manager.save(session)
        return self._serialize_session_summary(
            session_id,
            session,
            {"updated_at": session.updated_at.isoformat()},
        )

    def move_session_to_project(self, project_id: str, session_id: str) -> dict[str, Any]:
        if self.projects.get_project(project_id) is None:
            raise HTTPException(status_code=404, detail="Project not found")
        session = self.session_manager.get_or_create(session_id)
        if session.project_id:
            raise HTTPException(status_code=409, detail="Session already belongs to a project")
        session.set_project_id(project_id)
        self.session_manager.save(session)
        return {
            "session": self._serialize_session_summary(
                session_id,
                session,
                {"updated_at": session.updated_at.isoformat()},
            )
        }

    def _delete_session_now(self, session_id: str, *, audit_event: str = "session.deleted") -> bool:
        self.session_manager.invalidate(session_id)
        session_path = self.session_manager._get_session_path(session_id)
        if session_path.exists():
            session_path.unlink()
        upload_dir = self._session_upload_dir(session_id)
        uploads_removed = upload_dir.exists()
        if upload_dir.exists():
            shutil.rmtree(upload_dir, ignore_errors=True)
        channel, chat_id = (session_id.split(":", 1) if ":" in session_id else ("web", session_id))
        self.audit.record(
            audit_event,
            "success",
            session_key=session_id,
            channel=channel,
            chat_id=chat_id,
            actor="web_user",
            details={"uploads_removed": uploads_removed},
        )
        return True

    def delete_project(self, project_id: str) -> dict[str, Any]:
        project = self.projects.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        session_ids = [item["session_id"] for item in self.list_project_sessions(project_id)]
        for session_id in session_ids:
            self._delete_session_now(session_id, audit_event="project.session.deleted")

        try:
            self.projects.delete_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc

        self.audit.record(
            "project.deleted",
            "success",
            actor="web_user",
            details={
                "project_id": project_id,
                "project_name": project.name,
                "deleted_session_count": len(session_ids),
            },
        )
        return {
            "success": True,
            "project_id": project_id,
            "deleted_session_count": len(session_ids),
        }

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        return self._delete_session_now(session_id)

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
        title="TokenMind Web UI",
        description="Web UI for the TokenMind AI assistant",
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
    app.include_router(knowledge_router)
    app.include_router(memory_router)
    app.include_router(projects_router)
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
