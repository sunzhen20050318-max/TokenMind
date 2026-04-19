# TokenMind Project Workspaces Design

## Summary

This spec adds a first-class `项目` capability to `TokenMind`.

The goal is to let users create lightweight project containers, place conversations inside them, and keep those project conversations out of the normal recent-session list.

The interaction model is intentionally simple:

1. users create a project from a modal by entering a project name
2. the app opens that project's home page
3. the project starts empty until the user clicks `新聊天`
4. users can either create brand-new project conversations or move existing normal conversations into a project
5. project conversations are only visible after entering that specific project

This should feel close to ChatGPT's project experience, but still fit `TokenMind`'s current sidebar shell, session model, and workspace-first architecture.

## Goals

- Add a dedicated `项目` entry under `知识库` in the left sidebar
- Let users create a project from a modal with only a project name
- Open a project into a project home view rather than directly into a chat
- Let users create conversations inside a project
- Let users move existing normal conversations into a project
- Hide project conversations from the normal recent conversation list
- Only reveal project conversations after the user enters that specific project
- Preserve the existing chat, session history, and WebSocket flow as much as possible

## Non-Goals

- Do not build nested projects or folders inside projects
- Do not support moving project conversations back to the normal session list in v1
- Do not add project-level permissions, sharing, or multi-user collaboration
- Do not add project-specific knowledge bases, storage partitions, or model settings in v1
- Do not redesign the whole app shell around projects
- Do not change the existing `session_id` scheme

## Product Direction

Projects are a navigation and organization layer on top of the existing session system, not a replacement for sessions.

That means:

- a project is a container with metadata
- each conversation still remains a normal `session`
- a session becomes a project conversation by receiving a `project_id`

This gives the product a clean separation:

- `普通会话` are sessions with no project
- `项目会话` are sessions with a project assignment

The sidebar should present those two worlds differently:

- the regular recent list shows only normal conversations
- the project section shows only project names
- the user must enter a project before seeing its conversations

## Primary User Flows

### Flow 1: Create a project

1. user clicks the `项目` entry or `新项目`
2. a modal opens
3. user enters a project name
4. user confirms creation
5. the app creates the project
6. the app navigates into that project's home page
7. the project is empty until the user clicks `新聊天`

### Flow 2: Create a new conversation inside a project

1. user opens a project
2. the project home page appears
3. user clicks `新聊天`
4. a new session is created with that project's `project_id`
5. the app opens the normal chat view for that new project session
6. that session does not appear in the global recent list

### Flow 3: Move an existing normal conversation into a project

1. user finds an existing normal conversation in the regular session list
2. user opens a `移入项目` action
3. user chooses one of the existing projects
4. the session receives that `project_id`
5. the session disappears from the normal session list
6. the session appears inside the selected project's conversation list

### Flow 4: Browse a project's conversations

1. user expands the `项目` section in the sidebar
2. the dropdown shows project names only
3. user clicks a project
4. the main area opens the project home page
5. the project home page displays conversations belonging only to that project
6. clicking a project conversation opens that chat session

## Sidebar Information Architecture

The left sidebar keeps its current shell and gains one new section below `知识库`.

Recommended order:

1. brand
2. `新建对话`
3. `知识库`
4. `项目`
5. project dropdown content
6. `最近`
7. normal recent conversations
8. `设置中心`

The `项目` section behaves like a collapsible group:

- collapsed: shows only the `项目` label and an affordance to create a project
- expanded: shows a `新项目` action plus the list of existing project names
- expanded state does **not** reveal project conversations

Only the selected project view should reveal project conversations.

## Project Home Page

Opening a project should not immediately jump into a chat.

Instead, the right content area opens a dedicated project home page.

### Header

The top of the page should contain:

- project icon
- project name
- optional short supporting copy
- `新聊天` primary action

### Main Content

The default project surface should show:

- a clear empty state if no project conversations exist yet
- a list of conversations when the project already contains them

The list should feel similar to the screenshot reference:

- conversation title
- recent preview text when available
- updated date

### Empty State

If the project has no conversations yet, show:

- a clean empty state message
- a clear `新聊天` affordance
- copy explaining that conversations created here will belong only to this project

## Conversation Visibility Rules

This behavior is the core of the feature and should be implemented exactly.

### Normal Session List

The existing `/api/sessions`-backed list becomes a list of only sessions where `project_id` is empty.

That means:

- project conversations do not appear in `最近`
- project conversations do not appear in the default session picker
- moving a session into a project removes it from the normal list immediately

### Project Session List

The project-specific session list is visible only when a project is selected.

That means:

- the sidebar dropdown under `项目` shows project names only
- the project home page shows only that project's sessions
- the project chat context should keep the app visibly scoped to the selected project

## Data Model Direction

This feature should add one new top-level entity and extend session metadata minimally.

### Project

Fields:

- `id`
- `name`
- `created_at`
- `updated_at`

### Session Metadata Extension

Existing session JSONL storage remains the same, but session metadata gains:

