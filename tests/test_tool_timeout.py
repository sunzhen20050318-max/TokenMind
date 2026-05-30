"""ToolRegistry.execute timeout guard — a runaway tool must not hang the turn."""

import asyncio
from typing import Any

import pytest

from tokenmind.agent.tools.base import Tool
from tokenmind.agent.tools.registry import ToolRegistry


class SlowTool(Tool):
    @property
    def name(self) -> str:
        return "slow"

    @property
    def description(self) -> str:
        return "sleeps forever"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        await asyncio.sleep(10)
        return "done"


class FastTool(Tool):
    @property
    def name(self) -> str:
        return "fast"

    @property
    def description(self) -> str:
        return "returns immediately"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        return "quick"


@pytest.mark.asyncio
async def test_execute_times_out_a_runaway_tool() -> None:
    reg = ToolRegistry()
    reg.register(SlowTool())

    result = await reg.execute("slow", {}, timeout=0.05)

    assert result.startswith("Error")
    assert "超时" in result or "timeout" in result.lower()


@pytest.mark.asyncio
async def test_execute_returns_normally_within_timeout() -> None:
    reg = ToolRegistry()
    reg.register(FastTool())

    result = await reg.execute("fast", {}, timeout=5)

    assert result == "quick"


@pytest.mark.asyncio
async def test_execute_without_timeout_still_works() -> None:
    reg = ToolRegistry()
    reg.register(FastTool())

    result = await reg.execute("fast", {})

    assert result == "quick"
