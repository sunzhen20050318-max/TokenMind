# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**sun-agent** (formerly sun_agent) is an ultra-lightweight personal AI assistant framework. It connects to various chat platforms (Telegram, Discord, Feishu, WhatsApp, etc.) and provides an AI agent with tool execution capabilities. The CLI entry point remains `sun_agent`.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI / Gateway                        │
├─────────────────────────────────────────────────────────────┤
│                      MessageBus (queue.py)                   │
│                    inbound queue ←→ outbound queue            │
├──────────────┬──────────────────────────────┬────────────────┤
│   Channels   │        AgentLoop             │    Web UI      │
│  (telegram,  │  ┌──────────────────────┐   │  (FastAPI +    │
│   discord,   │  │ ContextBuilder       │   │   React)       │
│   feishu...) │  │ (prompt building)    │   │                │
│              │  ├──────────────────────┤   │                │
│              │  │ ToolRegistry        │   │                │
│              │  │ (tool execution)    │   │                │
│              │  ├──────────────────────┤   │                │
│              │  │ LLMProvider         │   │                │
│              │  │ (OpenRouter, etc.) │   │                │
│              │  └──────────────────────┘   │                │
└──────────────┴──────────────────────────────┴────────────────┘
```

### Core Components

- **MessageBus** (`sun_agent/bus/queue.py`): Async queue decoupling channels from agent
- **AgentLoop** (`sun_agent/agent/loop.py`): Core processing engine — receives messages, builds context, calls LLM, executes tools
- **Channels** (`sun_agent/channels/`): Platform integrations (Telegram, Discord, Feishu, WhatsApp, Slack, QQ, etc.)
- **ToolRegistry** (`sun_agent/agent/tools/registry.py`): Manages built-in tools (shell, filesystem, web search, message, cron, spawn, MCP)
- **SessionManager** (`sun_agent/session/manager.py`): Conversation session persistence
- **ContextBuilder** (`sun_agent/agent/context.py`): Builds prompts from history, memory, skills
- **Providers** (`sun_agent/providers/`): LLM provider integrations via LiteLLM, plus custom providers for OpenAI Codex, Azure OpenAI, and direct OpenAI-compatible endpoints
- **Skills** (`sun_agent/skills/`): Bundled agent skills (github, weather, tmux, cron, memory, summarize, clawhub, skill-creator). Each skill has a `SKILL.md` that defines its prompts and capabilities

### Web UI Stack

- **Backend**: FastAPI server (`sun_agent/server/app.py`) with WebSocket support, `WebChannel` bridges WebSocket messages to MessageBus
- **Frontend**: React + Vite + Zustand (`frontend/src/stores/chatStore.ts`) + react-markdown
- **Integration**: `WebChannel` implements `BaseChannel` interface, bridges WebSocket messages to MessageBus

## Commands

```bash
# Backend development
pip install -e ".[dev]"          # Install with dev dependencies
pytest                            # Run tests
ruff check sun_agent/               # Lint
ruff format sun_agent/              # Format

# Frontend development
cd frontend && npm install        # Install dependencies
npm run dev                       # Start dev server (Vite)
npm run build                     # Build for production

# Running sun_agent
sun_agent onboard                   # Initialize config at ~/.sun_agent/
sun_agent agent                     # Start CLI chat
sun_agent gateway                   # Start gateway (connects channels)
sun_agent status                    # Show status
sun_agent channels login            # Link WhatsApp (QR code)
sun_agent channels status           # Show channel status
sun_agent plugins list              # List built-in and plugin channels
sun_agent provider login openai-codex  # OAuth login for providers

# Web UI
sun_agent web --port 8080           # Start web server (if web command available)
```

## Key Patterns

### Adding a New LLM Provider

Add a `ProviderSpec` entry to `sun_agent/providers/registry.py` and a field to `ProvidersConfig` in `sun_agent/config/schema.py`. No if-elif chains to touch.

### Adding a New Channel

Implement `BaseChannel` interface in `sun_agent/channels/`. Key methods: `start()`, `stop()`, `send()`, `_handle_message()`. Register in `ChannelManager`.

### Tool Execution Flow

1. LLM returns tool call → `AgentLoop._run_agent_loop()`
2. `ToolRegistry.execute()` runs the tool
3. Result returned to LLM for final response
4. Tool calls sent via `on_progress()` callback for real-time UI updates

### WebSocket Tool Events

The backend sends metadata flags for tool events: `_tool_start`, `_tool_end`, `_tool_id`, `_tool_name`, `_tool_duration`. Frontend `useWebSocket.ts` parses these to update `toolCalls` in Zustand store.

### Session Management

Sessions are identified by `session_key = "channel:chat_id"`. `SessionManager` persists to JSONL files. On deletion, both in-memory cache (`invalidate()`) and disk file must be removed.

## Project Structure

```
sun_agent/
├── agent/          # Core agent logic
│   ├── loop.py     # Agent loop (LLM ↔ tool execution)
│   ├── context.py  # Prompt builder
│   ├── memory.py   # Persistent memory
│   ├── skills.py   # Skills loader
│   ├── subagent.py # Background task execution
│   └── tools/      # Built-in tools (shell, filesystem, web, message, cron, spawn, MCP)
├── skills/         # Bundled skills (github, weather, tmux, cron, memory, summarize...)
├── channels/       # Chat channel integrations
├── bus/            # Message routing (queue.py, events.py)
├── cron/           # Scheduled tasks
├── heartbeat/      # Proactive wake-up
├── providers/     # LLM providers (LiteLLM wrapper, custom, Azure, Codex)
├── session/        # Conversation sessions (JSONL persistence)
├── config/         # Configuration schema and loading
├── server/         # FastAPI web server
│   ├── app.py      # Main FastAPI app
│   ├── channel/web.py  # WebChannel (WebSocket ↔ MessageBus)
│   └── websocket/  # WebSocket connection management
├── cli/            # CLI commands (typer-based)
└── utils/          # Helpers, evaluator
frontend/           # React + Vite + Zustand + react-markdown
bridge/             # WhatsApp bridge (Node.js)
```

## Important Files

| File | Purpose |
|------|---------|
| `sun_agent/agent/loop.py` | Core agent processing loop |
| `sun_agent/bus/queue.py` | Async message queue |
| `sun_agent/bus/events.py` | `InboundMessage`, `OutboundMessage` dataclasses |
| `sun_agent/channels/base.py` | `BaseChannel` abstract interface |
| `sun_agent/session/manager.py` | Session persistence |
| `sun_agent/server/app.py` | FastAPI web server |
| `sun_agent/server/channel/web.py` | Web channel implementation |
| `frontend/src/stores/chatStore.ts` | Zustand state management |
| `sun_agent/providers/registry.py` | Provider registry (add new LLM providers here) |

## Branching Strategy

- **`main`**: Stable releases — bug fixes only
- **`nightly`**: Experimental features — new features and breaking changes

Target `nightly` for features, `main` for bug fixes. Stable features are cherry-picked from `nightly` to `main` weekly.
