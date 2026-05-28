"""Site login registry — user-curated list of websites + login state.

Auto-detecting login state across arbitrary sites is unreliable (captchas,
SPA redirects, cookie-only sessions). Instead we let the user declare:
this is the site I care about, this is its URL, and I'm logged in here.

The BrowserTool consults this registry before driving the browser: if the
URL maps to a known entry that's marked ``logged_in=false``, we pause and
ask the user to log in first via the same handoff modal used elsewhere.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_SCHEMA_VERSION = 1


@dataclass
class SiteEntry:
    id: str
    name: str
    url: str
    hostname: str
    logged_in: bool
    is_preset: bool
    adapter: str | None = None
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_hostname(value: str) -> str:
    """Lowercase + strip leading ``www.`` so ``www.foo.com`` matches ``foo.com``."""
    host = (value or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def hostname_from_url(url: str) -> str:
    """Best-effort hostname extraction from a URL or bare hostname."""
    raw = (url or "").strip()
    if not raw:
        return ""
    # urlparse needs a scheme to recognise the netloc; if the user typed
    # just ``xiaohongshu.com``, treat the whole string as the host.
    if "://" not in raw:
        host = raw.split("/", 1)[0]
        return _normalize_hostname(host)
    parsed = urlparse(raw)
    return _normalize_hostname(parsed.hostname or parsed.netloc)


# Curated defaults — covers the sites people actually want TokenMind to
# operate. Users can disable (mark not-logged-in) or rename, but presets
# are not deletable so a fresh install always has the sensible starter set.
_PRESETS: list[dict[str, Any]] = [
    {"name": "小红书", "url": "https://www.xiaohongshu.com", "adapter": "xiaohongshu"},
    {"name": "哔哩哔哩", "url": "https://www.bilibili.com", "adapter": "bilibili"},
    {"name": "微博", "url": "https://weibo.com", "adapter": "weibo"},
    {"name": "知乎", "url": "https://www.zhihu.com", "adapter": "zhihu"},
    {"name": "抖音", "url": "https://www.douyin.com", "adapter": None},
    {"name": "淘宝", "url": "https://www.taobao.com", "adapter": None},
    {"name": "京东", "url": "https://www.jd.com", "adapter": None},
    {"name": "X (Twitter)", "url": "https://x.com", "adapter": "twitter"},
    {"name": "YouTube", "url": "https://www.youtube.com", "adapter": "youtube"},
    {"name": "GitHub", "url": "https://github.com", "adapter": "github"},
    {"name": "Reddit", "url": "https://www.reddit.com", "adapter": "reddit"},
    {"name": "Hacker News", "url": "https://news.ycombinator.com", "adapter": "hackernews"},
]


class SiteRegistry:
    """JSON-backed registry of sites + user-declared login state.

    Thread-safe via a single lock — load/save/update all serialize. The
    file lives at ``<config_dir>/sites.json`` so it persists across
    workspaces (login state belongs to the Chrome profile, not the repo).
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._entries: dict[str, SiteEntry] = {}
        self._load()
        self._ensure_presets()

    @property
    def path(self) -> Path:
        return self._path

    # --- persistence ---------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        items = raw.get("sites") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                entry = SiteEntry(
                    id=str(item["id"]),
                    name=str(item.get("name", "")).strip() or "Untitled",
                    url=str(item.get("url", "")).strip(),
                    hostname=_normalize_hostname(str(item.get("hostname", ""))),
                    logged_in=bool(item.get("logged_in", False)),
                    is_preset=bool(item.get("is_preset", False)),
                    adapter=(item.get("adapter") or None),
                    updated_at=float(item.get("updated_at") or time.time()),
                )
            except (KeyError, ValueError, TypeError):
                continue
            if not entry.hostname:
                entry.hostname = hostname_from_url(entry.url)
            if entry.hostname:
                self._entries[entry.id] = entry

    def _save_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": _SCHEMA_VERSION,
            "sites": [e.to_dict() for e in self._entries.values()],
        }
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def _ensure_presets(self) -> None:
        """Add any missing preset entries on startup.

        Idempotent — matches by ``adapter`` first (stable identifier), then
        by normalized hostname (covers presets without an adapter). Existing
        user toggles / renames are preserved.
        """
        with self._lock:
            existing_hosts = {e.hostname for e in self._entries.values() if e.hostname}
            existing_adapters = {
                e.adapter for e in self._entries.values() if e.adapter
            }
            changed = False
            for preset in _PRESETS:
                hostname = hostname_from_url(preset["url"])
                adapter = preset.get("adapter") or None
                if adapter and adapter in existing_adapters:
                    continue
                if hostname in existing_hosts:
                    continue
                entry = SiteEntry(
                    id=uuid.uuid4().hex,
                    name=preset["name"],
                    url=preset["url"],
                    hostname=hostname,
                    logged_in=False,
                    is_preset=True,
                    adapter=adapter,
                )
                self._entries[entry.id] = entry
                existing_hosts.add(hostname)
                if adapter:
                    existing_adapters.add(adapter)
                changed = True
            if changed:
                self._save_locked()

    # --- read ----------------------------------------------------------

    def list(self) -> list[SiteEntry]:
        """Return all entries, presets first then by name."""
        with self._lock:
            entries = list(self._entries.values())
        entries.sort(key=lambda e: (not e.is_preset, e.name.lower()))
        return entries

    def get(self, entry_id: str) -> SiteEntry | None:
        with self._lock:
            return self._entries.get(entry_id)

    def find_by_url(self, url: str) -> SiteEntry | None:
        """Look up an entry whose hostname matches the URL's hostname.

        Returns the most-specific match if multiple entries share a
        suffix (e.g. ``mail.google.com`` over ``google.com``).
        """
        target = hostname_from_url(url)
        if not target:
            return None
        with self._lock:
            entries = list(self._entries.values())
        best: SiteEntry | None = None
        for entry in entries:
            if not entry.hostname:
                continue
            if entry.hostname == target or target.endswith("." + entry.hostname):
                if best is None or len(entry.hostname) > len(best.hostname):
                    best = entry
        return best

    def find_by_adapter(self, adapter: str) -> SiteEntry | None:
        if not adapter:
            return None
        adapter = adapter.strip()
        with self._lock:
            for entry in self._entries.values():
                if entry.adapter and entry.adapter == adapter:
                    return entry
        return None

    # --- write ---------------------------------------------------------

    def add(self, *, name: str, url: str, adapter: str | None = None) -> SiteEntry:
        name = (name or "").strip()
        url = (url or "").strip()
        if not name:
            raise ValueError("name is required")
        if not url:
            raise ValueError("url is required")
        hostname = hostname_from_url(url)
        if not hostname:
            raise ValueError("url must contain a hostname")
        with self._lock:
            for entry in self._entries.values():
                if entry.hostname == hostname:
                    raise ValueError(f"site with hostname '{hostname}' already exists")
            entry = SiteEntry(
                id=uuid.uuid4().hex,
                name=name,
                url=url,
                hostname=hostname,
                logged_in=False,
                is_preset=False,
                adapter=(adapter or None),
            )
            self._entries[entry.id] = entry
            self._save_locked()
            return entry

    def update(
        self,
        entry_id: str,
        *,
        name: str | None = None,
        url: str | None = None,
        logged_in: bool | None = None,
    ) -> SiteEntry:
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                raise KeyError(entry_id)
            if name is not None:
                stripped = name.strip()
                if not stripped:
                    raise ValueError("name cannot be empty")
                entry.name = stripped
            if url is not None:
                stripped_url = url.strip()
                if not stripped_url:
                    raise ValueError("url cannot be empty")
                hostname = hostname_from_url(stripped_url)
                if not hostname:
                    raise ValueError("url must contain a hostname")
                for other in self._entries.values():
                    if other.id != entry.id and other.hostname == hostname:
                        raise ValueError(
                            f"another site already uses hostname '{hostname}'"
                        )
                entry.url = stripped_url
                entry.hostname = hostname
            if logged_in is not None:
                entry.logged_in = bool(logged_in)
            entry.updated_at = time.time()
            self._save_locked()
            return entry

    def remove(self, entry_id: str) -> None:
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                raise KeyError(entry_id)
            if entry.is_preset:
                raise ValueError("preset entries cannot be removed")
            del self._entries[entry_id]
            self._save_locked()
