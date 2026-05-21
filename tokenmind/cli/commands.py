"""CLI commands for TokenMind."""

import asyncio
import os
import select
import signal
import sys
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any

# Force UTF-8 encoding for Windows console
if sys.platform == "win32":
    if sys.stdout.encoding != "utf-8":
        os.environ["PYTHONIOENCODING"] = "utf-8"
        # Re-open stdout/stderr with UTF-8 encoding
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import typer
from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.formatted_text import ANSI, HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from tokenmind import __logo__, __version__
from tokenmind.config.paths import get_workspace_path
from tokenmind.config.schema import Config
from tokenmind.utils.helpers import sync_workspace_templates

app = typer.Typer(
    name="tokenmind",
    help=f"{__logo__} TokenMind - Personal AI Assistant",
    no_args_is_help=True,
)

console = Console()
EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}
DEFAULT_WEB_PORT = 18888


def _cron_execution_session_key(job: Any) -> str:
    """Return the session where a cron run should save its turn and timeline."""
    channel = (getattr(job.payload, "channel", None) or "").strip()
    target = (getattr(job.payload, "to", None) or "").strip()
    if (
        getattr(job.payload, "deliver", False)
        and target.startswith("web:")
        and channel in {"", "web"}
    ):
        return target
    return f"cron:{job.id}"


def _build_cron_prompt(job: Any) -> str:
    """Build the instruction passed to the agent for a scheduled run."""
    from tokenmind.cron.delivery import build_task_trigger_message

    return build_task_trigger_message(job.name, job.payload.message)


# ---------------------------------------------------------------------------
# CLI input: prompt_toolkit for editing, paste, history, and display
# ---------------------------------------------------------------------------

_PROMPT_SESSION: PromptSession | None = None
_SAVED_TERM_ATTRS = None  # original termios settings, restored on exit


def _flush_pending_tty_input() -> None:
    """Drop unread keypresses typed while the model was generating output."""
    try:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
    except Exception:
        return

    try:
        import termios
        termios.tcflush(fd, termios.TCIFLUSH)
        return
    except Exception:
        pass

    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            if not os.read(fd, 4096):
                break
    except Exception:
        return


def _restore_terminal() -> None:
    """Restore terminal to its original state (echo, line buffering, etc.)."""
    if _SAVED_TERM_ATTRS is None:
        return
    try:
        import termios
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _SAVED_TERM_ATTRS)
    except Exception:
        pass


def _init_prompt_session() -> None:
    """Create the prompt_toolkit session with persistent file history."""
    global _PROMPT_SESSION, _SAVED_TERM_ATTRS

    # Save terminal state so we can restore it on exit
    try:
        import termios
        _SAVED_TERM_ATTRS = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass

    from tokenmind.config.paths import get_cli_history_path

    history_file = get_cli_history_path()
    history_file.parent.mkdir(parents=True, exist_ok=True)

    _PROMPT_SESSION = PromptSession(
        history=FileHistory(str(history_file)),
        enable_open_in_editor=False,
        multiline=False,   # Enter submits (single line mode)
    )


def _make_console() -> Console:
    return Console(file=sys.stdout)


def _render_interactive_ansi(render_fn) -> str:
    """Render Rich output to ANSI so prompt_toolkit can print it safely."""
    ansi_console = Console(
        force_terminal=True,
        color_system=console.color_system or "standard",
        width=console.width,
    )
    with ansi_console.capture() as capture:
        render_fn(ansi_console)
    return capture.get()


def _print_agent_response(response: str, render_markdown: bool) -> None:
    """Render assistant response with consistent terminal styling."""
    console = _make_console()
    content = response or ""
    body = Markdown(content) if render_markdown else Text(content)
    console.print()
    console.print(f"[cyan]{__logo__} TokenMind[/cyan]")
    console.print(body)
    console.print()


async def _print_interactive_line(text: str) -> None:
    """Print async interactive updates with prompt_toolkit-safe Rich styling."""
    def _write() -> None:
        ansi = _render_interactive_ansi(
            lambda c: c.print(f"  [dim]↳ {text}[/dim]")
        )
        print_formatted_text(ANSI(ansi), end="")

    await run_in_terminal(_write)


async def _print_interactive_response(response: str, render_markdown: bool) -> None:
    """Print async interactive replies with prompt_toolkit-safe Rich styling."""
    def _write() -> None:
        content = response or ""
        ansi = _render_interactive_ansi(
            lambda c: (
                c.print(),
                c.print(f"[cyan]{__logo__} TokenMind[/cyan]"),
                c.print(Markdown(content) if render_markdown else Text(content)),
                c.print(),
            )
        )
        print_formatted_text(ANSI(ansi), end="")

    await run_in_terminal(_write)


