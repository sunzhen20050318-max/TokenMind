from tokenmind.knowledge.models import KnowledgeBaseRecord
from tokenmind.knowledge.models import WikiSourceRecord, WikiPageRecord


def test_record_defaults_to_rag_type():
    rec = KnowledgeBaseRecord(id="kb_x", name="legacy")
    assert rec.type == "rag"


def test_record_accepts_wiki_type_and_wiki_fields():
    rec = KnowledgeBaseRecord(
        id="kb_y",
        name="wiki kb",
        type="wiki",
        language="zh",
        root_path="/tmp/kb_y",
        source_count=3,
        page_count=10,
        entity_count=4,
        topic_count=2,
        link_count=12,
    )
    assert rec.type == "wiki"
    assert rec.page_count == 10
    assert rec.entity_count == 4


def test_wiki_source_record_defaults():
    rec = WikiSourceRecord(
        id="src_x",
        knowledge_base_id="kb_y",
        title="notes",
        source_type="file",
        raw_path="raw/files/notes.md",
    )
    assert rec.status == "registered"
    assert rec.processing_progress == 100
    assert rec.source_page_id is None


def test_wiki_page_record_defaults():
    rec = WikiPageRecord(
        id="page_x",
        knowledge_base_id="kb_y",
        page_type="entity",
        title="GraphRAG",
        path="wiki/entities/GraphRAG.md",
    )
    assert rec.outgoing_links == []
    assert rec.backlinks == []
    assert rec.sources == []
