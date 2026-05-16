# 知识库双模设计：RAG + LLM Wiki 并存

> 状态：设计中（spec），待用户 review 后转 implementation plan
> 替代：`tokenmind_llm_wiki_migration_plan.md`（原计划是单向迁移到 Wiki + 移除 RAG，现已废弃）
> 参考：Karpathy 提出的 LLM Wiki 方法论；`sdyckjq-lab/llm-wiki-skill`（仅借鉴方法，不作为 skill 安装）

## 背景

TokenMind 当前知识库走 RAG-first：上传 → 切 chunk → embedding → 向量库 → `retrieve_for_session()` → ContextBuilder 自动注入 chunks。配置里有 vector_backend / chunk_size / embedding / rerank 等一整套。

LLM Wiki 是不同范式：上传 → LLM 在入库时把原文编译成 Markdown wiki 页面（entity / topic / source / synthesis），用 `[[双向链接]]` 形成图谱；查询时 LLM 像浏览维基百科一样**用工具一页一页探索**，不是被动接受预选 chunk。两种范式各有适用场景，本设计让它们在 TokenMind 内并存而非互相替换。

## 设计决策

| # | 决策 | 含义 |
|---|---|---|
| 1 | KB 级隔离 | 每个 KB 创建时选 `type=rag` 或 `type=wiki`，目录、记录、检索路径完全隔离；KB 内不混用 |
| 2 | 旧 KB 默认 RAG | metadata 中无 `type` 字段的 KB 读取时注入 `type=rag`，照旧逻辑运行；不提供强制迁移工具 |
| 3 | RAG 行为不变 | 「链接知识库」按钮专属 RAG，链接后自动 retrieve + 注入 ContextBuilder；现有配置、向量库、chunk 逻辑全部保留 |
| 4 | Wiki 工具化 | Wiki KB 不走自动注入；注册 `wiki_index / wiki_grep / wiki_read / wiki_backlinks / wiki_graph` 五个工具供 LLM 主动调用 |
| 5 | Wiki 查询纯 lexical + 双链 | 第一版不上 embedding；中文模糊语义召回不归 Wiki（归 Memory 系统） |
| 6 | Wiki 会话级激活 | 会话顶部下拉选当前 active Wiki KB；会话内可随时切换；一次只激活一个 |
| 7 | ContextBuilder 双路径 | RAG 走原 `_build_knowledge_context()` 注入 chunks；Wiki 在 system prompt 加一段"当前 Wiki KB 简介 + 可用工具列表"，不注入页面内容 |
| 8 | 创建 KB UI | 新建对话框增加 type 单选；KB 列表卡片显示类型徽标 |

## 架构

### 数据流总览

```
RAG KB                                  Wiki KB
──────                                  ───────
上传文件                                 上传文件
  ↓                                       ↓
切 chunk                                保存到 raw/
  ↓                                       ↓
embedding                              LLM 编译 source/entity/topic 页面
  ↓                                       ↓
qdrant / sqlite 向量库                   wiki/ + [[双链]] + graph-data.json
  ↓                                       ↓
会话链接 KB → retrieve_for_session     会话激活 KB → system prompt 提示 + 工具
  ↓                                       ↓
ContextBuilder 自动注入 chunks         LLM 主动调 wiki_grep / wiki_read 探索
  ↓                                       ↓
LLM 看到 [Linked Knowledge] 段          LLM 看到 [Active Wiki KB] 段 + 工具输出
```

### KB type 路由

`KnowledgeBaseRecord` 增加 `type: Literal["rag", "wiki"] = "rag"` 字段（默认 rag 保留向后兼容）。

`KnowledgeService` 内部分两条独立链路：

