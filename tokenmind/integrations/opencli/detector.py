"""Detection logic for the OpenCLI installation and Chrome bridge."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
from typing import Any

import httpx
from loguru import logger

from tokenmind.integrations.opencli.types import (
    InstallStep,
    OpencliInstallation,
    ProfileInfo,
)

DEFAULT_DAEMON_PORT = 19825
MIN_NODE_MAJOR = 20

CHROME_STORE_URL = (
    "https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk"
)
# Pinned version TokenMind is tested against. The one-click installer always
# requests exactly this — never "latest" — so adapter arg/output formats stay
# in sync with the parsing in service.py. Bump deliberately after re-testing.
PINNED_OPENCLI_VERSION = "1.8.0"
OPENCLI_PACKAGE = "@jackwener/opencli"
OPENCLI_INSTALL_COMMAND = f"npm install -g {OPENCLI_PACKAGE}@{PINNED_OPENCLI_VERSION}"
NODE_INSTALL_URL = "https://nodejs.org/"


async def install_opencli(
    version: str = PINNED_OPENCLI_VERSION, timeout: float = 240.0
) -> tuple[bool, str]:
    """Install the pinned OpenCLI npm package globally.

    Returns ``(ok, message)``. Only the npm package step is automatable — Node
    and the Chrome extension cannot be installed from here (Node is a system
    runtime; the extension is gated by browser security and must be added by
    the user in Chrome). Callers should re-detect afterward and guide the user
    through the remaining steps.
    """
    if shutil.which("npm") is None:
        return False, "未找到 npm —— 请先安装 Node.js (≥ 20)，npm 会随 Node 一起安装。"
    spec = f"{OPENCLI_PACKAGE}@{version}"
    code, out, err = await _run(["npm", "install", "-g", spec], timeout=timeout)
    if code == 0:
        return True, (out or err or f"已安装 {spec}").strip()
    detail = (err or out or f"npm 退出码 {code}").strip()
    return False, detail


def resolve_for_exec(argv: list[str]) -> list[str]:
    """Make argv runnable by ``asyncio.create_subprocess_exec`` cross-platform.

    npm installs ``opencli`` globally on Windows as ``opencli.cmd`` (a
    batch shim). asyncio's process spawn goes through Windows
    ``CreateProcess`` which can launch real ``.exe`` files but NOT
    ``.cmd`` / ``.bat`` shims — it fails with WinError 193 ("not a
    valid Win32 application"). The portable workaround is to wrap the
    command with ``cmd.exe /c``. We do that here based on the resolved
    file extension so the same code path works on macOS, Linux, and
    Windows.
    """
    if not argv:
        return argv
    head = argv[0]
    is_path = os.path.isabs(head) or os.sep in head or "/" in head
    full = head if is_path else (shutil.which(head) or head)
    if (
        sys.platform == "win32"
        and isinstance(full, str)
        and full.lower().endswith((".cmd", ".bat"))
    ):
        return ["cmd.exe", "/c", full, *argv[1:]]
    return [full, *argv[1:]]


async def _run(cmd: list[str], timeout: float = 8.0) -> tuple[int, str, str]:
    cmd = resolve_for_exec(cmd)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return 127, "", f"{cmd[0]}: not found"
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "", f"{cmd[0]}: timed out"
    return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def _parse_node_version(text: str) -> tuple[str | None, bool]:
    match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", text or "")
    if not match:
        return None, False
    major = int(match.group(1))
    version = f"{major}.{match.group(2)}.{match.group(3)}"
    return version, major >= MIN_NODE_MAJOR


async def _check_daemon(port: int) -> bool:
    """Probe the OpenCLI daemon's HTTP port.

    The daemon answers any HTTP request (404/200 both count); only a real
    refused connection means it's not running.
    """
    url = f"http://127.0.0.1:{port}/"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.get(url)
    except (httpx.ConnectError, httpx.ReadError):
        return False
    except httpx.HTTPError:
        return True
    return True


def _parse_profiles(stdout: str) -> list[ProfileInfo]:
    """Parse ``opencli profile list`` output.

    Actual format observed::

        Connected Browser Bridge profiles

          mrxe5zkr — connected v1.0.15
          * work (abc12345) — connected v1.0.15   # after `profile use`/`rename`

    Each profile lives on an indented line containing ``connected``.
    Context IDs are lowercase alphanumeric (not hex), so we can't rely
    on a strict charset. Aliases appear either bare (``work``) with the
    raw id in parentheses, or wrapped in ``[brackets]``.
    """
    profiles: list[ProfileInfo] = []
    for raw in (stdout or "").splitlines():
        if not raw or not raw.startswith((" ", "\t")):
            continue
        line = raw.strip()
        if not line or "connected" not in line.lower():
            continue
        is_default = line.startswith("*") or "(default)" in line.lower()
        body = line.lstrip("*").strip()
        head = re.split(r"\s+[—\-:]\s+", body, maxsplit=1)[0].strip()
        if not head:
            continue
        paren_match = re.search(r"[\[\(]([\w-]+)[\]\)]", head)
        if paren_match:
            wrapped = paren_match.group(1)
            outside = re.sub(r"\s*[\[\(].+?[\]\)]\s*", " ", head).strip()
            if wrapped and outside:
                alias, context_id = outside, wrapped
            else:
                alias, context_id = None, wrapped or outside
        else:
            tokens = head.split()
            context_id = tokens[0]
            alias = " ".join(tokens[1:]) if len(tokens) > 1 else None
        if not context_id:
            continue
        profiles.append(
            ProfileInfo(context_id=context_id, alias=alias, is_default=is_default)
        )
    return profiles


async def detect_installation(daemon_port: int = DEFAULT_DAEMON_PORT) -> OpencliInstallation:
    """Probe the host for OpenCLI readiness without raising."""

    missing: list[InstallStep] = []
    last_error: str | None = None

    opencli_path = shutil.which("opencli")
    opencli_installed = opencli_path is not None
    opencli_version: str | None = None
    node_version: str | None = None
    node_ok = False
    profiles: list[ProfileInfo] = []

    node_path = shutil.which("node")
    node_installed = node_path is not None
    if node_installed:
        code, out, err = await _run(["node", "--version"], timeout=4)
        if code == 0:
            node_version, node_ok = _parse_node_version(out or err)
        if not node_ok:
            missing.append(
                InstallStep(
                    key="node",
                    title="升级 Node.js 到 20+",
                    detail=f"当前 Node 版本 {node_version or 'unknown'}, OpenCLI 要求 ≥ {MIN_NODE_MAJOR}",
                    url=NODE_INSTALL_URL,
                )
            )
    else:
        missing.append(
            InstallStep(
                key="node",
                title="安装 Node.js 20+",
                detail="OpenCLI 是 Node 包，需要 Node 20 或以上",
                url=NODE_INSTALL_URL,
            )
        )

    if opencli_installed:
        code, out, err = await _run(["opencli", "--version"], timeout=4)
        if code == 0:
            opencli_version = (out or err).strip().splitlines()[0] if (out or err).strip() else None
    else:
        missing.append(
            InstallStep(
                key="opencli",
                title="安装 OpenCLI",
                detail="全局安装 OpenCLI npm 包",
                command=OPENCLI_INSTALL_COMMAND,
            )
        )

    daemon_running = False
    if opencli_installed and node_ok:
        try:
            daemon_running = await _check_daemon(daemon_port)
        except Exception as exc:  # noqa: BLE001
            last_error = f"daemon probe failed: {exc}"
            logger.exception("OpenCLI daemon probe failed")

    if opencli_installed and node_ok and not daemon_running:
        missing.append(
            InstallStep(
                key="extension",
                title="安装 / 启用 Chrome 扩展并打开 Chrome",
                detail=(
                    "OpenCLI 通过 Chrome 扩展 + 本地 daemon (端口 "
                    f"{daemon_port}) 工作。打开 Chrome 并安装扩展后, daemon 会自动启动。"
                ),
                url=CHROME_STORE_URL,
            )
        )

    if daemon_running and opencli_installed:
        code, out, err = await _run(["opencli", "profile", "list"], timeout=6)
        if code == 0:
            profiles = _parse_profiles(out)
        elif err:
            logger.debug("opencli profile list returned non-zero: {}", err.strip())

    ready = (
        opencli_installed
        and node_ok
        and daemon_running
        and not missing
    )

    return OpencliInstallation(
        opencli_installed=opencli_installed,
        opencli_version=opencli_version,
        opencli_path=opencli_path,
        node_installed=node_installed,
        node_version=node_version,
        node_ok=node_ok,
        daemon_port=daemon_port,
        daemon_running=daemon_running,
        profiles=profiles,
        missing_steps=missing,
        ready=ready,
        last_error=last_error,
    )


def installation_to_dict(install: OpencliInstallation) -> dict[str, Any]:
    """Serialize for JSON / API output."""
    return {
        "ready": install.ready,
        "opencli": {
            "installed": install.opencli_installed,
            "version": install.opencli_version,
            "path": install.opencli_path,
        },
        "node": {
            "installed": install.node_installed,
            "version": install.node_version,
            "ok": install.node_ok,
            "required_major": MIN_NODE_MAJOR,
        },
        "daemon": {
            "port": install.daemon_port,
            "running": install.daemon_running,
        },
        "profiles": [
            {"context_id": p.context_id, "alias": p.alias, "is_default": p.is_default}
            for p in install.profiles
        ],
        "missing_steps": [
            {
                "key": s.key,
                "title": s.title,
                "detail": s.detail,
                "command": s.command,
                "url": s.url,
            }
            for s in install.missing_steps
        ],
        "last_error": install.last_error,
    }
