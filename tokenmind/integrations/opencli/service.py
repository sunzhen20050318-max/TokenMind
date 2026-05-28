"""OpenCLI service: subprocess wrapper, caching, risk classification."""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from loguru import logger

from tokenmind.audit import AuditLogger
from tokenmind.integrations.opencli.detector import (
    DEFAULT_DAEMON_PORT,
    detect_installation,
    resolve_for_exec,
)
from tokenmind.integrations.opencli.types import (
    OpencliInstallation,
    ProfileInfo,
    RiskLevel,
    RunResult,
    SiteCommand,
    SiteInfo,
)

_INSTALL_TTL_S = 30
_SITES_TTL_S = 24 * 3600
_PROFILES_TTL_S = 30

_DEFAULT_TIMEOUT_S = 60.0
_LIST_TIMEOUT_S = 10.0

_SENSITIVE_SELECTOR_RE = re.compile(
    r"(password|passwd|pwd|pin|cvv|secret|token|otp|auth)",
    re.IGNORECASE,
)

_WRITE_COMMAND_KEYWORDS = {
    "post",
    "publish",
    "like",
    "unlike",
    "follow",
    "unfollow",
    "comment",
    "reply",
    "send",
    "upvote",
    "downvote",
    "save",
    "unsave",
    "subscribe",
    "unsubscribe",
    "delete",
    "remove",
    "block",
    "unblock",
    "favorite",
    "unfavorite",
    "bookmark",
    "unbookmark",
    "hide",
    "accept",
    "connect",
}

_READ_ONLY_PRIMITIVES = {
    "open",
    "state",
    "extract",
    "get",
    "find",
    "scroll",
    "wait",
    "back",
    "screenshot",
    "frames",
    "tab",
}

_WRITE_PRIMITIVES = {
    "click",
    "type",
    "fill",
    "select",
    "keys",
    "eval",
    "network",
    "close",
}


# Per-action positional argument order. OpenCLI's browser primitives take
# their primary inputs as positionals (e.g. ``opencli browser <s> open <url>``),
# not as ``--flag`` options. Anything not listed here defaults to no
# positionals; remaining kwargs are passed through as ``--flag value``.
# Fields the model commonly passes that map to opencli flags. Anything
# in this map will be forwarded as ``--<key> <value>`` IF the action's
# allowlist accepts it. Anything outside the action's allowlist is
# dropped silently before subprocess exec — opencli's commander errors
# hard on unknown options, and the model was burning turns chasing
# those "unknown option" messages.
_UNIVERSAL_FLAG_FIELDS = frozenset({"tab", "window"})

# Per-action accepted flag fields (positionals are handled separately).
# Pulled from each action's ``--help``. An action absent from this map
# accepts everything (legacy permissive behaviour, useful for actions
# we haven't surveyed yet).
_PRIMITIVE_VALID_FLAGS: dict[str, frozenset[str]] = {
    "click": frozenset({"role", "name", "label", "text", "testid", "css"}),
    "dblclick": frozenset({"role", "name", "label", "text", "testid", "css"}),
    "hover": frozenset({"role", "name", "label", "text", "testid", "css"}),
    "focus": frozenset({"role", "name", "label", "text", "testid", "css"}),
    "check": frozenset({"role", "name", "label", "text", "testid", "css"}),
    "uncheck": frozenset({"role", "name", "label", "text", "testid", "css"}),
    "type": frozenset({"role", "name", "label", "text", "testid", "css", "delay"}),
    "fill": frozenset({"role", "name", "label", "text", "testid", "css"}),
    "select": frozenset({"role", "name", "label", "text", "testid", "css"}),
    "find": frozenset({"role", "name", "label", "text", "testid", "css", "limit", "text-max"}),
    "extract": frozenset({"selector", "chunk-size", "start"}),
    "scroll": frozenset({"amount"}),
    "wait": frozenset({"timeout"}),
    "screenshot": frozenset(),
    "open": frozenset(),
    "back": frozenset(),
    "close": frozenset(),
    "state": frozenset(),
    "frames": frozenset(),
    "keys": frozenset(),
    "eval": frozenset(),
    "analyze": frozenset(),
    "get": frozenset(),
    "tab": frozenset(),
    "dialog": frozenset(),
    "drag": frozenset({"from-role", "from-name", "from-css", "to-role", "to-name", "to-css"}),
}