```python
def register_document_upload(self, kb_id, ...):
    kb = self.get_knowledge_base(kb_id)
    if kb.type == "wiki":
        return self._wiki_register_source(...)
    return self._rag_register_document(...)  # 现有逻辑原样保留

def process_document(self, doc_id):
    if self._is_wiki_doc(doc_id):
        return self._wiki_process_source(doc_id)
    return self._rag_process_chunk(doc_id)

def retrieve_for_session(self, session_id, query):
    # 只查链接的 RAG KB；Wiki KB 不参与自动 retrieve
    rag_kb_ids = [k for k in self.get_session_links(session_id) if self._kb_type(k) == "rag"]
    return self._rag_retrieve(rag_kb_ids, query)  # 现有逻辑原样
```

Wiki KB 永远不出现在 `retrieve_for_session()` 的结果里。它们的可见性由会话的 `active_wiki_kb_id` 字段控制，由 ContextBuilder 和工具层读取。

### Wiki KB 存储布局

每个 Wiki KB 独立目录（与 RAG KB 共享 `workspace/knowledge/{kb_id}/` 命名空间，但子结构不同）：

```
workspace/knowledge/{kb_id}/
├── raw/
│   ├── files/        ← 用户上传的原始文件
│   ├── webpages/
│   ├── chats/
│   ├── notes/
│   └── assets/
├── wiki/
│   ├── sources/      ← 资料摘要页（每个 raw 对应一个）
│   ├── entities/     ← 实体页（项目、工具、人物、概念）
│   ├── topics/       ← 主题页
│   ├── comparisons/  ← 对比分析
│   ├── synthesis/    ← 综合分析 / 深度报告
│   │   └── sessions/ ← 会话结晶化（后期阶段）
│   └── queries/      ← 持久化查询结果（后期阶段）
├── index.md          ← 入口索引（LLM 调 wiki_index 时返回）
├── purpose.md        ← KB 目标 / 范围（创建时由用户填）
├── log.md            ← 操作日志
├── .wiki-schema.md   ← 页面类型/链接规则
├── .wiki-cache.json  ← sha256 缓存，避免重复编译
├── graph-data.json   ← 扫描 wiki/ 中 [[链接]] 生成
└── lint-report.json  ← 后期阶段
```

RAG KB 沿用现有布局（`documents/`、`vectors.sqlite3`、`qdrant/`），不动。

两套布局在 `{kb_id}/` 层级互斥——一个 KB 要么是 RAG（有 `documents/`、`vectors.sqlite3`），要么是 Wiki（有 `raw/`、`wiki/`），不会同时出现。

### Wiki 工具集

五个工具注册到 `ToolRegistry`，作用域为当前会话的 `active_wiki_kb_id`：

| 工具 | 参数 | 返回 | 用途 |
|---|---|---|---|
| `wiki_index` | 无 | `index.md` 全文 + KB 元信息（页面数、最近更新） | 入口——LLM 第一次问问题时先了解 KB 全貌 |
| `wiki_grep` | `keyword: str`, `top_k: int = 5` | 命中页面列表（路径 + 命中片段 ± 3 行） | 关键词搜索；title/alias/正文都搜 |
| `wiki_read` | `page_path: str` | 完整页面 Markdown（含 frontmatter 和 `[[链接]]`） | 读单页详情 |
| `wiki_backlinks` | `page_path: str` | 反向链接到该页的所有页面列表 | 看"谁引用了我" |
| `wiki_graph` | 无 | `graph-data.json` 内容（nodes + edges） | 看整张图（可选；大 KB 慎用） |

工具实现位置：`tokenmind/agent/tools/wiki.py`（新文件）。所有工具签名**不带 kb_id 参数**——内部读会话状态的 `active_wiki_kb_id`，没有激活 KB 时返回明确错误而非空。

**LLM 探索流程示例**：用户问"GraphRAG 怎么处理多跳？"
1. LLM 调 `wiki_index()` → 看到 KB 是"AI 论文笔记"，主题包含图谱检索、长上下文
2. LLM 调 `wiki_grep("GraphRAG")` → 命中 `entities/GraphRAG.md` + `topics/图谱检索.md`
3. LLM 调 `wiki_read("entities/GraphRAG.md")` → 看到内容里有 `[[多跳推理]]`
4. LLM 调 `wiki_read("topics/多跳推理.md")` → 补足答案
5. LLM 综合所有读到的内容回答用户

