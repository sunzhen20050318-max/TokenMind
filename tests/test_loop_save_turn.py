from sun_agent.agent.context import ContextBuilder
from sun_agent.agent.loop import AgentLoop
from sun_agent.session.manager import Session


def _mk_loop() -> AgentLoop:
    loop = AgentLoop.__new__(AgentLoop)
    loop._TOOL_RESULT_MAX_CHARS = AgentLoop._TOOL_RESULT_MAX_CHARS
    return loop


def test_save_turn_skips_multimodal_user_when_only_runtime_context() -> None:
    loop = _mk_loop()
    session = Session(key="test:runtime-only")
    runtime = "\n".join([
        ContextBuilder._RUNTIME_CONTEXT_TAG,
        "Current Time: now (UTC)",
        ContextBuilder._RUNTIME_CONTEXT_END_TAG,
    ])

    loop._save_turn(
        session,
        [{"role": "user", "content": [{"type": "text", "text": runtime}]}],
        skip=0,
    )
    assert session.messages == []


def test_save_turn_keeps_image_placeholder_with_path_after_runtime_strip() -> None:
    loop = _mk_loop()
    session = Session(key="test:image")
    runtime = "\n".join([
        ContextBuilder._RUNTIME_CONTEXT_TAG,
        "Current Time: now (UTC)",
        ContextBuilder._RUNTIME_CONTEXT_END_TAG,
    ])

    loop._save_turn(
        session,
        [{
            "role": "user",
            "content": [
                {"type": "text", "text": runtime},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,abc"},
                    "_meta": {"path": "/media/feishu/photo.jpg"},
                },
            ],
        }],
        skip=0,
    )
    assert session.messages[0]["content"] == [{"type": "text", "text": "[image: /media/feishu/photo.jpg]"}]


def test_save_turn_keeps_image_placeholder_without_meta() -> None:
    loop = _mk_loop()
    session = Session(key="test:image-no-meta")
    runtime = "\n".join([
        ContextBuilder._RUNTIME_CONTEXT_TAG,
        "Current Time: now (UTC)",
        ContextBuilder._RUNTIME_CONTEXT_END_TAG,
    ])

    loop._save_turn(
        session,
        [{
            "role": "user",
            "content": [
                {"type": "text", "text": runtime},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        }],
        skip=0,
    )
    assert session.messages[0]["content"] == [{"type": "text", "text": "[image]"}]


def test_save_turn_keeps_tool_results_under_16k() -> None:
    loop = _mk_loop()
    session = Session(key="test:tool-result")
    content = "x" * 12_000

    loop._save_turn(
        session,
        [{"role": "tool", "tool_call_id": "call_1", "name": "read_file", "content": content}],
        skip=0,
    )

    assert session.messages[0]["content"] == content


def test_save_turn_strips_knowledge_context_prefix_from_user_message() -> None:
    loop = _mk_loop()
    session = Session(key="test:knowledge-strip")
    runtime = "\n".join([
        ContextBuilder._RUNTIME_CONTEXT_TAG,
        "Current Time: now (UTC)",
        ContextBuilder._RUNTIME_CONTEXT_END_TAG,
    ])
    knowledge = "\n".join([
        ContextBuilder._KNOWLEDGE_CONTEXT_TAG,
        "Linked knowledge references:",
        "- [产品资料] 文档摘录",
        ContextBuilder._KNOWLEDGE_CONTEXT_END_TAG,
    ])

    loop._save_turn(
        session,
        [{"role": "user", "content": f"{runtime}\n\n{knowledge}\n\n请总结产品能力"}],
        skip=0,
    )

    assert session.messages[0]["content"] == "请总结产品能力"


def test_strip_metadata_prefix_handles_legacy_knowledge_context_with_blank_lines() -> None:
    runtime = "\n".join([
        ContextBuilder._RUNTIME_CONTEXT_TAG,
        "Current Time: now (UTC)",
        ContextBuilder._RUNTIME_CONTEXT_END_TAG,
    ])
    legacy_knowledge = "\n".join([
        ContextBuilder._KNOWLEDGE_CONTEXT_TAG,
        "Use the following retrieved knowledge excerpts as supplemental context when answering.",
        "1. [测试知识库 / 成绩表.xlsx] 60\n\n60\n\n60",
        ContextBuilder._KNOWLEDGE_CONTEXT_TRAILER,
    ])
    raw = f"{runtime}\n\n{legacy_knowledge}\n\n我的学号是 230200496"

    assert ContextBuilder.strip_metadata_prefix(raw) == "我的学号是 230200496"
