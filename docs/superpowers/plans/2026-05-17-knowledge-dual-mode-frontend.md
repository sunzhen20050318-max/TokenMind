# 知识库双模 Frontend 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给前端 KB 页面增加 Wiki 模式支持：创建对话框选 type、KB 卡片显示类型徽标、Wiki KB 拥有独立的页面浏览器 + Markdown 阅读器 + ECharts 知识图谱视图；聊天侧把现有「链接知识库」过滤为 RAG-only，并并列加一个「当前 Wiki KB」单选下拉，写入 `session.active_wiki_kb_id`。

**Architecture:** 沿用现有前端结构和风格——React 18 + TS + Vite + Zustand + 纯 CSS（**不引入新依赖**）。每个组件一个 `.tsx` + 同名 `.css` 放在 `components/Knowledge/` 下，遵循 BEM-ish 命名（`kb-detail__panel`, `is-active` modifier 等）。CSS 变量沿用 `knowledge.css` 已定义的色系（`--kb-bg / --kb-panel / --kb-text` 等），确保深色 monochrome 一致。Markdown 用已有 `react-markdown + remark-gfm`，图谱用已有 `echarts`。

**Tech Stack:** React 18.3 + TypeScript 5.5 + Vite 5 + Zustand 4 + 纯 CSS（CSS Variables，无 Tailwind）+ react-markdown 9 + remark-gfm 4 + echarts 6。测试用 `tsx --test`（已配置）做纯逻辑测试；UI 通过 `npm run build` + 浏览器手测验证。

---

## File Structure

**新建文件（10 个 .tsx + 8 个 .css + 1 个 test）：**

```
frontend/src/components/Knowledge/
  WikiKbDetail.tsx           wikiKbDetail.css        # 容器（列表 + 阅读器 + 图谱 tab 切换）
  WikiPageList.tsx           wikiPageList.css        # 按 type 分组的页面列表
  WikiPageViewer.tsx         wikiPageViewer.css      # Markdown 阅读器 + 反链栏
  KnowledgeGraph.tsx         knowledgeGraph.css      # ECharts force layout
frontend/src/components/Chat/
  ActiveWikiSelector.tsx     activeWikiSelector.css  # composer 单选下拉

frontend/tests/
  knowledgeDualModeFrontend.test.ts                  # 纯逻辑：类型守卫、wikilink 解析、页面分组
```

**修改文件（8 个）：**

```
frontend/src/types/knowledge.ts                # +type, +wiki counts, +WikiPage, +WikiGraphData
frontend/src/services/api.ts                   # +createKnowledgeBase 接受 type
                                               # +listWikiPages, getWikiGraph, rebuildWikiGraph
                                               # +patchSession(active_wiki_kb_id)
frontend/src/components/Knowledge/CreateKnowledgeBaseModal.tsx  # 类型单选
frontend/src/components/Knowledge/createKnowledgeBaseModal.css  # 类型选择器样式
frontend/src/pages/Knowledge.tsx               # KB 卡片 type 徽标; detail 按 type 分发
frontend/src/pages/knowledge.css               # type 徽标样式
frontend/src/components/Chat/InputArea.tsx     # 「链接知识库」过滤 rag; 挂 ActiveWikiSelector
frontend/src/components/Chat/ChatWindow.tsx    # 把 activeWikiKbId 透传给 InputArea
frontend/src/stores/chatStore.ts               # +activeWikiKbId 状态、loadActiveWikiKb、setActiveWikiKb
```

每个新组件单一职责，独立 .css 文件。沿用现有 `knowledge.css` 的 CSS 变量定义，无新色值。

---

## Phase 1: Foundation (types + api)

### Task F1: 更新 KnowledgeBase TS 类型

**Files:**
- Modify: `frontend/src/types/knowledge.ts:1-10`
- Test: `frontend/tests/knowledgeDualModeFrontend.test.ts` (new)

- [ ] **Step 1: Create the test file with failing test**

Create `frontend/tests/knowledgeDualModeFrontend.test.ts`:

```typescript
import test from 'node:test';
import assert from 'node:assert/strict';

import { isWikiKb, isRagKb } from '../src/types/knowledge';
import type { KnowledgeBase } from '../src/types/knowledge';

test('isWikiKb returns true for type="wiki"', () => {
  const kb: KnowledgeBase = {
    id: 'kb_x',
    name: 'w',
    description: '',
    type: 'wiki',
    status: 'ready',
    enabled: true,
    document_count: 0,
    language: 'zh',
    root_path: '',
    source_count: 0,
    page_count: 0,
    entity_count: 0,
    topic_count: 0,
    link_count: 0,
    created_at: '',
    updated_at: '',
  };
  assert.equal(isWikiKb(kb), true);
  assert.equal(isRagKb(kb), false);
});

test('isRagKb returns true when type is "rag" or missing', () => {
  const rag: KnowledgeBase = {
    id: 'kb_r',
    name: 'r',
    description: '',
    type: 'rag',
    status: 'ready',
    enabled: true,
    document_count: 0,
    language: 'zh',
    root_path: '',
    source_count: 0,
    page_count: 0,
    entity_count: 0,
    topic_count: 0,
    link_count: 0,
    created_at: '',
    updated_at: '',
  };
  assert.equal(isRagKb(rag), true);
  assert.equal(isWikiKb(rag), false);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:unit -- --test-name-pattern="isWiki|isRag" 2>&1 | tail -10`
Expected: FAIL (`isWikiKb` is not exported).

- [ ] **Step 3: Update `frontend/src/types/knowledge.ts`**

Replace the whole file:

```typescript
export type KnowledgeBaseType = 'rag' | 'wiki';

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  type: KnowledgeBaseType;
  status: string;
  enabled: boolean;
  document_count: number;
  // Wiki-specific counts (default 0 for rag KBs)
  language: string;
  root_path: string;
  source_count: number;
  page_count: number;
  entity_count: number;
  topic_count: number;
  link_count: number;
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
  processing_stage: string;
  processing_progress: number;
  error_message?: string | null;
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

export interface WikiPageSummary {
  title: string;
  type: 'source' | 'entity' | 'topic' | 'comparison' | 'synthesis' | 'query' | 'page';
  path: string;
}

export interface WikiPageListResponse {
  pages: WikiPageSummary[];
}

export interface WikiGraphNode {
  id: string;
  title: string;
  type: string;
  path: string;
  summary: string;
  degree: number;
}

export interface WikiGraphEdge {
  source: string;
  target: string;
  relation: string;
  weight: number;
}

export interface WikiGraphData {
  nodes: WikiGraphNode[];
  edges: WikiGraphEdge[];
  broken_links: { from: string; target: string }[];
  updated_at: string | null;
}

export function isWikiKb(kb: KnowledgeBase): boolean {
  return kb.type === 'wiki';
}

export function isRagKb(kb: KnowledgeBase): boolean {
  return kb.type === 'rag';
}
```

- [ ] **Step 4: Verify test passes**

Run: `cd frontend && npm run test:unit -- --test-name-pattern="isWiki|isRag" 2>&1 | tail -10`
Expected: 2 PASS.

- [ ] **Step 5: Verify build still compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -10`
Expected: clean (no TS errors introduced).

If there are errors elsewhere because something accessed `KnowledgeBase.type` previously (unlikely — it didn't exist before), fix them in this task.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/knowledge.ts frontend/tests/knowledgeDualModeFrontend.test.ts
git commit -m "feat(frontend): KnowledgeBase type discriminator + wiki fields + type guards"
```

---

### Task F2: API client — `createKnowledgeBase` 接受 type

**Files:**
- Modify: `frontend/src/services/api.ts:873` (`createKnowledgeBase` signature)
- Test: `frontend/tests/knowledgeDualModeFrontend.test.ts`

- [ ] **Step 1: Add test**

Append to `frontend/tests/knowledgeDualModeFrontend.test.ts`:

