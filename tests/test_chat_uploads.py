from __future__ import annotations

import os
import time
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from sun_agent.server.app import ChatService
from sun_agent.session.manager import SessionManager


def make_service(tmp_path: Path) -> ChatService:
    session_manager = SessionManager(tmp_path)
    return ChatService(
        bus=SimpleNamespace(),
        agent_loop=SimpleNamespace(),
        session_manager=session_manager,
    )


def make_upload(filename: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(content), headers={"content-type": content_type})


def override_upload_policy(
    monkeypatch: pytest.MonkeyPatch,
    service: ChatService,
    *,
    max_file_bytes: int = 50 * 1024 * 1024,
    max_total_bytes: int = 1024 * 1024 * 1024,
    retention_days: int = 30,
    cleanup_interval_hours: int = 12,
) -> None:
    monkeypatch.setattr(
        service,
        "_upload_policy",
        lambda: {
            "max_file_mb": max(1, max_file_bytes // (1024 * 1024)),
            "max_total_mb": max(1, max_total_bytes // (1024 * 1024)),
            "retention_days": retention_days,
            "cleanup_interval_hours": cleanup_interval_hours,
            "max_file_bytes": max_file_bytes,
            "max_total_bytes": max_total_bytes,
            "retention": timedelta(days=retention_days),
            "cleanup_interval": timedelta(hours=cleanup_interval_hours),
        },
    )


@pytest.mark.asyncio
async def test_chat_service_save_uploads_persists_files(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    files = [
        make_upload("notes.md", b"# hello", "text/markdown"),
        make_upload("figure.png", b"\x89PNG\r\n\x1a\nrest", "image/png"),
    ]

    attachments = await service.save_uploads("web:test-session", files)

    assert len(attachments) == 2
    assert attachments[0]["category"] == "markdown"
    assert Path(attachments[0]["path"]).exists()
    assert attachments[1]["category"] == "image"
    assert attachments[1]["is_image"] is True
    assert Path(attachments[1]["path"]).exists()


@pytest.mark.asyncio
async def test_chat_service_enforces_single_file_size_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service(tmp_path)
    override_upload_policy(monkeypatch, service, max_file_bytes=5, max_total_bytes=100)

    with pytest.raises(HTTPException) as exc_info:
        await service.save_uploads(
            "web:test-session",
            [make_upload("large.md", b"123456", "text/markdown")],
        )

    assert exc_info.value.status_code == 413
    assert "单文件大小限制" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_chat_service_enforces_total_upload_quota(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service(tmp_path)
    override_upload_policy(monkeypatch, service, max_total_bytes=10, max_file_bytes=20)

    await service.save_uploads(
        "web:test-session",
        [make_upload("first.md", b"1234567", "text/markdown")],
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.save_uploads(
            "web:second-session",
            [make_upload("second.md", b"12345", "text/markdown")],
        )

    assert exc_info.value.status_code == 413
    assert "总配额" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_delete_session_removes_session_upload_directory(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    session = service.session_manager.get_or_create("web:test-session")
    session.add_message("user", "hello")
    service.session_manager.save(session)

    attachments = await service.save_uploads(
        "web:test-session",
        [make_upload("notes.md", b"cleanup me", "text/markdown")],
    )
    upload_path = Path(attachments[0]["path"])
    assert upload_path.exists()

    await service.delete_session("web:test-session")

    assert not upload_path.parent.exists()
    assert not service.session_manager._get_session_path("web:test-session").exists()


def test_cleanup_uploads_removes_old_unreferenced_files_and_keeps_referenced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service(tmp_path)
    uploads_root = service.uploads_dir
    stale_dir = uploads_root / "web_old-session"
    stale_dir.mkdir(parents=True, exist_ok=True)
    stale_file = stale_dir / "stale.txt"
    stale_file.write_text("stale", encoding="utf-8")

    referenced_dir = uploads_root / "web_live-session"
    referenced_dir.mkdir(parents=True, exist_ok=True)
    referenced_file = referenced_dir / "live.txt"
    referenced_file.write_text("live", encoding="utf-8")

    old_timestamp = time.time() - 60 * 60 * 24 * 45
    os.utime(stale_file, (old_timestamp, old_timestamp))
    os.utime(referenced_file, (old_timestamp, old_timestamp))

    session = service.session_manager.get_or_create("web:live-session")
    session.add_message(
        "user",
        "with attachment",
        attachments=[{"name": "live.txt", "path": str(referenced_file), "size": referenced_file.stat().st_size}],
    )
    service.session_manager.save(session)

    override_upload_policy(monkeypatch, service, retention_days=30)
    result = service.cleanup_uploads(force=True)

    assert result["deleted_files"] == 1
    assert not stale_file.exists()
    assert referenced_file.exists()


def test_get_storage_overview_reports_references_and_stale_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service(tmp_path)
    uploads_root = service.uploads_dir
    session_dir = uploads_root / "web_demo"
    session_dir.mkdir(parents=True, exist_ok=True)

    fresh_file = session_dir / "abcdef123456_notes.md"
    stale_file = session_dir / "abcdef123456_old.md"
    fresh_file.write_text("fresh", encoding="utf-8")
    stale_file.write_text("old", encoding="utf-8")

    old_timestamp = time.time() - 60 * 60 * 24 * 45
    os.utime(stale_file, (old_timestamp, old_timestamp))

    session = service.session_manager.get_or_create("web:demo")
    session.add_message(
        "user",
        "with attachment",
        attachments=[{"name": "notes.md", "path": str(fresh_file), "size": fresh_file.stat().st_size}],
    )
    session.set_title("演示会话")
    service.session_manager.save(session)

    override_upload_policy(monkeypatch, service, max_total_bytes=1024, retention_days=30)
    overview = service.get_storage_overview()

    assert overview["summary"]["file_count"] == 2
    assert overview["summary"]["referenced_file_count"] == 1
    assert overview["summary"]["stale_unreferenced_file_count"] == 1
    referenced = next(item for item in overview["files"] if item["referenced"])
    assert referenced["reference_count"] == 1
    assert referenced["referenced_by"][0]["title"] == "演示会话"


def test_delete_upload_file_rejects_referenced_files(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    uploads_root = service.uploads_dir
    session_dir = uploads_root / "web_demo"
    session_dir.mkdir(parents=True, exist_ok=True)
    target = session_dir / "abcdef123456_notes.md"
    target.write_text("demo", encoding="utf-8")

    session = service.session_manager.get_or_create("web:demo")
    session.add_message(
        "user",
        "with attachment",
        attachments=[{"name": "notes.md", "path": str(target), "size": target.stat().st_size}],
    )
    service.session_manager.save(session)

    with pytest.raises(HTTPException) as exc_info:
        service.delete_upload_file(str(target))

    assert exc_info.value.status_code == 409


def test_delete_upload_file_removes_unreferenced_file(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    uploads_root = service.uploads_dir
    session_dir = uploads_root / "web_demo"
    session_dir.mkdir(parents=True, exist_ok=True)
    target = session_dir / "abcdef123456_notes.md"
    target.write_text("demo", encoding="utf-8")

    result = service.delete_upload_file(str(target))

    assert result["success"] is True
    assert not target.exists()
