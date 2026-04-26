# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**TokenMind** is a local-first AI agent framework with multi-model, multi-channel, and tool execution capabilities. It consists of three parts: a Python backend (agent runtime, API, knowledge base, memory), a React frontend (Web UI), and a Node.js bridge (WhatsApp).

The public CLI entry point is `tokenmind`. Config lives at `~/.tokenmind/config.json`.

## Common Commands

```bash
# Install & run
pip install -e ".[dev]"
tokenmind onboard          # setup wizard
tokenmind web --port 18888  # start FastAPI + Web UI
tokenmind agent            # headless CLI agent mode
tokenmind gateway          # channel gateway

# Backend checks
pytest                     # all tests (asyncio_mode=auto)
pytest tests/test_foo.py   # single test file
pytest -k "test_name"      # single test by name
ruff check tokenmind/      # lint
ruff format tokenmind/     # format

# Frontend
cd frontend && npm install && npm run dev   # dev server at :5173
cd frontend && npm run build                # production build

# Bridge (WhatsApp)
cd bridge && npm install && npm run build
```

## Architecture

Core data flow: `Channel/WebUI → MessageBus → AgentLoop → Provider + Tools → Session/Memory/Knowledge → WebSocket/Channel output`

### Message Bus (`tokenmind/bus/`)

- `MessageBus` uses two `asyncio.Queue`s: `inbound` (channel→agent) and `outbound` (agent→channel)
- `InboundMessage.session_key` = `"channel:chat_id"` (or explicit override)
- `OutboundMessage.metadata` carries UI signals: `_progress`, `_tool_start`, `_tool_end`, `_approval_required`, `_citations`

### Agent Loop (`tokenmind/agent/loop.py`)

- `AgentLoop.run()` consumes from the inbound queue, dispatches per-session with async locks
- `_run_agent_loop()` iterates up to `max_tool_iterations` (default 40) calling the LLM and executing tool calls
- Tool approval flow: high-risk `exec` calls go through `_request_tool_approval()` → user approval via WebSocket → `_handle_tool_approval()`
- Memory consolidation runs as a background task after message processing

### Context Builder (`tokenmind/agent/context.py`)

- `ContextBuilder.build_system_prompt()` assembles: identity, bootstrap files (`AGENTS.md`, `SOUL.md`, `USER.md`, `TOOLS.md` from workspace), memory context, skills
- `build_messages()` returns sanitized history + runtime metadata + knowledge context + attachments
- Inline images are base64-encoded into user message content blocks

### Providers (`tokenmind/providers/`)

- `ProviderSpec` (frozen dataclass in `registry.py`) defines 21 providers with routing metadata: `backend` (openai_compat / anthropic / azure_openai / openai_codex), `is_gateway`, `is_local`, `detect_by_key_prefix`
- `LLMProvider` (abstract base in `base.py`): `chat()` and `chat_with_retry()` with exponential backoff
- `LLMResponse` returns: `content`, `tool_calls`, `finish_reason`, `usage`, `reasoning_content`, `thinking_blocks`
- Adding a provider: add `ProviderSpec` to `registry.py`, add field to `ProvidersConfig` in `config/schema.py`

### Tool System (`tokenmind/agent/tools/`)

- `ToolRegistry`: register/unregister/execute tools, `get_definitions()` returns OpenAI-format schemas
- `Tool` (abstract base in `base.py`): override `name`, `description`, `parameters`, `execute()`
- Built-in tools: `exec`, `read_file`, `write_file`, `edit_file`, `list_dir`, `web_search`, `web_fetch`, `message`, `deliver_attachment`, `spawn` (subagent), `cron`
- MCP tools (`tools/mcp.py`): auto-registered as `mcp_<server>_<tool>`, supports stdio/SSE/streamable HTTP transports

### Channels (`tokenmind/channels/`)

- `BaseChannel` (abstract): `start()`, `stop()`, `send(OutboundMessage)`, `_handle_message()`
- Implementations: telegram, discord, slack, email, dingtalk, feishu, matrix, wecom, qq, mochat, whatsapp
- Adding a channel: implement `BaseChannel`, register with channel manager

### Sessions (`tokenmind/session/manager.py`)

