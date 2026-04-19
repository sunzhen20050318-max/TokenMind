from pathlib import Path

from sun_agent.agent.context import ContextBuilder


def _make_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    return workspace


def test_build_messages_includes_attachment_metadata_and_preserves_attachment_field(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    builder = ContextBuilder(workspace)

    attachments = [
        {
            "name": "report.pdf",
            "path": str(workspace / "uploads" / "report.pdf"),
            "category": "pdf",
            "size": 12345,
            "is_image": False,
        }
    ]

    messages = builder.build_messages(
        history=[],
        current_message="请帮我总结这份报告。",
        attachments=attachments,
        channel="web",
        chat_id="demo-session",
    )

    user_message = messages[-1]
    assert user_message["role"] == "user"
    assert user_message["attachments"] == attachments
    assert isinstance(user_message["content"], str)
    assert ContextBuilder._ATTACHMENTS_CONTEXT_TAG in user_message["content"]
    assert "report.pdf" in user_message["content"]
    assert "请帮我总结这份报告。" in user_message["content"]


def test_build_messages_includes_linked_knowledge_context(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    builder = ContextBuilder(workspace)

    messages = builder.build_messages(
        history=[],
        current_message="请根据知识库回答。",
        knowledge_chunks=[
            {
                "knowledge_base_name": "产品资料",
                "document_name": "features.md",
                "content": "TokenMind 支持知识库、多会话和定时任务。",
            }
        ],
        channel="web",
        chat_id="demo-session",
    )

    user_message = messages[-1]
    assert isinstance(user_message["content"], str)
    assert ContextBuilder._KNOWLEDGE_CONTEXT_TAG in user_message["content"]
    assert "产品资料" in user_message["content"]
    assert "features.md" in user_message["content"]


def test_build_messages_strips_legacy_knowledge_metadata_from_history(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    builder = ContextBuilder(workspace)

    history = [
        {
            "role": "user",
            "content": (
                "[Linked Knowledge - retrieved context only, not user text]\n"
                "1. [测试知识库 / score.xlsx] 230200496 62\n\n"
                "2. [测试知识库 / score.xlsx] 230200479 62\n"
                "If the retrieved context is not relevant, say so instead of forcing it into the answer.\n\n"
                "我的学号是230200496"
            ),
        }
    ]

    messages = builder.build_messages(
        history=history,
        current_message="请帮我查找成绩。",
        channel="web",
        chat_id="demo-session",
    )

    restored_history_message = messages[1]
    assert restored_history_message["role"] == "user"
    assert restored_history_message["content"] == "我的学号是230200496"
