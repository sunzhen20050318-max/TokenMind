# TokenMind Knowledge Base Design

## Summary

This spec adds a first-class `知识库` capability to `TokenMind`.

The knowledge base is **not** a settings subsection and **not** a hidden developer feature. It becomes a new primary workspace entry in the main sidebar, directly under `新建对话`, and opens as a full main-area page.

The design goal is to make knowledge usable in two distinct but connected ways:

1. users can manage knowledge bases as standalone assets
2. users can manually link one or more knowledge bases to a chat session when they want the model to answer using those materials

This should feel like a product-level capability inspired by platforms such as `RAGFlow`, but implemented in a lighter, more user-friendly way that fits `TokenMind`'s personal AI assistant positioning.

## Goals

- Add a dedicated `知识库` entry to the main sidebar
- Make the knowledge base open as a full page in the right content area
- Let users create multiple knowledge bases
- Let each knowledge base contain mixed-format materials
- Make knowledge linking explicit and user-controlled
- Allow multiple knowledge bases to be linked to the same chat session
- Keep the workflow understandable for non-technical users
- Leave room for richer RAG behavior later without overbuilding v1

## Non-Goals

- Do not build a full enterprise RAG platform in v1
- Do not add external sync sources such as Notion, Drive, Confluence, or S3 yet
- Do not add multi-tenant permission systems in v1
- Do not require users to choose a knowledge base before every message
- Do not automatically enable knowledge bases behind the user's back
- Do not move the knowledge base into Settings

## Product Direction

The knowledge base should behave like a workspace inside the app, not like a configuration panel.

That means:

- the left sidebar gains a new primary entry: `知识库`
- clicking it replaces the main content area with a dedicated knowledge page
- the existing sidebar stays visible, just like it does for chat

The interaction model is intentionally split:

- `知识库页面` is for building and maintaining knowledge assets
- `聊天页面` is for deciding whether a given conversation should use one or more of those assets

This keeps the product simple:

- knowledge management happens in one place
- knowledge usage happens in the conversation where it matters

## Primary User Flows

### Flow 1: Create and manage knowledge

1. user clicks `知识库` in the main sidebar
2. the app opens the knowledge base home page
3. user sees all existing knowledge bases plus high-level stats
4. user creates a new knowledge base
5. user enters that knowledge base
6. user uploads files, reviews parsing state, removes files, or rebuilds indexing

### Flow 2: Use knowledge during chat

1. user opens or continues a conversation
2. in the composer area, below the input, they click `链接知识库`
3. a chooser opens with all available knowledge bases
4. the user selects one or more knowledge bases
5. selected knowledge bases appear as removable linked tags
6. from that point forward, the current session may use those linked knowledge bases
7. if the user removes them, the session stops using them

The system does **not** auto-link knowledge by default.

## Sidebar Information Architecture

The main sidebar order becomes:

1. brand
2. `新建对话`
3. `知识库`
4. recent conversations
5. `设置中心`

`知识库` is a primary entry, visually at the same importance tier as the core chat workspace.

It should not visually compete with `新建对话`, but it should be clearly visible and always reachable.

## Knowledge Base Page Structure

The first click into `知识库` should open a page that shows **all knowledge bases first**, not a single empty detail panel.

This overview page is the default landing surface.

### Top Region

The top of the page should contain:

- page title: `知识库`
- short supporting sentence explaining the purpose
- `新建知识库` primary action
- search input for filtering knowledge bases
- optional status filters such as:
  - `全部`
  - `可用`
  - `处理中`
  - `失败`

This area should feel like a clean workspace header, not an admin dashboard toolbar.

### Knowledge Base Overview Content

The main overview should show:

- summary metrics
  - total knowledge bases
  - total documents
  - documents currently processing
  - total linked sessions later if available
- a list or grid of knowledge base cards

Each knowledge base card should include:

- name
- short description
- number of documents
- last updated time
- status
- quick actions:
  - `进入`
  - `上传资料`
  - `删除`

The tone should be advanced but approachable:

- easy to scan
- not table-heavy
- not over-designed

## Single Knowledge Base Detail View

When the user clicks a specific knowledge base, the page switches into that knowledge base's detail workspace.

This detail view should emphasize the actual materials inside the knowledge base.

### Header

The detail header should show:

- knowledge base name
- description
- status
- back action to return to all knowledge bases
- actions such as:
  - `上传资料`
  - `重建索引`
  - `删除知识库`

### Primary Sections

The detail page should include these sections:

1. `资料列表`
2. `处理状态`
3. `检索设置`
4. `测试检索`

### 1. 资料列表

This is the main surface after entering a knowledge base.

It should show the files inside the selected knowledge base.

Each item should display:

- file name
- file type
- size
- upload time
- parse/index status
- chunk count if available later
- actions:
  - `删除`
  - `重新处理` when relevant

The page should clearly support mixed formats inside one knowledge base, including:

- `pdf`
- `docx`
- `pptx`
- `xlsx`
- `csv`
- `md`
- `txt`
- images where extraction is supported

The point is that a single knowledge base is a container of related materials, not a format-specific bucket.

### 2. 处理状态

This section explains whether the materials are ready for use.

It should surface:

- processing
- ready
- failed
- last indexed time

Failures should be understandable at a glance.

### 3. 检索设置

