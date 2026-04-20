# TokenMind AI Web Attachments Design

## Summary

This spec adds full assistant-generated attachment support to the TokenMind Web UI.

Today the web chat surface supports user uploads into a conversation, but it does not support the reverse direction: the assistant cannot return images, files, or generated downloadable artifacts back into the chat transcript as first-class attachments.

The target capability is a complete web-native attachment flow:

1. the assistant can return attachments from local files, remote URLs, or inline generated content
2. those attachments appear directly on the assistant message in the chat UI
3. attachments are temporarily stored by default
4. the user can download or retain an attachment
5. retained attachments are promoted from temporary storage into persistent workspace storage
6. message history keeps attachment references so refresh and reload still show attachment cards
7. expired temporary attachments remain visible in history, but become unavailable for download

## Goals

- Let assistant replies include first-class image and file attachments in the Web UI
- Support three assistant attachment sources:
  - local file paths
  - remote URLs
  - inline content written into a generated file
- Keep temporary assistant attachments under the same cleanup policy family as current upload storage
- Preserve attachment cards in chat history after refresh and reload
- Let users explicitly retain assistant attachments to promote them into persistent storage
- Keep the user experience close to ChatGPT-style file and image cards attached to an assistant message

## Non-Goals

- Do not build a standalone artifact center or results dashboard
- Do not add attachment version history
- Do not add resumable upload or large-file transfer infrastructure
- Do not redesign the existing user-upload flow beyond what is needed to unify attachment handling
- Do not add long-lived external URL passthrough; all assistant-returned attachments should be normalized into workspace-managed files
- Do not change non-web channels in this iteration except for compatibility bridges where needed

## Problem Statement

The current web chat path already supports:

- user uploads into chat
- assistant text replies
- attachment rendering on messages when `message.attachments` exists

But the actual web outbound pipeline does not attach files to assistant replies.

Specifically:

- the frontend `MessageBubble` can render `message.attachments`
- the websocket schema allows attachments on outbound user messages
- the web channel sends assistant replies as text-only `response_*` websocket events
- the `message` tool supports `media`, but the web channel does not forward that media as web attachments

This means assistant-generated outputs such as reports, CSVs, images, markdown exports, or downloaded remote assets cannot appear as downloadable or previewable artifacts in the web transcript.

## Product Direction

Assistant attachments should behave like message-bound artifacts, not like detached system logs.

The user should experience them as part of a normal assistant reply:

- the assistant answers in text
- the same assistant turn can include zero or more attachment cards
- images preview inline
- files render as downloadable cards
- temporary attachments are marked as temporary
- retained attachments are marked as saved
- expired temporary attachments remain visible in history with a clear unavailable state

This keeps the chat experience coherent and avoids fragmenting one assistant turn into multiple system-style messages.

## Supported Attachment Sources

Assistant-generated attachments will support these source types:

### Local File

The assistant or a tool returns a local path to a file produced inside allowed workspace-controlled directories.

Examples:

- generated PNG chart
- exported markdown report
- CSV summary file
- generated source file

### Remote URL

The assistant or a tool returns a remote URL to an image or file.

The backend must download and normalize the resource into workspace-managed storage before exposing it to the frontend. The frontend should never depend on a raw assistant-provided external URL for durable transcript rendering.

### Inline Generated Content

The assistant or a tool returns structured content that should be turned into a file.

Examples:

- markdown text -> `.md`
- CSV text -> `.csv`
- JSON text -> `.json`
- source code -> `.py`, `.ts`, `.js`

The backend writes this content into a real file in temporary attachment storage, then exposes it as an attachment.

## Storage Model

Assistant attachment storage follows the same cleanup-policy family as existing web uploads, but it is separated structurally so temporary and retained assistant artifacts remain tractable.

### Temporary Attachments

Store temporary assistant attachments under a dedicated assistant subtree:

