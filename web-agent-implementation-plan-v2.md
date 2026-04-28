# TokenMind 浏览器智能体（Web Agent）模块 — 修订版实施方案 v2

> **本版本相对 v1 的变化**：基于 agent-browser 实际版本（v0.21+）的真实协议和能力修订。
> 取消 Docker 依赖，简化进程管理，明确所有 IPC 细节。

---

## 0. 关键决策（已确定，不要改）

### 0.1 技术选型决策

| 决策项 | 决定 | 原因 |
|--------|------|------|
| 浏览器引擎 | agent-browser CLI v0.21+ | 命令式接口、支持 refs、daemon 自管理 |
| 部署方式 | **不使用 Docker**，直接 npm install -g | 用户群是个人用户，TokenMind 是本地优先产品 |
| 进程管理 | **不需要自实现进程池** | agent-browser 自带 daemon 自动启动和复用 |
| 项目隔离 | 通过 `--session <project_id>` 标志 | agent-browser 原生支持 |
| 与后端通信 | subprocess 调用 + JSON 输出 | 不需要自己实现 socket 协议 |
| 实时画面 | **优先使用 agent-browser 自带 dashboard** | 默认端口 4848，自动流式 |

### 0.2 产品决策

| 决策项 | 决定 |
|--------|------|
| 浏览器实例隔离 | 按 TokenMind 项目隔离 |
| 单用户并发任务 | 默认 3 个，超出排队 |
| 单任务最大执行时长 | 默认 30 分钟，可调到最长 2 小时 |
| 失败处理 | 不自动重试，由用户决定 |
| 用户群定位 | 个人用户 |

---

## 1. agent-browser 协议参考（重要）

### 1.1 安装方式

用户首次使用时需要：

```bash
npm install -g agent-browser   # 或 brew install agent-browser
agent-browser install          # 下载 Chrome for Testing
```

TokenMind 应该在首次进入"浏览器智能体"页面时检测环境，缺失就引导安装。

### 1.2 命令调用模式（核心）

**重要：永远加 `--json` 标志获得结构化输出。**

```bash
# 基础格式
agent-browser --session <project_id> --json <command> [args]

# 例子
agent-browser --session proj_001 --json open https://github.com
agent-browser --session proj_001 --json snapshot -i
agent-browser --session proj_001 --json click @e3
agent-browser --session proj_001 --json fill @e1 "user@example.com"
agent-browser --session proj_001 --json screenshot
agent-browser --session proj_001 --json close
```

### 1.3 JSON 响应 schema

> **真实 schema（基于 v0.26.0 实测）**：用 `success` 字段而不是 `ok`，没有 `id`，
> 没有 `warning` 字段。命令成功时 `data` 是命令特定字典，失败时 `data: null`。

```json
{ "success": true, "data": { /* 命令特定数据 */ }, "error": null }
```

失败时：

```json
{ "success": false, "data": null, "error": "Element not found. Verify the selector is correct..." }
```

实测样本（v0.26.0）：

| 命令 | success 时 `data` |
|---|---|
| `open <url>` | `{title, url}` |
| `snapshot -i` | `{origin, refs: {e1: {name, role}, ...}, snapshot: "ascii tree"}` |
| `click @e<n>` | `{clicked: "@e<n>"}` |
| `screenshot <path>` | `{path: "/abs/path/to.png"}` — 写入文件，不返回 base64 |
| `close` | `{closed: true}` |
| `close --all` | `{closed: <count>, sessions: [<closed names>]}` |

### 1.3a `doctor --json` 例外

`doctor` 不走 `{success, data, error}` 包装，而是返回：

```json
{
  "success": true,
  "summary": { "pass": 8, "warn": 0, "fail": 0 },
  "fixed": [],
  "checks": [
    { "category": "Environment", "id": "env.version", "message": "...", "status": "pass" },
    { "category": "Security", "id": "security.encryption_key", "message": "...", "status": "info", "fix": "export AGENT_BROWSER_ENCRYPTION_KEY=..." }
  ]
}
```

`status` 取值：`pass | info | warn | fail`。`fix` 只在该 check 有自动修复命令时存在。