_PRIMITIVE_POSITIONALS: dict[str, list[str]] = {
    "open": ["url"],
    "click": ["selector"],
    "dblclick": ["selector"],
    "hover": ["selector"],
    "focus": ["selector"],
    "type": ["selector", "value"],
    "fill": ["selector", "value"],
    "select": ["selector", "value"],
    "wait": ["type", "value"],
    "check": ["selector"],
    "uncheck": ["selector"],
    "keys": ["value"],
    "eval": ["value"],
    "upload": ["selector", "value"],
    "scroll": ["direction"],
    "screenshot": ["path"],
    "analyze": ["url"],
    "verify": ["name"],
    "init": ["name"],
    "tab": ["command"],
    "get": ["command"],
    "dialog": ["command"],
    "drag": ["source", "target"],
    # find / extract / state / back / close / frames / network / console /
    # bind / unbind take everything as flags — no positionals.
}


FEATURED_SITES: list[SiteInfo] = [
    SiteInfo(
        site="bilibili",
        featured=True,
        commands=[
            SiteCommand("hot", "热门视频"),
            SiteCommand("search", "搜索"),
            SiteCommand("ranking", "排行榜"),
            SiteCommand("video", "视频详情"),
            SiteCommand("comments", "评论"),
            SiteCommand("summary", "视频总结"),
        ],
    ),
    SiteInfo(
        site="zhihu",
        featured=True,
        commands=[
            SiteCommand("hot", "热榜"),
            SiteCommand("search", "搜索"),
            SiteCommand("question", "问题详情"),
            SiteCommand("answer", "回答详情"),
        ],
    ),
    SiteInfo(
        site="xiaohongshu",
        featured=True,
        commands=[
            SiteCommand("search", "搜索笔记"),
            SiteCommand("note", "笔记详情"),
            SiteCommand("notifications", "通知"),
            SiteCommand("comments", "评论"),
            SiteCommand("feed", "首页流"),
        ],
    ),
    SiteInfo(
        site="twitter",
        featured=True,
        commands=[
            SiteCommand("trending", "趋势"),
            SiteCommand("search", "搜索推文"),
            SiteCommand("timeline", "时间线"),
            SiteCommand("notifications", "通知"),
        ],
    ),
    SiteInfo(
        site="reddit",
        featured=True,
        commands=[
            SiteCommand("hot", "热门"),
            SiteCommand("subreddit", "子版"),
            SiteCommand("search", "搜索"),
            SiteCommand("read", "帖子详情"),
        ],
    ),
    SiteInfo(
        site="hackernews",
        featured=True,
        commands=[
            SiteCommand("top", "Top"),
            SiteCommand("new", "新帖"),
            SiteCommand("best", "Best"),
            SiteCommand("ask", "Ask HN"),
            SiteCommand("show", "Show HN"),
        ],
    ),
    SiteInfo(
        site="linkedin",
        featured=True,
        commands=[
            SiteCommand("inbox", "收件箱"),
            SiteCommand("posts", "动态"),
            SiteCommand("search", "搜索"),
            SiteCommand("profile-read", "个人主页"),
        ],
    ),
    SiteInfo(
        site="amazon",
        featured=True,
        commands=[
            SiteCommand("bestsellers", "畅销榜"),
            SiteCommand("search", "搜索"),
            SiteCommand("product", "商品详情"),
        ],
    ),
    SiteInfo(
        site="claude",
        featured=True,
        commands=[
            SiteCommand("ask", "提问"),
            SiteCommand("history", "历史"),
            SiteCommand("read", "对话详情"),
        ],
    ),
    SiteInfo(
        site="gemini",
        featured=True,
        commands=[
            SiteCommand("ask", "提问"),
            SiteCommand("image", "图像"),
            SiteCommand("deep-research", "深度研究"),
        ],
    ),
]


