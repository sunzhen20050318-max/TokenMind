from tokenmind.knowledge.wiki_prompts import (
    build_compile_system_prompt,
    build_compile_user_prompt,
)


def test_system_prompt_includes_schema_and_json_format():
    sys = build_compile_system_prompt(language="zh")
    assert "entities" in sys
    assert "topics" in sys
    assert "JSON" in sys.upper() or "json" in sys
    assert "[[" in sys  # 提到双向链接


def test_user_prompt_includes_source_and_context():
    user = build_compile_user_prompt(
        purpose="研究 AI 论文",
        existing_titles=["GraphRAG", "RAG"],
        source_title="LightRAG 论文",
        source_text="LightRAG 是一种轻量级 RAG ...",
    )
    assert "研究 AI 论文" in user
    assert "GraphRAG" in user
    assert "LightRAG" in user
    assert "轻量级 RAG" in user


def test_compile_with_llm_writes_entity_and_topic_pages(tmp_path):
    from tokenmind.knowledge.wiki_ingest import compile_with_llm
    from tokenmind.knowledge.wiki_paths import ensure_wiki_structure

    kb_root = tmp_path / "knowledge" / "kb_x"
    ensure_wiki_structure(kb_root, name="AI", description="papers", language="zh")

    class FakeProvider:
        async def chat(self, messages, **kwargs):
            payload = {
                "source_summary": {
                    "title": "LightRAG paper",
                    "summary": "Lightweight RAG variant.",
                    "key_points": ["fast", "memory-efficient"],
                },
                "entities": [{
                    "title": "LightRAG",
                    "type": "project",
                    "summary": "A lightweight RAG.",
                    "content": "LightRAG reduces overhead.",
                    "aliases": ["light-rag"],
                    "links": ["RAG"],
                }],
                "topics": [{
                    "title": "图谱检索",
                    "summary": "Graph-based retrieval methods.",
                    "content": "Methods that use graphs.",
                    "links": ["LightRAG"],
                }],
            }
            return type("R", (), {
                "content": __import__("json").dumps(payload),
                "tool_calls": [],
                "finish_reason": "stop",
                "usage": None,
                "reasoning_content": None,
                "thinking_blocks": None,
            })()

    import asyncio
    asyncio.run(compile_with_llm(
        provider=FakeProvider(),
        model="fake",
        kb_root=kb_root,
        source_title="LightRAG paper",
        source_text="LightRAG is a lightweight ...",
        source_page_id="page_src1",
    ))

    assert (kb_root / "wiki" / "entities" / "LightRAG.md").is_file()
    assert (kb_root / "wiki" / "topics" / "图谱检索.md").is_file()
    body = (kb_root / "wiki" / "entities" / "LightRAG.md").read_text(encoding="utf-8")
    assert "[[RAG]]" in body
