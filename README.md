# TokenMind

<p align="center">
  <img src="tokenmind-logo.png" alt="TokenMind logo" width="920" />
</p>

<p align="center">
  面向个人与团队的本地优先 AI Agent 工作台。聊天、多模型、工具调用、MCP、知识库（RAG / Wiki）、视觉解析、创意生成、定时任务，一套统一运行时。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-111111?style=flat-square" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/FastAPI-Backend-222222?style=flat-square" alt="FastAPI Backend" />
  <img src="https://img.shields.io/badge/React-Vite%20UI-333333?style=flat-square" alt="React Vite UI" />
  <img src="https://img.shields.io/badge/MCP-Ready-444444?style=flat-square" alt="MCP Ready" />
  <img src="https://img.shields.io/badge/Knowledge%20Base-RAG%20%2B%20Wiki-555555?style=flat-square" alt="Knowledge Base" />
  <img src="https://img.shields.io/badge/License-MIT-666666?style=flat-square" alt="MIT License" />
</p>

## 项目简介

`TokenMind` 是一个本地优先的 AI Agent 框架，目标不是只做一个聊天机器人，而是提供一套可持续扩展的 Agent 运行时与工作台：

- 统一接入主流模型与推理提供商（OpenAI / Anthropic / Gemini / DeepSeek / 国产多家 / Ollama / 自定义兼容接口）
- 在会话中调用文件、Shell、Web 搜索、定时任务、MCP 等工具，含高风险动作审批
- 提供 RAG + Wiki 两种知识库模式，可选视觉模型（VLM）解析复杂 PDF 与 Office 内嵌图
- 内置创意生成（图像 / 音乐 / TTS / 语音克隆 / 音色设计 / 视频）
- 完整 Web 控制台管理会话、模型、知识库、文件、定时任务、外部渠道、MCP 服务

适合搭建你自己的个人 AI 助手，也适合在团队内做私有化 Agent 工作台。

## 核心能力

| 维度 | 内容 |
|---|---|
| **多模型** | OpenAI · Anthropic · Gemini · DeepSeek · MiniMax · MiMo · OpenRouter · Ollama · SiliconFlow · Qwen (DashScope) · GLM (Zhipu) · Moonshot · 自定义兼容接口 |
| **知识库** | RAG 与 Wiki 两种模式；结构化文档解析（PDF / DOCX / DOC / PPTX / PPT / MD / TXT）；可选 VLM 视觉解析；Embedding + Rerank + 混合检索；来源引用 |
| **工具** | `exec`（Shell）· 文件读写 · Web 搜索 · 定时任务（Cron）· 消息发送 · 附件投递 · MCP 工具自动注册 · 子智能体（spawn）· 图片生成 |
| **创意服务** | 图像生成 · 音乐生成 · TTS · 语音克隆 · 音色设计 · 视频（MiniMax 后端） |
| **MCP** | `stdio` / `sse` / `streamableHttp` 三种传输；可限制单个服务暴露的工具范围 |
| **记忆** | 长期记忆 `MEMORY.md` + 滚动归档 `HISTORY.md`；按 token 阈值自动整理 |
| **会话** | 项目工作区（按项目分组会话）· 流式回复 · 工具时间线 · 高风险动作审批 · 审计日志 |
| **外部渠道** | Telegram · 飞书 · 钉钉 · 企业微信 · QQ · 邮件 · 微信公众号 · WhatsApp（通过 Node Bridge） |
| **跨平台** | macOS / Linux / Windows，含 PyInstaller + Inno Setup 一体化安装包 |

## 架构概览

<p align="center">
  <img src="tokenmind-arch.png" alt="TokenMind architecture" width="920" />
</p>

核心链路：

`Web UI / Channel → MessageBus → AgentLoop → Providers + Tools → Session / Memory / Knowledge → WebSocket / Channel Output`

主要由三部分组成：

- **Python 后端**：Agent 运行时、配置、知识库、记忆、会话、创意服务、API
- **React 前端**：聊天、设置中心、知识库、文件中心、记忆中心、定时任务、创意工作台
- **Node Bridge**：WhatsApp 等需要 Web/原生 SDK 的渠道桥接

## 快速开始

