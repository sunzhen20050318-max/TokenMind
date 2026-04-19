# Memory Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone Memory Center modal that lets users inspect and manage long-term memory, current session context, recent archive history, and a lightweight memory settings summary.

**Architecture:** Extend the existing FastAPI web surface with a dedicated memory router that reads and updates `workspace/memory/MEMORY.md`, derives current-context previews from the active session, and exposes archive previews from `HISTORY.md`. Mirror the established Settings / Tasks / Storage frontend pattern with a new sidebar action, API client bindings, typed responses, and a dark monochrome modal whose primary surface is an editable long-term memory document.

**Tech Stack:** FastAPI, Pydantic, Python session/memory services, React, TypeScript, Zustand, existing modal CSS pattern, pytest, Vite build.

---

## File Structure

- Create: `D:\project\sun-agent\sun_agent\server\routes\memory.py`
  - Dedicated Memory Center API router.
- Modify: `D:\project\sun-agent\sun_agent\server\routes\__init__.py`
  - Export the new router.
- Modify: `D:\project\sun-agent\sun_agent\server\app.py`
  - Register the new router and expose ChatService helpers for memory reads/writes.
- Modify: `D:\project\sun-agent\sun_agent\agent\memory.py`
  - Add small read helpers for archive previews and metadata-friendly access.
- Create: `D:\project\sun-agent\tests\test_memory_routes.py`
  - API tests for empty states, saves, current-context previews, and archive search.
- Create: `D:\project\sun-agent\frontend\src\types\memory.ts`
  - Memory Center response and payload types.
- Modify: `D:\project\sun-agent\frontend\src\services\api.ts`
  - Add Memory Center endpoints.
- Create: `D:\project\sun-agent\frontend\src\pages\Memory.tsx`
  - Standalone Memory Center modal.
- Create: `D:\project\sun-agent\frontend\src\pages\memory.css`
  - Dedicated styles for the modal.
- Modify: `D:\project\sun-agent\frontend\src\components\Layout\Sidebar.tsx`
  - Add the new sidebar action and modal wiring.
- Optional modify if needed: `D:\project\sun-agent\frontend\src\stores\chatStore.ts`
  - Reuse current session metadata cleanly for the new modal.

## Task 1: Add failing backend route tests

**Files:**
- Create: `D:\project\sun-agent\tests\test_memory_routes.py`
- Check patterns in: `D:\project\sun-agent\tests\test_storage_routes.py`
- Check patterns in: `D:\project\sun-agent\tests\test_config_routes.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

from fastapi.testclient import TestClient


def test_memory_overview_returns_empty_states_without_session(client: TestClient, workspace: Path):
    response = client.get("/api/memory")

    assert response.status_code == 200
    payload = response.json()
    assert payload["long_term"]["content"] == ""
    assert payload["current_context"]["session_id"] is None
    assert payload["current_context"]["items"] == []
    assert payload["archive"]["items"] == []


def test_memory_overview_returns_current_context_for_active_session(
    client: TestClient,
    chat_service,
):
    session = chat_service.session_manager.get_or_create("web:test-memory")
    session.add_message("user", "第一条消息")
    session.add_message("assistant", "第一条回复")
    chat_service.session_manager.save(session)

    response = client.get("/api/memory", params={"session_id": "web:test-memory"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_context"]["session_id"] == "web:test-memory"
    assert payload["current_context"]["items"][0]["role"] == "user"


def test_updating_long_term_memory_persists_content(client: TestClient, workspace: Path):
    response = client.put(
        "/api/memory/long-term",
        json={"content": "# 偏好\n- 喜欢简洁回答"},
    )

    assert response.status_code == 200
    assert (workspace / "memory" / "MEMORY.md").read_text(encoding="utf-8") == "# 偏好\n- 喜欢简洁回答"


def test_memory_overview_filters_archive_search(client: TestClient, workspace: Path):
    history_file = workspace / "memory" / "HISTORY.md"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text(
        "[2026-04-14 09:00] 讨论了上传策略\n\n[2026-04-14 10:00] 讨论了定时任务\n",
        encoding="utf-8",
    )

    response = client.get("/api/memory", params={"archive_query": "上传"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["archive"]["items"]) == 1
    assert "上传策略" in payload["archive"]["items"][0]["content"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest D:\project\sun-agent\tests\test_memory_routes.py -q`
Expected: FAIL with `404` for `/api/memory` or missing helper methods.

