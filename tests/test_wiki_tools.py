import asyncio

import pytest

from tokenmind.agent.tools.wiki import (
    WikiBacklinksTool,
    WikiGraphTool,
    WikiGrepTool,
    WikiIndexTool,
    WikiReadTool,
)
from tokenmind.knowledge.wiki_paths import ensure_wiki_structure


@pytest.fixture
def seeded_kb(tmp_path):
    kb_root = tmp_path / "knowledge" / "kb_t"
    ensure_wiki_structure(kb_root, name="t", description="", language="zh")
    (kb_root / "wiki" / "entities" / "Foo.md").write_text(
        "---\ntype: entity\ntitle: Foo\n---\n# Foo\nMentions [[Bar]].\n", encoding="utf-8",
    )
    (kb_root / "wiki" / "topics" / "Bar.md").write_text(
        "---\ntype: topic\ntitle: Bar\n---\n# Bar\nIs referenced by Foo.\n", encoding="utf-8",
    )
    return kb_root


def _resolver(kb_root):
    """A trivial active KB resolver for tests."""
    def get_active():
        return {"kb_root": kb_root, "kb_name": "t"}
    return get_active


def test_wiki_index_returns_index_md(seeded_kb):
    tool = WikiIndexTool(get_active_kb=_resolver(seeded_kb))
    result = asyncio.run(tool.execute())
    assert "# t" in result  # index.md header


def test_wiki_grep_finds_title(seeded_kb):
    tool = WikiGrepTool(get_active_kb=_resolver(seeded_kb))
    result = asyncio.run(tool.execute(keyword="Foo"))
    assert "Foo" in result
    assert "entities/Foo.md" in result


def test_wiki_read_returns_full_content(seeded_kb):
    tool = WikiReadTool(get_active_kb=_resolver(seeded_kb))
    result = asyncio.run(tool.execute(page_path="wiki/entities/Foo.md"))
    assert "Mentions [[Bar]]" in result


def test_wiki_backlinks_finds_referrers(seeded_kb):
    tool = WikiBacklinksTool(get_active_kb=_resolver(seeded_kb))
    result = asyncio.run(tool.execute(page_path="wiki/topics/Bar.md"))
    assert "Foo" in result


def test_wiki_graph_returns_json(seeded_kb):
    tool = WikiGraphTool(get_active_kb=_resolver(seeded_kb))
    result = asyncio.run(tool.execute())
    assert "nodes" in result
    assert "edges" in result


def test_wiki_tool_returns_error_when_no_active_kb(tmp_path):
    def get_active():
        return None
    tool = WikiGrepTool(get_active_kb=get_active)
    result = asyncio.run(tool.execute(keyword="x"))
    assert "Error" in result
    assert "active" in result.lower()