### 1. 环境要求

- Python `3.11+`
- Node.js `20+`（源码运行 Web UI、改前端、跑 WhatsApp Bridge 需要）
- **可选** LibreOffice：解析 `.doc` / `.ppt` 旧格式 + 知识库文档预览要用
- 推荐使用独立虚拟环境

### 2. 克隆并安装

**Windows PowerShell**

```powershell
git clone https://gitee.com/sun124578963_0/TokenMind.git
cd TokenMind

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install -U pip
python -m pip install -e .
```

**macOS / Linux**

```bash
git clone https://gitee.com/sun124578963_0/TokenMind.git
cd TokenMind

python3.11 -m venv .venv
source .venv/bin/activate

python -m pip install -U pip
python -m pip install -e .
```

### 3. 初始化配置

```bash
tokenmind onboard
```

会在 `~/.tokenmind/config.json` 生成默认配置。

### 4. 启动 Web UI

`pip install tokenmind-ai` 安装的用户前端构建产物已经打包进 Python 包里；`git clone` 源码用户需要自己先 build 前端。

**A. pip 安装 / 桌面安装包**

```bash
tokenmind web --port 18888
```

打开 `http://localhost:18888`。如果 18888 被占，换个空闲端口即可（同时改浏览器地址）。

**B. 源码生产模式**

```bash
cd frontend
npm install
npm run build
cd ..
tokenmind web --port 18888
```

打开 `http://localhost:18888`。如果浏览器返回 `{"detail":"Not Found"}`，多半是 `frontend/dist` 没生成；回到 `frontend` 重新跑 `npm run build`。

**C. 源码开发模式（边改边看）**

两个终端：

```bash
# 终端 1：后端
tokenmind web --port 18888

# 终端 2：前端
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`。Vite 会把 API 请求代理到后端 18888。如果后端用了别的端口（例如 3000）：

```bash
# PowerShell
$env:TOKENMIND_API_PROXY="http://localhost:3000"
npm run dev

# bash
TOKENMIND_API_PROXY=http://localhost:3000 npm run dev
```

### 5. 配置模型 API Key

打开 Web UI，进入 **设置中心 → 模型**：

1. 在 **Providers** 选择要用的提供商（OpenAI / Anthropic / DeepSeek 等）
2. 填入 API Key，可选填 Base URL
3. 在 **Models** 启用要用的模型
4. 切到聊天页就能用了

也可以直接编辑 `~/.tokenmind/config.json`，在 `providers.<name>.api_key` 填值。

### 6. 可选：启用 VLM 视觉解析

如果知识库里要解析复杂 PDF、图表型文档、Office 内嵌图，去 **设置中心 → 模型 → 知识库模型 → VLM (视觉解析)** 配置：

- 模型：任意 OpenAI 协议兼容的视觉模型（推荐 `Qwen/Qwen2.5-VL-7B-Instruct`、`gpt-4o-mini`、`gemini-1.5-flash` 等）
- API Key + Base URL
- 并发线程数（默认 8，控制单文档峰值 API 花费）

留空 = 关闭，知识库回退到纯文本解析。

### 7. 可选：启动外部渠道网关

如果想把 Agent 接到 Telegram / 飞书 / 钉钉等外部渠道：

```bash
tokenmind gateway
```

在 **设置中心 → 外部渠道** 配置各渠道凭据。

### 8. 可选：WhatsApp Bridge

```bash
cd bridge
npm install
npm run build
```

启动后扫码登录。

## Windows 安装包构建

把 TokenMind 做成普通用户可双击安装的 Windows 程序，用仓库内置的 `PyInstaller + Inno Setup` 流程。

构建机器准备：

- Python 3.11+
- Node.js 20+
- Inno Setup 6
- PyInstaller：`python -m pip install ".[windows]"`

然后：

```powershell
.\packaging\windows\build-installer.ps1
```

