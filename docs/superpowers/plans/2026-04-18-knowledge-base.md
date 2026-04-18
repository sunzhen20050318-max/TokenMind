# TokenMind Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a first-class Knowledge Base workspace in TokenMind, plus explicit session-level knowledge linking in chat so users can manually ground answers in one or more selected knowledge bases.

**Architecture:** Add a lightweight knowledge domain to the backend with workspace-local metadata, file storage, chunk records, and session-to-knowledge links. Expose REST routes for overview/detail/document management and chat linkage, then add a dedicated frontend knowledge page plus a composer-level “链接知识库” selector that persists selected knowledge bases per session.

**Tech Stack:** FastAPI, Pydantic, existing SessionManager workspace storage, React 18, Zustand, TypeScript, Vite.

---

## File Structure

### Backend

- Create: `D:\project\sun-agent\sun_agent\knowledge\__init__.py`
- Create: `D:\project\sun-agent\sun_agent\knowledge\models.py`
- Create: `D:\project\sun-agent\sun_agent\knowledge\service.py`
- Create: `D:\project\sun-agent\sun_agent\knowledge\chunking.py`
- Create: `D:\project\sun-agent\sun_agent\server\routes\knowledge.py`
- Modify: `D:\project\sun-agent\sun_agent\server\routes\__init__.py`
- Modify: `D:\project\sun-agent\sun_agent\server\app.py`
- Modify: `D:\project\sun-agent\sun_agent\server\websocket\handler.py`
- Modify: `D:\project\sun-agent\sun_agent\agent\context.py`
- Modify: `D:\project\sun-agent\sun_agent\agent\loop.py`
- Test: `D:\project\sun-agent\tests\test_knowledge_service.py`
- Test: `D:\project\sun-agent\tests\test_knowledge_routes.py`
- Test: `D:\project\sun-agent\tests\test_chat_knowledge_links.py`

### Frontend

- Create: `D:\project\sun-agent\frontend\src\pages\Knowledge.tsx`
- Create: `D:\project\sun-agent\frontend\src\pages\knowledge.css`
- Create: `D:\project\sun-agent\frontend\src\types\knowledge.ts`
- Modify: `D:\project\sun-agent\frontend\src\components\Layout\Sidebar.tsx`
- Modify: `D:\project\sun-agent\frontend\src\components\Layout\sidebar.css`
- Modify: `D:\project\sun-agent\frontend\src\App.tsx`
- Modify: `D:\project\sun-agent\frontend\src\components\Chat\InputArea.tsx`
- Modify: `D:\project\sun-agent\frontend\src\components\Chat\inputArea.css`
- Modify: `D:\project\sun-agent\frontend\src\services\api.ts`
- Modify: `D:\project\sun-agent\frontend\src\stores\chatStore.ts`

---

### Task 1: Create the backend knowledge domain and local storage model

**Files:**
- Create: `D:\project\sun-agent\sun_agent\knowledge\__init__.py`
- Create: `D:\project\sun-agent\sun_agent\knowledge\models.py`
- Create: `D:\project\sun-agent\sun_agent\knowledge\service.py`
- Create: `D:\project\sun-agent\sun_agent\knowledge\chunking.py`
- Test: `D:\project\sun-agent\tests\test_knowledge_service.py`

- [ ] **Step 1: Write the failing backend service tests**

```python
from pathlib import Path

from sun_agent.knowledge.service import KnowledgeService


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
    assert len(service.list_documents(kb.id)) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
pytest D:\project\sun-agent\tests\test_knowledge_service.py -q
```

Expected: FAIL with import errors because `sun_agent.knowledge` does not exist yet.

- [ ] **Step 3: Add the knowledge models and service**

Create `D:\project\sun-agent\sun_agent\knowledge\models.py`:

