"""Detect whether agent-browser CLI + Chrome for Testing are installed.

This drives the first-run setup wizard on the frontend so users get a clear
guide instead of a cryptic subprocess error.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from tokenmind.browser_agent.cli import resolve_agent_browser_binary

logger = logging.getLogger("tokenmind.browser_agent.env_check")

_VERSION_RE = re.compile(r"(\d+(?:\.\d+)+)")


@dataclass
class EnvCheckResult:
    cli_installed: bool
    chrome_installed: bool
    version: Optional[str] = None
    issues: list[str] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        return self.cli_installed and self.chrome_installed and not self.issues


async def check_environment() -> EnvCheckResult:
    """Check if agent-browser is installed without launching a browser window.

    ``agent-browser doctor`` performs a launch test, which is useful manually
    but surprising in the Web UI because it opens Chrome during a passive
    readiness check. Here we only inspect the CLI and the local browser cache.
    """
    binary = resolve_agent_browser_binary()
    if binary == "agent-browser" and not shutil.which("agent-browser"):
        return EnvCheckResult(
            cli_installed=False,
            chrome_installed=False,
            issues=[
                "agent-browser CLI 未在 PATH 中找到。请运行 `npm install -g agent-browser`。",
            ],
        )

    version, version_issue = await _read_cli_version(binary)
    chrome_installed = _has_chrome_for_testing()
    issues: list[str] = []
    if version_issue:
        issues.append(version_issue)
    if not chrome_installed:
        issues.append("Chrome for Testing 未安装。请运行 `agent-browser install`。")

    return EnvCheckResult(
        cli_installed=True,
        chrome_installed=chrome_installed,
        version=version,
        issues=issues,
    )


async def _read_cli_version(binary: str) -> tuple[Optional[str], Optional[str]]:
    try:
        proc = await asyncio.create_subprocess_exec(
            binary,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=8.0)
    except asyncio.TimeoutError:
        return None, "`agent-browser --version` 超时未返回。"
    except OSError as exc:
        return None, f"agent-browser 版本检测失败：{exc}"

    if proc.returncode != 0:
        message = stderr.decode("utf-8", errors="replace").strip()
        return None, f"agent-browser 版本检测失败：{message or proc.returncode}"

    output = stdout.decode("utf-8", errors="replace").strip()
    match = _VERSION_RE.search(output)
    return (match.group(1) if match else None), None


def _has_chrome_for_testing() -> bool:
    configured = os.environ.get("AGENT_BROWSER_EXECUTABLE_PATH")
    if configured and Path(configured).exists():
        return True

    browser_root = Path.home() / ".agent-browser" / "browsers"
    if not browser_root.exists():
        return False

    executable_names = ("chrome.exe", "chrome", "Chromium", "Google Chrome for Testing")
    for name in executable_names:
        if any(browser_root.glob(f"**/{name}")):
            return True
    return False
