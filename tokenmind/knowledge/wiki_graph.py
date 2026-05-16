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
    edges: list[dict] = []
    broken: list[dict] = []

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
        title, ptype, content = _parse_page(path, raw)
        rel = path.relative_to(kb_root)
        nodes_by_title[title] = {
            "id": title,
            "title": title,
            "type": ptype,
            "path": str(rel).replace("\\", "/"),
            "summary": "",
            "degree": 0,
        }
        pages.append((title, path, ptype, content))

    for title, _, _, content in pages:
        for link in _WIKILINK_RE.finditer(content):
            target = link.group(1).strip()
            if target == title:
                continue
            if target in nodes_by_title:
                edges.append({
                    "source": title,
                    "target": target,
                    "relation": "wiki_link",
                    "weight": 1.0,
                })
                nodes_by_title[title]["degree"] += 1
                nodes_by_title[target]["degree"] += 1
            else:
                broken.append({"from": title, "target": target})

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


def _parse_page(path: Path, raw: str) -> tuple[str, str, str]:
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            fm_text, body = parts[1], parts[2]
            fm = {}
            for line in fm_text.strip().splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    fm[k.strip()] = v.strip()
            title = fm.get("title", path.stem)
            ptype = fm.get("type", "page")
            return title, ptype, body
    return path.stem, "page", raw


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
