# TokenMind Project Workspaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ChatGPT-style project workspaces so users can create projects, enter a project home page, keep project chats out of the normal recent list, and move existing normal chats into a project.

**Architecture:** Add a dedicated backend project domain with its own workspace-local metadata store and keep project membership as a thin `project_id` field inside session metadata. Extend `ChatService` and REST routes to expose project CRUD, project-scoped chat creation, and session-linking flows, then add frontend project-aware shell state so the sidebar shows only project names while the main area renders a project home page with that project's conversations.

**Tech Stack:** FastAPI, Pydantic, existing JSON/JSONL workspace persistence, React 18, Zustand, TypeScript, Vite.

---

## File Structure

### Backend

- Create: `tokenmind/projects/__init__.py`
- Create: `tokenmind/projects/models.py`
- Create: `tokenmind/projects/store.py`
- Create: `tokenmind/server/routes/projects.py`
- Modify: `tokenmind/server/routes/__init__.py`
- Modify: `tokenmind/server/app.py`
- Modify: `tokenmind/server/routes/sessions.py`
- Modify: `tokenmind/session/manager.py`
- Test: `tests/test_project_store.py`
- Test: `tests/test_project_routes.py`
- Test: `tests/test_project_chat_service.py`

### Frontend

- Create: `frontend/src/pages/ProjectHome.tsx`
- Create: `frontend/src/components/Projects/CreateProjectModal.tsx`
- Create: `frontend/src/components/Projects/MoveSessionToProjectModal.tsx`
- Create: `frontend/src/components/Projects/projects.css`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/stores/chatStore.ts`
- Modify: `frontend/src/hooks/useSessions.ts`
- Modify: `frontend/src/components/Layout/Sidebar.tsx`
- Modify: `frontend/src/components/Layout/sidebar.css`
- Modify: `frontend/src/App.tsx`

---

### Task 1: Add backend project models and workspace storage

**Files:**
- Create: `tokenmind/projects/__init__.py`
- Create: `tokenmind/projects/models.py`
- Create: `tokenmind/projects/store.py`
- Test: `tests/test_project_store.py`

- [ ] **Step 1: Write the failing project-store tests**

```python
from pathlib import Path

from tokenmind.projects.store import ProjectStore


def test_create_project_persists_workspace_metadata(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)

    project = store.create_project("产品重构")

    assert project.name == "产品重构"
    assert (tmp_path / "projects" / "projects.json").exists()


