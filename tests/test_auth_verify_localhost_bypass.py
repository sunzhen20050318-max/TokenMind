"""Tests for the ``/api/auth/verify`` localhost bypass.

Even when an ``auth_secret`` is configured (because the server is bound
to ``0.0.0.0`` for LAN access), a caller hitting the API from
``localhost`` shouldn't be told that a secret is required — the HTTP
middleware already waves them through, and forcing the user-on-server
to paste a password is pure friction. Non-localhost callers still see
``required: True`` so the WebUI prompts for the secret.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from tokenmind.bus.queue import MessageBus
from tokenmind.server.app import create_app
from tokenmind.server.channel.web import WebChannel, WebChannelConfig
from tokenmind.server.websocket.manager import ConnectionManager


def _make_client(*, auth_secret: str) -> TestClient:
    bus = MessageBus()
    web_channel = WebChannel(WebChannelConfig(), bus)
    connection_manager = ConnectionManager()
    agent_loop = MagicMock()
    agent_loop.cron_service = None
    agent_loop.usage_recorder = None
    session_manager = MagicMock()

    app = create_app(
        bus=bus,
        agent_loop=agent_loop,
        session_manager=session_manager,
        connection_manager=connection_manager,
        web_channel=web_channel,
        auth_secret=auth_secret,
    )
    return TestClient(app)


def test_no_secret_configured_returns_not_required() -> None:
    client = _make_client(auth_secret="")
    r = client.post("/api/auth/verify", json={})
    assert r.status_code == 200
    body = r.json()
    assert body == {"required": False, "ok": True}


def test_secret_configured_localhost_bypasses_prompt() -> None:
    """The whole point of this test file: a server with a secret AND
    a localhost caller should report ``required: False`` so the
    AuthGate frontend skips the password prompt."""
    client = _make_client(auth_secret="s3cret-xyz")
    # TestClient sets client.host to "testclient" by default; force the
    # request to look like it came from 127.0.0.1.
    r = client.post(
        "/api/auth/verify",
        json={},
        headers={"X-TokenMind-Secret": "s3cret-xyz"},  # not strictly needed for localhost
    )
    # TestClient's default client_host is "testclient", which is NOT in
    # the localhost set — so this should NOT bypass. Confirm baseline
    # before we patch.
    assert r.json()["required"] is True

    # Now simulate a localhost call by overriding the test client host.
    with TestClient(client.app, base_url="http://localhost") as lc:
        # TestClient still reports client.host as "testclient" regardless
        # of base_url, so directly poke the client tuple via the ASGI scope.
        # The cleanest way is to use a manual ASGI call.
        pass

    # Use httpx directly with a custom transport that sets the client tuple.
    import httpx

    async def _call_localhost(app: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345)),
            base_url="http://testserver",
        ) as c:
            resp = await c.post("/api/auth/verify", json={})
            return resp.json()

    import asyncio

    body = asyncio.run(_call_localhost(client.app))
    assert body == {"required": False, "ok": True}


def test_secret_configured_non_localhost_caller_is_prompted() -> None:
    """LAN callers should still get ``required: True`` and ``ok=False``
    until they paste the right secret."""
    client = _make_client(auth_secret="s3cret-xyz")

    import asyncio

    import httpx

    async def _call(client_host: str, secret_in_body: str) -> dict[str, Any]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(client_app := client.app, client=(client_host, 33333)),
            base_url="http://testserver",
        ) as c:
            _ = client_app  # keep linter happy
            resp = await c.post("/api/auth/verify", json={"secret": secret_in_body})
            return resp.json()

    # Wrong secret from a LAN IP -> required + not ok.
    body = asyncio.run(_call("192.168.1.42", ""))
    assert body["required"] is True
    assert body["ok"] is False

    # Correct secret -> ok.
    body = asyncio.run(_call("192.168.1.42", "s3cret-xyz"))
    assert body["required"] is True
    assert body["ok"] is True


@pytest.mark.parametrize("localhost_addr", ["127.0.0.1", "::1", "localhost"])
def test_all_localhost_aliases_bypass(localhost_addr: str) -> None:
    client = _make_client(auth_secret="s3cret")

    import asyncio

    import httpx

    async def _call() -> dict[str, Any]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app, client=(localhost_addr, 12345)),
            base_url="http://testserver",
        ) as c:
            resp = await c.post("/api/auth/verify", json={})
            return resp.json()

    body = asyncio.run(_call())
    assert body == {"required": False, "ok": True}
