"""SSRF guard on the remote attachment downloader."""

from __future__ import annotations

import socket
from pathlib import Path
from unittest.mock import patch

import pytest

from tokenmind.server.attachments import AttachmentStore


def _resolve_internal(hostname, port, family=0, type_=0):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("169.254.169.254", 0))]


def test_remote_downloader_blocks_internal_target(tmp_path: Path) -> None:
    store = AttachmentStore(tmp_path)
    with patch("tokenmind.security.network.socket.getaddrinfo", _resolve_internal):
        with pytest.raises(ValueError, match="Blocked"):
            store._default_remote_downloader("http://metadata.internal/latest/meta-data/")


def test_remote_downloader_rejects_non_http_scheme(tmp_path: Path) -> None:
    store = AttachmentStore(tmp_path)
    with pytest.raises(ValueError, match="Blocked"):
        store._default_remote_downloader("file:///etc/passwd")
