"""Tests for /api/assets endpoints and AttachmentStore favorite/delete."""

from __future__ import annotations

from datetime import timedelta

import pytest


@pytest.fixture
def attachment_store(tmp_path):
    from tokenmind.server.attachments import AttachmentStore

    return AttachmentStore(tmp_path)


@pytest.mark.asyncio
async def test_categorize_attachment_recognises_video_extensions():
    from tokenmind.server.attachments import categorize_attachment

    assert categorize_attachment("clip.mp4", None) == ("video", False)
    assert categorize_attachment("clip.MOV", None) == ("video", False)
    assert categorize_attachment("ignored", "video/webm") == ("video", False)
    assert categorize_attachment("photo.png", None) == ("image", True)


def test_set_favorite_marks_temporary_record_as_saved(attachment_store):
    seed = attachment_store.create_generated(
        session_id="web:abc",
        filename="hello.txt",
        content="hi",
        mime_type="text/plain",
        retention=timedelta(hours=1),
    )
    record_id = seed["id"]

    record = attachment_store.set_favorite(record_id, True)
    assert record.favorite is True
    # Favoriting also retains the file so cleanup never sweeps it.
    assert record.status == "saved"
    assert record.expires_at is None

    cleared = attachment_store.set_favorite(record_id, False)
    assert cleared.favorite is False
    # Once retained we keep it retained — only the favorite flag flips.
    assert cleared.status == "saved"


def test_remove_deletes_file_and_index(attachment_store):
    seed = attachment_store.create_generated(
        session_id="web:abc",
        filename="hello.txt",
        content="hi",
        mime_type="text/plain",
        retention=timedelta(hours=1),
    )
    record_id = seed["id"]

    record = attachment_store.remove(record_id)
    from pathlib import Path

    assert not Path(record.storage_path).exists()
    assert attachment_store.get_record(record_id) is None


def _no_project(_session_id: str) -> str | None:
    return None


@pytest.mark.asyncio
async def test_list_assets_filters_by_category_and_favorite(monkeypatch, tmp_path):
    from tokenmind.server.attachments import AttachmentStore
    from tokenmind.server.routes import assets as assets_module

    store = AttachmentStore(tmp_path)
    store.create_generated(
        session_id="web:1",
        filename="cat.png",
        content=b"\x89PNG\r\n",
        mime_type="image/png",
        retention=timedelta(hours=1),
    )
    file_record = store.create_generated(
        session_id="web:1",
        filename="notes.md",
        content="# hi",
        mime_type="text/markdown",
        retention=timedelta(hours=1),
    )
    video_record = store.create_generated(
        session_id="web:2",
        filename="trailer.mp4",
        content=b"\x00\x00\x00",
        mime_type="video/mp4",
        retention=timedelta(hours=1),
    )
    audio_record = store.create_generated(
        session_id="creative:music",
        filename="song.mp3",
        content=b"ID3",
        mime_type="audio/mpeg",
        retention=timedelta(hours=1),
    )
    tts_record = store.create_generated(
        session_id="creative:tts",
        filename="tts.mp3",
        content=b"ID3",
        mime_type="audio/mpeg",
        retention=timedelta(hours=1),
    )
    clone_record = store.create_generated(
        session_id="creative:voice_clone",
        filename="voice-demo.mp3",
        content=b"ID3",
        mime_type="audio/mpeg",
        retention=timedelta(hours=1),
    )
    design_record = store.create_generated(
        session_id="creative:voice_design",
        filename="voice-design.mp3",
        content=b"ID3",
        mime_type="audio/mpeg",
        retention=timedelta(hours=1),
    )
    store.set_favorite(file_record["id"], True)

    images = await assets_module.list_assets(
        category="image", store=store, project_lookup=_no_project
    )
    assert {item.id for item in images.items} == {
        record.id for record in store.list_records() if record.category == "image"
    }
    assert images.total == 1

    videos = await assets_module.list_assets(
        category="video", store=store, project_lookup=_no_project
    )
    assert {item.id for item in videos.items} == {video_record["id"]}

    music = await assets_module.list_assets(
        category="music", store=store, project_lookup=_no_project
    )
    assert {item.id for item in music.items} == {audio_record["id"]}

    tts = await assets_module.list_assets(
        category="tts", store=store, project_lookup=_no_project
    )
    assert {item.id for item in tts.items} == {tts_record["id"]}

    clones = await assets_module.list_assets(
        category="voice_clone", store=store, project_lookup=_no_project
    )
    assert {item.id for item in clones.items} == {clone_record["id"]}

    designs = await assets_module.list_assets(
        category="voice_design", store=store, project_lookup=_no_project
    )
    assert {item.id for item in designs.items} == {design_record["id"]}

    audio = await assets_module.list_assets(
        category="audio", store=store, project_lookup=_no_project
    )
    assert {item.id for item in audio.items} == {
        audio_record["id"],
        tts_record["id"],
        clone_record["id"],
        design_record["id"],
    }

    files = await assets_module.list_assets(
        category="file", store=store, project_lookup=_no_project
    )
    assert {item.id for item in files.items} == {file_record["id"]}

    favorites = await assets_module.list_assets(
        category="file", favorite=True, store=store, project_lookup=_no_project
    )
    assert {item.id for item in favorites.items} == {file_record["id"]}
    not_favorites = await assets_module.list_assets(
        category="file", favorite=False, store=store, project_lookup=_no_project
    )
    assert {item.id for item in not_favorites.items} == set()


@pytest.mark.asyncio
async def test_list_assets_includes_project_id_when_session_belongs_to_project(tmp_path):
    from tokenmind.server.attachments import AttachmentStore
    from tokenmind.server.routes import assets as assets_module

    store = AttachmentStore(tmp_path)
    project_seed = store.create_generated(
        session_id="web:proj-session",
        filename="diagram.png",
        content=b"\x89PNG\r\n",
        mime_type="image/png",
        retention=timedelta(hours=1),
    )
    global_seed = store.create_generated(
        session_id="web:lone-session",
        filename="snapshot.png",
        content=b"\x89PNG\r\n",
        mime_type="image/png",
        retention=timedelta(hours=1),
    )

    fake_project_id = "proj-42"

    def lookup(session_id: str) -> str | None:
        return fake_project_id if session_id == "web:proj-session" else None

    response = await assets_module.list_assets(
        category="image", store=store, project_lookup=lookup
    )
    by_id = {item.id: item for item in response.items}
    assert by_id[project_seed["id"]].project_id == fake_project_id
    assert by_id[global_seed["id"]].project_id is None


@pytest.mark.asyncio
async def test_update_and_delete_asset_endpoints(tmp_path):
    from tokenmind.server.attachments import AttachmentStore
    from tokenmind.server.routes import assets as assets_module

    store = AttachmentStore(tmp_path)
    seed = store.create_generated(
        session_id="web:abc",
        filename="diagram.svg",
        content="<svg/>",
        mime_type="image/svg+xml",
        retention=timedelta(hours=1),
    )

    item = await assets_module.update_asset(
        seed["id"],
        assets_module.AssetFavoriteRequest(favorite=True),
        store=store,
        project_lookup=_no_project,
    )
    assert item.favorite is True

    response = await assets_module.delete_asset(seed["id"], store=store)
    assert response.success is True
    assert store.get_record(seed["id"]) is None
