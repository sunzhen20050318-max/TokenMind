"""Tests for storage API route helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from tokenmind.server.routes import storage as storage_routes


@pytest.mark.asyncio
async def test_get_storage_overview_returns_service_payload(monkeypatch: pytest.MonkeyPatch):
    expected = {
        "summary": {
            "used_bytes": 128,
            "quota_bytes": 1024,
            "available_bytes": 896,
            "max_file_bytes": 64,
            "file_count": 1,
            "referenced_file_count": 1,
            "unreferenced_file_count": 0,
            "stale_unreferenced_file_count": 0,
            "retention_days": 30,
            "cleanup_interval_hours": 12,
        },
        "files": [],
    }

    service = SimpleNamespace(get_storage_overview=lambda: expected)

    response = await storage_routes.get_storage_overview(service=service)

    assert response == expected


@pytest.mark.asyncio
async def test_cleanup_storage_returns_deleted_counts():
    service = SimpleNamespace(cleanup_uploads=lambda force=False: {"deleted_files": 2, "deleted_dirs": 1})

    response = await storage_routes.cleanup_storage(service=service)

    assert response["success"] is True
    assert response["deleted_files"] == 2
    assert response["deleted_dirs"] == 1


@pytest.mark.asyncio
async def test_delete_storage_file_preserves_http_exception():
    service = SimpleNamespace(delete_upload_file=lambda path: (_ for _ in ()).throw(HTTPException(status_code=409)))

    with pytest.raises(HTTPException) as exc_info:
        await storage_routes.delete_storage_file(
            storage_routes.DeleteStorageFileRequest(path="D:/demo.txt"),
            service=service,
        )

    assert exc_info.value.status_code == 409
