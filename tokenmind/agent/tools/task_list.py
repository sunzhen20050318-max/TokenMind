"""Task-list tool.

Lets the agent surface a structured to-do list to the user when working
through a complex multi-step task. Each call REPLACES the full list
(the agent always sends every task, not a delta) so the front-end
simply renders the latest snapshot.

Execution is intercepted by ``AgentLoop`` — the tool body itself is a
stub that should never run. Routing happens in the loop because we
need the calling ``InboundMessage`` (session/channel/chat) to publish
the WS frame that updates the bubble in the Web UI.
"""

from __future__ import annotations

from typing import Any

from tokenmind.agent.tools.base import Tool


class TaskListTool(Tool):
    @property
    def name(self) -> str:
        return "task_list"

    @property
    def description(self) -> str:
        return (
            "Maintain a structured task list for complex multi-step work "
            "(typically 3+ distinct steps). Call this FIRST to lay out "
            "the plan, then call again to update statuses as you progress. "
            "The tool REPLACES the full list each call — always include "
            "ALL tasks, not just the ones changing. "
            "\n\nStatus values: "
            "'pending' (not started), "
            "'in_progress' (currently working on — keep exactly ONE at a time), "
            "'completed' (done). "
            "\n\nDo NOT use this for simple single-step requests. "
            "Do NOT use as a chat aid (\"here's what I'll do\") — this is "
            "for tracked execution that the user watches. "
            "Mark tasks completed as soon as they're done; do not batch "
            "the final \"all done\" update."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 20,
                    "description": "The full task list (replaces previous list).",
                    "items": {
                        "type": "object",
                        "required": ["id", "content", "status"],
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": (
                                    "Stable identifier for this task. Keep "
                                    "the same id across updates so the UI "
                                    "can track each task individually."
                                ),
                            },
                            "content": {
                                "type": "string",
                                "description": "Short task description shown to the user.",
                            },
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                                "description": (
                                    "Task state. Exactly one task should be "
                                    "'in_progress' at any time."
                                ),
                            },
                        },
                    },
                }
            },
            "required": ["tasks"],
        }

    async def execute(self, **kwargs: Any) -> str:
        # AgentLoop intercepts this tool before invocation and handles
        # the WS round-trip; reaching here means routing is broken.
        return (
            "Error: task_list must be handled by the agent loop, not "
            "executed directly. This indicates an interception bug."
        )
