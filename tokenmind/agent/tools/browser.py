"""Browser automation via OpenCLI."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tokenmind.agent.tools.base import Tool
from tokenmind.integrations.opencli import (
    FEATURED_SITES,
    OpenCLIService,
    SiteEntry,
    SiteInfo,
    SiteRegistry,
)

_TOOL_RESULT_MAX_CHARS = 12_000


_PRIMITIVE_ACTIONS = [
    "analyze",
    "back",
    "bind",
    "check",
    "click",
    "close",
    "console",
    "dblclick",
    "dialog",
    "drag",
    "eval",
    "extract",
    "fill",
    "find",
    "focus",
    "frames",
    "get",
    "handoff",
    "hover",
    "init",
    "keys",
    "network",
    "open",
    "screenshot",
    "scroll",
    "select",
    "state",
    "tab",
    "type",
    "unbind",
    "uncheck",
    "upload",
    "verify",
    "wait",
]


_LOGIN_URL_PATTERNS = re.compile(
    r"(?:^|/)(login|signin|sign-in|sign_in|signup|register|auth(?:enticate)?|verify|verification|captcha|2fa|otp|mfa)"
    r"(?:[/?#]|$)",
    re.IGNORECASE,
)
_LOGIN_KEYWORDS = (
    "请登录",
    "请先登录",
    "登录后",
    "扫码登录",
    "手机号登录",
    "密码登录",
    "验证码",
    "滑动验证",
    "拖动滑块",
    "完成验证",
    "二步验证",
    "log in to continue",
    "sign in to continue",
    "please log in",
    "please sign in",
    "verify you are human",
    "i'm not a robot",
    "captcha",
)
_HANDOFF_HINT = (
    "\n\n[TokenMind hint] This page looks like a login or verification gate "
    "(matched URL pattern or page keyword). Do NOT attempt to type "
    "credentials, click through, or guess values. If proceeding requires "
    "the user to be signed in or to pass a captcha, call "
    "browser(mode='primitive', action='handoff', reason=..., instructions=...) "
    "so the user can take over in Chrome and click 'I'm done' when ready."
)


def _featured_description() -> str:
    lines = []
    for site in FEATURED_SITES:
        cmds = ", ".join(c.name for c in site.commands)
        lines.append(f"    {site.site}: {cmds}")
    return "\n".join(lines)


class BrowserTool(Tool):
    """Drive the user's logged-in Chrome via OpenCLI.

    Three modes — see ``description`` for what the LLM sees.
    """

    def __init__(
        self,
        service: OpenCLIService,
        *,
        get_session_key: Callable[[], str | None] | None = None,
        request_handoff: Callable[..., Any] | None = None,
        site_registry: SiteRegistry | None = None,
    ) -> None:
        self._service = service
        self._get_session_key = get_session_key or (lambda: None)
        # ``request_handoff`` is an async callable injected by the agent
        # loop. Signature: ``async (reason: str, instructions: str,
        # session_key: str | None) -> bool``. Returns True iff the user
        # clicked "I'm done". The loop owns the WS publish + pending
        # future machinery; the tool stays UI-agnostic.
        self._request_handoff = request_handoff
        self._site_registry = site_registry
        # Availability cache: get_definitions() is hot (once per LLM call), so
        # avoid scanning PATH on every probe. Short TTL so a fresh one-click
        # install flips the tool on within seconds without a restart.
        self._avail: bool | None = None
        self._avail_at: float = 0.0

    _AVAIL_TTL_S = 8.0

    def is_available(self) -> bool:
        """Only expose the browser tool when OpenCLI is actually installed.

        Without OpenCLI the tool can do nothing, so hiding it keeps its ~1.3k
        token schema out of the prompt entirely for users who haven't set it
        up. Uses ``shutil.which`` (same signal the detector uses) behind a
        short TTL cache. After the one-click installer drops ``opencli`` on
        PATH, the next probe past the TTL re-enables the tool automatically.
        """
        now = time.time()
        if self._avail is None or now - self._avail_at >= self._AVAIL_TTL_S:
            self._avail = shutil.which("opencli") is not None
            self._avail_at = now
        return self._avail

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        # Kept deliberately lean: this ships on every API call. Situational
        # quirks (wait seconds-vs-ms, SPA deep-link redirects, selector
        # escaping, synthetic Enter, login gates) are auto-handled or injected
        # as [hint] lines into the tool RESULT at runtime — exactly when
        # relevant — so they don't need to live in this always-on text.
        return (
            "Browse the web through the user's real Chrome (OpenCLI). Two "
            "engines via `mode`:\n\n"
            "── mode=primitive (DEFAULT for anything conversational) ──\n"
            "Drives the Chrome window the user is watching, via the OpenCLI "
            "extension. Same chat = same tab. Open more pages in the same "
            "window with action=tab, positional=[\"new\", \"https://...\"]. Use "
            "for: open/go to a site, search on a site, click/type/fill, "
            "scroll, screenshot, extract — anything the user expects to SEE.\n"
            "  Pass args as top-level fields (forwarded to the action):\n"
            "    url        → open / analyze\n"
            "    selector   → click / type / fill / hover / focus / find / extract\n"
            "    value      → type / fill / select / keys / eval / wait (2nd arg)\n"
            "    type       → wait (selector|text|time|xhr|download)\n"
            "    direction  → scroll (up|down|left|right)\n"
            "    positional → multi-arg sub-commands (tab new <url>, get text <css>, drag <src> <tgt>)\n"
            "  Leave `session` empty (auto-binds to the chat). screenshot "
            "auto-saves to a temp PNG and returns the path — pass it to "
            "deliver_attachment to show the user.\n"
            "  To search a site, do it IN the visible browser: open / tab-new "
            "the site's search URL (e.g. "
            "xiaohongshu.com/search_result?keyword=AI), or click the search "
            "box + type + click submit; then confirm with get url. TokenMind "
            "auto-corrects common pitfalls at runtime (wait seconds-vs-ms, SPA "
            "deep-link redirects, synthetic Enter) and appends [hint] lines to "
            "the result — follow them.\n"
            "  LOGIN: TokenMind tracks per-site login state. Opening a site "
            "marked not-logged-in auto-pauses and asks the user to sign in — "
            "you do NOT handle routine logins or ever guess credentials. For "
            "mid-flow gates only the user can clear (captcha, 2FA, OTP), call "
            "action=handoff with a short reason + instructions; it pauses and "
            "resumes when the user clicks done, then call state to re-read.\n\n"
            "── mode=site ── Runs an adapter in a BACKGROUND tab of the SAME "
            "Chrome (shares the user's login/cookies) and returns structured "
            "data (JSON/table); the user does not watch it work. Use only for "
            "batch / scheduled / 'just give me the data' requests. Required: "
            "site, command. Optional: positional (query/id, e.g. [\"AI\"]), "
            "args ({limit: 5}). Call mode=list_sites for the directory.\n\n"
            "── mode=list_sites ── return the supported site/command directory.\n\n"
            "RULE: conversational web work (打开/搜索/点击/查看/导航/截图) → "
            "mode=primitive. Use mode=site only when the user opted out of "
            "seeing the browser.\n"
            "Safety: post/like/follow/comment, typing into sensitive fields, "
            "and eval(JS) may pause for user approval."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["site", "primitive", "list_sites"],
                    "description": "Which OpenCLI surface to invoke.",
                },
                "site": {
                    "type": "string",
                    "description": "Site adapter name (mode=site). e.g. 'bilibili'.",
                },
                "command": {
                    "type": "string",
                    "description": "Site adapter command (mode=site). e.g. 'hot'.",
                },
                "args": {
                    "type": "object",
                    "description": "Flag-style options for site mode, e.g. {\"limit\": 5}. Do NOT put positional arguments (search query / id) here — those go in `positional`.",
                },
                "positional": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Explicit positional args. mode=site: query/id (e.g. [\"AI\"]). mode=primitive: multi-arg sub-commands — tab [\"new\",url], get [\"text\",css], drag [src,tgt]. Overrides per-action inference.",
                },
                "action": {
                    "type": "string",
                    "enum": _PRIMITIVE_ACTIONS,
                    "description": "Browser primitive action (mode=primitive).",
                },
                "session": {
                    "type": "string",
                    "description": "Browser session name. Defaults to the chat session.",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector or visible text (mode=primitive).",
                },
                "value": {
                    "type": "string",
                    "description": "Value for type/fill/select/eval/keys (mode=primitive).",
                },
                "url": {
                    "type": "string",
                    "description": "URL for action=open (mode=primitive).",
                },
                "options": {
                    "type": "object",
                    "description": "Additional CLI flags forwarded to the primitive.",
                },
                "profile": {
                    "type": "string",
                    "description": "Chrome profile alias when multiple profiles are connected.",
                },
                "timeout_s": {
                    "type": "integer",
                    "description": "Optional override of the subprocess timeout (seconds).",
                    "minimum": 1,
                    "maximum": 600,
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for handoff (mode=primitive, action=handoff). Short Chinese, what gate blocks you.",
                },
                "instructions": {
                    "type": "string",
                    "description": "User-facing instructions for handoff (Chinese, plain). E.g. '请在浏览器里完成小红书登录'.",
                },
            },
            "required": ["mode"],
        }

    async def execute(self, mode: str, **kwargs: Any) -> str:
        session_key = self._get_session_key()
        if mode == "list_sites":
            sites = await self._service.list_sites()
            return _format_sites(sites)

        install = await self._service.detect()

        if mode == "site":
            if not install.opencli_installed or not install.node_ok:
                return _format_not_ready(install)
            site = (kwargs.get("site") or "").strip()
            command = (kwargs.get("command") or "").strip()
            if not site or not command:
                return "Error: mode=site requires both 'site' and 'command'."
            args = kwargs.get("args") or {}
            if not isinstance(args, dict):
                return "Error: 'args' must be an object."
            raw_pos = kwargs.get("positional")
            if raw_pos is None:
                positional: list[str] | None = None
            elif isinstance(raw_pos, list):
                positional = [str(p) for p in raw_pos]
            elif isinstance(raw_pos, str):
                positional = [raw_pos]
            else:
                return "Error: 'positional' must be a list of strings or a single string."
            result = await self._service.run_site_command(
                site,
                command,
                args,
                positional=positional,
                profile=kwargs.get("profile"),
                timeout=kwargs.get("timeout_s"),
                session_key=session_key,
            )
            return _format_run_result(result, header=f"opencli {site} {command}")

        if mode == "primitive":
            if not install.ready:
                return _format_not_ready(install)
            action = (kwargs.get("action") or "").strip()
            if not action:
                return "Error: mode=primitive requires 'action'."

            # ``handoff`` is TokenMind-synthetic — it does not invoke
            # opencli. We pause the agent loop and surface a modal to the
            # user via the injected ``request_handoff`` callback. When
            # the user clicks "I'm done", the future resolves and we
            # return a tool result the model can act on.
            if action == "handoff":
                if self._request_handoff is None:
                    return (
                        "Error: handoff is not available outside an interactive "
                        "chat (no request_handoff handler wired)."
                    )
                reason = (kwargs.get("reason") or "").strip() or "User input needed"
                instructions = (kwargs.get("instructions") or "").strip() or (
                    "请在浏览器里完成操作，完成后点击下方按钮"
                )
                completed = await self._request_handoff(
                    reason=reason,
                    instructions=instructions,
                    session_key=session_key,
                )
                if completed:
                    return (
                        f"User has completed the handoff for: {reason}. "
                        "Now call browser(action='state') or browser(action='get', positional=['url']) "
                        "to verify the new page state, then continue with the original task."
                    )
                return (
                    f"User cancelled or timed out on the handoff for: {reason}. "
                    "Do not retry the gated action; ask the user what they'd "
                    "like to do instead."
                )

            session = (kwargs.get("session") or "").strip() or self._derive_session_name(
                session_key
            )
            options = self._primitive_options(kwargs)

            raw_pos = kwargs.get("positional")
            if raw_pos is None:
                positional_override: list[str] | None = None
            elif isinstance(raw_pos, list):
                positional_override = [str(p) for p in raw_pos]
            elif isinstance(raw_pos, str):
                positional_override = [raw_pos]
            else:
                return "Error: 'positional' must be a list of strings or a single string."

            screenshot_path: Path | None = None
            if (
                action == "screenshot"
                and positional_override is None
                and "path" not in options
            ):
                screenshot_path = _new_screenshot_path()
                options["path"] = str(screenshot_path)

            # ``wait time <N>`` takes SECONDS. LLMs trained on JS often
            # pass ms (2000 == 2 seconds-of-thinking-but-actually-2000-s).
            # If the user clearly meant ms, convert and annotate.
            wait_unit_note: str | None = None
            if action == "wait" and positional_override is None:
                if str(options.get("type", "")).lower() == "time":
                    raw = options.get("value")
                    try:
                        num = int(str(raw))
                        if num > 60:
                            converted = max(1, num // 1000)
                            options["value"] = str(converted)
                            wait_unit_note = (
                                f"[hint] wait time takes SECONDS, not milliseconds. "
                                f"You passed {num}; treated as {converted}s."
                            )
                    except (ValueError, TypeError):
                        pass

            # Resolve the URL this primitive is about to navigate to (if any),
            # so we can consult the site registry before we drive the browser.
            target_url = self._resolve_target_url(action, options, positional_override)
            login_entry: SiteEntry | None = None
            if target_url and self._site_registry is not None:
                login_entry = self._site_registry.find_by_url(target_url)

            result = await self._service.run_browser_primitive(
                session,
                action,
                options,
                positional=positional_override,
                profile=kwargs.get("profile"),
                timeout=kwargs.get("timeout_s"),
                session_key=session_key,
            )

            # Registry-driven login handoff: if the destination is a known
            # site marked "not logged in", pause the loop after the
            # navigation (the user already sees the page in Chrome) and
            # ask them to log in. We do this AFTER the open succeeds so
            # the Chrome window is already on the right URL for the user.
            handoff_note: str | None = None
            if (
                result.success
                and login_entry is not None
                and not login_entry.logged_in
                and self._request_handoff is not None
            ):
                completed = await self._request_handoff(
                    reason=f"登录 {login_entry.name}",
                    instructions=(
                        f"请在浏览器里完成 {login_entry.name} 的登录，"
                        "完成后回到 TokenMind 点「我已完成」。"
                        f"你也可以在浏览器侧边栏把 {login_entry.name} 标记为已登录，"
                        "之后 TokenMind 就不会再问你了。"
                    ),
                    session_key=session_key,
                )
                if completed:
                    handoff_note = (
                        f"[handoff] User completed login for {login_entry.name}. "
                        "Continue with the original task; call ``state`` if you "
                        "need to re-read the page."
                    )
                else:
                    handoff_note = (
                        f"[handoff] User cancelled/timed out the login for "
                        f"{login_entry.name}. Do not proceed with anything that "
                        "requires being signed in; ask the user what to do."
                    )

            # After ``tab new``, OpenCLI keeps the session's default tab
            # pointing at the OLD tab. The user sees the new tab in Chrome
            # but it's not focused, and any follow-up primitive command
            # (click/type/state/...) would still hit the old one. Auto
            # ``tab select`` here so both Chrome's foreground AND the
            # session binding move to the freshly created tab — that is
            # the UX users expect ("you opened a new tab, show me it").
            if (
                action == "tab"
                and positional_override
                and positional_override[0] == "new"
                and result.success
            ):
                new_id = _extract_page_id(result.stdout)
                if new_id:
                    select_result = await self._service.run_browser_primitive(
                        session,
                        "tab",
                        {},
                        positional=["select", new_id],
                        profile=kwargs.get("profile"),
                        timeout=kwargs.get("timeout_s"),
                        session_key=session_key,
                    )
                    if not select_result.success:
                        return _format_run_result(
                            result,
                            header=f"opencli browser {session} tab new",
                        ) + (
                            f"\n[warn] tab created (id={new_id}) but auto-select "
                            f"failed: {(select_result.stderr or '')[:200]}"
                        )

            if action == "screenshot" and result.success and screenshot_path is not None:
                if screenshot_path.is_file():
                    return (
                        f"Screenshot saved to {screenshot_path}. "
                        "Pass this path to deliver_attachment to show the user."
                    )
                return (
                    "Screenshot command succeeded but the output file was not "
                    f"found at {screenshot_path}. Stdout head: "
                    f"{(result.stdout or '')[:200]}"
                )

            formatted = _format_run_result(
                result,
                header=f"opencli browser {session} {action}",
            )
            if wait_unit_note:
                formatted += "\n\n" + wait_unit_note
            if handoff_note:
                formatted += "\n\n" + handoff_note
            if result.success and _looks_like_login_gate(result.stdout):
                formatted += _HANDOFF_HINT
            if action == "open" and result.success:
                requested = (kwargs.get("url") or "").strip()
                if requested:
                    redirect_hint = await self._check_open_redirect(
                        session, requested, kwargs, session_key
                    )
                    if redirect_hint:
                        formatted += "\n\n" + redirect_hint
            return formatted

        return f"Error: unknown mode '{mode}'. Use site / primitive / list_sites."

    _FRAMEWORK_KEYS = frozenset(
        {
            "mode",
            "action",
            "session",
            "options",
            "profile",
            "timeout_s",
            "args",
            "positional",
            "site",
            "command",
        }
    )

    def _primitive_options(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Forward LLM-supplied top-level fields into the opencli options dict.

        The LLM addresses primitive args with stable top-level names
        (``selector`` / ``value`` / ``url`` / ``type`` / ``direction`` /
        ``path`` / ``name`` / ``css`` / …). We pass them all through
        rather than enumerating a fixed allowlist — anything passed
        explicitly via ``options`` still wins.
        """
        options = dict(kwargs.get("options") or {})
        for key, value in kwargs.items():
            if key in self._FRAMEWORK_KEYS:
                continue
            if value is None or value == "":
                continue
            if key in options:
                continue
            options[key] = value

        action = (kwargs.get("action") or "").strip()
        # ``find`` uses ``--css`` for its CSS selector, not ``--selector``.
        # Other actions (click/type/extract/...) use ``--selector``, so we
        # only rename when the action is specifically ``find``.
        if action == "find" and "selector" in options and "css" not in options:
            options["css"] = options.pop("selector")
        return options

    @staticmethod
    def _resolve_target_url(
        action: str,
        options: dict[str, Any],
        positional_override: list[str] | None,
    ) -> str | None:
        """Figure out which URL a primitive is about to navigate to, if any.

        Used for the registry-driven login check — we only want to consult
        the site registry for actions that actually load a new origin
        (``open``, ``tab new``, ``analyze``). For everything else (click,
        type, screenshot, wait, etc.) the page is already loaded and the
        registry has nothing to add.
        """
        if action == "open":
            if positional_override:
                return positional_override[0]
            return str(options.get("url") or "").strip() or None
        if action == "tab" and positional_override:
            if len(positional_override) >= 2 and positional_override[0] == "new":
                return positional_override[1]
            return None
        if action == "analyze":
            if positional_override:
                return positional_override[0]
            return str(options.get("url") or "").strip() or None
        return None

    async def _check_open_redirect(
        self,
        session: str,
        requested_url: str,
        kwargs: dict[str, Any],
        session_key: str | None,
    ) -> str | None:
        """Detect SPA-side redirects after ``open <url>``.

        OpenCLI's ``open`` returns the requested URL verbatim — it doesn't
        observe the post-navigation state. Sites like xiaohongshu silently
        bounce direct-post URLs back to ``/explore`` (anti-deep-link
        behaviour for non-feed traffic). We run a cheap ``get url`` here
        and tell the model when it landed somewhere else so it stops
        operating on a wrong page assumption.
        """
        try:
            check = await self._service.run_browser_primitive(
                session,
                "get",
                {},
                positional=["url"],
                profile=kwargs.get("profile"),
                session_key=session_key,
                timeout=10.0,
            )
        except Exception:  # noqa: BLE001
            return None
        if not check.success:
            return None
        actual = (check.stdout or "").strip().splitlines()[-1].strip() if check.stdout else ""
        if not actual:
            return None
        if _same_path(requested_url, actual):
            return None
        return (
            f"[hint] You requested {requested_url} but the browser landed on "
            f"{actual}. The site likely blocks direct deep-links and requires "
            "navigation from a feed/list page. Try clicking the post card "
            "from the listing instead — e.g. "
            "``browser(action='eval', value=\"document.querySelector('a[href^=\\\"/explore/POST_ID\\\"]').click()\")`` "
            "— rather than ``open`` with the bare post URL. Re-verify with "
            "``state`` after the click."
        )

    @staticmethod
    def _derive_session_name(session_key: str | None) -> str:
        if not session_key:
            return "tokenmind"
        slug = re.sub(r"[^A-Za-z0-9_-]+", "-", session_key).strip("-")
        return slug or "tokenmind"

    @staticmethod
    def get_high_risk_reason(args: dict[str, Any]) -> str | None:
        """Return a short human reason if the call needs user approval.

        Mirrors ``ExecTool.get_high_risk_reason`` so the loop can route
        browser tool calls through the same approval modal.
        """
        if not isinstance(args, dict):
            return None
        from tokenmind.integrations.opencli.service import (  # local import to avoid cycles
            _SENSITIVE_SELECTOR_RE,
            _WRITE_COMMAND_KEYWORDS,
        )

        mode = (args.get("mode") or "").strip()
        if mode == "site":
            command = (args.get("command") or "").lower()
            for keyword in _WRITE_COMMAND_KEYWORDS:
                if keyword and keyword in command:
                    return (
                        f"Site action '{command}' writes to the remote service "
                        "(posts/likes/follows/etc.)."
                    )
            return None

        if mode == "primitive":
            action = (args.get("action") or "").lower()
            if action == "eval":
                return "Evaluating arbitrary JavaScript on the page."
            if action == "network":
                return "Intercepting network requests on the page."
            if action == "type":
                selector = str((args.get("options") or {}).get("selector") or args.get("selector") or "")
                if _SENSITIVE_SELECTOR_RE.search(selector):
                    return "Typing into what looks like a sensitive field (password/secret/token)."
            return None

        return None

    @staticmethod
    def format_display(args: dict[str, Any]) -> str:
        """One-line preview shown in the approval modal."""
        if not isinstance(args, dict):
            return "browser"
        mode = args.get("mode")
        if mode == "site":
            extras = args.get("args") or {}
            extras_str = ""
            if isinstance(extras, dict) and extras:
                pairs = " ".join(f"--{k}={v}" for k, v in list(extras.items())[:4])
                extras_str = f" {pairs}"
            return f"opencli {args.get('site')} {args.get('command')}{extras_str}".strip()
        if mode == "primitive":
            action = args.get("action")
            selector = args.get("selector") or (args.get("options") or {}).get("selector")
            tail = f" {selector!r}" if selector else ""
            return f"opencli browser <session> {action}{tail}".strip()
        return f"browser mode={mode}"


