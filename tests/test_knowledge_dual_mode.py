import hashlib
import json
from pathlib import Path

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

    def __init__(self, knowledge_or_path):
        from tokenmind.session.manager import SessionManager

        if isinstance(knowledge_or_path, KnowledgeService):
            self.knowledge = knowledge_or_path
            workspace = knowledge_or_path.workspace
        else:
            workspace = Path(knowledge_or_path)
            self.knowledge = KnowledgeService(workspace)
        self.session_manager = SessionManager(workspace)

    def create_knowledge_base(self, name, description, *, type="rag", language="zh"):
        return self.knowledge.create_knowledge_base(
            name, description, type=type, language=language
        ).model_dump()

    def get_wiki_graph(self, kb_id: str) -> dict:
        import json as _json
        kb = self.knowledge.get_knowledge_base(kb_id)
        if kb.type != "wiki":
            raise ValueError("graph is only available for wiki kbs")
        p = Path(kb.root_path) / "graph-data.json"
        if not p.is_file():
            return {"nodes": [], "edges": [], "updated_at": None}
        return _json.loads(p.read_text(encoding="utf-8"))

    def rebuild_wiki_graph(self, kb_id: str) -> dict:
        from tokenmind.knowledge.wiki_graph import build_graph_data
        kb = self.knowledge.get_knowledge_base(kb_id)
        if kb.type != "wiki":
            raise ValueError("graph is only available for wiki kbs")
        return build_graph_data(Path(kb.root_path), persist=True)

    def list_wiki_pages(self, kb_id: str) -> list[dict]:
        from tokenmind.knowledge.wiki_query import scan_pages
        kb = self.knowledge.get_knowledge_base(kb_id)
        if kb.type != "wiki":
            raise ValueError("pages endpoint is only for wiki kbs")
        pages = scan_pages(Path(kb.root_path))
        return [{"title": p["title"], "type": p["type"], "path": p["path"]} for p in pages]

    def patch_session(self, session_id: str, updates: dict) -> dict:
        session = self.session_manager.get_or_create(session_id)
        if "active_wiki_kb_id" in updates:
            new_kb_id = updates["active_wiki_kb_id"]
            if new_kb_id is not None:
                kb = self.knowledge.get_knowledge_base(new_kb_id)
                if kb.type != "wiki":
                    raise ValueError("active_wiki_kb_id must reference a wiki kb")
                previous = session.active_wiki_kb_id
                if previous and previous != new_kb_id:
                    try:
                        prev_kb = self.knowledge.get_knowledge_base(previous)
                        session.metadata["_previous_wiki_kb_name"] = prev_kb.name
                    except KeyError:
                        pass
            session.set_active_wiki_kb_id(new_kb_id)
            self.session_manager.save(session)
        return {
            "session_id": session_id,
            "active_wiki_kb_id": session.active_wiki_kb_id,
        }


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


def test_upload_to_wiki_kb_lands_in_raw_files(tmp_path):
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("wiki", "", type="wiki")
    src = tmp_path / "src.md"
    src.write_text("hello world", encoding="utf-8")
    doc = service.register_document_upload(kb.id, src, "src.md")
    assert "/raw/files/" in doc.path.replace("\\", "/")
    assert Path(doc.path).exists()


def test_upload_to_wiki_kb_writes_cache_with_sha256(tmp_path):
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("wiki", "", type="wiki")
    src = tmp_path / "src.md"
    content = b"content for sha"
    src.write_bytes(content)
    expected_sha = hashlib.sha256(content).hexdigest()

    service.register_document_upload(kb.id, src, "src.md")
    cache_path = tmp_path / "knowledge" / kb.id / ".wiki-cache.json"
    cache = json.loads(cache_path.read_text())
    assert f"sha256:{expected_sha}" in cache["sources"]


