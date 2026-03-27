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
        current_message="帮我总结这份报告。",
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
    assert "帮我总结这份报告。" in user_message["content"]