def _format_sites(sites: list[SiteInfo]) -> str:
    if not sites:
        return "No sites discovered. Try installing OpenCLI: npm install -g @jackwener/opencli"
    lines = ["Available OpenCLI sites:"]
    for s in sites:
        commands = ", ".join(c.name for c in s.commands) if s.commands else "(no commands)"
        star = "★ " if s.featured else ""
        lines.append(f"  {star}{s.site}: {commands}")
    return "\n".join(lines)


def _format_not_ready(install: Any) -> str:
    lines = ["Error: OpenCLI is not ready. Missing:"]
    for step in install.missing_steps:
        bits = [f"- {step.title}"]
        if step.detail:
            bits.append(f"  {step.detail}")
        if step.command:
            bits.append(f"  $ {step.command}")
        if step.url:
            bits.append(f"  {step.url}")
        lines.append("\n".join(bits))
    return "\n".join(lines)


def _format_run_result(result: Any, *, header: str) -> str:
    parts: list[str] = []
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.success:
        if not stdout:
            parts.append(f"{header} succeeded (no output, {result.duration_ms} ms)")
        else:
            parts.append(_compact_output(stdout))
    else:
        parts.append(
            f"Error: {header} failed with exit code {result.exit_code} "
            f"({result.duration_ms} ms)."
        )
        if stderr:
            parts.append(stderr[:2000])
        elif stdout:
            parts.append(stdout[:2000])
    text = "\n".join(parts)
    if len(text) > _TOOL_RESULT_MAX_CHARS:
        text = text[:_TOOL_RESULT_MAX_CHARS] + f"\n…[truncated, {len(text)} chars]"
    return text