def test_upload_to_rag_kb_unchanged(tmp_path):
    """Legacy RAG path stays at <kb>/documents/."""
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("rag", "")
    src = tmp_path / "src.md"
    src.write_text("legacy", encoding="utf-8")
    doc = service.register_document_upload(kb.id, src, "src.md")
    assert "/raw/files/" not in doc.path.replace("\\", "/")
    assert Path(doc.path).exists()


def test_compile_source_page_template(tmp_path):
    from tokenmind.knowledge.wiki_ingest import compile_source_page_template
    out = compile_source_page_template(
        page_id="page_x",
        source_id="doc_x",
        title="My Doc",
        raw_path="raw/files/my-doc.md",
        sha256="abc123",
        body_text="This is the content body...",
    )
    assert "# My Doc" in out
    assert "## 原始资料" in out
    assert "raw/files/my-doc.md" in out
    assert "abc123" in out
    assert "page_x" in out
    assert out.startswith("---")  # frontmatter


def test_process_wiki_document_writes_source_page(tmp_path):
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("wiki", "", type="wiki")
    src = tmp_path / "notes.md"
    src.write_text("# TokenMind\n\nA local-first agent framework.", encoding="utf-8")
    doc = service.register_document_upload(kb.id, src, "notes.md")

    updated = service.process_document(doc.id)

    assert updated.status == "ready"
    kb_root = tmp_path / "knowledge" / kb.id
    sources = list((kb_root / "wiki" / "sources").glob("*.md"))
    assert len(sources) == 1
    body = sources[0].read_text(encoding="utf-8")
    assert "TokenMind" in body
    assert "raw/files/notes.md" in body


def test_process_wiki_document_does_not_write_chunks(tmp_path):
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("wiki", "", type="wiki")
    src = tmp_path / "n.md"
    src.write_text("text", encoding="utf-8")
    doc = service.register_document_upload(kb.id, src, "n.md")
    service.process_document(doc.id)

    import sqlite3
    with sqlite3.connect(service.index_file) as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?", (doc.id,)
        ).fetchone()[0]
    assert n == 0


def test_process_rag_document_unchanged(tmp_path):
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("rag", "")
    src = tmp_path / "n.md"
    src.write_text("hello", encoding="utf-8")
    doc = service.register_document_upload(kb.id, src, "n.md")
    updated = service.process_document(doc.id)
    assert updated.status == "ready"
    # Legacy chunks still written
    import sqlite3
    with sqlite3.connect(service.index_file) as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?", (doc.id,)
        ).fetchone()[0]
    assert n >= 1


def test_process_wiki_doc_calls_llm_when_provider_set(tmp_path, monkeypatch):
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("wiki", "", type="wiki")
    src = tmp_path / "n.md"
    src.write_text("Content for LLM", encoding="utf-8")
    doc = service.register_document_upload(kb.id, src, "n.md")

    calls = []

    async def fake_compile(**kwargs):
        calls.append(kwargs["source_title"])
        return {"entities": [], "topics": []}

    monkeypatch.setattr("tokenmind.knowledge.service.compile_with_llm", fake_compile, raising=False)
    # Inject a stub provider via attribute set after service init
    service._wiki_llm_provider = object()
    service._wiki_llm_model = "stub"

    service.process_document(doc.id)
    assert "n.md" in calls or any("n" in c for c in calls)


def test_process_wiki_doc_skips_llm_when_no_provider(tmp_path):
    """No provider set → only template source page written, no error."""
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("wiki", "", type="wiki")
    src = tmp_path / "n.md"
    src.write_text("text", encoding="utf-8")
    doc = service.register_document_upload(kb.id, src, "n.md")
    updated = service.process_document(doc.id)
    assert updated.status == "ready"


def test_session_active_wiki_kb_id_accessor():
    from tokenmind.session.manager import Session
    s = Session(key="web:test")
    assert s.active_wiki_kb_id is None
    s.set_active_wiki_kb_id("kb_abc")
    assert s.active_wiki_kb_id == "kb_abc"
    assert s.metadata["active_wiki_kb_id"] == "kb_abc"
    s.set_active_wiki_kb_id(None)
    assert s.active_wiki_kb_id is None
    assert "active_wiki_kb_id" not in s.metadata


