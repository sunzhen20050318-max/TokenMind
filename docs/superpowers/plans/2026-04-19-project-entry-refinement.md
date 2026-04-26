# TokenMind Project Entry Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine the project experience so entering a project shows a project-scoped launcher page with an immediate input box and project conversation list, while the sidebar project dropdown looks like a true project directory instead of another stack of nav buttons.

**Architecture:** Keep the existing backend project/session model unchanged and focus this iteration on frontend information architecture. Add a small set of pure project-entry/project-sidebar helper modules with unit tests, then rebuild `ProjectHome` into a launcher surface, wire “send first message” into new project-session creation, and restyle the sidebar so projects and project-local conversations have a lighter second/third-level hierarchy.

**Tech Stack:** React 18, TypeScript, Zustand, Vite, Node `test`, lightweight `tsx` test runner for frontend unit tests.

---

## File Structure

### Frontend

- Create: `frontend/src/components/Projects/ProjectEntryComposer.tsx`
- Create: `frontend/src/components/Projects/projectEntryFlow.ts`
- Create: `frontend/src/components/Projects/projectEntryState.ts`
- Create: `frontend/src/components/Projects/projectSidebarState.ts`
- Create: `frontend/tests/projectEntryFlow.test.ts`
- Create: `frontend/tests/projectEntryState.test.ts`
- Create: `frontend/tests/projectSidebarState.test.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout/Sidebar.tsx`
- Modify: `frontend/src/components/Layout/sidebar.css`
- Modify: `frontend/src/components/Projects/projects.css`
- Modify: `frontend/src/pages/ProjectHome.tsx`
- Modify: `frontend/src/stores/chatStore.ts`

---

### Task 1: Add a runnable frontend unit-test loop and the core project-entry helper modules

**Files:**
- Create: `frontend/src/components/Projects/projectEntryFlow.ts`
- Create: `frontend/src/components/Projects/projectSidebarState.ts`
- Create: `frontend/tests/projectEntryFlow.test.ts`
- Create: `frontend/tests/projectSidebarState.test.ts`
- Modify: `frontend/package.json`

- [ ] **Step 1: Add a frontend unit-test runner script**

Modify `frontend/package.json`:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test:unit": "tsx --test tests/**/*.test.ts"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "tsx": "^4.19.2",
    "typescript": "^5.5.3",
    "vite": "^5.4.2"
  }
}
```

- [ ] **Step 2: Install the new dev dependency**

Run:

```powershell
npm install
```

Workdir:

```powershell
D:\project\TokenMind\frontend
```

Expected: PASS and `tsx` is available locally.

- [ ] **Step 3: Write the failing project-entry flow tests**

Create `frontend/tests/projectEntryFlow.test.ts`:

```ts
import test from 'node:test';
import assert from 'node:assert/strict';
import { createProjectConversation } from '../src/components/Projects/projectEntryFlow';

test('createProjectConversation creates a project session, sends the first message, and returns the session id', async () => {
  const calls: string[] = [];

  const sessionId = await createProjectConversation({
    projectId: 'proj_1',
    message: '帮我整理这个项目的待办',
    generateSessionId: () => 'web:test-project-session',
    createProjectSession: async (projectId, nextSessionId) => {
      calls.push(`create:${projectId}:${nextSessionId}`);
    },
    sendMessage: async (content, nextSessionId) => {
      calls.push(`send:${nextSessionId}:${content}`);
    },
  });

  assert.equal(sessionId, 'web:test-project-session');
  assert.deepEqual(calls, [
    'create:proj_1:web:test-project-session',
    'send:web:test-project-session:帮我整理这个项目的待办',
  ]);
});

test('createProjectConversation rejects blank messages', async () => {
  await assert.rejects(
    () =>
      createProjectConversation({
        projectId: 'proj_1',
        message: '   ',
        generateSessionId: () => 'web:test-project-session',
        createProjectSession: async () => undefined,
        sendMessage: async () => undefined,
      }),
    /message cannot be empty/i
  );
});
```

Create `frontend/tests/projectSidebarState.test.ts`:

```ts
import test from 'node:test';
import assert from 'node:assert/strict';
import { buildProjectSidebarTree } from '../src/components/Projects/projectSidebarState';

