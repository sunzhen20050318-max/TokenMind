from tokenmind.knowledge.wiki_paths import ensure_wiki_structure
from tokenmind.knowledge.wiki_query import query_wiki_pages, read_wiki_page


def _seed(tmp_path):
    kb = tmp_path / "knowledge" / "kb1"
    ensure_wiki_structure(kb, name="kb1", description="", language="zh")
    (kb / "wiki" / "entities" / "GraphRAG.md").write_text(
        "---\nid: p1\ntype: entity\ntitle: GraphRAG\n---\n# GraphRAG\nA retrieval framework using [[图谱检索]].\n",
        encoding="utf-8",
    )
    (kb / "wiki" / "topics" / "图谱检索.md").write_text(
        "---\nid: p2\ntype: topic\ntitle: 图谱检索\n---\n# 图谱检索\nMethods that use graphs; see [[GraphRAG]].\n",
        encoding="utf-8",
    )
    return kb


def test_query_returns_pages_by_title(tmp_path):
    kb = _seed(tmp_path)
    hits = query_wiki_pages(kb, "GraphRAG", top_k=5)
    titles = [h["title"] for h in hits]
    assert "GraphRAG" in titles


def test_query_expands_via_wikilink(tmp_path):
    """Query 'GraphRAG' should also surface '图谱检索' via [[link]] expansion."""
    kb = _seed(tmp_path)
    hits = query_wiki_pages(kb, "GraphRAG", top_k=5, expand_depth=1)
    titles = {h["title"] for h in hits}
    assert "GraphRAG" in titles
    assert "图谱检索" in titles


def test_read_wiki_page_returns_content_and_frontmatter(tmp_path):
    kb = _seed(tmp_path)
    page = read_wiki_page(kb, "wiki/entities/GraphRAG.md")
    assert page["title"] == "GraphRAG"
    assert page["type"] == "entity"
    assert "[[图谱检索]]" in page["content"]
