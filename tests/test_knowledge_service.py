from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from tokenmind.knowledge.service import KnowledgeService


def test_create_knowledge_base_persists_metadata(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path)

    knowledge = service.create_knowledge_base("产品资料", "官网、方案和宣传材料")

    assert knowledge.name == "产品资料"
    assert knowledge.description == "官网、方案和宣传材料"
    assert (tmp_path / "knowledge" / "metadata.json").exists()


def test_linked_knowledge_bases_are_saved_per_session(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("售前资料", "")

    service.set_session_links("web:test-session", [kb.id])

    linked = service.get_session_links("web:test-session")
    assert linked == [kb.id]


def test_add_document_registers_file_under_knowledge_base(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("合同库", "")
    source = tmp_path / "source.txt"
    source.write_text("合同第一条\n合同第二条", encoding="utf-8")

    document = service.add_document(kb.id, source, "合同范本.txt")

    assert document.name == "合同范本.txt"
    assert document.status == "ready"
    assert document.chunk_count >= 1
    assert len(service.list_documents(kb.id)) == 1


def test_register_document_upload_creates_processing_record(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("上传测试", "")
    source = tmp_path / "source.txt"
    source.write_text("这是一个待处理的知识库文档。", encoding="utf-8")

    document = service.register_document_upload(kb.id, source, "source.txt")

    assert document.status == "processing"
    assert document.processing_stage == "queued"
    assert document.processing_progress > 0
    assert document.chunk_count == 0
    assert service.get_document(kb.id, document.id).status == "processing"


def test_process_document_marks_processing_record_ready(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("处理测试", "")
    source = tmp_path / "source.txt"
    source.write_text("第一段内容。\n\n第二段内容会被用于切块。", encoding="utf-8")

    document = service.register_document_upload(kb.id, source, "source.txt")
    processed = service.process_document(document.id)

    assert processed.status == "ready"
    assert processed.processing_stage == "ready"
    assert processed.processing_progress == 100
    assert processed.chunk_count >= 1


def test_overview_marks_knowledge_base_processing_when_documents_are_ingesting(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("处理中知识库", "")
    source = tmp_path / "source.txt"
    source.write_text("知识库内容。", encoding="utf-8")

    service.register_document_upload(kb.id, source, "source.txt")

    overview = service.get_knowledge_overview()

    assert overview["items"][0]["status"] == "processing"


def test_delete_document_removes_it_from_knowledge_base(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("图片资料", "")
    source = tmp_path / "notes.md"
    source.write_text("# 标题\n内容", encoding="utf-8")

    document = service.add_document(kb.id, source, "notes.md")
    service.delete_document(kb.id, document.id)

    assert service.list_documents(kb.id) == []


def test_delete_knowledge_base_removes_documents_chunks_and_session_links(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("测试知识库", "")
    source = tmp_path / "notes.md"
    source.write_text("# 标题\n知识库内容", encoding="utf-8")

    document = service.add_document(kb.id, source, "notes.md")
    service.set_session_links("web:test", [kb.id])

    result = service.delete_knowledge_base(kb.id)

    assert result["success"] is True
    assert result["knowledge_base_id"] == kb.id
    assert service.list_knowledge_bases() == []
    assert service.get_session_links("web:test") == []
    assert not Path(document.path).exists()
    with sqlite3.connect(service.index_file) as conn:
        count = conn.execute("SELECT COUNT(*) FROM chunks WHERE knowledge_base_id = ?", (kb.id,)).fetchone()[0]
    assert count == 0


def test_retrieve_for_session_returns_hits_from_linked_knowledge_bases_only(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path)
    product_kb = service.create_knowledge_base("产品资料", "")
    contract_kb = service.create_knowledge_base("合同资料", "")

    product_doc = tmp_path / "product.md"
    product_doc.write_text(
        "TokenMind 提供知识库、定时任务和文件中心能力，用于个人 AI 助手场景。",
        encoding="utf-8",
    )
    contract_doc = tmp_path / "contract.md"
    contract_doc.write_text(
        "本合同说明付款方式、违约责任和发票开具要求。",
        encoding="utf-8",
    )

    service.add_document(product_kb.id, product_doc, "product.md")
    service.add_document(contract_kb.id, contract_doc, "contract.md")
    service.set_session_links("web:test", [product_kb.id])

    hits = service.retrieve_for_session("web:test", "知识库能力有哪些", top_k=3)

    assert hits
    assert hits[0]["knowledge_base_id"] == product_kb.id
    assert "知识库" in hits[0]["content"]
    assert all(hit["knowledge_base_id"] != contract_kb.id for hit in hits)


def test_qdrant_local_can_store_and_retrieve_embeddings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = KnowledgeService(
        tmp_path,
        vector_backend="qdrant",
        embedding_model="mock-embedding-model",
    )
    kb = service.create_knowledge_base("产品资料", "")
    source = tmp_path / "feature.txt"
    source.write_text("TokenMind 支持知识库问答和多会话管理。", encoding="utf-8")

    def fake_embed_texts(texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            if "知识库" in text:
                vectors.append([1.0, 0.0, 0.0])
            else:
                vectors.append([0.0, 1.0, 0.0])
        return vectors

    monkeypatch.setattr(service, "_embed_texts", fake_embed_texts)
    service.add_document(kb.id, source, "feature.txt")
    service.set_session_links("web:test", [kb.id])

    hits = service.retrieve_for_session("web:test", "知识库", top_k=3)

    assert hits
    assert hits[0]["knowledge_base_id"] == kb.id


def test_add_document_uses_semantic_chunking_when_embedding_model_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = KnowledgeService(
        tmp_path,
        chunk_size=400,
        embedding_model="mock-embedding-model",
    )
    kb = service.create_knowledge_base("语义切分测试", "")
    source = tmp_path / "semantic.txt"
    source.write_text(
        "TokenMind 支持知识库检索。"
        "它可以为对话提供引用上下文。"
        "今天上海会有明显降温。"
        "出门最好多穿一件外套。",
        encoding="utf-8",
    )

    def fake_embed_texts(texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            if "知识库" in text or "引用上下文" in text:
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return vectors

    monkeypatch.setattr(service, "_embed_texts", fake_embed_texts)

    document = service.add_document(kb.id, source, "semantic.txt")

    assert document.chunk_count == 2


def test_retrieve_for_session_prefers_hits_supported_by_lexical_and_vector_signals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = KnowledgeService(
        tmp_path,
        embedding_model="mock-embedding-model",
    )
    kb = service.create_knowledge_base("Hybrid 检索测试", "")

    consensus_doc = tmp_path / "consensus.txt"
    consensus_doc.write_text("consensus result", encoding="utf-8")
    lexical_doc = tmp_path / "lexical.txt"
    lexical_doc.write_text("lexical only result", encoding="utf-8")
    vector_doc = tmp_path / "vector.txt"
    vector_doc.write_text("vector only result", encoding="utf-8")

    def fake_embed_texts(texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            if text == "hybrid ranking":
                vectors.append([1.0, 0.0])
            elif "lexical only result" in text:
                vectors.append([0.0, 1.0])
            else:
                vectors.append([1.0, 0.0])
        return vectors

    monkeypatch.setattr(service, "_embed_texts", fake_embed_texts)

    service.add_document(kb.id, consensus_doc, "consensus.txt")
    service.add_document(kb.id, lexical_doc, "lexical.txt")
    service.add_document(kb.id, vector_doc, "vector.txt")
    service.set_session_links("web:test", [kb.id])

    with sqlite3.connect(service.index_file) as conn:
        rows = conn.execute("SELECT id, content FROM chunks").fetchall()
    chunk_ids = {content: chunk_id for chunk_id, content in rows}

    lexical_scores = {
        "consensus result": 0.55,
        "lexical only result": 0.9,
        "vector only result": 0.05,
    }

    def fake_lexical_score(_: str, content: str) -> float:
        return lexical_scores.get(content, 0.0)

    def fake_qdrant_hits(*_args, **_kwargs) -> list[dict[str, object]]:
        return [
            {"id": chunk_ids["vector only result"], "vector_score": 0.95},
            {"id": chunk_ids["consensus result"], "vector_score": 0.75},
        ]

    monkeypatch.setattr(service, "_lexical_score", fake_lexical_score)
    monkeypatch.setattr(service, "_qdrant_hits", fake_qdrant_hits)

    hits = service.retrieve_for_session("web:test", "hybrid ranking", top_k=3)

    assert hits
    assert hits[0]["content"] == "consensus result"
