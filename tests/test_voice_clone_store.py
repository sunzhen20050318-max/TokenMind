from __future__ import annotations

from pathlib import Path

from tokenmind.creative.voice_clone_store import VoiceCloneRecord, VoiceCloneStore


def _record(voice_id: str, **overrides: object) -> VoiceCloneRecord:
    data: dict[str, object] = {
        "voice_id": voice_id,
        "model": "speech-2.8-hd",
        "provider": "minimax",
        "created_at": "2026-04-24T09:00:00Z",
    }
    data.update(overrides)
    return VoiceCloneRecord(**data)  # type: ignore[arg-type]


def test_upsert_creates_then_updates_single_record(tmp_path: Path) -> None:
    store = VoiceCloneStore(tmp_path)
    store.upsert(_record("clone_abcdef01", preview_text="hi"))
    store.upsert(
        _record("clone_abcdef01", preview_text="updated", demo_attachment_id="att_1")
    )

    records = store.list()
    assert len(records) == 1
    assert records[0].preview_text == "updated"
    assert records[0].demo_attachment_id == "att_1"


def test_list_returns_newest_first(tmp_path: Path) -> None:
    store = VoiceCloneStore(tmp_path)
    store.upsert(_record("clone_aaaaaaaa", created_at="2026-04-20T09:00:00Z"))
    store.upsert(_record("clone_bbbbbbbb", created_at="2026-04-24T09:00:00Z"))
    store.upsert(_record("clone_cccccccc", created_at="2026-04-22T09:00:00Z"))

    ids = [record.voice_id for record in store.list()]
    assert ids == ["clone_bbbbbbbb", "clone_cccccccc", "clone_aaaaaaaa"]


def test_mark_kept_alive_records_timestamp(tmp_path: Path) -> None:
    store = VoiceCloneStore(tmp_path)
    store.upsert(_record("clone_alive01a"))

    updated = store.mark_kept_alive("clone_alive01a", timestamp="2026-04-30T10:00:00Z")
    assert updated.last_kept_alive_at == "2026-04-30T10:00:00Z"

    fetched = store.get("clone_alive01a")
    assert fetched is not None
    assert fetched.last_kept_alive_at == "2026-04-30T10:00:00Z"


def test_delete_removes_record_and_returns_it(tmp_path: Path) -> None:
    store = VoiceCloneStore(tmp_path)
    store.upsert(_record("clone_deletable"))

    removed = store.delete("clone_deletable")
    assert removed is not None
    assert removed.voice_id == "clone_deletable"
    assert store.list() == []


def test_delete_returns_none_for_unknown_id(tmp_path: Path) -> None:
    store = VoiceCloneStore(tmp_path)
    assert store.delete("clone_missing01") is None


def test_malformed_json_is_treated_as_empty(tmp_path: Path) -> None:
    (tmp_path / "voice_clones.json").write_text("{not json", encoding="utf-8")
    store = VoiceCloneStore(tmp_path)
    assert store.list() == []

    # Can recover by writing a fresh record
    store.upsert(_record("clone_new00001"))
    assert [record.voice_id for record in store.list()] == ["clone_new00001"]