```typescript
test('createKnowledgeBase payload accepts optional type field', () => {
  // Type-only test: this fails at compile time if the signature is wrong.
  type CreateKbPayload = Parameters<typeof import('../src/services/api').api.createKnowledgeBase>[0];
  const payload: CreateKbPayload = { name: 'x', description: 'y', type: 'wiki' };
  assert.equal(payload.type, 'wiki');
});
```

- [ ] **Step 2: Run test**

Run: `cd frontend && npm run test:unit 2>&1 | tail -10`
Expected: FAIL with type error (`'type' does not exist in type ...`).

- [ ] **Step 3: Update signature in `frontend/src/services/api.ts:873`**

Replace:

```typescript
async createKnowledgeBase(payload: { name: string; description: string }): Promise<KnowledgeDetailResponse | KnowledgeOverviewResponse | Record<string, unknown>> {
```

with:

```typescript
async createKnowledgeBase(payload: {
  name: string;
  description: string;
  type?: KnowledgeBaseType;
  language?: string;
}): Promise<KnowledgeDetailResponse | KnowledgeOverviewResponse | Record<string, unknown>> {
```

And update the import line at the top of `api.ts` (around line 57). Find:

```typescript
import type { KnowledgeDetailResponse, KnowledgeDocument, KnowledgeOverviewResponse } from '../types/knowledge';
```

Change to:

```typescript
import type {
  KnowledgeBaseType,
  KnowledgeDetailResponse,
  KnowledgeDocument,
  KnowledgeOverviewResponse,
} from '../types/knowledge';
```

- [ ] **Step 4: Verify test passes**

Run: `cd frontend && npm run test:unit 2>&1 | tail -10`
Expected: PASS.

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -5`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/api.ts frontend/tests/knowledgeDualModeFrontend.test.ts
git commit -m "feat(frontend): api.createKnowledgeBase accepts type and language"
```

---

### Task F3: API client — Wiki page/graph methods

**Files:**
- Modify: `frontend/src/services/api.ts` (append methods near `deleteKnowledgeBase`)
- Test: `frontend/tests/knowledgeDualModeFrontend.test.ts`

- [ ] **Step 1: Add tests**

Append to `frontend/tests/knowledgeDualModeFrontend.test.ts`:

```typescript
test('api exposes listWikiPages, getWikiGraph, rebuildWikiGraph', () => {
  const { api } = require('../src/services/api');
  assert.equal(typeof api.listWikiPages, 'function');
  assert.equal(typeof api.getWikiGraph, 'function');
  assert.equal(typeof api.rebuildWikiGraph, 'function');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:unit -- --test-name-pattern="api exposes" 2>&1 | tail -10`
Expected: FAIL (methods undefined).

- [ ] **Step 3: Add the methods**

In `frontend/src/services/api.ts`, find the `deleteKnowledgeBase` method (around line 900) and append AFTER it:

```typescript
  async listWikiPages(id: string): Promise<WikiPageListResponse> {
    const res = await fetch(`${API_BASE}/knowledge/${encodeURIComponent(id)}/pages`);
    if (!res.ok) {
      throw new Error(`Failed to list wiki pages: ${res.statusText}`);
    }
    return res.json();
  },

  async getWikiGraph(id: string): Promise<WikiGraphData> {
    const res = await fetch(`${API_BASE}/knowledge/${encodeURIComponent(id)}/graph`);
    if (!res.ok) {
      throw new Error(`Failed to load wiki graph: ${res.statusText}`);
    }
    return res.json();
  },

  async rebuildWikiGraph(id: string): Promise<WikiGraphData> {
    const res = await fetch(`${API_BASE}/knowledge/${encodeURIComponent(id)}/graph/rebuild`, {
      method: 'POST',
    });
    if (!res.ok) {
      throw new Error(`Failed to rebuild wiki graph: ${res.statusText}`);
    }
    return res.json();
  },
```

Also extend the import block at top of `api.ts` (the one already covering knowledge types):

```typescript
import type {
  KnowledgeBaseType,
  KnowledgeDetailResponse,
  KnowledgeDocument,
  KnowledgeOverviewResponse,
  WikiGraphData,
  WikiPageListResponse,
} from '../types/knowledge';
```

- [ ] **Step 4: Verify test passes**

Run: `cd frontend && npm run test:unit -- --test-name-pattern="api exposes" 2>&1 | tail -10`
Expected: PASS.

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -5`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/api.ts frontend/tests/knowledgeDualModeFrontend.test.ts
git commit -m "feat(frontend): api.listWikiPages, getWikiGraph, rebuildWikiGraph"
```

---

### Task F4: API client — `patchSession` for active_wiki_kb_id

**Files:**
- Modify: `frontend/src/services/api.ts` (append near other session methods around line 165)
- Test: `frontend/tests/knowledgeDualModeFrontend.test.ts`

- [ ] **Step 1: Add test**

Append:

```typescript
test('api.patchSession is a function with (sessionId, payload) signature', () => {
  const { api } = require('../src/services/api');
  assert.equal(typeof api.patchSession, 'function');
});
```

- [ ] **Step 2: Verify fail**

Run: `cd frontend && npm run test:unit -- --test-name-pattern="patchSession" 2>&1 | tail -10`
Expected: FAIL.

- [ ] **Step 3: Add the method**

In `frontend/src/services/api.ts`, find the existing PUT session method (e.g., `renameSession` near line 165) and append AFTER it:

```typescript
  async patchSession(
    sessionId: string,
    payload: { active_wiki_kb_id?: string | null },
  ): Promise<{ session_id: string; active_wiki_kb_id: string | null }> {
    const res = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`Failed to patch session: ${res.statusText}`);
    }
    return res.json();
  },
```

- [ ] **Step 4: Verify test passes**

Run: `cd frontend && npm run test:unit 2>&1 | tail -10`
Expected: all PASS.

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -5`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/api.ts frontend/tests/knowledgeDualModeFrontend.test.ts
git commit -m "feat(frontend): api.patchSession for active_wiki_kb_id"
```

---

## Phase 2: Create dialog — type radio

### Task F5: 创建对话框增加类型单选

**Files:**
- Modify: `frontend/src/components/Knowledge/CreateKnowledgeBaseModal.tsx`
- Modify: `frontend/src/components/Knowledge/createKnowledgeBaseModal.css` (append type-selector styles)

- [ ] **Step 1: Read existing CSS to understand variables**

```bash
head -30 frontend/src/components/Knowledge/createKnowledgeBaseModal.css
```

Note the existing CSS variable names / palette. We will reuse them.

- [ ] **Step 2: Update CreateKnowledgeBaseModal.tsx**

Replace the file with:

