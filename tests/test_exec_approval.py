from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tokenmind.agent.loop import AgentLoop
from tokenmind.bus.events import InboundMessage
from tokenmind.bus.queue import MessageBus
from tokenmind.providers.base import LLMResponse, ToolCallRequest


def _make_loop(tmp_path: Path, responses: list[LLMResponse]) -> AgentLoop:
    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.chat_with_retry = AsyncMock(side_effect=responses)
    return AgentLoop(bus=bus, provider=provider, workspace=tmp_path)


@pytest.mark.asyncio
async def test_request_tool_approval_waits_for_resolution_and_logs(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, [])
    msg = InboundMessage(
        channel="web",
        sender_id="web_user",
        chat_id="session-1",
        content="run something",
        metadata={"websocket": True},
        session_key_override="web:session-1",
    )

    approval_task = asyncio.create_task(
        loop._request_tool_approval(
            msg=msg,
            tool_id="call_1",
            tool_name="exec",
            command="git push origin main",
            reason="This command will change Git history or push code.",
            working_dir=str(tmp_path),
        )
    )

    outbound = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=1.0)
    assert outbound.metadata["_approval_required"] is True
    approval_id = outbound.metadata["_approval_id"]

    await loop._handle_tool_approval(
        InboundMessage(
            channel="web",
            sender_id="web_user",
            chat_id="session-1",
            content="/tool-approval",
            metadata={"control": "tool_approval", "approval_id": approval_id, "approved": True},
            session_key_override="web:session-1",
        )
    )

    assert await approval_task is True
    audit_lines = (tmp_path / "logs" / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    actions = [json.loads(line)["action"] for line in audit_lines]
    assert "tool.exec.approval_requested" in actions
    assert "tool.exec.approval_resolved" in actions


@pytest.mark.asyncio
async def test_safe_exec_still_requires_approval_on_web(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, [])
    msg = InboundMessage(
        channel="web",
        sender_id="web_user",
        chat_id="session-1",
        content="run something",
        metadata={"websocket": True},
        session_key_override="web:session-1",
    )

    should_confirm, reason, display_command, working_dir = loop._should_confirm_high_risk_tool(
        msg,
        "exec",
        {"command": "python -c \"print('hello')\""},
    )

    assert should_confirm is True
    assert "Shell commands can modify files" in (reason or "")
    assert display_command == "python -c \"print('hello')\""
    assert working_dir == str(tmp_path)


@pytest.mark.asyncio
async def test_high_risk_exec_rejection_skips_execution_and_persists_tool_error(tmp_path: Path) -> None:
    responses = [
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCallRequest(
                    id="call_1",
                    name="exec",
                    arguments={"command": "git push origin main"},
                )
            ],
        ),
        LLMResponse(content="Okay, I did not execute that command."),
    ]
    loop = _make_loop(tmp_path, responses)
    loop.tools.execute = AsyncMock(return_value="should not run")
    loop._request_tool_approval = AsyncMock(return_value=False)

    msg = InboundMessage(
        channel="web",
        sender_id="web_user",
        chat_id="session-1",
        content="push the branch",
        metadata={"websocket": True},
        session_key_override="web:session-1",
    )

    response = await loop._process_message(msg)

    assert response is not None
    assert response.content == "Okay, I did not execute that command."
    loop.tools.execute.assert_not_awaited()

    session = loop.sessions.get_or_create("web:session-1")
    tool_messages = [entry for entry in session.messages if entry.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert "not approved" in tool_messages[0]["content"]
    assert any(event["type"] == "tool_error" for event in session.timeline_events)
