from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tokenmind.server.app import ChatService
from tokenmind.server.routes import chat as chat_routes
from tokenmind.session.manager import SessionManager


def make_service(tmp_path: Path) -> ChatService:
    session_manager = SessionManager(tmp_path)
    return ChatService(
        bus=SimpleNamespace(),
        agent_loop=SimpleNamespace(),
        session_manager=session_manager,
    )


@pytest.mark.asyncio
async def test_create_generated_attachment_persists_file_and_index(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    ref = service.create_generated_attachment(
        "web:test-session",
        filename="summary.md",
        content="# hello world",
        mime_type="text/markdown",
        message_id="assistant-1",
    )

    assert ref["id"]
    assert ref["origin"] == "assistant_generated"
    # Auto-save: assistant-generated attachments now go straight to "saved".
    assert ref["status"] == "saved"

    record = service.get_attachment_record(ref["id"])
    assert record is not None
    assert record["name"] == "summary.md"
    assert "saved" in str(record["storage_path"])
    assert Path(record["storage_path"]).exists()
    assert Path(record["storage_path"]).read_text(encoding="utf-8") == "# hello world"


@pytest.mark.asyncio
async def test_create_local_attachment_copies_workspace_file_into_temp_storage(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    source = tmp_path / "exports" / "chart.png"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"\x89PNG\r\n\x1a\npayload")

    ref = service.create_local_attachment(
        "web:test-session",
        source_path=source,
        message_id="assistant-local-1",
    )

    assert ref["origin"] == "assistant_local"
    record = service.get_attachment_record(ref["id"])
    assert record is not None
    stored = Path(record["storage_path"])
    assert stored.exists()
    assert stored.read_bytes() == source.read_bytes()
    assert stored != source


@pytest.mark.asyncio
async def test_create_local_attachment_copies_external_file_into_temp_storage(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    external_root = tmp_path.parent / f"{tmp_path.name}_external"
    external_root.mkdir(parents=True, exist_ok=True)
    source = external_root / "desktop-image.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\nexternal")

    ref = service.create_local_attachment(
        "web:test-session",
        source_path=source,
        message_id="assistant-local-external-1",
    )

    assert ref["origin"] == "assistant_local"
    record = service.get_attachment_record(ref["id"])
    assert record is not None
    stored = Path(record["storage_path"])
    assert stored.exists()
    assert stored.read_bytes() == source.read_bytes()
    assert stored != source


@pytest.mark.asyncio
async def test_create_remote_attachment_downloads_and_indexes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service(tmp_path)

    def fake_downloader(_url: str) -> tuple[bytes, str | None]:
        return (b"remote-data", "text/plain")

    monkeypatch.setattr(service.attachments, "_default_remote_downloader", fake_downloader)

    ref = service.create_remote_attachment(
        "web:test-session",
        source_url="https://example.com/report.txt",
        message_id="assistant-remote-1",
        filename="report.txt",
    )

    assert ref["origin"] == "assistant_remote"
    record = service.get_attachment_record(ref["id"])
    assert record is not None
    assert record["source_url"] == "https://example.com/report.txt"
    assert Path(record["storage_path"]).read_text(encoding="utf-8") == "remote-data"


@pytest.mark.asyncio
async def test_retain_attachment_is_idempotent_on_auto_saved_records(tmp_path: Path) -> None:
    """Auto-save means new generated attachments are already saved; retain is a no-op."""
    service = make_service(tmp_path)
    ref = service.create_generated_attachment(
        "web:test-session",
        filename="report.txt",
        content="draft",
        mime_type="text/plain",
        message_id="assistant-2",
    )

    before = service.get_attachment_record(ref["id"])
    assert before is not None
    assert before["status"] == "saved"
    before_path = Path(before["storage_path"])

    retained = service.retain_attachment(ref["id"])

    assert retained["status"] == "saved"
    after = service.get_attachment_record(ref["id"])
    assert after is not None
    assert Path(after["storage_path"]) == before_path
    assert before_path.exists()


@pytest.mark.asyncio
async def test_cleanup_uploads_keeps_auto_saved_assistant_attachments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Auto-saved assistant attachments must survive cleanup sweeps."""
    service = make_service(tmp_path)
    monkeypatch.setattr(
        service,
        "_upload_policy",
        lambda: {
            "max_file_mb": 50,
            "max_total_mb": 1024,
            "retention_days": 0,
            "cleanup_interval_hours": 0,
            "max_file_bytes": 50 * 1024 * 1024,
            "max_total_bytes": 1024 * 1024 * 1024,
            "retention": __import__("datetime").timedelta(days=0),
            "cleanup_interval": __import__("datetime").timedelta(hours=0),
        },
    )

    ref = service.create_generated_attachment(
        "web:test-session",
        filename="kept.json",
        content='{"ok": true}',
        mime_type="application/json",
        message_id="assistant-3",
    )
    record = service.get_attachment_record(ref["id"])
    assert record is not None
    storage_path = Path(record["storage_path"])
    stale = storage_path.stat().st_mtime - 3600
    os.utime(storage_path, (stale, stale))

    service.cleanup_uploads(force=True)

    after = service.get_attachment_record(ref["id"])
    assert after is not None
    assert after["status"] == "saved"
    assert Path(after["storage_path"]).exists()


@pytest.mark.asyncio
async def test_history_serialization_reflects_latest_attachment_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service(tmp_path)
    monkeypatch.setattr(
        service,
        "_upload_policy",
        lambda: {
            "max_file_mb": 50,
            "max_total_mb": 1024,
            "retention_days": 0,
            "cleanup_interval_hours": 0,
            "max_file_bytes": 50 * 1024 * 1024,
            "max_total_bytes": 1024 * 1024 * 1024,
            "retention": __import__("datetime").timedelta(days=0),
            "cleanup_interval": __import__("datetime").timedelta(hours=0),
        },
    )

    ref = service.create_generated_attachment(
        "web:test-session",
        filename="summary.csv",
        content="a,b\n1,2\n",
        mime_type="text/csv",
        message_id="assistant-4",
    )
    session = service.session_manager.get_or_create("web:test-session")
    session.add_message("assistant", "已生成文件。", attachments=[ref])
    service.session_manager.save(session)

    record = service.get_attachment_record(ref["id"])
    assert record is not None
    storage_path = Path(record["storage_path"])
    stale = storage_path.stat().st_mtime - 3600
    os.utime(storage_path, (stale, stale))
    service.cleanup_uploads(force=True)

    history = await service.get_history("web:test-session")

    # Auto-saved attachments survive cleanup, so the status stays "saved".
    assert history["messages"][0]["attachments"][0]["status"] == "saved"


def build_chat_test_client(service: ChatService) -> TestClient:
    app = FastAPI()
    app.include_router(chat_routes.router)
    app.dependency_overrides[chat_routes.get_chat_service] = lambda: service
    return TestClient(app)


def test_attachment_download_route_returns_file(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    ref = service.create_generated_attachment(
        "web:test-session",
        filename="notes.md",
        content="# hi",
        mime_type="text/markdown",
        message_id="assistant-5",
    )
    client = build_chat_test_client(service)

    response = client.get(f"/api/chat/attachments/{ref['id']}")

    assert response.status_code == 200
    assert response.text == "# hi"


def test_user_upload_attachment_download_route_returns_file(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    client = build_chat_test_client(service)

    upload_response = client.post(
        "/api/chat/upload",
        data={"session_id": "web:test-session"},
        files={"files": ("image.png", b"\x89PNG\r\n\x1a\npayload", "image/png")},
    )

    assert upload_response.status_code == 200
    attachment = upload_response.json()["attachments"][0]

    response = client.get(f"/api/chat/attachments/{attachment['id']}")

    assert response.status_code == 200
    assert response.content == b"\x89PNG\r\n\x1a\npayload"


def test_attachment_retain_route_updates_status(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    ref = service.create_generated_attachment(
        "web:test-session",
        filename="draft.txt",
        content="hello",
        mime_type="text/plain",
        message_id="assistant-6",
    )
    client = build_chat_test_client(service)

    response = client.post(f"/api/chat/attachments/{ref['id']}/retain")

    assert response.status_code == 200
    payload = response.json()
    assert payload["attachment"]["id"] == ref["id"]
    assert payload["attachment"]["status"] == "saved"
