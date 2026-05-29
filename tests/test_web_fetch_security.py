"""Tests for web_fetch SSRF protection and untrusted content marking."""

from __future__ import annotations

import json
import socket
from unittest.mock import patch

import pytest

from tokenmind.agent.tools.web import WebFetchTool


def _fake_resolve_private(hostname, port, family=0, type_=0):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("169.254.169.254", 0))]


def _fake_resolve_public(hostname, port, family=0, type_=0):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]


@pytest.mark.asyncio
async def test_web_fetch_blocks_private_ip():
    tool = WebFetchTool()
    with patch("tokenmind.security.network.socket.getaddrinfo", _fake_resolve_private):
        result = await tool.execute(url="http://169.254.169.254/computeMetadata/v1/")
    data = json.loads(result)
    assert "error" in data
    assert "private" in data["error"].lower() or "blocked" in data["error"].lower()


@pytest.mark.asyncio
async def test_web_fetch_blocks_localhost():
    tool = WebFetchTool()
    def _resolve_localhost(hostname, port, family=0, type_=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0))]
    with patch("tokenmind.security.network.socket.getaddrinfo", _resolve_localhost):
        result = await tool.execute(url="http://localhost/admin")
    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_web_fetch_result_contains_untrusted_flag():
    """When fetch succeeds, result JSON must include untrusted=True and the banner."""
    tool = WebFetchTool()

    fake_html = "<html><head><title>Test</title></head><body><p>Hello world</p></body></html>"

    import httpx

    class FakeResponse:
        status_code = 200
        url = "https://example.com/page"
        text = fake_html
        headers = {"content-type": "text/html"}
        is_redirect = False
        def raise_for_status(self): pass
        def json(self): return {}

    async def _fake_get(self, url, **kwargs):
        return FakeResponse()

    with patch("tokenmind.security.network.socket.getaddrinfo", _fake_resolve_public), \
         patch("httpx.AsyncClient.get", _fake_get):
        result = await tool.execute(url="https://example.com/page")

    data = json.loads(result)
    assert data.get("untrusted") is True
    assert "[External content" in data.get("text", "")


@pytest.mark.asyncio
async def test_web_fetch_blocks_redirect_to_internal():
    """A public URL that 302-redirects to an internal address must be blocked
    BEFORE the request to the internal host fires."""
    tool = WebFetchTool()

    class RedirectResponse:
        status_code = 302
        url = "https://example.com/page"
        text = ""
        headers = {"location": "http://169.254.169.254/latest/meta-data/"}
        is_redirect = True
        def raise_for_status(self): pass
        def json(self): return {}

    requested_urls: list[str] = []

    async def _fake_get(self, url, **kwargs):
        requested_urls.append(str(url))
        return RedirectResponse()

    def _resolve(hostname, port, family=0, type_=0):
        ip = "169.254.169.254" if "169.254" in hostname else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 0))]

    with patch("tokenmind.security.network.socket.getaddrinfo", _resolve), \
         patch("httpx.AsyncClient.get", _fake_get):
        result = await tool.execute(url="https://example.com/page")

    data = json.loads(result)
    assert "error" in data
    assert "redirect" in data["error"].lower()
    # The internal host must never have been requested.
    assert not any("169.254" in u for u in requested_urls)