def test_duplicate_project_name_is_rejected(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    store.create_project("发布计划")

    try:
        store.create_project("发布计划")
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("Expected duplicate project name to fail")


def test_list_projects_returns_most_recent_first(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    first = store.create_project("A")
    second = store.create_project("B")

    items = store.list_projects()

    assert items[0].id == second.id
    assert items[1].id == first.id
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
pytest tests/test_project_store.py -q
```

Expected: FAIL with import errors because `tokenmind.projects` does not exist yet.

- [ ] **Step 3: Implement the models and store**

Create `tokenmind/projects/models.py`:

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now().isoformat()


class ProjectRecord(BaseModel):
    id: str
    name: str
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
```

Create `tokenmind/projects/store.py`:

```python
from __future__ import annotations

import json
import uuid
from pathlib import Path

from tokenmind.projects.models import ProjectRecord


class ProjectStore:
    def __init__(self, workspace: Path):
        self.root = workspace / "projects"
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "projects.json"

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, items: list[dict]) -> None:
        self.path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_projects(self) -> list[ProjectRecord]:
        items = [ProjectRecord(**item) for item in self._load()]
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def create_project(self, name: str) -> ProjectRecord:
        normalized = name.strip()
        if not normalized:
            raise ValueError("Project name cannot be empty")
        items = self._load()
        if any(str(item.get("name", "")).strip().lower() == normalized.lower() for item in items):
            raise ValueError(f"Project '{normalized}' already exists")
        project = ProjectRecord(id=f"proj_{uuid.uuid4().hex[:10]}", name=normalized)
        items.append(project.model_dump())
        self._save(items)
        return project

    def get_project(self, project_id: str) -> ProjectRecord | None:
        for item in self._load():
            if item.get("id") == project_id:
                return ProjectRecord(**item)
        return None

    def rename_project(self, project_id: str, name: str) -> ProjectRecord:
        normalized = name.strip()
        if not normalized:
            raise ValueError("Project name cannot be empty")
        items = self._load()
        for item in items:
            if item.get("id") != project_id and str(item.get("name", "")).strip().lower() == normalized.lower():
                raise ValueError(f"Project '{normalized}' already exists")
        for item in items:
            if item.get("id") == project_id:
                item["name"] = normalized
                item["updated_at"] = now_iso()
                self._save(items)
                return ProjectRecord(**item)
        raise KeyError(project_id)
```

Create `tokenmind/projects/__init__.py`:

```python
from tokenmind.projects.store import ProjectStore

__all__ = ["ProjectStore"]
```

- [ ] **Step 4: Run the store tests to verify they pass**

Run:

```powershell
pytest tests/test_project_store.py -q
```

Expected: PASS with 3 passing tests.

### Task 2: Extend session metadata and expose project APIs through ChatService

**Files:**
- Create: `tokenmind/server/routes/projects.py`
- Modify: `tokenmind/server/routes/__init__.py`
- Modify: `tokenmind/server/app.py`
- Modify: `tokenmind/server/routes/sessions.py`
- Modify: `tokenmind/session/manager.py`
- Test: `tests/test_project_routes.py`
- Test: `tests/test_project_chat_service.py`

- [ ] **Step 1: Write the failing service and route tests**

```python
from pathlib import Path
from types import SimpleNamespace
import asyncio

import pytest

from tokenmind.agent.memory import MemoryStore
from tokenmind.server.app import ChatService
from tokenmind.session.manager import SessionManager


def make_service(tmp_path: Path) -> ChatService:
    session_manager = SessionManager(tmp_path)
    memory_store = MemoryStore(tmp_path)
    agent_loop = SimpleNamespace(
        memory_consolidator=SimpleNamespace(
            store=memory_store,
            templates_config=SimpleNamespace(memory_system="", memory_prompt=""),
        )
    )
    return ChatService(bus=SimpleNamespace(), agent_loop=agent_loop, session_manager=session_manager)


def test_list_sessions_excludes_project_sessions(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    normal = service.session_manager.get_or_create("web:normal")
    normal.add_message("user", "普通会话")
    service.session_manager.save(normal)
    project = service.session_manager.get_or_create("web:project")
    project.metadata["project_id"] = "proj_1"
    project.add_message("user", "项目会话")
    service.session_manager.save(project)

    sessions = asyncio.run(service.list_sessions())

    assert [item["session_id"] for item in sessions] == ["web:normal"]


def test_move_session_to_project_preserves_history(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    created = service.create_project("发布计划")
    session = service.session_manager.get_or_create("web:existing")
    session.add_message("user", "第一条消息")
    session.add_message("assistant", "保留历史")
    service.session_manager.save(session)

    result = service.move_session_to_project(created["id"], "web:existing")
    moved = service.session_manager.get_or_create("web:existing")

    assert result["session"]["project_id"] == created["id"]
    assert moved.messages[0]["content"] == "第一条消息"
    assert moved.messages[1]["content"] == "保留历史"
```

```python
import importlib
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_list_projects_route_returns_service_payload() -> None:
    routes = importlib.import_module("tokenmind.server.routes.projects")
    service = SimpleNamespace(list_projects=lambda: {"items": [{"id": "proj_1", "name": "发布计划"}]})

    response = await routes.list_projects(service=service)

    assert response["items"][0]["name"] == "发布计划"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
pytest tests/test_project_chat_service.py tests/test_project_routes.py -q
```

Expected: FAIL because project APIs and session filtering are not implemented.

- [ ] **Step 3: Add project metadata helpers to the session layer**

Modify `tokenmind/session/manager.py`:

```python
    @property
    def project_id(self) -> str | None:
        value = self.metadata.get("project_id")
        return value if isinstance(value, str) and value else None

    def set_project_id(self, project_id: str | None) -> None:
        if project_id:
            self.metadata["project_id"] = project_id
        else:
            self.metadata.pop("project_id", None)
        self.updated_at = datetime.now()
```

Also include project metadata in session listings:

```python
                            sessions.append({
                                "key": key,
                                "created_at": data.get("created_at"),
                                "updated_at": data.get("updated_at"),
                                "path": str(path),
                                "title": (data.get("metadata") or {}).get("title"),
                                "project_id": (data.get("metadata") or {}).get("project_id"),
                            })
```

- [ ] **Step 4: Add project-aware methods to ChatService**

Modify `tokenmind/server/app.py`:

```python
from tokenmind.projects import ProjectStore
```

```python
        self.projects = ProjectStore(session_manager.workspace)
```

```python
    def _serialize_session_summary(self, session_id: str, session: Any, summary: dict[str, Any]) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "updated_at": self._session_last_activity_iso(session, summary.get("updated_at")),
            "created_at": session.created_at.isoformat() if session else None,
            "message_count": len(session.messages) if session else 0,
            "first_message": self._extract_first_message_preview(session),
            "title": session.title if session else summary.get("title"),
            "project_id": getattr(session, "project_id", None) or summary.get("project_id"),
        }
```

```python
    async def list_sessions(self) -> list[dict]:
        result = []
        for summary in self.session_manager.list_sessions():
            if summary.get("project_id"):
                continue
            session_id = summary.get("key", "")
            session = self.session_manager.get_or_create(session_id)
            if getattr(session, "project_id", None):
                continue
            result.append(self._serialize_session_summary(session_id, session, summary))
        return sorted(result, key=lambda item: item.get("updated_at") or "", reverse=True)

    def list_project_sessions(self, project_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for summary in self.session_manager.list_sessions():
            session_id = summary.get("key", "")
            session = self.session_manager.get_or_create(session_id)
            if getattr(session, "project_id", None) != project_id:
                continue
            items.append(self._serialize_session_summary(session_id, session, summary))
        return sorted(items, key=lambda item: item.get("updated_at") or "", reverse=True)

    def list_projects(self) -> dict[str, Any]:
        items = []
        for project in self.projects.list_projects():
            items.append({**project.model_dump(), "session_count": len(self.list_project_sessions(project.id))})
        return {"items": items}

    def create_project(self, name: str) -> dict[str, Any]:
        project = self.projects.create_project(name)
        return {**project.model_dump(), "session_count": 0}

    def get_project_detail(self, project_id: str) -> dict[str, Any]:
        project = self.projects.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return {"project": project.model_dump(), "sessions": self.list_project_sessions(project_id)}

    def create_project_session(self, project_id: str, session_id: str, title: str | None = None) -> dict[str, Any]:
        if self.projects.get_project(project_id) is None:
            raise HTTPException(status_code=404, detail="Project not found")
        session = self.session_manager.get_or_create(session_id)
        session.set_project_id(project_id)
        if title:
            session.set_title(title)
        self.session_manager.save(session)
        return self._serialize_session_summary(session_id, session, {"updated_at": session.updated_at.isoformat()})

    def move_session_to_project(self, project_id: str, session_id: str) -> dict[str, Any]:
        if self.projects.get_project(project_id) is None:
            raise HTTPException(status_code=404, detail="Project not found")
        session = self.session_manager.get_or_create(session_id)
        if session.project_id:
            raise HTTPException(status_code=409, detail="Session already belongs to a project")
        session.set_project_id(project_id)
        self.session_manager.save(session)
        return {"session": self._serialize_session_summary(session_id, session, {"updated_at": session.updated_at.isoformat()})}
```

- [ ] **Step 5: Add the project routes**

Create `tokenmind/server/routes/projects.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from tokenmind.server.dependencies import get_chat_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str


class RenameProjectRequest(BaseModel):
    name: str


class CreateProjectSessionRequest(BaseModel):
    session_id: str
    title: str | None = None


class LinkProjectSessionRequest(BaseModel):
    session_id: str


@router.get("")
async def list_projects(service=Depends(get_chat_service)) -> dict:
    return service.list_projects()


@router.post("")
async def create_project(request: CreateProjectRequest, service=Depends(get_chat_service)) -> dict:
    return service.create_project(request.name)


@router.get("/{project_id}")
async def get_project(project_id: str, service=Depends(get_chat_service)) -> dict:
    return service.get_project_detail(project_id)


@router.put("/{project_id}")
async def rename_project(project_id: str, request: RenameProjectRequest, service=Depends(get_chat_service)) -> dict:
    return service.rename_project(project_id, request.name)


@router.post("/{project_id}/sessions")
async def create_project_session(project_id: str, request: CreateProjectSessionRequest, service=Depends(get_chat_service)) -> dict:
    return service.create_project_session(project_id, request.session_id, request.title)


@router.post("/{project_id}/sessions/link")
async def link_session_to_project(project_id: str, request: LinkProjectSessionRequest, service=Depends(get_chat_service)) -> dict:
    return service.move_session_to_project(project_id, request.session_id)
```

Modify `tokenmind/server/routes/__init__.py` and `tokenmind/server/app.py` to import and register `projects_router`.

- [ ] **Step 6: Run the backend tests**

Run:

```powershell
pytest tests/test_project_store.py tests/test_project_chat_service.py tests/test_project_routes.py -q
```

Expected: PASS.

### Task 3: Add frontend project types, API client, store state, and project home page

**Files:**
- Create: `frontend/src/pages/ProjectHome.tsx`
- Create: `frontend/src/components/Projects/CreateProjectModal.tsx`
- Create: `frontend/src/components/Projects/projects.css`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/stores/chatStore.ts`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add the frontend types**

Add to `frontend/src/types/index.ts`:

```ts
export interface Project {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  session_count: number;
}

export interface ProjectSession extends Session {
  project_id?: string;
}

export interface ProjectDetailResponse {
  project: Project;
  sessions: ProjectSession[];
}
```

- [ ] **Step 2: Extend the API client**

Modify `frontend/src/services/api.ts`:

```ts
import type { Project, ProjectDetailResponse, ProjectSession } from '../types';
```

```ts
async listProjects(): Promise<{ items: Project[] }> {
  const res = await fetch(`${API_BASE}/projects`);
  if (!res.ok) throw new Error(`Failed to list projects: ${res.statusText}`);
  return res.json();
},

async createProject(name: string): Promise<Project> {
  const res = await fetch(`${API_BASE}/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => null);
    throw new Error(error?.detail || `Failed to create project: ${res.statusText}`);
  }
  return res.json();
},

async getProject(projectId: string): Promise<ProjectDetailResponse> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}`);
  if (!res.ok) throw new Error(`Failed to load project: ${res.statusText}`);
  return res.json();
},

async createProjectSession(projectId: string, sessionId: string, title?: string): Promise<ProjectSession> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, title }),
  });
  if (!res.ok) throw new Error(`Failed to create project session: ${res.statusText}`);
  return res.json();
},