```python
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class KnowledgeBaseRecord(BaseModel):
    id: str
    name: str
    description: str = ""
    status: str = "ready"
    document_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class KnowledgeDocumentRecord(BaseModel):
    id: str
    knowledge_base_id: str
    name: str
    path: str
    file_type: str
    size: int
    status: str = "ready"
    chunk_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class SessionKnowledgeLinks(BaseModel):
    session_id: str
    knowledge_base_ids: list[str] = Field(default_factory=list)
```

Create `D:\project\sun-agent\sun_agent\knowledge\chunking.py`:

```python
from __future__ import annotations


def simple_chunks(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    clean = text.strip()
    if not clean:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + size)
        chunks.append(clean[start:end])
        if end >= len(clean):
            break
        start = max(end - overlap, start + 1)
    return chunks
```

Create `D:\project\sun-agent\sun_agent\knowledge\service.py`:

```python
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from sun_agent.knowledge.chunking import simple_chunks
from sun_agent.knowledge.models import KnowledgeBaseRecord, KnowledgeDocumentRecord


class KnowledgeService:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.root = workspace / "knowledge"
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.root / "metadata.json"
        self._state = self._load()

    def _load(self) -> dict:
        if self.metadata_file.exists():
            return json.loads(self.metadata_file.read_text(encoding="utf-8"))
        return {"knowledge_bases": [], "documents": [], "session_links": {}}

    def _save(self) -> None:
        self.metadata_file.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_knowledge_base(self, name: str, description: str) -> KnowledgeBaseRecord:
        record = KnowledgeBaseRecord(id=f"kb_{uuid.uuid4().hex[:10]}", name=name, description=description)
        self._state["knowledge_bases"].append(record.model_dump())
        self._save()
        return record

    def list_knowledge_bases(self) -> list[KnowledgeBaseRecord]:
        return [KnowledgeBaseRecord(**item) for item in self._state["knowledge_bases"]]

    def set_session_links(self, session_id: str, knowledge_base_ids: list[str]) -> None:
        self._state["session_links"][session_id] = knowledge_base_ids
        self._save()

    def get_session_links(self, session_id: str) -> list[str]:
        return list(self._state["session_links"].get(session_id, []))

    def add_document(self, knowledge_base_id: str, source: Path, original_name: str) -> KnowledgeDocumentRecord:
        target_dir = self.root / knowledge_base_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / original_name
        shutil.copy2(source, target)
        text = target.read_text(encoding="utf-8", errors="ignore")
        record = KnowledgeDocumentRecord(
            id=f"doc_{uuid.uuid4().hex[:10]}",
            knowledge_base_id=knowledge_base_id,
            name=original_name,
            path=str(target),
            file_type=target.suffix.lower().lstrip("."),
            size=target.stat().st_size,
            chunk_count=len(simple_chunks(text)),
        )
        self._state["documents"].append(record.model_dump())
        self._save()
        return record

    def list_documents(self, knowledge_base_id: str) -> list[KnowledgeDocumentRecord]:
        return [
            KnowledgeDocumentRecord(**item)
            for item in self._state["documents"]
            if item["knowledge_base_id"] == knowledge_base_id
        ]
```

Create `D:\project\sun-agent\sun_agent\knowledge\__init__.py`:

```python
from sun_agent.knowledge.service import KnowledgeService

__all__ = ["KnowledgeService"]
```

- [ ] **Step 4: Run the backend service tests to verify they pass**

Run:

```powershell
pytest D:\project\sun-agent\tests\test_knowledge_service.py -q
```

Expected: PASS with 3 passing tests.

- [ ] **Step 5: Commit**

```powershell
git add D:\project\sun-agent\sun_agent\knowledge D:\project\sun-agent\tests\test_knowledge_service.py
git commit -m "feat: add knowledge service foundation"
```

### Task 2: Add knowledge routes and expose them from the FastAPI app

**Files:**
- Create: `D:\project\sun-agent\sun_agent\server\routes\knowledge.py`
- Modify: `D:\project\sun-agent\sun_agent\server\routes\__init__.py`
- Modify: `D:\project\sun-agent\sun_agent\server\app.py`
- Test: `D:\project\sun-agent\tests\test_knowledge_routes.py`

