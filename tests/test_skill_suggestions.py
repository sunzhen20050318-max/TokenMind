from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tokenmind.agent.loop import AgentLoop
from tokenmind.agent.skill_suggestions import SkillSuggestionStore
from tokenmind.agent.tools.skill_suggestion import ProposeSkillTool
from tokenmind.bus.queue import MessageBus
from tokenmind.providers.base import LLMResponse


def test_create_and_list_skill_suggestion(tmp_path: Path) -> None:
    store = SkillSuggestionStore(tmp_path)

    suggestion = store.create(
        name="Browser Debugging",
        description="Debug browser automation failures",
        body="Use this when browser clicks do not change the page.",
        triggers=["browser stuck", "click failed"],
        source_session_id="web:abc",
    )

    assert suggestion.name == "browser-debugging"
    assert suggestion.description == "Debug browser automation failures"
    assert suggestion.triggers == ["browser stuck", "click failed"]
    assert suggestion.source_session_id == "web:abc"
    assert (tmp_path / "skills" / ".suggestions" / f"{suggestion.id}.json").exists()

    listed = store.list_pending()
    assert [item.id for item in listed] == [suggestion.id]


def test_approve_skill_suggestion_writes_skill_file(tmp_path: Path) -> None:
    store = SkillSuggestionStore(tmp_path)
    suggestion = store.create(
        name="repeatable workflow",
        description="A reusable workflow",
        body="1. Inspect the current state.\n2. Make the smallest safe change.",
        triggers=["repeatable task"],
    )

    approved = store.approve(suggestion.id)

    assert approved.name == "repeatable-workflow"
    skill_file = tmp_path / "skills" / "repeatable-workflow" / "SKILL.md"
    assert skill_file.exists()
    content = skill_file.read_text(encoding="utf-8")
    assert "description: \"A reusable workflow\"" in content
    assert "repeatable task" in content
    assert "Make the smallest safe change" in content
    assert not (tmp_path / "skills" / ".suggestions" / f"{suggestion.id}.json").exists()


def test_skill_suggestion_preview_matches_approved_file(tmp_path: Path) -> None:
    store = SkillSuggestionStore(tmp_path)
    suggestion = store.create(
        name="release checklist",
        description="Release a package safely",
        body="1. Run tests.\n2. Build artifacts.\n3. Publish.",
        triggers=["release package"],
    )

    preview = store.render_preview(suggestion)
    approved = store.approve(suggestion.id)
    written = Path(approved.path or "").read_text(encoding="utf-8")

    assert preview == written
    assert preview.startswith("---\n")
    assert 'description: "Release a package safely"' in preview


def test_update_skill_suggestion_writes_diff_and_overwrites_target(tmp_path: Path) -> None:
    store = SkillSuggestionStore(tmp_path)
    target = tmp_path / "skills" / "release-checklist"
    target.mkdir(parents=True)
    old = """---
name: release-checklist
description: "Old release flow"
---

# release-checklist

## Procedure

1. Run tests.
"""
    target_file = target / "SKILL.md"
    target_file.write_text(old, encoding="utf-8")
    new = """---
name: release-checklist
description: "Updated release flow"
---

# release-checklist

## Procedure

1. Run tests.
2. Build artifacts.
3. Verify pip install.
"""

    suggestion = store.create_update(
        target_skill="release-checklist",
        description="Updated release flow",
        markdown=new,
        previous_markdown=old,
        triggers=["release package"],
        source_session_id="web:abc",
    )

    assert suggestion.kind == "update"
    assert suggestion.target_skill == "release-checklist"
    assert "Verify pip install" in store.render_preview(suggestion)
    assert "+3. Verify pip install." in store.render_diff(suggestion)

    approved = store.approve(suggestion.id)

    assert approved.path == str(target_file)
    assert "Updated release flow" in target_file.read_text(encoding="utf-8")
    assert not (tmp_path / "skills" / ".suggestions" / f"{suggestion.id}.json").exists()


def test_reject_skill_suggestion_deletes_pending_file(tmp_path: Path) -> None:
    store = SkillSuggestionStore(tmp_path)
    suggestion = store.create(name="discard me", description="x", body="x")

    assert store.reject(suggestion.id) is True
    assert store.list_pending() == []
    assert store.reject(suggestion.id) is False


def test_skill_suggestion_rejects_path_traversal(tmp_path: Path) -> None:
    store = SkillSuggestionStore(tmp_path)

    suggestion = store.create(name="../../unsafe", description="x", body="x")

    assert suggestion.name == "unsafe"
    approved = store.approve(suggestion.id)
    assert approved.path == str(tmp_path / "skills" / "unsafe" / "SKILL.md")
    assert not (tmp_path / "unsafe").exists()