async moveSessionToProject(projectId: string, sessionId: string): Promise<{ session: ProjectSession }> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/sessions/link`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!res.ok) throw new Error(`Failed to move session to project: ${res.statusText}`);
  return res.json();
},
```

- [ ] **Step 3: Add project-aware global state**

Modify `frontend/src/stores/chatStore.ts`:

```ts
type MainView = 'chat' | 'knowledge' | 'project-home' | 'project-chat';
```

```ts
  projects: Project[];
  activeProjectId: string | null;
  projectSessions: ProjectSession[];
  mainView: MainView;
  loadProjects: () => Promise<void>;
  openProject: (projectId: string) => Promise<void>;
  setMainView: (view: MainView) => void;
```

```ts
  projects: [],
  activeProjectId: null,
  projectSessions: [],
  mainView: 'chat',
```

```ts
  setMainView: (mainView) => set({ mainView }),

  loadProjects: async () => {
    const payload = await api.listProjects();
    set({ projects: payload.items });
  },

  openProject: async (projectId) => {
    const payload = await api.getProject(projectId);
    set({
      activeProjectId: projectId,
      projectSessions: payload.sessions,
      mainView: 'project-home',
      currentSession: null,
      messages: [],
      toolCalls: [],
      timelineEvents: [],
    });
  },
```