- `workspace/uploads/web/<session>/assistant/temp/<attachment_id>/...`

### Retained Attachments

When the user retains an attachment, promote it into:

- `workspace/uploads/web/<session>/assistant/saved/<attachment_id>/...`

This keeps retained artifacts in the workspace and allows long-lived access without depending on the temporary cleanup path.

### Attachment Index

Maintain a workspace-scoped attachment index file:

- `workspace/uploads/web/attachments.json`

This file records attachment metadata and status independently of the message transcript.

## Data Model

Assistant attachments should not be represented only as loose dictionaries hanging off a message.

Use a two-layer model:

1. lightweight message references
2. full attachment records in a workspace index

### MessageAttachmentRef

Each stored message keeps a lightweight attachment reference list.

Required fields:

- `id`
- `name`
- `category`
- `is_image`
- `origin`
- `status`

Optional display fields:

- `mime_type`
- `size`

This keeps history payloads compact while still allowing the UI to render stable attachment cards.

### AttachmentRecord

The attachment index stores the mutable source-of-truth record.

Required fields:

- `id`
- `session_id`
- `message_id` or another stable per-message anchor chosen during implementation
- `owner_role`
- `origin`
- `status`
- `name`
- `mime_type`
- `size`
- `is_image`
- `storage_path`
- `created_at`
- `expires_at`

Optional fields:

- `source_url`
- `retained_at`
- `preview_text`
- `error`

### Enumerations

`origin` values:

- `user_upload`
- `assistant_local`
- `assistant_remote`
- `assistant_generated`

`status` values:

- `temporary`
- `saved`
- `expired`

## Message Persistence Rules

Assistant messages should persist attachment references alongside content in the normal chat history.

This means:

- the message transcript continues to be the canonical turn history
- attachments do not disappear from history just because temporary storage expires
- the UI can still show the attachment card after reload
- expired attachments remain visible but unavailable

The full mutable attachment state stays in the attachment index, not in the message body.

## Cleanup Behavior

Temporary assistant attachments should follow the same retention philosophy as the current upload cleanup policy.

Behavior:

- temporary assistant attachments are eligible for cleanup under the configured retention window
- cleanup deletes the physical file
- cleanup updates the corresponding attachment record from `temporary` to `expired`
- expired attachments remain referenced by history messages
- retained attachments are excluded from temporary cleanup

This matches the approved behavior:

- temporary first
- explicit user retention promotes to permanent
- message history remains intact even after the file expires

## Backend Architecture

### Attachment Service

Introduce a backend attachment service dedicated to normalization, storage, retrieval, retention, and cleanup.

Responsibilities:

- normalize local files, remote URLs, and inline content into workspace-managed files
- create and persist `AttachmentRecord`
- return `MessageAttachmentRef` values for transcript storage
- resolve download and preview requests
- promote temporary attachments into retained storage
- expire stale temporary attachments

This service should sit next to the current upload-related logic in the web backend and share as much storage-policy infrastructure as possible.

## Web Chat Flow

The assistant reply flow should remain text-first and streaming-friendly.

Recommended behavior:

1. `response_start` begins the assistant turn
2. `response_delta` streams text only
3. any assistant-generated attachments are fully materialized server-side before the final event
4. `response_end` includes:
   - `content`
   - `citations`
   - `attachments`

Do not emit attachments as detached system messages unless a future product decision explicitly changes the UX.

## WebSocket Schema Changes

Extend assistant response events to allow attachments on final responses.

Required additions:

- `response` may include `attachments`
- `response_end` may include `attachments`

No change is needed for user outbound websocket messages beyond existing attachment support.

## HTTP Endpoints

Add assistant-attachment endpoints for the web client:

### `GET /api/chat/attachments/{attachment_id}`

Purpose:

- preview image attachments
- download file attachments
- return 404 or 410-style response for expired or missing files

### `POST /api/chat/attachments/{attachment_id}/retain`