def test_approve_existing_skill_requires_overwrite(tmp_path: Path) -> None:
    store = SkillSuggestionStore(tmp_path)
    existing = tmp_path / "skills" / "alpha"
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("# existing", encoding="utf-8")
    suggestion = store.create(name="alpha", description="new", body="new body")

    with pytest.raises(FileExistsError):
        store.approve(suggestion.id)

    approved = store.approve(suggestion.id, overwrite=True)
    assert approved.name == "alpha"
    assert "new body" in (existing / "SKILL.md").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_propose_skill_tool_creates_pending_suggestion(tmp_path: Path) -> None:
    tool = ProposeSkillTool(workspace=tmp_path)

    result = await tool.execute(
        name="safe refactor",
        description="How to do safe refactors",
        body="Read first, patch second, verify last.",
        triggers=["refactor", "safe change"],
        source_session_id="web:abc",
    )

    assert "待确认" in result
    suggestions = SkillSuggestionStore(tmp_path).list_pending()
    assert len(suggestions) == 1
    assert suggestions[0].name == "safe-refactor"


def _make_reflection_loop(tmp_path: Path) -> AgentLoop:
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.chat_with_retry = AsyncMock(return_value=LLMResponse(content="ok"))
    return AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="test-model",
    )


def test_agent_loop_does_not_expose_propose_skill_in_regular_tools(tmp_path: Path) -> None:
    loop = _make_reflection_loop(tmp_path)

    assert "propose_skill" not in loop.tools.tool_names


def test_skill_reflection_is_scheduled_every_fifteen_user_turns(tmp_path: Path) -> None:
    loop = _make_reflection_loop(tmp_path)
    scheduled = []
    loop._schedule_background = lambda coro: scheduled.append(coro)  # type: ignore[method-assign]

    session = loop.sessions.get_or_create("web:test")
    for index in range(14):
        session.add_message("user", f"user {index}")
        session.add_message("assistant", f"assistant {index}")
    loop._maybe_schedule_skill_reflection(session)
    assert scheduled == []

    session.add_message("user", "user 15")
    session.add_message("assistant", "assistant 15")
    loop._maybe_schedule_skill_reflection(session)

    assert len(scheduled) == 1
    assert session.metadata["last_skill_reflection_user_count"] == 15
    scheduled[0].close()


@pytest.mark.asyncio
async def test_skill_reflection_creates_pending_suggestion_after_review(tmp_path: Path) -> None:
    loop = _make_reflection_loop(tmp_path)
    loop.provider.chat_with_retry = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps(
                {
                    "action": "create",
                    "name": "release-checklist",
                    "description": "发布前的重复检查流程",
                    "triggers": ["发布版本", "构建包"],
                    "body": "1. 检查工作区状态。\n2. 运行测试。\n3. 构建产物并验证安装。",
                    "source_message": "最近 15 轮多次讨论发布流程。",
                },
                ensure_ascii=False,
            )
        )
    )
    session = loop.sessions.get_or_create("web:test")
    for index in range(15):
        session.add_message("user", f"第 {index} 轮：发布包前要检查什么？")
        session.add_message("assistant", "先检查状态，再运行测试，最后构建并验证。")
    loop.sessions.save(session)

    await loop._reflect_skills_for_session("web:test", 15)

    suggestions = SkillSuggestionStore(tmp_path).list_pending()
    assert len(suggestions) == 1
    assert suggestions[0].name == "release-checklist"
    assert suggestions[0].source_session_id == "web:test"
    kwargs = loop.provider.chat_with_retry.await_args.kwargs
    assert kwargs["tools"] is None


@pytest.mark.asyncio
async def test_skill_reflection_creates_pending_update_suggestion(tmp_path: Path) -> None:
    existing = tmp_path / "skills" / "release-checklist"
    existing.mkdir(parents=True)
    old = """---
name: release-checklist
description: "Release packages"
metadata: '{"tokenmind":{"triggers":["release package"]}}'
---

# release-checklist

## Procedure

1. Run tests.
"""
    (existing / "SKILL.md").write_text(old, encoding="utf-8")
    loop = _make_reflection_loop(tmp_path)
    updated = """---
name: release-checklist
description: "Release packages safely"
metadata: '{"tokenmind":{"triggers":["release package","verify install"]}}'
---

# release-checklist

## Procedure

1. Run tests.
2. Build artifacts.
3. Verify installation.
"""
    loop.provider.chat_with_retry = AsyncMock(
        side_effect=[
            LLMResponse(
                content=json.dumps(
                    {
                        "action": "update_candidate",
                        "target_skill": "release-checklist",
                        "description": "Add build and install verification",
                        "triggers": ["verify install"],
                        "source_message": "The recent conversation refined the release workflow.",
                    }
                )
            ),
            LLMResponse(
                content=json.dumps(
                    {
                        "action": "update",
                        "target_skill": "release-checklist",
                        "description": "Release packages safely",
                        "triggers": ["release package", "verify install"],
                        "markdown": updated,
                        "source_message": "Add build and install verification.",
                    }
                )
            ),
        ]
    )
    session = loop.sessions.get_or_create("web:test")
    for index in range(15):
        session.add_message("user", f"release workflow turn {index}")
        session.add_message("assistant", "Run tests, build artifacts, and verify installation.")
    loop.sessions.save(session)

    await loop._reflect_skills_for_session("web:test", 15)

    suggestions = SkillSuggestionStore(tmp_path).list_pending()
    assert len(suggestions) == 1
    suggestion = suggestions[0]
    assert suggestion.kind == "update"
    assert suggestion.target_skill == "release-checklist"
    assert suggestion.previous_markdown == old
    assert "Verify installation" in (suggestion.markdown or "")
    assert loop.provider.chat_with_retry.await_count == 2