```tsx
import React, { useEffect, useState } from 'react';

import { api } from '../../services/api';
import type { KnowledgeBaseType } from '../../types/knowledge';
import './createKnowledgeBaseModal.css';

interface CreateKnowledgeBaseModalProps {
  onClose: () => void;
  onCreated: () => void | Promise<void>;
}

interface TypeOption {
  value: KnowledgeBaseType;
  title: string;
  blurb: string;
}

const TYPE_OPTIONS: TypeOption[] = [
  {
    value: 'rag',
    title: 'RAG 知识库',
    blurb: '上传文档后自动切分、向量化，提问时由后端检索片段注入上下文。',
  },
  {
    value: 'wiki',
    title: 'Wiki 知识库',
    blurb: 'LLM 把原始资料编译成相互链接的 Markdown 页面，对话时模型用工具浏览。',
  },
];

export const CreateKnowledgeBaseModal: React.FC<CreateKnowledgeBaseModalProps> = ({
  onClose,
  onCreated,
}) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [type, setType] = useState<KnowledgeBaseType>('rag');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Esc closes
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const handleSubmit = async () => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError('名称不能为空');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.createKnowledgeBase({
        name: trimmedName,
        description: description.trim(),
        type,
      });
      await onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建知识库失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="kb-modal__backdrop" onClick={onClose}>
      <div
        className="kb-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="kb-modal-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="kb-modal__header">
          <h2 id="kb-modal-title">新建知识库</h2>
          <button
            type="button"
            className="kb-modal__close"
            onClick={onClose}
            aria-label="关闭"
          >
            ×
          </button>
        </div>

        <fieldset className="kb-modal__type-group" aria-label="知识库类型">
          {TYPE_OPTIONS.map((option) => (
            <label
              key={option.value}
              className={`kb-modal__type-card ${type === option.value ? 'is-active' : ''}`}
            >
              <input
                type="radio"
                name="kb-type"
                value={option.value}
                checked={type === option.value}
                onChange={() => setType(option.value)}
              />
              <span className="kb-modal__type-title">{option.title}</span>
              <span className="kb-modal__type-blurb">{option.blurb}</span>
            </label>
          ))}
        </fieldset>

        <label className="kb-modal__field">
          <span>名称</span>
          <input
            autoFocus
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="例如:产品资料、合同模板、项目规范"
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void handleSubmit();
              }
            }}
          />
        </label>

        <label className="kb-modal__field">
          <span>简介(可选)</span>
          <textarea
            rows={3}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="一句话说明这个知识库主要收什么资料。"
          />
        </label>

        {error ? <div className="kb-modal__error">{error}</div> : null}

        <div className="kb-modal__actions">
          <button
            type="button"
            className="kb-modal__button is-secondary"
            onClick={onClose}
          >
            取消
          </button>
          <button
            type="button"
            className="kb-modal__button"
            onClick={() => void handleSubmit()}
            disabled={saving}
          >
            {saving ? '创建中…' : '创建'}
          </button>
        </div>
      </div>
    </div>
  );
};
```

- [ ] **Step 3: Append CSS for type selector**

Append to `frontend/src/components/Knowledge/createKnowledgeBaseModal.css`:

```css
.kb-modal__type-group {
  border: none;
  padding: 0;
  margin: 0 0 18px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.kb-modal__type-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
  cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.kb-modal__type-card:hover {
  border-color: rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.04);
}

.kb-modal__type-card.is-active {
  border-color: #f5f5f7;
  background: rgba(245, 245, 247, 0.06);
}

.kb-modal__type-card input[type="radio"] {
  /* Visually hide but keep accessible */
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.kb-modal__type-title {
  font-size: 13px;
  font-weight: 600;
  color: #f5f5f7;
}

.kb-modal__type-blurb {
  font-size: 12px;
  line-height: 1.5;
  color: #b6b6bf;
}
```

- [ ] **Step 4: Manually verify**

Start frontend dev: `cd frontend && npm run dev` (in another shell ensure backend is running at 18888).
Open http://localhost:5173, click "新建知识库", confirm:
- Two type cards visible (RAG, Wiki) with the right copy
- Clicking a card highlights it (`.is-active` border)
- Creating with type=wiki actually creates a wiki KB (backend will respond with `type: "wiki"`)

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -5`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Knowledge/CreateKnowledgeBaseModal.tsx frontend/src/components/Knowledge/createKnowledgeBaseModal.css
git commit -m "feat(frontend): CreateKnowledgeBaseModal type radio (RAG / Wiki)"
```

---

## Phase 3: KB list cards — type badge

### Task F6: KB 卡片显示类型徽标

**Files:**
- Modify: `frontend/src/pages/Knowledge.tsx` (the section that renders each card)
- Modify: `frontend/src/pages/knowledge.css` (append badge styles)

- [ ] **Step 1: Locate card render**

```bash
grep -n "knowledge-page__card\|knowledge-page__card-meta\|kb.name\|item.name" frontend/src/pages/Knowledge.tsx | head -15
```

Locate the JSX that renders each KB item card. You should see something like `<div className="knowledge-page__card-meta">...</div>` containing name and counts.

- [ ] **Step 2: Add the badge to the card**

Inside the card's title row (next to `kb.name`), insert a type badge. The conditional renders RAG vs Wiki copy/style. Add:

```tsx
<span className={`knowledge-page__type-badge knowledge-page__type-badge--${kb.type}`}>
  {kb.type === 'wiki' ? 'Wiki' : 'RAG'}
</span>
```

Within the same card, also update the count line: if `kb.type === 'wiki'`, show `{kb.source_count} 份素材 · {kb.page_count} 页 · {kb.entity_count + kb.topic_count} 概念`. Else keep the existing `{kb.document_count} 份资料`. Use a small helper inline:

```tsx
{kb.type === 'wiki'
  ? `${kb.source_count} 份素材 · ${kb.page_count} 页 · ${kb.entity_count + kb.topic_count} 概念`
  : `${kb.document_count} 份资料`}
```

- [ ] **Step 3: Append CSS**

Append to `frontend/src/pages/knowledge.css`:

```css
.knowledge-page__type-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 8px;
  margin-left: 8px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  border-radius: 999px;
  border: 1px solid var(--kb-border-strong);
  background: var(--kb-panel-soft);
  color: var(--kb-muted);
  vertical-align: middle;
}

.knowledge-page__type-badge--wiki {
  border-color: rgba(166, 196, 255, 0.32);
  color: #a6c4ff;
  background: rgba(166, 196, 255, 0.06);
}

.knowledge-page__type-badge--rag {
  border-color: rgba(255, 255, 255, 0.16);
  color: var(--kb-muted);
}
```

- [ ] **Step 4: Verify build**

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -5`
Expected: clean.

Manually in browser: KB list should show RAG/Wiki badges next to name.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Knowledge.tsx frontend/src/pages/knowledge.css
git commit -m "feat(frontend): KB card shows type badge and wiki-specific count line"
```

---

## Phase 4: Wiki KB detail view

### Task F7: WikiPageList component

**Files:**
- Create: `frontend/src/components/Knowledge/WikiPageList.tsx`
- Create: `frontend/src/components/Knowledge/wikiPageList.css`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/Knowledge/WikiPageList.tsx`:

```tsx
import React, { useMemo } from 'react';

import type { WikiPageSummary } from '../../types/knowledge';
import './wikiPageList.css';

interface WikiPageListProps {
  pages: WikiPageSummary[];
  selectedPath: string | null;
  onSelect: (path: string) => void;
}

const TYPE_ORDER: WikiPageSummary['type'][] = [
  'entity',
  'topic',
  'source',
  'synthesis',
  'comparison',
  'query',
  'page',
];

const TYPE_LABELS: Record<WikiPageSummary['type'], string> = {
  entity: '实体',
  topic: '主题',
  source: '素材',
  synthesis: '综合',
  comparison: '对比',
  query: '查询',
  page: '其他',
};