### Wiki 会话激活模型

`Session.metadata` 增加可选字段 `active_wiki_kb_id: str | None`。

- 用户在会话顶部下拉切换：前端 PATCH `/api/sessions/{session_id}` 设置该字段
- 切换是**即时生效**的；下一轮对话 system prompt 重新计算
- 切换不影响历史消息——之前的对话引用旧 KB 的内容保留原样
- 会话首次创建时该字段为 `None`，LLM 看不到任何 Wiki KB
- 同时该会话还可以通过老的"链接知识库"按钮链接 RAG KB，两者独立工作

### ContextBuilder 改造

`build_messages()` / `build_system_prompt()` 两个变化：

1. **RAG 路径不动**：`retrieve_for_session()` 已经过滤掉 Wiki KB，返回的 chunks 通过 `_build_knowledge_context()` 注入，输出 `[Linked Knowledge]` 段，格式不变。
2. **新增 Wiki system prompt 段**：读取 `session.metadata.active_wiki_kb_id`，若存在则在 system prompt 拼接：

```
[Active Wiki Knowledge Base]
You have an active Wiki knowledge base for this conversation:

- Name: {kb.name}
- Purpose: {purpose.md 首段}
- Page counts: {entity_count} entities, {topic_count} topics, {source_count} sources

You can explore it using these tools:
  - wiki_index() — read the index page first to understand the KB
  - wiki_grep(keyword) — search pages by keyword
  - wiki_read(page_path) — read a specific page
  - wiki_backlinks(page_path) — see what links to a page
  - wiki_graph() — see the full link graph

Prefer to read multiple pages and follow [[links]] before answering.
Do not invent information not present in the Wiki.
[/Active Wiki Knowledge Base]
```

KB 内容**不注入** system prompt——只放元信息和工具使用提示。

`ChatService`（`server/app.py:87`）和 `AgentLoop`（`agent/loop.py:149`）各自的 `KnowledgeService` 实例都要看到同一份 KB type 状态。这点现状已经满足——两者读同一份 `metadata.json`。

### 数据模型

#### `KnowledgeBaseRecord`（修改）

```python
class KnowledgeBaseRecord(BaseModel):
    id: str
    name: str
    description: str = ""
    type: Literal["rag", "wiki"] = "rag"   # 新增；默认 rag 保留向后兼容
    status: str = "ready"
    enabled: bool = True

    # RAG 字段（rag 类型使用）
    document_count: int = 0

    # Wiki 字段（wiki 类型使用）
    language: str = "zh"
    root_path: str = ""
    source_count: int = 0
    page_count: int = 0
    entity_count: int = 0
    topic_count: int = 0
    link_count: int = 0

    created_at: str
    updated_at: str
```

Wiki 字段对 RAG KB 取默认 0；前端按 type 决定显示哪组。

#### `WikiSourceRecord`（新增，wiki 类型 KB 专用）

```python
class WikiSourceRecord(BaseModel):
    id: str
    knowledge_base_id: str
    title: str
    source_type: Literal["file", "webpage", "chat", "note"]
    raw_path: str                # 相对 kb_root
    original_name: str = ""
    source_url: str | None = None
    sha256: str = ""
    size: int = 0
    status: Literal["registered", "processing", "ready", "failed"] = "registered"
    processing_stage: str = "ready"
    processing_progress: int = 100
    error_message: str | None = None
    source_page_id: str | None = None
    created_at: str
    updated_at: str
```

#### `WikiPageRecord`（新增）

```python
class WikiPageRecord(BaseModel):
    id: str
    knowledge_base_id: str
    page_type: Literal["source", "entity", "topic", "comparison", "synthesis", "query"]
    title: str
    path: str                    # 相对 kb_root，例如 wiki/entities/GraphRAG.md
    summary: str = ""
    outgoing_links: list[str] = []   # [[X]] 解析出来的目标 title
    backlinks: list[str] = []        # 由 graph 重建时填充
    sources: list[str] = []          # 关联的 WikiSourceRecord.id
    created_at: str
    updated_at: str
```