### 1.3b `batch` 响应

`batch` 返回数组（不带 `{success}` 外包装）：

```json
[
  { "command": ["open", "https://x"], "success": true, "result": {...}, "error": null },
  { "command": ["snapshot", "-i"],   "success": true, "result": {...}, "error": null }
]
```

注意：批量子项里 `result` 替代了 `data` 字段。

### 1.3c CLI 调用语法（实测修正）

- 命令以 **空格** 分隔的 args 直接传，不需要 JSON 数组：
  ```bash
  agent-browser --session proj --json batch 'open https://example.org' 'snapshot -i' 'close'
  ```
- 加 `--bail` 让批量遇错就停（默认全跑完）。
- `screenshot` 需要传输出路径，不指定时也能跑但默认输出到 `--screenshot-dir`。

### 1.4 snapshot 输出（关键）

snapshot 命令返回 accessibility tree 带 refs：

```
- heading "Example Domain" [ref=e1]
- paragraph [ref=e2]
- link "More information..." [ref=e3]
- button "Sign in" [ref=e4]
- textbox "Email" [ref=e5]
```

LLM 通过 ref（`@e1`、`@e3`、`@e5`）精确选择元素。比 CSS selector 和坐标都可靠。

### 1.5 ref 失效规则（必须遵守）

页面变化后 refs 失效。必须 re-snapshot：
- 页面跳转后
- 点击触发的 DOM 变化后
- 等待异步加载完成后

### 1.6 batch 命令（性能优化）

确定性的多步操作可以一次执行：

```bash
agent-browser --session proj_001 --json batch '[
  ["fill", "@e1", "user@example.com"],
  ["fill", "@e2", "password"],
  ["click", "@e3"]
]'
```

返回数组形式的结果。用于已知步骤序列的场景，省 subprocess 启动开销。

### 1.7 dashboard（可选利用）

```bash
agent-browser dashboard start --port 4848
```

启动后所有 session 自动 stream 到 dashboard。前端可以 iframe 嵌入。

> **iframe 嵌入实测可行**（v0.26.0）：dashboard 响应没有 `X-Frame-Options` 也没有
> `Content-Security-Policy: frame-ancestors`，并且 `Access-Control-Allow-Origin: *`。
> 可以直接 `<iframe src="http://localhost:4848" />` 嵌入到 TokenMind 前端，不需要降级方案。

---

## 2. 整体架构（修订版）

```
┌──────────────────────────────────────────────────────────────┐
│  前端层                                                       │
│  ┌──────────────────┐ ┌──────────────────┐ ┌─────────────┐  │
│  │ 浏览器智能体页面  │ │ 普通聊天窗口      │ │ 侧边栏入口   │  │
│  └──────────────────┘ └──────────────────┘ └─────────────┘  │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│  API 层 (TokenMind 后端新增)                                  │
│  ┌──────────────────┐ ┌──────────────────┐ ┌─────────────┐  │
│  │ REST 路由         │ │ WebSocket        │ │ 工具注册     │  │
│  └──────────────────┘ └──────────────────┘ └─────────────┘  │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│  业务层 (核心模块)                                            │
│  ┌──────────────────┐ ┌──────────────────┐ ┌─────────────┐  │
│  │ TaskService      │ │ AgentBrowserCLI  │ │ ArtifactStore│ │
│  │ 任务生命周期      │ │ 封装 subprocess  │ │ 产物落地     │  │
│  └──────────────────┘ └──────────────────┘ └─────────────┘  │
│  ┌──────────────────┐ ┌──────────────────┐                   │
│  │ EnvironmentCheck │ │ StuckDetector    │                   │
│  │ 检测安装状态      │ │ 检测需要接管      │                   │
│  └──────────────────┘ └──────────────────┘                   │
└──────────────────────────────────────────────────────────────┘
                              │
                    subprocess (CLI 调用)
                              │
┌──────────────────────────────────────────────────────────────┐
│  agent-browser CLI (用户本地安装)                             │
│  ↓ 自动管理                                                   │
│  agent-browser daemon (per session)                          │
│  ↓ CDP                                                       │
│  Chromium                                                    │
└──────────────────────────────────────────────────────────────┘
```

