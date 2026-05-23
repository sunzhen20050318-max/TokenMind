"""Ask-user-question tool.

The agent calls this when it needs the human to choose between concrete
options (plan confirmation, ambiguous design decisions, "which approach
do you prefer", etc.). Up to four sub-questions can be bundled into one
call; each surfaces as its own tab in the Web UI.

Execution is intercepted by ``AgentLoop`` — the tool body itself is a
stub that should never run. Routing happens in the loop because we need
the calling ``InboundMessage`` (session/channel/chat) to deliver the
question over WebSocket and await the reply, which is not available
inside ``Tool.execute``.
"""

from __future__ import annotations

from typing import Any

from tokenmind.agent.tools.base import Tool


class AskUserQuestionTool(Tool):
    @property
    def name(self) -> str:
        return "ask_user_question"

    @property
    def description(self) -> str:
        return (
            "Ask the human for a structured decision when you need their "
            "input to proceed. Use for plan confirmation, ambiguous "
            "requirements, or choosing between concrete options. Bundle 1-4 "
            "related questions in one call. Each question must offer 2-4 "
            "options; an 'Other' free-text option is added automatically by "
            "the UI so the user can always type a custom answer. Do NOT use "
            "for open-ended questions where free-form chat is more "
            "appropriate; for those, just send a regular message."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 4,
                    "description": "1-4 related questions to ask in one batch.",
                    "items": {
                        "type": "object",
                        "required": ["question", "header", "options"],
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": (
                                    "The full question text shown to the user."
                                ),
                            },
                            "header": {
                                "type": "string",
                                "description": (
                                    "Very short label (<=12 chars) used as the tab "
                                    "title when multiple questions are bundled."
                                ),
                            },
                            "multiSelect": {
                                "type": "boolean",
                                "default": False,
                                "description": (
                                    "True if the user can pick multiple options. "
                                    "Default false (single-select)."
                                ),
                            },
                            "options": {
                                "type": "array",
                                "minItems": 2,
                                "maxItems": 4,
                                "items": {
                                    "type": "object",
                                    "required": ["label"],
                                    "properties": {
                                        "label": {
                                            "type": "string",
                                            "description": "Short choice title (1-5 words).",
                                        },
                                        "description": {
                                            "type": "string",
                                            "description": (
                                                "Optional one-line explanation of "
                                                "the trade-off this choice implies."
                                            ),
                                        },
                                    },
                                },
                            },
                        },
                    },
                }
            },
            "required": ["questions"],
        }

    async def execute(self, **kwargs: Any) -> str:
        # AgentLoop intercepts this tool before invocation and handles the
        # round-trip itself; reaching here means routing is broken.
        return (
            "Error: ask_user_question must be handled by the agent loop, "
            "not executed directly. This indicates an interception bug."
        )
