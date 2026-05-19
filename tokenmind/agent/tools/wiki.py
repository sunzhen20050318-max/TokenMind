"""Tools for the LLM to navigate the active Wiki knowledge base."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from tokenmind.agent.tools.base import Tool
from tokenmind.knowledge.wiki_query import backlinks as wiki_backlinks_query
from tokenmind.knowledge.wiki_query import query_wiki_pages, read_wiki_page

ActiveKbResolver = Callable[[], dict | None]
# Returns {"kb_root": Path, "kb_name": str, "kb_id": str} or None when no active KB.

_NO_ACTIVE = "Error: No active Wiki knowledge base for this session. Ask the user to select one."


class _BaseWikiTool(Tool):
    def __init__(self, get_active_kb: ActiveKbResolver):
        self._get_active = get_active_kb

    def is_available(self) -> bool:
        """Hide the wiki tools from the LLM's tool list when no Wiki KB is
        active. ``ToolRegistry.get_definitions()`` filters on this."""
        return self._get_active() is not None

    def _resolve(self) -> tuple[Path, str] | None:
        active = self._get_active()
        if not active:
            return None
        return Path(active["kb_root"]), str(active.get("kb_name", ""))


class WikiIndexTool(_BaseWikiTool):
    @property
    def name(self) -> str:
        return "wiki_index"

    @property
    def description(self) -> str:
        return (
            "Return the index.md of the currently active Wiki knowledge base. "
            "Call this FIRST to understand the KB structure before grepping."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> str:
        ctx = self._resolve()
        if ctx is None:
            return _NO_ACTIVE
        kb_root, _ = ctx
        index = kb_root / "index.md"
        if not index.is_file():
            return "Error: index.md missing"
        return index.read_text(encoding="utf-8")


class WikiGrepTool(_BaseWikiTool):
    @property
    def name(self) -> str:
        return "wiki_grep"

    @property
    def description(self) -> str:
        return (
            "Search the active Wiki KB for pages matching the keyword. "
            "Returns up to top_k page paths with snippets. Follow [[links]] inside snippets with wiki_read."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "keyword to search"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
            },
            "required": ["keyword"],
        }

    async def execute(self, *, keyword: str, top_k: int = 5) -> str:
        ctx = self._resolve()
        if ctx is None:
            return _NO_ACTIVE
        kb_root, _ = ctx
        hits = query_wiki_pages(kb_root, keyword, top_k=top_k, expand_depth=1)
        if not hits:
            return f"No pages matched '{keyword}'."
        lines = [f"Found {len(hits)} page(s):"]
        for hit in hits:
            lines.append(f"- [{hit['type']}] {hit['title']} ({hit['path']})")
            lines.append(f"  {hit['snippet']}")
        return "\n".join(lines)


class WikiReadTool(_BaseWikiTool):
    @property
    def name(self) -> str:
        return "wiki_read"

    @property
    def description(self) -> str:
        return (
            "Read the full content of a Wiki page by its relative path "
            "(e.g. 'wiki/entities/Foo.md'). Follow [[links]] you see in the content with another wiki_read."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "page_path": {"type": "string", "description": "path relative to KB root, e.g. 'wiki/entities/Foo.md'"},
            },
            "required": ["page_path"],
        }

    async def execute(self, *, page_path: str) -> str:
        ctx = self._resolve()
        if ctx is None:
            return _NO_ACTIVE
        kb_root, _ = ctx
        try:
            page = read_wiki_page(kb_root, page_path)
        except FileNotFoundError:
            return f"Error: page not found: {page_path}"
        except ValueError as exc:
            return f"Error: {exc}"
        content = page["content"]
        if len(content) > 4000:
            content = content[:4000] + "\n\n[... page truncated; ask for specific sections ...]"
        return (
            f"# {page['title']}\n"
            f"Type: {page['type']}\n"
            f"Path: {page['path']}\n\n"
            f"{content}"
        )


class WikiBacklinksTool(_BaseWikiTool):
    @property
    def name(self) -> str:
        return "wiki_backlinks"

    @property
    def description(self) -> str:
        return "List pages that link to the given page via [[title]]."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"page_path": {"type": "string"}},
            "required": ["page_path"],
        }

    async def execute(self, *, page_path: str) -> str:
        ctx = self._resolve()
        if ctx is None:
            return _NO_ACTIVE
        kb_root, _ = ctx
        try:
            page = read_wiki_page(kb_root, page_path)
        except FileNotFoundError:
            return f"Error: page not found: {page_path}"
        refs = wiki_backlinks_query(kb_root, page["title"])
        if not refs:
            return f"No backlinks to [[{page['title']}]]."
        lines = [f"{len(refs)} page(s) link to [[{page['title']}]]:"]
        for r in refs:
            lines.append(f"- [{r['type']}] {r['title']} ({r['path']})")
        return "\n".join(lines)


class WikiGraphTool(_BaseWikiTool):
    @property
    def name(self) -> str:
        return "wiki_graph"

    @property
    def description(self) -> str:
        return "Return the full link graph (nodes + edges) of the active KB. Heavy for large KBs."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> str:
        ctx = self._resolve()
        if ctx is None:
            return _NO_ACTIVE
        kb_root, _ = ctx
        graph_file = kb_root / "graph-data.json"
        if not graph_file.is_file():
            return json.dumps({"nodes": [], "edges": [], "note": "graph not built yet"})
        return graph_file.read_text(encoding="utf-8")