Update `setCurrentSession` so project sessions switch the app into `project-chat`.

- [ ] **Step 4: Add the create-project modal and project home page**

Create `frontend/src/components/Projects/CreateProjectModal.tsx`:

```tsx
import React, { useState } from 'react';
import { api } from '../../services/api';
import { useChatStore } from '../../stores/chatStore';
import './projects.css';

export const CreateProjectModal: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const { loadProjects, openProject } = useChatStore();

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError('项目名称不能为空');
      return;
    }
    setSaving(true);
    try {
      const project = await api.createProject(name.trim());
      await loadProjects();
      await openProject(project.id);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建项目失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="project-modal__backdrop">
      <div className="project-modal">
        <h2>创建项目</h2>
        <input value={name} onChange={(event) => setName(event.target.value)} placeholder="输入项目名称" />
        {error ? <div className="project-modal__error">{error}</div> : null}
        <div className="project-modal__actions">
          <button type="button" onClick={onClose}>取消</button>
          <button type="button" onClick={handleSubmit} disabled={saving}>{saving ? '创建中...' : '创建项目'}</button>
        </div>
      </div>
    </div>
  );
};
```

Create `frontend/src/pages/ProjectHome.tsx`:

```tsx
import React from 'react';
import { useChatStore } from '../stores/chatStore';
import '../components/Projects/projects.css';

export const ProjectHome: React.FC<{ onCreateChat: () => void; onOpenSession: (sessionId: string) => void }> = ({
  onCreateChat,
  onOpenSession,
}) => {
  const { projects, activeProjectId, projectSessions } = useChatStore();
  const project = projects.find((item) => item.id === activeProjectId);

  return (
    <section className="project-home">
      <header className="project-home__header">
        <div>
          <p className="project-home__eyebrow">项目</p>
          <h1>{project?.name || '项目'}</h1>
          <p>项目中的聊天只会在当前项目内显示。</p>
        </div>
        <button type="button" onClick={onCreateChat}>新聊天</button>
      </header>

      {projectSessions.length === 0 ? (
        <div className="project-home__empty">
          <h2>还没有项目聊天</h2>
          <p>从这里创建的新会话会只属于当前项目，不会出现在全局最近列表。</p>
        </div>
      ) : (
        <div className="project-home__list">
          {projectSessions.map((session) => (
            <button key={session.session_id} type="button" className="project-home__item" onClick={() => onOpenSession(session.session_id)}>
              <strong>{session.title || session.first_message || '新对话'}</strong>
              <span>{session.first_message || '暂无摘要'}</span>
              <small>{session.updated_at ? new Date(session.updated_at).toLocaleDateString('zh-CN') : ''}</small>
            </button>
          ))}
        </div>
      )}
    </section>
  );
};
```