class _ThinkingSpinner:
    """Spinner wrapper with pause support for clean progress output."""

    def __init__(self, enabled: bool):
        self._spinner = console.status(
            "[dim]TokenMind is thinking...[/dim]", spinner="dots"
        ) if enabled else None
        self._active = False

    def __enter__(self):
        if self._spinner:
            self._spinner.start()
        self._active = True
        return self

    def __exit__(self, *exc):
        self._active = False
        if self._spinner:
            self._spinner.stop()
        return False

    @contextmanager
    def pause(self):
        """Temporarily stop spinner while printing progress."""
        if self._spinner and self._active:
            self._spinner.stop()
        try:
            yield
        finally:
            if self._spinner and self._active:
                self._spinner.start()


def _print_cli_progress_line(text: str, thinking: _ThinkingSpinner | None) -> None:
    """Print a CLI progress line, pausing the spinner if needed."""
    with thinking.pause() if thinking else nullcontext():
        console.print(f"  [dim]↳ {text}[/dim]")


async def _print_interactive_progress_line(text: str, thinking: _ThinkingSpinner | None) -> None:
    """Print an interactive progress line, pausing the spinner if needed."""
    with thinking.pause() if thinking else nullcontext():
        await _print_interactive_line(text)


def _is_exit_command(command: str) -> bool:
    """Return True when input should end interactive chat."""
    return command.lower() in EXIT_COMMANDS


async def _read_interactive_input_async() -> str:
    """Read user input using prompt_toolkit (handles paste, history, display).

    prompt_toolkit natively handles:
    - Multiline paste (bracketed paste mode)
    - History navigation (up/down arrows)
    - Clean display (no ghost characters or artifacts)
    """
    if _PROMPT_SESSION is None:
        raise RuntimeError("Call _init_prompt_session() first")
    try:
        with patch_stdout():
            return await _PROMPT_SESSION.prompt_async(
                HTML("<b fg='ansiblue'>You:</b> "),
            )
    except EOFError as exc:
        raise KeyboardInterrupt from exc



def version_callback(value: bool):
    if value:
        console.print(f"{__logo__} TokenMind v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True
    ),
):
    """TokenMind - Personal AI Assistant."""
    pass


# ============================================================================
# Onboard / Setup
# ============================================================================


@app.command()
def onboard(
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    wizard: bool = typer.Option(False, "--wizard", help="Use interactive wizard"),
):
    """Initialize TokenMind configuration and workspace."""
    from tokenmind.config.loader import get_config_path, load_config, save_config, set_config_path
    from tokenmind.config.schema import Config

    explicit_config_path = config is not None
    if config:
        config_path = Path(config).expanduser().resolve()
        set_config_path(config_path)
        console.print(f"[dim]Using config: {config_path}[/dim]")
    else:
        config_path = get_config_path()

    def _apply_workspace_override(loaded: Config) -> Config:
        if workspace:
            loaded.agents.defaults.workspace = workspace
        return loaded

    # Create or update config
    if config_path.exists():
        if wizard:
            config = _apply_workspace_override(load_config(config_path))
        else:
            console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
            console.print("  [bold]y[/bold] = overwrite with defaults (existing values will be lost)")
            console.print("  [bold]N[/bold] = refresh config, keeping existing values and adding new fields")
            if typer.confirm("Overwrite?"):
                config = _apply_workspace_override(Config())
                save_config(config, config_path)
                console.print(f"[green]✓[/green] Config reset to defaults at {config_path}")
            else:
                config = _apply_workspace_override(load_config(config_path))
                save_config(config, config_path)
                console.print(f"[green]✓[/green] Config refreshed at {config_path} (existing values preserved)")
    else:
        config = _apply_workspace_override(Config())
        # In wizard mode, don't save yet - the wizard will handle saving if should_save=True
        if not wizard:
            save_config(config, config_path)
            console.print(f"[green]✓[/green] Created config at {config_path}")

    # Run interactive wizard if enabled
    if wizard:
        from tokenmind.cli.onboard_wizard import run_onboard

        try:
            result = run_onboard(initial_config=config)
            if not result.should_save:
                console.print("[yellow]Configuration discarded. No changes were saved.[/yellow]")
                return

            config = result.config
            save_config(config, config_path)
            console.print(f"[green]✓[/green] Config saved at {config_path}")
        except Exception as e:
            console.print(f"[red]✗[/red] Error during configuration: {e}")
            console.print("[yellow]Please run 'tokenmind onboard' again to complete setup.[/yellow]")
            raise typer.Exit(1)
    _onboard_plugins(config_path)

    # Create workspace, preferring the configured workspace path.
    workspace_path = get_workspace_path(config.workspace_path)
    if not workspace_path.exists():
        workspace_path.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]✓[/green] Created workspace at {workspace_path}")

    sync_workspace_templates(workspace_path)

    web_cmd = f"tokenmind web --port {DEFAULT_WEB_PORT}"
    if explicit_config_path:
        web_cmd += f" --config {config_path}"

    console.print(f"\n{__logo__} TokenMind is ready!")
    console.print("\nNext steps:")
    console.print(f"  1. Start Web UI: [cyan]{web_cmd}[/cyan]")
    console.print(f"  2. Open [cyan]http://localhost:{DEFAULT_WEB_PORT}[/cyan], add your API key in Settings, and enable the model you want to use.")
    if _source_checkout_needs_frontend_build():
        console.print("\n[yellow]Source checkout note:[/yellow]")
        console.print("  This repository does not have built Web UI assets yet.")
        console.print(f"  Before opening [cyan]http://localhost:{DEFAULT_WEB_PORT}[/cyan], run:")
        console.print("  [cyan]cd frontend && npm install && npm run build && cd ..[/cyan]")
        console.print("  For frontend development, keep the backend running and open [cyan]http://localhost:5173[/cyan] after [cyan]npm run dev[/cyan].")