**与 v1 的关键区别**：
- ❌ 删除 SessionPool（agent-browser 自管理 daemon）
- ❌ 删除 docker-compose.yml 修改
- ❌ 删除自定义 IPC 协议代码
- ✅ 新增 EnvironmentCheck 模块（检测安装状态）
- ✅ AgentBrowserCLI 简化为纯 subprocess 封装

---

## 3. 模块结构（修订版）

### 3.1 后端

```
tokenmind/
└── browser_agent/                          # 新增模块
    ├── __init__.py
    ├── cli.py                              # AgentBrowserCLI: subprocess 封装
    ├── env_check.py                        # 检测 agent-browser 是否安装
    ├── task_service.py                     # TaskService: 任务生命周期与执行循环
    ├── stuck_detector.py                   # StuckDetector: 检测需要接管的场景
    ├── artifact_store.py                   # ArtifactStore: 产物落地
    ├── tools.py                            # 浏览器工具集 (注册到 TokenMind 工具系统)
    ├── models.py                           # Pydantic 模型: Task / Step / Artifact
    ├── storage.py                          # SQLite 存储层
    └── prompts.py                          # LLM 提示词模板

tokenmind/server/routes/
└── browser_tasks.py                        # 新增 REST 路由

tokenmind/server/websocket/
└── browser_stream.py                       # 新增 WebSocket 处理器
```

### 3.2 前端

```
frontend/src/
├── pages/
│   ├── BrowserAgent.tsx                    # 主页面 (任务列表 + 输入)
│   ├── BrowserTaskDetail.tsx               # 任务详情 / 历史回放
│   ├── BrowserTaskRunning.tsx              # 正在执行视图 (含可视化接管)
│   ├── BrowserAgentSetup.tsx               # 环境检测 + 安装引导（新增）
│   └── browserAgent.css
├── services/
│   └── browserAgent.ts
└── stores/
    └── browserAgentStore.ts
```

### 3.3 配置文件修改

```
项目根目录/
├── pyproject.toml                          # 修改 (添加 aiohttp 依赖)
└── tokenmind/server/routes/__init__.py     # 修改 (注册新路由)
└── tokenmind/server/app.py                 # 修改 (include 新路由)
```

**没有 Docker 改动。** 不需要修改 docker-compose.yml（如果项目根目录有的话），也不需要新建。

---

## 4. 数据模型

（与 v1 相同，三张 SQLite 表，写入 TokenMind 现有的 SQLite 数据库文件）

### 4.1 `browser_tasks` 表

```sql
CREATE TABLE IF NOT EXISTS browser_tasks (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    session_id      TEXT,
    instruction     TEXT NOT NULL,
    start_url       TEXT,
    status          TEXT NOT NULL,
    result_summary  TEXT,
    error_detail    TEXT,
    created_at      INTEGER NOT NULL,
    started_at      INTEGER,
    finished_at     INTEGER,
    step_count      INTEGER DEFAULT 0,
    max_steps       INTEGER DEFAULT 50,
    timeout_seconds INTEGER DEFAULT 1800,
    metadata        TEXT
);

CREATE INDEX IF NOT EXISTS idx_browser_tasks_project_status 
    ON browser_tasks(project_id, status);
CREATE INDEX IF NOT EXISTS idx_browser_tasks_created 
    ON browser_tasks(created_at DESC);
```

### 4.2 `browser_steps` 表

```sql
CREATE TABLE IF NOT EXISTS browser_steps (
    id                      TEXT PRIMARY KEY,
    task_id                 TEXT NOT NULL,
    step_index              INTEGER NOT NULL,
    phase                   TEXT NOT NULL,
    action_name             TEXT,
    action_args             TEXT,
    thinking                TEXT,
    observation             TEXT,
    screenshot_artifact_id  TEXT,
    success                 INTEGER NOT NULL,
    error                   TEXT,
    duration_ms             INTEGER,
    timestamp               INTEGER NOT NULL,
    FOREIGN KEY (task_id) REFERENCES browser_tasks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_browser_steps_task 
    ON browser_steps(task_id, step_index);
```