#### `KnowledgeChunkRecord`（保留）

RAG 类型使用，不动。Wiki KB 永远不写 chunk 表。

#### `Session.metadata` 字段增加

```python
metadata = {
    ...
    "active_wiki_kb_id": str | None,   # 当前激活的 Wiki KB
    ...
}
```

### API 表面

**保留（行为不变）**：

```
GET    /api/knowledge                          # 列出所有 KB（rag + wiki），前端按 type 渲染
POST   /api/knowledge                          # 创建 KB（body 增加 type 字段）
GET    /api/knowledge/{kb_id}
PUT    /api/knowledge/{kb_id}
DELETE /api/knowledge/{kb_id}
GET    /api/knowledge/links/{session_id}       # RAG 链接关系
PUT    /api/knowledge/links/{session_id}       # 仅允许 rag 类型 KB 进入此列表
POST   /api/knowledge/{kb_id}/documents        # 上传——内部按 type 分发
DELETE /api/knowledge/{kb_id}/documents/{document_id}
```

**新增**：

```
PATCH  /api/sessions/{session_id}              # 设置 active_wiki_kb_id（已存在路由的话扩展 body）
GET    /api/knowledge/{kb_id}/pages            # wiki only：列出 wiki 页面
GET    /api/knowledge/{kb_id}/pages/{page_id}  # wiki only：读单页
PUT    /api/knowledge/{kb_id}/pages/{page_id}  # wiki only：人工编辑
GET    /api/knowledge/{kb_id}/graph            # wiki only：返回 graph-data.json
POST   /api/knowledge/{kb_id}/graph/rebuild    # wiki only：重建（异步，返回 202）
```

后期阶段才上的（不在第一版范围）：

```
POST   /api/knowledge/{kb_id}/lint
POST   /api/knowledge/{kb_id}/digest
POST   /api/knowledge/{kb_id}/crystallize
```

### 前端

#### 新增组件

- `frontend/src/components/Knowledge/CreateKbDialog.tsx`：新建对话框增加 `type` 单选（RAG / Wiki）
- `frontend/src/components/Knowledge/WikiKbDetail.tsx`：Wiki KB 详情页
- `frontend/src/components/Knowledge/WikiPageList.tsx`：按 source / entity / topic 分组列表
- `frontend/src/components/Knowledge/WikiPageViewer.tsx`：Markdown 渲染 + frontmatter + 反链栏
- `frontend/src/components/Knowledge/KnowledgeGraph.tsx`：ECharts 图谱
- `frontend/src/components/Chat/ActiveWikiKbSelector.tsx`：会话顶部 active Wiki KB 下拉

#### `KnowledgePage.tsx` 修改

KB 列表卡片增加 type 徽标（"RAG" / "Wiki"）。点击 RAG KB 进入现有详情页；点击 Wiki KB 进入新的 `WikiKbDetail`。

#### Chat 页面修改

- 顶部增加 active Wiki KB 选择器，跟现有"链接知识库"按钮并列
- 选择器选项 = 用户所有 `type=wiki` 的 KB
- 选中后 `PATCH /api/sessions/{session_id}` 写入 `active_wiki_kb_id`
- 选择"无"清空激活

## 实施阶段（高层）

> 细化的 step-by-step 由 writing-plans 阶段产出。这里只列阶段顺序，与原计划对比的删改在每阶段注明。

