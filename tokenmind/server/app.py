"""FastAPI application for TokenMind Web UI."""

from __future__ import annotations

import asyncio
import hmac
import mimetypes
import shutil
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from tokenmind.agent.context import ContextBuilder
from tokenmind.agent.memory import split_history_entries
from tokenmind.audit import AuditLogger
from tokenmind.bus.events import InboundMessage
from tokenmind.bus.queue import MessageBus
from tokenmind.config.loader import load_config
from tokenmind.config.schema import KnowledgeConfig, UploadsConfig
from tokenmind.creative.music_generation import MusicGenerationService
from tokenmind.creative.tts import SYSTEM_VOICES, TtsService
from tokenmind.creative.voice_clone import VoiceCloneService
from tokenmind.creative.voice_clone_store import VoiceCloneRecord, VoiceCloneStore
from tokenmind.creative.voice_design import VoiceDesignService
from tokenmind.knowledge import KnowledgeService
from tokenmind.projects import ProjectStore
from tokenmind.server.attachments import AttachmentStore, categorize_attachment
from tokenmind.server.channel.web import WebChannel
from tokenmind.server.dependencies import (
    set_app,
    set_chat_service,
    set_connection_manager,
    set_cron_service,
    set_inbound_queue,
    set_usage_recorder,
)
from tokenmind.server.frontend import (
    register_frontend_routes,
    register_missing_frontend_routes,
    resolve_frontend_dist_dir,
)
from tokenmind.server.routes import (
    assets_router,
    browser_router,
    chat_router,
    config_router,
    creative_router,
    cron_router,
    knowledge_router,
    memory_router,
    projects_router,
    sessions_router,
    skills_router,
    status_router,
    storage_router,
    updates_router,
    usage_router,
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
        # Share the single KnowledgeService owned by AgentLoop so HTTP-side
        # uploads (which trigger wiki LLM compilation) and chat-side wiki tools
        # see the same instance — and so set_wiki_llm() that AgentLoop already
        # called actually applies to the upload path.
        knowledge_service = getattr(agent_loop, "knowledge", None)
        if knowledge_service is None:
            knowledge = self._load_knowledge_config()
            knowledge_service = KnowledgeService(
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
                vlm_model=knowledge.vlm_model,
                vlm_api_key=knowledge.vlm_api_key,
                vlm_api_base=knowledge.vlm_api_base,
                vlm_timeout=knowledge.vlm_timeout,
                vlm_max_dim=knowledge.vlm_max_dim,
                vlm_max_workers=knowledge.vlm_max_workers,
            )
        self.knowledge = knowledge_service
        self.projects = ProjectStore(session_manager.workspace)
        self.audit = AuditLogger(session_manager.workspace)
        self.attachments = AttachmentStore(session_manager.workspace)
        self.voice_clones = VoiceCloneStore(session_manager.workspace)
        self._response_futures: dict[str, asyncio.Future] = {}
        self._last_upload_cleanup_at: datetime | None = None
        self._knowledge_tasks: set[asyncio.Task[Any]] = set()
        # Per-KB serialization for wiki compile. Different KBs can compile in
        # parallel; within one KB the queue is strictly serial so an LLM
        # compiling document N sees the entity/topic titles that compile N-1
        # just wrote to disk. Used by _process_knowledge_document.
        self._kb_compile_locks: dict[str, asyncio.Lock] = {}

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
            vlm_model=config.vlm_model,
            vlm_api_key=config.vlm_api_key,
            vlm_api_base=config.vlm_api_base,
            vlm_timeout=config.vlm_timeout,
            vlm_max_dim=config.vlm_max_dim,
            vlm_max_workers=config.vlm_max_workers,
        )

    def _schedule_knowledge_task(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._knowledge_tasks.add(task)
        task.add_done_callback(self._knowledge_tasks.discard)

    async def _process_knowledge_document(self, document_id: str) -> None:
        try:
            kb_id = self._lookup_document_kb_id(document_id)
            if kb_id and self._document_kb_is_wiki(kb_id):
                lock = self._kb_compile_locks.setdefault(kb_id, asyncio.Lock())
                async with lock:
                    await asyncio.to_thread(self.knowledge.process_document, document_id)
            else:
                await asyncio.to_thread(self.knowledge.process_document, document_id)
        except Exception:
            logger.exception("Failed background processing for knowledge document {}", document_id)

    def _lookup_document_kb_id(self, document_id: str) -> str | None:
        try:
            for item in self.knowledge._state["documents"]:  # type: ignore[attr-defined]
                if item.get("id") == document_id:
                    return str(item.get("knowledge_base_id") or "")
        except Exception:
            return None
        return None

    def _document_kb_is_wiki(self, kb_id: str) -> bool:
        try:
            kb = self.knowledge.get_knowledge_base(kb_id)
            return kb.type == "wiki"
        except Exception:
            return False

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

    # OS-specific files we should never surface to the user as "uploads":
    # macOS Finder metadata + Windows Explorer thumbnail caches.
    _UPLOAD_IGNORED_NAMES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini", "ehthumbs.db"})

    @classmethod
    def _is_ignored_upload_path(cls, path: Path) -> bool:
        if path.name in cls._UPLOAD_IGNORED_NAMES:
            return True
        # Any dotfile (or file inside a dot-named directory) is system noise
        # in the context of user-visible uploads.
        return any(part.startswith(".") for part in path.parts)

    def _iter_upload_files(self) -> list[Path]:
        uploads_root = self.uploads_dir
        if not uploads_root.exists():
            return []
        return [
            path
            for path in uploads_root.rglob("*")
            if path.is_file() and not self._is_ignored_upload_path(path.relative_to(uploads_root))
        ]

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
        managed_paths = self.attachments.managed_paths()
        cutoff = now - policy["retention"]

        for path in self._iter_upload_files():
            try:
                resolved = str(path.resolve())
                modified_at = datetime.fromtimestamp(path.stat().st_mtime)
            except OSError:
                continue
            if resolved in managed_paths:
                continue
            if resolved in referenced or modified_at >= cutoff:
                continue
            try:
                path.unlink()
                deleted_files += 1
            except OSError:
                logger.warning("Failed to delete stale upload file {}", path)

        attachment_cleanup = self.attachments.expire_stale(cutoff)
        deleted_files += int(attachment_cleanup.get("deleted_files", 0))

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
        return categorize_attachment(filename, mime_type)

    def create_generated_attachment(
        self,
        session_id: str,
        *,
        filename: str,
        content: str | bytes,
        mime_type: str | None = None,
        message_id: str | None = None,
        preview_text: str | None = None,
    ) -> dict[str, Any]:
        return self.attachments.create_generated(
            session_id,
            filename=filename,
            content=content,
            mime_type=mime_type,
            retention=self._upload_policy()["retention"],
            message_id=message_id,
            preview_text=preview_text,
        )

    def create_local_attachment(
        self,
        session_id: str,
        *,
        source_path: str | Path,
        message_id: str | None = None,
        attachment_name: str | None = None,
    ) -> dict[str, Any]:
        return self.attachments.create_local(
            session_id,
            source_path=source_path,
            retention=self._upload_policy()["retention"],
            message_id=message_id,
            attachment_name=attachment_name,
        )

    def create_remote_attachment(
        self,
        session_id: str,
        *,
        source_url: str,
        message_id: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        return self.attachments.create_remote(
            session_id,
            source_url=source_url,
            retention=self._upload_policy()["retention"],
            message_id=message_id,
            filename=filename,
        )

    def get_attachment_record(self, attachment_id: str) -> dict[str, Any] | None:
        return self.attachments.get_record(attachment_id)

    def resolve_attachment(self, attachment_id: str) -> dict[str, Any]:
        return self.attachments.resolve(attachment_id).to_dict()

    def retain_attachment(self, attachment_id: str) -> dict[str, Any]:
        return self.attachments.retain(attachment_id)

    async def generate_music(
        self,
        *,
        prompt: str,
        lyrics: str | None = None,
        lyrics_optimizer: bool = False,
        is_instrumental: bool = False,
        count: int = 1,
        reference_audio_base64: str | None = None,
        reference_audio_name: str | None = None,
    ) -> dict[str, Any]:
        """Generate music through the configured creative music capability."""
        config = load_config()
        has_reference_audio = bool((reference_audio_base64 or "").strip())
        capability = config.creative.music_cover if has_reference_audio else config.creative.music
        if not MusicGenerationService.is_configured(capability):
            if has_reference_audio:
                raise ValueError("Music cover generation is not configured or enabled")
            raise ValueError("Music generation is not configured or enabled")

        service = MusicGenerationService(capability)
        normalized_count = max(1, min(4, int(count or 1)))
        attachments: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []

        for _ in range(normalized_count):
            result = await service.generate(
                prompt=prompt,
                lyrics=lyrics,
                lyrics_optimizer=lyrics_optimizer,
                is_instrumental=is_instrumental,
                reference_audio_base64=reference_audio_base64,
            )
            attachment = self.create_generated_attachment(
                "creative:music",
                filename=result.filename,
                content=result.data,
                mime_type=result.mime_type,
                message_id="creative-music",
            )
            attachments.append(attachment)
            results.append(
                {
                    "filename": result.filename,
                    "mime_type": result.mime_type,
                    "model": result.model,
                    "provider": result.provider,
                    "duration_ms": result.duration_ms,
                    "trace_id": result.trace_id,
                    "reference_audio_name": reference_audio_name,
                }
            )

        if not attachments or not results:
            raise RuntimeError("Music generation returned no results")

        return {
            "attachment": attachments[0],
            "result": results[0],
            "attachments": attachments,
            "results": results,
        }

    async def upload_voice_clone_audio(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        content_type: str | None,
    ) -> dict[str, Any]:
        """Upload a clone source audio sample through the configured voice_clone capability."""
        config = load_config()
        capability = config.creative.voice_clone
        if not VoiceCloneService.is_configured(capability):
            raise ValueError("Voice clone capability is not configured or enabled")

        service = VoiceCloneService(capability)
        uploaded = await service.upload_audio(
            audio_bytes=audio_bytes,
            filename=filename,
            content_type=content_type,
        )
        return {
            "file_id": uploaded.file_id,
            "filename": uploaded.filename,
            "bytes": uploaded.bytes,
            "created_at": uploaded.created_at,
        }

    async def create_voice_clone(
        self,
        *,
        file_id: int,
        voice_id: str | None,
        preview_text: str | None,
        need_noise_reduction: bool,
        need_volume_normalization: bool,
        language_boost: str | None,
        source_filename: str | None = None,
    ) -> dict[str, Any]:
        """Clone a voice, archive the demo audio locally, and persist a record."""
        config = load_config()
        capability = config.creative.voice_clone
        if not VoiceCloneService.is_configured(capability):
            raise ValueError("Voice clone capability is not configured or enabled")

        service = VoiceCloneService(capability)
        result = await service.clone_voice(
            file_id=file_id,
            voice_id=voice_id,
            preview_text=preview_text,
            need_noise_reduction=need_noise_reduction,
            need_volume_normalization=need_volume_normalization,
            language_boost=language_boost,
        )

        demo_attachment_id: str | None = None
        if result.demo_audio_url:
            try:
                audio_bytes, mime_type = await service.download_demo_audio(result.demo_audio_url)
                ext = "mp3" if mime_type.endswith("mpeg") else mime_type.split("/")[-1]
                filename = f"voice-demo-{result.voice_id}.{ext}"
                attachment = self.create_generated_attachment(
                    "creative:voice_clone",
                    filename=filename,
                    content=audio_bytes,
                    mime_type=mime_type,
                    message_id=f"voice-clone-{result.voice_id}",
                    preview_text=preview_text,
                )
                retained = self.retain_attachment(attachment["id"])
                demo_attachment_id = retained.get("id") or attachment["id"]
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to archive voice clone demo audio for voice_id {}",
                    result.voice_id,
                )

        record = VoiceCloneRecord(
            voice_id=result.voice_id,
            model=result.model,
            provider=result.provider,
            created_at=datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            preview_text=(preview_text or "").strip() or None,
            source_filename=source_filename,
            demo_audio_url=result.demo_audio_url,
            demo_attachment_id=demo_attachment_id,
            last_kept_alive_at=None,
        )
        self.voice_clones.upsert(record)

        return {
            **record.to_dict(),
            "input_sensitive": result.input_sensitive,
            "input_sensitive_type": result.input_sensitive_type,
            "trace_id": result.trace_id,
        }

    async def design_voice(
        self,
        *,
        prompt: str,
        preview_text: str,
        voice_id: str | None = None,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        """Design a new voice from a text prompt and persist the generated audio."""
        config = load_config()
        capability = config.creative.voice_design
        # Fall back to voice_clone / tts capability so users with one MiniMax key
        # don't have to duplicate their credentials across entries.
        if not VoiceDesignService.is_configured(capability):
            capability = config.creative.voice_clone
        if not VoiceDesignService.is_configured(capability):
            capability = config.creative.tts
        if not VoiceDesignService.is_configured(capability):
            raise ValueError("Voice design is not configured or enabled")

        service = VoiceDesignService(capability)
        result = await service.design_voice(
            prompt=prompt,
            preview_text=preview_text,
            voice_id=voice_id,
        )

        attachment = self.create_generated_attachment(
            "creative:voice_design",
            filename=f"voice-design-{result.voice_id}.mp3",
            content=result.trial_audio,
            mime_type=result.mime_type,
            message_id=f"voice-design-{result.voice_id}",
            preview_text=preview_text,
        )
        retained = self.retain_attachment(attachment["id"])
        demo_attachment_id = retained.get("id") or attachment["id"]

        record = VoiceCloneRecord(
            voice_id=result.voice_id,
            model=result.model,
            provider=result.provider,
            created_at=datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            preview_text=preview_text.strip() or None,
            source_filename=None,
            demo_audio_url=None,
            demo_attachment_id=demo_attachment_id,
            last_kept_alive_at=None,
            source="design",
            display_name=(display_name or "").strip() or None,
            notes=prompt.strip() or None,
        )
        self.voice_clones.upsert(record)

        return {
            **record.to_dict(),
            "trace_id": result.trace_id,
        }

    def list_voice_clones(self) -> list[dict[str, Any]]:
        """List all persisted voice clone records."""
        return [record.to_dict() for record in self.voice_clones.list()]

    def delete_voice_clone(self, voice_id: str) -> dict[str, Any] | None:
        """Delete a local voice clone record (and its demo attachment if present)."""
        record = self.voice_clones.get(voice_id)
        if record is None:
            return None
        if record.demo_attachment_id:
            try:
                existing = self.attachments.get_record(record.demo_attachment_id)
                if existing is not None:
                    self.attachments.mark_expired(record.demo_attachment_id)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to expire demo attachment {} for voice_id {}",
                    record.demo_attachment_id,
                    voice_id,
                )
        self.voice_clones.delete(voice_id)
        return record.to_dict()

    async def synthesize_voice(
        self,
        *,
        text: str,
        voice_id: str,
        model: str | None = None,
        speed: float = 1.0,
        volume: float = 1.0,
        pitch: int = 0,
        emotion: str | None = None,
    ) -> dict[str, Any]:
        """Synthesize ``text`` with ``voice_id`` and persist the audio as an attachment."""
        config = load_config()
        capability = config.creative.tts
        # Fall back to the voice_clone capability so users who only configured one
        # MiniMax key can still do TTS without setting the same key twice.
        if not TtsService.is_configured(capability):
            capability = config.creative.voice_clone
        if not TtsService.is_configured(capability):
            raise ValueError("Voice synthesis is not configured or enabled")

        service = TtsService(capability)
        result = await service.synthesize(
            text=text,
            voice_id=voice_id,
            model=model,
            speed=speed,
            volume=volume,
            pitch=pitch,
            emotion=emotion,
        )
        attachment = self.create_generated_attachment(
            "creative:tts",
            filename=result.filename,
            content=result.data,
            mime_type=result.mime_type,
            message_id=f"tts-{result.voice_id}",
            preview_text=text.strip()[:500],
        )
        retained = self.retain_attachment(attachment["id"])
        attachment_id = retained.get("id") or attachment["id"]

        return {
            "voice_id": result.voice_id,
            "model": result.model,
            "provider": result.provider,
            "filename": result.filename,
            "mime_type": result.mime_type,
            "usage_characters": result.usage_characters,
            "trace_id": result.trace_id,
            "attachment_id": attachment_id,
            "attachment": retained,
        }

    def list_tts_voices(self) -> dict[str, list[dict[str, Any]]]:
        """Aggregate cloned voices and built-in system voices for the TTS picker."""
        cloned: list[dict[str, Any]] = []
        for record in self.voice_clones.list():
            payload = record.to_dict()
            payload["kind"] = "cloned"
            payload["label"] = record.voice_id
            cloned.append(payload)
        system: list[dict[str, Any]] = [
            {
                "kind": "system",
                "voice_id": voice.voice_id,
                "label": voice.label,
                "gender": voice.gender,
                "description": voice.description,
            }
            for voice in SYSTEM_VOICES
        ]
        return {"cloned": cloned, "system": system}

    async def keep_alive_voice_clone(self, voice_id: str) -> dict[str, Any]:
        """Call MiniMax TTS with a short text to reset the 7-day inactivity timer."""
        config = load_config()
        capability = config.creative.voice_clone
        if not VoiceCloneService.is_configured(capability):
            raise ValueError("Voice clone capability is not configured or enabled")

        record = self.voice_clones.get(voice_id)
        if record is None:
            raise ValueError(f"Voice clone '{voice_id}' not found")

        service = VoiceCloneService(capability)
        await service.keep_alive_voice(voice_id=voice_id)
        updated = self.voice_clones.mark_kept_alive(voice_id)
        return updated.to_dict()

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

        attachments: list[dict[str, Any]] = []
        for item in pending_uploads:
            attachment_ref, destination = self.attachments.create_user_upload(
                session_id,
                filename=item["filename"],
                content=item["content"],
                mime_type=item["mime_type"],
                retention=policy["retention"],
            )
            attachments.append(
                {
                    **attachment_ref,
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
        managed_paths = self.attachments.managed_paths()
        files: list[dict[str, Any]] = []
        for path in sorted(self._iter_upload_files(), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                stats = path.stat()
                resolved = str(path.resolve())
            except OSError:
                continue
            if resolved in managed_paths:
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

    def create_knowledge_base(
        self,
        name: str,
        description: str,
        *,
        type: str = "rag",
        language: str = "zh",
    ) -> dict[str, Any]:
        self._sync_knowledge_config()
        return self.knowledge.create_knowledge_base(
            name, description, type=type, language=language
        ).model_dump()

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
        result = self.knowledge.delete_knowledge_base(
            knowledge_base_id, session_manager=self.session_manager
        )
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

    def get_wiki_graph(self, kb_id: str) -> dict[str, Any]:
        import json
        self._sync_knowledge_config()
        kb = self.knowledge.get_knowledge_base(kb_id)
        if kb.type != "wiki":
            raise ValueError("graph is only available for wiki kbs")
        p = Path(kb.root_path) / "graph-data.json"
        if not p.is_file():
            return {"nodes": [], "edges": [], "updated_at": None}
        return json.loads(p.read_text(encoding="utf-8"))

    def rebuild_wiki_graph(self, kb_id: str) -> dict[str, Any]:
        from tokenmind.knowledge.wiki_graph import build_graph_data
        self._sync_knowledge_config()
        kb = self.knowledge.get_knowledge_base(kb_id)
        if kb.type != "wiki":
            raise ValueError("graph is only available for wiki kbs")
        result = build_graph_data(Path(kb.root_path), persist=True)
        self.knowledge.refresh_knowledge_base_counts(kb_id)
        return result

    async def add_url_source(
        self, knowledge_base_id: str, url: str
    ) -> dict[str, Any]:
        """Fetch a URL (currently: WeChat 公众号) and register it as a
        wiki source. Schedules the same compile pipeline as a file upload."""
        self._sync_knowledge_config()
        document = await asyncio.to_thread(
            self.knowledge.register_url_source, knowledge_base_id, url
        )
        self._schedule_knowledge_task(self._process_knowledge_document(document.id))
        return {"document": document.model_dump()}

    async def recompile_wiki_sources(self, kb_id: str) -> dict[str, Any]:
        """Re-run the wiki ingest pipeline (including LLM compile) for every
        source document already registered in this KB. Runs each document in a
        worker thread because process_document is sync and may itself spin up
        a fresh asyncio loop for the LLM call."""
        self._sync_knowledge_config()
        kb = self.knowledge.get_knowledge_base(kb_id)
        if kb.type != "wiki":
            raise ValueError("recompile is only available for wiki kbs")
        documents = self.knowledge.list_documents(kb_id)
        results: list[dict[str, Any]] = []
        for doc in documents:
            try:
                # Recompile always bypasses the SHA cache gate — that's the
                # whole point of clicking "recompile".
                await asyncio.to_thread(self.knowledge.process_document, doc.id, force=True)
                results.append({"document_id": doc.id, "status": "ok"})
            except Exception as exc:
                logger.exception("recompile failed for document {}", doc.id)
                results.append({"document_id": doc.id, "status": "failed", "error": str(exc)})
        return {"processed": len(results), "results": results}

    def list_wiki_pages(self, kb_id: str) -> list[dict[str, Any]]:
        from tokenmind.knowledge.wiki_query import scan_pages
        self._sync_knowledge_config()
        kb = self.knowledge.get_knowledge_base(kb_id)
        if kb.type != "wiki":
            raise ValueError("pages endpoint is only for wiki kbs")
        pages = scan_pages(Path(kb.root_path))
        return [{"title": p["title"], "type": p["type"], "path": p["path"]} for p in pages]

    def read_wiki_page(self, kb_id: str, page_path: str) -> dict[str, Any]:
        from tokenmind.knowledge.wiki_query import read_wiki_page
        self._sync_knowledge_config()
        kb = self.knowledge.get_knowledge_base(kb_id)
        if kb.type != "wiki":
            raise ValueError("page read is only available for wiki kbs")
        return read_wiki_page(Path(kb.root_path), page_path)

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
        compaction_threshold = int(getattr(self.agent_loop, "context_window_tokens", 0) or 0)
        return {
            "messages": [self._serialize_history_message_for_ui(message) for message in session.messages] if session else [],
            "timeline_events": session.timeline_events if session else [],
            "consolidated_offset": session.last_consolidated if session else 0,
            "personality": session.personality if session else None,
            "plan_mode": session.plan_mode if session else False,
            "compaction_threshold_tokens": compaction_threshold,
            "last_prompt_tokens": session.last_prompt_tokens if session else None,
            "last_prompt_at": session.last_prompt_at if session else None,
            "last_prompt_model": session.last_prompt_model if session else None,
        }

    async def compact_session(self, session_id: str) -> dict:
        """Force-compact the session into HISTORY.md/MEMORY.md.

        Returns the new ``consolidated_offset`` so the frontend can fold
        the archived portion of the chat. Also publishes a
        ``_session_compacted`` outbound message so other WS subscribers
        (e.g. additional tabs) re-render.
        """
        from tokenmind.bus.events import OutboundMessage

        consolidator = getattr(self.agent_loop, "memory_consolidator", None)
        if consolidator is None:
            raise HTTPException(status_code=503, detail="memory consolidator unavailable")
        session = self.session_manager.get_or_create(session_id)
        previous_offset, new_offset = await consolidator.force_consolidate(session)
        messages_compacted = max(0, new_offset - previous_offset)
        channel, chat_id = (
            session_id.split(":", 1) if ":" in session_id else ("web", session_id)
        )
        if messages_compacted > 0:
            try:
                await self.bus.publish_outbound(
                    OutboundMessage(
                        channel=channel,
                        chat_id=session_id,
                        content="",
                        metadata={
                            "_session_compacted": True,
                            "_session_id": session_id,
                            "_consolidated_offset": new_offset,
                            "_messages_compacted": messages_compacted,
                        },
                    )
                )
            except Exception:
                logger.exception("Failed to publish session_compacted frame for %s", session_id)
        return {
            "session_id": session_id,
            "previous_offset": previous_offset,
            "consolidated_offset": new_offset,
            "messages_compacted": messages_compacted,
        }

    def _serialize_history_message_for_ui(self, message: dict[str, Any]) -> dict[str, Any]:
        serialized = self._serialize_history_message(message)
        attachments = serialized.get("attachments")
        if isinstance(attachments, list):
            serialized["attachments"] = self.attachments.hydrate_refs(attachments)
        return serialized

    async def list_sessions(self) -> list[dict]:
        """List all sessions, including ones that belong to a project.

        Project sessions carry their ``project_id`` in the serialized summary
        so the web UI can surface them in the global recent list and still
        open them inside their project workspace.
        """
        result = []
        for summary in self.session_manager.list_sessions():
            session_id = summary.get("key", "")
            session = self.session_manager.get_or_create(session_id)
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
        knowledge_base: dict[str, Any] | None = None
        documents: list[dict[str, Any]] = []
        if project.knowledge_base_id:
            try:
                detail = self.get_knowledge_base_detail(project.knowledge_base_id)
                knowledge_base = detail.get("knowledge_base")
                documents = detail.get("documents", [])
            except KeyError:
                # Stored KB was deleted out from under the project — treat as
                # having no KB; a fresh one is created on the next upload.
                knowledge_base = None
        return {
            "project": project.model_dump(),
            "sessions": self.list_project_sessions(project_id),
            "knowledge_base": knowledge_base,
            "documents": documents,
        }

    def ensure_project_wiki(self, project_id: str) -> str:
        """Return the project's wiki KB id, lazily creating it on first use.

        Recreates the KB if the project's stored id points to a base that no
        longer exists.
        """
        project = self.projects.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if project.knowledge_base_id:
            try:
                self.knowledge.get_knowledge_base(project.knowledge_base_id)
                return project.knowledge_base_id
            except KeyError:
                pass  # stored KB gone; fall through and recreate
        self._sync_knowledge_config()
        kb = self.knowledge.create_knowledge_base(
            f"项目：{project.name}",
            f"项目「{project.name}」的知识库",
            type="wiki",
            project_id=project_id,
        )
        self.projects.update_project(project_id, knowledge_base_id=kb.id)
        return kb.id

    def update_project_instructions(self, project_id: str, instructions: str) -> dict[str, Any]:
        try:
            project = self.projects.update_project(project_id, instructions=instructions)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc
        return {"project": project.model_dump()}

    async def upload_project_documents(self, project_id: str, files: list[Any]) -> dict[str, Any]:
        kb_id = self.ensure_project_wiki(project_id)
        return await self.upload_knowledge_documents(kb_id, files)

    async def add_project_url_source(self, project_id: str, url: str) -> dict[str, Any]:
        kb_id = self.ensure_project_wiki(project_id)
        return await self.add_url_source(kb_id, url)

    def list_project_documents(self, project_id: str) -> dict[str, Any]:
        project = self.projects.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if not project.knowledge_base_id:
            return {"documents": []}
        try:
            return {"documents": self.get_knowledge_base_detail(project.knowledge_base_id).get("documents", [])}
        except KeyError:
            return {"documents": []}

    def delete_project_document(self, project_id: str, document_id: str) -> dict[str, Any]:
        project = self.projects.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if not project.knowledge_base_id:
            raise HTTPException(status_code=404, detail="Project has no knowledge base")
        return self.delete_knowledge_document(project.knowledge_base_id, document_id)

    async def recompile_project_wiki(self, project_id: str) -> dict[str, Any]:
        project = self.projects.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if not project.knowledge_base_id:
            raise HTTPException(status_code=400, detail="Project has no knowledge base yet")
        return await self.recompile_wiki_sources(project.knowledge_base_id)

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
        # Drop the per-session read tracker so its ReadState entries don't
        # accumulate indefinitely (~500 bytes each, no cleanup elsewhere).
        file_states = getattr(self.agent_loop, "file_states", None)
        if file_states is not None:
            file_states.clear_session(session_id)
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

        # Remove the project's owned wiki KB so it doesn't linger orphaned.
        if project.knowledge_base_id:
            try:
                self.knowledge.delete_knowledge_base(
                    project.knowledge_base_id, session_manager=self.session_manager
                )
            except KeyError:
                pass

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

    async def delete_message(self, session_id: str, timestamp: str) -> bool:
        """Remove a single message from a session (and connected tool scaffolding)."""
        session = self.session_manager.get_or_create(session_id)
        if not session.delete_message(timestamp):
            return False
        self.session_manager.save(session)
        channel, chat_id = (session_id.split(":", 1) if ":" in session_id else ("web", session_id))
        self.audit.record(
            "session.message.deleted",
            "success",
            session_key=session_id,
            channel=channel,
            chat_id=chat_id,
            actor="web_user",
            details={"timestamp": timestamp},
        )
        return True

    async def clear_history(self, session_id: str) -> bool:
        """Clear history for a session."""
        session = self.session_manager.get_or_create(session_id)
        if session:
            session.clear()
            self.session_manager.save(session)
            # History cleared = the agent should re-read any files it
            # previously knew about; the surviving session_key would
            # otherwise let edit_file proceed without a fresh read.
            file_states = getattr(self.agent_loop, "file_states", None)
            if file_states is not None:
                file_states.clear_session(session_id)
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

    def patch_session(self, session_id: str, updates: dict) -> dict:
        """Partially update session attributes.

        Supported keys:
          - ``active_wiki_kb_id``: must reference a wiki-type KB (or ``None``
            to clear). When switching between active wikis the previous KB's
            name is recorded in ``session.metadata['_previous_wiki_kb_name']``.
          - ``personality``: ``"warm"`` / ``"pragmatic"`` / ``None``. Drives
            the reply-style section ContextBuilder injects into the system prompt.
          - ``plan_mode``: ``True`` / ``False`` / ``None``. When enabled, the agent
            must call ``task_list`` before multi-step work.
        """
        session = self.session_manager.get_or_create(session_id)
        dirty = False
        if "active_wiki_kb_id" in updates:
            new_kb_id = updates["active_wiki_kb_id"]
            if new_kb_id is not None:
                kb = self.knowledge.get_knowledge_base(new_kb_id)
                if kb.type != "wiki":
                    raise ValueError("active_wiki_kb_id must reference a wiki kb")
                previous = session.active_wiki_kb_id
                if previous and previous != new_kb_id:
                    try:
                        prev_kb = self.knowledge.get_knowledge_base(previous)
                        session.metadata["_previous_wiki_kb_name"] = prev_kb.name
                    except KeyError:
                        pass
            session.set_active_wiki_kb_id(new_kb_id)
            dirty = True
        if "personality" in updates:
            value = updates["personality"]
            if value is not None and value not in ("warm", "pragmatic"):
                raise ValueError("personality must be 'warm', 'pragmatic', or null")
            session.set_personality(value)
            dirty = True
        if "plan_mode" in updates:
            session.set_plan_mode(bool(updates["plan_mode"]))
            dirty = True
        if dirty:
            self.session_manager.save(session)
        return {
            "session_id": session_id,
            "active_wiki_kb_id": session.active_wiki_kb_id,
            "personality": session.personality,
            "plan_mode": session.plan_mode,
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
    try:
        yield
    finally:
        # Force-close any lingering WebSocket connections so uvicorn doesn't
        # block on "Waiting for background tasks to complete" when the user
        # left a browser tab open.
        manager = getattr(app.state, "connection_manager", None)
        if manager is not None:
            try:
                await manager.close_all()
            except Exception:
                logger.exception("Failed to close WebSocket connections during shutdown")


def _consteq(provided: str, expected: str) -> bool:
    """Constant-time string comparison so the LAN gate can't be timing-probed."""
    return bool(expected) and hmac.compare_digest(provided, expected)


def create_app(
    bus: MessageBus,
    agent_loop: Any,
    session_manager: Any,
    connection_manager: ConnectionManager,
    web_channel: WebChannel,
    auth_secret: str = "",
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
    set_usage_recorder(getattr(agent_loop, "usage_recorder", None))

    from tokenmind.server.dependencies import set_opencli_service, set_site_registry

    set_opencli_service(getattr(agent_loop, "opencli_service", None))
    set_site_registry(getattr(agent_loop, "site_registry", None))

    # Create FastAPI app
    app = FastAPI(
        title="TokenMind Web UI",
        description="Web UI for the TokenMind AI assistant",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.chat_service = chat_service
    app.state.connection_manager = connection_manager
    app.state.auth_secret = auth_secret or ""
    set_app(app)

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # LAN access gate: when an auth_secret is configured, every non-localhost
    # request (including LAN devices like a phone on the same Wi-Fi) must
    # present it as ``X-TokenMind-Secret`` or ``?secret=...``. Localhost calls
    # bypass entirely so the user never needs to enter the secret on the
    # machine that runs the server.
    @app.middleware("http")
    async def _lan_auth_gate(request, call_next):
        secret = (getattr(app.state, "auth_secret", "") or "").strip()
        if not secret:
            return await call_next(request)
        client_host = ""
        if request.client is not None:
            client_host = (request.client.host or "").strip()
        if client_host in {"127.0.0.1", "::1", "localhost"}:
            return await call_next(request)
        # Allow the verify endpoint itself so the frontend can prompt the
        # user for the secret without being blocked.
        if request.url.path == "/api/auth/verify":
            return await call_next(request)
        # Allow the static frontend HTML/JS/CSS so users can at least load
        # the page and see the auth prompt; data endpoints are gated.
        path = request.url.path
        is_api = path.startswith("/api") or path.startswith("/ws")
        if not is_api:
            return await call_next(request)
        provided = (
            request.headers.get("X-TokenMind-Secret")
            or request.query_params.get("secret")
            or ""
        )
        if not _consteq(provided, secret):
            from fastapi.responses import JSONResponse

            return JSONResponse(
                {"detail": "LAN 访问需要密钥，请在前端输入访问密钥"},
                status_code=401,
            )
        return await call_next(request)

    # Include routers
    app.include_router(assets_router)
    app.include_router(browser_router)
    app.include_router(chat_router)
    app.include_router(config_router)
    app.include_router(creative_router)
    app.include_router(cron_router)
    app.include_router(knowledge_router)
    app.include_router(memory_router)
    app.include_router(projects_router)
    app.include_router(sessions_router)
    app.include_router(skills_router)
    app.include_router(status_router)
    app.include_router(storage_router)
    app.include_router(updates_router)
    app.include_router(usage_router)

    # Lightweight auth probe: the frontend hits this with the secret the
    # user pastes into the AuthGate. Always returns 200 with whether the
    # provided secret matches (the LAN middleware above also gates it
    # against unauthenticated callers when configured, but we additionally
    # let the call through so the prompt can verify on the same request).
    #
    # Localhost callers are reported as ``required: False`` even when a
    # secret is configured: the HTTP middleware already lets them through,
    # so making the user-on-the-server-machine paste a password would be
    # purely friction.
    @app.post("/api/auth/verify")
    async def _api_auth_verify(payload: dict, request: Request):
        secret = (getattr(app.state, "auth_secret", "") or "").strip()
        if not secret:
            return {"required": False, "ok": True}
        client_host = ""
        if request.client is not None:
            client_host = (request.client.host or "").strip()
        if client_host in {"127.0.0.1", "::1", "localhost"}:
            return {"required": False, "ok": True}
        provided = (payload or {}).get("secret", "")
        if not isinstance(provided, str):
            provided = ""
        return {"required": True, "ok": _consteq(provided, secret)}

    # WebSocket endpoint
    @app.websocket("/ws/chat")
    async def ws_chat(websocket: WebSocket, session_id: str | None = None):
        """WebSocket endpoint for real-time chat."""
        # LAN auth gate — same as the HTTP middleware. WS doesn't go through
        # FastAPI middleware so we enforce it inline before accepting the
        # handshake. Browsers can't set custom headers on the WebSocket
        # constructor, so we accept the secret via ``?secret=...`` query.
        secret = (getattr(app.state, "auth_secret", "") or "").strip()
        if secret:
            client_host = ""
            if websocket.client is not None:
                client_host = (websocket.client.host or "").strip()
            if client_host not in {"127.0.0.1", "::1", "localhost"}:
                provided = websocket.query_params.get("secret") or ""
                if not _consteq(provided, secret):
                    await websocket.close(code=4401, reason="LAN auth required")
                    return

        if session_id is None:
            # Generate a random session ID for anonymous users
            import uuid
            session_id = f"web:{uuid.uuid4().hex[:12]}"

        await websocket_handler(
            websocket=websocket,
            session_key=session_id,
            connection_manager=connection_manager,
            inbound_queue=bus.inbound,
            uploads_root=chat_service.attachments.uploads_root,
        )

    # Set WebChannel's ws manager
    web_channel.set_ws_manager(connection_manager)

    frontend_dir = resolve_frontend_dist_dir()
    if frontend_dir is not None:
        register_frontend_routes(app, frontend_dir)
    else:
        logger.warning(
            "TokenMind Web UI bundle not found. Source checkouts must run "
            "`cd frontend && npm install && npm run build` before opening the backend port, "
            "or use `npm run dev` and open http://localhost:5173."
        )
        register_missing_frontend_routes(app)

    # Return app without starting dispatcher - it will be started via lifespan
    return app