### 4.3 `browser_artifacts` 表

```sql
CREATE TABLE IF NOT EXISTS browser_artifacts (
    id                  TEXT PRIMARY KEY,
    task_id             TEXT NOT NULL,
    step_index          INTEGER,
    kind                TEXT NOT NULL,
    file_path           TEXT NOT NULL,
    source_url          TEXT,
    mime_type           TEXT,
    size_bytes          INTEGER,
    created_at          INTEGER NOT NULL,
    knowledge_doc_id    TEXT,
    metadata            TEXT,
    FOREIGN KEY (task_id) REFERENCES browser_tasks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_browser_artifacts_task 
    ON browser_artifacts(task_id);
```

### 4.4 Pydantic 模型

（与 v1 相同，参见 v1 第 3.4 节）

---

## 5. AgentBrowserCLI 模块设计（替代 v1 的 client.py + session_pool.py）

### 5.1 核心思路

**不要自己管理 daemon 进程。** agent-browser CLI 自动处理 daemon 的启动、复用、清理。我们只需要：

1. 检测 agent-browser 是否安装
2. 调用 CLI 命令时传 `--session <project_id>` 标志
3. 解析 `--json` 输出
4. 处理超时和错误

### 5.2 关键代码片段（伪代码，给 Claude Code 参考）

```python
# tokenmind/browser_agent/cli.py
from __future__ import annotations
import asyncio
import json
import logging
import shutil
from typing import Any

logger = logging.getLogger("tokenmind.browser_agent.cli")


class AgentBrowserError(Exception):
    """Raised when agent-browser CLI returns an error."""


class AgentBrowserCLI:
    """Wraps agent-browser CLI as a subprocess.
    
    Does not manage daemons — the CLI handles that internally per session.
    """

    def __init__(self, binary: str = "agent-browser") -> None:
        self.binary = binary

    @staticmethod
    def is_installed() -> bool:
        """Check if agent-browser is available in PATH."""
        return shutil.which("agent-browser") is not None

    async def run(
        self,
        project_id: str,
        command: str,
        *args: str,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Execute an agent-browser command.
        
        Returns the parsed JSON response.
        Raises AgentBrowserError on non-zero exit or daemon errors.
        """
        full_cmd = [
            self.binary,
            "--session", project_id,
            "--json",
            command,
            *args,
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise AgentBrowserError(f"command {command} timed out after {timeout}s")
        
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace")
            raise AgentBrowserError(f"agent-browser exited {proc.returncode}: {err}")
        
        try:
            response = json.loads(stdout.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise AgentBrowserError(f"invalid JSON from agent-browser: {e}")
        
        # Real CLI uses `success` not `ok`. `batch` returns a list — caller handles those.
        if isinstance(response, dict) and not response.get("success", False):
            raise AgentBrowserError(
                response.get("error", "unknown error from agent-browser")
            )
        
        return response

    async def close_session(self, project_id: str) -> None:
        """Close a session's daemon and browser."""
        try:
            await self.run(project_id, "close", timeout=10.0)
        except AgentBrowserError as e:
            logger.warning("close session %s: %s", project_id, e)

    async def batch(
        self,
        project_id: str,
        commands: list[list[str]],
        timeout: float = 60.0,
    ) -> list[dict[str, Any]]:
        """Execute multiple commands in a single CLI invocation.
        
        commands is a list of [command, *args] arrays.
        """
        commands_json = json.dumps(commands)
        response = await self.run(
            project_id, "batch", commands_json, timeout=timeout
        )
        return response.get("data", [])
```

### 5.3 性能优化

虽然每次命令都启动 CLI 子进程会有开销（约 50-100ms），但：

1. agent-browser 的 daemon 是常驻的，subprocess 启动后立刻通过 socket 连到 daemon
2. 真正的浏览器操作开销远大于 subprocess 启动
3. 用 `batch` 命令可以一次执行多个动作，分摊开销

如果在 M1 测试中发现 subprocess 开销影响体验（单步 >200ms），再考虑通过 `agent-browser interactive` 模式（如果支持）做长连接。但优先级低。