def _source_checkout_needs_frontend_build() -> bool:
    """Return True when an editable/source checkout lacks built Web UI assets."""
    source_root = Path(__file__).resolve().parents[2]
    if not (source_root / "frontend" / "package.json").is_file():
        return False

    from tokenmind.server.frontend import resolve_frontend_dist_dir

    return resolve_frontend_dist_dir() is None


def _merge_missing_defaults(existing: Any, defaults: Any) -> Any:
    """Recursively fill in missing values from defaults without overwriting user config."""
    if not isinstance(existing, dict) or not isinstance(defaults, dict):
        return existing

    merged = dict(existing)
    for key, value in defaults.items():
        if key not in merged:
            merged[key] = value
        else:
            merged[key] = _merge_missing_defaults(merged[key], value)
    return merged


def _onboard_plugins(config_path: Path) -> None:
    """Inject default config for all discovered channels (built-in + plugins)."""
    import json

    from tokenmind.channels.registry import discover_all

    all_channels = discover_all()
    if not all_channels:
        return

    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)

    channels = data.setdefault("channels", {})
    for name, cls in all_channels.items():
        if name not in channels:
            channels[name] = cls.default_config()
        else:
            channels[name] = _merge_missing_defaults(channels[name], cls.default_config())

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _make_provider_for_web(config: Config):
    """Create provider for web command, allowing missing API key."""
    from tokenmind.providers.base import GenerationSettings
    from tokenmind.providers.openai_compat_provider import OpenAICompatProvider
    from tokenmind.providers.registry import find_by_name

    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)
    spec = find_by_name(provider_name) if provider_name else None
    has_key = p and p.api_key
    needs_key = (
        not model.startswith("bedrock/")
        and not has_key
        and not (spec and (spec.is_oauth or spec.is_local or spec.is_direct))
    )

    if needs_key:
        console.print("[yellow]Warning: No API key configured. "
                      "The Web UI will start, but chat will not work "
                      "until you add an API key in Settings.[/yellow]")
        provider = OpenAICompatProvider(
            api_key=None,
            api_base=None,
            default_model=model,
        )
    else:
        provider = _make_provider(config)
        return provider

    defaults = config.agents.defaults
    provider.generation = GenerationSettings(
        temperature=defaults.temperature,
        max_tokens=defaults.max_tokens,
        reasoning_effort=defaults.reasoning_effort,
    )
    return provider


async def _route_web_outbound_message(
    msg: Any,
    web_channel: Any,
    external_channels: Any,
    logger: Any,
) -> None:
    """Route web-runtime outbound messages to WebSocket or enabled chat channels."""
    if msg.channel == "web":
        await web_channel.send(msg)
        return

    channel = external_channels.get_channel(msg.channel) if external_channels else None
    if channel:
        await channel.send(msg)
        return

    logger.warning("Unknown channel in web runtime: {}", msg.channel)


def _make_provider(config: Config):
    """Create the appropriate LLM provider from config."""
    from tokenmind.providers.anthropic_provider import AnthropicProvider
    from tokenmind.providers.base import GenerationSettings
    from tokenmind.providers.registry import find_by_name

    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)
    spec = find_by_name(provider_name) if provider_name else None
    backend = spec.backend if spec else "openai_compat"

    if backend == "anthropic":
        if not p or not p.api_key:
            console.print("[red]Error: Anthropic requires api_key.[/red]")
            console.print("Set it in ~/.tokenmind/config.json under providers.anthropic section")
            raise typer.Exit(1)
        provider = AnthropicProvider(
            api_key=p.api_key,
            api_base=config.get_api_base(model),
            default_model=model,
            extra_headers=p.extra_headers if p else None,
        )
    else:
        from tokenmind.providers.openai_compat_provider import OpenAICompatProvider

        if (
            not model.startswith("bedrock/")
            and not (p and p.api_key)
            and not (spec and (spec.is_oauth or spec.is_local or spec.is_direct))
        ):
            console.print("[red]Error: No API key configured.[/red]")
            console.print("Set one in ~/.tokenmind/config.json under providers section")
            raise typer.Exit(1)
        provider = OpenAICompatProvider(
            api_key=p.api_key if p else None,
            api_base=config.get_api_base(model),
            default_model=model,
            extra_headers=p.extra_headers if p else None,
            spec=spec,
        )

    defaults = config.agents.defaults
    provider.generation = GenerationSettings(
        temperature=defaults.temperature,
        max_tokens=defaults.max_tokens,
        reasoning_effort=defaults.reasoning_effort,
    )
    return provider