- [ ] **Step 1: Write failing route tests**

```python
import importlib
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_route_wrapper_returns_overview_payload() -> None:
    route_module = importlib.import_module("sun_agent.server.routes.knowledge")
    service = SimpleNamespace(get_knowledge_overview=lambda: {"items": [{"id": "kb_1", "name": "测试库"}]})

    response = await route_module.list_knowledge_bases(service=service)

    assert response["items"][0]["name"] == "测试库"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
pytest D:\project\sun-agent\tests\test_knowledge_routes.py -q
```

Expected: FAIL because `sun_agent.server.routes.knowledge` does not exist.

- [ ] **Step 3: Implement the routes and wire them into the app**

Create `D:\project\sun-agent\sun_agent\server\routes\knowledge.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from sun_agent.server.app import ChatService
from sun_agent.server.dependencies import get_chat_service

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class CreateKnowledgeBasePayload(BaseModel):
    name: str
    description: str = ""


@router.get("")
async def list_knowledge_bases(service: ChatService = Depends(get_chat_service)) -> dict:
    return service.get_knowledge_overview()


@router.post("")
async def create_knowledge_base(payload: CreateKnowledgeBasePayload, service: ChatService = Depends(get_chat_service)) -> dict:
    return service.create_knowledge_base(payload.name, payload.description)


@router.get("/{knowledge_base_id}")
async def get_knowledge_base_detail(knowledge_base_id: str, service: ChatService = Depends(get_chat_service)) -> dict:
    return service.get_knowledge_base_detail(knowledge_base_id)
```

Modify `D:\project\sun-agent\sun_agent\server\routes\__init__.py`:

```python
from sun_agent.server.routes.knowledge import router as knowledge_router

__all__ = [
    "chat_router",
    "config_router",
    "cron_router",
    "knowledge_router",
    "memory_router",
    "sessions_router",
    "status_router",
    "storage_router",
]
```

Modify `D:\project\sun-agent\sun_agent\server\app.py`:

```python
from sun_agent.knowledge import KnowledgeService
from sun_agent.server.routes import knowledge_router
```

```python
self.knowledge = KnowledgeService(session_manager.workspace)

def get_knowledge_overview(self) -> dict[str, Any]:
    return {"items": [item.model_dump() for item in self.knowledge.list_knowledge_bases()]}

def create_knowledge_base(self, name: str, description: str) -> dict[str, Any]:
    return self.knowledge.create_knowledge_base(name, description).model_dump()

def get_knowledge_base_detail(self, knowledge_base_id: str) -> dict[str, Any]:
    knowledge = next(item for item in self.knowledge.list_knowledge_bases() if item.id == knowledge_base_id)
    return {
        "knowledge_base": knowledge.model_dump(),
        "documents": [doc.model_dump() for doc in self.knowledge.list_documents(knowledge_base_id)],
    }
```

Also register the router:

```python
app.include_router(knowledge_router)
```

- [ ] **Step 4: Run the route tests**

Run:

```powershell
pytest D:\project\sun-agent\tests\test_knowledge_routes.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add D:\project\sun-agent\sun_agent\server\routes\knowledge.py D:\project\sun-agent\sun_agent\server\routes\__init__.py D:\project\sun-agent\sun_agent\server\app.py D:\project\sun-agent\tests\test_knowledge_routes.py
git commit -m "feat: add knowledge API routes"
```

### Task 3: Build the dedicated Knowledge page and main-shell entry

**Files:**
- Create: `D:\project\sun-agent\frontend\src\pages\Knowledge.tsx`
- Create: `D:\project\sun-agent\frontend\src\pages\knowledge.css`
- Create: `D:\project\sun-agent\frontend\src\types\knowledge.ts`
- Modify: `D:\project\sun-agent\frontend\src\services\api.ts`
- Modify: `D:\project\sun-agent\frontend\src\components\Layout\Sidebar.tsx`
- Modify: `D:\project\sun-agent\frontend\src\components\Layout\sidebar.css`
- Modify: `D:\project\sun-agent\frontend\src\App.tsx`

