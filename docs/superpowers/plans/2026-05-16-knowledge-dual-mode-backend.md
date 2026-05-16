# 知识库双模（RAG + LLM Wiki）后端实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 TokenMind 知识库加 `type=wiki` 模式，与现有 RAG 并存：创建时选类型、文件分库存储、Wiki KB 自动编译 source/entity/topic 页面、注册 5 个 Wiki 工具让 LLM 主动浏览。RAG 行为完全不动。前端集成留给后续 plan。

**Architecture:** `KnowledgeBaseRecord.type` 字段做路由：RAG 走现有 chunk/vector 链路，Wiki 走新增的 `raw/` + `wiki/` + 双向链接 + 工具调用。`KnowledgeService` 内部按 type 分发，对外 API 兼容。LLM 通过新增的 `wiki_index / wiki_grep / wiki_read / wiki_backlinks / wiki_graph` 工具浏览 Wiki，作用域由 `Session.metadata.active_wiki_kb_id` 决定，不自动注入 ContextBuilder。

**Tech Stack:** Python 3.12 + Pydantic v2 + FastAPI + pytest（`asyncio_mode=auto`）+ 现有 `LLMProvider` 抽象。文件路径全部相对 workspace。

---

## File Structure

**新建文件（11 个）：**

```
tokenmind/knowledge/wiki_paths.py         # 目录/路径辅助；目录初始化；safe filename
tokenmind/knowledge/wiki_extractors.py    # 文本提取（从 service.py 抽出）
tokenmind/knowledge/wiki_ingest.py        # 上传 → raw → source/entity/topic page 编译
tokenmind/knowledge/wiki_prompts.py       # LLM 编译用的 system/user prompt 模板
tokenmind/knowledge/wiki_query.py         # 纯 lexical + 双链扩展查询
tokenmind/knowledge/wiki_graph.py         # 扫描 [[链接]] 生成 graph-data.json
tokenmind/agent/tools/wiki.py             # 5 个 wiki_* 工具
tests/test_knowledge_dual_mode.py         # type 路由 / Wiki KB 创建 / 上传 / source page
tests/test_wiki_ingest.py                 # LLM 编译 entity/topic（mock LLM）
tests/test_wiki_query.py                  # 查询召回
tests/test_wiki_tools.py                  # 5 个 tool 的 execute
tests/test_wiki_graph.py                  # 图谱生成
```

**修改文件（7 个）：**

```
tokenmind/knowledge/models.py             # +type 字段、+WikiSourceRecord、+WikiPageRecord
tokenmind/knowledge/service.py            # type 路由：create / register / process / retrieve / delete
tokenmind/server/routes/knowledge.py      # POST 接受 type；新增 pages / graph 路由
tokenmind/server/routes/sessions.py       # PATCH 接受 active_wiki_kb_id（若路由已存在则扩展）
tokenmind/session/manager.py              # Session.active_wiki_kb_id accessor
tokenmind/agent/context.py                # +[Active Wiki Knowledge Base] system prompt 段
tokenmind/agent/loop.py                   # 注册 wiki_* 工具；retrieve_for_session 仅取 RAG KB
```

每个文件保持单一职责。`wiki_*.py` 拆得细一些，避免 `service.py`（已 1018 行）继续膨胀。

---

## Phase 1: 数据模型 + Wiki KB 创建骨架

### Task 1: 给 KnowledgeBaseRecord 加 type 与 Wiki 字段

**Files:**
- Modify: `tokenmind/knowledge/models.py:12-20`
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_knowledge_dual_mode.py
import pytest
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v`
Expected: FAIL with `type`, `language`, `root_path`, etc. unknown fields (Pydantic ValidationError).

- [ ] **Step 3: Add fields to KnowledgeBaseRecord**

Edit `tokenmind/knowledge/models.py`, replace the class definition:

```python
from typing import Literal

class KnowledgeBaseRecord(BaseModel):
    id: str
    name: str
    description: str = ""
    type: Literal["rag", "wiki"] = "rag"
    status: str = "ready"
    enabled: bool = True
    # RAG 字段
    document_count: int = 0
    # Wiki 字段（rag 类型保持默认值）
    language: str = "zh"
    root_path: str = ""
    source_count: int = 0
    page_count: int = 0
    entity_count: int = 0
    topic_count: int = 0
    link_count: int = 0
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
```

- [ ] **Step 4: Verify both tests pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenmind/knowledge/models.py tests/test_knowledge_dual_mode.py
git commit -m "feat(knowledge): add type field and wiki-specific fields to KnowledgeBaseRecord"
```

---

### Task 2: 新增 WikiSourceRecord 和 WikiPageRecord

**Files:**
- Modify: `tokenmind/knowledge/models.py`
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Add tests**

Append to `tests/test_knowledge_dual_mode.py`:

```python
from tokenmind.knowledge.models import WikiSourceRecord, WikiPageRecord


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
```

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py::test_wiki_source_record_defaults tests/test_knowledge_dual_mode.py::test_wiki_page_record_defaults -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Add models**

Append to `tokenmind/knowledge/models.py`:

```python
class WikiSourceRecord(BaseModel):
    id: str
    knowledge_base_id: str
    title: str
    source_type: Literal["file", "webpage", "chat", "note"]
    raw_path: str
    original_name: str = ""
    source_url: str | None = None
    sha256: str = ""
    size: int = 0
    status: Literal["registered", "processing", "ready", "failed"] = "registered"
    processing_stage: str = "ready"
    processing_progress: int = 100
    error_message: str | None = None
    source_page_id: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class WikiPageRecord(BaseModel):
    id: str
    knowledge_base_id: str
    page_type: Literal["source", "entity", "topic", "comparison", "synthesis", "query"]
    title: str
    path: str
    summary: str = ""
    outgoing_links: list[str] = Field(default_factory=list)
    backlinks: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenmind/knowledge/models.py tests/test_knowledge_dual_mode.py
git commit -m "feat(knowledge): add WikiSourceRecord and WikiPageRecord models"
```

---

### Task 3: 新增 wiki_paths.py（路径辅助）

**Files:**
- Create: `tokenmind/knowledge/wiki_paths.py`
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Add tests**

Append to `tests/test_knowledge_dual_mode.py`:

