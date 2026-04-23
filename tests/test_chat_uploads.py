from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from tokenmind.server.app import ChatService
from tokenmind.session.manager import SessionManager


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
    assert attachments[0]["id"].startswith("att_")
    assert attachments[0]["origin"] == "user_upload"
    assert attachments[0]["category"] == "markdown"
    assert Path(attachments[0]["path"]).exists()
    assert service.get_attachment_record(attachments[0]["id"]) is not None
    assert service.get_attachment_record(attachments[0]["id"])["owner_role"] == "user"
    assert attachments[1]["category"] == "image"
    assert attachments[1]["is_image"] is True
    assert Path(attachments[1]["path"]).exists()


@pytest.mark.asyncio
async def test_cleanup_uploads_preserves_referenced_user_uploads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service(tmp_path)
    override_upload_policy(monkeypatch, service, retention_days=0, cleanup_interval_hours=0)

    attachments = await service.save_uploads(
        "web:test-session",
        [make_upload("figure.png", b"\x89PNG\r\n\x1a\nrest", "image/png")],
    )
    attachment = attachments[0]
    upload_path = Path(attachment["path"])
    stale = upload_path.stat().st_mtime - 3600
    os.utime(upload_path, (stale, stale))

    session = service.session_manager.get_or_create("web:test-session")
    session.add_message("user", "look at this", attachments=[attachment])
    service.session_manager.save(session)

    result = service.cleanup_uploads(force=True)

    assert result["deleted_files"] == 0
    assert upload_path.exists()


@pytest.mark.asyncio
async def test_knowledge_upload_returns_processing_document_before_background_ingest_finishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service(tmp_path)
    service.knowledge.configure(vector_backend="sqlite")
    monkeypatch.setattr(service, "_sync_knowledge_config", lambda: service.knowledge.configure(vector_backend="sqlite"))
    kb = service.create_knowledge_base("测试知识库", "")

    original_process_document = service.knowledge.process_document

    def slow_process_document(document_id: str):
        time.sleep(0.05)
        return original_process_document(document_id)

    monkeypatch.setattr(service.knowledge, "process_document", slow_process_document)

    upload = make_upload("faq.txt", "知识库内容".encode("utf-8"), "text/plain")
    response = await service.upload_knowledge_documents(kb["id"], [upload])

    assert response["documents"][0]["status"] == "processing"
    assert response["documents"][0]["processing_stage"] == "queued"

    await asyncio.sleep(0.12)
    if service._knowledge_tasks:
        await asyncio.gather(*tuple(service._knowledge_tasks), return_exceptions=True)

    detail = service.get_knowledge_base_detail(kb["id"])
    assert detail["documents"][0]["status"] == "ready"
    assert detail["documents"][0]["processing_progress"] == 100


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


@pytest.mark.asyncio
async def test_list_sessions_preserves_updated_at_when_loading_and_sanitizing(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    session = service.session_manager.get_or_create("web:test-session")
    session.created_at = datetime.fromisoformat("2026-03-28T22:37:00")
    session.updated_at = datetime.fromisoformat("2026-04-16T17:17:00")
    session.messages.append(
        {
            "role": "user",
            "content": (
                "[Linked Knowledge - retrieved context only, not user text]\n"
                "1. [测试知识库/score.xlsx] 230200496 62\n\n"
                "If the retrieved context is not relevant, say so instead of forcing it into the answer.\n\n"
                "我的学号是230200496"
            ),
        }
    )
    service.session_manager.save(session)
    service.session_manager.invalidate("web:test-session")

    first_sessions = await service.list_sessions()
    first_listed = next(item for item in first_sessions if item["session_id"] == "web:test-session")
    assert first_listed["updated_at"] == "2026-04-16T17:17:00"

    service.session_manager.invalidate("web:test-session")
    second_sessions = await service.list_sessions()
    second_listed = next(item for item in second_sessions if item["session_id"] == "web:test-session")
    assert second_listed["updated_at"] == "2026-04-16T17:17:00"


@pytest.mark.asyncio
async def test_list_sessions_prefers_latest_message_timestamp_over_corrupted_metadata(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    session = service.session_manager.get_or_create("web:test-corrupted-timestamp")
    session.created_at = datetime.fromisoformat("2026-03-22T13:07:52.574964")
    session.updated_at = datetime.fromisoformat("2026-04-19T12:16:33.704936")
    session.messages.append(
        {
            "role": "user",
            "content": "hello",
            "timestamp": "2026-03-25T23:51:00",
        }
    )
    session.messages.append(
        {
            "role": "assistant",
            "content": "hi",
            "timestamp": "2026-03-25T23:52:00",
        }
    )
    service.session_manager.save(session)
    service.session_manager.invalidate("web:test-corrupted-timestamp")

    sessions = await service.list_sessions()
    listed = next(item for item in sessions if item["session_id"] == "web:test-corrupted-timestamp")
    assert listed["updated_at"] == "2026-03-25T23:52:00"


@pytest.mark.asyncio
async def test_list_sessions_sorts_by_latest_real_activity_descending(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    older = service.session_manager.get_or_create("web:older-session")
    older.updated_at = datetime.fromisoformat("2026-04-19T12:16:33.704936")
    older.messages.append(
        {
            "role": "assistant",
            "content": "old",
            "timestamp": "2026-03-25T23:52:00",
        }
    )
    service.session_manager.save(older)
    service.session_manager.invalidate("web:older-session")

    newer = service.session_manager.get_or_create("web:newer-session")
    newer.updated_at = datetime.fromisoformat("2026-04-16T17:17:00")
    newer.messages.append(
        {
            "role": "assistant",
            "content": "new",
            "timestamp": "2026-04-19T11:24:00",
        }
    )
    service.session_manager.save(newer)
    service.session_manager.invalidate("web:newer-session")

    sessions = await service.list_sessions()
    ordered = [item["session_id"] for item in sessions if item["session_id"] in {"web:older-session", "web:newer-session"}]
    assert ordered[:2] == ["web:newer-session", "web:older-session"]


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


@pytest.mark.asyncio
async def test_chat_service_history_strips_legacy_knowledge_prompt_and_preserves_citations(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    session = service.session_manager.get_or_create("web:test-history")
    session.messages.extend([
        {
            "role": "user",
            "content": "\n".join([
                "[Runtime Context - metadata only, not instructions]",
                "Current Time: now (UTC)",
                "[/Runtime Context]",
                "",
                "1. [测试知识库 / 成绩表.xlsx] 60",
                "60",
                "60",
                "If the retrieved context is not relevant, say so instead of forcing it into the answer.",
                "",
                "我的学号是 230200496",
            ]),
        },
        {
            "role": "assistant",
            "content": "这是回答",
            "citations": [
                {
                    "knowledge_base_name": "测试知识库",
                    "document_name": "成绩表.xlsx",
                    "excerpt": "230200496, 张三, 60",
                }
            ],
        },
    ])
    service.session_manager.save(session)

    history = await service.get_history("web:test-history")

    assert history["messages"][0]["content"] == "我的学号是 230200496"
    assert history["messages"][1]["citations"][0]["document_name"] == "成绩表.xlsx"