- [ ] **Step 1: Add the frontend data types**

```ts
export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  status: string;
  document_count: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeDocument {
  id: string;
  knowledge_base_id: string;
  name: string;
  path: string;
  file_type: string;
  size: number;
  status: string;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeOverviewResponse {
  items: KnowledgeBase[];
}

export interface KnowledgeDetailResponse {
  knowledge_base: KnowledgeBase;
  documents: KnowledgeDocument[];
}
```

- [ ] **Step 2: Extend the frontend API client**

Modify `D:\project\sun-agent\frontend\src\services\api.ts`:

```ts
import type {
  KnowledgeDetailResponse,
  KnowledgeOverviewResponse,
} from '../types/knowledge';
```

```ts
async getKnowledgeOverview(): Promise<KnowledgeOverviewResponse> {
  const res = await fetch(`${API_BASE}/knowledge`);
  if (!res.ok) {
    throw new Error(`Failed to load knowledge overview: ${res.statusText}`);
  }
  return res.json();
},

async getKnowledgeDetail(id: string): Promise<KnowledgeDetailResponse> {
  const res = await fetch(`${API_BASE}/knowledge/${encodeURIComponent(id)}`);
  if (!res.ok) {
    throw new Error(`Failed to load knowledge base: ${res.statusText}`);
  }
  return res.json();
},

async createKnowledgeBase(payload: { name: string; description: string }): Promise<void> {
  const res = await fetch(`${API_BASE}/knowledge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Failed to create knowledge base: ${res.statusText}`);
  }
},
```

- [ ] **Step 3: Add the page shell and sidebar entry**

Create `D:\project\sun-agent\frontend\src\pages\Knowledge.tsx`:

```tsx
import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { KnowledgeBase, KnowledgeDetailResponse } from '../types/knowledge';
import './knowledge.css';

export const KnowledgePage: React.FC = () => {
  const [items, setItems] = useState<KnowledgeBase[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<KnowledgeDetailResponse | null>(null);

  useEffect(() => {
    void api.getKnowledgeOverview().then((payload) => setItems(payload.items));
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    void api.getKnowledgeDetail(selectedId).then(setDetail);
  }, [selectedId]);

  return (
    <section className="knowledge-page">
      {!selectedId ? (
        <div className="knowledge-page__overview">
          <header className="knowledge-page__header">
            <div>
              <h1>知识库</h1>
              <p>创建和管理可在聊天中手动链接的资料库。</p>
            </div>
          </header>
          <div className="knowledge-page__grid">
            {items.map((item) => (
              <button key={item.id} type="button" className="knowledge-card" onClick={() => setSelectedId(item.id)}>
                <strong>{item.name}</strong>
                <span>{item.description || '未填写描述'}</span>
                <small>{item.document_count} 份资料</small>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="knowledge-page__detail">
          <button type="button" className="knowledge-page__back" onClick={() => setSelectedId(null)}>
            返回全部知识库
          </button>
          <h1>{detail?.knowledge_base.name}</h1>
          <div className="knowledge-documents">
            {detail?.documents.map((doc) => (
              <div key={doc.id} className="knowledge-document">
                <strong>{doc.name}</strong>
                <span>{doc.file_type.toUpperCase()} · {doc.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};
```

Modify `D:\project\sun-agent\frontend\src\App.tsx`:

```tsx
const [mainView, setMainView] = useState<'chat' | 'knowledge'>('chat');
```

```tsx
<Sidebar
  collapsed={sidebarCollapsed}
  onToggleCollapse={() => setSidebarCollapsed((value) => !value)}
  mainView={mainView}
  onSelectMainView={setMainView}
/>
```

```tsx
{mainView === 'knowledge'
  ? <KnowledgePage />
  : currentSession
    ? <ChatWindow sessionId={currentSession} />
    : <div className="app-main__empty">点击“新建对话”开始新的会话</div>}
```

