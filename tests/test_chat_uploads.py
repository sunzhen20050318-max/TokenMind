from __future__ import annotations

import os
import time
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
    monkeypatch.setattr(ChatService, "max_upload_file_bytes", 5)

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
    monkeypatch.setattr(ChatService, "max_total_upload_bytes", 10)
    monkeypatch.setattr(ChatService, "max_upload_file_bytes", 20)

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

    monkeypatch.setattr(ChatService, "unreferenced_upload_retention", service.unreferenced_upload_retention)
    result = service.cleanup_uploads(force=True)

    assert result["deleted_files"] == 1
    assert not stale_file.exists()
    assert referenced_file.exists()