test('buildProjectSidebarTree nests sessions only under the active project', () => {
  const tree = buildProjectSidebarTree({
    projects: [
      { id: 'proj_1', name: '项目一', created_at: '', updated_at: '', session_count: 2 },
      { id: 'proj_2', name: '项目二', created_at: '', updated_at: '', session_count: 1 },
    ],
    activeProjectId: 'proj_1',
    projectSessions: [
      { session_id: 'web:s1', title: '问候交流', message_count: 2, project_id: 'proj_1' },
      { session_id: 'web:s2', title: '排期整理', message_count: 4, project_id: 'proj_1' },
    ],
  });

  assert.equal(tree.length, 2);
  assert.equal(tree[0].project.id, 'proj_1');
  assert.equal(tree[0].sessions.length, 2);
  assert.equal(tree[1].project.id, 'proj_2');
  assert.equal(tree[1].sessions.length, 0);
});
```

- [ ] **Step 4: Run the tests to verify they fail**

Run:

```powershell
npm run test:unit -- tests/projectEntryFlow.test.ts tests/projectSidebarState.test.ts
```

Workdir:

```powershell
D:\project\TokenMind\frontend
```

Expected: FAIL with import errors because the helper modules do not exist yet.

- [ ] **Step 5: Implement the minimal helper modules**

Create `frontend/src/components/Projects/projectEntryFlow.ts`:

```ts
export interface CreateProjectConversationOptions {
  projectId: string;
  message: string;
  generateSessionId: () => string;
  createProjectSession: (projectId: string, sessionId: string) => Promise<void>;
  sendMessage: (message: string, sessionId: string) => Promise<void>;
}

export async function createProjectConversation(
  options: CreateProjectConversationOptions
): Promise<string> {
  const trimmed = options.message.trim();
  if (!trimmed) {
    throw new Error('message cannot be empty');
  }

  const sessionId = options.generateSessionId();
  await options.createProjectSession(options.projectId, sessionId);
  await options.sendMessage(trimmed, sessionId);
  return sessionId;
}
```

Create `frontend/src/components/Projects/projectSidebarState.ts`:

```ts
import type { Project, Session } from '../../types';

interface BuildProjectSidebarTreeOptions {
  projects: Project[];
  activeProjectId: string | null;
  projectSessions: Session[];
}

interface ProjectSidebarNode {
  project: Project;
  sessions: Session[];
}

export function buildProjectSidebarTree(
  options: BuildProjectSidebarTreeOptions
): ProjectSidebarNode[] {
  return options.projects.map((project) => ({
    project,
    sessions: project.id === options.activeProjectId ? options.projectSessions : [],
  }));
}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run:

```powershell
npm run test:unit -- tests/projectEntryFlow.test.ts tests/projectSidebarState.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add frontend/package.json frontend/src/components/Projects/projectEntryFlow.ts frontend/src/components/Projects/projectSidebarState.ts frontend/tests/projectEntryFlow.test.ts frontend/tests/projectSidebarState.test.ts
git commit -m "test: add project entry frontend unit loop"
```

### Task 2: Rebuild the project page into a launcher surface with inline composer and lightweight empty state

**Files:**
- Create: `frontend/src/components/Projects/ProjectEntryComposer.tsx`
- Create: `frontend/src/components/Projects/projectEntryState.ts`
- Create: `frontend/tests/projectEntryState.test.ts`
- Modify: `frontend/src/pages/ProjectHome.tsx`
- Modify: `frontend/src/components/Projects/projects.css`

- [ ] **Step 1: Write the failing project-entry state tests**

Create `frontend/tests/projectEntryState.test.ts`:

```ts
import test from 'node:test';
import assert from 'node:assert/strict';
import { buildProjectEntryState } from '../src/components/Projects/projectEntryState';

test('buildProjectEntryState returns an inline empty hint for empty projects', () => {
  const state = buildProjectEntryState({
    projectName: '测试项目',
    sessions: [],
  });

  assert.equal(state.title, '测试项目');
  assert.equal(state.showEmptyHint, true);
  assert.match(state.emptyHint, /还没有项目聊天/);
});

test('buildProjectEntryState disables the empty hint when project sessions exist', () => {
  const state = buildProjectEntryState({
    projectName: '测试项目',
    sessions: [{ session_id: 'web:s1', title: '问候交流', message_count: 2 }],
  });

  assert.equal(state.showEmptyHint, false);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
npm run test:unit -- tests/projectEntryState.test.ts
```

