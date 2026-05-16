from tokenmind.knowledge.models import KnowledgeBaseRecord


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