- [ ] **Step 4: Add page styling and shell integration**

Create `D:\project\sun-agent\frontend\src\pages\knowledge.css`:

```css
.knowledge-page {
  height: 100%;
  overflow: auto;
  padding: 34px 40px 56px;
}

.knowledge-page__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 28px;
}

.knowledge-page__header h1 {
  margin: 0;
  color: #f5f6f7;
  font-size: 34px;
}

.knowledge-page__header p {
  margin: 10px 0 0;
  color: #8d9098;
}

.knowledge-page__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 18px;
}

.knowledge-card {
  padding: 18px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.03);
  color: inherit;
  text-align: left;
}
```

- [ ] **Step 5: Run the frontend build**

Run:

```powershell
npm run build
```

Workdir:

```powershell
D:\project\sun-agent\frontend
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add D:\project\sun-agent\frontend\src\pages\Knowledge.tsx D:\project\sun-agent\frontend\src\pages\knowledge.css D:\project\sun-agent\frontend\src\types\knowledge.ts D:\project\sun-agent\frontend\src\services\api.ts D:\project\sun-agent\frontend\src\components\Layout\Sidebar.tsx D:\project\sun-agent\frontend\src\components\Layout\sidebar.css D:\project\sun-agent\frontend\src\App.tsx
git commit -m "feat: add knowledge workspace shell"
```

### Task 4: Add document upload/delete flows to a single knowledge base

**Files:**
- Modify: `D:\project\sun-agent\sun_agent\server\routes\knowledge.py`
- Modify: `D:\project\sun-agent\sun_agent\server\app.py`
- Modify: `D:\project\sun-agent\sun_agent\knowledge\service.py`
- Modify: `D:\project\sun-agent\frontend\src\services\api.ts`
- Modify: `D:\project\sun-agent\frontend\src\pages\Knowledge.tsx`
- Test: `D:\project\sun-agent\tests\test_knowledge_routes.py`

- [ ] **Step 1: Extend the backend tests to cover upload and delete**

```python
from pathlib import Path


def test_add_document_to_knowledge_base_exposes_it_in_detail(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("图片资料", "")
    source = tmp_path / "notes.md"
    source.write_text("# 标题\n内容", encoding="utf-8")

    service.add_document(kb.id, source, "notes.md")

    detail = service.get_knowledge_base_detail(kb.id)
    assert detail["documents"][0]["name"] == "notes.md"
```

- [ ] **Step 2: Run the tests to verify failure**

Run:

```powershell
pytest D:\project\sun-agent\tests\test_knowledge_routes.py -q
```

Expected: FAIL because upload/delete route helpers are not implemented.

- [ ] **Step 3: Add upload and delete API support**

Modify `D:\project\sun-agent\sun_agent\server\routes\knowledge.py`:

```python
from fastapi import File, UploadFile


@router.post("/{knowledge_base_id}/documents")
async def upload_knowledge_documents(
    knowledge_base_id: str,
    files: list[UploadFile] = File(...),
    service: ChatService = Depends(get_chat_service),
) -> dict:
    return await service.upload_knowledge_documents(knowledge_base_id, files)


@router.delete("/{knowledge_base_id}/documents/{document_id}")
async def delete_knowledge_document(
    knowledge_base_id: str,
    document_id: str,
    service: ChatService = Depends(get_chat_service),
) -> dict:
    return service.delete_knowledge_document(knowledge_base_id, document_id)
```

Modify `D:\project\sun-agent\sun_agent\server\app.py`:

```python
async def upload_knowledge_documents(self, knowledge_base_id: str, files: list[Any]) -> dict[str, Any]:
    uploaded = []
    for file in files:
        temp_dir = self.session_manager.workspace / "tmp-knowledge"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / safe_filename(file.filename or "upload.bin")
        temp_path.write_bytes(await file.read())
        uploaded.append(self.knowledge.add_document(knowledge_base_id, temp_path, file.filename or temp_path.name).model_dump())
    return {"documents": uploaded}

def delete_knowledge_document(self, knowledge_base_id: str, document_id: str) -> dict[str, Any]:
    self.knowledge.delete_document(knowledge_base_id, document_id)
    return {"success": True, "document_id": document_id}
```

