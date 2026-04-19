from __future__ import annotations

from tokenmind.knowledge.chunking import semantic_chunks, simple_chunks


def test_simple_chunks_splits_long_paragraph_by_sentence() -> None:
    text = (
        "TokenMind 可以管理知识库和文件。"
        "它支持会话级链接知识库。"
        "用户可以上传 PDF、Markdown 和表格。"
        "当内容较长时，系统应该优先按句子切分。"
        "这样检索结果会更稳定，也更容易附带引用来源。"
    )

    chunks = simple_chunks(text, size=28, overlap=0)

    assert len(chunks) >= 2
    assert all(len(chunk) <= 28 for chunk in chunks)
    assert chunks[0].endswith("。")
    assert chunks[1].startswith("它支持")


def test_simple_chunks_keeps_paragraphs_when_they_fit() -> None:
    text = "第一段介绍知识库。\n\n第二段介绍检索配置。"

    chunks = simple_chunks(text, size=200, overlap=0)

    assert chunks == [text]


def test_semantic_chunks_split_on_meaning_change_when_embeddings_are_available() -> None:
    text = (
        "TokenMind 支持知识库检索。"
        "它可以为对话提供引用上下文。"
        "今天上海会有明显降温。"
        "出门最好多穿一件外套。"
    )

    def fake_embed_texts(texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for item in texts:
            if "知识库" in item or "引用上下文" in item:
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return vectors

    chunks = semantic_chunks(text, fake_embed_texts, size=200, overlap=0, min_chunk_chars=10)

    assert len(chunks) == 2
    assert "知识库检索" in chunks[0]
    assert "降温" in chunks[1]