---

## 6. EnvironmentCheck 模块（新增）

### 6.1 职责

检测用户环境：
1. agent-browser CLI 是否安装
2. Chrome 是否已下载（agent-browser install）
3. 通过 `agent-browser doctor --json` 一键检查

### 6.2 关键代码

```python
# tokenmind/browser_agent/env_check.py
from __future__ import annotations
import asyncio
import json
import shutil
from typing import Optional


class EnvCheckResult:
    def __init__(
        self,
        cli_installed: bool,
        chrome_installed: bool,
        version: Optional[str] = None,
        issues: Optional[list[str]] = None,
    ):
        self.cli_installed = cli_installed
        self.chrome_installed = chrome_installed
        self.version = version
        self.issues = issues or []

    @property
    def is_ready(self) -> bool:
        return self.cli_installed and self.chrome_installed and not self.issues


async def check_environment() -> EnvCheckResult:
    """Check if agent-browser is properly installed."""
    if not shutil.which("agent-browser"):
        return EnvCheckResult(
            cli_installed=False,
            chrome_installed=False,
            issues=["agent-browser CLI not found in PATH"],
        )
    
    # Run agent-browser doctor for comprehensive check
    try:
        proc = await asyncio.create_subprocess_exec(
            "agent-browser", "doctor", "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15.0)
        result = json.loads(stdout.decode("utf-8"))
        
        return EnvCheckResult(
            cli_installed=True,
            chrome_installed=result.get("data", {}).get("chrome_ok", False),
            version=result.get("data", {}).get("version"),
            issues=result.get("data", {}).get("issues", []),
        )
    except (asyncio.TimeoutError, json.JSONDecodeError, OSError) as e:
        return EnvCheckResult(
            cli_installed=True,
            chrome_installed=False,
            issues=[f"doctor check failed: {e}"],
        )
```

### 6.3 前端引导页

`BrowserAgentSetup.tsx`：用户第一次进浏览器智能体页面时显示。

```
┌─────────────────────────────────────────┐
│ 浏览器智能体 - 环境检测                    │
├─────────────────────────────────────────┤
│ ✓ 检测到 agent-browser v0.21.0           │
│ ✗ Chrome 浏览器未安装                     │
│                                          │
│ [一键安装] 自动运行 agent-browser install │
│                                          │
│ 或手动执行：                              │
│   agent-browser install                  │
└─────────────────────────────────────────┘
```

如果用户没装 agent-browser：

```
┌─────────────────────────────────────────┐
│ 浏览器智能体 - 首次使用                    │
├─────────────────────────────────────────┤
│ 浏览器智能体需要 agent-browser 工具        │
│                                          │
│ 请在终端运行：                            │
│   npm install -g agent-browser           │
│   agent-browser install                  │
│                                          │
│ 安装完成后点 [重新检测]                   │
└─────────────────────────────────────────┘
```

---

## 7. TaskService 执行循环（修订版）