- [ ] **Step 5: Wire the new view into App**

Modify `frontend/src/App.tsx`:

```tsx
  const {
    currentSession,
    fetchModelProviders,
    setCurrentSession,
    mainView,
    setMainView,
    activeProjectId,
  } = useChatStore();
```

```tsx
            {mainView === 'knowledge' ? (
              <KnowledgePage isActive />
            ) : mainView === 'project-home' ? (
              <ProjectHome
                onCreateChat={() => {
                  void createNewSession();
                }}
                onOpenSession={(sessionId) => setCurrentSession(sessionId)}
              />
            ) : currentSession ? (
              <ChatWindow sessionId={currentSession} />
            ) : (
              <div className="app-main__empty">点击左侧“新建对话”开始新的会话</div>
            )}
```

- [ ] **Step 6: Run the frontend build**

Run:

```powershell
npm run build
```

Workdir:

```powershell
frontend
```

Expected: PASS.

### Task 4: Extend the sidebar and add project chat creation and move-to-project flows

**Files:**
- Create: `frontend/src/components/Projects/MoveSessionToProjectModal.tsx`
- Modify: `frontend/src/components/Layout/Sidebar.tsx`
- Modify: `frontend/src/components/Layout/sidebar.css`
- Modify: `frontend/src/hooks/useSessions.ts`
- Modify: `frontend/src/stores/chatStore.ts`
- Test: `tests/test_project_chat_service.py`

- [ ] **Step 1: Add project-aware session creation to the hook**

Modify `frontend/src/hooks/useSessions.ts`:

```ts
import { api } from '../services/api';
```

```ts
  const { sessions, loadSessions, setCurrentSession, activeProjectId } = useChatStore();
```