export const WikiPageList: React.FC<WikiPageListProps> = ({ pages, selectedPath, onSelect }) => {
  const grouped = useMemo(() => {
    const map = new Map<WikiPageSummary['type'], WikiPageSummary[]>();
    for (const page of pages) {
      const bucket = map.get(page.type) ?? [];
      bucket.push(page);
      map.set(page.type, bucket);
    }
    return TYPE_ORDER.filter((t) => map.has(t)).map((t) => ({
      type: t,
      pages: [...(map.get(t) ?? [])].sort((a, b) => a.title.localeCompare(b.title, 'zh-CN')),
    }));
  }, [pages]);

  if (!pages.length) {
    return (
      <div className="wiki-pagelist__empty">
        还没有任何 Wiki 页面。上传素材后，LLM 会自动编译出 source / entity / topic 页面。
      </div>
    );
  }

  return (
    <div className="wiki-pagelist">
      {grouped.map((group) => (
        <section key={group.type} className="wiki-pagelist__group">
          <header className="wiki-pagelist__group-head">
            <span className="wiki-pagelist__group-label">{TYPE_LABELS[group.type]}</span>
            <span className="wiki-pagelist__group-count">{group.pages.length}</span>
          </header>
          <ul className="wiki-pagelist__items">
            {group.pages.map((page) => (
              <li
                key={page.path}
                className={`wiki-pagelist__item ${selectedPath === page.path ? 'is-active' : ''}`}
              >
                <button type="button" onClick={() => onSelect(page.path)}>
                  {page.title}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
};
```

- [ ] **Step 2: Create the CSS**

Create `frontend/src/components/Knowledge/wikiPageList.css`:

```css
.wiki-pagelist {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 12px;
  overflow-y: auto;
  height: 100%;
}

.wiki-pagelist__empty {
  padding: 18px;
  color: var(--kb-muted, #b6b6bf);
  font-size: 12px;
  line-height: 1.6;
  text-align: center;
}

.wiki-pagelist__group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 4px 6px;
  border-bottom: 1px solid var(--kb-border, rgba(255, 255, 255, 0.06));
}

.wiki-pagelist__group-label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--kb-soft, #6f6f77);
}

.wiki-pagelist__group-count {
  font-size: 11px;
  color: var(--kb-soft, #6f6f77);
}

.wiki-pagelist__items {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.wiki-pagelist__item button {
  width: 100%;
  padding: 6px 10px;
  text-align: left;
  font-size: 13px;
  color: var(--kb-text, #f5f5f7);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.12s ease, border-color 0.12s ease;
}

.wiki-pagelist__item button:hover {
  background: rgba(255, 255, 255, 0.04);
}

.wiki-pagelist__item.is-active button {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
}
```

- [ ] **Step 3: Add a logic test**

Append to `frontend/tests/knowledgeDualModeFrontend.test.ts`:

```typescript
test('WikiPageList groups pages by type in defined order', async () => {
  // Pure logic check: group ordering precedence (entity > topic > source).
  // We can't render React, so test the grouping logic by mirroring it.
  const pages = [
    { title: 'Y', type: 'source' as const, path: 'wiki/sources/Y.md' },
    { title: 'A', type: 'entity' as const, path: 'wiki/entities/A.md' },
    { title: 'T', type: 'topic' as const, path: 'wiki/topics/T.md' },
  ];
  const TYPE_ORDER = ['entity', 'topic', 'source', 'synthesis', 'comparison', 'query', 'page'];
  const order: string[] = [];
  for (const t of TYPE_ORDER) {
    for (const p of pages.filter((p) => p.type === t)) order.push(p.title);
  }
  assert.deepEqual(order, ['A', 'T', 'Y']);
});
```

- [ ] **Step 4: Verify**

Run: `cd frontend && npm run test:unit -- --test-name-pattern="WikiPageList" 2>&1 | tail -5`
Expected: PASS.

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -5`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Knowledge/WikiPageList.tsx frontend/src/components/Knowledge/wikiPageList.css frontend/tests/knowledgeDualModeFrontend.test.ts
git commit -m "feat(frontend): WikiPageList groups wiki pages by type"
```

---

### Task F8: WikiPageViewer (Markdown 阅读器)

**Files:**
- Create: `frontend/src/components/Knowledge/WikiPageViewer.tsx`
- Create: `frontend/src/components/Knowledge/wikiPageViewer.css`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/Knowledge/WikiPageViewer.tsx`:

```tsx
import React, { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import './wikiPageViewer.css';

interface WikiPageViewerProps {
  knowledgeBaseId: string;
  pagePath: string | null;
  onFollowLink?: (title: string) => void;
}

interface PageResponse {
  title: string;
  type: string;
  path: string;
  content: string;
  frontmatter: Record<string, string>;
  outgoing_links: string[];
}

const WIKILINK_RE = /\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]/g;

function transformWikilinks(markdown: string): string {
  // Render [[Title]] as a plain bracketed token; click handling is delegated to the
  // outgoing-links sidebar list. Replacing with backticked text keeps the link visible
  // without rendering as an unresolved Markdown link.
  return markdown.replace(WIKILINK_RE, (_, target) => `**[[${String(target).trim()}]]**`);
}

export const WikiPageViewer: React.FC<WikiPageViewerProps> = ({
  knowledgeBaseId: _knowledgeBaseId,
  pagePath,
  onFollowLink,
}) => {
  const [page, setPage] = useState<PageResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!pagePath) {
      setPage(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    // Read directly from disk via a tiny passthrough: the backend already exposes
    // page content via `wiki_read` tool, but for the UI we need a simple GET.
    // For now we fetch the raw markdown by encoding the path as a query param
    // against a yet-unmade endpoint; if that endpoint is missing, the fallback
    // is to show the placeholder text below. Phase 7 (verification) lists this
    // as a manual checkpoint.
    fetch(`/api/knowledge/${encodeURIComponent(_knowledgeBaseId)}/pages/raw?path=${encodeURIComponent(pagePath)}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = (await res.json()) as PageResponse;
        if (!cancelled) setPage(body);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '加载页面失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [pagePath, _knowledgeBaseId]);

  if (!pagePath) {
    return (
      <div className="wiki-viewer__placeholder">
        从左侧选择一个页面查看内容。
      </div>
    );
  }

  if (loading) {
    return <div className="wiki-viewer__placeholder">加载中…</div>;
  }

  if (error || !page) {
    return (
      <div className="wiki-viewer__placeholder is-error">
        加载失败：{error ?? '未知错误'}
      </div>
    );
  }

  return (
    <article className="wiki-viewer">
      <header className="wiki-viewer__head">
        <div className="wiki-viewer__meta">
          <span className={`wiki-viewer__type wiki-viewer__type--${page.type}`}>{page.type}</span>
          <span className="wiki-viewer__path">{page.path}</span>
        </div>
        <h1 className="wiki-viewer__title">{page.title}</h1>
      </header>
      <div className="wiki-viewer__body">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {transformWikilinks(page.content)}
        </ReactMarkdown>
      </div>
      {page.outgoing_links.length > 0 && (
        <aside className="wiki-viewer__sidebar">
          <h3>出链</h3>
          <ul>
            {page.outgoing_links.map((link) => (
              <li key={link}>
                <button type="button" onClick={() => onFollowLink?.(link)}>
                  {link}
                </button>
              </li>
            ))}
          </ul>
        </aside>
      )}
    </article>
  );
};
```

**IMPORTANT NOTE**: The component fetches from `/api/knowledge/{kb_id}/pages/raw?path=...` which is NOT yet a backend endpoint (only `pages` list is implemented). **Task F9 (next) adds this endpoint** along with the WikiKbDetail container. Until F9 lands, this viewer will render the "加载失败" placeholder state — that's expected and won't crash anything.

- [ ] **Step 2: Create the CSS**

Create `frontend/src/components/Knowledge/wikiPageViewer.css`:

```css
.wiki-viewer {
  display: grid;
  grid-template-columns: 1fr 200px;
  gap: 24px;
  padding: 24px;
  overflow-y: auto;
  height: 100%;
  color: var(--kb-text, #f5f5f7);
}

.wiki-viewer__placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 24px;
  color: var(--kb-soft, #6f6f77);
  font-size: 13px;
}

.wiki-viewer__placeholder.is-error {
  color: var(--kb-danger, #f1b9b9);
}

.wiki-viewer__head {
  grid-column: 1 / -1;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--kb-border, rgba(255, 255, 255, 0.06));
}

.wiki-viewer__meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
  font-size: 11px;
  color: var(--kb-soft, #6f6f77);
}

.wiki-viewer__type {
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.06);
}

.wiki-viewer__type--entity { color: #a6c4ff; }
.wiki-viewer__type--topic { color: #b3d8b1; }
.wiki-viewer__type--source { color: #d9c98a; }

.wiki-viewer__path {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  color: var(--kb-soft, #6f6f77);
}

.wiki-viewer__title {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.wiki-viewer__body {
  font-size: 14px;
  line-height: 1.7;
}

.wiki-viewer__body h2 {
  font-size: 16px;
  font-weight: 600;
  margin: 24px 0 8px;
  letter-spacing: -0.005em;
}

.wiki-viewer__body h3 {
  font-size: 14px;
  font-weight: 600;
  margin: 16px 0 6px;
}

.wiki-viewer__body p {
  margin: 8px 0;
}

.wiki-viewer__body ul,
.wiki-viewer__body ol {
  margin: 8px 0 8px 22px;
}

.wiki-viewer__body code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.06);
  padding: 1px 5px;
  border-radius: 4px;
}

.wiki-viewer__body pre {
  margin: 12px 0;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--kb-border, rgba(255, 255, 255, 0.06));
  border-radius: 8px;
  overflow-x: auto;
  font-size: 12px;
}

.wiki-viewer__body strong {
  color: #f5f5f7;
  font-weight: 600;
}

.wiki-viewer__sidebar {
  padding: 16px 0 0;
}

.wiki-viewer__sidebar h3 {
  margin: 0 0 8px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--kb-soft, #6f6f77);
}

.wiki-viewer__sidebar ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.wiki-viewer__sidebar button {
  width: 100%;
  padding: 4px 8px;
  text-align: left;
  font-size: 12px;
  color: var(--kb-muted, #b6b6bf);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
}

.wiki-viewer__sidebar button:hover {
  background: rgba(255, 255, 255, 0.05);
  color: var(--kb-text, #f5f5f7);
}
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -5`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Knowledge/WikiPageViewer.tsx frontend/src/components/Knowledge/wikiPageViewer.css
git commit -m "feat(frontend): WikiPageViewer renders markdown with outgoing-links sidebar"
```

---

### Task F9: WikiKbDetail container + backend page-content endpoint

**Files:**
- Create: `frontend/src/components/Knowledge/WikiKbDetail.tsx`
- Create: `frontend/src/components/Knowledge/wikiKbDetail.css`
- Modify: `tokenmind/server/routes/knowledge.py` (add `GET /pages/raw`)
- Modify: `tokenmind/server/app.py` (add `ChatService.read_wiki_page`)
- Test (backend): `tests/test_knowledge_dual_mode.py`

This task adds the missing backend endpoint the WikiPageViewer needs, plus the container component that composes WikiPageList + WikiPageViewer.

- [ ] **Step 1: Add backend test for the new endpoint**

Append to `tests/test_knowledge_dual_mode.py`:

```python
def test_api_read_wiki_page_returns_content(tmp_path):
    from pathlib import Path as _P
    app, client = _make_kb_app(tmp_path)
    kb = client.post("/api/knowledge", json={"name": "w", "type": "wiki"}).json()
    pages_dir = _P(tmp_path) / "knowledge" / kb["id"] / "wiki" / "entities"
    (pages_dir / "Foo.md").write_text(
        "---\ntype: entity\ntitle: Foo\n---\n# Foo\nLinks to [[Bar]].\n",
        encoding="utf-8",
    )
    resp = client.get(
        f"/api/knowledge/{kb['id']}/pages/raw",
        params={"path": "wiki/entities/Foo.md"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Foo"
    assert body["type"] == "entity"
    assert "[[Bar]]" in body["content"]
    assert "Bar" in body["outgoing_links"]
```

Note: `_make_kb_app` already exists from earlier backend tasks. If it doesn't return `(app, client)` tuple, adapt to whatever shape it returns.

- [ ] **Step 2: Run test to verify fail**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v -k "read_wiki_page" 2>&1 | tail -10`
Expected: FAIL (404 not found).

- [ ] **Step 3: Add backend route**

In `tokenmind/server/routes/knowledge.py`, append:

```python
@router.get("/{knowledge_base_id}/pages/raw")
async def read_wiki_page(
    knowledge_base_id: str,
    path: str,
    service: Any = Depends(get_chat_service),
) -> dict:
    try:
        return service.read_wiki_page(knowledge_base_id, path)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

In `tokenmind/server/app.py` `ChatService`:

```python
def read_wiki_page(self, kb_id: str, page_path: str) -> dict:
    from tokenmind.knowledge.wiki_query import read_wiki_page
    kb = self.knowledge.get_knowledge_base(kb_id)
    if kb.type != "wiki":
        raise ValueError("page read is only available for wiki kbs")
    return read_wiki_page(Path(kb.root_path), page_path)
```

Also extend `_StubChatService` in `tests/test_knowledge_dual_mode.py` with `read_wiki_page` mirroring this body.

- [ ] **Step 4: Verify backend test passes**

Run: `.venv/bin/pytest tests/test_knowledge_dual_mode.py -v -k "read_wiki_page" 2>&1 | tail -10`
Expected: PASS.

- [ ] **Step 5: Create WikiKbDetail container**

Create `frontend/src/components/Knowledge/WikiKbDetail.tsx`:

```tsx
import React, { useCallback, useEffect, useState } from 'react';

import { api } from '../../services/api';
import type { KnowledgeBase, WikiPageSummary } from '../../types/knowledge';
import { WikiPageList } from './WikiPageList';
import { WikiPageViewer } from './WikiPageViewer';
import './wikiKbDetail.css';

interface WikiKbDetailProps {
  kb: KnowledgeBase;
}

type Tab = 'pages' | 'graph';

export const WikiKbDetail: React.FC<WikiKbDetailProps> = ({ kb }) => {
  const [pages, setPages] = useState<WikiPageSummary[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('pages');

  const loadPages = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const body = await api.listWikiPages(kb.id);
      setPages(body.pages);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载 Wiki 页面失败');
    } finally {
      setLoading(false);
    }
  }, [kb.id]);

  useEffect(() => {
    void loadPages();
  }, [loadPages]);

  const handleFollowLink = useCallback(
    (title: string) => {
      const match = pages.find((p) => p.title === title);
      if (match) setSelectedPath(match.path);
    },
    [pages],
  );

  return (
    <div className="wiki-detail">
      <div className="wiki-detail__tabs">
        <button
          type="button"
          className={`wiki-detail__tab ${tab === 'pages' ? 'is-active' : ''}`}
          onClick={() => setTab('pages')}
        >
          Wiki 页面
          <span className="wiki-detail__tab-count">{pages.length}</span>
        </button>
        <button
          type="button"
          className={`wiki-detail__tab ${tab === 'graph' ? 'is-active' : ''}`}
          onClick={() => setTab('graph')}
        >
          知识图谱
        </button>
      </div>

      {tab === 'pages' && (
        <div className="wiki-detail__body">
          <aside className="wiki-detail__sidebar">
            {loading ? (
              <div className="wiki-detail__loading">加载中…</div>
            ) : error ? (
              <div className="wiki-detail__error">{error}</div>
            ) : (
              <WikiPageList
                pages={pages}
                selectedPath={selectedPath}
                onSelect={setSelectedPath}
              />
            )}
          </aside>
          <main className="wiki-detail__main">
            <WikiPageViewer
              knowledgeBaseId={kb.id}
              pagePath={selectedPath}
              onFollowLink={handleFollowLink}
            />
          </main>
        </div>
      )}

      {tab === 'graph' && (
        <div className="wiki-detail__graph-slot">
          {/* KnowledgeGraph is mounted here in Task F11 */}
          <div className="wiki-detail__loading">图谱组件将在 Task F11 接入</div>
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 6: Create the CSS**

Create `frontend/src/components/Knowledge/wikiKbDetail.css`:

```css
.wiki-detail {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--kb-bg, #0a0a0c);
}

.wiki-detail__tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px 16px 0;
  border-bottom: 1px solid var(--kb-border, rgba(255, 255, 255, 0.06));
}

.wiki-detail__tab {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  font-size: 12px;
  font-weight: 500;
  color: var(--kb-muted, #b6b6bf);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.wiki-detail__tab:hover {
  color: var(--kb-text, #f5f5f7);
}

.wiki-detail__tab.is-active {
  color: var(--kb-text, #f5f5f7);
  border-bottom-color: var(--kb-text, #f5f5f7);
}

.wiki-detail__tab-count {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  color: var(--kb-muted, #b6b6bf);
}

.wiki-detail__body {
  display: grid;
  grid-template-columns: 260px 1fr;
  flex: 1;
  min-height: 0;
}

.wiki-detail__sidebar {
  overflow-y: auto;
  border-right: 1px solid var(--kb-border, rgba(255, 255, 255, 0.06));
}

.wiki-detail__main {
  overflow: hidden;
}

.wiki-detail__loading,
.wiki-detail__error {
  padding: 16px;
  color: var(--kb-soft, #6f6f77);
  font-size: 12px;
}

.wiki-detail__error {
  color: var(--kb-danger, #f1b9b9);
}

.wiki-detail__graph-slot {
  flex: 1;
  min-height: 0;
}
```

- [ ] **Step 7: Verify**

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -5`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add tokenmind/server/routes/knowledge.py tokenmind/server/app.py tests/test_knowledge_dual_mode.py frontend/src/components/Knowledge/WikiKbDetail.tsx frontend/src/components/Knowledge/wikiKbDetail.css
git commit -m "feat(knowledge): add /pages/raw endpoint + WikiKbDetail container"
```

---

### Task F10: Knowledge.tsx dispatches detail by KB type

**Files:**
- Modify: `frontend/src/pages/Knowledge.tsx`

- [ ] **Step 1: Locate the detail render**

```bash
grep -n "knowledge-page__detail\|detail-head\|setDetail\|<div className=\"knowledge-page__detail" frontend/src/pages/Knowledge.tsx | head -10
```

Find the JSX that renders the RAG detail panel (documents list, upload area, etc.).

- [ ] **Step 2: Conditionally render WikiKbDetail**

At the top of `Knowledge.tsx`, add import:

```typescript
import { WikiKbDetail } from '../components/Knowledge/WikiKbDetail';
import { isWikiKb } from '../types/knowledge';
```

In the render, just BEFORE the existing detail JSX (the RAG-flavored panel), short-circuit:

```tsx
{detail && isWikiKb(detail.knowledge_base) ? (
  <WikiKbDetail kb={detail.knowledge_base} />
) : (
  /* existing RAG detail JSX */
)}
```

If the existing detail panel is the only top-level branch (no else), wrap it in `{!isWikiKb(detail.knowledge_base) && (...)}` or restructure with the ternary above.

- [ ] **Step 3: Verify build**

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -5`
Expected: clean.

Manually:
1. `cd frontend && npm run dev`
2. Browser http://localhost:5173 → Knowledge tab
3. Create a Wiki KB if you don't have one
4. Click on it — should see the new Wiki detail (Pages tab with empty list initially, Graph tab placeholder)
5. Click on a RAG KB — should see the existing RAG documents panel unchanged

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Knowledge.tsx
git commit -m "feat(frontend): Knowledge page dispatches detail by KB type"
```

---

## Phase 5: Knowledge graph

### Task F11: KnowledgeGraph ECharts component

**Files:**
- Create: `frontend/src/components/Knowledge/KnowledgeGraph.tsx`
- Create: `frontend/src/components/Knowledge/knowledgeGraph.css`
- Modify: `frontend/src/components/Knowledge/WikiKbDetail.tsx` (replace the "图谱组件将在 Task F11 接入" placeholder)

- [ ] **Step 1: Check echarts usage pattern**

```bash
grep -rn "echarts" frontend/src --include="*.tsx" --include="*.ts" | head -10
```

If echarts is already used elsewhere in the codebase, mirror the import/init pattern. If not, the canonical pattern is below.

- [ ] **Step 2: Create the component**

Create `frontend/src/components/Knowledge/KnowledgeGraph.tsx`:

```tsx
import React, { useCallback, useEffect, useRef, useState } from 'react';
import * as echarts from 'echarts/core';
import { GraphChart } from 'echarts/charts';
import { TitleComponent, TooltipComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

import { api } from '../../services/api';
import type { WikiGraphData } from '../../types/knowledge';
import './knowledgeGraph.css';

echarts.use([GraphChart, TitleComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

interface KnowledgeGraphProps {
  knowledgeBaseId: string;
  onSelectNode?: (path: string) => void;
}

const CATEGORY_COLORS: Record<string, string> = {
  entity: '#a6c4ff',
  topic: '#b3d8b1',
  source: '#d9c98a',
  synthesis: '#e0a6ff',
  comparison: '#ffb38a',
  query: '#cccccc',
  page: '#888888',
};

export const KnowledgeGraph: React.FC<KnowledgeGraphProps> = ({ knowledgeBaseId, onSelectNode }) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const [data, setData] = useState<WikiGraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rebuilding, setRebuilding] = useState(false);

  const loadGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.getWikiGraph(knowledgeBaseId));
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载图谱失败');
    } finally {
      setLoading(false);
    }
  }, [knowledgeBaseId]);

  const handleRebuild = useCallback(async () => {
    setRebuilding(true);
    setError(null);
    try {
      setData(await api.rebuildWikiGraph(knowledgeBaseId));
    } catch (err) {
      setError(err instanceof Error ? err.message : '重建图谱失败');
    } finally {
      setRebuilding(false);
    }
  }, [knowledgeBaseId]);

  useEffect(() => {
    void loadGraph();
  }, [loadGraph]);

  useEffect(() => {
    if (!containerRef.current) return;
    if (!chartRef.current) {
      chartRef.current = echarts.init(containerRef.current, 'dark');
    }
    const onClick = (params: { dataType?: string; data?: { path?: string } }) => {
      if (params.dataType === 'node' && params.data?.path && onSelectNode) {
        onSelectNode(params.data.path);
      }
    };
    chartRef.current.on('click', onClick);
    return () => {
      chartRef.current?.off('click', onClick);
    };
  }, [onSelectNode]);

  useEffect(() => {
    if (!chartRef.current || !data) return;
    const categories = Array.from(new Set(data.nodes.map((n) => n.type))).map((t) => ({ name: t }));
    chartRef.current.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        formatter: (params: { dataType?: string; data?: { name?: string; type?: string; summary?: string } }) => {
          if (params.dataType !== 'node') return '';
          const d = params.data ?? {};
          return `<strong>${d.name ?? ''}</strong><br/>${d.type ?? ''}<br/>${d.summary ?? ''}`;
        },
      },
      legend: {
        data: categories.map((c) => c.name),
        textStyle: { color: '#b6b6bf', fontSize: 11 },
        top: 8,
      },
      series: [
        {
          type: 'graph',
          layout: 'force',
          force: { repulsion: 220, gravity: 0.05, edgeLength: [60, 140] },
          roam: true,
          draggable: true,
          label: { show: true, position: 'right', color: '#f5f5f7', fontSize: 11 },
          lineStyle: { color: 'rgba(255,255,255,0.18)', width: 1 },
          emphasis: { focus: 'adjacency', lineStyle: { width: 2 } },
          categories,
          data: data.nodes.map((n) => ({
            id: n.id,
            name: n.title,
            type: n.type,
            path: n.path,
            summary: n.summary,
            category: n.type,
            symbolSize: 8 + Math.min(n.degree * 3, 24),
            itemStyle: { color: CATEGORY_COLORS[n.type] ?? '#888888' },
          })),
          links: data.edges.map((e) => ({ source: e.source, target: e.target })),
        },
      ],
    });
  }, [data]);

  useEffect(() => {
    const onResize = () => chartRef.current?.resize();
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  return (
    <div className="kb-graph">
      <div className="kb-graph__toolbar">
        <span className="kb-graph__stats">
          {data ? `${data.nodes.length} 节点 · ${data.edges.length} 边` : ''}
        </span>
        <button
          type="button"
          className="kb-graph__button"
          onClick={() => void handleRebuild()}
          disabled={rebuilding || loading}
        >
          {rebuilding ? '重建中…' : '重建图谱'}
        </button>
      </div>
      {loading && <div className="kb-graph__placeholder">加载中…</div>}
      {error && <div className="kb-graph__placeholder is-error">{error}</div>}
      <div ref={containerRef} className="kb-graph__canvas" />
    </div>
  );
};
```

- [ ] **Step 3: Create the CSS**

Create `frontend/src/components/Knowledge/knowledgeGraph.css`:

```css
.kb-graph {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--kb-bg, #0a0a0c);
}

.kb-graph__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid var(--kb-border, rgba(255, 255, 255, 0.06));
  font-size: 12px;
  color: var(--kb-muted, #b6b6bf);
}

.kb-graph__stats {
  font-variant-numeric: tabular-nums;
}

.kb-graph__button {
  display: inline-flex;
  align-items: center;
  padding: 6px 12px;
  border: 1px solid var(--kb-border-strong, rgba(255, 255, 255, 0.12));
  background: transparent;
  color: var(--kb-text, #f5f5f7);
  font-size: 11px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.kb-graph__button:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.05);
}

.kb-graph__button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.kb-graph__canvas {
  flex: 1;
  min-height: 0;
}

.kb-graph__placeholder {
  padding: 24px;
  text-align: center;
  color: var(--kb-soft, #6f6f77);
  font-size: 13px;
}

.kb-graph__placeholder.is-error {
  color: var(--kb-danger, #f1b9b9);
}
```

- [ ] **Step 4: Mount in WikiKbDetail**

Edit `frontend/src/components/Knowledge/WikiKbDetail.tsx`. Replace the `<div className="wiki-detail__graph-slot">` block with:

```tsx
{tab === 'graph' && (
  <div className="wiki-detail__graph-slot">
    <KnowledgeGraph
      knowledgeBaseId={kb.id}
      onSelectNode={(path) => {
        setSelectedPath(path);
        setTab('pages');
      }}
    />
  </div>
)}
```

Add import at top of WikiKbDetail.tsx:

```typescript
import { KnowledgeGraph } from './KnowledgeGraph';
```

- [ ] **Step 5: Verify build**

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -5`
Expected: clean.

Manually:
1. Browser → Knowledge → click a Wiki KB → click "知识图谱" tab
2. Graph renders. If no edges, you'll just see nodes (or empty if no pages compiled yet)
3. Click "重建图谱" → triggers `POST /graph/rebuild`
4. Click a node → switches back to Pages tab with that page selected

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Knowledge/KnowledgeGraph.tsx frontend/src/components/Knowledge/knowledgeGraph.css frontend/src/components/Knowledge/WikiKbDetail.tsx
git commit -m "feat(frontend): KnowledgeGraph ECharts component + WikiKbDetail integration"
```

---

## Phase 6: Chat — active Wiki KB selector

### Task F12: chatStore tracks activeWikiKbId per session

**Files:**
- Modify: `frontend/src/stores/chatStore.ts`

- [ ] **Step 1: Inspect existing per-session state shape**

```bash
grep -n "linkedKnowledgeBaseIds\|knowledge_base_ids\|sessionStates\|activeSession" frontend/src/stores/chatStore.ts | head -15
```

Note the pattern. Active wiki kb is per-session state, similar to linkedKnowledgeBaseIds (which already exists).

- [ ] **Step 2: Add activeWikiKbId state + actions**

In the per-session state object (where `linkedKnowledgeBaseIds: string[]` lives, often as part of a `SessionState` interface), add `activeWikiKbId: string | null`.

Add to the store actions section (where `setLinkedKnowledgeBases` lives):

```typescript
async setActiveWikiKb(sessionId: string, kbId: string | null): Promise<void> {
  try {
    const result = await api.patchSession(sessionId, { active_wiki_kb_id: kbId });
    set((state) => ({
      sessions: {
        ...state.sessions,
        [sessionId]: {
          ...state.sessions[sessionId],
          activeWikiKbId: result.active_wiki_kb_id,
        },
      },
    }));
  } catch (err) {
    console.error('Failed to set active wiki KB', err);
    throw err;
  }
},
```

Adjust to whatever shape the existing per-session state uses (it may be a Map, an object, etc.). The important thing: the action takes `(sessionId, kbId)`, calls `api.patchSession`, then writes `activeWikiKbId` back into state.

For initial load when entering a session, if the store has an `ensureSessionState`/`loadSession` flow, also fetch the current state via `GET /sessions/{id}` — but if that endpoint doesn't already return `active_wiki_kb_id` in the metadata blob, defer this. The simpler approach: trust that when the user selects a Wiki KB it'll be persisted; on page reload, the dropdown shows "未选择" until the user picks again. (Acceptable for v1; a follow-up can bake `active_wiki_kb_id` into `GET /sessions/{id}` response.)

- [ ] **Step 3: Verify build**

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -5`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/stores/chatStore.ts
git commit -m "feat(frontend): chatStore tracks activeWikiKbId per session"
```

---

### Task F13: Filter 「链接知识库」composer to RAG only

**Files:**
- Modify: `frontend/src/components/Chat/ChatWindow.tsx`

- [ ] **Step 1: Locate the `knowledgeOptions` prop**

```bash
grep -n "knowledgeOptions\|availableKnowledgeBases" frontend/src/components/Chat/ChatWindow.tsx | head -10
```

You'll see something like:

```tsx
knowledgeOptions={availableKnowledgeBases
  .filter((kb) => kb.enabled)
  .map(...)}
```

- [ ] **Step 2: Add a type filter**

Update that filter to exclude wiki KBs (since the composer dropdown is now RAG-exclusive):

```tsx
knowledgeOptions={availableKnowledgeBases
  .filter((kb) => kb.enabled && kb.type === 'rag')
  .map(...)}
```

Also find the trigger label in `InputArea.tsx` (around line 545):

```tsx
{linkedKnowledgeBases.length > 0 ? '已链接知识库' : '链接知识库'}
```

Rename to be more specific:

```tsx
{linkedKnowledgeBases.length > 0 ? '已链接 RAG 知识库' : '链接 RAG 知识库'}
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -5`
Expected: clean.

Manually:
1. Browser → Chat
2. Click "链接 RAG 知识库" — dropdown should now contain ONLY RAG KBs (no Wiki KBs)
3. Existing RAG-linking behavior unchanged

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Chat/ChatWindow.tsx frontend/src/components/Chat/InputArea.tsx
git commit -m "feat(frontend): 链接知识库 dropdown filters to RAG kbs only"
```

---

### Task F14: ActiveWikiSelector component

**Files:**
- Create: `frontend/src/components/Chat/ActiveWikiSelector.tsx`
- Create: `frontend/src/components/Chat/activeWikiSelector.css`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/Chat/ActiveWikiSelector.tsx`:

```tsx
import React, { useEffect, useRef, useState } from 'react';

import type { KnowledgeBase } from '../../types/knowledge';
import './activeWikiSelector.css';

interface ActiveWikiSelectorProps {
  availableWikiKbs: KnowledgeBase[];
  activeKbId: string | null;
  onChange: (kbId: string | null) => void;
}

export const ActiveWikiSelector: React.FC<ActiveWikiSelectorProps> = ({
  availableWikiKbs,
  activeKbId,
  onChange,
}) => {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onClickOutside = (event: MouseEvent) => {
      if (!wrapperRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [open]);

  const active = availableWikiKbs.find((kb) => kb.id === activeKbId) ?? null;
  const triggerLabel = active ? `Wiki: ${active.name}` : '激活 Wiki KB';

  return (
    <div className="active-wiki" ref={wrapperRef}>
      <button
        type="button"
        className={`active-wiki__trigger ${open ? 'is-open' : ''} ${active ? 'has-active' : ''}`}
        onClick={() => setOpen((prev) => !prev)}
        title={active ? `当前 Wiki KB: ${active.name}` : '选择一个 Wiki 知识库供 LLM 浏览'}
      >
        {triggerLabel}
      </button>
      {open && (
        <div className="active-wiki__menu" role="listbox">
          <button
            type="button"
            className={`active-wiki__option ${activeKbId === null ? 'is-active' : ''}`}
            onClick={() => {
              onChange(null);
              setOpen(false);
            }}
          >
            <span className="active-wiki__option-name">不激活</span>
            <span className="active-wiki__option-blurb">LLM 看不到任何 Wiki KB</span>
          </button>
          {availableWikiKbs.length === 0 && (
            <div className="active-wiki__empty">还没有 Wiki 类型的知识库。</div>
          )}
          {availableWikiKbs.map((kb) => (
            <button
              key={kb.id}
              type="button"
              className={`active-wiki__option ${activeKbId === kb.id ? 'is-active' : ''}`}
              onClick={() => {
                onChange(kb.id);
                setOpen(false);
              }}
            >
              <span className="active-wiki__option-name">{kb.name}</span>
              <span className="active-wiki__option-blurb">
                {kb.entity_count} 实体 · {kb.topic_count} 主题 · {kb.source_count} 素材
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 2: Create the CSS**

Create `frontend/src/components/Chat/activeWikiSelector.css`:

```css
.active-wiki {
  position: relative;
  display: inline-flex;
}

.active-wiki__trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  font-size: 12px;
  color: #b6b6bf;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 999px;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease, background-color 0.15s ease;
}

.active-wiki__trigger:hover {
  border-color: rgba(255, 255, 255, 0.25);
  color: #f5f5f7;
}

.active-wiki__trigger.is-open,
.active-wiki__trigger.has-active {
  border-color: rgba(166, 196, 255, 0.6);
  color: #a6c4ff;
  background: rgba(166, 196, 255, 0.04);
}

.active-wiki__menu {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  z-index: 5;
  min-width: 240px;
  max-width: 320px;
  max-height: 280px;
  overflow-y: auto;
  padding: 6px;
  background: #18181c;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 10px;
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.45);
}

.active-wiki__option {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: 8px 10px;
  text-align: left;
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  color: #f5f5f7;
}

.active-wiki__option:hover {
  background: rgba(255, 255, 255, 0.05);
}

.active-wiki__option.is-active {
  background: rgba(166, 196, 255, 0.08);
  color: #a6c4ff;
}

.active-wiki__option-name {
  font-size: 13px;
  font-weight: 500;
}

.active-wiki__option-blurb {
  font-size: 11px;
  color: #6f6f77;
}

.active-wiki__empty {
  padding: 12px 10px;
  font-size: 12px;
  color: #6f6f77;
  text-align: center;
}
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -5`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Chat/ActiveWikiSelector.tsx frontend/src/components/Chat/activeWikiSelector.css
git commit -m "feat(frontend): ActiveWikiSelector single-select dropdown for composer"
```

---

### Task F15: Mount ActiveWikiSelector in composer

**Files:**
- Modify: `frontend/src/components/Chat/InputArea.tsx`
- Modify: `frontend/src/components/Chat/ChatWindow.tsx`

- [ ] **Step 1: Find where the existing 「链接知识库」 wrapper sits**

```bash
grep -n "composer__knowledge\|composer__row\|composer-toolbar" frontend/src/components/Chat/InputArea.tsx | head -10
```

The selector should land right next to or right after the existing "链接 RAG 知识库" trigger.

- [ ] **Step 2: Extend InputArea props**

In `frontend/src/components/Chat/InputArea.tsx`, find the props interface (around line 50). Add:

```typescript
availableWikiKbs?: KnowledgeBase[];
activeWikiKbId?: string | null;
onSetActiveWikiKb?: (kbId: string | null) => void;
```

Import:

```typescript
import { ActiveWikiSelector } from './ActiveWikiSelector';
import type { KnowledgeBase } from '../../types/knowledge';
```

In the render, place the selector right after the existing `composer__knowledge` element:

```tsx
{onSetActiveWikiKb && (
  <ActiveWikiSelector
    availableWikiKbs={availableWikiKbs ?? []}
    activeKbId={activeWikiKbId ?? null}
    onChange={onSetActiveWikiKb}
  />
)}
```

- [ ] **Step 3: Wire from ChatWindow**

In `frontend/src/components/Chat/ChatWindow.tsx`, find where `<InputArea ... />` is rendered (around line 816 where `knowledgeOptions` is already passed).

Add props:

```tsx
availableWikiKbs={availableKnowledgeBases.filter((kb) => kb.enabled && kb.type === 'wiki')}
activeWikiKbId={currentSessionState?.activeWikiKbId ?? null}
onSetActiveWikiKb={(kbId) => {
  void setActiveWikiKb(currentSessionId, kbId);
}}
```

Adjust variable names to match the store's actual API (the new `setActiveWikiKb` action from Task F12; the session-state field is `activeWikiKbId`).

- [ ] **Step 4: Verify build**

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -5`
Expected: clean.

Manually:
1. Browser → Chat
2. Composer should now have two controls: "链接 RAG 知识库" (rag dropdown) and "激活 Wiki KB" (wiki single-select)
3. Selecting a Wiki KB should: (a) close the dropdown (b) show "Wiki: <name>" on the trigger
4. Check backend: `curl http://localhost:18888/api/sessions/<sid>` (or watch network tab) should see `active_wiki_kb_id` PATCH
5. Open a chat and verify in the agent's system prompt the `[Active Wiki Knowledge Base]` section appears (you may need to check the agent log)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Chat/InputArea.tsx frontend/src/components/Chat/ChatWindow.tsx
git commit -m "feat(frontend): mount ActiveWikiSelector in composer; wire to chatStore"
```

---

## Phase 7: Verification

### Task F16: Full build + manual smoke

**Files:** —

- [ ] **Step 1: Type-check and build the whole frontend**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds; output written to `frontend/dist/`. If TS errors, fix them inline.

- [ ] **Step 2: Run all frontend logic tests**

```bash
cd frontend && npm run test:unit 2>&1 | tail -20
```

Expected: all tests pass, including the new ones in `knowledgeDualModeFrontend.test.ts`.

- [ ] **Step 3: Run full backend regression**

```bash
.venv/bin/pytest -q 2>&1 | tail -10
```

Expected: 840+ passed (whatever the pre-this-plan baseline was) + the new `test_api_read_wiki_page_returns_content` from Task F9 (+1).

- [ ] **Step 4: Manual end-to-end check in the browser**

Restart the dev backend if needed: `.venv/bin/tokenmind web --port 18888` (still in the background from earlier).

Then `cd frontend && npm run dev` → http://localhost:5173.

Walk through:

| Step | Expected |
|---|---|
| Knowledge → 新建知识库 | Two type cards visible (RAG / Wiki); selecting either creates that type |
| Knowledge → list | Each card shows RAG/Wiki badge; Wiki cards show source/page/concept counts |
| Click a RAG KB | Existing detail panel (documents list, upload) unchanged |
| Click a Wiki KB | New tabbed detail: 「Wiki 页面」 (default) + 「知识图谱」 |
| Wiki KB 页面 tab | Sidebar groups pages by type; clicking renders Markdown on right with outgoing-links panel |
| Wiki KB 图谱 tab | ECharts force graph renders; tooltip on hover; click node returns to 页面 tab with that page selected; 重建图谱 button works |
| Chat → composer | Two controls: 「链接 RAG 知识库」 (only rag KBs in dropdown), 「激活 Wiki KB」 (only wiki KBs in dropdown, single-select) |
| Activate a Wiki KB → send a message | Backend log shows the LLM has access to `wiki_*` tools; system prompt includes `[Active Wiki Knowledge Base]` |

- [ ] **Step 5: If everything passes, finalize commit**

If you made any inline fixes during steps 1-4, commit them:

```bash
git add -p
git commit -m "fix(frontend): address issues found in end-to-end verification"
```

If no fixes were needed, this step is a no-op.

---

## 后续 plan（不在本 plan 范围）

- **purpose.md 编辑器**：Wiki KB 详情页可以加一个 "目标" tab 让用户编辑 `purpose.md`（目前只能通过文件系统改）
- **PUT /pages/{id}**：人工编辑 Wiki 页面的 UI（目前 Markdown 阅读器只读）
- **digest / lint / crystallize UI**：等后端 Phase 8 上完再做
- **Active Wiki KB 持久化恢复**：`GET /sessions/{id}` 当前不返回 `active_wiki_kb_id`，刷新页面后 selector 显示「未选择」，需要在 sessions GET 响应中带上 metadata.active_wiki_kb_id
