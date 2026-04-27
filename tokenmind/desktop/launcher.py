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


def main(argv: Sequence[str] | None = None) -> int:
    """Start TokenMind and open the local Web UI."""
    args = parse_args(argv)
    port = find_available_port(args.port)
    url = f"http://localhost:{port}"

    print(f"Starting TokenMind desktop on {url}")
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
        print(f"TokenMind is ready: {url}")
        if not args.no_browser:
            webbrowser.open(url)
    else:
        print(
            f"TokenMind did not become ready within {DEFAULT_READY_TIMEOUT_S:.0f}s. "
            f"Try opening {url} or check the logs above.",
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
