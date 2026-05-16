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