Modify `D:\project\sun-agent\sun_agent\knowledge\service.py` to add `delete_document()`.

Modify `D:\project\sun-agent\frontend\src\services\api.ts`:

```ts
async uploadKnowledgeDocuments(id: string, files: File[]): Promise<void> {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  const res = await fetch(`${API_BASE}/knowledge/${encodeURIComponent(id)}/documents`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    throw new Error(`Failed to upload knowledge documents: ${res.statusText}`);
  }
},

async deleteKnowledgeDocument(knowledgeBaseId: string, documentId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/knowledge/${encodeURIComponent(knowledgeBaseId)}/documents/${encodeURIComponent(documentId)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error(`Failed to delete knowledge document: ${res.statusText}`);
  }
},
```

Modify `D:\project\sun-agent\frontend\src\pages\Knowledge.tsx` to add:

- upload button in detail header
- hidden file input
- delete button per document
- reload detail after mutation

- [ ] **Step 4: Run route tests and frontend build**

Run:

```powershell
pytest D:\project\sun-agent\tests\test_knowledge_routes.py -q
npm run build
```

Frontend workdir:

```powershell
D:\project\sun-agent\frontend
```

Expected: both pass.

- [ ] **Step 5: Commit**

```powershell
git add D:\project\sun-agent\sun_agent\server\routes\knowledge.py D:\project\sun-agent\sun_agent\server\app.py D:\project\sun-agent\sun_agent\knowledge\service.py D:\project\sun-agent\frontend\src\services\api.ts D:\project\sun-agent\frontend\src\pages\Knowledge.tsx D:\project\sun-agent\tests\test_knowledge_routes.py
git commit -m "feat: manage knowledge documents"
```

### Task 5: Add session-level “链接知识库” controls to the composer

**Files:**
- Modify: `D:\project\sun-agent\sun_agent\knowledge\service.py`
- Modify: `D:\project\sun-agent\sun_agent\server\routes\knowledge.py`
- Modify: `D:\project\sun-agent\frontend\src\services\api.ts`
- Modify: `D:\project\sun-agent\frontend\src\stores\chatStore.ts`
- Modify: `D:\project\sun-agent\frontend\src\components\Chat\InputArea.tsx`
- Modify: `D:\project\sun-agent\frontend\src\components\Chat\inputArea.css`
- Test: `D:\project\sun-agent\tests\test_chat_knowledge_links.py`

- [ ] **Step 1: Write the failing session-link tests**

```python
from pathlib import Path

from sun_agent.knowledge.service import KnowledgeService


def test_session_can_link_multiple_knowledge_bases(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path)
    kb_a = service.create_knowledge_base("产品", "")
    kb_b = service.create_knowledge_base("合同", "")

    service.set_session_links("web:test", [kb_a.id, kb_b.id])

    assert service.get_session_links("web:test") == [kb_a.id, kb_b.id]
```

- [ ] **Step 2: Run the tests to verify failure**

Run:

```powershell
pytest D:\project\sun-agent\tests\test_chat_knowledge_links.py -q
```

Expected: FAIL because route wrappers and frontend state are not connected.

- [ ] **Step 3: Add API endpoints for session links**

Modify `D:\project\sun-agent\sun_agent\server\routes\knowledge.py`:

```python
class SessionKnowledgePayload(BaseModel):
    session_id: str
    knowledge_base_ids: list[str]


@router.get("/links/{session_id}")
async def get_session_knowledge_links(session_id: str, service: ChatService = Depends(get_chat_service)) -> dict:
    return {"session_id": session_id, "knowledge_base_ids": service.get_session_links(session_id)}


@router.put("/links/{session_id}")
async def update_session_knowledge_links(
    session_id: str,
    payload: SessionKnowledgePayload,
    service: ChatService = Depends(get_chat_service),
) -> dict:
    service.set_session_links(session_id, payload.knowledge_base_ids)
    return {"session_id": session_id, "knowledge_base_ids": payload.knowledge_base_ids}
```

