"""Tests for the desktop launcher's URL builder.

The launcher hands a URL to webbrowser.open. Browsers reuse existing tabs
keyed on URL, so an upgraded .app needs the URL to differ each launch —
otherwise the cached tab from the previous version sticks around without
ever revalidating its bundled JavaScript.
"""

from __future__ import annotations

import re

from tokenmind.desktop.launcher import build_launch_url


def test_build_launch_url_uses_localhost_and_port() -> None:
    url = build_launch_url(18888, launched_at=1_700_000_000)
    assert url.startswith("http://localhost:18888/")


def test_build_launch_url_carries_launch_at_query_param() -> None:
    url = build_launch_url(18888, launched_at=1_700_000_000)
    assert "?launch_at=1700000000" in url


def test_build_launch_url_uniqueness_per_launch_timestamp() -> None:
    """Two launches at different timestamps must produce different URLs;
    that's the whole point of the cache-busting query parameter."""
    url_a = build_launch_url(18888, launched_at=1_700_000_000)
    url_b = build_launch_url(18888, launched_at=1_700_000_005)
    assert url_a != url_b


def test_build_launch_url_uses_current_time_when_unspecified() -> None:
    """The default timestamp source should be live wall-clock time so each
    real-world launch differs without callers needing to thread anything in."""
    url = build_launch_url(18888)
    match = re.search(r"\?launch_at=(\d+)", url)
    assert match is not None
    ts = int(match.group(1))
    # Sanity: epoch seconds for any modern launch — never zero, never
    # absurdly large. Anything roughly in the 2025-2050 range passes.
    assert 1_700_000_000 < ts < 2_500_000_000


def test_build_launch_url_handles_alternate_port() -> None:
    url = build_launch_url(9999, launched_at=1_700_000_000)
    assert url.startswith("http://localhost:9999/")