| 阶段 | 内容 | 与原计划差异 |
|---|---|---|
| 1 | 后端 `type` 字段 + Wiki KB 创建路径（目录、种子文件）+ KB type 路由骨架 | 原 §3，保留；`type` 默认值改 rag |
| 2 | Wiki KB 上传 raw + sha256 缓存 | 原 §4，保留 |
| 3 | Source page 生成（模板版，先不调 LLM） | 原 §5，保留 |
| 4 | LLM 编译 entity/topic 页面 | 原 §6，保留；merge 策略简化为"只追加新区段" |
| 5 | **Wiki 工具注册 + ContextBuilder 双路径** | 原 §7 重写——不动 retrieve_for_session（仅过滤 type），改成新增工具 + system prompt 提示 |
| 6 | graph-data.json 扫描生成 + `/graph` API | 原 §8，保留 |
| 7 | 前端创建 KB 对话框 + Wiki KB 详情页 + 会话激活 Wiki KB 下拉 | 原 §9，保留并增加激活下拉 |
| 8 | digest / lint / crystallize | 原 §10/§11/§12，保留为后期增强 |
| ~~9~~ | ~~移除 RAG 主链路~~ | **删除**（原 §13） |
| ~~10~~ | ~~旧 RAG 数据迁移工具~~ | **删除**（原 §14） |

## 非目标 / 显式不做

- **不移除 RAG**：所有 RAG 配置、代码、向量库、chunk 检索、embedding、rerank 全部保留
- **不强制迁移**：旧 KB 默认 `type=rag` 继续用；不提供 CLI 迁移工具
- **不支持 type 就地变更**：KB type 创建后不可改（不支持 rag→wiki 或 wiki→rag 转换）；想换类型就新建一个 KB
- **Wiki 不上 embedding**：第一版纯 lexical；模糊语义召回由 Memory 系统负责，不归 Wiki
- **不支持跨 KB 链接**：`[[X]]` 仅在 KB 内解析；跨 KB 的关联需用户在内容里手工标注
- **不支持单会话同时激活多个 Wiki KB**：一次一个；同时也不强制将 Wiki KB 绑到 Project（Project 级绑定作为后续增强）
- **不直接集成 `llm-wiki-skill`**：仅借鉴方法，不安装到 `tokenmind/skills/`，不调它的 shell 脚本

## 风险与处理

| 风险 | 处理 |
|---|---|
| LLM 编译 entity/topic 不稳定 | Step 1（结构化 JSON 分析）+ Step 2（页面写入）两步走，JSON 校验失败回退到单步；写入用 frontmatter `confidence` 标注（EXTRACTED/INFERRED/AMBIGUOUS/UNVERIFIED） |
| Wiki 纯 lexical 召回差 | 第一版纯 lexical + 双链扩展；监控实际使用，必要时为 wiki 页面级别加 embedding（不切 chunk） |
| 大页面塞爆 LLM 上下文 | `wiki_read` 对超过 2000 字的页面只返回 frontmatter + 前 500 字 + grep 命中段落上下文 |
| 用户既链 RAG 又激活 Wiki | 两条路径独立工作：system prompt 同时出现 `[Linked Knowledge]`（RAG 注入）和 `[Active Wiki Knowledge Base]`（Wiki 工具提示）。LLM 自行判断引用哪个 |
| LLM 编辑 wiki 页面覆盖人工内容 | 编译时检测页面是否包含 `<!-- human-edited -->` 标记或修改时间晚于 source 处理时间，是则只追加新区段 |
| Graph 重建大 KB 慢 | `/graph/rebuild` 异步执行；返回 202 + task_id；前端轮询 |

## 边界 case 决策

- **Wiki KB 删除**：删除时扫描所有会话，把 `active_wiki_kb_id == 该 kb_id` 的会话字段重置为 null。避免悬空引用导致工具调用报错。
- **Wiki KB 重命名 / purpose 变更**：不需要任何缓存失效——system prompt 每轮重建。
- **切换 active KB 后历史里的旧工具结果**：不修改消息历史（消息不可变）。在 system prompt 的 `[Active Wiki Knowledge Base]` 段追加一句"You previously used another Wiki KB in this conversation; tool results from it remain in history but the active KB is now {current_name}"。LLM 每轮看到提示就不会把旧 KB 内容当成当前 KB。
- **purpose.md 生成**：创建 Wiki KB 时后端用模板 + KB 的 name/description 自动生成 `purpose.md` 草稿。用户在 KB 详情页可后续编辑。创建对话框不暴露 purpose 输入。
