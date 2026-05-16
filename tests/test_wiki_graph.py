from tokenmind.knowledge.wiki_graph import build_graph_data
from tokenmind.knowledge.wiki_paths import ensure_wiki_structure


def test_build_graph_extracts_nodes_and_edges(tmp_path):
    kb = tmp_path / "knowledge" / "g"
    ensure_wiki_structure(kb, name="g", description="", language="zh")
    (kb / "wiki" / "entities" / "TokenMind.md").write_text(
        "---\ntype: entity\ntitle: TokenMind\n---\n# TokenMind\nUses [[Wiki-first 知识库]].\n",
        encoding="utf-8",
    )
    (kb / "wiki" / "topics" / "Wiki-first 知识库.md").write_text(
        "---\ntype: topic\ntitle: Wiki-first 知识库\n---\n# Wiki-first 知识库\nReferenced by [[TokenMind]].\n",
        encoding="utf-8",
    )

    graph = build_graph_data(kb)
    node_ids = {n["id"] for n in graph["nodes"]}
    assert "TokenMind" in node_ids
    assert "Wiki-first 知识库" in node_ids
    # 双向链接 produces both edges
    edge_pairs = {(e["source"], e["target"]) for e in graph["edges"]}
    assert ("TokenMind", "Wiki-first 知识库") in edge_pairs


def test_build_graph_persists_to_graph_data_json(tmp_path):
    import json
    kb = tmp_path / "knowledge" / "g"
    ensure_wiki_structure(kb, name="g", description="", language="zh")
    (kb / "wiki" / "entities" / "X.md").write_text(
        "---\ntype: entity\ntitle: X\n---\n# X\n", encoding="utf-8")

    build_graph_data(kb, persist=True)
    data = json.loads((kb / "graph-data.json").read_text())
    assert data["nodes"][0]["id"] == "X"
    assert data["updated_at"] is not None
