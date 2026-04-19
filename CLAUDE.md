# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

**TokenMind** is a lightweight personal AI assistant framework. It connects to multiple chat platforms and provides an AI agent with tool execution capabilities. The public CLI is `tokenmind`, while the internal Python package remains `tokenmind` for compatibility.

## Architecture

The runtime is centered around:

- `tokenmind/bus/queue.py` — async message bus
- `tokenmind/agent/loop.py` — core agent processing loop
- `tokenmind/agent/context.py` — prompt and context builder
- `tokenmind/session/manager.py` — session persistence
- `tokenmind/providers/` — provider implementations and registry
- `tokenmind/server/app.py` — FastAPI backend and Web UI entrypoint
- `frontend/` — React + Vite UI
- `bridge/` — Node.js WhatsApp bridge

## Common Commands

```bash
# Backend development
pip install -e ".[dev]"
pytest
ruff check tokenmind/
ruff format tokenmind/

# Frontend development
cd frontend
npm install
npm run dev
npm run build

# Running TokenMind
tokenmind onboard
tokenmind agent
tokenmind gateway
tokenmind status
tokenmind channels login
tokenmind channels status
tokenmind plugins list
tokenmind provider login openai-codex

# Web UI
tokenmind web --port 8080
```

## Key Patterns

### Adding a New LLM Provider

Add a `ProviderSpec` entry to `tokenmind/providers/registry.py` and a field to `ProvidersConfig` in `tokenmind/config/schema.py`.

### Adding a New Channel

Implement the `BaseChannel` interface in `tokenmind/channels/`, then register it with the channel manager.

### Tool Execution Flow

1. The model requests a tool call
2. `AgentLoop` dispatches it through `ToolRegistry`
3. The result is fed back into the model
4. Progress events are emitted for the frontend timeline

### Session Management

Sessions use `session_key = "channel:chat_id"` and persist to JSONL. Deleting a session should remove both in-memory and on-disk state.

## Project Structure

```text
tokenmind/
├─ agent/
├─ bus/
├─ channels/
├─ cli/
├─ config/
├─ cron/
├─ heartbeat/
├─ providers/
├─ server/
├─ session/
├─ skills/
└─ utils/
frontend/
bridge/
```

## Important Files

| File | Purpose |
|------|---------|
| `tokenmind/agent/loop.py` | Core agent processing loop |
| `tokenmind/bus/queue.py` | Async message queue |
| `tokenmind/bus/events.py` | Event dataclasses |
| `tokenmind/channels/base.py` | Base channel interface |
| `tokenmind/session/manager.py` | Session persistence |
| `tokenmind/server/app.py` | FastAPI server |
| `tokenmind/server/channel/web.py` | Web channel bridge |
| `frontend/src/stores/chatStore.ts` | Frontend Zustand state |
| `tokenmind/providers/registry.py` | Provider registry |
