"""Wiki query: lexical match + double-link expansion."""
from __future__ import annotations

import re
from pathlib import Path

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")


def query_wiki_pages(
    kb_root: Path,
    query: str,
    *,
    top_k: int = 5,
    expand_depth: int = 1,
) -> list[dict]:
    """Return list of {title, path, type, summary, content (snippet), score, matched_via}."""
    query = (query or "").strip()
    if not query:
        return []
    pages = _scan_pages(kb_root)
    q_lower = query.lower()

    scored: list[dict] = []
    for page in pages:
        score = 0
        matched_via = []
        title_lower = page["title"].lower()
        if q_lower == title_lower:
            score += 10
            matched_via.append("title_exact")
        elif q_lower in title_lower:
            score += 6
            matched_via.append("title_substr")
        body_lower = page["content"].lower()
        body_hits = body_lower.count(q_lower)
        if body_hits:
            score += min(body_hits, 4)
            matched_via.append(f"body_x{body_hits}")
        if score > 0:
            page["score"] = score
            page["matched_via"] = matched_via
            scored.append(page)

    scored.sort(key=lambda p: -p["score"])
    direct = scored[:top_k]

    if expand_depth <= 0 or not direct:
        return [_snippet(p, query) for p in direct]

    seen = {p["path"] for p in direct}
    expanded = list(direct)
    for page in direct:
        for link in _extract_wikilinks(page["content"]):
            for candidate in pages:
                if candidate["title"] == link and candidate["path"] not in seen:
                    candidate["score"] = 1
                    candidate["matched_via"] = [f"link_from:{page['title']}"]
                    expanded.append(candidate)
                    seen.add(candidate["path"])
    return [_snippet(p, query) for p in expanded[: top_k * 2]]


def read_wiki_page(kb_root: Path, page_path: str) -> dict:
    """Return {title, type, path, frontmatter, content, outgoing_links}."""
    rel = Path(page_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"page_path must be relative within kb: {page_path}")
    full = kb_root / rel
    if not full.is_file():
        raise FileNotFoundError(f"page not found: {page_path}")
    raw = full.read_text(encoding="utf-8")
    frontmatter, content = _split_frontmatter(raw)
    return {
        "title": frontmatter.get("title", rel.stem),
        "type": frontmatter.get("type", _type_from_path(rel)),
        "path": str(rel).replace("\\", "/"),
        "frontmatter": frontmatter,
        "content": content,
        "outgoing_links": _extract_wikilinks(content),
    }


def backlinks(kb_root: Path, target_title: str) -> list[dict]:
    """Pages whose content contains [[target_title]]."""
    out = []
    for page in _scan_pages(kb_root):
        if target_title in _extract_wikilinks(page["content"]):
            out.append({"title": page["title"], "path": page["path"], "type": page["type"]})
    return out


def _scan_pages(kb_root: Path) -> list[dict]:
    pages: list[dict] = []
    wiki_dir = kb_root / "wiki"
    if not wiki_dir.is_dir():
        return pages
    for path in wiki_dir.rglob("*.md"):
        raw = path.read_text(encoding="utf-8")
        fm, content = _split_frontmatter(raw)
        rel = path.relative_to(kb_root)
        pages.append({
            "title": fm.get("title", path.stem),
            "type": fm.get("type", _type_from_path(rel)),
            "path": str(rel).replace("\\", "/"),
            "content": content,
        })
    return pages


# Public alias for callers outside this module (Task 23's API route will use this)
scan_pages = _scan_pages


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    _, fm_text, body = parts
    fm: dict = {}
    for line in fm_text.strip().splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm, body.lstrip("\n")


def _extract_wikilinks(text: str) -> list[str]:
    return [m.group(1).strip() for m in _WIKILINK_RE.finditer(text)]


def _type_from_path(rel: Path) -> str:
    mapping = {"entities": "entity", "topics": "topic", "sources": "source",
               "comparisons": "comparison", "synthesis": "synthesis", "queries": "query"}
    parts = rel.parts
    if len(parts) >= 2 and parts[0] == "wiki":
        return mapping.get(parts[1], "page")
    return "page"


def _snippet(page: dict, query: str, ctx_chars: int = 120) -> dict:
    body = page["content"]
    lower = body.lower()
    idx = lower.find(query.lower())
    if idx < 0:
        snippet = body[:240]
    else:
        start = max(0, idx - ctx_chars)
        end = min(len(body), idx + len(query) + ctx_chars)
        snippet = ("..." if start > 0 else "") + body[start:end] + ("..." if end < len(body) else "")
    return {
        "title": page["title"],
        "type": page["type"],
        "path": page["path"],
        "snippet": " ".join(snippet.split())[:400],
        "score": page.get("score", 0),
        "matched_via": page.get("matched_via", []),
    }
