<p align="center">
  <img src="tokenmind-logo.png" alt="TokenMind logo" width="920" />
</p>

<h1 align="center">TokenMind</h1>

<p align="center">
  <b>A local-first AI agent workbench</b><br/>
  Multi-model · tool calling · MCP · knowledge base (RAG / Wiki) · browser automation · voice input · scheduled tasks — one unified runtime.
</p>

<p align="center">
  <a href="https://pypi.org/project/tokenmind-ai/"><img src="https://img.shields.io/pypi/v/tokenmind-ai?style=flat-square&color=111111&label=PyPI" alt="PyPI" /></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-222222?style=flat-square" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/FastAPI-Backend-333333?style=flat-square" alt="FastAPI Backend" />
  <img src="https://img.shields.io/badge/React-Vite%20UI-444444?style=flat-square" alt="React Vite UI" />
  <img src="https://img.shields.io/badge/MCP-Ready-555555?style=flat-square" alt="MCP Ready" />
  <img src="https://img.shields.io/badge/License-MIT-666666?style=flat-square" alt="MIT License" />
</p>

<p align="center">
  <a href="README.md">简体中文</a> ·
  <b>English</b>
</p>

---

`TokenMind` is not just another chatbot — it's an extensible **agent runtime and workbench**: connect mainstream LLMs, then call tools, query knowledge bases, drive a browser, and run scheduled jobs inside the conversation — all wrapped in a local-first, self-hostable web console. Use it to build your own personal AI assistant, or to stand up a private agent platform for your team.

## ✨ Highlights

- 🧠 **Unified multi-model access** — 13+ providers (OpenAI / Anthropic / Gemini / DeepSeek / Qwen / GLM / Kimi / MiniMax / Ollama / OpenRouter / SiliconFlow…), `<provider>/<model>` routing, and **transparent fallback** with a circuit breaker when the primary model fails.
- 🛠️ **In-conversation tool calling** — shell exec, file I/O, web search/fetch, scheduled tasks, sub-agents (spawn), image generation; high-risk actions go through **human approval + an audit log**.
- 🧩 **Native MCP support** — `stdio` / `SSE` / `streamableHTTP` transports, tools auto-registered, per-server tool scoping.
- 📚 **Dual-mode knowledge base** — RAG (vector retrieval + rerank) or Wiki (graph compilation); structured PDF / DOCX / PPTX parsing with optional **VLM vision parsing** for complex pages.
- 🌐 **Browser automation** — drive your **logged-in** local Chrome via OpenCLI to complete web tasks; long-running tasks can hand control back to you mid-run.
- 🎙️ **Voice input** — one-tap mic transcription via on-device `faster-whisper` (offline, no key) or Groq cloud Whisper.
- 💬 **Multi-channel** — Telegram · Feishu · DingTalk · WeCom · QQ · Email · WeChat Official Account · WhatsApp (Node bridge).
- 🗂️ **Memory / projects / sessions** — long-term memory auto-consolidated by token threshold, project workspaces, streaming replies, tool timeline, context-budget gauge.
- 🔒 **Local-first** — config and data stay on your machine (`~/.tokenmind/`), with built-in SSRF / private-IP guards.

## 📑 Table of Contents