## Task 2: Implement backend memory helpers and routes

**Files:**
- Modify: `D:\project\sun-agent\sun_agent\agent\memory.py`
- Modify: `D:\project\sun-agent\sun_agent\server\app.py`
- Create: `D:\project\sun-agent\sun_agent\server\routes\memory.py`
- Modify: `D:\project\sun-agent\sun_agent\server\routes\__init__.py`

- [ ] **Step 1: Add archive/current-memory helper methods**

```python
class MemoryStore:
    ...
    def read_archive(self) -> str:
        if self.history_file.exists():
            return self.history_file.read_text(encoding="utf-8")
        return ""


def split_history_entries(content: str) -> list[str]:
    return [chunk.strip() for chunk in content.split("\n\n") if chunk.strip()]
```

- [ ] **Step 2: Add ChatService helpers for Memory Center payloads**

```python
class ChatService:
    ...
    def get_memory_overview(self, session_id: str | None = None, archive_query: str | None = None) -> dict[str, Any]:
        memory_store = getattr(self.agent_loop, "memory_consolidator", None)
        store = memory_store.store if memory_store else None
        long_term = store.read_long_term() if store else ""
        archive_text = store.read_archive() if store else ""
        archive_items = self._build_archive_items(archive_text, archive_query)
        current_context = self._build_current_context(session_id)
        return {
            "long_term": {...},
            "current_context": {...},
            "archive": {...},
            "settings": {...},
        }

    def update_long_term_memory(self, content: str) -> dict[str, Any]:
        ...
```

- [ ] **Step 3: Add the new router**

```python
router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("")
async def get_memory(session_id: str | None = None, archive_query: str | None = None):
    return get_chat_service().get_memory_overview(session_id=session_id, archive_query=archive_query)


@router.put("/long-term")
async def update_long_term(payload: UpdateLongTermMemoryRequest):
    return get_chat_service().update_long_term_memory(payload.content)
```

- [ ] **Step 4: Register the router**

```python
from .memory import router as memory_router
...
app.include_router(memory_router)
```

- [ ] **Step 5: Run backend tests**

Run: `pytest D:\project\sun-agent\tests\test_memory_routes.py -q`
Expected: PASS

## Task 3: Add typed frontend API bindings

**Files:**
- Create: `D:\project\sun-agent\frontend\src\types\memory.ts`
- Modify: `D:\project\sun-agent\frontend\src\services\api.ts`

- [ ] **Step 1: Add memory response types**

```ts
export interface MemoryContextItem {
  role: string;
  content: string;
  timestamp?: string;
}

export interface MemoryArchiveItem {
  id: string;
  content: string;
  timestamp?: string;
}

export interface MemoryOverviewResponse {
  long_term: {
    content: string;
    updated_at: string | null;
    character_count: number;
    editable: boolean;
  };
  current_context: {
    session_id: string | null;
    session_label: string | null;
    items: MemoryContextItem[];
  };
  archive: {
    query: string;
    total: number;
    items: MemoryArchiveItem[];
  };
  settings: {
    auto_consolidation: boolean;
    template_enabled: boolean;
    editable_long_term: boolean;
    summary: string;
  };
}
```

- [ ] **Step 2: Add API client methods**

```ts
async getMemoryOverview(sessionId?: string, archiveQuery?: string): Promise<MemoryOverviewResponse> {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);
  if (archiveQuery) params.set('archive_query', archiveQuery);
  const suffix = params.toString() ? `?${params.toString()}` : '';
  const res = await fetch(`${API_BASE}/memory${suffix}`);
  ...
}

async updateLongTermMemory(content: string): Promise<MemoryOverviewResponse['long_term']> {
  const res = await fetch(`${API_BASE}/memory/long-term`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  ...
}
```

- [ ] **Step 3: Run frontend type/build verification**

Run: `npm run build`
Expected: FAIL only if the new modal does not exist yet; type definitions should be accepted.

## Task 4: Build the Memory Center modal

**Files:**
- Create: `D:\project\sun-agent\frontend\src\pages\Memory.tsx`
- Create: `D:\project\sun-agent\frontend\src\pages\memory.css`
- Modify: `D:\project\sun-agent\frontend\src\components\Layout\Sidebar.tsx`

- [ ] **Step 1: Create the modal shell and sidebar entry**

```tsx
const [showMemory, setShowMemory] = useState(false);
...
<button onClick={() => setShowMemory(true)}>记忆中心</button>
...
{showMemory ? <MemoryModal onClose={() => setShowMemory(false)} currentSessionId={currentSession} /> : null}
```

