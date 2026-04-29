"""Prompts for the browser-agent ReAct loop.

The loop:
1. snapshot the page → feed to LLM as observation
2. ask LLM for the next action (one of the supported tools, or finish)
3. execute the action via AgentBrowserCLI
4. record the outcome and loop again

We keep the prompt small and deterministic. The LLM must reply with a strict
JSON object — never prose — so we can parse it reliably and detect
malformed output for retry.
"""

from __future__ import annotations

from typing import Any, Optional

# Allowed action names. Mirrors the helper methods on AgentBrowserCLI plus
# the meta-action ``finish`` that signals the loop to terminate.
ACTION_SCHEMAS: dict[str, dict[str, Any]] = {
    "open": {
        "description": "Navigate the browser tab to a fully-qualified URL.",
        "args": {"url": "string — absolute URL"},
    },
    "click": {
        "description": "Click an element by ref (preferred, e.g. @e7) or CSS selector.",
        "args": {"selector": "string — element ref or CSS selector"},
    },
    "type": {
        "description": "Type text into an element WITHOUT clearing it first.",
        "args": {
            "selector": "string — element ref or CSS selector",
            "text": "string — text to type",
        },
    },
    "fill": {
        "description": "Clear the element then type the given text into it.",
        "args": {
            "selector": "string — element ref or CSS selector",
            "text": "string — text to fill",
        },
    },
    "press": {
        "description": "Press a key (Enter, Tab, Escape, Control+a, etc.).",
        "args": {"key": "string — key name"},
    },
    "scroll": {
        "description": "Scroll the page in a direction.",
        "args": {
            "direction": "one of up | down | left | right",
            "pixels": "int (optional) — number of pixels, defaults to one screen",
        },
    },
    "wait": {
        "description": "Wait for an element selector to appear, OR a millisecond duration.",
        "args": {"target": "string — element ref/selector OR an integer ms (e.g. \"2000\")"},
    },
    "back": {
        "description": "Navigate back in the browser history.",
        "args": {},
    },
    "forward": {
        "description": "Navigate forward in the browser history.",
        "args": {},
    },
    "reload": {
        "description": "Reload the current page.",
        "args": {},
    },
    "get_text": {
        "description": "Read the inner text of an element. Use to extract specific data.",
        "args": {"selector": "string — element ref or CSS selector"},
    },
    "screenshot": {
        "description": "Capture the current viewport as a PNG only when the user explicitly asks for a screenshot.",
        "args": {},
    },
    "save_page_text": {
        "description": "保存当前页面的可读全文为一个文本产物（用于摘录、归档等）。",
        "args": {
            "label": "string (optional) — 给这个文本产物起个名字，便于在产物列表里识别"
        },
    },
    "extract": {
        "description": (
            "按 selector → 字段名映射，从页面提取结构化 JSON 并保存为产物。"
            "适合一次性抽多条信息（标题、作者、价格…）。"
        ),
        "args": {
            "fields": (
                "object — { 字段名: selector } 形式的映射，例如 "
                "{\"title\":\".post-title\",\"author\":\".byline\"}"
            ),
            "label": "string (optional) — 给这个 JSON 产物起个名字",
        },
    },
    "finish": {
        "description": "Signal that the task is complete.",
        "args": {
            "summary": "string — human-readable summary of what was accomplished, "
            "ideally listing concrete findings the user asked for",
        },
    },
}


SYSTEM_PROMPT = """你是 TokenMind 的「Web Agent」，控制一个真实的 Chrome 浏览器，按用户指令完成网页任务。

每一轮你会收到：
- 用户的原始任务指令
- 当前页面的可访问性快照（用 [ref=eN] 标识可交互元素，比如按钮、链接、输入框）
- 之前已经执行过的步骤摘要

你必须只输出一个 JSON 对象，描述下一步动作，**不要输出任何解释、Markdown、代码块标记**。
JSON 结构：

{
  "thinking": "用一两句话说明你为什么选这个动作（中文）",
  "action": "动作名（必须从允许列表里选）",
  "args": {...动作参数...}
}

动作参数必须严格按 schema 来。例如：
- 点击 ref e7：{"action":"click","args":{"selector":"@e7"}}
- 在 ref e28 输入文本：{"action":"fill","args":{"selector":"@e28","text":"TokenMind"}}
- 按下回车：{"action":"press","args":{"key":"Enter"}}

完成任务时输出：
{"thinking":"...","action":"finish","args":{"summary":"你完成了什么"}}

规则：
1. 每一步**只执行一个**动作，不要批量。
2. 动作执行后，下一轮你会拿到新的快照——根据新快照决定下一步。
3. ref（@eN）只在最近一次 snapshot 内有效，旧快照里的 ref 不要复用。
4. 如果连续 2 步没有进展（页面没变），就调用 finish 并解释为什么放弃。
5. 不要尝试不在允许列表里的动作。
6. 不要输出非 JSON 内容，否则会被判定为格式错误，浪费一次重试机会。
7. 不要为了记录过程自动截图；只有用户明确要求截图、保存画面或交付视觉证据时才使用 screenshot。
8. 如果任务要求给帖子/笔记/视频点赞、收藏或关注，必须优先操作主内容区域的作者/标题/正文附近按钮；不要点击评论区里的点赞、回复或评论操作。若快照无法区分主帖按钮和评论按钮，先读取页面文本或请求用户接管，不要猜。
9. 如果任务需要依次处理多个搜索结果或多个帖子，完成当前详情页后必须先使用 back 返回列表/搜索结果页，再选择下一条；不要在详情页还打开时点击列表中下一条的大概位置。
10. 如果连续看到当前页面仍是详情页、弹窗或覆盖层，而下一步目标在列表页，优先 back / Escape / 关闭按钮回到列表，不要继续点详情页里的图片或评论区。
"""


def build_action_reference() -> str:
    """Format the action catalog as a compact reference appended to the prompt."""
    lines = ["允许的动作列表："]
    for name, spec in ACTION_SCHEMAS.items():
        args_summary = (
            ", ".join(f"{k}={v}" for k, v in spec["args"].items()) if spec["args"] else "无参数"
        )
        lines.append(f"- {name}: {spec['description']} 参数: {args_summary}")
    return "\n".join(lines)


def build_user_message(
    *,
    instruction: str,
    snapshot: str,
    history: list[dict[str, Any]],
    last_error: Optional[str] = None,
) -> str:
    """Assemble the per-turn user message.

    ``history`` is a list of step dicts shaped like
    ``{"action": "fill", "args": {...}, "observation": "..."}``.
    ``last_error`` is filled when the previous LLM response was unparseable
    so the model can self-correct on the retry.
    """
    parts: list[str] = [
        f"# 任务指令\n{instruction}",
        build_action_reference(),
    ]

    if history:
        history_lines = ["# 已执行的步骤"]
        for idx, step in enumerate(history[-10:], start=1):  # last 10 steps only
            action = step.get("action") or "?"
            args = step.get("args") or {}
            obs = step.get("observation") or ""
            ok = "✓" if step.get("success", True) else "✗"
            history_lines.append(f"{idx}. {ok} {action}({args}) → {obs[:200]}")
        parts.append("\n".join(history_lines))

    parts.append("# 当前页面快照\n" + (snapshot or "(快照为空)"))

    if last_error:
        parts.append(
            "# ⚠️ 上一次输出格式错误\n"
            f"{last_error}\n请仅输出严格 JSON，不要包含解释或代码块。"
        )

    parts.append("# 你的下一步动作（只输出 JSON）")
    return "\n\n".join(parts)