- [🚀 Quick Start](#quick-start)
- [🏗️ Architecture](#architecture)
- [🧠 Models & Providers](#models--providers)
- [📚 Knowledge Base](#knowledge-base)
- [🧩 Tools & MCP](#tools--mcp)
- [🌐 Browser Automation](#browser-automation)
- [🎙️ Voice Input](#voice-input)
- [💬 Channels](#channels)
- [🖥️ Web Console](#web-console)
- [🛠️ Built-in Skills](#built-in-skills)
- [📦 Desktop Installers](#desktop-installers)
- [💻 Development](#development)
- [📁 Project Layout](#project-layout)
- [📖 Docs](#docs)
- [📄 License](#license)

## Quick Start

### Requirements

- Python **3.11+**
- Node.js **20+** (needed to run the Web UI from source, hack on the frontend, or run the WhatsApp bridge)
- **Optional** LibreOffice — to parse legacy `.doc` / `.ppt` files
- **Optional** OpenCLI — to enable the browser automation tool
- A dedicated virtualenv is recommended

### Option A: pip install (recommended)

```bash
pip install tokenmind-ai
tokenmind onboard          # initialize config → ~/.tokenmind/config.json
tokenmind web --port 18888 # start backend + Web UI
```

Open <http://localhost:18888>. The pip package bundles the prebuilt frontend, so it works out of the box.

### Option B: from source

**macOS / Linux**

```bash
git clone https://gitee.com/sun124578963_0/TokenMind.git
cd TokenMind

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .

tokenmind onboard

# source users must build the frontend first
cd frontend && npm install && npm run build && cd ..
tokenmind web --port 18888
```

**Windows PowerShell**

```powershell
git clone https://gitee.com/sun124578963_0/TokenMind.git
cd TokenMind

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .

tokenmind onboard
cd frontend; npm install; npm run build; cd ..
tokenmind web --port 18888
```

> If the browser returns `{"detail":"Not Found"}`, `frontend/dist` likely wasn't built — re-run `npm run build` in `frontend`.

### Configure model API keys

Open the Web UI → **Settings → Models**:

1. Pick a provider under **Providers** (OpenAI / Anthropic / DeepSeek…)
2. Enter the API key, and a Base URL if needed
3. Enable the models you want under **Models**
4. Switch to the chat page and start using it

You can also edit `providers.<name>.api_key` directly in `~/.tokenmind/config.json`.

### Common commands

| Command | Description |
|---|---|
| `tokenmind onboard` | Setup wizard, writes `~/.tokenmind/config.json` |
| `tokenmind web --port 18888` | Start FastAPI + Web UI |
| `tokenmind agent` | Headless CLI agent (interactive REPL) |
| `tokenmind gateway` | Run the channel gateway (Telegram / email / Feishu…) |
| `tokenmind status` | Diagnostics for config / providers / channels |
| `tokenmind channels status` | List configured channels and their state |
| `tokenmind channels login` | Interactive login for a channel |
| `tokenmind plugins list` | List installed / discovered plugins |
| `tokenmind provider login` | Interactive OAuth / API-key setup |

## Architecture

<p align="center">
  <img src="tokenmind-arch.png" alt="TokenMind architecture" width="920" />
</p>

Core data flow:

```
Web UI / Channel → MessageBus → AgentLoop → Providers + Tools → Session / Memory / Knowledge → WebSocket / Channel Output
```

Three parts:

- **Python backend** — agent runtime, config, knowledge base, memory, sessions, image generation, API
- **React frontend** — chat, settings, knowledge base, file center, memory center, scheduled tasks, asset library
- **Node bridge** — bridges channels that need a web/native SDK (WhatsApp)

## Models & Providers

Routing is `<provider>/<model>`; you can also pin a default provider in config. When the primary model returns an error, TokenMind transparently fails over through `fallback_models` in order, and a circuit breaker temporarily skips a primary that fails repeatedly.

| Provider | Example models |
| --- | --- |
| Anthropic | `claude-opus-4-5` / `claude-sonnet-4-5` |
| OpenAI | `gpt-4o` / `gpt-4o-mini` |
| Gemini | `gemini-2.0-flash` |
| DeepSeek | `deepseek-chat` / `deepseek-reasoner` |
| Qwen (DashScope) | `qwen-max` / `qwen-vl-max` |
| GLM (Zhipu) | `glm-4-plus` |
| Moonshot | `kimi-k2.5` |
| MiniMax | `MiniMax-Text-01` |
| MiMo | Xiaomi MiMo reasoning model |
| OpenRouter | `anthropic/claude-sonnet-4-5` and other aggregated routes |
| SiliconFlow | `Qwen/Qwen2.5-7B-Instruct`, etc. |
| Ollama | `llama3.2` / any local model |
| Custom | Any OpenAI-compatible gateway |

- Default model: `anthropic/claude-opus-4-5`
- Default context window: `262144` (256k — a soft compaction threshold; memory is auto-consolidated past it)
- Reasoning models (DeepSeek / MiMo) require strict `reasoning_content` handling; TokenMind auto-sanitizes non-conforming legacy history when switching to them — no manual work needed

## Knowledge Base

Two modes share the same document parser plus optional VLM vision parsing:

| Mode | Best for |
|---|---|
| **RAG** | Vector retrieval + rerank — FAQs, doc Q&A, cited answers |
| **Wiki** | The LLM compiles uploads into Markdown source pages + an entity / topic graph for visual browsing — knowledge management & inventory |

**Supported formats**

- `PDF` — text via pymupdf; complex pages (no text + large images) can optionally be sent to a VLM for captions
- `DOCX` — python-docx, preserving paragraphs / heading levels / tables / nested tables
- `DOC` — converted to `.docx` via local LibreOffice (`soffice`)
- `PPTX` — python-pptx, paginated by slide, title flagged, shapes ordered by position
- `PPT` — converted to `.pptx` via LibreOffice
- `MD / TXT / JSON / YAML / CSV / RST / LOG`, etc. — read directly as UTF-8

> `.doc` / `.ppt` legacy formats require LibreOffice installed locally; without it the document is flagged `failed` with an install hint.
> Spreadsheets (`xlsx` / `xls`) are intentionally unsupported — cell-format losses make text extraction unreliable for retrieval.

**Vector backends**: `Qdrant` (default) or `SQLite` (lightweight fallback, no extra service). Embedding / rerank / VLM models are user-configured.

## Tools & MCP

Built-in tools available in conversation:

| Tool | Purpose |
|---|---|
| `exec` | Shell command execution (high-risk actions need approval) |
| `read_file` / `write_file` / `edit_file` / `list_dir` | File I/O and browsing |
| `web_search` / `web_fetch` | Search & fetch web pages (with SSRF guards) |
| `cron` | Scheduled task management (catch-up + periodic heartbeat scheduling) |
| `spawn` | Spawn a sub-agent for subtasks |
| `generate_image` | Image generation |
| `message` / `deliver_attachment` | Proactively message / deliver files to the user |
| `browser` | Browser automation (requires OpenCLI, see below) |
| `task_list` / `ask_user_question` | Task list / ask the user |
| `wiki_index` / `wiki_grep` | Wiki knowledge-base lookup |

**MCP**: native support for the MCP tool protocol — tools auto-register as `mcp_<server>_<tool>`. Under **Settings → MCP** you can import via form or JSON, scope which tools a server exposes, check connection status, and refresh tool lists. Supports `stdio` / `sse` / `streamableHttp`.

## Browser Automation

The `browser` tool drives your **logged-in** local Chrome via the external **OpenCLI** binary to complete tasks that need an authenticated session (research, filling forms, scraping page content, etc.).

- The tool is only exposed when an `opencli` binary is detected (so it doesn't waste context otherwise)
- The Web UI offers one-click install and site-profile management (`/api/browser/*`)
- Long-running tasks can hand control back to you mid-run (click "I'm done" to continue)

## Voice Input

The Web UI mic button turns speech into text:

- **Local** (default): `faster-whisper` — offline, no API key. Install the `asr` extra: `pip install "tokenmind-ai[asr]"`
- **Cloud**: Groq Whisper — reads `GROQ_API_KEY` or the key in config

Switch backend and model (faster-whisper size / device / compute type / language) under **Settings**. Single-clip cap: 25 MB.

## Channels

Connect the agent to external IMs / email:

```bash
tokenmind gateway
```

Supported: **Telegram · Feishu · DingTalk · WeCom · QQ · Email · WeChat Official Account · WhatsApp**. Configure credentials under **Settings → Channels**. WhatsApp runs through the Node bridge:

```bash
cd bridge && npm install && npm run build   # scan the QR to log in
```

## Web Console

Sidebar groups:

- **Chat** — session list / search / rename / delete / streaming replies / tool timeline / stop generation / context-budget gauge
- **Knowledge** — manage multiple knowledge bases; RAG and Wiki modes
- **Assets** — unified view of generated images
- **Projects** — group sessions under a project
- **More** — scheduled tasks · token usage
- **Settings**
  - Models — providers / API keys / default model / fallback; knowledge embedding · rerank · VLM
  - Tools — web search · shell exec · upload policy · knowledge chunking
  - MCP — server list · tool visibility · JSON import
  - Channels — per-channel credentials and online status
  - Skills — enable / disable built-in skills
  - Service — web host / port · channel message behavior
  - Memory — edit long-term memory · current context · recent archives
  - Files — upload list · quota · cleanup policy

## Built-in Skills

Bundled in `tokenmind/skills/`, discovered automatically:

| Skill | Purpose |
|---|---|
| `documents` | Create / edit / redline / compare / render DOCX — 30+ python-docx scripts + OOXML reference |
| `presentations` | Build editable PPTX — templates / design system / render scripts |
| `memory` | Long-term memory & archiving operations |
| `cron` | Scheduled task management |
| `github` | gh-CLI-wrapped GitHub operations |
| `weather` | wttr.in / Open-Meteo weather lookup |
| `summarize` | Summarize URLs / files / videos |
| `tmux` | Remote tmux session control |
| `skill-creator` | Scaffold a new skill |
| `clawhub` | Search & install third-party skills from the ClawHub registry |

Skill requirements (python packages / binaries / env vars) are auto-detected under **Settings → Skills**, with install hints when missing.

## Desktop Installers

Package TokenMind into a double-click desktop app — end users don't need Node.js.

**Windows (PyInstaller + Inno Setup)**

```powershell
python -m pip install ".[windows]"
.\packaging\windows\build-installer.ps1
```

Produces `dist-installer\TokenMindSetup-<version>.exe`. To test PyInstaller without building the installer, add `-SkipInstaller`.

**macOS (PyInstaller + DMG)**

```bash
python -m pip install ".[macos]"
./packaging/macos/build.sh
```

## Development

**Backend**

```bash
python -m pip install -e ".[dev]"
pytest                     # asyncio_mode=auto
ruff check tokenmind/
ruff format tokenmind/
```

**Frontend**

```bash
cd frontend
npm install
npm run dev          # dev server at http://localhost:5173 (proxies API to backend 18888)
npm run build        # production build → frontend/dist
npm run test:unit    # logic-only unit tests
```

**Bridge**

```bash
cd bridge && npm install && npm run build
```

## Project Layout

```text
TokenMind/
├─ tokenmind/                # Python backend package
│  ├─ agent/                 # agent loop, context builder, tool system, skills, sub-agents
│  ├─ bus/                   # message bus & events
│  ├─ channels/              # chat channel integrations (Telegram / Feishu / DingTalk / QQ / email …)
│  ├─ cli/                   # CLI entry point + onboarding wizard
│  ├─ config/                # config schema (pydantic) & loading
│  ├─ creative/              # image generation
│  ├─ cron/                  # scheduled task service
│  ├─ integrations/opencli/  # browser automation (OpenCLI driver)
│  ├─ knowledge/             # knowledge base: parsing / chunking / wiki compile / vector retrieval
│  ├─ providers/             # model provider implementations + fallback + usage accounting
│  ├─ security/              # SSRF / private-IP guards
│  ├─ server/                # FastAPI, WebSocket, routes, attachments, web channel
│  ├─ session/               # session & history persistence
│  ├─ skills/                # built-in skills
│  └─ templates/             # workspace templates (AGENTS.md / MEMORY …)
├─ frontend/                 # React + Vite Web UI
├─ bridge/                   # Node channel bridge (WhatsApp)
├─ tests/                    # backend tests
├─ packaging/                # Windows / macOS installer builds
├─ README.md
└─ pyproject.toml
```

## Docs

- [Architecture (CLAUDE.md)](CLAUDE.md)
- [Architecture (AGENTS.md)](AGENTS.md) — kept in sync with CLAUDE.md, for non-Claude coding agents
- [Security notes](SECURITY.md)
- [Skill development guide](tokenmind/skills/README.md)

## License

[MIT](LICENSE)