- [ ] **Step 2: Build the Memory modal state and data loading**

```tsx
export const MemoryModal: React.FC<MemoryModalProps> = ({ onClose, currentSessionId }) => {
  const [section, setSection] = useState<MemorySection>('long-term');
  const [overview, setOverview] = useState<MemoryOverviewResponse | null>(null);
  const [draft, setDraft] = useState('');
  const [archiveQuery, setArchiveQuery] = useState('');
  ...
}
```

- [ ] **Step 3: Implement the long-term memory editor**

```tsx
<section className="memory-panel">
  <div className="memory-panel__head">
    <h3>长期记忆</h3>
    <button disabled={!dirty || saving} onClick={() => void handleSave()}>
      {saving ? '保存中' : '保存'}
    </button>
  </div>
  <textarea value={draft} onChange={(event) => setDraft(event.target.value)} />
</section>
```

- [ ] **Step 4: Implement current-context and archive views**

```tsx
{section === 'current-context' ? (
  overview?.current_context.items.length ? (
    overview.current_context.items.map((item) => <article key=...>{item.content}</article>)
  ) : (
    <div className="memory-empty">还没有活动会话。开始一段对话后，这里会显示当前参与推理的上下文内容。</div>
  )
) : null}
```

- [ ] **Step 5: Implement the memory settings summary**

```tsx
<dl className="memory-facts">
  <div><dt>自动归档</dt><dd>{overview?.settings.auto_consolidation ? '已启用' : '未启用'}</dd></div>
  <div><dt>模板状态</dt><dd>{overview?.settings.template_enabled ? '已启用' : '默认模板'}</dd></div>
  <div><dt>长期记忆可编辑</dt><dd>{overview?.settings.editable_long_term ? '是' : '否'}</dd></div>
</dl>
```

- [ ] **Step 6: Style the modal to match the existing monochrome system**

```css
.memory-overlay { ... }
.memory-modal { ... }
.memory-nav { ... }
.memory-editor { ... }
.memory-empty { ... }
```

- [ ] **Step 7: Run frontend build**

Run: `npm run build`
Expected: PASS

## Task 5: Verify the full flow and polish

**Files:**
- Modify as needed based on test/build feedback:
  - `D:\project\sun-agent\sun_agent\server\routes\memory.py`
  - `D:\project\sun-agent\frontend\src\pages\Memory.tsx`
  - `D:\project\sun-agent\frontend\src\pages\memory.css`
  - `D:\project\sun-agent\frontend\src\components\Layout\Sidebar.tsx`

- [ ] **Step 1: Run targeted backend tests**

Run: `pytest D:\project\sun-agent\tests\test_memory_routes.py D:\project\sun-agent\tests\test_memory_consolidation_types.py -q`
Expected: PASS

- [ ] **Step 2: Run full Python verification without optional Matrix dependency**

Run: `pytest -q --ignore=D:\project\sun-agent\tests\test_matrix_channel.py`
Expected: PASS

- [ ] **Step 3: Run compile verification**

Run: `python -m compileall D:\project\sun-agent\sun_agent D:\project\sun-agent\tests`
Expected: PASS

- [ ] **Step 4: Run frontend production build**

Run: `npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add D:/project/sun-agent/sun_agent/agent/memory.py D:/project/sun-agent/sun_agent/server/app.py D:/project/sun-agent/sun_agent/server/routes/__init__.py D:/project/sun-agent/sun_agent/server/routes/memory.py D:/project/sun-agent/tests/test_memory_routes.py D:/project/sun-agent/frontend/src/types/memory.ts D:/project/sun-agent/frontend/src/services/api.ts D:/project/sun-agent/frontend/src/pages/Memory.tsx D:/project/sun-agent/frontend/src/pages/memory.css D:/project/sun-agent/frontend/src/components/Layout/Sidebar.tsx
git commit -m "feat: add memory center"
```

## Self-Review

- Spec coverage: this plan covers the standalone sidebar entry, content-first modal layout, editable long-term memory, read-only current context, searchable archive preview, lightweight settings summary, and the no-active-session empty state.
- Placeholder scan: no `TODO`, `TBD`, or “similar to above” steps remain; each task names exact files and concrete commands.
- Type consistency: backend payload names (`long_term`, `current_context`, `archive`, `settings`) match the frontend types and API bindings defined in later tasks.
