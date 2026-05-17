"""Wiki ingest pipeline: raw → source page → (later) entity/topic pages."""
from __future__ import annotations

import json
import re
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from tokenmind.knowledge.wiki_paths import safe_wiki_filename
from tokenmind.knowledge.wiki_prompts import (
    build_compile_system_prompt,
    build_compile_user_prompt,
)


def compile_source_page_template(
    *,
    page_id: str,
    source_id: str,
    title: str,
    raw_path: str,
    sha256: str,
    body_text: str,
    max_excerpt: int = 800,
) -> str:
    """Build a deterministic source page (no LLM)."""
    now = datetime.now(timezone.utc).isoformat()
    excerpt = body_text.strip()
    if len(excerpt) > max_excerpt:
        excerpt = excerpt[: max_excerpt - 3] + "..."

    return (
        f"---\n"
        f"id: {page_id}\n"
        f"type: source\n"
        f"source_id: {source_id}\n"
        f"title: {title}\n"
        f"created_at: {now}\n"
        f"updated_at: {now}\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"## 摘要\n\n"
        f"## 内容节选\n\n"
        f"{excerpt}\n\n"
        f"## 原始资料\n\n"
        f"- 路径：{raw_path}\n"
        f"- SHA256：{sha256}\n\n"
        f"## 提到的概念\n"
    )


async def compile_with_llm(
    *,
    provider,
    model: str,
    kb_root: Path,
    source_title: str,
    source_text: str,
    source_page_id: str,
    language: str = "zh",
) -> dict:
    """Call LLM to compile source into entity/topic pages. Returns parsed JSON.

    On JSON parse failure, returns {"_fallback": true, "error": ...} and does NOT write pages.
    Caller decides whether to retry or accept template-only source page.
    """
    purpose = _read_purpose(kb_root)
    existing_titles = _scan_existing_titles(kb_root)
    sys_msg = build_compile_system_prompt(language=language)
    user_msg = build_compile_user_prompt(
        purpose=purpose,
        existing_titles=existing_titles,
        source_title=source_title,
        source_text=source_text,
    )
    response = await provider.chat(
        messages=[
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ],
        model=model,
        max_tokens=8000,
    )
    raw = (response.content or "").strip()
    cleaned = _extract_json_payload(raw)
    data = _try_parse_json(cleaned)
    if data is None:
        # One repair retry: ask the LLM to fix the JSON it just emitted.
        repaired_raw = await _repair_json_via_llm(provider, model, cleaned)
        if repaired_raw:
            data = _try_parse_json(_extract_json_payload(repaired_raw))
    if data is None:
        logger.warning(
            "wiki compile JSON parse failed after repair (cleaned head: {!r})",
            cleaned[:300],
        )
        return {"_fallback": True, "error": "json parse failed", "raw": raw[:500]}

    entities = data.get("entities", []) or []
    topics = data.get("topics", []) or []
    logger.info(
        "wiki compile parsed: entities={} topics={} for {}",
        len(entities), len(topics), source_title,
    )
    for entity in entities:
        _write_or_merge_page(
            kb_root=kb_root,
            page_type="entity",
            data=entity,
            source_page_id=source_page_id,
        )
    for topic in topics:
        _write_or_merge_page(
            kb_root=kb_root,
            page_type="topic",
            data=topic,
            source_page_id=source_page_id,
        )
    return data


_THINK_BLOCK_RE = re.compile(r"<\s*(think|thinking|reasoning)\b[^>]*>.*?<\s*/\s*\1\s*>", re.IGNORECASE | re.DOTALL)
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n?|\n?```", re.IGNORECASE)


def _try_parse_json(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


async def _repair_json_via_llm(provider, model: str, broken_json: str) -> str | None:
    """Ask the LLM to fix its own broken JSON. Returns the repaired raw text
    or None on failure. Cheap because we only ship the broken payload, not
    the original source material."""
    try:
        response = await provider.chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You repair invalid JSON. Output ONLY a valid JSON object that "
                        "preserves the original structure and content. Do not add commentary, "
                        "do not wrap in code fences."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Fix this JSON:\n\n{broken_json[:12000]}",
                },
            ],
            model=model,
            max_tokens=8000,
        )
        return (response.content or "").strip()
    except Exception as exc:
        logger.warning(f"JSON repair call failed: {exc}")
        return None


def _extract_json_payload(raw: str) -> str:
    """Pull the JSON object out of an LLM response that may be wrapped in
    ``<think>`` blocks (reasoning models), ```` ```json ```` code fences, or
    surrounded by prose. Returns the substring most likely to parse as JSON,
    or the original string if no obvious wrapper is detected."""
    text = _THINK_BLOCK_RE.sub("", raw).strip()
    text = _CODE_FENCE_RE.sub("", text).strip()
    # Find the outermost balanced { ... } region.
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def _read_purpose(kb_root: Path) -> str:
    purpose_file = kb_root / "purpose.md"
    return purpose_file.read_text(encoding="utf-8") if purpose_file.is_file() else ""


def _scan_existing_titles(kb_root: Path) -> list[str]:
    titles: list[str] = []
    for sub in ("entities", "topics"):
        d = kb_root / "wiki" / sub
        if d.is_dir():
            titles.extend(p.stem for p in d.glob("*.md"))
    return titles


def _write_or_merge_page(*, kb_root: Path, page_type: str, data: dict, source_page_id: str) -> None:
    title = data.get("title", "untitled").strip()
    safe = safe_wiki_filename(title)
    dir_name = "entities" if page_type == "entity" else "topics"
    path = kb_root / "wiki" / dir_name / f"{safe}.md"
    now = datetime.now(timezone.utc).isoformat()

    summary = data.get("summary", "").strip()
    content = data.get("content", "").strip()
    links = data.get("links", [])
    aliases = data.get("aliases", []) if page_type == "entity" else []
    link_block = "\n".join(f"- [[{link}]]" for link in links) or "- 暂无"

    if path.exists():
        # Append a "New from {source}" section; do not rewrite existing body.
        body = path.read_text(encoding="utf-8")
        addition = (
            f"\n\n## 新增信息（来自 [[{source_page_id}]] · {now}）\n\n"
            f"{summary}\n\n{content}\n"
        )
        path.write_text(body + addition, encoding="utf-8")
        return

    frontmatter = (
        f"---\n"
        f"id: page_{_uuid.uuid4().hex[:10]}\n"
        f"type: {page_type}\n"
        f"title: {title}\n"
        + ("aliases:\n" + "".join(f"  - {a}\n" for a in aliases) if aliases else "")
        + f"sources:\n  - {source_page_id}\n"
        f"created_at: {now}\n"
        f"updated_at: {now}\n"
        f"---\n\n"
    )
    section = "关联主题" if page_type == "entity" else "相关页面"
    body = (
        f"# {title}\n\n"
        f"## 摘要\n\n{summary}\n\n"
        f"## 内容\n\n{content}\n\n"
        f"## {section}\n\n{link_block}\n\n"
        f"## 来源\n\n- [[{source_page_id}]]\n"
    )
    path.write_text(frontmatter + body, encoding="utf-8")