Purpose:

- promote attachment state from `temporary` to `saved`
- move or reclassify backing storage
- return updated attachment metadata

No separate download endpoint is required if `GET` is implemented cleanly.

## Assistant Tooling

The assistant should not handcraft frontend attachment payloads.

Introduce a dedicated tool, recommended name:

- `deliver_attachment`

Supported modes:

- `local_file`
- `remote_url`
- `inline_content`

The tool returns a structured attachment result to the agent runtime, which is then merged into the final assistant reply as message-bound attachments.

This is preferable to overloading the current `message(media=...)` path for the web channel.

## Compatibility with Existing Message Tool

The existing `message` tool already supports `media` for non-web channels.

Compatibility strategy:

- keep `message` behavior unchanged for channels that already consume `media`
- prefer `deliver_attachment` for the web experience
- optionally bridge `message(media=...)` into web attachments as a compatibility adapter if the active channel is `web`

This avoids breaking other channels while still creating a clean first-class web attachment pipeline.

## Security Boundaries

Assistant attachment delivery must not become a generic arbitrary-file exfiltration mechanism.

Rules:

- local file delivery is restricted to approved workspace-controlled directories
- arbitrary system paths are rejected
- remote URL fetching stays inside existing network policy boundaries
- inline content generation enforces size limits
- attachment metadata should not leak raw disallowed paths back to the client

## Frontend Experience

Assistant attachment cards appear directly below the assistant message content inside the existing message bubble.

### Image Attachments

Render:

- inline preview thumbnail
- file name
- optional size/type label
- status badge
- actions: `下载`, `保留`

### File Attachments

Render:

- file name
- file category or MIME-derived label
- optional size
- status badge
- actions: `下载`, `保留`

### Expired State

Expired temporary attachments remain visible as cards, but:

- preview is disabled
- download is disabled
- retain is disabled
- the card clearly says the temporary file expired

### Saved State

Retained attachments remain visible with a saved badge and continue to support download.

## History and Refresh Behavior

When history is loaded:

- assistant messages return attachment references
- the frontend renders cards immediately
- attachment actions use the current backend state

This means the transcript stays stable across:

- page refresh
- session switching
- app restart

## Testing Strategy

### Backend Unit Tests

Cover:

- local file normalization
- remote URL download normalization
- inline content file generation
- attachment record creation
- attachment retention promotion
- expiration updates
- invalid path rejection
- oversize inline content rejection

### WebSocket / Response Flow Tests

Cover:

- final assistant response includes attachments
- text streaming still works when attachments are present
- no regressions for pure text replies

### API Tests

Cover:

- `GET /api/chat/attachments/{id}`
- `POST /api/chat/attachments/{id}/retain`
- expired attachment behavior
- retained attachment behavior

### Frontend Tests

Cover:

- image card rendering
- file card rendering
- temporary state
- saved state
- expired state
- retain action UI update
- history rehydration with attachment refs

## Migration and Compatibility

This feature must be backward compatible.

Rules:

- existing messages without attachments continue to render unchanged
- existing user-upload attachments continue to work
- old transcripts remain valid
- new assistant attachment metadata is additive
- no destructive migration of existing session history is required

## Implementation Boundaries

This iteration should stop once the web chat supports:

- assistant-generated image and file attachments
- temporary attachment storage
- retain-to-save promotion
- history persistence and refresh replay
- expiration visibility

Do not add:

- attachment center UI
- artifact search
- attachment versioning
- resumable transfers
- long-term external URL passthrough

## Recommendation

Implement the feature as a unified attachment system with:

- message-level lightweight attachment references
- workspace-level mutable attachment records
- a dedicated attachment service
- a dedicated assistant attachment delivery tool
- final-response websocket attachment delivery

This is the smallest architecture that still cleanly supports:

- temporary versus retained state
- image preview
- file download
- expiry
- transcript persistence
