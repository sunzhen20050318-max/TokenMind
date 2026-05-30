"""Tool registry for dynamic tool management."""

import asyncio
from typing import Any

from tokenmind.agent.tools.base import Tool


class ToolRegistry:
    """
    Registry for agent tools.

    Allows dynamic registration and execution of tools.
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def get_definitions(self) -> list[dict[str, Any]]:
        """Get tool definitions in OpenAI format, filtered by availability.

        Tools whose ``is_available()`` returns ``False`` are skipped so the
        LLM doesn't see them in its tool list. Wiki tools use this to stay
        hidden until the user picks an active Wiki KB.
        """
        return [
            tool.to_schema()
            for tool in self._tools.values()
            if tool.is_available()
        ]

    async def execute(self, name: str, params: dict[str, Any], timeout: float | None = None) -> str:
        """Execute a tool by name with given parameters.

        When ``timeout`` (seconds) is set, a runaway tool is abandoned after
        that long so it can't hang the whole turn — the caller gets an error
        string and the agent loop keeps control. The underlying coroutine is
        cancelled (a blocking ``to_thread`` may keep running in the background,
        but it no longer blocks the conversation). An external cancel (user
        ``/stop``) still propagates, since CancelledError isn't caught here.
        """
        _HINT = "\n\n[Analyze the error above and try a different approach.]"

        tool = self._tools.get(name)
        if not tool:
            return f"Error: Tool '{name}' not found. Available: {', '.join(self.tool_names)}"

        try:
            # Attempt to cast parameters to match schema types
            params = tool.cast_params(params)

            # Validate parameters
            errors = tool.validate_params(params)
            if errors:
                return f"Error: Invalid parameters for tool '{name}': " + "; ".join(errors) + _HINT
            if timeout is not None and timeout > 0:
                result = await asyncio.wait_for(tool.execute(**params), timeout)
            else:
                result = await tool.execute(**params)
            if isinstance(result, str) and result.startswith("Error"):
                return result + _HINT
            return result
        except asyncio.TimeoutError:
            return (
                f"Error: 工具 {name} 执行超时（>{timeout:g}s），已放弃。"
                "请缩小范围或换一种方式。" + _HINT
            )
        except Exception as e:
            return f"Error executing {name}: {str(e)}" + _HINT

    @property
    def tool_names(self) -> list[str]:
        """Get list of registered tool names."""
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