```python
from pathlib import Path
from tokenmind.knowledge.wiki_paths import (
    get_kb_root,
    ensure_wiki_structure,
    safe_wiki_filename,
)


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
```

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v`
Expected: 3 new FAIL (ImportError).

- [ ] **Step 3: Implement wiki_paths.py**

Create `tokenmind/knowledge/wiki_paths.py`:

```python
"""Path helpers for Wiki-type knowledge bases."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

_WIKI_DIRS = (
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
)


def get_kb_root(workspace: Path, kb_id: str) -> Path:
    return Path(workspace) / "knowledge" / kb_id


def safe_wiki_filename(title: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]", "", title).strip()
    cleaned = re.sub(r"\s+", "-", cleaned)
    return cleaned or "untitled"


def ensure_wiki_structure(
    kb_root: Path,
    *,
    name: str,
    description: str,
    language: str = "zh",
) -> None:
    kb_root.mkdir(parents=True, exist_ok=True)
    for rel in _WIKI_DIRS:
        (kb_root / rel).mkdir(parents=True, exist_ok=True)

    purpose = (
        f"# 知识库目标\n\n"
        f"名称：{name}\n\n"
        f"描述：{description}\n\n"
        f"语言：{ '中文' if language == 'zh' else 'English'}\n\n"
        "本知识库使用 TokenMind Wiki-first 模式：\n"
        "- raw/ 保存原始资料\n"
        "- wiki/ 保存 AI 编译后的 Markdown 页面\n"
        "- [[双向链接]] 连接实体、主题、来源\n"
        "- graph-data.json 保存图谱数据\n"
    )
    index = f"# {name}\n\n## 入口\n\n- [[资料来源]]\n- [[核心主题]]\n- [[重要实体]]\n\n## 最近更新\n\n暂无。\n"
    schema = (
        "# Wiki Schema\n\n## 页面类型\n\n- source：原始资料摘要\n"
        "- entity：实体、工具、人物、概念\n- topic：主题\n"
        "- comparison：对比分析\n- synthesis：综合分析\n- query：保存的查询\n\n"
        "## 链接规则\n\n使用 `[[页面标题]]` 连接相关知识。\n"
    )
    cache = {"version": 1, "sources": {}, "pages": {}, "updated_at": None}
    graph = {"nodes": [], "edges": [], "updated_at": None}

    _write_if_absent(kb_root / "purpose.md", purpose)
    _write_if_absent(kb_root / "index.md", index)
    _write_if_absent(kb_root / "log.md", f"# Log\n\n创建于 {datetime.now(timezone.utc).isoformat()}\n")
    _write_if_absent(kb_root / ".wiki-schema.md", schema)
    _write_if_absent(kb_root / ".wiki-cache.json", json.dumps(cache, ensure_ascii=False, indent=2))
    _write_if_absent(kb_root / "graph-data.json", json.dumps(graph, ensure_ascii=False, indent=2))


def _write_if_absent(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8")
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenmind/knowledge/wiki_paths.py tests/test_knowledge_dual_mode.py
git commit -m "feat(knowledge): wiki_paths helpers for kb root, dir tree, seed files"
```

---

### Task 4: create_knowledge_base 按 type 分发

**Files:**
- Modify: `tokenmind/knowledge/service.py:201-214`
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Add tests**

Append to `tests/test_knowledge_dual_mode.py`:

```python
from tokenmind.knowledge.service import KnowledgeService


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
```

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v`
Expected: 2 new FAIL (`create_knowledge_base` doesn't accept `type`).

- [ ] **Step 3: Update create_knowledge_base**

Replace `tokenmind/knowledge/service.py:201-214`:

```python
def create_knowledge_base(
    self,
    name: str,
    description: str,
    *,
    type: str = "rag",
    language: str = "zh",
) -> KnowledgeBaseRecord:
    from tokenmind.knowledge.wiki_paths import get_kb_root, ensure_wiki_structure
    if type not in ("rag", "wiki"):
        raise ValueError(f"invalid kb type: {type}")
    with self._state_lock:
        self._reload()
        now = utc_now_iso()
        kb_id = f"kb_{uuid.uuid4().hex[:10]}"
        root_path = ""
        if type == "wiki":
            kb_root = get_kb_root(self.root.parent, kb_id)
            ensure_wiki_structure(kb_root, name=name, description=description, language=language)
            root_path = str(kb_root)
        record = KnowledgeBaseRecord(
            id=kb_id,
            name=name,
            description=description,
            type=type,
            language=language,
            root_path=root_path,
            created_at=now,
            updated_at=now,
        )
        self._state["knowledge_bases"].append(record.model_dump())
        self._save()
        return record
```

Note: `self.root` is `<workspace>/knowledge` (verify by reading `KnowledgeService.__init__`); we pass `self.root.parent` to `get_kb_root` which prepends `knowledge/`. If `self.root` is actually `<workspace>` itself, drop `.parent`.

- [ ] **Step 4: Verify root layout assumption**

Run:
```bash
.venv/bin/python -c "
from pathlib import Path
from tokenmind.knowledge.service import KnowledgeService
s = KnowledgeService(Path('/tmp/test_kb'))
print(s.root)
"
```

Expected: prints `/tmp/test_kb/knowledge` (so use `self.root.parent` in the impl). If different, adjust step 3 accordingly.

- [ ] **Step 5: Verify pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v`
Expected: 9 PASS.

- [ ] **Step 6: Commit**

```bash
git add tokenmind/knowledge/service.py tests/test_knowledge_dual_mode.py
git commit -m "feat(knowledge): dispatch create_knowledge_base by type, init wiki layout"
```

---

### Task 5: API POST /api/knowledge 接受 type

**Files:**
- Modify: `tokenmind/server/routes/knowledge.py:16-19` and `42-52`
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Add API test**

Append to `tests/test_knowledge_dual_mode.py`:

```python
from fastapi.testclient import TestClient


def test_api_create_wiki_kb(tmp_path, monkeypatch):
    """POST /api/knowledge with type=wiki creates wiki structure."""
    from tokenmind.server.app import create_app
    from tokenmind.config.schema import Config

    monkeypatch.setenv("TOKENMIND_WORKSPACE", str(tmp_path))
    app = create_app()
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
```

Note: if `TOKENMIND_WORKSPACE` env override doesn't work in tests, mock `get_chat_service` dependency directly. See existing API tests in `tests/` for the pattern.

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py::test_api_create_wiki_kb -v`
Expected: FAIL (CreateKnowledgeBasePayload rejects `type` field, or default RAG path taken).

- [ ] **Step 3: Extend the payload model**

Edit `tokenmind/server/routes/knowledge.py:16-19`:

```python
class CreateKnowledgeBasePayload(BaseModel):
    name: str
    description: str = ""
    type: str = "rag"
    language: str = "zh"
```

Edit `tokenmind/server/routes/knowledge.py:48`:

```python
return service.create_knowledge_base(
    payload.name,
    payload.description,
    type=payload.type,
    language=payload.language,
)
```

Note: `service.create_knowledge_base` here is `ChatService.create_knowledge_base`, which thin-wraps `KnowledgeService.create_knowledge_base`. Inspect `tokenmind/server/app.py` around `create_knowledge_base` to see whether `ChatService` forwards extra kwargs. If it doesn't, update its signature too:

```python
def create_knowledge_base(self, name, description, *, type="rag", language="zh"):
    return self.knowledge.create_knowledge_base(name, description, type=type, language=language).model_dump()
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenmind/server/routes/knowledge.py tokenmind/server/app.py tests/test_knowledge_dual_mode.py
git commit -m "feat(api): POST /api/knowledge accepts type and language"
```

---

## Phase 2: 上传 Wiki 资料到 raw/

### Task 6: 抽出文本提取到 wiki_extractors.py

**Files:**
- Create: `tokenmind/knowledge/wiki_extractors.py`
- Modify: `tokenmind/knowledge/service.py`（删除被搬走的私有函数，改导入）
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Locate functions to move**

Run:
```bash
grep -n "_extract_text\|_extract_pdf_text\|_extract_docx_text\|_extract_pptx_text\|_extract_xlsx_text\|TEXT_SUFFIXES" tokenmind/knowledge/service.py | head -20
```

Note the line ranges. These will be moved verbatim to `wiki_extractors.py` and re-exported.

- [ ] **Step 2: Create wiki_extractors.py**

Create `tokenmind/knowledge/wiki_extractors.py`:

```python
"""Text extraction from various source formats."""
from __future__ import annotations

from pathlib import Path

TEXT_SUFFIXES = {".md", ".txt", ".markdown", ".rst", ".log"}


def extract_text(path: Path) -> str:
    """Dispatch by suffix; return UTF-8 text or raise."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix == ".pptx":
        return _extract_pptx(path)
    if suffix == ".xlsx":
        return _extract_xlsx(path)
    if suffix in TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8", errors="replace")
    raise ValueError(f"unsupported file type: {suffix}")


def _extract_pdf(path: Path) -> str:
    import pypdf
    reader = pypdf.PdfReader(str(path))
    return "\n\n".join(p.extract_text() or "" for p in reader.pages)


def _extract_docx(path: Path) -> str:
    try:
        import docx  # python-docx
    except ImportError as exc:
        raise RuntimeError("python-docx not installed") from exc
    d = docx.Document(str(path))
    return "\n\n".join(p.text for p in d.paragraphs if p.text)


def _extract_pptx(path: Path) -> str:
    try:
        from pptx import Presentation
    except ImportError as exc:
        raise RuntimeError("python-pptx not installed") from exc
    pres = Presentation(str(path))
    out = []
    for slide in pres.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    text = "".join(run.text for run in para.runs)
                    if text:
                        out.append(text)
    return "\n".join(out)


def _extract_xlsx(path: Path) -> str:
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError("openpyxl not installed") from exc
    wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
    rows = []
    for sheet in wb.worksheets:
        for row in sheet.iter_rows(values_only=True):
            rows.append("\t".join(str(c) if c is not None else "" for c in row))
    return "\n".join(rows)
```

Note: keep `service.py`'s existing `_extract_*` methods to preserve legacy RAG path. Just add `from tokenmind.knowledge.wiki_extractors import extract_text` for wiki use. (Don't break what's working.)

- [ ] **Step 3: Add a quick smoke test**

Append:

```python
def test_extract_text_reads_markdown(tmp_path):
    from tokenmind.knowledge.wiki_extractors import extract_text
    f = tmp_path / "x.md"
    f.write_text("# Hello", encoding="utf-8")
    assert "Hello" in extract_text(f)
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py::test_extract_text_reads_markdown -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenmind/knowledge/wiki_extractors.py tests/test_knowledge_dual_mode.py
git commit -m "feat(knowledge): wiki_extractors module for text extraction"
```

---

### Task 7: register_document_upload 按 type 分发

**Files:**
- Modify: `tokenmind/knowledge/service.py:767-796`
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Add tests**

Append:

```python
import hashlib
import json


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
```

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v -k "upload"`
Expected: wiki tests FAIL (file lands in legacy `documents/` dir).

- [ ] **Step 3: Branch register_document_upload**

Edit `tokenmind/knowledge/service.py:767-796`. Replace with:

```python
def register_document_upload(
    self,
    knowledge_base_id: str,
    source: Path,
    original_name: str,
) -> KnowledgeDocumentRecord:
    kb = self.get_knowledge_base(knowledge_base_id)
    if kb.type == "wiki":
        return self._wiki_register_source(kb, source, original_name)
    return self._rag_register_document(knowledge_base_id, source, original_name)


def _rag_register_document(self, knowledge_base_id, source, original_name):
    # original body of register_document_upload moved here verbatim
    with self._state_lock:
        self._reload()
        target, safe_name = self._prepare_document_target(knowledge_base_id, original_name, source)
        shutil.copy2(source, target)
        now = utc_now_iso()
        document = KnowledgeDocumentRecord(
            id=f"doc_{uuid.uuid4().hex[:10]}",
            knowledge_base_id=knowledge_base_id,
            name=original_name or safe_name,
            path=str(target),
            file_type=target.suffix.lower().lstrip("."),
            size=target.stat().st_size,
            status="processing",
            processing_stage="queued",
            processing_progress=5,
            chunk_count=0,
            created_at=now,
            updated_at=now,
        )
        self._state["documents"].append(document.model_dump())
        self._update_knowledge_base_counts(knowledge_base_id)
        self._save()
        return document


def _wiki_register_source(self, kb, source, original_name):
    import hashlib
    from tokenmind.knowledge.wiki_paths import get_kb_root, safe_wiki_filename
    kb_root = Path(kb.root_path or get_kb_root(self.root.parent, kb.id))
    raw_dir = kb_root / "raw" / "files"
    raw_dir.mkdir(parents=True, exist_ok=True)
    sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    safe_name = safe_wiki_filename(Path(original_name).stem) + Path(original_name).suffix
    target = raw_dir / safe_name
    if target.exists():
        target = raw_dir / f"{Path(safe_name).stem}-{uuid.uuid4().hex[:6]}{Path(safe_name).suffix}"
    shutil.copy2(source, target)
    now = utc_now_iso()

    document = KnowledgeDocumentRecord(
        id=f"doc_{uuid.uuid4().hex[:10]}",
        knowledge_base_id=kb.id,
        name=original_name or safe_name,
        path=str(target),
        file_type=target.suffix.lower().lstrip("."),
        size=target.stat().st_size,
        status="processing",
        processing_stage="queued",
        processing_progress=5,
        chunk_count=0,
        created_at=now,
        updated_at=now,
    )
    with self._state_lock:
        self._reload()
        self._state["documents"].append(document.model_dump())
        self._update_wiki_cache(kb_root, sha256=sha256, document=document)
        self._update_knowledge_base_counts(kb.id)
        self._save()
    return document


def _update_wiki_cache(self, kb_root: Path, *, sha256: str, document):
    import json
    cache_path = kb_root / ".wiki-cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    cache["sources"][f"sha256:{sha256}"] = {
        "document_id": document.id,
        "title": document.name,
        "raw_path": str(Path(document.path).relative_to(kb_root)),
        "status": "registered",
        "created_at": document.created_at,
    }
    cache["updated_at"] = utc_now_iso()
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v -k "upload"`
Expected: 3 PASS.

- [ ] **Step 5: Run full existing test suite to confirm RAG untouched**

Run: `.venv/bin/pytest tests/test_knowledge_service.py -v 2>&1 | tail -20`
Expected: All previously passing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add tokenmind/knowledge/service.py tests/test_knowledge_dual_mode.py
git commit -m "feat(knowledge): register_document_upload dispatches by kb type"
```

---

## Phase 3: Source 页面（模板版）

### Task 8: 创建 wiki_ingest 模板 source page

**Files:**
- Create: `tokenmind/knowledge/wiki_ingest.py`
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Add test**

Append:

```python
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
```

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py::test_compile_source_page_template -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Create wiki_ingest.py**

Create `tokenmind/knowledge/wiki_ingest.py`:

```python
"""Wiki ingest pipeline: raw → source page → (later) entity/topic pages."""
from __future__ import annotations

