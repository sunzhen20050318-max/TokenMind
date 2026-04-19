# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

**TokenMind** is a lightweight personal AI assistant framework. It connects to multiple chat platforms and provides an AI agent with tool execution capabilities. The public CLI is `tokenmind`, while the internal Python package remains `sun_agent` for compatibility.

## Architecture

The runtime is centered around:

- `sun_agent/bus/queue.py` — async message bus
- `sun_agent/agent/loop.py` — core agent processing loop
- `sun_agent/agent/context.py` — prompt and context builder
- `sun_agent/session/manager.py` — session persistence
- `sun_agent/providers/` — provider implementations and registry
- `sun_agent/server/app.py` — FastAPI backend and Web UI entrypoint
- `frontend/` — React + Vite UI
- `bridge/` — Node.js WhatsApp bridge

## Common Commands

```bash
# Backend development
pip install -e ".[dev]"
pytest
ruff check sun_agent/
ruff format sun_agent/

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

Add a `ProviderSpec` entry to `sun_agent/providers/registry.py` and a field to `ProvidersConfig` in `sun_agent/config/schema.py`.

### Adding a New Channel

Implement the `BaseChannel` interface in `sun_agent/channels/`, then register it with the channel manager.

### Tool Execution Flow

1. The model requests a tool call
2. `AgentLoop` dispatches it through `ToolRegistry`
3. The result is fed back into the model
4. Progress events are emitted for the frontend timeline

### Session Management

Sessions use `session_key = "channel:chat_id"` and persist to JSONL. Deleting a session should remove both in-memory and on-disk state.

## Project Structure

```text
sun_agent/
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
| `sun_agent/agent/loop.py` | Core agent processing loop |
| `sun_agent/bus/queue.py` | Async message queue |
| `sun_agent/bus/events.py` | Event dataclasses |
| `sun_agent/channels/base.py` | Base channel interface |
| `sun_agent/session/manager.py` | Session persistence |
| `sun_agent/server/app.py` | FastAPI server |
| `sun_agent/server/channel/web.py` | Web channel bridge |
| `frontend/src/stores/chatStore.ts` | Frontend Zustand state |
| `sun_agent/providers/registry.py` | Provider registry |
