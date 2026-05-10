"""Desktop launcher for packaged TokenMind Windows builds."""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser
from collections.abc import Sequence

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18888
DEFAULT_PORT_ATTEMPTS = 50
DEFAULT_READY_TIMEOUT_S = 60.0


def is_port_available(port: int, host: str = DEFAULT_HOST) -> bool:
    """Return True when a local TCP port can be bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_available_port(
    start_port: int = DEFAULT_PORT,
    *,
    attempts: int = DEFAULT_PORT_ATTEMPTS,
    host: str = DEFAULT_HOST,
) -> int:
    """Find the first available localhost port, starting at ``start_port``."""
    for offset in range(max(1, attempts)):
        port = start_port + offset
        if is_port_available(port, host):
            return port
    raise RuntimeError(f"No available local port found from {start_port} to {start_port + attempts - 1}")


def wait_for_port(
    port: int,
    *,
    host: str = DEFAULT_HOST,
    timeout_s: float = DEFAULT_READY_TIMEOUT_S,
) -> bool:
    """Wait until a TCP port accepts connections."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def run_web_server(port: int, *, workspace: str | None = None, config: str | None = None) -> None:
    """Run the existing TokenMind web server in this process."""
    from tokenmind.cli.commands import web

    web(port=port, workspace=workspace, config=config)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse desktop launcher options."""
    parser = argparse.ArgumentParser(description="Start TokenMind desktop Web UI.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Preferred local web port.")
    parser.add_argument("--workspace", default=None, help="Optional TokenMind workspace directory.")
    parser.add_argument("--config", default=None, help="Optional TokenMind config file path.")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the local server without opening the browser automatically.",
    )
    return parser.parse_args(argv)


def build_launch_url(port: int, *, launched_at: int | None = None) -> str:
    """Compose the URL the desktop launcher hands to webbrowser.open.

    The ``launch_at`` query parameter is intentional cache-busting: most
    browsers reuse an existing tab when ``webbrowser.open`` is called with
    a URL that's already open, which means an upgraded .app would land on
    the previous launch's stale-cached page. Making the URL unique per
    launch forces a fresh tab and a fresh document load — the only
    reliable way to break out of a sticky browser cache after upgrading
    over an older release that lacked our no-cache headers.
    """
    ts = int(launched_at if launched_at is not None else time.time())
    return f"http://localhost:{port}/?launch_at={ts}"


def main(argv: Sequence[str] | None = None) -> int:
    """Start TokenMind and open the local Web UI."""
    args = parse_args(argv)
    port = find_available_port(args.port)
    base_url = f"http://localhost:{port}"
    launch_url = build_launch_url(port)

    print(f"Starting TokenMind desktop on {base_url}")
    print("Keep this window open while using TokenMind. Close it to stop the local service.")

    server_thread = threading.Thread(
        target=run_web_server,
        kwargs={
            "port": port,
            "workspace": args.workspace,
            "config": args.config,
        },
        name="tokenmind-web-server",
        daemon=True,
    )
    server_thread.start()

    if wait_for_port(port):
        print(f"TokenMind is ready: {base_url}")
        if not args.no_browser:
            # new=2 asks the browser to open a new tab rather than reuse an
            # existing one. Combined with the per-launch query param above,
            # this gives the upgraded build a clean rendering surface.
            webbrowser.open(launch_url, new=2)
    else:
        print(
            f"TokenMind did not become ready within {DEFAULT_READY_TIMEOUT_S:.0f}s. "
            f"Try opening {base_url} or check the logs above.",
            file=sys.stderr,
        )

    try:
        while server_thread.is_alive():
            server_thread.join(timeout=0.5)
    except KeyboardInterrupt:
        print("\nStopping TokenMind...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