from datetime import datetime, timezone


def compile_source_page_template(
    *,
    page_id: str,
    source_id: str,
    title: str,
    raw_path: str,
    sha256: str,
    body_text: str,
    max_excerpt: int = 800,
) -> str:
    """Build a deterministic source page (no LLM)."""
    now = datetime.now(timezone.utc).isoformat()
    excerpt = body_text.strip()
    if len(excerpt) > max_excerpt:
        excerpt = excerpt[: max_excerpt - 3] + "..."

    return (
        f"---\n"
        f"id: {page_id}\n"
        f"type: source\n"
        f"source_id: {source_id}\n"
        f"title: {title}\n"
        f"created_at: {now}\n"
        f"updated_at: {now}\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"## 摘要\n\n"
        f"（待 LLM 编译生成摘要）\n\n"
        f"## 内容节选\n\n"
        f"{excerpt}\n\n"
        f"## 原始资料\n\n"
        f"- 路径：{raw_path}\n"
        f"- SHA256：{sha256}\n\n"
        f"## 关联\n\n"
        f"- [[待归类主题]]\n"
    )
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py::test_compile_source_page_template -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenmind/knowledge/wiki_ingest.py tests/test_knowledge_dual_mode.py
git commit -m "feat(knowledge): wiki_ingest.compile_source_page_template (no LLM yet)"
```

---

### Task 9: process_document 按 type 分发，Wiki 路径写 source page

**Files:**
- Modify: `tokenmind/knowledge/service.py:798-885`
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Add tests**

Append:

```python
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
```

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v -k "process_wiki or process_rag"`
Expected: wiki tests FAIL.

- [ ] **Step 3: Branch process_document**

Locate `process_document` at `tokenmind/knowledge/service.py:798`. Rename it to `_rag_process_document` keeping body intact. Add new dispatcher:

```python
def process_document(self, document_id: str) -> KnowledgeDocumentRecord:
    with self._state_lock:
        self._reload()
        existing = next((item for item in self._state["documents"] if item["id"] == document_id), None)
        if existing is None:
            raise KeyError(f"Knowledge document not found: {document_id}")
        kb_id = str(existing["knowledge_base_id"])
    kb = self.get_knowledge_base(kb_id)
    if kb.type == "wiki":
        return self._wiki_process_document(kb, document_id)
    return self._rag_process_document(document_id)


def _wiki_process_document(self, kb, document_id):
    import uuid as _uuid
    from tokenmind.knowledge.wiki_extractors import extract_text
    from tokenmind.knowledge.wiki_ingest import compile_source_page_template
    from tokenmind.knowledge.wiki_paths import safe_wiki_filename

    def save_state(**updates):
        with self._state_lock:
            self._reload()
            updated = self._update_document_record(document_id, **updates)
            self._update_knowledge_base_counts(kb.id)
            self._save()
            return updated

    doc = next(item for item in self._state["documents"] if item["id"] == document_id)
    path = Path(doc["path"])
    if not path.exists():
        return save_state(status="failed", processing_stage="failed", error_message="raw missing")

    save_state(status="processing", processing_stage="extracting", processing_progress=25)
    try:
        text = extract_text(path)
    except Exception as exc:
        return save_state(status="failed", processing_stage="failed", error_message=str(exc))

    save_state(processing_stage="compiling_source", processing_progress=70)
    kb_root = Path(kb.root_path)
    raw_rel = str(path.relative_to(kb_root))
    page_id = f"page_{_uuid.uuid4().hex[:10]}"
    title = doc.get("name") or path.stem
    safe_name = safe_wiki_filename(Path(title).stem) + ".md"

    # SHA from cache
    import json
    cache = json.loads((kb_root / ".wiki-cache.json").read_text(encoding="utf-8"))
    sha = ""
    for key, entry in cache.get("sources", {}).items():
        if entry.get("document_id") == document_id:
            sha = key.split(":", 1)[1] if ":" in key else ""
            break

    page_md = compile_source_page_template(
        page_id=page_id,
        source_id=document_id,
        title=title,
        raw_path=raw_rel,
        sha256=sha,
        body_text=text,
    )
    page_path = kb_root / "wiki" / "sources" / safe_name
    page_path.write_text(page_md, encoding="utf-8")

    cache["sources"].setdefault(f"sha256:{sha}", {})["status"] = "ready"
    cache["sources"][f"sha256:{sha}"]["source_page_id"] = page_id
    cache["pages"][page_id] = {
        "path": f"wiki/sources/{safe_name}",
        "type": "source",
        "title": title,
        "source_id": document_id,
    }
    (kb_root / ".wiki-cache.json").write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    return save_state(status="ready", processing_stage="ready", processing_progress=100)
```

- [ ] **Step 4: Update KB count helper to cover Wiki**

`_update_knowledge_base_counts` (`service.py:295` and nearby) currently sets `document_count` only. For Wiki KB also recompute `source_count` and `page_count` from `.wiki-cache.json`. Add inside the loop where the matching kb is found:

```python
if item.get("type") == "wiki":
    import json
    cache_path = Path(item.get("root_path") or "") / ".wiki-cache.json"
    if cache_path.is_file():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            item["source_count"] = len(cache.get("sources", {}))
            item["page_count"] = len(cache.get("pages", {}))
        except Exception:
            pass
```

- [ ] **Step 5: Verify pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v`
Expected: all PASS.

Then run full KB test suite:
Run: `.venv/bin/pytest tests/test_knowledge_service.py -v 2>&1 | tail -10`
Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add tokenmind/knowledge/service.py tests/test_knowledge_dual_mode.py
git commit -m "feat(knowledge): process_document dispatch; wiki path writes source page"
```

---

## Phase 4: LLM 编译 entity/topic 页面

### Task 10: wiki_prompts.py（LLM 输入模板）

**Files:**
- Create: `tokenmind/knowledge/wiki_prompts.py`
- Test: `tests/test_wiki_ingest.py`

- [ ] **Step 1: Create file with tests**

Create `tests/test_wiki_ingest.py`:

```python
import json
import pytest
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
```

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_wiki_ingest.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement wiki_prompts.py**

Create `tokenmind/knowledge/wiki_prompts.py`:

```python
"""LLM prompts for compiling raw text into Wiki pages."""
from __future__ import annotations


def build_compile_system_prompt(language: str = "zh") -> str:
    return (
        "You are a knowledge base curator. Given raw source text, you produce a strict JSON object describing:\n"
        "  - source_summary: { title, summary (<=80 words), key_points (list of 3-6) }\n"
        "  - entities: list of { title, type (concept|tool|person|project|other), summary (<=40 words),\n"
        "      content (Markdown, <=300 words), aliases (list), links (list of related entity/topic titles) }\n"
        "  - topics: list of { title, summary (<=40 words), content (Markdown), links (list of entity/topic titles) }\n"
        "Use [[title]] inline to link to other pages. Reuse existing page titles when they match the same concept.\n"
        "Output language: " + ("Chinese" if language == "zh" else "English") + ".\n"
        "Output ONLY a valid JSON object. No prose, no markdown code fences."
    )


def build_compile_user_prompt(
    *,
    purpose: str,
    existing_titles: list[str],
    source_title: str,
    source_text: str,
    max_source_chars: int = 8000,
) -> str:
    text = source_text.strip()
    if len(text) > max_source_chars:
        text = text[:max_source_chars] + "\n...[truncated]"
    existing = ", ".join(f"[[{t}]]" for t in existing_titles[:60]) or "(none)"
    return (
        f"# Knowledge base purpose\n{purpose}\n\n"
        f"# Existing page titles (reuse when applicable)\n{existing}\n\n"
        f"# Source title\n{source_title}\n\n"
        f"# Source text\n{text}\n\n"
        "Return the JSON object now."
    )
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_wiki_ingest.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenmind/knowledge/wiki_prompts.py tests/test_wiki_ingest.py
git commit -m "feat(knowledge): wiki_prompts for LLM compile (entity/topic extraction)"
```

---

### Task 11: wiki_ingest.compile_with_llm（mock LLM 测试）

**Files:**
- Modify: `tokenmind/knowledge/wiki_ingest.py`
- Test: `tests/test_wiki_ingest.py`

- [ ] **Step 1: Add test with mocked LLM**

Append to `tests/test_wiki_ingest.py`:

```python
def test_compile_with_llm_writes_entity_and_topic_pages(tmp_path):
    from tokenmind.knowledge.wiki_paths import ensure_wiki_structure
    from tokenmind.knowledge.wiki_ingest import compile_with_llm

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
```

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_wiki_ingest.py::test_compile_with_llm_writes_entity_and_topic_pages -v`
Expected: FAIL.

- [ ] **Step 3: Implement compile_with_llm**

Append to `tokenmind/knowledge/wiki_ingest.py`:

```python
import json
import re
from pathlib import Path

from tokenmind.knowledge.wiki_paths import safe_wiki_filename
from tokenmind.knowledge.wiki_prompts import (
    build_compile_system_prompt,
    build_compile_user_prompt,
)