```python
# tokenmind/browser_agent/task_service.py 核心伪代码

async def execute_task(self, task: BrowserTask) -> None:
    """Execute a browser task with ReAct loop."""
    
    # 1. Pre-flight: check environment
    env = await check_environment()
    if not env.is_ready:
        await self._mark_failed(task, "环境未就绪：" + "; ".join(env.issues))
        return
    
    # 2. Initial navigation if start_url provided
    if task.start_url:
        try:
            await self.cli.run(task.project_id, "open", task.start_url)
        except AgentBrowserError as e:
            await self._mark_failed(task, f"无法打开起始页：{e}")
            return
    
    # 3. ReAct loop
    history: list[BrowserStep] = []
    
    for step_index in range(1, task.max_steps + 1):
        if await self._check_cancelled(task.id):
            await self._mark_status(task.id, TaskStatus.CANCELLED)
            return
        
        # 3.1 Snapshot current state
        try:
            snap_response = await self.cli.run(
                task.project_id, "snapshot", "-i"
            )
        except AgentBrowserError as e:
            await self._record_step(task.id, step_index, 
                phase=StepPhase.OBSERVATION, success=False, error=str(e))
            continue
        
        accessibility_tree = snap_response["data"]["tree"]
        current_url = snap_response["data"].get("url", "")
        
        # 3.2 Stuck detection
        signal = self.stuck_detector.detect(snap_response["data"])
        if signal.needs_intervention:
            await self._mark_status(task.id, TaskStatus.AWAITING_USER)
            await self._ws_push(task.id, {
                "type": "intervention_needed",
                "reason": signal.reason,
                "detected": signal.detected,
            })
            await self._wait_for_resume_or_timeout(task.id, timeout=1800)
            if await self._check_cancelled(task.id):
                return
            await self._mark_status(task.id, TaskStatus.RUNNING)
            continue
        
        # 3.3 LLM decides next action
        decision = await self._llm_decide(
            instruction=task.instruction,
            history=history[-5:],  # 只给最近 5 步避免 token 爆炸
            snapshot=accessibility_tree,
            current_url=current_url,
        )
        
        await self._record_step(
            task.id, step_index,
            phase=StepPhase.THINKING,
            thinking=decision.thinking,
            action_name=decision.tool_name,
            action_args=decision.args,
        )
        
        # 3.4 Check for done
        if decision.tool_name == "browser_done":
            task.result_summary = decision.args.get("result", "")
            await self._mark_status(task.id, TaskStatus.COMPLETED)
            await self._save_task_log(task)
            return
        
        # 3.5 Execute action
        try:
            ab_command, ab_args = self._tool_to_cli_command(
                decision.tool_name, decision.args
            )
            result = await self.cli.run(task.project_id, ab_command, *ab_args)
            await self._record_step(
                task.id, step_index,
                phase=StepPhase.ACTION,
                action_name=decision.tool_name,
                action_args=decision.args,
                success=True,
            )
        except AgentBrowserError as e:
            await self._record_step(
                task.id, step_index,
                phase=StepPhase.ACTION,
                action_name=decision.tool_name,
                success=False,
                error=str(e),
            )
            # Continue loop, let LLM see error and try recovery
            continue
        
        # 3.6 Save artifact if any
        if "artifact" in result.get("data", {}):
            artifact = await self.artifact_store.save(
                task_id=task.id,
                step_index=step_index,
                kind=result["data"]["artifact"]["kind"],
                data=result["data"]["artifact"]["data"],
                source_url=current_url,
            )
            await self._ws_push(task.id, {
                "type": "artifact_created",
                "artifact": artifact.dict(),
            })
        
        history.append(...)
    
    # Max steps reached
    await self._mark_failed(task, "达到最大步数限制")
```

---

## 8. 工具集 → CLI 命令映射

| TokenMind 工具 | agent-browser CLI 命令 |
|---------------|----------------------|
| `browser_open` | `open <url>` |
| `browser_snapshot` | `snapshot -i` （interactive elements only，省 token） |
| `browser_click` | `click @<ref>` 或 `click --x N --y M` |
| `browser_fill` | `fill @<ref> "<text>"` |
| `browser_select` | `select @<ref> "<value>"` |
| `browser_scroll` | `scroll <direction> [amount]` |
| `browser_wait_for` | `wait --selector ... --timeout ...` |
| `browser_screenshot` | `screenshot [--full]` |
| `browser_download` | `download <url>` 或触发后用 `wait` |
| `browser_extract` | `eval --stdin "<JS code>"` 或自己用 LLM 处理 snapshot |
| `browser_save_page` | `save --format markdown` 或 `pdf` |
| `browser_done` | （不调用 CLI，仅标记任务完成） |

---

## 9. 阶段性实施计划（修订版）

### M1：核心链路打通（预计 5 天，比 v1 快）

#### 任务清单

1. **环境检测**
   - 实现 `env_check.py`
   - 创建 `BrowserAgentSetup.tsx` 引导页
   - 验证：在没装 agent-browser 的机器上能正确显示安装引导