```ts
  const createNewSession = async () => {
    const newSessionId = `web:${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    if (activeProjectId) {
      await api.createProjectSession(activeProjectId, newSessionId);
    }
    setCurrentSession(newSessionId);
    return newSessionId;
  };
```

- [ ] **Step 2: Add the move-to-project modal**

Create `frontend/src/components/Projects/MoveSessionToProjectModal.tsx`:

```tsx
import React, { useState } from 'react';
import { api } from '../../services/api';
import { useChatStore } from '../../stores/chatStore';
import './projects.css';

export const MoveSessionToProjectModal: React.FC<{ sessionId: string; onClose: () => void }> = ({ sessionId, onClose }) => {
  const { projects, loadProjects, loadSessions, openProject } = useChatStore();
  const [selectedProjectId, setSelectedProjectId] = useState(projects[0]?.id || '');
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!selectedProjectId) {
      setError('请选择一个项目');
      return;
    }
    try {
      await api.moveSessionToProject(selectedProjectId, sessionId);
      await loadSessions();
      await loadProjects();
      await openProject(selectedProjectId);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '移动会话失败');
    }
  };

  return (
    <div className="project-modal__backdrop">
      <div className="project-modal">
        <h2>移入项目</h2>
        <select value={selectedProjectId} onChange={(event) => setSelectedProjectId(event.target.value)}>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>{project.name}</option>
          ))}
        </select>
        {error ? <div className="project-modal__error">{error}</div> : null}
        <div className="project-modal__actions">
          <button type="button" onClick={onClose}>取消</button>
          <button type="button" onClick={handleSubmit}>确认移入</button>
        </div>
      </div>
    </div>
  );
};
```

- [ ] **Step 3: Add the project section to the sidebar**

Modify `frontend/src/components/Layout/Sidebar.tsx` to:

- load `projects`, `loadProjects`, `openProject`, and `mainView`
- add a `项目` collapsible group directly below `知识库`
- show `新项目` plus project names only in the expanded group
- open `CreateProjectModal` from `新项目`
- add a `移入项目` action for normal sessions
- keep the existing recent list bound to `sessions`, which the backend already filters

Core structure:

```tsx
<div className="shell-sidebar__group">
  <button type="button" className="shell-sidebar__group-toggle" onClick={() => setProjectsExpanded((value) => !value)}>
    <span>项目</span>
    <span>{projectsExpanded ? '▾' : '▸'}</span>
  </button>
  {projectsExpanded ? (
    <div className="shell-sidebar__project-list">
      <button type="button" className="shell-sidebar__project-create" onClick={() => setShowCreateProject(true)}>
        新项目
      </button>
      {projects.map((project) => (
        <button key={project.id} type="button" className="shell-sidebar__project-item" onClick={() => void openProject(project.id)}>
          <span>{project.name}</span>
        </button>
      ))}
    </div>
  ) : null}
</div>
```

- [ ] **Step 4: Run the targeted tests and frontend build**

Run:

```powershell
pytest tests/test_project_store.py tests/test_project_chat_service.py tests/test_project_routes.py -q
npm run build
```

Frontend workdir:

```powershell
frontend
```

Expected: all tests pass and frontend build passes.

- [ ] **Step 5: Run final regression verification**

Run:

```powershell
pytest tests/test_storage_routes.py tests/test_memory_routes.py -q
python -m compileall tokenmind
```

Expected: PASS.

## Self-Review

### Spec coverage

- create-project modal with name only: covered in Tasks 3 and 4
- sidebar “项目” section under knowledge base: covered in Task 4
- project dropdown shows names only: covered in Task 4
- project home page with empty state and session list: covered in Task 3
- new chats created inside a project: covered in Task 4
- global recent list hides project sessions: covered in Task 2
- move existing normal chat into a project: covered in Task 4
- preserve session history after moving: covered in Task 2

### Placeholder scan

- no `TBD`, `TODO`, or “implement later”
- each task includes exact paths and runnable commands
- each code-changing step includes concrete snippets to anchor the implementation

### Type consistency

- backend names stay aligned on `ProjectStore`, `ProjectRecord`, `project_id`, `list_project_sessions`, `create_project_session`, and `move_session_to_project`
- frontend names stay aligned on `Project`, `ProjectSession`, `projects`, `activeProjectId`, `projectSessions`, and `mainView`
