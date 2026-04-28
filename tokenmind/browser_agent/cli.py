"""Async subprocess wrapper around the ``agent-browser`` CLI.

We do not manage daemon processes — agent-browser does that internally per
``--session <name>`` flag. This wrapper just runs commands with ``--json``,
parses the response, and surfaces errors as ``AgentBrowserError`` so the
TaskService can decide whether to retry or escalate.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shutil
from typing import Any, Optional

logger = logging.getLogger("tokenmind.browser_agent.cli")


class AgentBrowserError(RuntimeError):
    """Raised when agent-browser CLI returns a non-success response."""


class AgentBrowserCLI:
    """Wraps the ``agent-browser`` CLI with isolated sessions per project."""

    def __init__(self, binary: str = "agent-browser") -> None:
        self.binary = binary

    @staticmethod
    def is_installed() -> bool:
        return shutil.which("agent-browser") is not None

    def session_args(self, project_id: str) -> list[str]:
        """Common prefix args used by every command for a given session."""
        return [self.binary, "--session", project_id, "--json"]

    async def run(
        self,
        project_id: str,
        command: str,
        *args: str,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Execute one agent-browser command and return its JSON payload.

        Returns the full ``{success, data, error}`` dict on success.
        Raises :class:`AgentBrowserError` on non-zero exit, malformed JSON,
        or ``success: false`` responses.
        """
        full_cmd = [*self.session_args(project_id), command, *args]
        logger.debug("agent-browser exec: %s", full_cmd)

        try:
            proc = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise AgentBrowserError(
                f"agent-browser CLI not found: {exc}. Run `npm install -g agent-browser`."
            ) from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            with contextlib.suppress(OSError):
                proc.kill()
            raise AgentBrowserError(
                f"agent-browser command `{command}` timed out after {timeout:.0f}s"
            ) from exc

        if proc.returncode != 0:
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
            raise AgentBrowserError(
                f"agent-browser exited with code {proc.returncode}: {stderr or '(no stderr)'}"
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise AgentBrowserError(
                f"agent-browser returned invalid JSON: {exc}; raw={stdout[:200]!r}"
            ) from exc

        # ``batch`` returns a list — the caller is responsible for inspecting
        # individual entries; we don't error here just because the wrapper
        # response isn't shaped like the unary-command envelope.
        if isinstance(payload, list):
            return {"success": True, "data": payload, "error": None}

        if not isinstance(payload, dict):
            raise AgentBrowserError(
                f"agent-browser returned unexpected JSON type: {type(payload).__name__}"
            )

        if not payload.get("success", False):
            raise AgentBrowserError(
                payload.get("error") or f"agent-browser command `{command}` failed"
            )

        return payload

    async def open_url(self, project_id: str, url: str, timeout: float = 60.0) -> dict[str, Any]:
        """Navigate to ``url``."""
        return await self.run(project_id, "open", url, timeout=timeout)

    async def snapshot(
        self,
        project_id: str,
        *,
        interactive_only: bool = True,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Capture an accessibility tree snapshot for LLM consumption."""
        args = ["snapshot"]
        if interactive_only:
            args.append("-i")
        return await self.run(project_id, *args, timeout=timeout)

    async def screenshot(
        self,
        project_id: str,
        path: Optional[str] = None,
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Take a screenshot. If ``path`` is given the file is written there."""
        args: list[str] = []
        if path:
            args.append(path)
        return await self.run(project_id, "screenshot", *args, timeout=timeout)

    async def click(
        self,
        project_id: str,
        selector: str,
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Click on an element by selector or @ref."""
        return await self.run(project_id, "click", selector, timeout=timeout)

    async def close_session(self, project_id: str) -> None:
        """Close a session and release the underlying browser tab."""
        try:
            await self.run(project_id, "close", timeout=15.0)
        except AgentBrowserError as exc:
            logger.warning("close session %s failed: %s", project_id, exc)
