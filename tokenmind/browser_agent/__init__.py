"""Browser automation agent module.

Wraps the third-party ``agent-browser`` CLI (https://agent-browser.dev) into a
TokenMind module that exposes browser tasks via REST + the chat agent loop.
"""

from tokenmind.browser_agent.models import (
    ArtifactKind,
    BrowserArtifact,
    BrowserStep,
    BrowserTask,
    StepPhase,
    TaskStatus,
)

__all__ = [
    "ArtifactKind",
    "BrowserArtifact",
    "BrowserStep",
    "BrowserTask",
    "StepPhase",
    "TaskStatus",
]
