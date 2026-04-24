"""Persistence layer for cloned voice records.

Records live at ``<workspace>/voice_clones.json`` as a JSON array. We keep one
entry per cloned ``voice_id`` so the UI can show the list across sessions and
devices, and so we can manage keep-alive against the MiniMax 7-day cleanup
policy without relying on browser local storage.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class VoiceCloneRecord:
    """Metadata persisted for every successfully cloned or designed voice."""

    voice_id: str
    model: str
    provider: str
    created_at: str
    preview_text: str | None = None
    source_filename: str | None = None
    demo_audio_url: str | None = None
    demo_attachment_id: str | None = None
    last_kept_alive_at: str | None = None
    notes: str | None = None
    # "clone" for /v1/voice_clone, "design" for /v1/voice_design. Kept open to
    # accommodate future voice-generation sources without a schema migration.
    source: str = "clone"
    # Free-form name shown in UI (falls back to source_filename / voice_id).
    display_name: str | None = None
    extra: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        if not data.get("extra"):
            data.pop("extra", None)
        return data


class VoiceCloneStore:
    """Append-only style store for cloned voice records."""

    FILENAME = "voice_clones.json"

    def __init__(self, workspace: Path) -> None:
        self.root = workspace
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / self.FILENAME

    def _load(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def _save(self, items: list[dict[str, object]]) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(items, ensure_ascii=False, indent=2, sort_keys=False),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    @staticmethod
    def _parse(entry: dict[str, object]) -> VoiceCloneRecord | None:
        voice_id = entry.get("voice_id")
        if not isinstance(voice_id, str) or not voice_id:
            return None
        raw_source = entry.get("source")
        source = raw_source if isinstance(raw_source, str) and raw_source.strip() else "clone"
        return VoiceCloneRecord(
            voice_id=voice_id,
            model=str(entry.get("model") or ""),
            provider=str(entry.get("provider") or ""),
            created_at=str(entry.get("created_at") or _now_iso()),
            preview_text=entry.get("preview_text") if isinstance(entry.get("preview_text"), str) else None,
            source_filename=entry.get("source_filename")
            if isinstance(entry.get("source_filename"), str)
            else None,
            demo_audio_url=entry.get("demo_audio_url")
            if isinstance(entry.get("demo_audio_url"), str)
            else None,
            demo_attachment_id=entry.get("demo_attachment_id")
            if isinstance(entry.get("demo_attachment_id"), str)
            else None,
            last_kept_alive_at=entry.get("last_kept_alive_at")
            if isinstance(entry.get("last_kept_alive_at"), str)
            else None,
            notes=entry.get("notes") if isinstance(entry.get("notes"), str) else None,
            source=source,
            display_name=entry.get("display_name")
            if isinstance(entry.get("display_name"), str)
            else None,
            extra={
                key: str(value)
                for key, value in (entry.get("extra") or {}).items()
                if isinstance(key, str)
            }
            if isinstance(entry.get("extra"), dict)
            else {},
        )

    def list(self, *, source: str | None = None) -> list[VoiceCloneRecord]:
        records: list[VoiceCloneRecord] = []
        for entry in self._load():
            parsed = self._parse(entry)
            if parsed is None:
                continue
            if source is not None and parsed.source != source:
                continue
            records.append(parsed)
        return sorted(records, key=lambda item: item.created_at, reverse=True)

    def get(self, voice_id: str) -> VoiceCloneRecord | None:
        for record in self.list():
            if record.voice_id == voice_id:
                return record
        return None

    def upsert(self, record: VoiceCloneRecord) -> VoiceCloneRecord:
        items = self._load()
        replaced = False
        serialized = record.to_dict()
        for index, item in enumerate(items):
            if item.get("voice_id") == record.voice_id:
                items[index] = serialized
                replaced = True
                break
        if not replaced:
            items.append(serialized)
        self._save(items)
        return record

    def mark_kept_alive(self, voice_id: str, timestamp: str | None = None) -> VoiceCloneRecord:
        existing = self.get(voice_id)
        if existing is None:
            raise KeyError(voice_id)
        updated = replace(existing, last_kept_alive_at=timestamp or _now_iso())
        return self.upsert(updated)

    def delete(self, voice_id: str) -> VoiceCloneRecord | None:
        items = self._load()
        removed: VoiceCloneRecord | None = None
        next_items = []
        for item in items:
            if item.get("voice_id") == voice_id:
                removed = self._parse(item)
                continue
            next_items.append(item)
        if removed is not None:
            self._save(next_items)
        return removed