def _load_runtime_config(config: str | None = None, workspace: str | None = None) -> Config:
    """Load config and optionally override the active workspace."""
    from tokenmind.config.loader import get_config_path, load_config, save_config, set_config_path

    config_path = None
    if config:
        config_path = Path(config).expanduser().resolve()
        if not config_path.exists():
            console.print(f"[red]Error: Config file not found: {config_path}[/red]")
            raise typer.Exit(1)
        set_config_path(config_path)
        console.print(f"[dim]Using config: {config_path}[/dim]")

    loaded = load_config(config_path)
    if config_path is None:
        default_config_path = get_config_path()
        if not default_config_path.exists():
            save_config(loaded, default_config_path)
    _warn_deprecated_config_keys(config_path)
    if workspace:
        loaded.agents.defaults.workspace = workspace
    return loaded


def _warn_deprecated_config_keys(config_path: Path | None) -> None:
    """Hint users to remove obsolete keys from their config file."""
    import json

    from tokenmind.config.loader import get_config_path

    path = config_path or get_config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if "memoryWindow" in raw.get("agents", {}).get("defaults", {}):
        console.print(
            "[dim]Hint: `memoryWindow` in your config is no longer used "
            "and can be safely removed.[/dim]"
        )



# ============================================================================
# Gateway / Server
# ============================================================================


