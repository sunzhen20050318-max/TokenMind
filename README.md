# sun-agent

**sun-agent** 是一个轻量级的个人 AI 助手框架，支持多种聊天平台和 LLM 提供商。

![Architecture](sun-agent_arch.png)

## 主要特性

- **多平台支持**: Telegram, Discord, Feishu, WhatsApp, Slack, QQ, 等
- **多模型支持**: 支持 21 个 LLM 提供商（MiniMax, DeepSeek, OpenAI, Anthropic, Gemini, Groq 等）
- **工具系统**: 内置 Shell、文件系统、Web 搜索、消息、定时任务、MCP 等工具
- **Web UI**: React + Vite + Zustand 构建的实时聊天界面
- **会话管理**: 支持多会话、上下文记忆、历史持久化
- **技能系统**: 可扩展的 agent 技能（GitHub, Weather, Tmux, Cron 等）

## 快速开始

### 安装

```bash
pip install -e ".[dev]"
```

### 初始化配置

```bash
sun_agent onboard
```

### 启动 Web UI

```bash
sun_agent web --port 8080
```

### 启动 Gateway（连接聊天频道）

```bash
sun_agent gateway
```

## 配置模型

1. 打开 Web UI，点击侧边栏的模型选择器
2. 在设置中配置 API Key 和 API URL
3. 点击启用按钮切换模型

支持的模型提供商:

| 提供商 | 默认模型 |
|--------|---------|
| MiniMax | MiniMax-M2.7 |
| DeepSeek | deepseek-chat |
| OpenAI | gpt-4o |
| Anthropic | claude-sonnet-4-5 |
| Gemini | gemini-2.0-flash |
| Groq | llama-3.3-70b-versatile |
| SiliconFlow | Qwen/Qwen2.5-7B-Instruct |
| VolcEngine | doubao-1-5-pro-32k |
| ... | ... |

## 项目结构

```
sun_agent/
├── agent/          # 核心 Agent 逻辑
│   ├── loop.py     # Agent 主循环
│   ├── context.py  # Prompt 构建
│   └── tools/      # 内置工具
├── channels/       # 聊天平台集成
├── providers/      # LLM 提供商
├── server/         # FastAPI Web 服务器
├── session/        # 会话管理
└── skills/         # Agent 技能
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 代码检查
ruff check sun_agent/
```

## 文档

- [架构说明](CLAUDE.md)
- [贡献指南](CONTRIBUTING.md)
- [交流规范](COMMUNICATION.md)

## License

MIT
