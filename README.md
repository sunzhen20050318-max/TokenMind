# TokenMind

<p align="center">
  <img src="tokenmind-logo.png" alt="TokenMind logo" width="920" />
</p>

<p align="center">
  面向个人与团队的本地优先 AI Agent 工作台，集成聊天、多模型、工具调用、MCP、知识库、记忆系统与 Web 控制台。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-111111?style=flat-square" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/FastAPI-Backend-222222?style=flat-square" alt="FastAPI Backend" />
  <img src="https://img.shields.io/badge/React-Vite%20UI-333333?style=flat-square" alt="React Vite UI" />
  <img src="https://img.shields.io/badge/MCP-Ready-444444?style=flat-square" alt="MCP Ready" />
  <img src="https://img.shields.io/badge/Knowledge%20Base-Built--in-555555?style=flat-square" alt="Knowledge Base" />
  <img src="https://img.shields.io/badge/License-MIT-666666?style=flat-square" alt="MIT License" />
</p>

## 项目简介

`TokenMind` 是一个本地优先的 AI Agent 框架，目标不是只做一个聊天机器人，而是提供一套可持续扩展的 Agent 运行时与工作台：

- 统一接入多种模型与推理提供商
- 在会话中调用文件、Shell、Web 搜索、MCP 等工具
- 提供知识库、记忆系统、定时任务与文件中心
- 用完整的 Web UI 管理对话、模型、知识库和运行时设置

它适合用来搭建你自己的个人 AI 助手，也适合在团队内做私有化 Agent 工作台。

## 核心能力

- 多模型支持：内置 OpenAI、Anthropic、Gemini、DeepSeek、Groq、MiniMax、OpenRouter、Ollama、vLLM 等提供商
- Web 控制台：支持会话管理、流式回复、工具时间线、停止生成、模型切换、知识库链接
- 工具系统：内置 `exec`、文件读写、Web 搜索、定时任务、消息发送、MCP 工具接入
- MCP 集成：支持 `stdio`、`sse`、`streamableHttp` 三类服务
- 知识库：支持多知识库、多文档格式、Embedding、Rerank、混合检索、来源引用
- 记忆系统：包含长期记忆、当前上下文、近期归档与会话持久化
- 审批与审计：支持高风险 `exec` 审批、审计日志与会话级授权

## 架构概览

<p align="center">
  <img src="tokenmind-arch.png" alt="TokenMind architecture" width="920" />
</p>

核心链路可以概括为：

`Web UI / Channel -> MessageBus -> AgentLoop -> Providers + Tools -> Session / Memory / Knowledge -> WebSocket / Channel Output`

主要由三部分组成：

- Python 后端：负责 Agent 运行时、配置系统、知识库、记忆、会话和 API
- React 前端：负责聊天、设置中心、知识库、记忆中心、文件中心和定时任务
- Node Bridge：负责某些渠道桥接能力，例如 WhatsApp

## 快速开始

### 1. 环境要求

- Python `3.11+`
- Node.js `20+`
- 推荐使用独立虚拟环境

### 2. 克隆项目

```bash
git clone https://gitee.com/sun124578963_0/TokenMind.git
cd TokenMind
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

```bash
tokenmind web --port 8080
```

### 6. 启动前端开发环境

```bash
cd frontend
npm install
npm run dev
```

默认访问地址：

```text
http://localhost:5173
```

### 7. 可选：启动网关

如果你想把 Agent 接到聊天渠道，而不只是使用本地 Web UI，可以继续启动：

```bash
tokenmind gateway
```

## Web 控制台

当前 Web UI 已经覆盖了日常使用的核心能力：

- 最近会话列表、搜索、重命名、删除
- 流式回复与停止生成
- 工具执行时间线与审批
- 设置中心
- 记忆中心
- 定时任务
- 文件中心
- 知识库总览、详情、资料上传、检索配置

如果你只是想先把项目跑起来，最简单的流程是：

1. 完成模型 API Key 配置
2. 启动 `tokenmind web --port 8080`
3. 打开 `http://localhost:5173`
4. 在设置中心里完成模型和运行时配置

## 知识库

`TokenMind` 内置了轻量知识库能力，并且和聊天会话直接打通。

支持的能力包括：

- 新建多个知识库
- 每个知识库上传多种格式资料
- 文档切块、Embedding、Rerank、混合检索
- 聊天输入框下方手动“链接知识库”
- 只在用户主动链接后参与回答
- 回答附来源引用

支持的资料类型包括：

- `pdf`
- `docx`
- `pptx`
- `xlsx`
- `md`
- `txt`
- 图片类资料（依赖解析链）

默认向量后端支持：

- `Qdrant`
- `SQLite`（轻量兜底）

Embedding 与 Rerank 模型支持用户自定义配置。

## 模型与配置

你可以通过两种方式管理模型配置：

- 在 Web UI 的设置中心里直接配置 Provider、模型、API Key 与运行时参数
- 手动编辑 `~/.tokenmind/config.json`

当前常见提供商包括但不限于：

| Provider | 示例模型 |
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

`TokenMind` 原生支持 MCP 服务接入，工具会自动注册到 Agent 工具集。

支持的接入方式：

- `stdio`
- `sse`
- `streamableHttp`

接入后会暴露为统一工具名，例如：

```text
mcp_minimax_web_search
mcp_minimax_understand_image
```

你可以在设置中心里：

- 管理 MCP 服务配置
- 限制暴露工具范围
- 查看连通状态
- 刷新并查看工具列表

## 项目结构

```text
TokenMind/
├─ tokenmind/                 # Python 后端主包
│  ├─ agent/                 # Agent 主循环、上下文构建、工具系统
│  ├─ bus/                   # 消息总线与队列
│  ├─ channels/              # 聊天渠道接入
│  ├─ cli/                   # 命令行入口
│  ├─ config/                # 配置模型与加载逻辑
│  ├─ cron/                  # 定时任务
│  ├─ knowledge/             # 知识库与检索
│  ├─ providers/             # 模型提供商实现
│  ├─ server/                # FastAPI、WebSocket、Web channel
│  ├─ session/               # 会话与历史持久化
│  └─ skills/                # 内置技能
├─ frontend/                 # React + Vite Web UI
├─ bridge/                   # Node 渠道桥接服务
├─ tests/                    # 后端测试
├─ README.md
└─ pyproject.toml
```

## 开发

### 后端

```bash
pip install -e ".[dev]"
pytest -q
ruff check tokenmind/
```

### 前端

```bash
cd frontend
npm install
npm run dev
npm run build
```

### Bridge

```bash
cd bridge
npm install
npm run build
```

## 适合什么场景

`TokenMind` 比较适合这些使用方式：

- 想要一套能长期演进的个人 AI 助手框架
- 想把多模型、多工具、多渠道统一到同一个运行时
- 想做本地优先、私有部署的 Agent 工作台
- 想把知识库、记忆、会话、MCP 和工具链放到一个项目里统一管理

## 文档

- [架构说明](CLAUDE.md)
- [安全说明](SECURITY.md)
- [技能说明](tokenmind/skills/README.md)

## License

MIT
