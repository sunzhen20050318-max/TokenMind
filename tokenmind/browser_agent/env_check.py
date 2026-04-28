"""Detect whether agent-browser CLI + Chrome for Testing are installed.

This drives the first-run setup wizard on the frontend so users get a clear
guide instead of a cryptic subprocess error.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("tokenmind.browser_agent.env_check")


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
    """Check if agent-browser is properly installed and Chrome is downloaded."""
    if not shutil.which("agent-browser"):
        return EnvCheckResult(
            cli_installed=False,
            chrome_installed=False,
            issues=[
                "agent-browser CLI 未在 PATH 中找到。请运行 `npm install -g agent-browser`。",
            ],
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            "agent-browser",
            "doctor",
            "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=20.0)
        payload = json.loads(stdout.decode("utf-8"))
    except asyncio.TimeoutError:
        return EnvCheckResult(
            cli_installed=True,
            chrome_installed=False,
            issues=["`agent-browser doctor --json` 超时未返回。"],
        )
    except (OSError, json.JSONDecodeError) as exc:
        return EnvCheckResult(
            cli_installed=True,
            chrome_installed=False,
            issues=[f"agent-browser doctor 调用失败：{exc}"],
        )

    checks = payload.get("checks") if isinstance(payload, dict) else None
    if not isinstance(checks, list):
        return EnvCheckResult(
            cli_installed=True,
            chrome_installed=False,
            issues=["agent-browser doctor 输出格式异常。"],
        )

    chrome_installed = False
    version: Optional[str] = None
    issues: list[str] = []

    for check in checks:
        if not isinstance(check, dict):
            continue
        check_id = check.get("id")
        status = check.get("status")
        message = check.get("message") or ""

        if check_id == "env.version" and isinstance(message, str):
            # Message looks like "CLI version 0.26.0 (macos x86_64)".
            for token in message.split():
                if token.replace(".", "").isdigit():
                    version = token
                    break
        if check_id == "chrome.installed" and status == "pass":
            chrome_installed = True
        if status == "fail":
            issues.append(message)

    if not chrome_installed and not issues:
        issues.append("Chrome for Testing 未安装。请运行 `agent-browser install`。")

    return EnvCheckResult(
        cli_installed=True,
        chrome_installed=chrome_installed,
        version=version,
        issues=issues,
    )
