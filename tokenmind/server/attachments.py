"""Attachment storage helpers for web chat messages."""

from __future__ import annotations

import json
import mimetypes
import secrets
import shutil
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

from fastapi import HTTPException

from tokenmind.utils.helpers import safe_filename

AttachmentDownloader = Callable[[str], tuple[bytes, str | None]]


def categorize_attachment(filename: str, mime_type: str | None) -> tuple[str, bool]:
    """Return a coarse attachment category and whether it is an image."""
    suffix = Path(filename).suffix.lower()
    mime = (mime_type or "").lower()
    if mime.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}:
        return "image", True
    if mime.startswith("video/") or suffix in {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}:
        return "video", False
    if mime.startswith("audio/") or suffix in {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}:
        return "audio", False
    if suffix in {".md", ".markdown"}:
        return "markdown", False
    if suffix == ".pdf":
        return "pdf", False
    if suffix in {".ppt", ".pptx", ".key"}:
        return "presentation", False
    if suffix in {".xls", ".xlsx", ".csv"}:
        return "spreadsheet", False
    if suffix in {".txt", ".json", ".yaml", ".yml", ".xml", ".py", ".ts", ".js", ".tsx", ".jsx"}:
        return "text", False
    return "document", False


@dataclass
class MessageAttachmentRef:
    id: str
    name: str
    category: str
    is_image: bool
    origin: str
    status: str
    mime_type: str | None = None
    size: int | None = None
    preview_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {key: value for key, value in data.items() if value is not None}


@dataclass
class AttachmentRecord:
    id: str
    session_id: str
    message_id: str | None
    owner_role: str
    origin: str
    status: str
    name: str
    mime_type: str
    size: int
    category: str
    is_image: bool
    storage_path: str
    created_at: str
    expires_at: str | None
    source_url: str | None = None
    retained_at: str | None = None
    preview_text: str | None = None
    error: str | None = None
    favorite: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_message_ref(self) -> dict[str, Any]:
        return MessageAttachmentRef(
            id=self.id,
            name=self.name,
            category=self.category,
            is_image=self.is_image,
            origin=self.origin,
            status=self.status,
            mime_type=self.mime_type or None,
            size=self.size,
            preview_text=self.preview_text,
        ).to_dict()


