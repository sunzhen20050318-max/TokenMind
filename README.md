# TokenMind

<p align="center">
  <img src="tokenmind-logo.png" alt="TokenMind logo" width="920" />
</p>

<p align="center">
  一个面向个人与团队的多模型 AI Agent 框架，集成聊天渠道、工具调用、MCP、会话持久化与 Web 控制台。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-111111?style=flat-square" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/FastAPI-Backend-222222?style=flat-square" alt="FastAPI Backend" />
  <img src="https://img.shields.io/badge/React-Vite%20UI-333333?style=flat-square" alt="React Vite UI" />
  <img src="https://img.shields.io/badge/MCP-Ready-444444?style=flat-square" alt="MCP Ready" />
  <img src="https://img.shields.io/badge/License-MIT-555555?style=flat-square" alt="MIT License" />
</p>

## 项目简介

`TokenMind` 是一个以 Python Agent 运行时为核心、以 React Web UI 为控制台、并支持 Node 渠道桥接的 AI Agent 项目。

它的目标不是只做一个聊天机器人，而是提供一套可持续扩展的 Agent 基础设施：

- 支持多模型提供商统一接入
- 支持多渠道消息收发与网关模式
- 支持文件、Shell、Web 搜索、消息、定时任务、MCP 等工具调用
- 支持会话持久化、上下文构建、技能系统与子代理能力
- 提供可直接使用的 Web 控制台，用于聊天、会话管理、模型配置与 MCP 可视化

## 核心能力

- 多模型支持：内置 OpenAI、Anthropic、Gemini、DeepSeek、Groq、MiniMax、OpenRouter、Ollama、vLLM 等多种模型提供商
- 多渠道接入：支持 Telegram、Discord、Feishu、Slack、WhatsApp、QQ 等渠道扩展
- 工具系统：内置 `exec`、文件系统、Web 搜索、消息发送、Cron、MCP 等工具
- MCP 集成：支持 `stdio`、`sse`、`streamableHttp` 三类 MCP 服务接入
- Web 控制台：支持流式回复、停止生成、工具执行时间线、会话搜索与重命名、设置中心
- 会话持久化：本地保存聊天历史、工具调用链和时间线事件
- 技能机制：支持通过 `SKILL.md` 扩展 Agent 行为与工作流

## 架构概览

<p align="center">
  <img src="tokenmind-arch.png" alt="TokenMind architecture" width="920" />
</p>

核心链路可以概括为：

`Channel / Web UI -> MessageBus -> AgentLoop -> Provider + Tools -> SessionManager -> WebSocket / Channel Output`

项目结构上主要由三部分组成：

- Python 后端：负责 Agent 运行时、配置系统、会话、工具执行和 API 服务
- React 前端：负责聊天界面、设置中心、MCP 工具可视化和会话管理
- Node Bridge：负责某些渠道桥接能力，例如 WhatsApp

## 快速开始

### 1. 环境要求

- Python `3.11+`
- Node.js `20+`
- 推荐使用独立虚拟环境

### 2. 克隆项目

```bash
git clone https://gitee.com/sun124578963_0/TokenMind.git
cd TokenMind   # 仓库目录当前仍沿用历史名称
```

### 3. 安装后端依赖

```bash
pip install -e ".[dev]"
```

### 4. 初始化配置

```bash
tokenmind onboard
```

默认配置文件位于：

```text
~/.tokenmind/config.json
```

### 5. 启动 Web 服务

旧版 `~/.tokenmind/config.json` 如果存在，会在首次启动时自动迁移到 `~/.tokenmind/config.json`。

```bash
tokenmind web --port 8080
```

### 6. 启动前端开发环境

```bash
cd frontend
npm install
npm run dev
```

前端默认访问地址：

```text
http://localhost:5173
```

### 7. 启动网关

如果你要把 Agent 接到聊天渠道，而不只是本地 Web UI，可以继续启动：

```bash
tokenmind gateway
```

## Web 控制台

当前 Web UI 已经覆盖了项目的核心日常操作：

- 会话列表、搜索、重命名与删除
- 聊天消息流式显示
- 停止生成
- 工具执行时间线
- 模型与 Agent 参数配置
- 工具、MCP、运行时配置
- MCP 服务工具列表实时探测与可视化

如果你只想先把项目跑起来，最简单的方式就是：

1. 配好模型 API Key
2. 启动 `tokenmind web --port 8080`
3. 进入 `http://localhost:5173`
4. 在“设置中心”里完成模型和工具配置

## 模型配置

你可以通过两种方式配置模型：

- 在 Web UI 的“设置中心”中直接填写 provider、API Key、默认模型等信息
- 手动编辑 `~/.tokenmind/config.json`

默认支持的模型提供商包括但不限于：

| Provider | 默认模型示例 |
| --- | --- |
| OpenAI | `gpt-4o` |
| Anthropic | `claude-sonnet-4-5` |
| Gemini | `gemini-2.0-flash` |
| DeepSeek | `deepseek-chat` |
| Groq | `llama-3.3-70b-versatile` |
| MiniMax | `MiniMax-M2.7` |
| OpenRouter | `anthropic/claude-sonnet-4-5` |
| Ollama | `llama3.2` |
| vLLM | `llama-3.1-8b-instruct` |

## MCP 支持

`TokenMind` 原生支持把 MCP 服务注册为 Agent 工具。

支持的接入方式：

- `stdio`
- `sse`
- `streamableHttp`

接入后，MCP 工具会被包装成统一的工具名，例如：

```text
mcp_minimax_web_search
mcp_minimax_understand_image
```

在设置中心的 `MCP` 分组里，你可以：

- 管理 MCP 服务配置
- 限制允许暴露的工具范围
- 查看服务是否连通
- 刷新并查看实时工具列表

## 项目结构

```text
tokenmind/
├─ tokenmind/
│  ├─ agent/                 # Agent 主循环、上下文构建、工具系统
│  ├─ bus/                   # 消息总线与队列
│  ├─ channels/              # 各聊天渠道接入
│  ├─ cli/                   # 命令行入口
│  ├─ config/                # 配置模型与加载逻辑
│  ├─ cron/                  # 定时任务相关能力
│  ├─ providers/             # LLM provider 实现
│  ├─ server/                # FastAPI、WebSocket、Web channel
│  ├─ session/               # 会话与历史持久化
│  └─ skills/                # 内置技能
├─ frontend/                 # React + Vite Web UI
├─ bridge/                   # Node 渠道桥接服务
├─ tests/                    # 后端测试
├─ README.md
└─ pyproject.toml
```

## 开发说明

### 后端开发

```bash
pip install -e ".[dev]"
pytest -q
ruff check tokenmind/
```

### 前端开发

```bash
cd frontend
npm install
npm run dev
npm run build
```

### WhatsApp Bridge

```bash
cd bridge
npm install
npm run build
```

## 适合什么场景

`TokenMind` 适合这几类使用方式：

- 想要一套能长期演进的个人 Agent 基础框架
- 想把多模型、多渠道、多工具统一到一个运行时中
- 想在本地或私有环境中部署自己的 AI 助手
- 想把 MCP、Web 控制台、会话历史和工具执行链整合到同一个项目里

## 文档

- [架构说明](CLAUDE.md)
- [TokenMind Skills 说明](tokenmind/skills/README.md)

## License

MIT