Expected: FAIL because `projectEntryState.ts` does not exist yet.

- [ ] **Step 3: Implement the minimal project-entry state helper**

Create `frontend/src/components/Projects/projectEntryState.ts`:

```ts
import type { Session } from '../../types';

interface BuildProjectEntryStateOptions {
  projectName: string;
  sessions: Session[];
}

export function buildProjectEntryState(options: BuildProjectEntryStateOptions) {
  return {
    title: options.projectName,
    showEmptyHint: options.sessions.length === 0,
    emptyHint: '还没有项目聊天，直接在上面的输入框里发起第一段项目内对话。',
  };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
npm run test:unit -- tests/projectEntryState.test.ts
```

Expected: PASS.

- [ ] **Step 5: Build the launcher-style project entry surface**

Create `frontend/src/components/Projects/ProjectEntryComposer.tsx`:

```tsx
import React from 'react';

interface ProjectEntryComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
}

export const ProjectEntryComposer: React.FC<ProjectEntryComposerProps> = ({
  value,
  onChange,
  onSubmit,
  disabled = false,
}) => (
  <div className="project-entry-composer">
    <textarea
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
          event.preventDefault();
          onSubmit();
        }
      }}
      placeholder="在这个项目中发起新聊天"
      disabled={disabled}
      rows={1}
      className="project-entry-composer__input"
    />
    <button type="button" onClick={onSubmit} disabled={disabled || !value.trim()} className="project-entry-composer__submit">
      发送
    </button>
  </div>
);
```

Modify `frontend/src/pages/ProjectHome.tsx` so it:

- renders a compact project header
- renders `ProjectEntryComposer` immediately below the title
- keeps the conversation list directly below the composer
- replaces the large empty panel with a small inline empty hint

Core structure:

```tsx
const entryState = buildProjectEntryState({
  projectName: project?.name || '项目',
  sessions: projectSessions,
});

return (
  <section className="project-home">
    <header className="project-home__header is-entry">
      <div className="project-home__identity">
        <span className="project-home__icon">📁</span>
        <div>
          <h1>{entryState.title}</h1>
        </div>
      </div>
    </header>

    <ProjectEntryComposer
      value={draft}
      onChange={setDraft}
      onSubmit={() => {
        void onStartConversation(draft);
      }}
    />

    {entryState.showEmptyHint ? (
      <p className="project-home__inline-empty">{entryState.emptyHint}</p>
    ) : (
      <div className="project-home__list">...</div>
    )}
  </section>
);
```

Modify `frontend/src/components/Projects/projects.css` so the page becomes tighter and more launcher-like:

```css
.project-home {
  height: 100%;
  overflow: auto;
  padding: 28px 42px 40px;
}

.project-home__header.is-entry {
  margin-bottom: 18px;
}

.project-home__identity {
  display: flex;
  align-items: center;
  gap: 14px;
}

.project-entry-composer {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
  padding: 10px 12px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.035);
}

.project-home__inline-empty {
  margin: 8px 2px 0;
  color: #9095a1;
  font-size: 13px;
}
```

- [ ] **Step 6: Run the unit tests and build**

Run:

```powershell
npm run test:unit -- tests/projectEntryState.test.ts tests/projectEntryFlow.test.ts tests/projectSidebarState.test.ts
npm run build
```

Workdir:

```powershell
D:\project\TokenMind\frontend
```

Expected: both commands PASS.

- [ ] **Step 7: Commit**

```powershell
git add frontend/src/components/Projects/ProjectEntryComposer.tsx frontend/src/components/Projects/projectEntryState.ts frontend/tests/projectEntryState.test.ts frontend/src/pages/ProjectHome.tsx frontend/src/components/Projects/projects.css
git commit -m "feat: turn project page into launcher surface"
```