class OpenCLIService:
    """Thin async wrapper around the ``opencli`` CLI."""

    def __init__(
        self,
        audit: AuditLogger,
        *,
        daemon_port: int = DEFAULT_DAEMON_PORT,
        default_timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self._audit = audit
        self._daemon_port = daemon_port
        self._default_timeout = default_timeout_s
        self._install_cache: OpencliInstallation | None = None
        self._install_cache_at: float = 0.0
        self._sites_cache: list[SiteInfo] | None = None
        self._sites_cache_at: float = 0.0
        self._profiles_cache: list[ProfileInfo] | None = None
        self._profiles_cache_at: float = 0.0
        # Per (site, command) probe cache: True ⇔ adapter accepts the
        # ``--site-session`` / ``--window`` browser flags. Non-browser
        # adapters (HTTP-only, e.g. ``hackernews top``) reject them with
        # ``unknown option`` so we must avoid passing them. Probed on
        # first use via ``--help`` and cached for the process lifetime.
        self._browser_flag_cache: dict[tuple[str, str], bool] = {}
        self._lock = asyncio.Lock()

    @property
    def daemon_port(self) -> int:
        return self._daemon_port

    async def detect(self, *, force: bool = False) -> OpencliInstallation:
        now = time.time()
        if (
            not force
            and self._install_cache is not None
            and now - self._install_cache_at < _INSTALL_TTL_S
        ):
            return self._install_cache
        async with self._lock:
            install = await detect_installation(self._daemon_port)
            self._install_cache = install
            self._install_cache_at = now
            return install

    def featured_sites(self) -> list[SiteInfo]:
        return list(FEATURED_SITES)

    async def list_sites(self, *, force: bool = False) -> list[SiteInfo]:
        now = time.time()
        if (
            not force
            and self._sites_cache is not None
            and now - self._sites_cache_at < _SITES_TTL_S
        ):
            return self._sites_cache

        install = await self.detect()
        if not install.opencli_installed:
            return list(FEATURED_SITES)

        sites = await self._discover_sites()
        merged = self._merge_with_featured(sites)
        self._sites_cache = merged
        self._sites_cache_at = now
        return merged

    async def list_profiles(self, *, force: bool = False) -> list[ProfileInfo]:
        now = time.time()
        if (
            not force
            and self._profiles_cache is not None
            and now - self._profiles_cache_at < _PROFILES_TTL_S
        ):
            return self._profiles_cache
        install = await self.detect()
        self._profiles_cache = list(install.profiles)
        self._profiles_cache_at = now
        return self._profiles_cache

    async def set_default_profile(self, alias_or_id: str) -> RunResult:
        return await self._run(
            ["opencli", "profile", "use", alias_or_id],
            audit_action="opencli.profile.use",
            timeout=_LIST_TIMEOUT_S,
        )

    async def _site_supports_browser_flags(self, site: str, command: str) -> bool:
        """Cache-backed probe: does (site, command) accept ``--site-session``?

        Non-browser adapters (HTTP-only) reject these flags with
        ``unknown option``. We learn each adapter's behavior by parsing
        its ``--help`` output once and caching.
        """
        key = (site, command)
        cached = self._browser_flag_cache.get(key)
        if cached is not None:
            return cached
        code, out, err = await _exec(
            ["opencli", site, command, "--help"], timeout=_LIST_TIMEOUT_S
        )
        if code != 0:
            self._browser_flag_cache[key] = False
            return False
        supports = "--site-session" in (out or "") or "Browser: yes" in (out or "")
        self._browser_flag_cache[key] = supports
        return supports

    async def run_site_command(
        self,
        site: str,
        command: str,
        args: dict[str, Any] | None = None,
        *,
        positional: list[str] | None = None,
        profile: str | None = None,
        timeout: float | None = None,
        session_key: str | None = None,
    ) -> RunResult:
        argv = ["opencli"]
        if profile:
            argv += ["--profile", profile]
        argv += [site, command]
        if positional:
            argv += [str(p) for p in positional if p is not None and p != ""]

        flag_args = dict(args or {})
        # Only inject browser-control flags when the adapter actually
        # supports them; HTTP-only adapters (e.g. hackernews) error on
        # unknown options. See ``_site_supports_browser_flags``.
        #
        # Default: ``--window background`` so adapter Chromium stays
        # invisible (mode=site is for pure data fetch — the user reads
        # the result in chat, not in a popup window). We deliberately do
        # NOT default ``--site-session persistent``: in OpenCLI parlance
        # ``persistent`` means "this is an INTERACTIVE adapter, surface
        # the tab to the user for continuity", which causes the very
        # window-pop the user just complained about. Default ephemeral
        # = clean headless one-shot. Callers can still opt in via
        # ``args: {"site-session": "persistent"}`` when they actually
        # want the tab visible.
        if await self._site_supports_browser_flags(site, command):
            if "window" not in flag_args:
                flag_args["window"] = "background"

        argv += _flatten_args(flag_args)
        return await self._run(
            argv,
            audit_action="opencli.site.run",
            timeout=timeout or self._default_timeout,
            session_key=session_key,
            details={
                "site": site,
                "command": command,
                "positional": positional,
                "args": _safe_args(args),
            },
        )

    async def run_browser_primitive(
        self,
        session: str,
        action: str,
        options: dict[str, Any] | None = None,
        *,
        positional: list[str] | None = None,
        profile: str | None = None,
        timeout: float | None = None,
        session_key: str | None = None,
    ) -> RunResult:
        # ``keys`` via OpenCLI uses CDP ``Input.dispatchKeyEvent`` (OS-level
        # key events). React/Vue SPAs (xiaohongshu, twitter, etc.) listen
        # through synthetic event systems that often ignore those — they
        # respond only to JS-dispatched ``KeyboardEvent``. We transparently
        # rewrite ``keys`` into an ``eval`` call that dispatches the
        # synthetic event sequence on the focused element so the action
        # actually triggers the page's handlers. Verified e2e against xhs.
        if action == "keys" and positional is None:
            options = options or {}
            key_spec = str(options.get("value") or "").strip()
            if key_spec:
                action = "eval"
                options = {"value": _build_synthetic_key_script(key_spec)}

        argv = ["opencli"]
        if profile:
            argv += ["--profile", profile]
        argv += ["browser", session]

        remaining = dict(options or {})

        # ``--window`` is parsed by the ``browser`` subcommand AFTER the
        # ``<session>`` positional and BEFORE the inner ``<action>``. The
        # docs say ``opencli browser <session> <command> [options]`` but
        # empirically commander only accepts it in that gap — putting it
        # before <session> consumes the session as a subcommand name,
        # putting it after <action> trips "unknown option --window"
        # because the inner action's own commander has no --window flag.
        window = remaining.pop("window", None) or "foreground"
        argv += ["--window", str(window)]

        argv.append(action)

        if positional is not None:
            # Explicit positional list (escape hatch for multi-level
            # subcommands like ``tab new <url>`` or ``get text <sel>``).
            # Bypasses the per-action mapping entirely.
            argv += [str(p) for p in positional if p is not None and p != ""]
        else:
            for pos_key in _PRIMITIVE_POSITIONALS.get(action, []):
                value = remaining.pop(pos_key, None)
                if value is None or value == "":
                    continue
                argv.append(str(value))

        # Per-action flag allowlist: drop anything not valid for this
        # action so a stray ``value`` on a ``click`` (or similar) doesn't
        # produce ``unknown option`` from opencli's commander.
        valid = _PRIMITIVE_VALID_FLAGS.get(action)
        if valid is not None:
            allowed = valid | _UNIVERSAL_FLAG_FIELDS
            remaining = {k: v for k, v in remaining.items() if k in allowed}

        argv += _flatten_args(remaining)

        return await self._run(
            argv,
            audit_action="opencli.browser.run",
            timeout=timeout or self._default_timeout,
            session_key=session_key,
            details={
                "session": session,
                "action": action,
                "options": _safe_args(options),
            },
        )

    def classify_risk(
        self,
        mode: str,
        *,
        site: str | None = None,
        command: str | None = None,
        action: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> RiskLevel:
        if mode == "site":
            cmd = (command or "").lower()
            for keyword in _WRITE_COMMAND_KEYWORDS:
                if keyword in cmd:
                    return "high"
            return "low"

        if mode == "primitive":
            act = (action or "").lower()
            if act in _READ_ONLY_PRIMITIVES:
                return "low"
            if act == "type":
                selector = (options or {}).get("selector") or ""
                if _SENSITIVE_SELECTOR_RE.search(str(selector)):
                    return "high"
                return "medium"
            if act in _WRITE_PRIMITIVES:
                if act in {"eval", "network"}:
                    return "high"
                return "medium"
            return "medium"

        return "medium"

    async def _discover_sites(self) -> list[SiteInfo]:
        code, out, err = await _exec(["opencli", "list", "--json"], timeout=_LIST_TIMEOUT_S)
        if code == 0 and out.strip():
            sites = _parse_sites_json(out)
            if sites:
                return sites
        code, out, err = await _exec(["opencli", "list"], timeout=_LIST_TIMEOUT_S)
        if code != 0:
            logger.debug("opencli list failed: {}", err.strip())
            return []
        return _parse_sites_text(out)

    def _merge_with_featured(self, discovered: list[SiteInfo]) -> list[SiteInfo]:
        by_name = {s.site: s for s in discovered}
        for featured in FEATURED_SITES:
            existing = by_name.get(featured.site)
            if existing is None:
                by_name[featured.site] = featured
            else:
                existing_cmds = {c.name for c in existing.commands}
                merged_cmds = list(existing.commands)
                for cmd in featured.commands:
                    if cmd.name not in existing_cmds:
                        merged_cmds.append(cmd)
                by_name[featured.site] = SiteInfo(
                    site=existing.site,
                    commands=merged_cmds,
                    featured=True,
                )
        result = sorted(by_name.values(), key=lambda s: (not s.featured, s.site))
        return result

    async def _run(
        self,
        argv: list[str],
        *,
        audit_action: str,
        timeout: float,
        session_key: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> RunResult:
        started = time.perf_counter()
        code, out, err = await _exec(argv, timeout=timeout)
        duration_ms = int((time.perf_counter() - started) * 1000)
        success = code == 0
        audit_details = dict(details or {})
        audit_details.update({"exit_code": code, "duration_ms": duration_ms})
        if not success and err:
            audit_details["stderr_head"] = err[:400]
        self._audit.record(
            audit_action,
            "success" if success else "failure",
            session_key=session_key,
            actor="opencli",
            details=audit_details,
        )
        return RunResult(
            success=success,
            stdout=out,
            stderr=err,
            exit_code=code,
            duration_ms=duration_ms,
            command=argv,
        )


def _flatten_args(args: dict[str, Any]) -> list[str]:
    """Turn ``{key: value}`` into ``--key value`` argv tokens.

    Booleans become bare flags. Lists become ``--key v1 --key v2``. None
    values are skipped. Keys already starting with ``-`` are passed
    through unchanged.
    """
    out: list[str] = []
    for raw_key, value in args.items():
        if value is None:
            continue
        key = raw_key if raw_key.startswith("-") else f"--{raw_key.replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                out.append(key)
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                out.append(key)
                out.append(str(item))
            continue
        out.append(key)
        out.append(str(value))
    return out


def _safe_args(args: dict[str, Any] | None) -> dict[str, Any]:
    if not args:
        return {}
    safe: dict[str, Any] = {}
    for k, v in args.items():
        if _SENSITIVE_SELECTOR_RE.search(str(k)):
            safe[k] = "<redacted>"
            continue
        if isinstance(v, str) and len(v) > 200:
            safe[k] = v[:200] + "…"
        else:
            safe[k] = v
    sel = safe.get("selector")
    if isinstance(sel, str) and _SENSITIVE_SELECTOR_RE.search(sel):
        if "value" in safe:
            safe["value"] = "<redacted>"
    return safe


def _parse_sites_json(text: str) -> list[SiteInfo]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    sites: list[SiteInfo] = []
    if isinstance(data, dict):
        iterable = data.get("sites") or data.get("commands") or data
    else:
        iterable = data
    if isinstance(iterable, dict):
        for site, cmds in iterable.items():
            commands = _coerce_commands(cmds)
            sites.append(SiteInfo(site=str(site), commands=commands))
    elif isinstance(iterable, list):
        for entry in iterable:
            if not isinstance(entry, dict):
                continue
            site = entry.get("site") or entry.get("name")
            if not site:
                continue
            cmds = entry.get("commands") or entry.get("cmds") or []
            sites.append(SiteInfo(site=str(site), commands=_coerce_commands(cmds)))
    return sites


def _coerce_commands(raw: Any) -> list[SiteCommand]:
    if isinstance(raw, list):
        out: list[SiteCommand] = []
        for item in raw:
            if isinstance(item, str):
                out.append(SiteCommand(item))
            elif isinstance(item, dict):
                name = item.get("name") or item.get("command")
                if name:
                    out.append(SiteCommand(str(name), item.get("description")))
        return out
    return []


_SITE_HEADER_RE = re.compile(r"^  ([A-Za-z][\w.-]*)\s*$")
_COMMAND_LINE_RE = re.compile(
    r"^    (\S+)(?:\s+\[[^\]]+\])?(?:\s+[—\-:]+\s+(.*))?\s*$"
)


def _parse_sites_text(text: str) -> list[SiteInfo]:
    """Parse the human-readable ``opencli list`` output.

    The CLI prints sites as ``"  site"`` (2-space indent) followed by
    commands ``"    cmd [auth] — description"`` (4-space indent). We
    ignore the auth tag and capture the description when present.
    """
    by_site: dict[str, list[SiteCommand]] = {}
    current: str | None = None
    for line in (text or "").splitlines():
        if not line.strip():
            current = None
            continue
        site_match = _SITE_HEADER_RE.match(line)
        if site_match:
            current = site_match.group(1)
            by_site.setdefault(current, [])
            continue
        if current is None:
            continue
        cmd_match = _COMMAND_LINE_RE.match(line)
        if not cmd_match:
            continue
        cmd_name = cmd_match.group(1)
        description = (cmd_match.group(2) or "").strip() or None
        by_site[current].append(SiteCommand(cmd_name, description))
    return [SiteInfo(site=s, commands=cmds) for s, cmds in by_site.items() if cmds]


_SPECIAL_KEY_MAP: dict[str, tuple[str, str, int]] = {
    # name → (key, code, keyCode)
    "Enter": ("Enter", "Enter", 13),
    "Escape": ("Escape", "Escape", 27),
    "Esc": ("Escape", "Escape", 27),
    "Tab": ("Tab", "Tab", 9),
    "Backspace": ("Backspace", "Backspace", 8),
    "Delete": ("Delete", "Delete", 46),
    "ArrowUp": ("ArrowUp", "ArrowUp", 38),
    "ArrowDown": ("ArrowDown", "ArrowDown", 40),
    "ArrowLeft": ("ArrowLeft", "ArrowLeft", 37),
    "ArrowRight": ("ArrowRight", "ArrowRight", 39),
    "Space": (" ", "Space", 32),
    "Home": ("Home", "Home", 36),
    "End": ("End", "End", 35),
    "PageUp": ("PageUp", "PageUp", 33),
    "PageDown": ("PageDown", "PageDown", 34),
}

_MODIFIER_MAP: dict[str, str] = {
    "ctrl": "ctrlKey",
    "control": "ctrlKey",
    "shift": "shiftKey",
    "alt": "altKey",
    "option": "altKey",
    "meta": "metaKey",
    "cmd": "metaKey",
    "command": "metaKey",
}


def _build_synthetic_key_script(key_spec: str) -> str:
    """Build a JS expression that dispatches a synthetic key event sequence.

    Handles single keys (``"Enter"``) and combos (``"Control+a"``,
    ``"Shift+Tab"``). The script dispatches keydown → keypress → keyup
    on the focused element with proper ``key`` / ``code`` / ``keyCode``
    / modifier flags so React's synthetic event system fires its
    handlers.
    """
    parts = [p.strip() for p in key_spec.split("+") if p.strip()]
    modifiers = parts[:-1] if len(parts) > 1 else []
    main_key = parts[-1] if parts else key_spec

    init: dict[str, Any] = {"bubbles": True, "cancelable": True}
    for mod in modifiers:
        prop = _MODIFIER_MAP.get(mod.lower())
        if prop:
            init[prop] = True

    if main_key in _SPECIAL_KEY_MAP:
        k, code, key_code = _SPECIAL_KEY_MAP[main_key]
    elif len(main_key) == 1:
        upper = main_key.upper()
        k = main_key
        if upper.isalpha():
            code = f"Key{upper}"
        elif upper.isdigit():
            code = f"Digit{upper}"
        else:
            code = main_key
        key_code = ord(upper)
    else:
        k = main_key
        code = main_key
        key_code = 0

    init["key"] = k
    init["code"] = code
    init["keyCode"] = key_code
    init["which"] = key_code

    init_json = json.dumps(init)
    safe_label = key_spec.replace("'", "\\'")
    return (
        "(()=>{"
        "const el=document.activeElement||document.body;"
        f"['keydown','keypress','keyup'].forEach(t=>el.dispatchEvent(new KeyboardEvent(t,{init_json})));"
        f"return 'dispatched: {safe_label}';"
        "})()"
    )


async def _exec(argv: list[str], *, timeout: float) -> tuple[int, str, str]:
    """Run an OpenCLI subprocess.

    Window mode is set per-call (foreground for browser primitives that
    the user expects to see, background for site adapters that run in
    OpenCLI's own Chromium and shouldn't flash a window at the user).

    ``resolve_for_exec`` wraps Windows ``.cmd`` shims with ``cmd.exe /c``
    so npm-installed CLIs (``opencli.cmd``) can be launched via
    ``create_subprocess_exec``, which otherwise refuses non-PE binaries.
    """
    argv = resolve_for_exec(argv)
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return 127, "", f"{argv[0]}: not found"
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "", f"{argv[0]}: timed out after {timeout}s"
    return (
        proc.returncode or 0,
        out.decode("utf-8", "replace"),
        err.decode("utf-8", "replace"),
    )