若 PowerShell 执行策略拦截：

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\windows\build-installer.ps1
```

脚本会：

1. 构建 `frontend/dist`
2. 用 PyInstaller 生成 `dist-windows\TokenMind\TokenMind.exe`
3. 用 Inno Setup 生成安装包 `dist-installer\TokenMindSetup-版本号.exe`

最终交给用户的就是 `dist-installer` 里的单个安装包。用户不需要装 Node.js。

只测 PyInstaller、不生成安装包：

```powershell
.\packaging\windows\build-installer.ps1 -SkipInstaller
```

## Web 控制台

侧边栏分组：

- **聊天** — 会话列表 / 搜索 / 重命名 / 删除 / 流式回复 / 工具时间线 / 停止生成
- **知识库** — 多个知识库管理；RAG 与 Wiki 两种模式
- **资产库** — 创意生成产物（图片 / 音乐 / 语音 / 视频）的统一视图
- **项目** — 把多个会话归到同一项目下
- **更多** — 音乐 · 声音克隆 · 语音合成 · 音色设计 · 视频 · 定时任务 · Token 用量
- **设置中心**：
  - 模型 — 提供商 / API Key / 默认模型；知识库 Embedding · Rerank · VLM
  - 工具 — Web 搜索 · Shell exec · 上传策略 · 知识库切片
  - MCP — 服务列表 · 工具可见范围 · JSON 导入
  - 外部渠道 — Telegram / 飞书 / 钉钉 / 企业微信 / QQ / 邮件 / WhatsApp / 公众号
  - 技能 — 启用 / 停用内置技能
  - 服务 — Web 服务监听 host / port · 外部渠道消息行为
  - 记忆中心 — 长期记忆编辑 · 当前上下文 · 近期归档
  - 文件中心 — 上传文件清单 · 配额 · 清理策略

子页编辑器都以右侧抽屉形式打开，不会内联在卡片下方。

## 知识库

`TokenMind` 内置两种知识库模式，**同一文档解析器** + **可选 VLM 视觉解析**：

| 模式 | 适用场景 |
|---|---|
| **RAG** | 经典向量召回 + Rerank，适合 FAQ / 文档问答 / 引用回答 |
| **Wiki** | LLM 把上传资料编译成 Markdown source page + entity / topic 图谱，可视化浏览，适合知识管理与盘点 |

**支持的资料类型**：

- `PDF` — pymupdf (fitz) 抽文本；复杂页（无文字 + 有图，或文字 < 800 字 + 大图占页 > 5%）可选喂 VLM 生成图文描述
- `DOCX` — python-docx 保留段落 / 标题层级 / 表格 cell | cell 行 / 嵌套表格
- `DOC` — 调本地 LibreOffice (`soffice`) 转 `.docx` 后走 DOCX 路径
- `PPTX` — python-pptx 按 slide 分页 + title 单独标记 + shape 按位置排序
- `PPT` — 同上经 LibreOffice 转 `.pptx`
- `MD / TXT / JSON / YAML / CSV / RST / LOG` 等 — UTF-8 直读

`.doc` / `.ppt` 旧格式需要本机装好 LibreOffice。未安装时文档会标记 failed 并提示安装。

**向量后端**：

- `Qdrant`（默认）
- `SQLite`（轻量兜底，无需额外服务）

Embedding / Rerank / VLM 模型用户自配。

## 模型与配置

| Provider | 示例模型 |
| --- | --- |
| OpenAI | `gpt-4o` / `gpt-4o-mini` |
| Anthropic | `claude-opus-4-5` / `claude-sonnet-4-5` |
| Gemini | `gemini-2.0-flash` |
| DeepSeek | `deepseek-chat` / `deepseek-reasoner` / `deepseek-v4-pro` |
| MiniMax | `MiniMax-Text-01` / `MiniMax-M2.7` |
| MiMo | 小米 MiMo 思考模型 |
| OpenRouter | `anthropic/claude-sonnet-4-5` |
| Ollama | `llama3.2` / 本地任意模型 |
| SiliconFlow | `Qwen/Qwen2.5-7B-Instruct` / `Qwen/Qwen2.5-VL-7B-Instruct` |
| Qwen (DashScope) | `qwen-max` / `qwen-vl-max` |
| GLM (Zhipu) | `glm-4-plus` |
| Moonshot | `kimi-k2.5` |
| Custom | 任何 OpenAI 协议兼容的网关 |

默认模型：`anthropic/claude-opus-4-5`。默认 Web 服务监听端口：`18888`。

DeepSeek / MiMo 等思考模型需要严格 `reasoning_content` 配套，TokenMind 在切到这些模型时会自动清理历史里不合规的 legacy assistant + tool_calls 段，不需要手动处理。

## MCP 支持

原生支持 MCP 工具协议接入，工具会自动注册到 Agent。

支持的传输：`stdio` / `sse` / `streamableHttp`。

设置中心 → MCP 里：

- 通过表单或 JSON 批量导入
- 限制单个服务暴露的工具范围
- 查看连通状态
- 刷新工具列表

## 内置技能 (Skills)

内置在 `tokenmind/skills/` 里，发现即可用：

| Skill | 用途 |
|---|---|
| `documents` | 创建 / 编辑 / 红线 / 比对 / 渲染 DOCX，含 30+ 个 python-docx 脚本与 OOXML 参考 |
| `presentations` | 构建可编辑 PPTX，slide 模板 / 设计系统 / 渲染脚本一应俱全 |
| `memory` | 长期记忆与归档操作 |
| `cron` | 定时任务管理 |
| `github` | gh CLI 包装的 GitHub 操作 |
| `weather` | wttr.in / Open-Meteo 天气查询 |
| `summarize` | URL / 文件 / YouTube 视频摘要 |
| `tmux` | 远程 tmux 会话控制 |
| `skill-creator` | 创建新 skill 的脚手架 |
| `clawhub` | 从 ClawHub 注册中心搜索安装第三方 skill |

技能依赖（python 包 / 二进制 / 环境变量）会在 **设置中心 → 技能** 自动检测，缺失时显示安装提示。

## 项目结构

```text
TokenMind/
├─ tokenmind/                    # Python 后端主包
│  ├─ agent/                    # Agent 主循环、上下文构建、工具系统、技能加载、子智能体
│  ├─ bus/                      # 消息总线与事件
│  ├─ channels/                 # 聊天渠道接入（Telegram/飞书/钉钉/QQ/邮件/...）
│  ├─ cli/                      # 命令行入口 + onboarding 向导
│  ├─ config/                   # 配置 schema (pydantic) 与加载逻辑
│  ├─ creative/                 # 创意生成（图像 / 音乐 / TTS / 语音克隆 / 视频）
│  ├─ cron/                     # 定时任务服务
│  ├─ knowledge/                # 知识库：parsers / chunking / wiki 编译 / 向量检索
│  ├─ providers/                # 模型提供商实现
│  ├─ security/                 # SSRF / 内网 IP 守卫等安全工具
│  ├─ server/                   # FastAPI、WebSocket、路由、附件、Web channel
│  ├─ session/                  # 会话与历史持久化
│  ├─ skills/                   # 内置技能
│  ├─ templates/                # AGENTS.md / MEMORY 等工作区模板
│  └─ utils/                    # 跨平台 office (LibreOffice) 探测等共享工具
├─ frontend/                    # React + Vite Web UI
├─ bridge/                      # Node 渠道桥接服务（WhatsApp）
├─ tests/                       # 后端测试
├─ packaging/windows/           # Windows 安装包构建脚本
├─ README.md
└─ pyproject.toml
```

## 开发

### 后端

```bash
python -m pip install -e ".[dev]"
pytest -q
ruff check tokenmind/
```

### 前端

```bash
cd frontend
npm install
npm run dev          # 开发模式 http://localhost:5173
npm run build        # 生产构建到 frontend/dist
npm run test:unit    # 纯逻辑单测
```

### Bridge

```bash
cd bridge
npm install
npm run build
```

## 适合什么场景

- 想要一套能长期演进的个人 AI 助手框架
- 想把多模型、多工具、多渠道、多模态生成统一到同一个运行时
- 想做本地优先、私有部署的 Agent 工作台
- 想把知识库、记忆、定时任务、MCP、技能、文件管理放在一个项目里

## 文档

- [架构详解 (CLAUDE.md)](CLAUDE.md)
- [架构详解 (AGENTS.md)](AGENTS.md) — 与 CLAUDE.md 同步，给非 Claude 系 Coding Agent 使用
- [安全说明](SECURITY.md)
- [技能开发说明](tokenmind/skills/README.md)

## License

MIT