@app.command()
def gateway(
    port: int | None = typer.Option(None, "--port", "-p", help="Gateway port"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Start the TokenMind gateway."""
    from tokenmind.agent.loop import AgentLoop
    from tokenmind.bus.queue import MessageBus
    from tokenmind.channels.manager import ChannelManager
    from tokenmind.config.loader import get_config_path
    from tokenmind.config.paths import get_cron_dir
    from tokenmind.cron.service import CronService
    from tokenmind.cron.types import CronJob
    from tokenmind.session.manager import SessionManager

    if verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    config = _load_runtime_config(config, workspace)
    port = port if port is not None else config.gateway.port

    console.print(f"{__logo__} Starting TokenMind gateway version {__version__} on port {port}...")
    sync_workspace_templates(config.workspace_path)
    bus = MessageBus()
    provider = _make_provider(config)
    session_manager = SessionManager(config.workspace_path)

    # Create cron service first (callback set after agent creation)
    cron_store_path = get_cron_dir() / "jobs.json"
    cron = CronService(cron_store_path)

    # Create agent with cron service
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        context_window_tokens=config.agents.defaults.context_window_tokens,
        web_search_config=config.tools.web.search,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        knowledge_config=config.tools.knowledge,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
        templates_config=config.templates,
        config_path=get_config_path(),
        creative_config=config.creative,
    )

    # Set cron callback (needs agent)
    async def on_cron_job(job: CronJob) -> str | None:
        """Execute a cron job through the agent."""
        from tokenmind.agent.tools.cron import CronTool
        from tokenmind.agent.tools.message import MessageTool
        from tokenmind.utils.evaluator import evaluate_response

        reminder_note = _build_cron_prompt(job)
        execution_session_key = _cron_execution_session_key(job)

        cron_tool = agent.tools.get("cron")
        cron_token = None
        if isinstance(cron_tool, CronTool):
            cron_token = cron_tool.set_cron_context(True)
        try:
            response = await agent.process_direct(
                reminder_note,
                session_key=execution_session_key,
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to or "direct",
            )
        finally:
            if isinstance(cron_tool, CronTool) and cron_token is not None:
                cron_tool.reset_cron_context(cron_token)

        message_tool = agent.tools.get("message")
        if isinstance(message_tool, MessageTool) and message_tool._sent_in_turn:
            return response

        if job.payload.deliver and job.payload.to and response:
            should_notify = await evaluate_response(
                response, job.payload.message, provider, agent.model,
            )
            if should_notify:
                from tokenmind.bus.events import OutboundMessage
                await bus.publish_outbound(OutboundMessage(
                    channel=job.payload.channel or "cli",
                    chat_id=job.payload.to,
                    content=response,
                ))
        return response
    cron.on_job = on_cron_job

    # Create channel manager
    channels = ChannelManager(config, bus)

    if channels.enabled_channels:
        console.print(f"[green]✓[/green] Channels enabled: {', '.join(channels.enabled_channels)}")
    else:
        console.print("[yellow]Warning: No channels enabled[/yellow]")

    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"[green]✓[/green] Cron: {cron_status['jobs']} scheduled jobs")

    async def run():
        try:
            await cron.start()
            await asyncio.gather(
                agent.run(),
                channels.start_all(),
            )
        except KeyboardInterrupt:
            console.print("\nShutting down...")
        except Exception:
            import traceback
            console.print("\n[red]Error: Gateway crashed unexpectedly[/red]")
            console.print(traceback.format_exc())
        finally:
            await agent.close_mcp()
            cron.stop()
            agent.stop()
            await channels.stop_all()

    asyncio.run(run())


@app.command()
def web(
    port: int = typer.Option(DEFAULT_WEB_PORT, "--port", "-p", help="Web server port"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Start the TokenMind Web UI server."""
    import uvicorn
    from loguru import logger

    from tokenmind.agent.loop import AgentLoop
    from tokenmind.bus.queue import MessageBus
    from tokenmind.channels.manager import ChannelManager
    from tokenmind.config.loader import get_config_path
    from tokenmind.config.paths import get_cron_dir
    from tokenmind.cron.service import CronService
    from tokenmind.cron.types import CronJob
    from tokenmind.server.app import create_app
    from tokenmind.server.channel.web import WebChannel, WebChannelConfig
    from tokenmind.server.dependencies import set_channel_manager
    from tokenmind.server.frontend import resolve_frontend_dist_dir
    from tokenmind.server.websocket.manager import ConnectionManager
    from tokenmind.session.manager import SessionManager

    config = _load_runtime_config(config, workspace)
    console.print(f"{__logo__} Starting TokenMind Web UI on port {port}...")
    sync_workspace_templates(config.workspace_path)

    bus = MessageBus()
    provider = _make_provider_for_web(config)
    session_manager = SessionManager(config.workspace_path)

    # Create cron service
    cron_store_path = get_cron_dir() / "jobs.json"
    cron = CronService(cron_store_path)

    # Create agent
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        context_window_tokens=config.agents.defaults.context_window_tokens,
        web_search_config=config.tools.web.search,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        knowledge_config=config.tools.knowledge,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
        templates_config=config.templates,
        config_path=get_config_path(),
        creative_config=config.creative,
    )

    # Set cron callback
    async def on_cron_job(job: CronJob) -> str | None:
        from tokenmind.agent.tools.cron import CronTool
        from tokenmind.agent.tools.message import MessageTool
        from tokenmind.cron.delivery import persist_task_result

        reminder_note = _build_cron_prompt(job)
        execution_session_key = _cron_execution_session_key(job)

        cron_tool = agent.tools.get("cron")
        cron_token = None
        if isinstance(cron_tool, CronTool):
            cron_token = cron_tool.set_cron_context(True)
        try:
            response = await agent.process_direct(
                reminder_note,
                session_key=execution_session_key,
                channel=job.payload.channel or "web",
                chat_id=job.payload.to or "web",
            )
        finally:
            if isinstance(cron_tool, CronTool) and cron_token is not None:
                cron_tool.reset_cron_context(cron_token)

        effective_channel = job.payload.channel or "web"
        message_tool = agent.tools.get("message")
        message_was_sent = isinstance(message_tool, MessageTool) and message_tool._sent_in_turn
        if message_was_sent and effective_channel != "web":
            return response

        if job.payload.deliver and job.payload.to and response:
            if execution_session_key != job.payload.to:
                persist_task_result(
                    session_manager=session_manager,
                    session_id=job.payload.to,
                    job_name=job.name,
                    instruction=job.payload.message,
                    response=response,
                )
            from tokenmind.bus.events import OutboundMessage
            await bus.publish_outbound(OutboundMessage(
                channel=effective_channel,
                chat_id=job.payload.to,
                content=response,
            ))
        return response

    cron.on_job = on_cron_job

    # Create WebChannel and ConnectionManager
    web_channel_config = WebChannelConfig(allow_from=["*"])
    web_channel = WebChannel(web_channel_config, bus)
    external_channels = ChannelManager(config, bus, strict_allow_from=False)
    set_channel_manager(external_channels)
    connection_manager = ConnectionManager()

    # Create FastAPI app
    app = create_app(
        bus=bus,
        agent_loop=agent,
        session_manager=session_manager,
        connection_manager=connection_manager,
        web_channel=web_channel,
    )
    frontend_dir = resolve_frontend_dist_dir()
    if frontend_dir is None:
        console.print("[yellow]Web UI assets were not found for this source checkout.[/yellow]")
        console.print(f"  Build once for {DEFAULT_WEB_PORT}: [cyan]cd frontend && npm install && npm run build && cd ..[/cyan]")
        console.print("  Or use dev mode: keep this backend running, run [cyan]cd frontend && npm install && npm run dev[/cyan], then open [cyan]http://localhost:5173[/cyan].")
    else:
        console.print(f"[green]✓[/green] Web UI ready: [cyan]http://localhost:{port}[/cyan]")

    # Outbound message dispatcher task
    outbound_dispatcher_task: asyncio.Task | None = None

    async def dispatch_outbound():
        """Forward outbound messages to WebSocket clients and enabled external channels."""
        while True:
            try:
                msg = await bus.consume_outbound()
                await _route_web_outbound_message(msg, web_channel, external_channels, logger)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error dispatching outbound message: {}", e)

    # Set cron callback on MessageTool
    async def on_progress(content: str, *, tool_hint: bool = False) -> None:
        pass  # Web UI handles progress via WebSocket

    async def run():
        nonlocal outbound_dispatcher_task
        agent_task: asyncio.Task | None = None
        try:
            await cron.start()
            await web_channel.start()
            for name in external_channels.channels:
                logger.info("Starting {} channel in web runtime...", name)
                external_channels.start_channel_background(name)
            # Start outbound dispatcher
            outbound_dispatcher_task = asyncio.create_task(dispatch_outbound())
            # Start agent loop in background
            agent_task = asyncio.create_task(agent.run())
            # Start FastAPI server
            config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
            server = uvicorn.Server(config)
            await server.serve()
        except KeyboardInterrupt:
            console.print("\nShutting down...")
        except Exception:
            import traceback
            console.print("\n[red]Error: Web server crashed unexpectedly[/red]")
            console.print(traceback.format_exc())
        finally:
            if agent_task:
                agent_task.cancel()
                try:
                    await agent_task
                except asyncio.CancelledError:
                    pass
            if outbound_dispatcher_task:
                outbound_dispatcher_task.cancel()
                try:
                    await outbound_dispatcher_task
                except asyncio.CancelledError:
                    pass
            await agent.close_mcp()
            cron.stop()
            agent.stop()
            await external_channels.stop_all()
            await web_channel.stop()

    asyncio.run(run())


# ============================================================================
# Agent Commands
# ============================================================================


@app.command()
def agent(
    message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
    session_id: str = typer.Option("cli:direct", "--session", "-s", help="Session ID"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Config file path"),
    markdown: bool = typer.Option(True, "--markdown/--no-markdown", help="Render assistant output as Markdown"),
    logs: bool = typer.Option(False, "--logs/--no-logs", help="Show TokenMind runtime logs during chat"),
):
    """Interact with the agent directly."""
    from loguru import logger

    from tokenmind.agent.loop import AgentLoop
    from tokenmind.bus.queue import MessageBus
    from tokenmind.config.loader import get_config_path
    from tokenmind.config.paths import get_cron_dir
    from tokenmind.cron.service import CronService

    config = _load_runtime_config(config, workspace)
    sync_workspace_templates(config.workspace_path)

    bus = MessageBus()
    provider = _make_provider(config)

    # Create cron service for tool usage (no callback needed for CLI unless running)
    cron_store_path = get_cron_dir() / "jobs.json"
    cron = CronService(cron_store_path)

    if logs:
        logger.enable("tokenmind")
    else:
        logger.disable("tokenmind")

    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        context_window_tokens=config.agents.defaults.context_window_tokens,
        web_search_config=config.tools.web.search,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        knowledge_config=config.tools.knowledge,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
        templates_config=config.templates,
        config_path=get_config_path(),
        creative_config=config.creative,
    )

    # Shared reference for progress callbacks
    _thinking: _ThinkingSpinner | None = None

    async def _cli_progress(content: str, *, tool_hint: bool = False) -> None:
        ch = agent_loop.channels_config
        if ch and tool_hint and not ch.send_tool_hints:
            return
        if ch and not tool_hint and not ch.send_progress:
            return
        _print_cli_progress_line(content, _thinking)

    if message:
        # Single message mode — direct call, no bus needed
        async def run_once():
            nonlocal _thinking
            _thinking = _ThinkingSpinner(enabled=not logs)
            with _thinking:
                response = await agent_loop.process_direct(message, session_id, on_progress=_cli_progress)
            _thinking = None
            _print_agent_response(response, render_markdown=markdown)
            await agent_loop.close_mcp()

        asyncio.run(run_once())
    else:
        # Interactive mode — route through bus like other channels
        from tokenmind.bus.events import InboundMessage
        _init_prompt_session()
        console.print(f"{__logo__} Interactive mode (type [bold]exit[/bold] or [bold]Ctrl+C[/bold] to quit)\n")

        if ":" in session_id:
            cli_channel, cli_chat_id = session_id.split(":", 1)
        else:
            cli_channel, cli_chat_id = "cli", session_id

        def _handle_signal(signum, frame):
            sig_name = signal.Signals(signum).name
            _restore_terminal()
            console.print(f"\nReceived {sig_name}, goodbye!")
            sys.exit(0)

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
        # SIGHUP is not available on Windows
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, _handle_signal)
        # Ignore SIGPIPE to prevent silent process termination when writing to closed pipes
        # SIGPIPE is not available on Windows
        if hasattr(signal, 'SIGPIPE'):
            signal.signal(signal.SIGPIPE, signal.SIG_IGN)

        async def run_interactive():
            bus_task = asyncio.create_task(agent_loop.run())
            turn_done = asyncio.Event()
            turn_done.set()
            turn_response: list[str] = []

            async def _consume_outbound():
                while True:
                    try:
                        msg = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
                        if msg.metadata.get("_progress"):
                            is_tool_hint = msg.metadata.get("_tool_hint", False)
                            ch = agent_loop.channels_config
                            if ch and is_tool_hint and not ch.send_tool_hints:
                                pass
                            elif ch and not is_tool_hint and not ch.send_progress:
                                pass
                            else:
                                await _print_interactive_progress_line(msg.content, _thinking)

                        elif not turn_done.is_set():
                            if msg.content:
                                turn_response.append(msg.content)
                            turn_done.set()
                        elif msg.content:
                            await _print_interactive_response(msg.content, render_markdown=markdown)

                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break

            outbound_task = asyncio.create_task(_consume_outbound())

            try:
                while True:
                    try:
                        _flush_pending_tty_input()
                        user_input = await _read_interactive_input_async()
                        command = user_input.strip()
                        if not command:
                            continue

                        if _is_exit_command(command):
                            _restore_terminal()
                            console.print("\nGoodbye!")
                            break

                        turn_done.clear()
                        turn_response.clear()

                        await bus.publish_inbound(InboundMessage(
                            channel=cli_channel,
                            sender_id="user",
                            chat_id=cli_chat_id,
                            content=user_input,
                        ))

                        nonlocal _thinking
                        _thinking = _ThinkingSpinner(enabled=not logs)
                        with _thinking:
                            await turn_done.wait()
                        _thinking = None

                        if turn_response:
                            _print_agent_response(turn_response[0], render_markdown=markdown)
                    except KeyboardInterrupt:
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break
                    except EOFError:
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break
            finally:
                agent_loop.stop()
                outbound_task.cancel()
                await asyncio.gather(bus_task, outbound_task, return_exceptions=True)
                await agent_loop.close_mcp()

        asyncio.run(run_interactive())


