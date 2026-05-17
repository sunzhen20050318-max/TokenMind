"""Scan wiki/ pages and build a [[link]] graph."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")


def build_graph_data(kb_root: Path, *, persist: bool = False) -> dict:
    wiki_dir = kb_root / "wiki"
    nodes_by_title: dict[str, dict] = {}
    title_aliases: dict[str, str] = {}  # alias_or_id → canonical title
    edges: list[dict] = []
    broken: list[dict] = []
    seen_edges: set[tuple[str, str]] = set()

    if not wiki_dir.is_dir():
        graph = {"nodes": [], "edges": [], "broken_links": [], "updated_at": _now()}
        if persist:
            (kb_root / "graph-data.json").write_text(
                json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return graph

    pages: list[tuple[str, Path, str, str]] = []  # (title, abs_path, page_type, content)
    for path in wiki_dir.rglob("*.md"):
        raw = path.read_text(encoding="utf-8")
        title, ptype, content, page_id, aliases = _parse_page(path, raw)
        rel = path.relative_to(kb_root)
        nodes_by_title[title] = {
            "id": title,
            "title": title,
            "type": ptype,
            "path": str(rel).replace("\\", "/"),
            "summary": "",
            "degree": 0,
        }
        # Index alternative ways to reach this page.
        title_aliases[title] = title
        if page_id:
            title_aliases[page_id] = title
        for alias in aliases:
            title_aliases.setdefault(alias, title)
        # Whitespace-normalized variant so [[Wiki-first 知识库]] resolves to
        # `Wiki-first知识库` and vice versa.
        title_aliases.setdefault(_normalize(title), title)
        pages.append((title, path, ptype, content))

    for title, _, _, content in pages:
        for link in _WIKILINK_RE.finditer(content):
            raw_target = link.group(1).strip()
            target = title_aliases.get(raw_target) or title_aliases.get(_normalize(raw_target))
            if not target or target == title:
                if not target:
                    broken.append({"from": title, "target": raw_target})
                continue
            key = (title, target)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges.append({
                "source": title,
                "target": target,
                "relation": "wiki_link",
                "weight": 1.0,
            })
            nodes_by_title[title]["degree"] += 1
            nodes_by_title[target]["degree"] += 1

    graph = {
        "nodes": list(nodes_by_title.values()),
        "edges": edges,
        "broken_links": broken,
        "updated_at": _now(),
    }
    if persist:
        (kb_root / "graph-data.json").write_text(
            json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return graph


def _parse_page(path: Path, raw: str) -> tuple[str, str, str, str, list[str]]:
    """Return (title, type, body, page_id, aliases)."""
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            fm_text, body = parts[1], parts[2]
            fm: dict[str, str] = {}
            aliases: list[str] = []
            current_list_key: str | None = None
            for line in fm_text.splitlines():
                if not line.strip():
                    current_list_key = None
                    continue
                # YAML block list item: "  - alias"
                if line.lstrip().startswith("-") and current_list_key == "aliases":
                    item = line.lstrip()[1:].strip()
                    if item:
                        aliases.append(item)
                    continue
                if ":" in line and not line.startswith(" "):
                    key, _, value = line.partition(":")
                    value = value.strip()
                    fm[key.strip()] = value
                    current_list_key = key.strip() if value == "" else None
            title = fm.get("title", path.stem)
            ptype = fm.get("type", "page")
            page_id = fm.get("id", "")
            return title, ptype, body, page_id, aliases
    return path.stem, "page", raw, "", []


def _normalize(s: str) -> str:
    """Strip ASCII and CJK whitespace so '[[Wiki-first 知识库]]' matches
    the on-disk title 'Wiki-first知识库'."""
    return "".join(s.split()).lower()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