def _same_path(a: str, b: str) -> bool:
    """Compare two URLs by host + path only (ignoring query, fragment).

    Used by the open-redirect detector — if the user requested
    ``/explore/POST_ID`` and the browser landed on ``/explore``, we
    consider that a redirect even though both URLs share the
    ``xiaohongshu.com`` host.
    """
    from urllib.parse import urlparse

    try:
        pa, pb = urlparse(a), urlparse(b)
    except Exception:  # noqa: BLE001
        return a == b
    return (pa.netloc, pa.path.rstrip("/")) == (pb.netloc, pb.path.rstrip("/"))


_PAGE_ID_RE = re.compile(r'"page"\s*:\s*"([^"]+)"')
_URL_LINE_RE = re.compile(r'"url"\s*:\s*"([^"]+)"|^URL:\s*(\S+)|^url:\s*(\S+)', re.MULTILINE)


def _looks_like_login_gate(stdout: str | None) -> bool:
    """Heuristic: does the primitive result indicate a login / verification page?

    Two signals combined — URL pattern (``/login`` / ``/signin`` / ``/verify``
    / ``/captcha`` / ``/2fa``) and DOM-content keywords (登录 / 验证码 / sign
    in / captcha). Either match flags the page so the model gets a hint
    to call ``handoff`` instead of guessing credentials.
    """
    if not stdout:
        return False
    for match in _URL_LINE_RE.finditer(stdout):
        url = next((g for g in match.groups() if g), "")
        if url and _LOGIN_URL_PATTERNS.search(url):
            return True
    lower = stdout.lower()
    for kw in _LOGIN_KEYWORDS:
        if kw in stdout or kw in lower:
            return True
    return False


def _extract_page_id(stdout: str | None) -> str | None:
    """Parse the new tab's page/target ID out of ``tab new``'s JSON output."""
    if not stdout:
        return None
    m = _PAGE_ID_RE.search(stdout)
    return m.group(1) if m else None


def _new_screenshot_path() -> Path:
    """Build a unique temp path for an auto-saved screenshot.

    Use a dedicated subdir so cleanup tooling (or the user) can identify and
    purge them; uuid keeps concurrent calls from colliding.
    """
    base = Path(tempfile.gettempdir()) / "tokenmind-browser-screenshots"
    base.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return base / f"screenshot-{stamp}-{uuid.uuid4().hex[:6]}.png"


def _compact_output(text: str) -> str:
    """Pretty-print JSON if the output is JSON, otherwise return as-is."""
    candidate = text.strip()
    if candidate.startswith("{") or candidate.startswith("["):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            return text
        return json.dumps(data, ensure_ascii=False, indent=2)
    return text