async def compile_with_llm(
    *,
    provider,
    model: str,
    kb_root: Path,
    source_title: str,
    source_text: str,
    source_page_id: str,
    language: str = "zh",
) -> dict:
    """Call LLM to compile source into entity/topic pages. Returns parsed JSON.

    On JSON parse failure, returns {"_fallback": true, "error": ...} and does NOT write pages.
    Caller decides whether to retry or accept template-only source page.
    """
    purpose = _read_purpose(kb_root)
    existing_titles = _scan_existing_titles(kb_root)
    sys_msg = build_compile_system_prompt(language=language)
    user_msg = build_compile_user_prompt(
        purpose=purpose,
        existing_titles=existing_titles,
        source_title=source_title,
        source_text=source_text,
    )
    response = await provider.chat(
        messages=[
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ],
        model=model,
        max_tokens=4000,
    )
    raw = (response.content or "").strip()
    raw = re.sub(r"^```(json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"_fallback": True, "error": str(exc), "raw": raw[:500]}

    for entity in data.get("entities", []):
        _write_or_merge_page(
            kb_root=kb_root,
            page_type="entity",
            data=entity,
            source_page_id=source_page_id,
        )
    for topic in data.get("topics", []):
        _write_or_merge_page(
            kb_root=kb_root,
            page_type="topic",
            data=topic,
            source_page_id=source_page_id,
        )
    return data


def _read_purpose(kb_root: Path) -> str:
    purpose_file = kb_root / "purpose.md"
    return purpose_file.read_text(encoding="utf-8") if purpose_file.is_file() else ""


def _scan_existing_titles(kb_root: Path) -> list[str]:
    titles: list[str] = []
    for sub in ("entities", "topics"):
        d = kb_root / "wiki" / sub
        if d.is_dir():
            titles.extend(p.stem for p in d.glob("*.md"))
    return titles


def _write_or_merge_page(*, kb_root: Path, page_type: str, data: dict, source_page_id: str) -> None:
    import uuid as _uuid
    from datetime import datetime, timezone
    title = data.get("title", "untitled").strip()
    safe = safe_wiki_filename(title)
    dir_name = "entities" if page_type == "entity" else "topics"
    path = kb_root / "wiki" / dir_name / f"{safe}.md"
    now = datetime.now(timezone.utc).isoformat()

    summary = data.get("summary", "").strip()
    content = data.get("content", "").strip()
    links = data.get("links", [])
    aliases = data.get("aliases", []) if page_type == "entity" else []
    link_block = "\n".join(f"- [[{l}]]" for l in links) or "- 暂无"

    if path.exists():
        # Append a "New from {source}" section; do not rewrite existing body.
        body = path.read_text(encoding="utf-8")
        addition = (
            f"\n\n## 新增信息（来自 [[{source_page_id}]] · {now}）\n\n"
            f"{summary}\n\n{content}\n"
        )
        path.write_text(body + addition, encoding="utf-8")
        return

    frontmatter = (
        f"---\n"
        f"id: page_{_uuid.uuid4().hex[:10]}\n"
        f"type: {page_type}\n"
        f"title: {title}\n"
        + (f"aliases:\n" + "".join(f"  - {a}\n" for a in aliases) if aliases else "")
        + f"sources:\n  - {source_page_id}\n"
        f"created_at: {now}\n"
        f"updated_at: {now}\n"
        f"---\n\n"
    )
    section = "关联主题" if page_type == "entity" else "相关页面"
    body = (
        f"# {title}\n\n"
        f"## 摘要\n\n{summary}\n\n"
        f"## 内容\n\n{content}\n\n"
        f"## {section}\n\n{link_block}\n\n"
        f"## 来源\n\n- [[{source_page_id}]]\n"
    )
    path.write_text(frontmatter + body, encoding="utf-8")
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_wiki_ingest.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenmind/knowledge/wiki_ingest.py tests/test_wiki_ingest.py
git commit -m "feat(knowledge): compile_with_llm writes entity/topic pages from JSON"
```

---

### Task 12: 接入 compile_with_llm 到 _wiki_process_document（可选 LLM）

**Files:**
- Modify: `tokenmind/knowledge/service.py` `_wiki_process_document`
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Add test guarded by mock provider**

Append to `tests/test_knowledge_dual_mode.py`:

```python
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
```

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v -k "calls_llm or skips_llm"`
Expected: first test FAIL.

- [ ] **Step 3: Wire compile_with_llm into _wiki_process_document**

In `tokenmind/knowledge/service.py`:

1. Add imports at top:
   ```python
   from tokenmind.knowledge.wiki_ingest import compile_with_llm
   ```

2. Add `__init__` attrs (find `__init__` method of `KnowledgeService`):
   ```python
   self._wiki_llm_provider = None
   self._wiki_llm_model: str | None = None
   ```

3. Add setter:
   ```python
   def set_wiki_llm(self, provider, model: str) -> None:
       self._wiki_llm_provider = provider
       self._wiki_llm_model = model
   ```

4. Inside `_wiki_process_document`, after writing the template source page and before the final `save_state(status="ready", ...)`, call:
   ```python
   if self._wiki_llm_provider is not None and self._wiki_llm_model:
       try:
           import asyncio
           coro = compile_with_llm(
               provider=self._wiki_llm_provider,
               model=self._wiki_llm_model,
               kb_root=kb_root,
               source_title=title,
               source_text=text,
               source_page_id=page_id,
               language=getattr(kb, "language", "zh"),
           )
           if asyncio.get_event_loop().is_running():
               # Called from sync method; run via threadpool-friendly path
               loop = asyncio.new_event_loop()
               try:
                   loop.run_until_complete(coro)
               finally:
                   loop.close()
           else:
               asyncio.run(coro)
       except Exception as exc:
           logger.warning(f"wiki LLM compile failed: {exc}")
   ```

   Note: `logger` is loguru; import if missing.

- [ ] **Step 4: Wire provider in AgentLoop**

Edit `tokenmind/agent/loop.py` after line 162 (where `self.knowledge = KnowledgeService(...)` is constructed):

```python
self.knowledge.set_wiki_llm(provider=provider, model=self.model)
```

- [ ] **Step 5: Verify pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v -k "calls_llm or skips_llm"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tokenmind/knowledge/service.py tokenmind/agent/loop.py tests/test_knowledge_dual_mode.py
git commit -m "feat(knowledge): invoke compile_with_llm in wiki process pipeline when provider set"
```

---

## Phase 5: Wiki 查询 + 工具 + 会话激活

### Task 13: wiki_query.py 纯 lexical + 双链扩展

**Files:**
- Create: `tokenmind/knowledge/wiki_query.py`
- Test: `tests/test_wiki_query.py`

- [ ] **Step 1: Create tests**

Create `tests/test_wiki_query.py`:

```python
from pathlib import Path
import pytest

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
```

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_wiki_query.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement wiki_query.py**

Create `tokenmind/knowledge/wiki_query.py`:

```python
"""Wiki query: lexical match + double-link expansion."""
from __future__ import annotations

import re
from pathlib import Path

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")


def query_wiki_pages(
    kb_root: Path,
    query: str,
    *,
    top_k: int = 5,
    expand_depth: int = 1,
) -> list[dict]:
    """Return list of {title, path, type, summary, content (snippet), score, matched_via}."""
    query = (query or "").strip()
    if not query:
        return []
    pages = _scan_pages(kb_root)
    q_lower = query.lower()

    scored: list[dict] = []
    for page in pages:
        score = 0
        matched_via = []
        title_lower = page["title"].lower()
        if q_lower == title_lower:
            score += 10
            matched_via.append("title_exact")
        elif q_lower in title_lower:
            score += 6
            matched_via.append("title_substr")
        body_lower = page["content"].lower()
        body_hits = body_lower.count(q_lower)
        if body_hits:
            score += min(body_hits, 4)
            matched_via.append(f"body_x{body_hits}")
        if score > 0:
            page["score"] = score
            page["matched_via"] = matched_via
            scored.append(page)

    scored.sort(key=lambda p: -p["score"])
    direct = scored[:top_k]

    if expand_depth <= 0 or not direct:
        return [_snippet(p, query) for p in direct]

    seen = {p["path"] for p in direct}
    expanded = list(direct)
    for page in direct:
        for link in _extract_wikilinks(page["content"]):
            for candidate in pages:
                if candidate["title"] == link and candidate["path"] not in seen:
                    candidate["score"] = 1
                    candidate["matched_via"] = [f"link_from:{page['title']}"]
                    expanded.append(candidate)
                    seen.add(candidate["path"])
    return [_snippet(p, query) for p in expanded[: top_k * 2]]


def read_wiki_page(kb_root: Path, page_path: str) -> dict:
    """Return {title, type, path, frontmatter, content, outgoing_links}."""
    rel = Path(page_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"page_path must be relative within kb: {page_path}")
    full = kb_root / rel
    if not full.is_file():
        raise FileNotFoundError(f"page not found: {page_path}")
    raw = full.read_text(encoding="utf-8")
    frontmatter, content = _split_frontmatter(raw)
    return {
        "title": frontmatter.get("title", rel.stem),
        "type": frontmatter.get("type", _type_from_path(rel)),
        "path": str(rel).replace("\\", "/"),
        "frontmatter": frontmatter,
        "content": content,
        "outgoing_links": _extract_wikilinks(content),
    }


def backlinks(kb_root: Path, target_title: str) -> list[dict]:
    """Pages whose content contains [[target_title]]."""
    out = []
    for page in _scan_pages(kb_root):
        if target_title in _extract_wikilinks(page["content"]):
            out.append({"title": page["title"], "path": page["path"], "type": page["type"]})
    return out


def _scan_pages(kb_root: Path) -> list[dict]:
    pages: list[dict] = []
    wiki_dir = kb_root / "wiki"
    if not wiki_dir.is_dir():
        return pages
    for path in wiki_dir.rglob("*.md"):
        raw = path.read_text(encoding="utf-8")
        fm, content = _split_frontmatter(raw)
        rel = path.relative_to(kb_root)
        pages.append({
            "title": fm.get("title", path.stem),
            "type": fm.get("type", _type_from_path(rel)),
            "path": str(rel).replace("\\", "/"),
            "content": content,
        })
    return pages


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    _, fm_text, body = parts
    fm: dict = {}
    for line in fm_text.strip().splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm, body.lstrip("\n")


def _extract_wikilinks(text: str) -> list[str]:
    return [m.group(1).strip() for m in _WIKILINK_RE.finditer(text)]


def _type_from_path(rel: Path) -> str:
    parts = rel.parts
    if len(parts) >= 2 and parts[0] == "wiki":
        return parts[1].rstrip("s")  # entities -> entitie ; fix below
    return "page"


def _snippet(page: dict, query: str, ctx_chars: int = 120) -> dict:
    body = page["content"]
    lower = body.lower()
    idx = lower.find(query.lower())
    if idx < 0:
        snippet = body[:240]
    else:
        start = max(0, idx - ctx_chars)
        end = min(len(body), idx + len(query) + ctx_chars)
        snippet = ("..." if start > 0 else "") + body[start:end] + ("..." if end < len(body) else "")
    return {
        "title": page["title"],
        "type": page["type"],
        "path": page["path"],
        "snippet": " ".join(snippet.split())[:400],
        "score": page.get("score", 0),
        "matched_via": page.get("matched_via", []),
    }
```

Note: `_type_from_path` has a quick `.rstrip("s")` heuristic — fix it: replace the function body with:

```python
def _type_from_path(rel: Path) -> str:
    mapping = {"entities": "entity", "topics": "topic", "sources": "source",
               "comparisons": "comparison", "synthesis": "synthesis", "queries": "query"}
    parts = rel.parts
    if len(parts) >= 2 and parts[0] == "wiki":
        return mapping.get(parts[1], "page")
    return "page"
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_wiki_query.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenmind/knowledge/wiki_query.py tests/test_wiki_query.py
git commit -m "feat(knowledge): wiki_query lexical + 1-hop wikilink expansion"
```

---

### Task 14: Session.active_wiki_kb_id accessor

**Files:**
- Modify: `tokenmind/session/manager.py:51-62`
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Add test**

Append:

```python
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
```

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py::test_session_active_wiki_kb_id_accessor -v`
Expected: FAIL.

- [ ] **Step 3: Add accessor**

Add to `tokenmind/session/manager.py` after `project_id` property (around line 62):

```python
@property
def active_wiki_kb_id(self) -> str | None:
    value = self.metadata.get("active_wiki_kb_id")
    return value if isinstance(value, str) and value else None


def set_active_wiki_kb_id(self, kb_id: str | None) -> None:
    if kb_id:
        self.metadata["active_wiki_kb_id"] = kb_id
    else:
        self.metadata.pop("active_wiki_kb_id", None)
    self.updated_at = datetime.now()
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py::test_session_active_wiki_kb_id_accessor -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenmind/session/manager.py tests/test_knowledge_dual_mode.py
git commit -m "feat(session): add active_wiki_kb_id accessor"
```

---

### Task 15: 5 个 Wiki 工具

**Files:**
- Create: `tokenmind/agent/tools/wiki.py`
- Test: `tests/test_wiki_tools.py`

- [ ] **Step 1: Add tests**

Create `tests/test_wiki_tools.py`:

```python
import asyncio
import pytest
from pathlib import Path

from tokenmind.knowledge.wiki_paths import ensure_wiki_structure
from tokenmind.agent.tools.wiki import (
    WikiIndexTool,
    WikiGrepTool,
    WikiReadTool,
    WikiBacklinksTool,
    WikiGraphTool,
)


@pytest.fixture
def seeded_kb(tmp_path):
    kb_root = tmp_path / "knowledge" / "kb_t"
    ensure_wiki_structure(kb_root, name="t", description="", language="zh")
    (kb_root / "wiki" / "entities" / "Foo.md").write_text(
        "---\ntype: entity\ntitle: Foo\n---\n# Foo\nMentions [[Bar]].\n", encoding="utf-8",
    )
    (kb_root / "wiki" / "topics" / "Bar.md").write_text(
        "---\ntype: topic\ntitle: Bar\n---\n# Bar\nIs referenced by Foo.\n", encoding="utf-8",
    )
    return kb_root


def _resolver(kb_root):
    """A trivial active KB resolver for tests."""
    def get_active():
        return {"kb_root": kb_root, "kb_name": "t"}
    return get_active


def test_wiki_index_returns_index_md(seeded_kb):
    tool = WikiIndexTool(get_active_kb=_resolver(seeded_kb))
    result = asyncio.run(tool.execute())
    assert "# t" in result  # index.md header


def test_wiki_grep_finds_title(seeded_kb):
    tool = WikiGrepTool(get_active_kb=_resolver(seeded_kb))
    result = asyncio.run(tool.execute(keyword="Foo"))
    assert "Foo" in result
    assert "entities/Foo.md" in result


def test_wiki_read_returns_full_content(seeded_kb):
    tool = WikiReadTool(get_active_kb=_resolver(seeded_kb))
    result = asyncio.run(tool.execute(page_path="wiki/entities/Foo.md"))
    assert "Mentions [[Bar]]" in result


def test_wiki_backlinks_finds_referrers(seeded_kb):
    tool = WikiBacklinksTool(get_active_kb=_resolver(seeded_kb))
    result = asyncio.run(tool.execute(page_path="wiki/topics/Bar.md"))
    assert "Foo" in result


def test_wiki_graph_returns_json(seeded_kb):
    tool = WikiGraphTool(get_active_kb=_resolver(seeded_kb))
    result = asyncio.run(tool.execute())
    assert "nodes" in result
    assert "edges" in result


def test_wiki_tool_returns_error_when_no_active_kb(tmp_path):
    def get_active():
        return None
    tool = WikiGrepTool(get_active_kb=get_active)
    result = asyncio.run(tool.execute(keyword="x"))
    assert "Error" in result
    assert "active" in result.lower()
```

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_wiki_tools.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement tools**

Create `tokenmind/agent/tools/wiki.py`:

```python
"""Tools for the LLM to navigate the active Wiki knowledge base."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from tokenmind.agent.tools.base import Tool
from tokenmind.knowledge.wiki_query import (
    backlinks as wiki_backlinks_query,
    query_wiki_pages,
    read_wiki_page,
)

ActiveKbResolver = Callable[[], dict | None]
# Returns {"kb_root": Path, "kb_name": str, "kb_id": str} or None when no active KB.

_NO_ACTIVE = "Error: No active Wiki knowledge base for this session. Ask the user to select one."


class _BaseWikiTool(Tool):
    def __init__(self, get_active_kb: ActiveKbResolver):
        self._get_active = get_active_kb

    def _resolve(self) -> tuple[Path, str] | None:
        active = self._get_active()
        if not active:
            return None
        return Path(active["kb_root"]), str(active.get("kb_name", ""))


class WikiIndexTool(_BaseWikiTool):
    @property
    def name(self) -> str:
        return "wiki_index"

    @property
    def description(self) -> str:
        return (
            "Return the index.md of the currently active Wiki knowledge base. "
            "Call this FIRST to understand the KB structure before grepping."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> str:
        ctx = self._resolve()
        if ctx is None:
            return _NO_ACTIVE
        kb_root, _ = ctx
        index = kb_root / "index.md"
        if not index.is_file():
            return "Error: index.md missing"
        return index.read_text(encoding="utf-8")


class WikiGrepTool(_BaseWikiTool):
    @property
    def name(self) -> str:
        return "wiki_grep"

    @property
    def description(self) -> str:
        return (
            "Search the active Wiki KB for pages matching the keyword. "
            "Returns up to top_k page paths with snippets. Follow [[links]] inside snippets with wiki_read."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "keyword to search"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
            },
            "required": ["keyword"],
        }

    async def execute(self, *, keyword: str, top_k: int = 5) -> str:
        ctx = self._resolve()
        if ctx is None:
            return _NO_ACTIVE
        kb_root, _ = ctx
        hits = query_wiki_pages(kb_root, keyword, top_k=top_k, expand_depth=1)
        if not hits:
            return f"No pages matched '{keyword}'."
        lines = [f"Found {len(hits)} page(s):"]
        for hit in hits:
            lines.append(f"- [{hit['type']}] {hit['title']} ({hit['path']})")
            lines.append(f"  {hit['snippet']}")
        return "\n".join(lines)


class WikiReadTool(_BaseWikiTool):
    @property
    def name(self) -> str:
        return "wiki_read"

    @property
    def description(self) -> str:
        return (
            "Read the full content of a Wiki page by its relative path "
            "(e.g. 'wiki/entities/Foo.md'). Follow [[links]] you see in the content with another wiki_read."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "page_path": {"type": "string", "description": "path relative to KB root, e.g. 'wiki/entities/Foo.md'"},
            },
            "required": ["page_path"],
        }

    async def execute(self, *, page_path: str) -> str:
        ctx = self._resolve()
        if ctx is None:
            return _NO_ACTIVE
        kb_root, _ = ctx
        try:
            page = read_wiki_page(kb_root, page_path)
        except FileNotFoundError:
            return f"Error: page not found: {page_path}"
        except ValueError as exc:
            return f"Error: {exc}"
        content = page["content"]
        if len(content) > 4000:
            content = content[:4000] + "\n\n[... page truncated; ask for specific sections ...]"
        return (
            f"# {page['title']}\n"
            f"Type: {page['type']}\n"
            f"Path: {page['path']}\n\n"
            f"{content}"
        )


class WikiBacklinksTool(_BaseWikiTool):
    @property
    def name(self) -> str:
        return "wiki_backlinks"

    @property
    def description(self) -> str:
        return "List pages that link to the given page via [[title]]."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"page_path": {"type": "string"}},
            "required": ["page_path"],
        }

    async def execute(self, *, page_path: str) -> str:
        ctx = self._resolve()
        if ctx is None:
            return _NO_ACTIVE
        kb_root, _ = ctx
        try:
            page = read_wiki_page(kb_root, page_path)
        except FileNotFoundError:
            return f"Error: page not found: {page_path}"
        refs = wiki_backlinks_query(kb_root, page["title"])
        if not refs:
            return f"No backlinks to [[{page['title']}]]."
        lines = [f"{len(refs)} page(s) link to [[{page['title']}]]:"]
        for r in refs:
            lines.append(f"- [{r['type']}] {r['title']} ({r['path']})")
        return "\n".join(lines)


class WikiGraphTool(_BaseWikiTool):
    @property
    def name(self) -> str:
        return "wiki_graph"

    @property
    def description(self) -> str:
        return "Return the full link graph (nodes + edges) of the active KB. Heavy for large KBs."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> str:
        ctx = self._resolve()
        if ctx is None:
            return _NO_ACTIVE
        kb_root, _ = ctx
        graph_file = kb_root / "graph-data.json"
        if not graph_file.is_file():
            return json.dumps({"nodes": [], "edges": [], "note": "graph not built yet"})
        return graph_file.read_text(encoding="utf-8")
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_wiki_tools.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenmind/agent/tools/wiki.py tests/test_wiki_tools.py
git commit -m "feat(tools): wiki_index/grep/read/backlinks/graph for LLM-driven wiki navigation"
```

---

### Task 16: 注册 Wiki 工具到 AgentLoop

**Files:**
- Modify: `tokenmind/agent/loop.py`
- Test: `tests/test_wiki_tools.py`

- [ ] **Step 1: Add a test verifying registration via instance check**

Append to `tests/test_wiki_tools.py`:

```python
def test_agent_loop_registers_wiki_tools():
    """AgentLoop._register_default_tools includes all 5 wiki_* tools."""
    import inspect
    from tokenmind.agent import loop as loop_module

    src = inspect.getsource(loop_module.AgentLoop._register_default_tools)
    for tool_class in ("WikiIndexTool", "WikiGrepTool", "WikiReadTool",
                       "WikiBacklinksTool", "WikiGraphTool"):
        assert tool_class in src, f"{tool_class} not registered in _register_default_tools"
```

This is a source-level check (no AgentLoop construction needed). Real behavior is covered by the per-tool unit tests in this file and end-to-end manual verification in Task 25.

- [ ] **Step 2: Read existing _register_default_tools**

```bash
sed -n '214,260p' tokenmind/agent/loop.py
```

Note where tools are registered.

- [ ] **Step 3: Add wiki tool registration**

In `tokenmind/agent/loop.py`, around line 230 (after existing `self.tools.register(...)` calls in `_register_default_tools`), add:

```python
from tokenmind.agent.tools.wiki import (
    WikiIndexTool, WikiGrepTool, WikiReadTool, WikiBacklinksTool, WikiGraphTool,
)
self.tools.register(WikiIndexTool(get_active_kb=self._get_active_wiki_kb))
self.tools.register(WikiGrepTool(get_active_kb=self._get_active_wiki_kb))
self.tools.register(WikiReadTool(get_active_kb=self._get_active_wiki_kb))
self.tools.register(WikiBacklinksTool(get_active_kb=self._get_active_wiki_kb))
self.tools.register(WikiGraphTool(get_active_kb=self._get_active_wiki_kb))
```

Move the import to the top of the file alongside other tool imports.

- [ ] **Step 4: Add _get_active_wiki_kb method**

Add to `AgentLoop` class (anywhere in the class body):

```python
def _get_active_wiki_kb(self) -> dict | None:
    """Return active Wiki KB context for the session currently being processed.

    Returns {"kb_root": Path, "kb_name": str, "kb_id": str} or None.
    The current session key is tracked on a contextvar.
    """
    session_key = self._current_session_key.get(None)
    if not session_key:
        return None
    try:
        session = self.sessions.get_session(session_key)
    except Exception:
        return None
    kb_id = session.active_wiki_kb_id
    if not kb_id:
        return None
    try:
        kb = self.knowledge.get_knowledge_base(kb_id)
    except Exception:
        return None
    if kb.type != "wiki" or not kb.root_path:
        return None
    return {"kb_root": Path(kb.root_path), "kb_name": kb.name, "kb_id": kb.id}
```

- [ ] **Step 5: Plumb _current_session_key contextvar**

At the top of `tokenmind/agent/loop.py`:

```python
from contextvars import ContextVar
```

In `__init__`:
```python
self._current_session_key: ContextVar[str | None] = ContextVar("session_key", default=None)
```

Wherever the agent enters a session loop (look for `async def _run_agent_loop` or per-session dispatch), wrap the run with:
```python
token = self._current_session_key.set(session_key)
try:
    ...
finally:
    self._current_session_key.reset(token)
```

Grep `def _run_agent_loop\|async def _dispatch` to locate.

- [ ] **Step 6: Verify pass**

Run: `.venv/bin/pytest tests/test_wiki_tools.py tests/test_knowledge_dual_mode.py -v`
Expected: all PASS.

Run full backend lint:
`.venv/bin/ruff check tokenmind/agent/loop.py tokenmind/agent/tools/wiki.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add tokenmind/agent/loop.py tests/test_wiki_tools.py
git commit -m "feat(agent): register wiki_* tools with session-scoped active KB resolver"
```

---

### Task 17: ContextBuilder 注入 [Active Wiki Knowledge Base] 段

**Files:**
- Modify: `tokenmind/agent/context.py`
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Add tests**

Append to `tests/test_knowledge_dual_mode.py`:

```python
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
```

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v -k "active_wiki_section"`
Expected: FAIL.

- [ ] **Step 3: Add tags + builder method**

Edit `tokenmind/agent/context.py`. Near the existing `_KNOWLEDGE_CONTEXT_TAG` constants (around line 25, search for that string), add:

```python
_ACTIVE_WIKI_TAG = "[Active Wiki Knowledge Base]"
_ACTIVE_WIKI_END_TAG = "[/Active Wiki Knowledge Base]"
```

Add the build method as a staticmethod near `_build_knowledge_context`:

```python
@staticmethod
def _build_active_wiki_section(active: dict | None) -> str | None:
    if not active:
        return None
    name = active.get("kb_name", "(unnamed)")
    purpose = (active.get("purpose_summary") or "").strip().splitlines()
    purpose_line = purpose[0] if purpose else "(no purpose set)"
    lines = [
        ContextBuilder._ACTIVE_WIKI_TAG,
        "You have an active Wiki knowledge base for this conversation.",
        f"- Name: {name}",
        f"- Purpose: {purpose_line}",
        f"- Counts: {active.get('entity_count', 0)} entities, "
        f"{active.get('topic_count', 0)} topics, "
        f"{active.get('source_count', 0)} sources "
        f"({active.get('page_count', 0)} pages total)",
        "",
        "Tools available for this KB:",
        "  - wiki_index() — read the index.md to understand structure",
        "  - wiki_grep(keyword) — search by keyword",
        "  - wiki_read(page_path) — read a specific page",
        "  - wiki_backlinks(page_path) — find pages linking to one",
        "  - wiki_graph() — get the full link graph",
        "",
        "Prefer to read multiple pages and follow [[links]] before answering. "
        "Do not invent information not present in the Wiki.",
    ]
    if active.get("switched_from"):
        lines.append("")
        lines.append(
            f"Note: You previously used Wiki KB '{active['switched_from']}' in this conversation; "
            "tool results from it remain in history but the active KB is now the one above."
        )
    lines.append(ContextBuilder._ACTIVE_WIKI_END_TAG)
    return "\n".join(lines)
```

Also update `strip_metadata_prefix` (around line 211) to include the new tags in its `metadata_pairs` tuple:

```python
metadata_pairs = (
    (cls._RUNTIME_CONTEXT_TAG, cls._RUNTIME_CONTEXT_END_TAG),
    (cls._ATTACHMENTS_CONTEXT_TAG, cls._ATTACHMENTS_CONTEXT_END_TAG),
    (cls._KNOWLEDGE_CONTEXT_TAG, cls._KNOWLEDGE_CONTEXT_END_TAG),
    (cls._ACTIVE_WIKI_TAG, cls._ACTIVE_WIKI_END_TAG),
)
```

- [ ] **Step 4: Wire it into build_messages**

In `build_messages` (around line 295), add `active_wiki` param and use it:

```python
def build_messages(
    self,
    history: list[dict[str, Any]],
    current_message: str,
    skill_names: list[str] | None = None,
    media: list[str] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    knowledge_chunks: list[dict[str, Any]] | None = None,
    active_wiki: dict | None = None,
    channel: str | None = None,
    chat_id: str | None = None,
    current_role: str = "user",
) -> list[dict[str, Any]]:
    ...
    knowledge_ctx = self._build_knowledge_context(knowledge_chunks)
    active_wiki_ctx = self._build_active_wiki_section(active_wiki)
    metadata_blocks = [runtime_ctx]
    if attachments_ctx:
        metadata_blocks.append(attachments_ctx)
    if knowledge_ctx:
        metadata_blocks.append(knowledge_ctx)
    if active_wiki_ctx:
        metadata_blocks.append(active_wiki_ctx)
    ...
```

- [ ] **Step 5: Pass active_wiki from AgentLoop**

In `AgentLoop._run_agent_loop` (or wherever `self.context.build_messages` is called), construct the dict via `_get_active_wiki_kb()` plus an extra `purpose_summary` read:

```python
active_kb = self._get_active_wiki_kb()
active_wiki_arg = None
if active_kb:
    kb_root = active_kb["kb_root"]
    purpose = (kb_root / "purpose.md").read_text(encoding="utf-8") if (kb_root / "purpose.md").is_file() else ""
    kb = self.knowledge.get_knowledge_base(active_kb["kb_id"])
    active_wiki_arg = {
        "kb_name": active_kb["kb_name"],
        "purpose_summary": purpose[:400],
        "page_count": kb.page_count,
        "entity_count": kb.entity_count,
        "topic_count": kb.topic_count,
        "source_count": kb.source_count,
        "switched_from": session.metadata.get("_previous_wiki_kb_name"),
    }
messages = self.context.build_messages(..., active_wiki=active_wiki_arg)
```

- [ ] **Step 6: Verify pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v -k "active_wiki_section or previous_kb"`
Expected: 3 PASS.

- [ ] **Step 7: Commit**

```bash
git add tokenmind/agent/context.py tokenmind/agent/loop.py tests/test_knowledge_dual_mode.py
git commit -m "feat(context): inject [Active Wiki Knowledge Base] system prompt section"
```

---

### Task 18: retrieve_for_session 仅取 RAG KB

**Files:**
- Modify: `tokenmind/knowledge/service.py:930-1006`
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Add test**

Append:

```python
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
```

- [ ] **Step 2: Verify**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py::test_retrieve_for_session_skips_wiki_kbs -v`
Expected: depending on test ordering it may pass or fail; explicitly filter to be safe.

- [ ] **Step 3: Filter at retrieve_for_session**

Edit `tokenmind/knowledge/service.py:937`, replace:

```python
linked_ids = self.get_session_links(session_id)
```

with:

```python
all_linked_ids = self.get_session_links(session_id)
# Wiki KBs are not auto-retrieved; they're accessed via tools (wiki_*) when active.
with self._state_lock:
    self._reload()
    rag_kb_ids = {
        item["id"]
        for item in self._state["knowledge_bases"]
        if item["id"] in all_linked_ids and item.get("type", "rag") == "rag"
    }
linked_ids = [k for k in all_linked_ids if k in rag_kb_ids]
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py::test_retrieve_for_session_skips_wiki_kbs -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenmind/knowledge/service.py tests/test_knowledge_dual_mode.py
git commit -m "feat(knowledge): retrieve_for_session ignores wiki kbs (only rag auto-injects)"
```

---

### Task 19: 删除 Wiki KB 时清空会话 active_wiki_kb_id

**Files:**
- Modify: `tokenmind/knowledge/service.py:251-280` (`delete_knowledge_base`)
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Add test**

Append:

```python
def test_delete_wiki_kb_clears_active_in_sessions(tmp_path):
    from tokenmind.session.manager import SessionManager

    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("wiki", "", type="wiki")
    sm = SessionManager(tmp_path)
    s = sm.create_session("web:s1")
    s.set_active_wiki_kb_id(kb.id)
    sm.save_session(s)

    service.delete_knowledge_base(kb.id, session_manager=sm)

    reloaded = sm.get_session("web:s1")
    assert reloaded.active_wiki_kb_id is None
```

Note: this test assumes `SessionManager.create_session`, `.save_session`, `.get_session` exist. If signatures differ, adapt (check `tokenmind/session/manager.py`).

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py::test_delete_wiki_kb_clears_active_in_sessions -v`
Expected: FAIL.

- [ ] **Step 3: Extend delete_knowledge_base**

Edit `tokenmind/knowledge/service.py:251`, change signature to accept optional `session_manager`:

```python
def delete_knowledge_base(self, knowledge_base_id: str, *, session_manager=None) -> dict[str, Any]:
    # existing body ...
    # after cleanup of session_links, add:
    if session_manager is not None:
        for s in session_manager.list_sessions():
            if s.active_wiki_kb_id == knowledge_base_id:
                s.set_active_wiki_kb_id(None)
                session_manager.save_session(s)
    return {"success": True, "knowledge_base_id": knowledge_base_id}
```

Check `SessionManager` has `list_sessions` and `save_session` — if names differ adjust. Search:
```bash
grep -n "def list_sessions\|def save_session\|def get_session" tokenmind/session/manager.py
```

- [ ] **Step 4: Wire session_manager through ChatService**

In `tokenmind/server/app.py`, find the `delete_knowledge_base` wrapper in `ChatService` and pass `session_manager=self.sessions` to the underlying call.

- [ ] **Step 5: Verify pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py::test_delete_wiki_kb_clears_active_in_sessions -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tokenmind/knowledge/service.py tokenmind/server/app.py tests/test_knowledge_dual_mode.py
git commit -m "feat(knowledge): cascade-clear active_wiki_kb_id when wiki kb deleted"
```

---

## Phase 6: graph-data.json + API

### Task 20: wiki_graph.py 扫描链接生成图谱

**Files:**
- Create: `tokenmind/knowledge/wiki_graph.py`
- Test: `tests/test_wiki_graph.py`

- [ ] **Step 1: Create tests**

Create `tests/test_wiki_graph.py`:

```python
from pathlib import Path

from tokenmind.knowledge.wiki_paths import ensure_wiki_structure
from tokenmind.knowledge.wiki_graph import build_graph_data


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
```

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_wiki_graph.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement wiki_graph.py**

Create `tokenmind/knowledge/wiki_graph.py`:

```python
"""Scan wiki/ pages and build a [[link]] graph."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")


def build_graph_data(kb_root: Path, *, persist: bool = False) -> dict:
    wiki_dir = kb_root / "wiki"
    nodes_by_title: dict[str, dict] = {}
    edges: list[dict] = []
    broken: list[dict] = []

    if not wiki_dir.is_dir():
        graph = {"nodes": [], "edges": [], "broken_links": [], "updated_at": _now()}
        if persist:
            (kb_root / "graph-data.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
        return graph

    pages: list[tuple[str, Path, str, str]] = []  # (title, abs_path, page_type, content)
    for path in wiki_dir.rglob("*.md"):
        raw = path.read_text(encoding="utf-8")
        title, ptype, content = _parse_page(path, raw)
        rel = path.relative_to(kb_root)
        nodes_by_title[title] = {
            "id": title,
            "title": title,
            "type": ptype,
            "path": str(rel).replace("\\", "/"),
            "summary": "",
            "degree": 0,
        }
        pages.append((title, path, ptype, content))

    for title, _, _, content in pages:
        for link in _WIKILINK_RE.finditer(content):
            target = link.group(1).strip()
            if target == title:
                continue
            if target in nodes_by_title:
                edges.append({
                    "source": title,
                    "target": target,
                    "relation": "wiki_link",
                    "weight": 1.0,
                })
                nodes_by_title[title]["degree"] += 1
                nodes_by_title[target]["degree"] += 1
            else:
                broken.append({"from": title, "target": target})

    graph = {
        "nodes": list(nodes_by_title.values()),
        "edges": edges,
        "broken_links": broken,
        "updated_at": _now(),
    }
    if persist:
        (kb_root / "graph-data.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    return graph


def _parse_page(path: Path, raw: str) -> tuple[str, str, str]:
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            fm_text, body = parts[1], parts[2]
            fm = {}
            for line in fm_text.strip().splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    fm[k.strip()] = v.strip()
            title = fm.get("title", path.stem)
            ptype = fm.get("type", "page")
            return title, ptype, body
    return path.stem, "page", raw


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_wiki_graph.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenmind/knowledge/wiki_graph.py tests/test_wiki_graph.py
git commit -m "feat(knowledge): wiki_graph builds nodes+edges from [[wikilinks]]"
```

---

### Task 21: 编译后自动 rebuild graph

**Files:**
- Modify: `tokenmind/knowledge/service.py` `_wiki_process_document`
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Add test**

Append:

```python
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
```

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py::test_process_wiki_doc_rebuilds_graph -v`
Expected: FAIL (graph still empty initial).

- [ ] **Step 3: Trigger rebuild**

In `tokenmind/knowledge/service.py` `_wiki_process_document`, just before the final `save_state(status="ready", ...)` add:

```python
from tokenmind.knowledge.wiki_graph import build_graph_data
try:
    build_graph_data(kb_root, persist=True)
except Exception as exc:
    logger.warning(f"wiki graph rebuild failed: {exc}")
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py::test_process_wiki_doc_rebuilds_graph -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenmind/knowledge/service.py tests/test_knowledge_dual_mode.py
git commit -m "feat(knowledge): rebuild graph-data after each wiki ingest"
```

---

### Task 22: GET /api/knowledge/{kb_id}/graph 和 POST .../graph/rebuild

**Files:**
- Modify: `tokenmind/server/routes/knowledge.py`
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Add API tests**

Append:

```python
def test_api_get_graph_returns_json(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from tokenmind.server.app import create_app
    monkeypatch.setenv("TOKENMIND_WORKSPACE", str(tmp_path))
    app = create_app()
    client = TestClient(app)

    kb = client.post("/api/knowledge", json={"name": "g", "type": "wiki"}).json()
    resp = client.get(f"/api/knowledge/{kb['id']}/graph")
    assert resp.status_code == 200
    body = resp.json()
    assert "nodes" in body and "edges" in body


def test_api_get_graph_rejects_rag_kb(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from tokenmind.server.app import create_app
    monkeypatch.setenv("TOKENMIND_WORKSPACE", str(tmp_path))
    app = create_app()
    client = TestClient(app)
    kb = client.post("/api/knowledge", json={"name": "r"}).json()
    resp = client.get(f"/api/knowledge/{kb['id']}/graph")
    assert resp.status_code == 400


def test_api_rebuild_graph_returns_count(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from tokenmind.server.app import create_app
    monkeypatch.setenv("TOKENMIND_WORKSPACE", str(tmp_path))
    app = create_app()
    client = TestClient(app)
    kb = client.post("/api/knowledge", json={"name": "g", "type": "wiki"}).json()
    resp = client.post(f"/api/knowledge/{kb['id']}/graph/rebuild")
    assert resp.status_code == 200
    body = resp.json()
    assert "nodes" in body
```

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v -k "api_get_graph or api_rebuild_graph"`
Expected: 404.

- [ ] **Step 3: Add routes**

Append to `tokenmind/server/routes/knowledge.py`:

```python
@router.get("/{knowledge_base_id}/graph")
async def get_kb_graph(
    knowledge_base_id: str,
    service: Any = Depends(get_chat_service),
) -> dict:
    try:
        return service.get_wiki_graph(knowledge_base_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{knowledge_base_id}/graph/rebuild")
async def rebuild_kb_graph(
    knowledge_base_id: str,
    service: Any = Depends(get_chat_service),
) -> dict:
    try:
        return service.rebuild_wiki_graph(knowledge_base_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 4: Add ChatService methods**

In `tokenmind/server/app.py`, add to `ChatService`:

```python
def get_wiki_graph(self, kb_id: str) -> dict:
    import json
    kb = self.knowledge.get_knowledge_base(kb_id)
    if kb.type != "wiki":
        raise ValueError("graph is only available for wiki kbs")
    p = Path(kb.root_path) / "graph-data.json"
    if not p.is_file():
        return {"nodes": [], "edges": [], "updated_at": None}
    return json.loads(p.read_text(encoding="utf-8"))


def rebuild_wiki_graph(self, kb_id: str) -> dict:
    from tokenmind.knowledge.wiki_graph import build_graph_data
    kb = self.knowledge.get_knowledge_base(kb_id)
    if kb.type != "wiki":
        raise ValueError("graph is only available for wiki kbs")
    return build_graph_data(Path(kb.root_path), persist=True)
```

- [ ] **Step 5: Verify pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v -k "api_get_graph or api_rebuild_graph"`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add tokenmind/server/routes/knowledge.py tokenmind/server/app.py tests/test_knowledge_dual_mode.py
git commit -m "feat(api): GET /{kb_id}/graph and POST /{kb_id}/graph/rebuild for wiki kbs"
```

---

### Task 23: GET /api/knowledge/{kb_id}/pages 列出 wiki 页面

**Files:**
- Modify: `tokenmind/server/routes/knowledge.py`
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Add test**

Append:

```python
def test_api_list_pages_groups_by_type(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from tokenmind.server.app import create_app
    monkeypatch.setenv("TOKENMIND_WORKSPACE", str(tmp_path))
    app = create_app()
    client = TestClient(app)
    kb = client.post("/api/knowledge", json={"name": "g", "type": "wiki"}).json()

    # Seed a page manually
    from pathlib import Path as _P
    pages_dir = _P(tmp_path) / "knowledge" / kb["id"] / "wiki" / "entities"
    (pages_dir / "Foo.md").write_text(
        "---\ntype: entity\ntitle: Foo\n---\n# Foo\n", encoding="utf-8"
    )

    resp = client.get(f"/api/knowledge/{kb['id']}/pages")
    assert resp.status_code == 200
    body = resp.json()
    titles = [p["title"] for p in body["pages"]]
    assert "Foo" in titles
```

- [ ] **Step 2: Verify fail**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py::test_api_list_pages_groups_by_type -v`
Expected: 404.

- [ ] **Step 3: Add route + service method**

`tokenmind/server/routes/knowledge.py`:

```python
@router.get("/{knowledge_base_id}/pages")
async def list_wiki_pages(
    knowledge_base_id: str,
    service: Any = Depends(get_chat_service),
) -> dict:
    try:
        return {"pages": service.list_wiki_pages(knowledge_base_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

`tokenmind/server/app.py` `ChatService`:

```python
def list_wiki_pages(self, kb_id: str) -> list[dict]:
    from tokenmind.knowledge.wiki_query import _scan_pages  # public-ish helper
    kb = self.knowledge.get_knowledge_base(kb_id)
    if kb.type != "wiki":
        raise ValueError("pages endpoint is only for wiki kbs")
    pages = _scan_pages(Path(kb.root_path))
    return [{"title": p["title"], "type": p["type"], "path": p["path"]} for p in pages]
```

Note: `_scan_pages` is technically private. Either expose it (rename to `scan_pages`) or duplicate the loop here. Pick rename: edit `wiki_query.py` to export `scan_pages` as an alias:

```python
scan_pages = _scan_pages
```

And use `scan_pages` in `list_wiki_pages`.

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py::test_api_list_pages_groups_by_type -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenmind/server/routes/knowledge.py tokenmind/server/app.py tokenmind/knowledge/wiki_query.py tests/test_knowledge_dual_mode.py
git commit -m "feat(api): GET /{kb_id}/pages lists wiki pages by type"
```

---

### Task 24: PATCH /api/sessions/{session_id} 设置 active_wiki_kb_id

**Files:**
- Modify: `tokenmind/server/routes/sessions.py`
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Inspect current sessions routes**

```bash
grep -n "router\|@router\|active_wiki_kb_id" tokenmind/server/routes/sessions.py | head -30
```

Find the existing PATCH (or PUT) endpoint for session updates. If there isn't one, you'll add a new route.

- [ ] **Step 2: Add test**

Append:

```python
def test_api_patch_session_sets_active_wiki_kb_id(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from tokenmind.server.app import create_app
    monkeypatch.setenv("TOKENMIND_WORKSPACE", str(tmp_path))
    app = create_app()
    client = TestClient(app)
    kb = client.post("/api/knowledge", json={"name": "w", "type": "wiki"}).json()

    # Create a session by hitting chat history endpoint (or directly):
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


def test_api_patch_session_rejects_non_wiki_kb(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from tokenmind.server.app import create_app
    monkeypatch.setenv("TOKENMIND_WORKSPACE", str(tmp_path))
    app = create_app()
    client = TestClient(app)
    rag_kb = client.post("/api/knowledge", json={"name": "r"}).json()
    resp = client.patch(
        "/api/sessions/web:foo",
        json={"active_wiki_kb_id": rag_kb["id"]},
    )
    assert resp.status_code == 400
```

- [ ] **Step 3: Verify fail**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v -k "patch_session"`
Expected: 404 or method-not-allowed.

- [ ] **Step 4: Add PATCH endpoint**

In `tokenmind/server/routes/sessions.py`, add:

```python
from pydantic import BaseModel


class SessionPatchPayload(BaseModel):
    active_wiki_kb_id: str | None = None
    # Add more patchable fields here later if needed.


@router.patch("/{session_id}")
async def patch_session(
    session_id: str,
    payload: SessionPatchPayload,
    service: Any = Depends(get_chat_service),
) -> dict:
    try:
        return service.patch_session(session_id, payload.model_dump(exclude_unset=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

Note: the existing `sessions.py` may not have `router = APIRouter(...)` with the right prefix. Verify the prefix is `/api/sessions`. If not, adjust the URL.

- [ ] **Step 5: Add ChatService.patch_session**

In `tokenmind/server/app.py` `ChatService`:

```python
def patch_session(self, session_id: str, updates: dict) -> dict:
    session = self.sessions.get_session(session_id) or self.sessions.create_session(session_id)
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
        self.sessions.save_session(session)
    return {
        "session_id": session_id,
        "active_wiki_kb_id": session.active_wiki_kb_id,
    }
```

- [ ] **Step 6: Verify pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v -k "patch_session"`
Expected: 2 PASS.

- [ ] **Step 7: Commit**

```bash
git add tokenmind/server/routes/sessions.py tokenmind/server/app.py tests/test_knowledge_dual_mode.py
git commit -m "feat(api): PATCH /api/sessions/{id} accepts active_wiki_kb_id"
```

---

### Task 24a: 删除 Wiki 文档清理 source page + 重建 graph

**Files:**
- Modify: `tokenmind/knowledge/service.py` `delete_document`
- Test: `tests/test_knowledge_dual_mode.py`

- [ ] **Step 1: Find existing delete_document**

```bash
grep -n "def delete_document" tokenmind/knowledge/service.py
```

- [ ] **Step 2: Add test**

Append to `tests/test_knowledge_dual_mode.py`:

```python
def test_delete_wiki_document_removes_source_page_and_cache_entry(tmp_path):
    import json
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("w", "", type="wiki")
    src = tmp_path / "x.md"
    src.write_text("hello", encoding="utf-8")
    doc = service.register_document_upload(kb.id, src, "x.md")
    service.process_document(doc.id)

    kb_root = tmp_path / "knowledge" / kb.id
    source_pages_before = list((kb_root / "wiki" / "sources").glob("*.md"))
    assert source_pages_before, "precondition: source page exists"

    service.delete_document(kb.id, doc.id)

    # raw file deleted
    assert not Path(doc.path).exists()
    # source page deleted
    assert list((kb_root / "wiki" / "sources").glob("*.md")) == []
    # cache entry removed
    cache = json.loads((kb_root / ".wiki-cache.json").read_text())
    assert not any(e.get("document_id") == doc.id for e in cache["sources"].values())
```

- [ ] **Step 3: Verify fail**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v -k "delete_wiki_document"`
Expected: FAIL.

- [ ] **Step 4: Branch delete_document for Wiki**

In `delete_document` (current implementation deletes legacy doc + chunks), add Wiki branch at the start:

```python
def delete_document(self, knowledge_base_id: str, document_id: str) -> dict[str, Any]:
    kb = self.get_knowledge_base(knowledge_base_id)
    if kb.type == "wiki":
        return self._wiki_delete_document(kb, document_id)
    return self._rag_delete_document(knowledge_base_id, document_id)


def _wiki_delete_document(self, kb, document_id: str) -> dict[str, Any]:
    import json
    from tokenmind.knowledge.wiki_graph import build_graph_data

    kb_root = Path(kb.root_path)
    cache_path = kb_root / ".wiki-cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8"))

    source_page_id = None
    cache_key_to_remove = None
    for key, entry in cache.get("sources", {}).items():
        if entry.get("document_id") == document_id:
            source_page_id = entry.get("source_page_id")
            cache_key_to_remove = key
            break

    with self._state_lock:
        self._reload()
        doc = next((d for d in self._state["documents"] if d["id"] == document_id), None)
        if doc is None:
            raise KeyError(f"document not found: {document_id}")
        raw_path = Path(doc["path"])
        if raw_path.exists():
            raw_path.unlink()
        self._state["documents"] = [d for d in self._state["documents"] if d["id"] != document_id]
        self._update_knowledge_base_counts(kb.id)
        self._save()

    if source_page_id and source_page_id in cache.get("pages", {}):
        page_rel = cache["pages"][source_page_id]["path"]
        page_path = kb_root / page_rel
        if page_path.exists():
            page_path.unlink()
        del cache["pages"][source_page_id]
    if cache_key_to_remove:
        del cache["sources"][cache_key_to_remove]
    cache["updated_at"] = utc_now_iso()
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        build_graph_data(kb_root, persist=True)
    except Exception as exc:
        logger.warning(f"graph rebuild after delete failed: {exc}")

    return {"success": True, "document_id": document_id}
```

Rename the original `delete_document` body to `_rag_delete_document`.

- [ ] **Step 5: Verify pass**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v -k "delete_wiki_document"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tokenmind/knowledge/service.py tests/test_knowledge_dual_mode.py
git commit -m "feat(knowledge): wiki delete_document removes source page + cache + rebuilds graph"
```

---

## Phase 7: 全量验证

### Task 25: 跑全 backend 测试 + lint + 起服务手测

**Files:** —

- [ ] **Step 1: 全量 pytest**

Run: `.venv/bin/pytest -q 2>&1 | tail -30`
Expected: all PASS, no regressions. If failures, fix root cause; do not silence.

- [ ] **Step 2: ruff**

Run: `.venv/bin/ruff check tokenmind/ 2>&1 | tail -20`
Expected: clean. Fix any new warnings introduced by this work.

- [ ] **Step 3: 起服务做端到端手测**

Stop any running server first (TaskStop the old `bqwt850wn` if still running). Then:

```bash
.venv/bin/tokenmind web --port 18888
```

In another shell, curl:

```bash
# Create a wiki KB
curl -s -X POST http://localhost:18888/api/knowledge \
  -H 'Content-Type: application/json' \
  -d '{"name":"smoke","description":"manual test","type":"wiki"}' | jq .

# Get its id, upload a file
KB_ID=$(curl -s http://localhost:18888/api/knowledge | jq -r '.items[] | select(.name=="smoke") | .id')
echo -e "# Hello\n\nThis is about [[TokenMind]]." > /tmp/smoke.md
curl -s -X POST "http://localhost:18888/api/knowledge/$KB_ID/documents" \
  -F 'files=@/tmp/smoke.md' | jq .

# Wait a couple seconds then read graph
sleep 3
curl -s "http://localhost:18888/api/knowledge/$KB_ID/graph" | jq .

# List pages
curl -s "http://localhost:18888/api/knowledge/$KB_ID/pages" | jq .

# Set active wiki kb on a session
SID="web:smoke"
curl -s -X PATCH "http://localhost:18888/api/sessions/$SID" \
  -H 'Content-Type: application/json' \
  -d "{\"active_wiki_kb_id\":\"$KB_ID\"}" | jq .
```

Expected: each step returns 200 and meaningful data. `pages` lists at least one source page. `graph` shows nodes.

- [ ] **Step 4: Verify in workspace**

```bash
ls ~/.tokenmind/workspace/knowledge/$KB_ID/raw/files
ls ~/.tokenmind/workspace/knowledge/$KB_ID/wiki/sources
cat ~/.tokenmind/workspace/knowledge/$KB_ID/graph-data.json | jq .
```

Expected: `raw/files/smoke.md` exists, `wiki/sources/*.md` has the compiled source page, graph has a "smoke" node (and possibly a "TokenMind" broken-link entry since no entity page yet).

- [ ] **Step 5: Final commit if any fixes**

If steps 1-4 found issues that were fixed inline, commit them now:

```bash
git add -p
git commit -m "fix: address issues found in dual-mode end-to-end verification"
```

---

## 后续 plan（不在本 plan 范围）

- **Frontend plan**: 创建对话框增加 type 单选；KB 列表卡片显示徽标；Wiki KB 详情页（页面列表 + Markdown 阅读器 + 图谱）；会话顶部 active Wiki KB 选择器
- **PUT /api/knowledge/{kb_id}/pages/{page_id}**: 允许人工编辑 Wiki 页面（spec §API 列出）。本 plan 暂不实现——LLM 编译路径已 "只追加不重写"，人工编辑通过直接改文件系统亦可。后续 plan 加正式 API。
- **Phase 8 of spec**: digest / lint / crystallize 三个高级工作流
- **Optional**: 给 Wiki 页面加 embedding 提升中文模糊召回（spec 风险表已记录）