Modify `D:\project\sun-agent\sun_agent\server\app.py`:

```python
def get_session_knowledge_links(self, session_id: str) -> list[str]:
    return self.knowledge.get_session_links(session_id)

def set_session_knowledge_links(self, session_id: str, knowledge_base_ids: list[str]) -> None:
    self.knowledge.set_session_links(session_id, knowledge_base_ids)
```

- [ ] **Step 4: Add the composer UI and state**

Modify `D:\project\sun-agent\frontend\src\stores\chatStore.ts`:

```ts
linkedKnowledgeBaseIds: string[];
setLinkedKnowledgeBases: (knowledgeBaseIds: string[]) => Promise<void>;
loadLinkedKnowledgeBases: (sessionId: string) => Promise<void>;
```

```ts
linkedKnowledgeBaseIds: [],

setLinkedKnowledgeBases: async (knowledgeBaseIds) => {
  const sessionId = get().currentSession;
  if (!sessionId) return;
  await api.updateSessionKnowledgeLinks(sessionId, knowledgeBaseIds);
  set({ linkedKnowledgeBaseIds: knowledgeBaseIds });
},

loadLinkedKnowledgeBases: async (sessionId) => {
  const payload = await api.getSessionKnowledgeLinks(sessionId);
  set({ linkedKnowledgeBaseIds: payload.knowledge_base_ids });
},
```

Modify `D:\project\sun-agent\frontend\src\components\Chat\InputArea.tsx` to add:

- a `链接知识库` trigger
- a popover with multi-select rows
- removable linked tags

Core structure:

```tsx
<div className="composer__knowledge">
  <button type="button" className="composer__knowledge-trigger">链接知识库</button>
  <div className="composer__knowledge-tags">
    {linkedKnowledgeBases.map((item) => (
      <button key={item.id} type="button" className="composer__knowledge-tag">
        <span>{item.name}</span>
        <span>×</span>
      </button>
    ))}
  </div>
</div>
```

- [ ] **Step 5: Run the tests and build**

Run:

```powershell
pytest D:\project\sun-agent\tests\test_chat_knowledge_links.py -q
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add D:\project\sun-agent\sun_agent\server\routes\knowledge.py D:\project\sun-agent\sun_agent\server\app.py D:\project\sun-agent\sun_agent\knowledge\service.py D:\project\sun-agent\frontend\src\services\api.ts D:\project\sun-agent\frontend\src\stores\chatStore.ts D:\project\sun-agent\frontend\src\components\Chat\InputArea.tsx D:\project\sun-agent\frontend\src\components\Chat\inputArea.css D:\project\sun-agent\tests\test_chat_knowledge_links.py
git commit -m "feat: add session knowledge linking"
```

### Task 6: Inject linked knowledge into chat context

**Files:**
- Modify: `D:\project\sun-agent\sun_agent\knowledge\service.py`
- Modify: `D:\project\sun-agent\sun_agent\server\websocket\handler.py`
- Modify: `D:\project\sun-agent\sun_agent\agent\context.py`
- Modify: `D:\project\sun-agent\sun_agent\agent\loop.py`
- Test: `D:\project\sun-agent\tests\test_chat_knowledge_links.py`

- [ ] **Step 1: Add a failing retrieval integration test**

```python
from pathlib import Path

from sun_agent.knowledge.service import KnowledgeService


def test_retrieve_for_session_uses_only_linked_knowledge_bases(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path)
    kb = service.create_knowledge_base("售前", "")
    source = tmp_path / "faq.txt"
    source.write_text("TokenMind 支持多知识库链接。", encoding="utf-8")
    service.add_document(kb.id, source, "faq.txt")
    service.set_session_links("web:test", [kb.id])

    results = service.retrieve_for_session("web:test", "支持什么链接")

    assert results
    assert "多知识库链接" in results[0]["content"]
```

