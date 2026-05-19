# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**TokenMind** is a local-first AI agent framework with multi-model, multi-channel, and tool execution capabilities. It consists of three parts: a Python backend (agent runtime, API, knowledge base, memory), a React frontend (Web UI), and a Node.js bridge (WhatsApp).

The public CLI entry point is `tokenmind`. Config lives at `~/.tokenmind/config.json`.

## Common Commands

```bash
# Install & run (Python 3.11+)
pip install -e ".[dev]"
tokenmind onboard          # setup wizard (writes ~/.tokenmind/config.json)
tokenmind web --port 18888 # start FastAPI + Web UI
tokenmind agent            # headless CLI agent mode (interactive REPL)
tokenmind gateway          # run channel gateway (telegram/email/feishu/etc.)
tokenmind status           # diagnostics for config + providers + channels
tokenmind channels status  # list configured channels and their state
tokenmind channels login   # interactive login for a channel
tokenmind plugins list     # list installed/discovered plugins
tokenmind provider login   # interactive OAuth/API-key setup for a provider

# Backend checks
pytest                     # all tests (asyncio_mode=auto, no shared conftest)
pytest tests/test_foo.py   # single test file
pytest -k "test_name"      # single test by name
ruff check tokenmind/      # lint
ruff format tokenmind/     # format

# Frontend (React + Vite)
cd frontend && npm install && npm run dev   # dev server at :5173 (proxies API to backend)
cd frontend && npm run build                # production build → frontend/dist
cd frontend && npm test                     # logic-only tests in frontend/tests/

# Bridge (WhatsApp / Baileys, Node.js 20+)
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

- `ProviderSpec` (frozen dataclass in `registry.py`) defines the supported provider presets with routing metadata: `backend` (openai_compat / anthropic), `is_gateway`, `is_local`, `detect_by_key_prefix`
- Concrete clients: `anthropic_provider.py`, `openai_compat_provider.py` (used by OpenAI, DeepSeek, DashScope (Qwen), Zhipu (GLM), Moonshot, MiniMax, MiMo, Gemini, OpenRouter, SiliconFlow, Ollama, etc.), `custom_provider.py`, plus `transcription.py` for ASR. `azure_openai_provider.py` and `openai_codex_provider.py` exist as optional clients but are not registered in `registry.py` — reach them via the `custom` preset
- Provider selection: `Config._match_provider(model)` in `config/schema.py` resolves by explicit `agents.defaults.provider`, then by model prefix (`<provider>/<model>`), then by registry keyword/key-prefix detection
- `LLMProvider` (abstract base in `base.py`): `chat()` and `chat_with_retry()` with exponential backoff
- `LLMResponse` returns: `content`, `tool_calls`, `finish_reason`, `usage`, `reasoning_content`, `thinking_blocks`
- Adding a provider: add `ProviderSpec` to `registry.py`, add field to `ProvidersConfig` in `config/schema.py`, implement client if a new backend is needed

### Tool System (`tokenmind/agent/tools/`)

- `ToolRegistry`: register/unregister/execute tools, `get_definitions()` returns OpenAI-format schemas
- `Tool` (abstract base in `base.py`): override `name`, `description`, `parameters`, `execute()`
- Built-in tools: `exec` (`shell.py`), `read_file`/`write_file`/`edit_file`/`list_dir` (`filesystem.py`), `web_search`/`web_fetch` (`web.py`), `message` (`message.py`), `deliver_attachment` (`deliver_attachment.py`), `spawn` (subagent — `spawn.py`), `cron` (`cron.py`), `generate_image` (`generate_image.py`), `skill_suggestion` (`skill_suggestion.py`)
- MCP tools (`tools/mcp.py`): auto-registered as `mcp_<server>_<tool>`, supports stdio/SSE/streamable HTTP transports

### Creative Services (`tokenmind/creative/`)

- MiniMax-backed media generation: `image_generation.py`, `music_generation.py`, `tts.py`, `voice_clone.py` (+ `voice_clone_store.py` for persisted clones), `voice_design.py`
- Each service is a thin async client that returns a `Generated*Result` dataclass; HTTP routes live in `server/routes/creative.py`
- Configured via `CreativeConfig` (per-capability `provider`/`model`/credentials) in `tokenmind/config/schema.py`

### Channels (`tokenmind/channels/`)

- `BaseChannel` (abstract): `start()`, `stop()`, `send(OutboundMessage)`, `_handle_message()`
- Implementations: telegram, email, dingtalk, feishu, wecom, qq, mochat, whatsapp
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
- Supported formats: pdf, docx, doc, pptx, ppt, md/txt and other UTF-8 text. PDF goes through pymupdf (fitz); docx/pptx through python-docx / python-pptx with table + slide structure preserved; legacy `.doc`/`.ppt` are converted by local LibreOffice (`soffice`). Optional VLM config in `KnowledgeConfig.vlm_*` captions complex PDF pages and embedded Office images via an OpenAI-compatible vision model. Spreadsheet formats (xlsx/xls) intentionally not supported — cell-format losses make text extraction unreliable for retrieval.

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

### Server (`tokenmind/server/`)

- `app.py` wires the FastAPI app and includes routers from `tokenmind/server/routes/` (one module per surface): `assets`, `chat`, `config`, `creative`, `cron`, `knowledge`, `memory`, `projects`, `sessions`, `skills`, `status`, `storage`, `updates`, `usage`
- WebSocket lives in `tokenmind/server/websocket/` (`manager.py` connection registry, `handler.py` protocol); endpoint is `/ws/{session_key}`
- `tokenmind/server/channel/web.py` (`WebChannel`) bridges WebSocket ↔ MessageBus
- `tokenmind/server/dependencies.py` wires shared singletons (config, bus, agent loop, stores) for FastAPI `Depends()`
- Serves frontend SPA from bundled `webui/` (via `hatch_build.py` build hook) or `frontend/dist/` with HTML5 history fallback (`server/frontend.py`)

### Cross-cutting Services

- `tokenmind/audit.py` — `AuditLogger` records tool execution, approvals, and high-risk actions
- `tokenmind/security/network.py` — SSRF/private-IP guards (`validate_url_target`, `validate_resolved_url`, `contains_internal_url`); use these whenever a tool fetches user-supplied URLs or runs shell commands containing URLs
- `tokenmind/desktop/launcher.py` — desktop launcher entry point (port discovery + browser open) used by packaged Windows builds

### Frontend (`frontend/`)

- React 18 + TypeScript + Vite + Zustand (state management)
- Key stores: `chatStore.ts` (sessions, messages, timeline, projects), `settingsStore.ts` (provider/model config), `knowledgeStore.ts`
- Project UI: `components/Projects/` (create, move session, confirm modals, sidebar state)
- Overlay system: `components/Overlay/` (portal + host for modals)
- WebSocket client for real-time streaming and tool timeline events

## Configuration (`tokenmind/config/schema.py`)

All Pydantic models with camelCase/snake_case alias support (`Base.model_config` uses `to_camel` alias generator + `populate_by_name=True`). Key sections:

- `AgentDefaults`: model (default `anthropic/claude-opus-4-5`), provider ("auto"), workspace, max_tokens, context_window_tokens, reasoning_effort
- `ProvidersConfig`: per-provider api_key, api_base, extra_headers, default_model (one field per registered provider preset: `custom`, `anthropic`, `openai`, `openrouter`, `deepseek`, `zhipu`, `dashscope`, `ollama`, `gemini`, `moonshot`, `minimax`, `mimo`, `siliconflow`)
- `ToolsConfig`: exec (confirm_high_risk, approval_timeout_s), uploads (max_file_mb, retention_days), knowledge (vector_backend, chunk_size), mcp_servers
- `CreativeConfig`: per-capability provider/model for image, music, music_cover, tts, voice_clone, voice_design, video
- `GatewayConfig`: web server `host` (default `0.0.0.0`) and `port` (default `18888`)
- `MCPServerConfig`: type (auto-detected), command/args/env (stdio), url/headers (HTTP), tool_timeout, enabled_tools

Config file lives at `~/.tokenmind/config.json` by default; override with `tokenmind --config <path>` or `TOKENMIND_CONFIG`.

## Testing

- Framework: pytest with `asyncio_mode = "auto"`
- ~90+ test files in `tests/` covering providers, channels, tools, knowledge, sessions, config, projects, attachments, and features
- Frontend tests in `frontend/tests/` (pure logic tests, no DOM runner)
- Tests import mocks/fixtures independently (no shared conftest.py)

## Build & Packaging

- `hatch_build.py`: custom Hatchling build hook that bundles `frontend/dist/` into `webui/` inside the wheel
- PyPI readme uses `README_PYPI.md` (not `README.md`)
- Docker: base `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` with Node.js 20, exposes port 18790, config at `/root/.tokenmind`