2. **后端基础**
   - 创建 `tokenmind/browser_agent/` 目录
   - 实现 `models.py`、`storage.py`（建表 + CRUD）
   - 实现 `cli.py`：AgentBrowserCLI（先实现 run、close_session）
   - 实现 `task_service.py`：最简执行循环（先支持 open、snapshot、click、screenshot 四个命令）

3. **后端路由**
   - 创建 `tokenmind/server/routes/browser_tasks.py`
   - 实现 `POST /api/browser-tasks`、`GET /api/browser-tasks`、`GET /api/browser-tasks/{id}`、`POST /api/browser-tasks/{id}/cancel`
   - 实现 `GET /api/browser-agent/env-check`（环境检测）
   - 注册到 routes/__init__.py 和 app.py

4. **前端最小可用**
   - 修改 `Sidebar.tsx`、`App.tsx` 添加入口
   - 创建 `BrowserAgent.tsx`（任务输入 + 列表）
   - 创建 `BrowserAgentSetup.tsx`（环境引导）
   - 创建 `services/browserAgent.ts` 和 `stores/browserAgentStore.ts`

#### M1 验收标准

```
✓ 用户没装 agent-browser 时，进入页面看到清晰的安装引导
✓ 装好后能输入 "打开 baidu.com 并截屏"
✓ 任务从 pending → running → completed
✓ 数据库三张表都有正确数据
✓ 任务详情页能看到 4-5 步的执行记录
✓ 截图文件落到项目目录的 browser/screenshots/ 下
```

---

### M2：完整工具集 + 实时画面（预计 1 周）

#### 任务清单

1. **完整 CLI 命令包装**
   - `cli.py` 实现所有 12 个工具对应的命令
   - 实现 `batch` 方法用于多步操作优化

2. **产物落地**
   - 实现 `artifact_store.py`
   - 处理截图（base64 → 文件）、页面文本、PDF、下载文件
   - 元数据写入 `browser_artifacts` 表

3. **WebSocket 推流**
   - 创建 `browser_stream.py`
   - 实现 `WS /api/browser-tasks/{id}/stream`
   - 推送 step、screenshot、artifact_created 等事件
   - **可选**：尝试 iframe 嵌入 agent-browser 自带 dashboard，决定哪个体验更好

4. **LLM 决策**
   - `prompts.py` 完整提示词
   - 集成 TokenMind 现有 provider
   - JSON 输出解析 + 失败重试（最多 3 次）

5. **前端**
   - `BrowserTaskDetail.tsx`：步骤回放 + 产物预览
   - `BrowserTaskRunning.tsx`：实时画面 + 步骤日志

#### M2 验收标准

```
✓ 跑任务"在 GitHub 搜 browser-use 提取 README 重点"
✓ 产物完整落地（截图、页面文本、extract JSON）
✓ 任务详情页能完整回放
✓ 实时执行时前端能看到画面更新
✓ JSON 解析失败时自动重试，不会任务卡死
```

---

### M3：可视化接管（预计 1 周）

（任务清单和验收标准与 v1 相同，参见 v1 第 8 章 M3）

**关键修改**：用户在前端的点击事件，最终通过 `cli.run(project_id, "click", "--x", str(x), "--y", str(y))` 转发到 agent-browser。

---

### M4：与 TokenMind 现有系统深度集成（预计 3-5 天）

（与 v1 完全相同，参见 v1 第 8 章 M4）

---

## 10. 实施流程指令（给 Claude Code）

### 10.1 通用规则

1. **严格按 M1 → M2 → M3 → M4 顺序执行**
2. **M1 开始前必须先在本地装好 agent-browser 并跑通基础命令**：
   ```bash
   npm install -g agent-browser
   agent-browser install
   agent-browser --json open https://example.com
   agent-browser --json snapshot -i
   agent-browser --json close
   ```
   把这 4 条命令的真实输出贴到任务记录里，作为后续解析逻辑的基准。
3. **修改现有文件时**：先用 view 工具看完整文件，确认上下文后再用 str_replace
4. **遵循 TokenMind 现有代码风格**（Python：类型注解齐全；TypeScript：Hook + 函数式组件）
5. **不引入新依赖**（aiohttp 已被 v1 列入需要，仍然需要）
6. **错误处理**：所有 subprocess 调用都要 try/except AgentBrowserError
7. **日志**：logger 名字 `tokenmind.browser_agent.<module>`