### Task 3: Wire “send from project page” into project-session creation and immediate chat navigation

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/stores/chatStore.ts`
- Modify: `frontend/src/pages/ProjectHome.tsx`

- [ ] **Step 1: Extend the failing project-entry flow test to cover navigation result wiring**

Update `frontend/tests/projectEntryFlow.test.ts`:

```ts
test('createProjectConversation uses the generated session id for the first message send', async () => {
  let sentToSessionId = '';

  await createProjectConversation({
    projectId: 'proj_1',
    message: '创建项目聊天',
    generateSessionId: () => 'web:project-seeded',
    createProjectSession: async () => undefined,
    sendMessage: async (_message, sessionId) => {
      sentToSessionId = sessionId;
    },
  });

  assert.equal(sentToSessionId, 'web:project-seeded');
});
```

- [ ] **Step 2: Run the test to verify current behavior**

Run:

```powershell
npm run test:unit -- tests/projectEntryFlow.test.ts
```

Expected: PASS if the helper is still correct. This step locks the contract before wiring UI around it.

- [ ] **Step 3: Implement the UI flow in `App.tsx` and `ProjectHome.tsx`**

Modify `frontend/src/App.tsx`:

```tsx
import { api } from './services/api';
import { createProjectConversation } from './components/Projects/projectEntryFlow';
```

```tsx
const { currentSession, fetchModelProviders, setCurrentSession, activeProjectId } = useChatStore();
```

```tsx
<ProjectHome
  onStartConversation={async (message) => {
    if (!activeProjectId) {
      return;
    }
    const sessionId = await createProjectConversation({
      projectId: activeProjectId,
      message,
      generateSessionId: () => `web:${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      createProjectSession: async (projectId, nextSessionId) => {
        await api.createProjectSession(projectId, nextSessionId);
      },
      sendMessage: async (content, nextSessionId) => {
        await api.sendMessage(content, nextSessionId);
      },
    });

    setCurrentSession(sessionId);
    setMainView('project-chat');
  }}
  onOpenSession={(sessionId) => {
    setCurrentSession(sessionId);
    setMainView('project-chat');
  }}
/>;
```

Modify `frontend/src/pages/ProjectHome.tsx` props:

```tsx
interface ProjectHomeProps {
  onStartConversation: (message: string) => Promise<void> | void;
  onOpenSession: (sessionId: string) => void;
}
```

- [ ] **Step 4: Run the unit tests and build**

Run:

```powershell
npm run test:unit -- tests/projectEntryFlow.test.ts tests/projectEntryState.test.ts tests/projectSidebarState.test.ts
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/App.tsx frontend/src/pages/ProjectHome.tsx frontend/src/stores/chatStore.ts
git commit -m "feat: launch project chats from entry composer"
```

### Task 4: Refine the sidebar into a directory-style project hierarchy with nested active-project conversations

**Files:**
- Modify: `frontend/src/components/Layout/Sidebar.tsx`
- Modify: `frontend/src/components/Layout/sidebar.css`
- Modify: `frontend/src/stores/chatStore.ts`

- [ ] **Step 1: Write the failing sidebar-tree test for nested project conversations**

Update `frontend/tests/projectSidebarState.test.ts`:

```ts
test('buildProjectSidebarTree exposes active-project sessions as third-level items', () => {
  const tree = buildProjectSidebarTree({
    projects: [
      { id: 'proj_1', name: '项目一', created_at: '', updated_at: '', session_count: 2 },
    ],
    activeProjectId: 'proj_1',
    projectSessions: [
      { session_id: 'web:s1', title: '问候交流', message_count: 2, project_id: 'proj_1' },
    ],
  });

  assert.equal(tree[0].sessions[0].title, '问候交流');
});
```

- [ ] **Step 2: Run the test to verify the current helper contract**

Run:

```powershell
npm run test:unit -- tests/projectSidebarState.test.ts
```

Expected: PASS. This locks the data shape before the visual refactor.

- [ ] **Step 3: Rebuild the sidebar project section using the helper tree**

Modify `frontend/src/components/Layout/Sidebar.tsx`:

```tsx
import { buildProjectSidebarTree } from '../Projects/projectSidebarState';
```

```tsx
const projectTree = buildProjectSidebarTree({
  projects,
  activeProjectId,
  projectSessions,
});
```

Replace the current project list block with:

```tsx
<div className="shell-sidebar__project-directory">
  <button type="button" className="shell-sidebar__project-create is-quiet" onClick={() => setShowCreateProject(true)}>
    + 新项目
  </button>

  {projectTree.map((node) => (
    <div key={node.project.id} className="shell-sidebar__project-node">
      <button
        type="button"
        className={`shell-sidebar__project-row ${activeProjectId === node.project.id ? 'is-active' : ''}`}
        onClick={() => {
          void handleOpenProject(node.project.id);
        }}
      >
        <span className="shell-sidebar__project-row-icon">📁</span>
        <span className="shell-sidebar__project-row-label">{node.project.name}</span>
      </button>

      {node.sessions.length > 0 ? (
        <div className="shell-sidebar__project-session-list">
          {node.sessions.map((session) => (
            <button
              key={session.session_id}
              type="button"
              className={`shell-sidebar__project-session ${currentSession === session.session_id ? 'is-active' : ''}`}
              onClick={() => {
                setCurrentSession(session.session_id);
                onSelectMainView('project-chat');
              }}
            >
              {session.title || session.first_message || '新对话'}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  ))}
</div>
```

Modify `frontend/src/components/Layout/sidebar.css` so second-level and third-level items are lighter than first-level nav:

```css
.shell-sidebar__project-directory {
  display: grid;
  gap: 4px;
  margin-top: 6px;
}

.shell-sidebar__project-create.is-quiet {
  justify-content: flex-start;
  padding: 7px 12px;
  background: transparent;
  border: 1px dashed rgba(255, 255, 255, 0.06);
  color: #a7acb7;
}

.shell-sidebar__project-row {
  position: relative;
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px 8px 14px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  color: #d2d5dd;
}

.shell-sidebar__project-row.is-active::before {
  content: '';
  position: absolute;
  left: 6px;
  top: 7px;
  bottom: 7px;
  width: 2px;
  border-radius: 999px;
  background: #f3f4f6;
}

.shell-sidebar__project-session-list {
  display: grid;
  gap: 3px;
  margin: 2px 0 6px 22px;
  padding-left: 10px;
  border-left: 1px solid rgba(255, 255, 255, 0.05);
}

.shell-sidebar__project-session {
  padding: 6px 10px;
  border-radius: 10px;
  background: transparent;
  color: #9ea4b0;
  font-size: 12px;
  text-align: left;
}
```

- [ ] **Step 4: Run the unit tests and final frontend verification**

Run:

```powershell
npm run test:unit -- tests/projectEntryFlow.test.ts tests/projectEntryState.test.ts tests/projectSidebarState.test.ts
npm run build
```

Expected: PASS.

- [ ] **Step 5: Run product regression verification**

Manual checks:

1. open a project and verify the title is shown at the top
2. verify the composer is immediately under the title
3. send a first message and confirm the app jumps into the new project chat
4. click the project name again and confirm the new conversation is now listed on the launcher page
5. confirm the sidebar project dropdown looks lighter than first-level nav items
6. confirm only the active project reveals nested project-local conversations
7. confirm global recent sessions still exclude project conversations

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/components/Layout/Sidebar.tsx frontend/src/components/Layout/sidebar.css frontend/src/stores/chatStore.ts
git commit -m "feat: refine project entry and sidebar hierarchy"
```

## Self-Review

### Spec coverage

- project page shows project name at the top: covered in Task 2
- project page shows input directly below title: covered in Task 2
- project conversation list sits below the input: covered in Task 2
- first message creates project session and opens the full chat page: covered in Task 3
- project dropdown becomes directory-like instead of button-like: covered in Task 4
- third-level project conversations appear only after entering a project: covered in Task 4
- global recent list behavior remains unchanged: regression checks in Task 4

### Placeholder scan

- no `TBD`, `TODO`, or deferred “implement later” language
- each task lists exact files, code anchors, and commands
- all verification steps have explicit expected outcomes

### Type consistency

- `createProjectConversation`, `buildProjectEntryState`, and `buildProjectSidebarTree` are introduced once and reused consistently
- project-entry flow still uses existing `projectId`, `sessionId`, and `projectSessions` naming
- view names stay aligned with existing `project-home` and `project-chat`