def test_context_builder_includes_active_wiki_section(tmp_path):
    from tokenmind.agent.context import ContextBuilder
    cb = ContextBuilder(tmp_path)
    section = cb._build_active_wiki_section({
        "kb_name": "AI 论文",
        "purpose_summary": "围绕 GraphRAG 的论文集",
        "page_count": 10,
        "entity_count": 4,
        "topic_count": 3,
        "source_count": 5,
        "switched_from": None,
    })
    assert section is not None
    assert "AI 论文" in section
    assert "wiki_index" in section
    assert "wiki_grep" in section
    assert "GraphRAG" in section


def test_context_builder_returns_none_without_active_kb():
    from tokenmind.agent.context import ContextBuilder
    cb = ContextBuilder(Path("/tmp"))
    assert cb._build_active_wiki_section(None) is None


def test_context_builder_mentions_previous_kb_when_switched():
    from tokenmind.agent.context import ContextBuilder
    cb = ContextBuilder(Path("/tmp"))
    section = cb._build_active_wiki_section({
        "kb_name": "B",
        "purpose_summary": "",
        "page_count": 0,
        "entity_count": 0,
        "topic_count": 0,
        "source_count": 0,
        "switched_from": "A",
    })
    assert "previously used" in section.lower() or "A" in section


def test_retrieve_for_session_skips_wiki_kbs(tmp_path):
    service = KnowledgeService(tmp_path)
    rag_kb = service.create_knowledge_base("rag", "")
    wiki_kb = service.create_knowledge_base("wiki", "", type="wiki")
    # Link both
    service.set_session_links("web:s1", [rag_kb.id, wiki_kb.id])
    # Upload to wiki — should NOT be retrievable
    src = tmp_path / "x.md"
    src.write_text("alpha beta gamma keyword", encoding="utf-8")
    doc = service.register_document_upload(wiki_kb.id, src, "x.md")
    service.process_document(doc.id)

    hits = service.retrieve_for_session("web:s1", "keyword")
    for hit in hits:
        assert hit["knowledge_base_id"] != wiki_kb.id, f"wiki KB leaked into retrieve: {hit}"


def test_delete_wiki_kb_clears_active_in_sessions(tmp_path):
    from tokenmind.session.manager import SessionManager

    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("wiki", "", type="wiki")
    sm = SessionManager(tmp_path)
    s = sm.get_or_create("web:s1")
    s.set_active_wiki_kb_id(kb.id)
    sm.save(s)

    service.delete_knowledge_base(kb.id, session_manager=sm)

    # Force a re-read from disk to verify the change was persisted.
    sm.invalidate("web:s1")
    reloaded = sm.get_or_create("web:s1")
    assert reloaded.active_wiki_kb_id is None


def test_process_wiki_doc_rebuilds_graph(tmp_path):
    import json
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("wiki", "", type="wiki")
    src = tmp_path / "n.md"
    src.write_text("# Note\n[[Other]]", encoding="utf-8")
    doc = service.register_document_upload(kb.id, src, "n.md")
    service.process_document(doc.id)

    graph = json.loads((tmp_path / "knowledge" / kb.id / "graph-data.json").read_text())
    titles = {n["id"] for n in graph["nodes"]}
    # The source page got written, so its title (probably "n" or similar) appears as a node.
    assert len(titles) >= 1


def _make_kb_app(tmp_path):
    """Helper: build a FastAPI app wired to a stub ChatService over tmp_path."""
    from tokenmind.server.dependencies import get_chat_service
    from tokenmind.server.routes.knowledge import router as knowledge_router

    knowledge = KnowledgeService(tmp_path)
    stub = _StubChatService(knowledge)
    app = FastAPI()
    app.include_router(knowledge_router)
    app.dependency_overrides[get_chat_service] = lambda: stub
    return app