# ============================================================================
# Channel Commands
# ============================================================================


channels_app = typer.Typer(help="Manage channels")
app.add_typer(channels_app, name="channels")


@channels_app.command("status")
def channels_status():
    """Show channel status."""
    from tokenmind.channels.registry import discover_all
    from tokenmind.config.loader import load_config

    config = load_config()

    table = Table(title="Channel Status")
    table.add_column("Channel", style="cyan")
    table.add_column("Enabled", style="green")

    for name, cls in sorted(discover_all().items()):
        section = getattr(config.channels, name, None)
        if section is None:
            enabled = False
        elif isinstance(section, dict):
            enabled = section.get("enabled", False)
        else:
            enabled = getattr(section, "enabled", False)
        table.add_row(
            cls.display_name,
            "[green]\u2713[/green]" if enabled else "[dim]\u2717[/dim]",
        )

    console.print(table)


def _get_bridge_dir() -> Path:
    """Get the bridge directory, setting it up if needed."""
    import shutil
    import subprocess

    # User's bridge location
    from tokenmind.config.paths import get_bridge_install_dir

    user_bridge = get_bridge_install_dir()

    # Check if already built
    if (user_bridge / "dist" / "index.js").exists():
        return user_bridge

    # Check for npm
    npm_path = shutil.which("npm")
    if not npm_path:
        console.print("[red]npm not found. Please install Node.js >= 18.[/red]")
        raise typer.Exit(1)

    # Find source bridge: first check package data, then source dir
    pkg_bridge = Path(__file__).parent.parent / "bridge"  # tokenmind/bridge (installed)
    src_bridge = Path(__file__).parent.parent.parent / "bridge"  # repo root/bridge (dev)

    source = None
    if (pkg_bridge / "package.json").exists():
        source = pkg_bridge
    elif (src_bridge / "package.json").exists():
        source = src_bridge

    if not source:
        console.print("[red]Bridge source not found.[/red]")
        console.print("Try reinstalling: pip install --force-reinstall tokenmind-ai")
        raise typer.Exit(1)

    console.print(f"{__logo__} Setting up bridge...")

    # Copy to user directory
    user_bridge.parent.mkdir(parents=True, exist_ok=True)
    if user_bridge.exists():
        shutil.rmtree(user_bridge)
    shutil.copytree(source, user_bridge, ignore=shutil.ignore_patterns("node_modules", "dist"))

    # Install and build
    try:
        console.print("  Installing dependencies...")
        subprocess.run([npm_path, "install"], cwd=user_bridge, check=True, capture_output=True)

        console.print("  Building...")
        subprocess.run([npm_path, "run", "build"], cwd=user_bridge, check=True, capture_output=True)

        console.print("[green]✓[/green] Bridge ready\n")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Build failed: {e}[/red]")
        if e.stderr:
            console.print(f"[dim]{e.stderr.decode()[:500]}[/dim]")
        raise typer.Exit(1)

    return user_bridge


