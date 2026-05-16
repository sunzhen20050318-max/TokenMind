"""Path helpers for Wiki-type knowledge bases."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

_WIKI_DIRS = (
    "raw/files",
    "raw/webpages",
    "raw/chats",
    "raw/notes",
    "raw/assets",
    "wiki/sources",
    "wiki/entities",
    "wiki/topics",
    "wiki/comparisons",
    "wiki/synthesis/sessions",
    "wiki/queries",
)


def get_kb_root(workspace: Path, kb_id: str) -> Path:
    return Path(workspace) / "knowledge" / kb_id


def safe_wiki_filename(title: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]", "", title).strip()
    cleaned = re.sub(r"\s+", "-", cleaned)
    return cleaned or "untitled"


def ensure_wiki_structure(
    kb_root: Path,
    *,
    name: str,
    description: str,
    language: str = "zh",
) -> None:
    kb_root.mkdir(parents=True, exist_ok=True)
    for rel in _WIKI_DIRS:
        (kb_root / rel).mkdir(parents=True, exist_ok=True)

    purpose = (
        f"# 知识库目标\n\n"
        f"名称：{name}\n\n"
        f"描述：{description}\n\n"
        f"语言：{'中文' if language == 'zh' else 'English'}\n\n"
        "本知识库使用 TokenMind Wiki-first 模式：\n"
        "- raw/ 保存原始资料\n"
        "- wiki/ 保存 AI 编译后的 Markdown 页面\n"
        "- [[双向链接]] 连接实体、主题、来源\n"
        "- graph-data.json 保存图谱数据\n"
    )
    index = f"# {name}\n\n## 入口\n\n- [[资料来源]]\n- [[核心主题]]\n- [[重要实体]]\n\n## 最近更新\n\n暂无。\n"
    schema = (
        "# Wiki Schema\n\n## 页面类型\n\n- source：原始资料摘要\n"
        "- entity：实体、工具、人物、概念\n- topic：主题\n"
        "- comparison：对比分析\n- synthesis：综合分析\n- query：保存的查询\n\n"
        "## 链接规则\n\n使用 `[[页面标题]]` 连接相关知识。\n"
    )
    cache = {"version": 1, "sources": {}, "pages": {}, "updated_at": None}
    graph = {"nodes": [], "edges": [], "updated_at": None}

    _write_if_absent(kb_root / "purpose.md", purpose)
    _write_if_absent(kb_root / "index.md", index)
    _write_if_absent(kb_root / "log.md", f"# Log\n\n创建于 {datetime.now(timezone.utc).isoformat()}\n")
    _write_if_absent(kb_root / ".wiki-schema.md", schema)
    _write_if_absent(kb_root / ".wiki-cache.json", json.dumps(cache, ensure_ascii=False, indent=2))
    _write_if_absent(kb_root / "graph-data.json", json.dumps(graph, ensure_ascii=False, indent=2))


def _write_if_absent(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8")
