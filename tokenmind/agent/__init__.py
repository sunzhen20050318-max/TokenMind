"""Agent core module."""

from __future__ import annotations

from typing import Any

__all__ = ["AgentLoop", "ContextBuilder", "MemoryStore", "SkillsLoader"]


def __getattr__(name: str) -> Any:
    """Load agent exports lazily to avoid import cycles between loop and sessions."""
    if name == "AgentLoop":
        from tokenmind.agent.loop import AgentLoop

        return AgentLoop
    if name == "ContextBuilder":
        from tokenmind.agent.context import ContextBuilder

        return ContextBuilder
    if name == "MemoryStore":
        from tokenmind.agent.memory import MemoryStore

        return MemoryStore
    if name == "SkillsLoader":
        from tokenmind.agent.skills import SkillsLoader

        return SkillsLoader
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
