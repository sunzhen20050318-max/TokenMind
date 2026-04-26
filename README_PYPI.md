# TokenMind

TokenMind is a lightweight personal AI assistant framework focused on local-first agent workflows.

It combines:

- multi-provider LLM access
- tool execution inside conversations
- knowledge base retrieval
- long-term memory and session persistence
- a FastAPI backend with a web chat surface
- optional channel integrations and bridge services

## Install

```bash
pip install tokenmind-ai
```

After installation, the CLI entry point is:

```bash
tokenmind --help
```

## Quick Start

Initialize your local workspace and config:

```bash
tokenmind onboard
```

Run the backend web service:

```bash
tokenmind web --port 18888
```

Then open:

```text
http://localhost:18888
```

## Notes

- Python `3.11+` is required.
- The published Python package bundles the production web UI, so `tokenmind web` can serve it directly after installation.
- The React/Vite frontend still exists in this repository for local development.

## Source

- Repository: <https://gitee.com/sun124578963_0/TokenMind>
- Issues: <https://gitee.com/sun124578963_0/TokenMind/issues>
