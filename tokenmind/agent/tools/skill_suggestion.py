"""Tool for proposing reusable skills without writing them immediately."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tokenmind.agent.skill_suggestions import SkillSuggestionStore
from tokenmind.agent.tools.base import Tool


class ProposeSkillTool(Tool):
    """Let the model draft a reusable skill for later user approval."""

    def __init__(self, workspace: Path | str):
        self.workspace = Path(workspace)
        self._channel = ""
        self._chat_id = ""

    @property
    def name(self) -> str:
        return "propose_skill"

    @property
    def description(self) -> str:
        return (
            "Propose a reusable TokenMind skill when a pattern, workflow, troubleshooting method, "
            "or user preference should be saved for future conversations. This only creates a "
            "pending suggestion; the user must approve it in Settings before it becomes active."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short skill folder name, such as browser-debugging or safe-refactor.",
                    "minLength": 1,
                },
                "description": {
                    "type": "string",
                    "description": "One sentence describing what the skill helps with.",
                    "minLength": 1,
                },
                "body": {
                    "type": "string",
                    "description": "The actual reusable instructions to save in SKILL.md.",
                    "minLength": 1,
                },
                "triggers": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                    "description": "Optional phrases or situations that should trigger this skill.",
                },
                "source_session_id": {
                    "type": ["string", "null"],
                    "description": "Optional source session id; normally omitted because TokenMind fills context.",
                },
                "source_message": {
                    "type": ["string", "null"],
                    "description": "Optional short quote or note explaining why this suggestion was created.",
                },
            },
            "required": ["name", "description", "body"],
        }

    def set_context(self, channel: str, chat_id: str) -> None:
        self._channel = channel
        self._chat_id = chat_id

    async def execute(
        self,
        name: str,
        description: str,
        body: str,
        triggers: list[str] | None = None,
        source_session_id: str | None = None,
        source_message: str | None = None,
        **_: Any,
    ) -> str:
        session_id = source_session_id
        if not session_id and self._channel and self._chat_id:
            session_id = f"{self._channel}:{self._chat_id}"
        suggestion = SkillSuggestionStore(self.workspace).create(
            name=name,
            description=description,
            body=body,
            triggers=triggers,
            source_session_id=session_id,
            source_message=source_message,
        )
        return (
            f"已创建待确认技能建议：{suggestion.name}。"
            "请到设置中心的技能页面确认后，它才会写入 workspace/skills 并在后续对话中生效。"
        )
