from pathlib import Path

from tokenmind.agent.context import ContextBuilder


def _make_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    return workspace


def test_knowledge_excerpt_preserves_chunk_up_to_default_chunk_size(tmp_path: Path) -> None:
    """A retrieved chunk no larger than the default chunk size (900) must be
    injected in full — the old hard-coded 500-char cap dropped ~44% of it."""
    builder = ContextBuilder(_make_workspace(tmp_path))
    content = "知" * 800  # < default chunk_size (900)
    chunks = [
        {
            "content": content,
            "knowledge_base_name": "kb",
            "document_name": "doc",
        }
    ]

    result = builder._build_knowledge_context(chunks)

    assert result is not None
    assert content in result  # full chunk preserved
    assert "..." not in result  # not truncated


def test_knowledge_excerpt_respects_configured_max_chars(tmp_path: Path) -> None:
    """When the excerpt budget is raised (to track a larger chunk_size), a
    chunk within that budget must be injected in full."""
    builder = ContextBuilder(_make_workspace(tmp_path), knowledge_excerpt_max_chars=2000)
    content = "知" * 1500
    chunks = [{"content": content, "knowledge_base_name": "kb", "document_name": "doc"}]

    result = builder._build_knowledge_context(chunks)

    assert result is not None
    assert content in result


def test_knowledge_excerpt_still_truncates_beyond_budget(tmp_path: Path) -> None:
    """Truncation is not removed — a chunk far above the budget is still capped
    so a pathological chunk can't blow up the prompt."""
    builder = ContextBuilder(_make_workspace(tmp_path), knowledge_excerpt_max_chars=900)
    content = "知" * 5000
    chunks = [{"content": content, "knowledge_base_name": "kb", "document_name": "doc"}]

    result = builder._build_knowledge_context(chunks)

    assert result is not None
    assert "..." in result  # still truncated
    assert content not in result  # full 5000-char content not injected
