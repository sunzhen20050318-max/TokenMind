# Memory Center Design

## Goal

Add a new standalone `记忆中心` entry to the main web UI so users can inspect and manage the agent's memory system without digging into the filesystem or configuration JSON.

The Memory Center should make the current memory model understandable at a glance:

- `长期记忆` for stable facts and preferences
- `当前上下文` for the active session's short-term working context
- `近期归档` for recently consolidated historical snippets
- `记忆设置` for a small, focused set of memory-related controls

This surface should feel like a product feature, not a developer tool.

## Product Direction

The Memory Center will be a standalone modal entry in the left sidebar, parallel to:

- `设置中心`
- `定时任务`
- `文件中心`

It will not live inside Settings. Memory is a first-class system capability, not just another configuration subsection.

The UI direction is content-first, configuration-second:

- the default landing tab is `长期记忆`
- editable long-term memory is the primary surface
- short-term context and archive history are clearly visible but mostly read-only
- settings stay lightweight and do not dominate the experience

## Information Architecture

### Entry

Add a new sidebar action:

- label: `记忆中心`

It opens a dedicated modal, consistent with the existing Settings / Tasks / Storage interaction model.

### Modal Structure

The modal uses a two-column layout:

- left: memory navigation
- right: content panel

Navigation items:

1. `长期记忆`
2. `当前上下文`
3. `近期归档`
4. `记忆设置`

Default selection:

- `长期记忆`

## Section Design

### 1. 长期记忆

Purpose:

- show the current persistent memory the agent carries across conversations

Behavior:

- load and display `workspace/memory/MEMORY.md`
- support direct in-app editing
- support save action
- show metadata such as:
  - last updated time
  - character count
  - whether there are unsaved edits

UX notes:

- this is the primary editing surface
- editor should feel clean and document-like, not like a raw textarea dumped into the page
- save affordance should be obvious and low-friction

### 2. 当前上下文

Purpose:

- show what the active conversation is currently contributing as short-term context

Behavior:

- if there is an active session, show a readable preview of the current session context
- if there is no active session, show an empty state instead of fabricating a temporary one

Content model:

- recent unconsolidated session messages
- ordered in a way that helps users understand what the model still "remembers right now"

Scope:

- read-only in the first version
- this view explains context; it does not let users rewrite chat history

Empty state:

- message indicating that no active session is selected yet
- copy should explain that this section fills in after a conversation starts

### 3. 近期归档

Purpose:

- surface the recent history that has already been moved out of the live prompt context

Behavior:

- read from `workspace/memory/HISTORY.md`
- show the latest archive blocks in reverse chronological order
- include search / filter input for quick scanning

Scope:

- read-only in the first version
- no inline editing of archive blocks

Reason:

- archive history is a system log-like surface
- letting users freely edit it would blur the line between memory and history too much for v1

### 4. 记忆设置

Purpose:

- expose only the most meaningful memory controls, without turning the page into another generic settings form

First-version controls:

- auto consolidation status
- current memory template status
- whether long-term memory is editable in-app
- summary / explanation of the current memory model

Optional future controls:

- consolidation threshold strategy
- template editing
- archive retention behavior

The first release should prefer clarity over configurability.

## Empty and Edge States

### No active session

When the user opens Memory Center before entering any conversation:

- `长期记忆`: still fully available
- `近期归档`: available if archive exists
- `当前上下文`: show explicit empty state

This avoids creating fake session state and keeps system-level memory usable even before chat begins.

### No long-term memory yet

Show an empty-state editor with helpful starter text, not a broken blank panel.

### No archive yet

Show a clean empty state explaining that archived snippets will appear after conversations grow large enough to be consolidated.

## Data Sources

### Long-term memory

- source: `workspace/memory/MEMORY.md`

### Current context

- source: active session's unconsolidated / currently relevant messages from session state

### Recent archive

- source: `workspace/memory/HISTORY.md`

### Memory settings

- source: existing memory/consolidation configuration and template settings where available

## Backend Requirements

Add dedicated API support for the Memory Center rather than making the frontend read raw files directly.

Recommended endpoints:

- `GET /api/memory`
  - returns long-term memory content
  - returns archive preview
  - returns current-context preview for the active session if one is provided
  - returns memory settings summary

- `PUT /api/memory/long-term`
  - updates long-term memory content

- `GET /api/memory/archive`
  - optional separate archive pagination/search endpoint if the combined endpoint grows too large

The backend should stay the source of truth for any path resolution or session-context extraction.

## Frontend Requirements

### Sidebar

- add a new standalone action button for `记忆中心`
- keep visual style aligned with the existing dark, monochrome navigation system

### Modal

- match the app's existing modal language
- maintain generous scale similar to Settings / Storage
- keep scroll behavior stable
- emphasize readability over widget density

### Editor

- long-term memory editor should support:
  - multi-line editing
  - clear save state
  - unsaved-changes feedback

### Search

- archive view should support lightweight search from the start

## Interaction Model

### Saving long-term memory

Flow:

1. user edits memory
2. save button becomes active
3. save request persists content
4. success notice confirms save

### Navigating sections

- section switching should be instant
- unsaved long-term-memory edits should warn before losing local changes

### Current context inspection

- this is explanatory, not editable
- users should understand why content appears here and why older content may move to archive

## Visual Direction

The page should follow the existing product language:

- black / white / gray palette
- restrained contrast
- clean spacing
- minimal chrome
- obvious hierarchy

It should feel like a thoughtful internal systems panel, not a generic admin dashboard and not a file explorer.

## Out of Scope for V1

Do not include these in the first implementation:

- full archive editing
- memory version history / diff viewer
- per-session long-term memory branches
- AI-assisted rewrite tools for memory entries
- drag-and-drop organization

These can come later after the core center proves useful.

## Testing Plan

Backend:

- API returns correct empty states
- long-term memory read/write works
- current-context preview behaves correctly with and without active session
- archive preview is stable

Frontend:

- sidebar entry opens modal
- default tab is `长期记忆`
- long-term memory edits save successfully
- no-session empty state renders correctly in `当前上下文`
- archive search filters visible entries

## Recommendation

Ship the Memory Center as a content-first, standalone modal with:

- editable `长期记忆`
- read-only `当前上下文`
- searchable `近期归档`
- lightweight `记忆设置`

This provides a strong, understandable first version that fits the current product direction and can grow later without requiring a redesign.