- [ ] **Step 2: Run the integration test to verify failure**

Run:

```powershell
pytest D:\project\sun-agent\tests\test_chat_knowledge_links.py -q
```

Expected: FAIL because retrieval is not implemented yet.

- [ ] **Step 3: Implement minimal retrieval and prompt injection**

Modify `D:\project\sun-agent\sun_agent\knowledge\service.py`:

```python
def retrieve_for_session(self, session_id: str, query: str, top_k: int = 4) -> list[dict]:
    linked = set(self.get_session_links(session_id))
    if not linked:
        return []
    query_lower = query.lower()
    results: list[dict] = []
    for document in self._state["documents"]:
        if document["knowledge_base_id"] not in linked:
            continue
        path = Path(document["path"])
        text = path.read_text(encoding="utf-8", errors="ignore")
        for chunk in simple_chunks(text):
            score = sum(token in chunk.lower() for token in query_lower.split())
            if score:
                results.append({"document_name": document["name"], "content": chunk, "score": score})
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:top_k]
```

Modify `D:\project\sun-agent\sun_agent\server\websocket\handler.py`:

```python
metadata["knowledge_base_ids"] = chat_service.get_session_knowledge_links(session_id)
```

Modify `D:\project\sun-agent\sun_agent\agent\context.py`:

```python
knowledge_chunks = runtime_context.get("knowledge_chunks", [])
if knowledge_chunks:
    rendered_chunks = "\n\n".join(
        f"[{item['document_name']}]\n{item['content']}" for item in knowledge_chunks
    )
    user_text = f"[Linked Knowledge]\n{rendered_chunks}\n\n[User Request]\n{user_text}"
```

Modify `D:\project\sun-agent\sun_agent\agent\loop.py`:

```python
knowledge_chunks = []
session_id = getattr(message, "session_id", None)
user_text = message.content if isinstance(message.content, str) else ""
if session_id and user_text:
    knowledge_chunks = self.chat_service.knowledge.retrieve_for_session(session_id, user_text)
runtime_context["knowledge_chunks"] = knowledge_chunks
```

- [ ] **Step 4: Run the retrieval test and core regression tests**

Run:

```powershell
pytest D:\project\sun-agent\tests\test_chat_knowledge_links.py -q
pytest D:\project\sun-agent\tests\test_memory_routes.py D:\project\sun-agent\tests\test_config_routes.py -q
```

Expected: PASS.

- [ ] **Step 5: Final verification and commit**

Run:

```powershell
cd D:\project\sun-agent\frontend
npm run build
cd D:\project\sun-agent
python -m compileall D:\project\sun-agent\sun_agent
```

Expected:

- frontend build passes
- compileall passes

Commit:

```powershell
git add D:\project\sun-agent\sun_agent\knowledge D:\project\sun-agent\sun_agent\server\websocket\handler.py D:\project\sun-agent\sun_agent\agent\context.py D:\project\sun-agent\sun_agent\agent\loop.py D:\project\sun-agent\tests\test_chat_knowledge_links.py
git commit -m "feat: ground chat with linked knowledge bases"
```

## Self-Review

### Spec coverage

- standalone sidebar entry: covered in Task 3
- overview-first knowledge page: covered in Task 3
- single knowledge base detail with materials list: covered in Tasks 3 and 4
- mixed-format materials in one knowledge base: covered in Task 4 service and API shape
- manual composer linking: covered in Task 5
- multiple linked knowledge bases: covered in Task 5 and Task 6
- only user-selected knowledge applies: covered in Task 5 and Task 6

### Placeholder scan

- no `TBD` / `TODO`
- all tasks include concrete file paths, commands, and code skeletons

### Type consistency

- `KnowledgeService`
- `KnowledgeBaseRecord`
- `KnowledgeDocumentRecord`
- `get_session_links` / `set_session_links`
- `retrieve_for_session`

These names are used consistently across later tasks.