@channels_app.command("login")
def channels_login():
    """Link device via QR code."""
    import shutil
    import subprocess

    from tokenmind.config.loader import load_config
    from tokenmind.config.paths import get_runtime_subdir

    config = load_config()
    bridge_dir = _get_bridge_dir()

    console.print(f"{__logo__} Starting bridge...")
    console.print("Scan the QR code to connect.\n")

    env = {**os.environ}
    wa_cfg = getattr(config.channels, "whatsapp", None) or {}
    bridge_token = wa_cfg.get("bridgeToken", "") if isinstance(wa_cfg, dict) else getattr(wa_cfg, "bridge_token", "")
    if bridge_token:
        env["BRIDGE_TOKEN"] = bridge_token
    env["AUTH_DIR"] = str(get_runtime_subdir("whatsapp-auth"))

    npm_path = shutil.which("npm")
    if not npm_path:
        console.print("[red]npm not found. Please install Node.js.[/red]")
        raise typer.Exit(1)

    try:
        subprocess.run([npm_path, "start"], cwd=bridge_dir, check=True, env=env)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Bridge failed: {e}[/red]")


# ============================================================================
# Plugin Commands
# ============================================================================

plugins_app = typer.Typer(help="Manage channel plugins")
app.add_typer(plugins_app, name="plugins")