### 10.2 启动指令模板

```
请执行 TokenMind 浏览器智能体模块的 M1 阶段。
参考文档：web-agent-implementation-plan-v2.md
严格按 M1 任务清单执行。

执行前请先：
1. 在本地安装 agent-browser 并验证基础命令
2. 把 agent-browser --json open / snapshot / click / close 的真实 JSON 输出
   贴到 plan 中作为解析基准

完成后给我 M1 验收报告。
```

### 10.3 每个 Milestone 完成后必须输出

```
M[X] 完成报告
================
新增文件: [列表]
修改文件: [列表 + 修改摘要]
agent-browser 命令真实输出样本: [JSON]
数据库变更: [SQL 摘要]
验收测试结果: [逐条对照验收标准 + 实际操作录屏]
已知问题: [如果有]
下一阶段提示: [Claude Code 自己的判断]
```

---

## 11. 关键风险与对策（修订版）

### 11.1 已知风险

1. **agent-browser 协议变更** — v0.21+ 是当前版本，未来版本可能变命令名或 JSON schema
   - 对策：在 `pyproject.toml` 不锁版本（让用户自己装最新版），但 cli.py 写一层适配，对每个命令的输入输出做 schema 校验

2. **subprocess 启动开销** — 每次命令 50-100ms
   - 对策：高频路径用 batch 命令；M2 实测后再决定是否需要 long-running 进程模式

3. **LLM 输出 ref 错误** — LLM 可能引用一个失效的 ref
   - 对策：cli.py 检测到 ref 错误自动 re-snapshot 并把错误反馈给 LLM

4. **某些命令长时间无响应** — 比如下载大文件
   - 对策：每个命令默认 30s 超时，下载类命令单独配 300s 超时

### 11.2 完整回退

```bash
# 删除新增文件
rm -rf tokenmind/browser_agent/
rm tokenmind/server/routes/browser_tasks.py
rm tokenmind/server/websocket/browser_stream.py
rm -rf frontend/src/pages/BrowserAgent*.tsx
rm frontend/src/pages/browserAgent.css
rm frontend/src/services/browserAgent.ts
rm frontend/src/stores/browserAgentStore.ts

# 撤销修改文件
git checkout tokenmind/server/routes/__init__.py
git checkout tokenmind/server/app.py
git checkout frontend/src/components/Layout/Sidebar.tsx
git checkout frontend/src/App.tsx
git checkout pyproject.toml

# 删除数据库表（可选）
sqlite> DROP TABLE browser_tasks;
sqlite> DROP TABLE browser_steps;
sqlite> DROP TABLE browser_artifacts;
```

---

## 12. 总结

### 12.1 v2 相对 v1 的关键改进

| 项目 | v1 | v2 |
|------|----|----|
| 部署方式 | Docker | 直接 npm install |
| 进程管理 | 自实现 SessionPool | agent-browser 自管理 |
| IPC 协议 | 自己设计 stdin/stdout JSON | 直接调用 CLI 的 --json 输出 |
| 实时画面 | 自实现截图推流 | 优先尝试 iframe 嵌入官方 dashboard |
| 元素选择 | 文字/坐标 | refs（更可靠） |
| 项目隔离 | 自管理 daemon 进程池 | --session 标志 |
| M1 工时 | 1 周 | 5 天（更简单） |

### 12.2 总开发量预估（v2）

- M1: 5 天
- M2: 1 周  
- M3: 1 周
- M4: 3-5 天

**总计：约 3 周**（比 v1 缩短 1 周）

### 12.3 核心设计原则

1. **不重复发明轮子** — agent-browser 已经做好的事不要再做一遍（daemon 管理、IPC 协议、ref 系统）
2. **零侵入 TokenMind 主项目** — 所有代码都是新增模块，可一键回滚
3. **本地优先** — 不依赖任何容器、不依赖任何外部服务
4. **环境检测优雅** — 用户没装依赖时给清晰引导，不要直接报错
