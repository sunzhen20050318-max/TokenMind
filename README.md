<p align="center">
  <img src="tokenmind-logo.png" alt="TokenMind logo" width="920" />
</p>

<h1 align="center">TokenMind</h1>

<p align="center">
  <b>本地优先的 AI Agent 工作台</b><br/>
  多模型 · 工具调用 · MCP · 知识库（RAG / Wiki）· 浏览器自动化 · 语音输入 · 定时任务，一套统一运行时。
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
  <b>简体中文</b> ·
  <a href="README.en.md">English</a>
</p>

---

`TokenMind` 不是又一个聊天机器人，而是一套可持续扩展的 **Agent 运行时与工作台**：统一接入主流大模型，在对话里调用工具、读知识库、操作浏览器、跑定时任务，并把这一切放进一个本地优先、可私有部署的 Web 控制台。适合搭建你自己的个人 AI 助手，也适合团队内做私有化 Agent 平台。

## ✨ 核心特性

- 🧠 **多模型统一接入** —— 13+ Provider（OpenAI / Anthropic / Gemini / DeepSeek / Qwen / GLM / Kimi / MiniMax / Ollama / OpenRouter / SiliconFlow…），`<provider>/<model>` 路由，主模型失败时**自动故障转移（fallback）**并带熔断器。
- 🛠️ **会话内工具调用** —— Shell 执行、文件读写、Web 搜索/抓取、定时任务、子智能体（spawn）、图片生成；高风险动作走**人工审批 + 审计日志**。
- 🧩 **MCP 原生支持** —— `stdio` / `SSE` / `streamableHTTP` 三种传输，工具自动注册，可限制单服务暴露范围。
- 📚 **双模式知识库** —— RAG 向量召回 + Rerank，或 Wiki 图谱编译；PDF / DOCX / PPTX 结构化解析，可选 **VLM 视觉解析**复杂图表页。
- 🌐 **浏览器自动化** —— 通过 OpenCLI 驱动你本地**已登录**的 Chrome 完成网页任务，长任务支持中途交还控制权。
- 🎙️ **语音输入** —— 麦克风一键转写，本地 `faster-whisper`（离线、免密钥）或 Groq 云端 Whisper。
- 💬 **多渠道接入** —— Telegram · 飞书 · 钉钉 · 企业微信 · QQ · 邮件 · 微信公众号 · WhatsApp（Node Bridge）。
- 🗂️ **记忆 / 项目 / 会话** —— 长期记忆按 token 阈值自动整理、项目工作区分组、流式回复、工具时间线、上下文余量可视化。
- 🔒 **本地优先** —— 配置与数据留在本机（`~/.tokenmind/`），内置 SSRF / 内网 IP 守卫。

## 📑 目录