def test_api_get_graph_returns_json(tmp_path):
    app = _make_kb_app(tmp_path)
    client = TestClient(app)

    kb = client.post(
        "/api/knowledge", json={"name": "g", "type": "wiki"}
    ).json()
    resp = client.get(f"/api/knowledge/{kb['id']}/graph")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "nodes" in body and "edges" in body


def test_api_get_graph_rejects_rag_kb(tmp_path):
    app = _make_kb_app(tmp_path)
    client = TestClient(app)

    kb = client.post("/api/knowledge", json={"name": "r"}).json()
    resp = client.get(f"/api/knowledge/{kb['id']}/graph")
    assert resp.status_code == 400


def test_api_rebuild_graph_returns_count(tmp_path):
    app = _make_kb_app(tmp_path)
    client = TestClient(app)

    kb = client.post(
        "/api/knowledge", json={"name": "g", "type": "wiki"}
    ).json()
    resp = client.post(f"/api/knowledge/{kb['id']}/graph/rebuild")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "nodes" in body


def test_api_list_pages_groups_by_type(tmp_path):
    app = _make_kb_app(tmp_path)
    client = TestClient(app)

    kb = client.post(
        "/api/knowledge", json={"name": "g", "type": "wiki"}
    ).json()

    # Seed a page manually
    pages_dir = Path(tmp_path) / "knowledge" / kb["id"] / "wiki" / "entities"
    (pages_dir / "Foo.md").write_text(
        "---\ntype: entity\ntitle: Foo\n---\n# Foo\n", encoding="utf-8"
    )

    resp = client.get(f"/api/knowledge/{kb['id']}/pages")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    titles = [p["title"] for p in body["pages"]]
    assert "Foo" in titles


def test_api_list_pages_rejects_rag_kb(tmp_path):
    app = _make_kb_app(tmp_path)
    client = TestClient(app)

    kb = client.post("/api/knowledge", json={"name": "r"}).json()
    resp = client.get(f"/api/knowledge/{kb['id']}/pages")
    assert resp.status_code == 400


def test_api_patch_session_sets_active_wiki_kb_id(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from tokenmind.server.dependencies import get_chat_service
    from tokenmind.server.routes.knowledge import router as knowledge_router
    from tokenmind.server.routes.sessions import router as sessions_router

    app = FastAPI()
    app.include_router(knowledge_router)
    app.include_router(sessions_router)
    stub = _StubChatService(tmp_path)
    app.dependency_overrides[get_chat_service] = lambda: stub
    client = TestClient(app)

    kb = client.post("/api/knowledge", json={"name": "w", "type": "wiki"}).json()

    sid = "web:test123"
    resp = client.patch(
        f"/api/sessions/{sid}",
        json={"active_wiki_kb_id": kb["id"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["active_wiki_kb_id"] == kb["id"]

    # Verify clearing
    resp = client.patch(f"/api/sessions/{sid}", json={"active_wiki_kb_id": None})
    assert resp.status_code == 200
    assert resp.json()["active_wiki_kb_id"] is None


def test_api_patch_session_rejects_non_wiki_kb(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from tokenmind.server.dependencies import get_chat_service
    from tokenmind.server.routes.knowledge import router as knowledge_router
    from tokenmind.server.routes.sessions import router as sessions_router

    app = FastAPI()
    app.include_router(knowledge_router)
    app.include_router(sessions_router)
    stub = _StubChatService(tmp_path)
    app.dependency_overrides[get_chat_service] = lambda: stub
    client = TestClient(app)

    rag_kb = client.post("/api/knowledge", json={"name": "r"}).json()
    resp = client.patch(
        "/api/sessions/web:foo",
        json={"active_wiki_kb_id": rag_kb["id"]},
    )
    assert resp.status_code == 400