@plugins_app.command("list")
def plugins_list():
    """List all discovered channels (built-in and plugins)."""
    from tokenmind.channels.registry import discover_all, discover_channel_names
    from tokenmind.config.loader import load_config

    config = load_config()
    builtin_names = set(discover_channel_names())
    all_channels = discover_all()

    table = Table(title="Channel Plugins")
    table.add_column("Name", style="cyan")
    table.add_column("Source", style="magenta")
    table.add_column("Enabled", style="green")

    for name in sorted(all_channels):
        cls = all_channels[name]
        source = "builtin" if name in builtin_names else "plugin"
        section = getattr(config.channels, name, None)
        if section is None:
            enabled = False
        elif isinstance(section, dict):
            enabled = section.get("enabled", False)
        else:
            enabled = getattr(section, "enabled", False)
        table.add_row(
            cls.display_name,
            source,
            "[green]yes[/green]" if enabled else "[dim]no[/dim]",
        )

    console.print(table)


# ============================================================================
# Status Commands
# ============================================================================


@app.command()
def status():
    """Show TokenMind status."""
    from tokenmind.config.loader import get_config_path, load_config

    config_path = get_config_path()
    config = load_config()
    workspace = config.workspace_path

    console.print(f"{__logo__} TokenMind Status\n")

    console.print(f"Config: {config_path} {'[green]✓[/green]' if config_path.exists() else '[red]✗[/red]'}")
    console.print(f"Workspace: {workspace} {'[green]✓[/green]' if workspace.exists() else '[red]✗[/red]'}")

    if config_path.exists():
        from tokenmind.providers.registry import PROVIDERS

        console.print(f"Model: {config.agents.defaults.model}")

        # Check API keys from registry
        for spec in PROVIDERS:
            p = getattr(config.providers, spec.name, None)
            if p is None:
                continue
            if spec.is_oauth:
                console.print(f"{spec.label}: [green]✓ (OAuth)[/green]")
            elif spec.is_local:
                # Local deployments show api_base instead of api_key
                if p.api_base:
                    console.print(f"{spec.label}: [green]✓ {p.api_base}[/green]")
                else:
                    console.print(f"{spec.label}: [dim]not set[/dim]")
            else:
                has_key = bool(p.api_key)
                console.print(f"{spec.label}: {'[green]✓[/green]' if has_key else '[dim]not set[/dim]'}")


# ============================================================================
# OAuth Login
# ============================================================================

provider_app = typer.Typer(help="Manage providers")
app.add_typer(provider_app, name="provider")


_LOGIN_HANDLERS: dict[str, callable] = {}


def _register_login(name: str):
    def decorator(fn):
        _LOGIN_HANDLERS[name] = fn
        return fn
    return decorator


@provider_app.command("login")
def provider_login(
    provider: str = typer.Argument(..., help="OAuth provider name"),
):
    """Authenticate with an OAuth provider."""
    from tokenmind.providers.registry import PROVIDERS

    key = provider.replace("-", "_")
    spec = next((s for s in PROVIDERS if s.name == key and s.is_oauth), None)
    if not spec:
        names = ", ".join(s.name.replace("_", "-") for s in PROVIDERS if s.is_oauth)
        console.print(f"[red]Unknown OAuth provider: {provider}[/red]  Supported: {names}")
        raise typer.Exit(1)

    handler = _LOGIN_HANDLERS.get(spec.name)
    if not handler:
        console.print(f"[red]Login not implemented for {spec.label}[/red]")
        raise typer.Exit(1)

    console.print(f"{__logo__} OAuth Login - {spec.label}\n")
    handler()


if __name__ == "__main__":
    app()
