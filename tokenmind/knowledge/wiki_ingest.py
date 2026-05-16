"""Wiki ingest pipeline: raw → source page → (later) entity/topic pages."""
from __future__ import annotations

import json
import re
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

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
        f"（待 LLM 编译生成摘要）\n\n"
        f"## 内容节选\n\n"
        f"{excerpt}\n\n"
        f"## 原始资料\n\n"
        f"- 路径：{raw_path}\n"
        f"- SHA256：{sha256}\n\n"
        f"## 关联\n\n"
        f"- [[待归类主题]]\n"
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
        max_tokens=4000,
    )
    raw = (response.content or "").strip()
    raw = re.sub(r"^```(json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"_fallback": True, "error": str(exc), "raw": raw[:500]}

    for entity in data.get("entities", []):
        _write_or_merge_page(
            kb_root=kb_root,
            page_type="entity",
            data=entity,
            source_page_id=source_page_id,
        )
    for topic in data.get("topics", []):
        _write_or_merge_page(
            kb_root=kb_root,
            page_type="topic",
            data=topic,
            source_page_id=source_page_id,
        )
    return data


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