class AttachmentStore:
    """Workspace-backed index and file storage for assistant attachments."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.uploads_root = self.workspace / "uploads" / "web"
        self.uploads_root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.uploads_root / "attachments.json"

    def _load_index(self) -> dict[str, dict[str, Any]]:
        if not self.index_path.exists():
            return {}
        try:
            with open(self.index_path, encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return {
                    str(key): value
                    for key, value in data.items()
                    if isinstance(value, dict)
                }
        except Exception:
            return {}
        return {}

    def _save_index(self, data: dict[str, dict[str, Any]]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.index_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)

    def _session_root(self, session_id: str) -> Path:
        return self.uploads_root / safe_filename(session_id)

    def _attachment_dir(self, session_id: str, attachment_id: str, *, saved: bool) -> Path:
        state = "saved" if saved else "temp"
        path = self._session_root(session_id) / "assistant" / state / attachment_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _default_remote_downloader(url: str) -> tuple[bytes, str | None]:
        request = Request(url, headers={"User-Agent": "TokenMind/1.0"})
        with urlopen(request, timeout=20) as response:  # noqa: S310 - controlled server-side fetch
            content_type = response.headers.get_content_type() if response.headers else None
            return response.read(), content_type

    def _write_record(self, record: AttachmentRecord) -> dict[str, Any]:
        index = self._load_index()
        index[record.id] = record.to_dict()
        self._save_index(index)
        return record.to_message_ref()

    def _record_from_index(self, attachment_id: str) -> AttachmentRecord | None:
        payload = self._load_index().get(attachment_id)
        if not isinstance(payload, dict):
            return None
        # Defensive: drop unknown keys so older schemas can still be loaded.
        known = {field.name for field in fields(AttachmentRecord)}
        clean = {key: value for key, value in payload.items() if key in known}
        return AttachmentRecord(**clean)

    @staticmethod
    def _preview_text(content: bytes | str | None, mime_type: str | None) -> str | None:
        if content is None:
            return None
        if isinstance(content, bytes):
            try:
                decoded = content.decode("utf-8")
            except UnicodeDecodeError:
                return None
        else:
            decoded = content
        if not decoded.strip():
            return None
        if mime_type and mime_type.startswith("image/"):
            return None
        compact = decoded.strip().replace("\r\n", "\n").replace("\r", "\n")
        return compact[:140] + ("..." if len(compact) > 140 else "")

    @staticmethod
    def _parse_iso(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _new_record(
        self,
        *,
        session_id: str,
        message_id: str | None,
        origin: str,
        name: str,
        mime_type: str,
        size: int,
        storage_path: Path,
        retention: timedelta,
        source_url: str | None = None,
        preview_text: str | None = None,
    ) -> AttachmentRecord:
        category, is_image = categorize_attachment(name, mime_type)
        created_at = datetime.now()
        return AttachmentRecord(
            id=f"att_{secrets.token_hex(8)}",
            session_id=session_id,
            message_id=message_id,
            owner_role="assistant",
            origin=origin,
            status="temporary",
            name=name,
            mime_type=mime_type,
            size=size,
            category=category,
            is_image=is_image,
            storage_path=str(storage_path),
            created_at=created_at.isoformat(),
            expires_at=(created_at + retention).isoformat(),
            source_url=source_url,
            preview_text=preview_text,
        )

    def create_generated(
        self,
        session_id: str,
        *,
        filename: str,
        content: str | bytes,
        mime_type: str | None,
        retention: timedelta,  # kept for API compatibility; ignored in auto-save mode
        message_id: str | None = None,
        preview_text: str | None = None,
    ) -> dict[str, Any]:
        del retention  # auto-saved attachments never expire
        safe_name = safe_filename(filename or "attachment.txt")
        payload = content.encode("utf-8") if isinstance(content, str) else content
        resolved_mime = mime_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
        attachment_id = f"att_{secrets.token_hex(8)}"
        # Auto-save: place directly in the "saved" subtree so it persists.
        directory = self._attachment_dir(session_id, attachment_id, saved=True)
        destination = directory / safe_name
        destination.write_bytes(payload)
        now_iso = datetime.now().isoformat()
        record = AttachmentRecord(
            id=attachment_id,
            session_id=session_id,
            message_id=message_id,
            owner_role="assistant",
            origin="assistant_generated",
            status="saved",
            name=safe_name,
            mime_type=resolved_mime,
            size=len(payload),
            category=categorize_attachment(safe_name, resolved_mime)[0],
            is_image=categorize_attachment(safe_name, resolved_mime)[1],
            storage_path=str(destination),
            created_at=now_iso,
            expires_at=None,
            retained_at=now_iso,
            preview_text=preview_text if preview_text is not None else self._preview_text(content, resolved_mime),
        )
        return self._write_record(record)

    def create_local(
        self,
        session_id: str,
        *,
        source_path: str | Path,
        retention: timedelta,  # kept for API compatibility; ignored in auto-save mode
        message_id: str | None = None,
        attachment_name: str | None = None,
    ) -> dict[str, Any]:
        del retention
        source = Path(source_path)
        try:
            resolved = source.resolve(strict=True)
        except OSError as exc:
            raise HTTPException(status_code=404, detail=f"Attachment file not found: {exc}") from exc

        if not resolved.is_file():
            raise HTTPException(status_code=400, detail="Only local files can be attached")

        safe_name = safe_filename(attachment_name or resolved.name or "attachment.bin")
        mime_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
        attachment_id = f"att_{secrets.token_hex(8)}"
        directory = self._attachment_dir(session_id, attachment_id, saved=True)
        destination = directory / safe_name
        shutil.copy2(resolved, destination)
        now_iso = datetime.now().isoformat()

        record = AttachmentRecord(
            id=attachment_id,
            session_id=session_id,
            message_id=message_id,
            owner_role="assistant",
            origin="assistant_local",
            status="saved",
            name=safe_name,
            mime_type=mime_type,
            size=destination.stat().st_size,
            category=categorize_attachment(safe_name, mime_type)[0],
            is_image=categorize_attachment(safe_name, mime_type)[1],
            storage_path=str(destination),
            created_at=now_iso,
            expires_at=None,
            retained_at=now_iso,
        )
        return self._write_record(record)

    def create_remote(
        self,
        session_id: str,
        *,
        source_url: str,
        retention: timedelta,  # kept for API compatibility; ignored in auto-save mode
        message_id: str | None = None,
        filename: str | None = None,
        downloader: AttachmentDownloader | None = None,
    ) -> dict[str, Any]:
        del retention
        payload, content_type = (downloader or self._default_remote_downloader)(source_url)
        inferred_name = filename or Path(source_url.split("?", 1)[0]).name or "download.bin"
        safe_name = safe_filename(inferred_name)
        mime_type = content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
        attachment_id = f"att_{secrets.token_hex(8)}"
        directory = self._attachment_dir(session_id, attachment_id, saved=True)
        destination = directory / safe_name
        destination.write_bytes(payload)
        now_iso = datetime.now().isoformat()
        record = AttachmentRecord(
            id=attachment_id,
            session_id=session_id,
            message_id=message_id,
            owner_role="assistant",
            origin="assistant_remote",
            status="saved",
            name=safe_name,
            mime_type=mime_type,
            size=len(payload),
            category=categorize_attachment(safe_name, mime_type)[0],
            is_image=categorize_attachment(safe_name, mime_type)[1],
            storage_path=str(destination),
            created_at=now_iso,
            expires_at=None,
            retained_at=now_iso,
            source_url=source_url,
        )
        return self._write_record(record)

    def create_user_upload(
        self,
        session_id: str,
        *,
        filename: str,
        content: bytes,
        mime_type: str | None,
        retention: timedelta,
        message_id: str | None = None,
    ) -> tuple[dict[str, Any], Path]:
        safe_name = safe_filename(filename or "upload.bin")
        resolved_mime = mime_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
        attachment_id = f"att_{secrets.token_hex(8)}"
        directory = self._session_root(session_id) / "user" / "uploads" / attachment_id
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / safe_name
        destination.write_bytes(content)
        record = AttachmentRecord(
            id=attachment_id,
            session_id=session_id,
            message_id=message_id,
            owner_role="user",
            origin="user_upload",
            status="saved",
            name=safe_name,
            mime_type=resolved_mime,
            size=len(content),
            category=categorize_attachment(safe_name, resolved_mime)[0],
            is_image=categorize_attachment(safe_name, resolved_mime)[1],
            storage_path=str(destination),
            created_at=datetime.now().isoformat(),
            expires_at=(datetime.now() + retention).isoformat(),
            preview_text=self._preview_text(content, resolved_mime),
        )
        return self._write_record(record), destination

    def get_record(self, attachment_id: str) -> dict[str, Any] | None:
        record = self._record_from_index(attachment_id)
        return record.to_dict() if record else None

    def resolve(self, attachment_id: str) -> AttachmentRecord:
        record = self._record_from_index(attachment_id)
        if not record:
            raise HTTPException(status_code=404, detail="Attachment not found")

        path = Path(record.storage_path)
        if record.status == "expired" or not path.exists():
            if record.status != "expired":
                self.mark_expired(attachment_id)
                record = self._record_from_index(attachment_id) or record
            raise HTTPException(status_code=410, detail="Attachment has expired")
        return record

    def retain(self, attachment_id: str) -> dict[str, Any]:
        record = self._record_from_index(attachment_id)
        if not record:
            raise HTTPException(status_code=404, detail="Attachment not found")
        if record.status == "expired":
            raise HTTPException(status_code=410, detail="Attachment has expired")
        if record.status == "saved":
            return record.to_message_ref()

        current = Path(record.storage_path)
        if not current.exists():
            self.mark_expired(attachment_id)
            raise HTTPException(status_code=410, detail="Attachment has expired")

        destination_dir = self._attachment_dir(record.session_id, record.id, saved=True)
        destination = destination_dir / safe_filename(record.name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(current), str(destination))
        self._prune_empty_parents(current.parent)

        updated = AttachmentRecord(
            **{
                **record.to_dict(),
                "status": "saved",
                "storage_path": str(destination),
                "retained_at": datetime.now().isoformat(),
                "expires_at": None,
            }
        )
        self._write_record(updated)
        return updated.to_message_ref()

    def mark_expired(self, attachment_id: str) -> dict[str, Any] | None:
        record = self._record_from_index(attachment_id)
        if not record:
            return None
        updated = AttachmentRecord(
            **{
                **record.to_dict(),
                "status": "expired",
                "retained_at": record.retained_at,
            }
        )
        self._write_record(updated)
        return updated.to_message_ref()

    def expire_stale(self, cutoff: datetime) -> dict[str, int]:
        index = self._load_index()
        expired_count = 0
        deleted_files = 0
        for attachment_id, payload in list(index.items()):
            try:
                record = AttachmentRecord(**payload)
            except TypeError:
                continue
            if record.status != "temporary":
                continue

            path = Path(record.storage_path)
            created_at = self._parse_iso(record.created_at)
            expires_at = self._parse_iso(record.expires_at)
            should_expire = (
                (expires_at is not None and expires_at <= datetime.now())
                or (created_at is not None and created_at < cutoff)
                or not path.exists()
            )
            if not should_expire:
                continue

            if path.exists():
                try:
                    path.unlink()
                    deleted_files += 1
                except OSError:
                    pass
            self._prune_empty_parents(path.parent)
            payload["status"] = "expired"
            index[attachment_id] = payload
            expired_count += 1

        if expired_count:
            self._save_index(index)
        return {"expired_attachments": expired_count, "deleted_files": deleted_files}

    def hydrate_refs(self, attachments: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if not attachments:
            return []
        hydrated: list[dict[str, Any]] = []
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            attachment_id = attachment.get("id")
            if not attachment_id:
                hydrated.append(dict(attachment))
                continue
            record = self._record_from_index(str(attachment_id))
            if not record:
                hydrated.append(dict(attachment))
                continue
            if record.status != "expired" and not Path(record.storage_path).exists():
                self.mark_expired(str(attachment_id))
                record = self._record_from_index(str(attachment_id)) or record
            hydrated.append({**dict(attachment), **record.to_message_ref()})
        return hydrated

    def set_favorite(self, attachment_id: str, favorite: bool) -> AttachmentRecord:
        record = self._record_from_index(attachment_id)
        if not record:
            raise HTTPException(status_code=404, detail="Attachment not found")
        if record.favorite == favorite:
            return record
        updated_payload = {**record.to_dict(), "favorite": favorite}
        # Favoriting an item should also retain it (so it doesn't get auto-cleaned later).
        if favorite and record.status == "temporary":
            updated_payload["status"] = "saved"
            updated_payload["retained_at"] = datetime.now().isoformat()
            updated_payload["expires_at"] = None
        updated = AttachmentRecord(**updated_payload)
        self._write_record(updated)
        return updated

    def remove(self, attachment_id: str) -> AttachmentRecord:
        record = self._record_from_index(attachment_id)
        if not record:
            raise HTTPException(status_code=404, detail="Attachment not found")
        path = Path(record.storage_path)
        if path.exists():
            try:
                path.unlink()
            except OSError as exc:
                raise HTTPException(status_code=500, detail=f"Failed to delete file: {exc}") from exc
            self._prune_empty_parents(path.parent)
        index = self._load_index()
        index.pop(attachment_id, None)
        self._save_index(index)
        return record

    def list_records(self) -> list[AttachmentRecord]:
        records: list[AttachmentRecord] = []
        index = self._load_index()
        known = {field.name for field in fields(AttachmentRecord)}
        for payload in index.values():
            if not isinstance(payload, dict):
                continue
            try:
                clean = {key: value for key, value in payload.items() if key in known}
                records.append(AttachmentRecord(**clean))
            except TypeError:
                continue
        return records

    def managed_paths(self) -> set[str]:
        paths = {str(self.index_path.resolve())}
        for payload in self._load_index().values():
            if payload.get("owner_role") == "user":
                continue
            storage_path = payload.get("storage_path")
            if isinstance(storage_path, str) and storage_path:
                try:
                    paths.add(str(Path(storage_path).resolve()))
                except OSError:
                    continue
        return paths

    @staticmethod
    def _prune_empty_parents(directory: Path) -> None:
        current = directory
        while current.exists():
            try:
                next(current.iterdir())
                break
            except StopIteration:
                current.rmdir()
                current = current.parent
            except OSError:
                break