These are scoped to the knowledge base, not to the whole app.

Initial v1 settings:

- chunk size
- chunk overlap
- retrieval top-k
- embedding model
- rerank enabled/disabled if available

This section should stay compact in the first release. Advanced tuning can come later.

### 4. 测试检索

This allows the user to type a sample query and preview what the knowledge base would retrieve.

It should show:

- matching chunks
- source document names
- similarity or ranking hints if available

This makes the knowledge base feel trustworthy before the user uses it in a real conversation.

## Chat Integration

This is the most important interaction rule, and it should be implemented exactly as follows.

### Core Rule

Knowledge bases only affect answers **after the user explicitly links them**.

If the user does nothing, the model behaves as it does today.

### Composer Integration

In the chat composer area, below the input, add a `链接知识库` control.

Clicking it opens a selector panel that lists all available knowledge bases.

The user can:

- search the list
- select one knowledge base
- select multiple knowledge bases
- deselect linked knowledge bases

### Session-Level Persistence

Once linked, the selected knowledge bases remain attached to the current conversation until the user removes them.

This is session-level persistence, but still fully user-driven.

That means:

- not linked by default
- not silently auto-enabled
- continues working across the current chat session
- easy to remove at any time

### Linked Knowledge Display

Selected knowledge bases should appear as lightweight removable tags in the composer area.

Each tag includes:

- name
- remove action

The design should feel similar to currently linked contextual resources rather than big cards.

## Retrieval Behavior

For v1, the conversation layer should use linked knowledge bases like this:

1. user sends a message
2. system checks whether the session has linked knowledge bases
3. if none are linked, normal answer flow continues
4. if one or more are linked:
   - query linked knowledge bases
   - retrieve relevant chunks
   - inject retrieved context into the model prompt
   - generate an answer grounded in those materials

This should later support source citations in the reply, but source-linked answering is the key foundation.

## Data Model Direction

At the product level, we need three core entities:

### Knowledge Base

Fields:

- id
- name
- description
- created_at
- updated_at
- status
- retrieval settings

### Knowledge Document

Fields:

- id
- knowledge_base_id
- file name
- file path
- file type
- file size
- processing status
- created_at
- updated_at

### Session Knowledge Link

Fields:

- session_id
- knowledge_base_id
- linked_at

This keeps management and conversation linkage separate and understandable.

## Backend Requirements

Recommended backend modules:

- `knowledge/service.py`
  - top-level orchestration
- `knowledge/ingest.py`
  - file extraction
- `knowledge/chunking.py`
  - text segmentation
- `knowledge/embed.py`
  - embeddings
- `knowledge/index.py`
  - vector retrieval and storage
- `server/routes/knowledge.py`
  - API routes

Initial API surface should support:

- list knowledge bases
- create knowledge base
- delete knowledge base
- list documents in a knowledge base
- upload documents to a knowledge base
- delete a document from a knowledge base
- query processing status
- test retrieval
- link/unlink knowledge bases to a session
- fetch currently linked knowledge bases for a session

## Frontend Requirements

### Routing / State

The app currently behaves like a shell with one main content area. The knowledge base page should fit that model.

Recommended frontend state:

- active main surface:
  - `chat`
  - `knowledge`
- inside knowledge:
  - overview page
  - selected knowledge base detail page

### UI Components

Likely components:

- `KnowledgePage`
- `KnowledgeOverview`
- `KnowledgeCard`
- `KnowledgeDetail`
- `KnowledgeDocumentList`
- `KnowledgeLinkPicker`
- `LinkedKnowledgeTags`

These should be reusable and not buried inside Settings.

## Empty States

### No knowledge bases yet

Show:

- a clean empty state
- explanation of what a knowledge base is
- a primary `新建知识库` button

### Knowledge base exists but has no documents

Show:

- upload affordance
- examples of supported file types
- explanation that one knowledge base can contain mixed materials

### Linked no knowledge in chat

Show nothing by default, or a subtle idle `链接知识库` affordance only.

Do not imply that knowledge is active when it is not.

## Visual Direction

The page should inherit the current high-end dark UI language already being established in `TokenMind`.

It should feel:

- calmer than a database admin panel
- more practical than a marketing showcase
- more product-like than a raw developer tool

Visual priorities:

- strong hierarchy
- controlled density
- clean card groupings
- obvious primary actions
- clear processing states
- compact but elegant linked-knowledge controls in chat

## Rollout Strategy

Implement in this order:

1. sidebar entry + knowledge overview page shell
2. create knowledge base + list knowledge bases
3. single knowledge base detail page + document upload/list/delete
4. parsing + indexing pipeline
5. chat composer `链接知识库` selector
6. session-level knowledge linking
7. retrieval during chat
8. source display and further polish

This gives us a clean path from visible product shell to actual grounded answering.

## Recommendation

Build this as a dedicated `TokenMind` knowledge workspace with explicit chat linkage.

Do **not** hide it in Settings.
Do **not** auto-enable it.
Do **not** overbuild v1 into a heavy RAG platform.

The right first version is:

- standalone knowledge workspace
- multiple knowledge bases
- multiple mixed-format documents per knowledge base
- explicit multi-select session linking
- grounded retrieval only when the user chooses it

That gives `TokenMind` a strong, understandable knowledge capability without losing the simplicity of the current product.
