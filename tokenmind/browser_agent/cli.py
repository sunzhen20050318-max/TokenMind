"""Async subprocess wrapper around the ``agent-browser`` CLI.

We do not manage daemon processes — agent-browser does that internally per
``--session <name>`` flag. This wrapper just runs commands with ``--json``,
parses the response, and surfaces errors as ``AgentBrowserError`` so the
TaskService can decide whether to retry or escalate.

Coverage in M2 is the subset of agent-browser commands the LLM ReAct loop
actually needs:

* navigation — open / back / forward / reload
* interaction — click / dblclick / type / fill / press / hover / focus /
  check / uncheck / select / scroll / scrollintoview / wait
* observation — snapshot / screenshot / get / is / page text / pdf
* utility — eval / batch / close_session

For commands that take user-supplied free-text (type / fill / press / eval
/ JS expressions), we always pass the text as a separate argv entry — never
through a shell — so injection is impossible.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shlex
import shutil
from typing import Any, Iterable, Optional, Sequence

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

    # ── core executor ───────────────────────────────────────────────────

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

    # ── navigation ──────────────────────────────────────────────────────

    async def open_url(self, project_id: str, url: str, timeout: float = 60.0) -> dict[str, Any]:
        """Navigate to ``url``."""
        return await self.run(project_id, "open", url, timeout=timeout)

    async def back(self, project_id: str, timeout: float = 30.0) -> dict[str, Any]:
        return await self.run(project_id, "back", timeout=timeout)

    async def forward(self, project_id: str, timeout: float = 30.0) -> dict[str, Any]:
        return await self.run(project_id, "forward", timeout=timeout)

    async def reload(self, project_id: str, timeout: float = 30.0) -> dict[str, Any]:
        return await self.run(project_id, "reload", timeout=timeout)

    # ── interaction ─────────────────────────────────────────────────────

    async def click(self, project_id: str, selector: str, timeout: float = 30.0) -> dict[str, Any]:
        """Click on an element by selector or @ref."""
        return await self.run(project_id, "click", selector, timeout=timeout)

    async def dblclick(self, project_id: str, selector: str, timeout: float = 30.0) -> dict[str, Any]:
        return await self.run(project_id, "dblclick", selector, timeout=timeout)

    async def type_text(
        self,
        project_id: str,
        selector: str,
        text: str,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Type into an element (appends to existing text)."""
        return await self.run(project_id, "type", selector, text, timeout=timeout)

    async def fill(
        self,
        project_id: str,
        selector: str,
        text: str,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Clear the element then type ``text`` into it."""
        return await self.run(project_id, "fill", selector, text, timeout=timeout)

    async def press(self, project_id: str, key: str, timeout: float = 30.0) -> dict[str, Any]:
        """Press a key (Enter, Tab, Control+a, Escape, etc.)."""
        return await self.run(project_id, "press", key, timeout=timeout)

    async def hover(self, project_id: str, selector: str, timeout: float = 30.0) -> dict[str, Any]:
        return await self.run(project_id, "hover", selector, timeout=timeout)

    async def focus(self, project_id: str, selector: str, timeout: float = 30.0) -> dict[str, Any]:
        return await self.run(project_id, "focus", selector, timeout=timeout)

    async def check(self, project_id: str, selector: str, timeout: float = 30.0) -> dict[str, Any]:
        return await self.run(project_id, "check", selector, timeout=timeout)

    async def uncheck(self, project_id: str, selector: str, timeout: float = 30.0) -> dict[str, Any]:
        return await self.run(project_id, "uncheck", selector, timeout=timeout)

    async def select(
        self,
        project_id: str,
        selector: str,
        values: Sequence[str],
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Select dropdown option(s) by value/label."""
        return await self.run(project_id, "select", selector, *values, timeout=timeout)

    async def scroll(
        self,
        project_id: str,
        direction: str,
        pixels: Optional[int] = None,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        """Scroll the page. ``direction`` is one of up/down/left/right."""
        if direction not in {"up", "down", "left", "right"}:
            raise ValueError(f"invalid scroll direction: {direction}")
        args: list[str] = [direction]
        if pixels is not None:
            args.append(str(pixels))
        return await self.run(project_id, "scroll", *args, timeout=timeout)

    async def scroll_into_view(
        self, project_id: str, selector: str, timeout: float = 15.0
    ) -> dict[str, Any]:
        return await self.run(project_id, "scrollintoview", selector, timeout=timeout)

    async def wait(
        self,
        project_id: str,
        target: str,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Wait for an element selector or a fixed milliseconds duration."""
        return await self.run(project_id, "wait", target, timeout=timeout)

    # ── observation ─────────────────────────────────────────────────────

    async def snapshot(
        self,
        project_id: str,
        *,
        interactive_only: bool = True,
        compact: bool = False,
        depth: Optional[int] = None,
        selector: Optional[str] = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Capture an accessibility tree snapshot for LLM consumption."""
        args: list[str] = []
        if interactive_only:
            args.append("-i")
        if compact:
            args.append("-c")
        if depth is not None:
            args.extend(["-d", str(depth)])
        if selector is not None:
            args.extend(["-s", selector])
        return await self.run(project_id, "snapshot", *args, timeout=timeout)

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

    async def pdf(
        self,
        project_id: str,
        path: str,
        *,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        """Save the current page as a PDF at ``path``."""
        return await self.run(project_id, "pdf", path, timeout=timeout)

    async def get(
        self,
        project_id: str,
        what: str,
        selector: Optional[str] = None,
        *,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        """Get info about the page or an element.

        ``what`` is one of: text, html, value, attr, title, url, count, box,
        styles, cdp-url. ``attr`` requires an additional attribute name passed
        as ``selector`` parameter (caller embeds it).
        """
        args: list[str] = [what]
        if selector is not None:
            args.append(selector)
        return await self.run(project_id, "get", *args, timeout=timeout)

    async def is_state(
        self,
        project_id: str,
        what: str,
        selector: str,
        *,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        """Check element state (visible / enabled / checked)."""
        return await self.run(project_id, "is", what, selector, timeout=timeout)

    # ── utility ─────────────────────────────────────────────────────────

    async def eval_js(
        self,
        project_id: str,
        expression: str,
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Run a JavaScript expression in the page context."""
        return await self.run(project_id, "eval", expression, timeout=timeout)

    async def batch(
        self,
        project_id: str,
        commands: Iterable[Sequence[str]],
        *,
        bail: bool = False,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        """Execute multiple commands sequentially.

        ``commands`` is an iterable of argv-style sequences such as
        ``[("snapshot", "-i"), ("screenshot",)]``. Each sequence is joined
        with shell-style quoting so values with spaces survive intact.

        Returns the wrapped envelope ``{success, data: list, error: None}``
        where ``data`` is the list of per-command responses. ``bail=True``
        passes ``--bail`` so the first failing command short-circuits.
        """
        joined = [shlex.join(cmd) for cmd in commands]
        if not joined:
            raise ValueError("batch requires at least one command")
        args: list[str] = []
        if bail:
            args.append("--bail")
        args.extend(joined)
        return await self.run(project_id, "batch", *args, timeout=timeout)

    async def close_session(self, project_id: str) -> None:
        """Close a session and release the underlying browser tab."""
        try:
            await self.run(project_id, "close", timeout=15.0)
        except AgentBrowserError as exc:
            logger.warning("close session %s failed: %s", project_id, exc)
