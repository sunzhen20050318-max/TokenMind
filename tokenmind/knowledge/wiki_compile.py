"""LLM-driven Wiki compile runner.

Replaces the JSON-middleman approach in wiki_ingest.compile_with_llm: instead
of asking the LLM to return a JSON document and translating it into file
writes, we give the LLM filesystem tools (read/write/edit/list, scoped to
the KB root) and let it author the Wiki pages directly. This mirrors the
llm-wiki skill flow on which the design is based.

Per-source, single-shot runner: callers should invoke run() once per source
document, serially within a KB (per-KB locking is the caller's job).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from tokenmind.agent.tools.filesystem import (
    EditFileTool,
    ListDirTool,
    ReadFileTool,
    WriteFileTool,
)
from tokenmind.agent.tools.registry import ToolRegistry
from tokenmind.providers.base import LLMProvider
from tokenmind.utils.helpers import build_assistant_message


MAX_ITERATIONS = 40
MAX_SOURCE_CHARS = 9000


class WikiCompileRunner:
    """Run one wiki-compile session for a single source document.

    Lifecycle:
        runner = WikiCompileRunner(provider, model, kb_root, language)
        stats  = await runner.run(source_title=..., source_text=...,
                                  source_page_id=..., source_page_path=...)

    The runner returns a stats dict so callers can log progress, but the
    real output is on disk: the LLM should have written or amended
    wiki/sources/<name>.md, wiki/entities/*.md, and wiki/topics/*.md.
    """

    def __init__(
        self,
        provider: LLMProvider,
        model: str,
        kb_root: Path,
        language: str = "zh",
    ):
        self.provider = provider
        self.model = model
        self.kb_root = kb_root.resolve()
        self.language = language

    async def run(
        self,
        *,
        source_title: str,
        source_text: str,
        source_page_id: str,
        source_page_path: Path,
    ) -> dict[str, Any]:
        tools = self._build_tools()
        purpose = self._read_purpose()
        entity_titles, topic_titles = self._scan_existing_titles()

        rel_source_path = self._safe_relpath(source_page_path)
        user_msg = self._build_user_prompt(
            purpose=purpose,
            entity_titles=entity_titles,
            topic_titles=topic_titles,
            source_title=source_title,
            source_text=source_text,
            source_page_id=source_page_id,
            source_page_path=rel_source_path,
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": user_msg},
        ]

        stats: dict[str, Any] = {
            "iterations": 0,
            "tool_calls": 0,
            "tool_breakdown": {},
            "errors": [],
        }

        for _ in range(MAX_ITERATIONS):
            stats["iterations"] += 1
            try:
                response = await self.provider.chat_with_retry(
                    messages=messages,
                    tools=tools.get_definitions(),
                    model=self.model,
                )
            except Exception as exc:
                logger.warning("wiki compile chat error: {}", exc)
                stats["errors"].append({"type": "chat", "error": str(exc)})
                break

            if not response.has_tool_calls:
                stats["final_message"] = (response.content or "")[:600]
                break

            tool_call_dicts = [tc.to_openai_tool_call() for tc in response.tool_calls]
            messages.append(
                build_assistant_message(
                    response.content or "",
                    tool_calls=tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )
            )

            for tool_call in response.tool_calls:
                stats["tool_calls"] += 1
                stats["tool_breakdown"][tool_call.name] = (
                    stats["tool_breakdown"].get(tool_call.name, 0) + 1
                )
                try:
                    result = await tools.execute(tool_call.name, tool_call.arguments)
                except Exception as exc:
                    result = f"ERROR: {exc}"
                    stats["errors"].append({"tool": tool_call.name, "error": str(exc)})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.name,
                        "content": result if isinstance(result, str) else str(result),
                    }
                )
        else:
            stats["truncated"] = True
            logger.warning(
                "wiki compile hit iteration cap ({}) for {}",
                MAX_ITERATIONS,
                source_title,
            )

        return stats

    # ---- helpers --------------------------------------------------------

    def _build_tools(self) -> ToolRegistry:
        tools = ToolRegistry()
        tools.register(
            ReadFileTool(workspace=self.kb_root, allowed_dir=self.kb_root)
        )
        tools.register(
            WriteFileTool(workspace=self.kb_root, allowed_dir=self.kb_root)
        )
        tools.register(
            EditFileTool(workspace=self.kb_root, allowed_dir=self.kb_root)
        )
        tools.register(
            ListDirTool(workspace=self.kb_root, allowed_dir=self.kb_root)
        )
        return tools

    def _read_purpose(self) -> str:
        p = self.kb_root / "purpose.md"
        try:
            return p.read_text(encoding="utf-8") if p.is_file() else ""
        except OSError:
            return ""

    def _scan_existing_titles(self) -> tuple[list[str], list[str]]:
        entities: list[str] = []
        topics: list[str] = []
        for sub, bucket in (("entities", entities), ("topics", topics)):
            d = self.kb_root / "wiki" / sub
            if not d.is_dir():
                continue
            for md in d.glob("*.md"):
                bucket.append(md.stem)
        entities.sort()
        topics.sort()
        return entities, topics

    def _safe_relpath(self, p: Path) -> str:
        try:
            return str(p.resolve().relative_to(self.kb_root)).replace("\\", "/")
        except ValueError:
            return str(p)

    def _build_system_prompt(self) -> str:
        lang = "中文" if self.language == "zh" else "English"
        now = datetime.now(timezone.utc).isoformat()
        return (
            "# Wiki 编辑员\n\n"
            f"现在的 UTC 时间是 {now}。\n\n"
            "你是一个 LLM Wiki 知识库的编辑员。用户会给你一份原始素材,你的任务是:\n"
            "1. 阅读已有的源摘要页(stub),理解原文要点\n"
            "2. 浏览 wiki/entities/ 和 wiki/topics/,看现在已经有哪些页面\n"
            "3. 从素材中抽出具体概念(entity)和更高层主题(topic)\n"
            "4. 已存在同名页面 → 读完后**只在末尾追加**「## 新增信息(来自 …)」段落\n"
            "5. 不存在同名页面 → 新建一个 markdown 文件\n"
            "6. 最后回到源摘要页,补充其中的「## 摘要」和「## 提到的概念」段落\n\n"
            "## 文件位置\n"
            "- 源摘要页:`wiki/sources/<已给>.md`(**已有 stub,只能 Edit,禁止 write_file 新建源页面**)\n"
            "- 实体页:`wiki/entities/<标题>.md`(文件名就是标题。可能已存在,先 read 再 Write 或 Edit)\n"
            "- 主题页:`wiki/topics/<标题>.md`(文件名就是标题。可能已存在,先 read 再 Write 或 Edit)\n\n"
            "**注意区分**:frontmatter 里的 `id: page_xxxxx` 只是内部标识,**不是文件名**。文件名永远等于标题。\n\n"
            "## 路径约定\n"
            "所有路径都用**相对于 KB 根目录**的形式,例如 `wiki/entities/MinerU.md`。\n"
            "工具被限制在 KB 根目录内,不能访问外部文件。\n\n"
            "## 新页面 frontmatter 模板\n"
            "```\n"
            "---\n"
            "id: page_<10位随机十六进制>\n"
            "type: entity   # 或 topic\n"
            "title: <规范化标题>\n"
            "confidence: EXTRACTED   # 必填:EXTRACTED | INFERRED | AMBIGUOUS | UNVERIFIED\n"
            "evidence: \"<原文摘录或推理依据,<=80 字>\"\n"
            "aliases:        # 可选,仅 entity\n"
            "  - 别名1\n"
            "sources:\n"
            "  - <源页面 id,例如 page_abc1234567>\n"
            "created_at: <当前 UTC ISO 时间>\n"
            "updated_at: <当前 UTC ISO 时间>\n"
            "---\n"
            "```\n"
            "## 置信度规则\n"
            "- `EXTRACTED`:概念直接出现在原文里,有原文摘录作 evidence\n"
            "- `INFERRED`:从原文多处推断出来,原文没直接说,evidence 说明推理依据\n"
            "- `AMBIGUOUS`:原文有相关说法但歧义/不清楚,evidence 描述歧义点\n"
            "- `UNVERIFIED`:用了模型背景知识,原文无证据,evidence 可填 \"模型背景知识\"\n"
            "**严格要求**:每个 entity/topic frontmatter 都必须有 `confidence` 字段,默认应优先 EXTRACTED;只有当真无原文支撑时才标 INFERRED/UNVERIFIED。\n\n"
            "## 内联置信度(可选)\n"
            "对页面 `## 内容` 区里的某条具体说法,如果跟整体页面的 confidence 不同,可以在那一行/那一段前加 HTML 注释:\n"
            "```\n"
            "<!-- confidence: INFERRED -->\n"
            "- 该工具可能被广泛用于生产环境(原文未直接说,但提到了 Server 部署)\n"
            "```\n"
            "不强制每条都标,只在异常时标。\n\n"
            "frontmatter 后面接:\n"
            "```\n"
            "# <标题>\n\n"
            "## 摘要\n"
            "一段精要(<= 50 字)\n\n"
            "## 内容\n"
            "若干段或列表,可以用 [[别的标题]] 引用相关页面\n\n"
            "## 关联主题   <-- entity 用「关联主题」\n"
            "## 相关页面   <-- topic 用「相关页面」\n"
            "- [[相关 1]]\n"
            "- [[相关 2]]\n\n"
            "## 来源\n"
            "- [[<源页面 id>]]\n"
            "```\n\n"
            "## 追加段落模板\n"
            "对已存在的同名页面,用 Edit 在文件末尾追加:\n"
            "```\n\n"
            "## 新增信息(来自 [[<当前源页面 id>]])\n"
            "<这份素材里关于该概念/主题的新内容,可以引用其他 [[实体]]/[[主题]]>\n"
            "```\n\n"
            "## 重要约束\n"
            "- **复用现有标题**:如果一个概念在已有标题清单里出现过(可能同义异名),用清单里的标题,不要造新词\n"
            "- **跨页 [[wikilink]]**:只链接你确认存在的标题(以 list_dir 看到的、或本次会话刚 write 的为准)\n"
            "- **已存在页面不要重写主体**,只追加。摘要、内容、关联区都保留原样\n"
            "- **源页面**:摘要写完整,然后写「## 提到的概念」,把本次产出的所有 entity/topic 列成 `- [[标题]]`\n"
            f"- **输出语言**:{lang}\n\n"
            "## 完成前必查 checklist(每一项都要 ✓ 才能停)\n"
            "1. ✓ 已 `list_dir` 看过现有 entity/topic 页面\n"
            "2. ✓ 至少有一个 `write_file` 或 `edit_file` 操作完成(写了或合并了至少一个 entity 或 topic 页面)\n"
            "3. ✓ **已 `edit_file` 源页面 stub**:stub 里的 `## 摘要` 和 `## 提到的概念` 两个 heading 后面是空的,你要在每一段下面补上内容。**用 `edit_file` 在两个 heading 下面插入正文**,**不要 `write_file` 覆盖整个源页面**\n\n"
            "## edit_file 用法提示\n"
            "源页面 stub 里精确的两段是这样的(空内容):\n"
            "```\n"
            "## 摘要\n\n"
            "## 内容节选\n"
            "```\n"
            "你要把 `## 摘要` 后面、`## 内容节选` 前面的空行替换成真实摘要。例如 `edit_file` 用:\n"
            "- old_string: `## 摘要\\n\\n## 内容节选`\n"
            "- new_string: `## 摘要\\n\\n这份素材讲了 XXX...\\n\\n## 内容节选`\n\n"
            "「提到的概念」类似,在文件末尾的 `## 提到的概念` heading 后面追加 `[[wikilink]]` 列表。\n\n"
            "## 终止\n"
            "checklist 全部 ✓ 后,用 1-2 句话总结你做了什么,**不再调用任何工具**。\n"
            "如果发现源页面的摘要或提到的概念段落还是空的,**立刻 edit_file 补上**,不要终止。\n"
        )

    def _build_user_prompt(
        self,
        *,
        purpose: str,
        entity_titles: list[str],
        topic_titles: list[str],
        source_title: str,
        source_text: str,
        source_page_id: str,
        source_page_path: str,
    ) -> str:
        if len(source_text) > MAX_SOURCE_CHARS:
            source_text = source_text[:MAX_SOURCE_CHARS] + "\n...[truncated]"

        existing_entities = ", ".join(f"[[{t}]]" for t in entity_titles) or "(暂无)"
        existing_topics = ", ".join(f"[[{t}]]" for t in topic_titles) or "(暂无)"

        return (
            "# 知识库目标\n"
            f"{purpose.strip() or '(用户尚未填写 purpose.md)'}\n\n"
            "# 已有实体标题(请尽量复用)\n"
            f"{existing_entities}\n\n"
            "# 已有主题标题(请尽量复用)\n"
            f"{existing_topics}\n\n"
            "# 本次要消化的素材\n"
            f"- **源页面 stub 已经预先创建,文件路径就是这个**: `{source_page_path}`\n"
            f"- 源页面的 frontmatter id 是 `{source_page_id}`(只用于实体/主题页 `## 来源` 区的 `[[wikilink]]`,**不要**用它当文件名)\n"
            f"- 标题:{source_title}\n"
            f"- 原文(前 {MAX_SOURCE_CHARS} 字):\n"
            "```\n"
            f"{source_text}\n"
            "```\n\n"
            "## 严格规则\n"
            "- **源页面**:`" + source_page_path + "` 这个文件已存在,你只能用 `edit_file` 操作它,**禁止 write_file 创建新的源页面**\n"
            "- **实体/主题**:**文件名 = 标题**(例如 `wiki/entities/PaddleOCR.md`,而不是 `wiki/entities/page_xxx.md`)。frontmatter 里的 `id` 字段是内部 id,跟文件名无关\n"
            "- 写新实体页时,frontmatter 的 `id` 用 `page_<10位随机十六进制>` 格式\n\n"
            "## 建议步骤\n"
            "1. `read_file('" + source_page_path + "')` 看 stub 现在的内容\n"
            "2. `list_dir('wiki/entities')` 和 `list_dir('wiki/topics')` 看已有页面\n"
            "3. 决定要写或要追加的实体/主题(参考已有标题尽量复用)\n"
            "4. 对每个目标:\n"
            "   - 已存在 → `read_file` → `edit_file` 在文件末尾追加「## 新增信息」段落\n"
            f"   - 不存在 → `write_file` 新建,文件名为 `wiki/entities/<标题>.md` 或 `wiki/topics/<标题>.md`\n"
            "5. 最后 `edit_file('" + source_page_path + "')` 在 stub 里补「## 摘要」与「## 提到的概念」段落\n"
            "6. 一句话总结后停止\n"
        )


def new_page_id() -> str:
    """Helper for callers that need a page id outside the runner."""
    return f"page_{uuid.uuid4().hex[:10]}"
