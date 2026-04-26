# TokenMind AI Web Attachments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add full assistant-generated attachment support to the Web UI so assistant replies can return images and files from local paths, remote URLs, or inline generated content, with temporary storage, download/retain actions, history persistence, and expired-state rendering.

**Architecture:** Extend the existing `ChatService` upload/storage layer with a unified assistant attachment index and normalization service, then thread assistant attachment refs through stored session messages, websocket `response_end`, and frontend message rendering. Preserve backward compatibility with current user-upload messages and session history.

**Tech Stack:** FastAPI, Python dataclasses/helpers, existing workspace/session JSONL persistence, React 18, TypeScript, Zustand, Vite, Node `test`, `tsx`.

---

## File Structure

### Backend

- Create: `tokenmind/server/attachments.py`
- Modify: `tokenmind/server/app.py`
- Modify: `tokenmind/server/routes/chat.py`
- Modify: `tokenmind/server/channel/web.py`
- Modify: `tokenmind/server/websocket/handler.py`
- Modify: `tokenmind/agent/tools/message.py`
- Create: `tokenmind/agent/tools/deliver_attachment.py`
- Modify: `tokenmind/agent/loop.py`
- Modify: `tokenmind/bus/events.py`
- Create: `tests/test_chat_attachments.py`
- Modify: `tests/test_chat_uploads.py`

### Frontend

- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/hooks/useWebSocket.ts`
- Modify: `frontend/src/stores/chatStore.ts`
- Modify: `frontend/src/components/Chat/MessageBubble.tsx`
- Modify: `frontend/src/components/Chat/messageBubble.css`
- Create: `frontend/tests/assistantAttachments.test.ts`

---

### Task 1: Build backend attachment storage/index and cover it with tests

**Files:**
- Create: `tokenmind/server/attachments.py`
- Create: `tests/test_chat_attachments.py`
- Modify: `tokenmind/server/app.py`

- [ ] **Step 1: Write failing backend tests for assistant attachment normalization and retention**

Cover:
- local-file normalization into assistant temp storage
- inline-content generation into a real file
- remote URL normalization using a mocked downloader
- attachment index persistence and lookup
- retain flow promoting `temporary -> saved`
- cleanup expiring temporary assistant attachments without deleting history refs

- [ ] **Step 2: Implement unified assistant attachment helpers**

Create `tokenmind/server/attachments.py` with:
- `MessageAttachmentRef`
- `AttachmentRecord`
- `AttachmentStore`
- helpers for temp/saved assistant paths
- normalization helpers for `local_file`, `remote_url`, `inline_content`

- [ ] **Step 3: Extend `ChatService` to expose assistant attachment operations**

Add methods for:
- creating assistant attachments
- listing/loading attachment records
- resolving a download path safely
- retaining an attachment
- expiring stale temporary assistant attachments during cleanup

- [ ] **Step 4: Run backend tests**

Run:

```powershell
pytest tests/test_chat_attachments.py tests/test_chat_uploads.py -q
```

Expected: PASS.

---

### Task 2: Add attachment download/retain HTTP APIs and history serialization support

**Files:**
- Modify: `tokenmind/server/routes/chat.py`
- Modify: `tokenmind/server/app.py`

- [ ] **Step 1: Add failing API tests**

Cover:
- `GET /api/chat/attachments/{attachment_id}`
- `POST /api/chat/attachments/{attachment_id}/retain`
- expired attachment returns an unavailable error
- retained attachment remains downloadable

- [ ] **Step 2: Implement chat attachment routes**

Add endpoints for:
- download/preview
- retain/promote

Reuse `ChatService` attachment helpers instead of duplicating file logic in the route layer.

- [ ] **Step 3: Verify history responses preserve assistant attachment refs**

Ensure stored messages round-trip attachment refs through `get_history()` without breaking legacy sessions.

- [ ] **Step 4: Run API/backend verification**

Run:

```powershell
pytest tests/test_chat_attachments.py tests/test_chat_uploads.py tests/test_storage_routes.py -q
```

Expected: PASS.

---

### Task 3: Thread assistant attachments through outbound message flow and websocket events

**Files:**
- Modify: `tokenmind/bus/events.py`
- Modify: `tokenmind/server/channel/web.py`
- Modify: `tokenmind/server/websocket/handler.py`
- Modify: `tokenmind/server/app.py`

- [ ] **Step 1: Add failing tests for websocket payload shape and persisted assistant attachments**

Cover:
- assistant reply with attachments sends refs on `response_end`
- websocket `message` inbound remains backward-compatible
- stored assistant messages retain attachment refs in history

- [ ] **Step 2: Extend outbound message metadata/event handling**

Add assistant attachment refs to the outbound web flow, preferring `response_end` only after files have been normalized and indexed.

- [ ] **Step 3: Update `ChatService`/web channel persistence bridge**

When assistant text is finalized:
- persist assistant message with `attachments`
- return/emit refs to the frontend

- [ ] **Step 4: Run focused backend verification**

Run:

```powershell
pytest tests/test_chat_attachments.py -q
```

Expected: PASS.

---

### Task 4: Add frontend attachment cards, actions, and store/websocket support

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/hooks/useWebSocket.ts`
- Modify: `frontend/src/stores/chatStore.ts`
- Modify: `frontend/src/components/Chat/MessageBubble.tsx`
- Modify: `frontend/src/components/Chat/messageBubble.css`
- Create: `frontend/tests/assistantAttachments.test.ts`

- [ ] **Step 1: Write failing frontend tests**

Cover:
- assistant `response_end` attachments get committed to the streaming message
- image/file attachment cards render expected labels and actions
- retain updates attachment status in place
- expired attachments stay visible but disable actions

- [ ] **Step 2: Extend frontend attachment types and API client**

Add:
- attachment `id`, `origin`, `status`, optional download URL or preview metadata
- `retainAttachment()` and `getAttachmentUrl()` helpers

- [ ] **Step 3: Update websocket/store streaming completion flow**

Ensure `finishStreamingAssistant()` accepts attachment refs and stores them on the assistant message finalized by `response_end`.

- [ ] **Step 4: Implement assistant attachment cards**

Render:
- inline image previews
- file cards with metadata
- `下载`
- `保留`
- state labels for `临时 / 已保留 / 已过期`

- [ ] **Step 5: Run frontend verification**

Run:

```powershell
npm run test:unit -- tests/assistantAttachments.test.ts
npm run build
```

Workdir:

```powershell
D:\project\TokenMind\frontend
```

Expected: PASS.

---

### Task 5: Add the assistant-facing delivery tool and final end-to-end verification

**Files:**
- Create: `tokenmind/agent/tools/deliver_attachment.py`
- Modify: `tokenmind/agent/loop.py`
- Modify: `tokenmind/agent/tools/message.py`

- [ ] **Step 1: Add failing tool/integration tests**

Cover:
- tool accepts `local_file`, `remote_url`, `inline_content`
- invalid local paths are rejected
- assistant turn aggregates tool-created attachments onto the final assistant reply

- [ ] **Step 2: Implement `deliver_attachment`**

The tool should:
- validate source input
- call `ChatService`/attachment service normalization
- return lightweight attachment metadata for aggregation

- [ ] **Step 3: Bridge existing `message(media=...)` behavior for web compatibility**

Keep old channels working while allowing web turns to translate media paths into assistant attachment refs when appropriate.

- [ ] **Step 4: Run full verification**

Run:

```powershell
pytest tests/test_chat_attachments.py tests/test_chat_uploads.py -q
npm run test:unit -- tests/assistantAttachments.test.ts
npm run build
python -m compileall tokenmind
```

Expected: PASS.