- `Session.messages` is append-only, persisted to JSONL in `workspace/sessions/`
- `get_history(max_messages=500)` returns unconsolidated messages, aligned to legal tool-call boundaries via `_find_legal_start()`
- Sessions track: `metadata` (title, project_id), `timeline_events` (tool execution), `last_consolidated` (memory archive offset)

### Memory (`tokenmind/agent/memory.py`)

- Two-layer: `MEMORY.md` (long-term facts, editable) + `HISTORY.md` (timestamped log, append-only)
- `MemoryConsolidator` triggers by token threshold, calls LLM with `save_memory` tool, falls back to raw archiving

### Knowledge Base (`tokenmind/knowledge/`)

- `KnowledgeService`: vector backends (qdrant default, sqlite fallback)
- Flow: `add_document()` → async `process_document()` (chunk → embed → store) → `retrieve_for_session()` (hybrid retrieval with rerank)
- Supported formats: pdf, docx, pptx, xlsx, md, txt, images

### Skills (`tokenmind/skills/`)

- Each skill is a directory with `SKILL.md` (markdown + YAML frontmatter with `tokenmind` metadata)
- `SkillsLoader` in `agent/skills.py`: scans workspace + builtin skills, checks requirements (bins, env vars)
- Always-on skills are injected into context; others appear in skills summary

### Projects (`tokenmind/projects/`)

- `ProjectStore`: JSON-file-backed CRUD for project workspaces (`workspace/projects/projects.json`)
- Sessions are scoped to projects via `session.metadata["project_id"]`; global session list excludes project sessions
- Routes: `/api/projects/*` (list, create, rename, delete, detail with filtered sessions)

### Attachments (`tokenmind/server/attachments.py`)

- `AttachmentStore`: manages file lifecycle (temporary → saved/expired) with JSON index
- Three sources: local file copy, remote URL download, inline content (base64/text)
- `DeliverAttachmentTool` (`agent/tools/deliver_attachment.py`): lets the agent push files to users in web chat
- Cleanup runs periodically, deleting expired temporary files; retained files are preserved
- Upload policy configurable: `max_file_mb`, `retention_days`

### Server (`tokenmind/server/app.py`)

- FastAPI with routers: `/api/chat/*`, `/api/config/*`, `/api/knowledge/*`, `/api/memory`, `/api/cron/*`, `/api/sessions/*`, `/api/projects/*`, `/api/storage/*`, `/api/status`
- WebSocket at `/ws/{session_key}` via `ConnectionManager`
- `WebChannel` bridges WebSocket ↔ MessageBus
- Serves frontend SPA from bundled `webui/` (via `hatch_build.py` build hook) or `frontend/dist/` with HTML5 history fallback

### Frontend (`frontend/`)

- React 18 + TypeScript + Vite + Zustand (state management)
- Key stores: `chatStore.ts` (sessions, messages, timeline, projects), `settingsStore.ts` (provider/model config), `knowledgeStore.ts`
- Project UI: `components/Projects/` (create, move session, confirm modals, sidebar state)
- Overlay system: `components/Overlay/` (portal + host for modals)
- WebSocket client for real-time streaming and tool timeline events

## Configuration (`tokenmind/config/schema.py`)

All Pydantic models with camelCase/snake_case alias support. Key sections:

- `AgentDefaults`: model (default `anthropic/claude-opus-4-5`), provider ("auto"), workspace, max_tokens, context_window_tokens, reasoning_effort
- `ProvidersConfig`: per-provider api_key, api_base, extra_headers, default_model
- `ToolsConfig`: exec (confirm_high_risk, approval_timeout_s), uploads (max_file_mb, retention_days), knowledge (vector_backend, chunk_size), mcp_servers
- `MCPServerConfig`: type (auto-detected), command/args/env (stdio), url/headers (HTTP), tool_timeout, enabled_tools

## Testing

- Framework: pytest with `asyncio_mode = "auto"`
- ~81 test files in `tests/` covering providers, channels, tools, knowledge, sessions, config, projects, attachments, and features
- Frontend tests in `frontend/tests/` (pure logic tests, no DOM runner)
- Tests import mocks/fixtures independently (no shared conftest.py)

## Build & Packaging

- `hatch_build.py`: custom Hatchling build hook that bundles `frontend/dist/` into `webui/` inside the wheel
- PyPI readme uses `README_PYPI.md` (not `README.md`)
- Docker: base `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` with Node.js 20, exposes port 18790, config at `/root/.tokenmind`
