"""Wiki ingest pipeline: raw → source page → (later) entity/topic pages."""
from __future__ import annotations

from datetime import datetime, timezone


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