- `project_id: str | null`

Rules:

- missing or null `project_id` means a normal conversation
- non-null `project_id` means the session belongs to that project

### Storage Location

Projects should be stored separately from sessions, for example:

- `workspace/projects/projects.json`

Sessions remain in the existing `workspace/sessions/*.jsonl` storage.

This avoids overloading session storage with project registry concerns and keeps responsibilities clear.

## Backend Architecture

Projects should be added as a dedicated backend module rather than being hidden inside the existing session manager.

Recommended modules:

- `tokenmind/projects/store.py`
  - project metadata read/write
- `tokenmind/projects/models.py`
  - project DTOs
- `tokenmind/server/routes/projects.py`
  - project API endpoints

Existing components continue to own their current responsibilities:

- `SessionManager` keeps session load/save behavior
- `ChatService` becomes the composition layer that joins project state with session state

## Backend API Surface

### Project Endpoints

- `GET /api/projects`
  - list projects only
  - include per-project conversation count
- `POST /api/projects`
  - create project from `name`
- `GET /api/projects/{project_id}`
  - return project detail plus that project's conversation list
- `PUT /api/projects/{project_id}`
  - rename project
- `POST /api/projects/{project_id}/sessions`
  - create a new project conversation
- `POST /api/projects/{project_id}/sessions/link`
  - move an existing normal session into the project

### Existing Session Endpoints

- `GET /api/sessions`
  - returns only non-project sessions
- `GET /api/chat/history/{session_id}`
  - unchanged
- `POST /api/chat/send`
  - unchanged

This keeps project navigation and chat transport cleanly separated.

## Frontend Architecture

The current frontend should not be replaced. Instead, this feature adds a project-aware shell state around the existing chat view.

Recommended additions to the global app/store state:

- `projects`
- `activeProjectId`
- `projectSessions`
- `currentView`

Suggested view values:

- `chat`
- `knowledge`
- `project-home`
- `project-chat`

### New Components

Recommended new frontend components:

- `CreateProjectModal`
- `ProjectHome`
- `ProjectListSection`
- `MoveSessionToProjectModal` or dropdown picker

### Existing Components to Extend

- `Sidebar`
  - render the new project section
  - render project names only in the dropdown
  - keep recent sessions filtered to normal sessions
- `App`
  - switch between regular chat view and project home view
- `chatStore`
  - hold project state and project-aware session loading
- `api.ts`
  - add project endpoints

## Session Movement Rules

Moving an existing session into a project should obey these rules:

- only normal sessions can be moved in v1
- moving updates that session's `metadata.project_id`
- the session keeps its history, title, attachments, and timeline unchanged
- after the move, the session is removed from the normal session list
- after the move, the session is available inside the destination project

This operation is organizational, not transformative.

## Compatibility and Migration

Migration should be intentionally lightweight.

### Existing Sessions

All old sessions already on disk should continue working without migration.

Interpretation:

- no `project_id` field means the session is a normal session

### New Writes

Only these cases should write `project_id`:

- creating a new conversation from inside a project
- moving an existing normal conversation into a project

### Session IDs

Do not encode project identity into `session_id`.

The existing `session_id` and `session_key` model should remain unchanged.

## Error Handling

The system should handle these cases cleanly:

- creating a project with an empty name
- creating a project with a duplicate name
- linking a session to a project that does not exist
- linking a session that is already inside another project
- opening a deleted or missing project

User-facing behavior should be simple:

- validation errors stay in modal form
- missing project routes redirect back to the project list with an error notice
- link failures should not partially update the UI

## Testing Strategy

### Backend Tests

Add focused tests for:

- creating a project
- listing projects
- fetching a project's detail with its sessions
- filtering the normal session list to exclude project sessions
- creating a project session
- moving an existing normal session into a project
- preserving session history after project assignment

### Frontend Verification

For this iteration, manual product verification is acceptable if automated frontend coverage is not already established.

Required checks:

1. create project from modal
2. enter project home page
3. create new chat inside project
4. confirm that project chat is absent from `最近`
5. move existing normal chat into project
6. confirm it disappears from normal list and appears in the project
7. confirm opening the moved chat still shows the original history

## Rollout Strategy

Implement in this order:

1. backend project store and project routes
2. session filtering by `project_id`
3. create-project modal and project list section in sidebar
4. project home page
5. create new project conversation flow
6. move existing normal conversation into project flow
7. polish empty states and navigation behavior

This order delivers the new information architecture first, then the project-local chat flow, then the migration flow for existing sessions.

## Recommendation

Build projects as a thin organizational layer over the existing session system.

The right v1 is:

- project names in a sidebar dropdown
- project home page in the main area
- project conversations hidden from the global recent list
- explicit creation of project chats
- explicit movement of existing normal chats into a project

Do **not** redesign sessions around projects.
Do **not** expose project conversations globally.
Do **not** overload `session_id` with project semantics.

This keeps the feature aligned with the current `TokenMind` architecture while still delivering the ChatGPT-style project experience the product needs.