- [🚀 快速开始](#快速开始)
- [🏗️ 架构概览](#架构概览)
- [🧠 模型与 Provider](#模型与-provider)
- [📚 知识库](#知识库)
- [🧩 工具与 MCP](#工具与-mcp)
- [🌐 浏览器自动化](#浏览器自动化)
- [🎙️ 语音输入](#语音输入)
- [💬 外部渠道](#外部渠道)
- [🖥️ Web 控制台](#web-控制台)
- [🛠️ 内置技能](#内置技能)
- [📦 桌面安装包](#桌面安装包)
- [💻 开发](#开发)
- [📁 项目结构](#项目结构)
- [📖 文档](#文档)
- [📄 License](#license)

## 快速开始

### 环境要求

- Python **3.11+**
- Node.js **20+**（源码运行 Web UI、改前端、跑 WhatsApp Bridge 需要）
- **可选** LibreOffice：解析 `.doc` / `.ppt` 旧格式时需要
- **可选** OpenCLI：启用浏览器自动化工具时需要
- 推荐使用独立虚拟环境

### 方式一：pip 安装（推荐）

```bash
pip install tokenmind-ai
tokenmind onboard          # 初始化配置 → ~/.tokenmind/config.json
tokenmind web --port 18888 # 启动后端 + Web UI
```

打开 <http://localhost:18888>。pip 包已内置前端构建产物，开箱即用。

### 方式二：源码运行

**macOS / Linux**

```bash
git clone https://gitee.com/sun124578963_0/TokenMind.git
cd TokenMind

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .

tokenmind onboard

# 源码用户需先 build 前端
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

> 若浏览器返回 `{"detail":"Not Found"}`，多半是 `frontend/dist` 没生成，回到 `frontend` 重新 `npm run build` 即可。

### 配置模型 API Key

打开 Web UI → **设置中心 → 模型**：

1. 在 **Providers** 选择提供商（OpenAI / Anthropic / DeepSeek…）
2. 填入 API Key，按需填 Base URL
3. 在 **Models** 启用要用的模型
4. 切到聊天页即可使用

也可直接编辑 `~/.tokenmind/config.json` 的 `providers.<name>.api_key`。

### 常用命令

| 命令 | 说明 |
|---|---|
| `tokenmind onboard` | 初始化向导，生成 `~/.tokenmind/config.json` |
| `tokenmind web --port 18888` | 启动 FastAPI + Web UI |
| `tokenmind agent` | 无界面 CLI 交互式 Agent（REPL） |
| `tokenmind gateway` | 启动外部渠道网关（Telegram / 邮件 / 飞书…） |
| `tokenmind status` | 配置 / 提供商 / 渠道诊断 |
| `tokenmind channels status` | 列出已配置渠道及其状态 |
| `tokenmind channels login` | 交互式登录某个渠道 |
| `tokenmind plugins list` | 列出已安装 / 发现的插件 |
| `tokenmind provider login` | 交互式配置 OAuth / API Key |

## 架构概览

<p align="center">
  <img src="tokenmind-arch.png" alt="TokenMind architecture" width="920" />
</p>

核心数据链路：

```
Web UI / Channel → MessageBus → AgentLoop → Providers + Tools → Session / Memory / Knowledge → WebSocket / Channel Output
```

项目由三部分组成：

- **Python 后端** —— Agent 运行时、配置、知识库、记忆、会话、图片生成、API
- **React 前端** —— 聊天、设置中心、知识库、文件中心、记忆中心、定时任务、资产库
- **Node Bridge** —— WhatsApp 等需要 Web/原生 SDK 的渠道桥接

## 模型与 Provider

`<provider>/<model>` 形式路由；也可在配置里固定默认 Provider。主模型返回错误时，会按 `fallback_models` 顺序透明切换备用模型，主模型连续失败会被熔断器临时跳过。

| Provider | 示例模型 |
| --- | --- |
| Anthropic | `claude-opus-4-5` / `claude-sonnet-4-5` |
| OpenAI | `gpt-4o` / `gpt-4o-mini` |
| Gemini | `gemini-2.0-flash` |
| DeepSeek | `deepseek-chat` / `deepseek-reasoner` |
| Qwen (DashScope) | `qwen-max` / `qwen-vl-max` |
| GLM (Zhipu) | `glm-4-plus` |
| Moonshot | `kimi-k2.5` |
| MiniMax | `MiniMax-Text-01` |
| MiMo | 小米 MiMo 思考模型 |
| OpenRouter | `anthropic/claude-sonnet-4-5` 等聚合路由 |
| SiliconFlow | `Qwen/Qwen2.5-7B-Instruct` 等 |
| Ollama | `llama3.2` / 本地任意模型 |
| Custom | 任何 OpenAI 协议兼容网关 |

- 默认模型：`anthropic/claude-opus-4-5`
- 默认上下文窗口：`262144`（256k，软压缩阈值，超过自动整理记忆）
- DeepSeek / MiMo 等思考模型需要严格的 `reasoning_content` 配套，切换时 TokenMind 会自动清理历史里不合规的 legacy 段，无需手动处理

## 知识库

内置两种模式，共用同一套文档解析器 + 可选 VLM 视觉解析：

| 模式 | 适用场景 |
|---|---|
| **RAG** | 向量召回 + Rerank，适合 FAQ / 文档问答 / 引用回答 |
| **Wiki** | LLM 把上传资料编译成 Markdown source page + entity / topic 图谱，可视化浏览，适合知识管理与盘点 |

**支持的资料类型**

- `PDF` —— pymupdf 抽文本；复杂页（无文字 + 大图）可选喂 VLM 生成图文描述
- `DOCX` —— python-docx，保留段落 / 标题层级 / 表格 / 嵌套表格
- `DOC` —— 经本地 LibreOffice (`soffice`) 转 `.docx` 后处理
- `PPTX` —— python-pptx，按 slide 分页 + title 单独标记 + shape 按位置排序
- `PPT` —— 同上经 LibreOffice 转 `.pptx`
- `MD / TXT / JSON / YAML / CSV / RST / LOG` 等 —— UTF-8 直读

> `.doc` / `.ppt` 旧格式需本机安装 LibreOffice；未安装时文档标记为 failed 并提示安装。
> 电子表格（`xlsx` / `xls`）有意不支持 —— 单元格格式损失会让文本抽取不可靠。

**向量后端**：`Qdrant`（默认）或 `SQLite`（轻量兜底，无需额外服务）。Embedding / Rerank / VLM 模型由用户自配。

## 工具与 MCP

会话中可调用的内置工具：

| 工具 | 用途 |
|---|---|
| `exec` | Shell 命令执行（高风险动作需审批） |
| `read_file` / `write_file` / `edit_file` / `list_dir` | 文件读写与浏览 |
| `web_search` / `web_fetch` | 联网搜索与网页抓取（带 SSRF 守卫） |
| `cron` | 定时任务管理（补跨 + 周期心跳调度） |
| `spawn` | 派生子智能体处理子任务 |
| `generate_image` | 图片生成 |
| `message` / `deliver_attachment` | 主动发消息 / 向用户投递文件 |
| `browser` | 浏览器自动化（需 OpenCLI，详见下文） |
| `task_list` / `ask_user_question` | 任务清单 / 向用户提问 |
| `wiki_index` / `wiki_grep` | Wiki 知识库检索 |

**MCP**：原生支持 MCP 工具协议，工具自动注册为 `mcp_<server>_<tool>`。在 **设置中心 → MCP** 可通过表单或 JSON 批量导入、限制单服务暴露的工具范围、查看连通状态、刷新工具列表。支持 `stdio` / `sse` / `streamableHttp` 三种传输。

## 浏览器自动化

`browser` 工具通过外部 **OpenCLI** 驱动你本地**已登录**的 Chrome，完成需要登录态的网页任务（查资料、填表单、抓取页面内容等）。

- 仅当系统检测到 `opencli` 可执行文件时才暴露该工具（避免无谓占用上下文）
- Web UI 提供一键安装、站点档案管理（`/api/browser/*`）
- 长任务可中途把控制权交还用户（点「我搞定了」继续）

## 语音输入

Web UI 麦克风按钮把语音转成文字：

- **本地**（默认）：`faster-whisper`，离线、免 API Key —— 安装 `asr` 额外依赖即可：`pip install "tokenmind-ai[asr]"`
- **云端**：Groq Whisper —— 读取 `GROQ_API_KEY` 或配置中的密钥

在 **设置中心** 切换后端与模型（faster-whisper 大小 / 设备 / 计算精度 / 语言）。单次音频上限 25 MB。

## 外部渠道

把 Agent 接到外部 IM / 邮件：

```bash
tokenmind gateway
```

支持渠道：**Telegram · 飞书 · 钉钉 · 企业微信 · QQ · 邮件 · 微信公众号 · WhatsApp**。在 **设置中心 → 外部渠道** 配置各渠道凭据。WhatsApp 走 Node Bridge：

```bash
cd bridge && npm install && npm run build   # 启动后扫码登录
```

## Web 控制台

侧边栏分组：

- **聊天** —— 会话列表 / 搜索 / 重命名 / 删除 / 流式回复 / 工具时间线 / 停止生成 / 上下文余量环
- **知识库** —— 多知识库管理；RAG 与 Wiki 两种模式
- **资产库** —— 图片生成产物的统一视图
- **项目** —— 把多个会话归到同一项目下
- **更多** —— 定时任务 · Token 用量
- **设置中心**
  - 模型 —— 提供商 / API Key / 默认模型 / fallback；知识库 Embedding · Rerank · VLM
  - 工具 —— Web 搜索 · Shell exec · 上传策略 · 知识库切片
  - MCP —— 服务列表 · 工具可见范围 · JSON 导入
  - 外部渠道 —— 各渠道凭据与在线状态
  - 技能 —— 启用 / 停用内置技能
  - 服务 —— Web 监听 host / port · 渠道消息行为
  - 记忆中心 —— 长期记忆编辑 · 当前上下文 · 近期归档
  - 文件中心 —— 上传清单 · 配额 · 清理策略

## 内置技能

内置在 `tokenmind/skills/`，发现即可用：

| Skill | 用途 |
|---|---|
| `documents` | 创建 / 编辑 / 红线 / 比对 / 渲染 DOCX，含 30+ python-docx 脚本与 OOXML 参考 |
| `presentations` | 构建可编辑 PPTX，模板 / 设计系统 / 渲染脚本齐备 |
| `memory` | 长期记忆与归档操作 |
| `cron` | 定时任务管理 |
| `github` | gh CLI 包装的 GitHub 操作 |
| `weather` | wttr.in / Open-Meteo 天气查询 |
| `summarize` | URL / 文件 / 视频摘要 |
| `tmux` | 远程 tmux 会话控制 |
| `skill-creator` | 创建新 skill 的脚手架 |
| `clawhub` | 从 ClawHub 注册中心搜索安装第三方 skill |

技能依赖（python 包 / 二进制 / 环境变量）会在 **设置中心 → 技能** 自动检测，缺失时显示安装提示。

## 桌面安装包

可把 TokenMind 打包成普通用户双击即用的桌面程序，用户无需安装 Node.js。

**Windows（PyInstaller + Inno Setup）**

```powershell
python -m pip install ".[windows]"
.\packaging\windows\build-installer.ps1
```

产出 `dist-installer\TokenMindSetup-<版本>.exe`。只测 PyInstaller 不生成安装包：加 `-SkipInstaller`。

**macOS（PyInstaller + DMG）**

```bash
python -m pip install ".[macos]"
./packaging/macos/build.sh
```

## 开发

**后端**

```bash
python -m pip install -e ".[dev]"
pytest                     # asyncio_mode=auto
ruff check tokenmind/
ruff format tokenmind/
```

**前端**

```bash
cd frontend
npm install
npm run dev          # 开发模式 http://localhost:5173（API 代理到后端 18888）
npm run build        # 生产构建到 frontend/dist
npm run test:unit    # 纯逻辑单测
```

**Bridge**

```bash
cd bridge && npm install && npm run build
```

## 项目结构

```text
TokenMind/
├─ tokenmind/                # Python 后端主包
│  ├─ agent/                 # Agent 主循环、上下文构建、工具系统、技能、子智能体
│  ├─ bus/                   # 消息总线与事件
│  ├─ channels/              # 聊天渠道接入（Telegram / 飞书 / 钉钉 / QQ / 邮件 …）
│  ├─ cli/                   # 命令行入口 + onboarding 向导
│  ├─ config/               # 配置 schema (pydantic) 与加载逻辑
│  ├─ creative/              # 图片生成
│  ├─ cron/                  # 定时任务服务
│  ├─ integrations/opencli/  # 浏览器自动化（OpenCLI 驱动）
│  ├─ knowledge/             # 知识库：解析 / 切片 / wiki 编译 / 向量检索
│  ├─ providers/             # 模型提供商实现 + fallback + 用量统计
│  ├─ security/              # SSRF / 内网 IP 守卫
│  ├─ server/                # FastAPI、WebSocket、路由、附件、Web channel
│  ├─ session/               # 会话与历史持久化
│  ├─ skills/                # 内置技能
│  └─ templates/             # AGENTS.md / MEMORY 等工作区模板
├─ frontend/                 # React + Vite Web UI
├─ bridge/                   # Node 渠道桥接（WhatsApp）
├─ tests/                    # 后端测试
├─ packaging/                # Windows / macOS 安装包构建
├─ README.md
└─ pyproject.toml
```

## 文档

- [架构详解 (CLAUDE.md)](CLAUDE.md)
- [架构详解 (AGENTS.md)](AGENTS.md) —— 与 CLAUDE.md 同步，给非 Claude 系 Coding Agent 使用
- [安全说明](SECURITY.md)
- [技能开发说明](tokenmind/skills/README.md)

## License

[MIT](LICENSE)
