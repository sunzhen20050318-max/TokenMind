from fastapi import FastAPI
from fastapi.testclient import TestClient

from tokenmind.knowledge.models import KnowledgeBaseRecord, WikiPageRecord, WikiSourceRecord
from tokenmind.knowledge.service import KnowledgeService
from tokenmind.knowledge.wiki_paths import (
    ensure_wiki_structure,
    get_kb_root,
    safe_wiki_filename,
)


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


def test_get_kb_root_joins_workspace_knowledge_kbid(tmp_path):
    root = get_kb_root(tmp_path, "kb_abc")
    assert root == tmp_path / "knowledge" / "kb_abc"


def test_ensure_wiki_structure_creates_all_dirs_and_seeds(tmp_path):
    kb_root = tmp_path / "knowledge" / "kb_x"
    ensure_wiki_structure(kb_root, name="Test", description="desc", language="zh")
    for sub in [
        "raw/files",
        "raw/webpages",
        "raw/chats",
        "raw/notes",
        "raw/assets",
        "wiki/sources",
        "wiki/entities",
        "wiki/topics",
        "wiki/comparisons",
        "wiki/synthesis/sessions",
        "wiki/queries",
    ]:
        assert (kb_root / sub).is_dir(), f"{sub} not created"
    for seed in [
        "index.md",
        "purpose.md",
        "log.md",
        ".wiki-schema.md",
        ".wiki-cache.json",
        "graph-data.json",
    ]:
        assert (kb_root / seed).is_file(), f"{seed} not created"
    purpose = (kb_root / "purpose.md").read_text(encoding="utf-8")
    assert "Test" in purpose
    assert "desc" in purpose


def test_safe_wiki_filename_handles_special_chars():
    assert safe_wiki_filename("Hello / World?") == "Hello-World"
    assert safe_wiki_filename("  many   spaces  ") == "many-spaces"
    assert safe_wiki_filename("中文 标题") == "中文-标题"


def test_create_rag_kb_keeps_legacy_behavior(tmp_path):
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("legacy", "")
    assert kb.type == "rag"
    assert kb.root_path == ""
    # 没有 raw/wiki 目录
    assert not (tmp_path / "knowledge" / kb.id / "raw").exists()
    assert not (tmp_path / "knowledge" / kb.id / "wiki").exists()


def test_create_wiki_kb_creates_structure(tmp_path):
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("AI 论文", "GraphRAG 相关", type="wiki")
    assert kb.type == "wiki"
    root = tmp_path / "knowledge" / kb.id
    assert kb.root_path == str(root)
    assert (root / "raw" / "files").is_dir()
    assert (root / "wiki" / "entities").is_dir()
    assert (root / "wiki" / "sources").is_dir()
    assert (root / "purpose.md").is_file()
    assert (root / ".wiki-cache.json").is_file()
    # purpose.md 含描述
    assert "GraphRAG 相关" in (root / "purpose.md").read_text(encoding="utf-8")


class _StubChatService:
    """Minimal ChatService stand-in exposing the methods the route hits."""

    def __init__(self, knowledge: KnowledgeService):
        self.knowledge = knowledge

    def create_knowledge_base(self, name, description, *, type="rag", language="zh"):
        return self.knowledge.create_knowledge_base(
            name, description, type=type, language=language
        ).model_dump()


def test_api_create_wiki_kb(tmp_path):
    """POST /api/knowledge with type=wiki creates wiki structure."""
    from tokenmind.server.dependencies import get_chat_service
    from tokenmind.server.routes.knowledge import router as knowledge_router

    knowledge = KnowledgeService(tmp_path)
    stub = _StubChatService(knowledge)

    app = FastAPI()
    app.include_router(knowledge_router)
    app.dependency_overrides[get_chat_service] = lambda: stub

    client = TestClient(app)
    resp = client.post(
        "/api/knowledge",
        json={"name": "wiki kb", "description": "test", "type": "wiki"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["type"] == "wiki"
    kb_id = body["id"]
    assert (tmp_path / "knowledge" / kb_id / "raw" / "files").is_dir()


def test_extract_text_reads_markdown(tmp_path):
    from tokenmind.knowledge.wiki_extractors import extract_text
    f = tmp_path / "x.md"
    f.write_text("# Hello", encoding="utf-8")
    assert "Hello" in extract_text(f)
