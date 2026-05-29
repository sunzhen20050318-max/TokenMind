"""WebSocket attachment path confinement (anti arbitrary-file-read)."""

from __future__ import annotations

from pathlib import Path

from tokenmind.server.websocket.handler import _path_within


def test_accepts_path_inside_uploads_root(tmp_path: Path) -> None:
    root = tmp_path / "uploads" / "web"
    f = root / "web:sess" / "user" / "uploads" / "att_1" / "pic.png"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x")
    assert _path_within(str(f), root) is True


def test_rejects_path_outside_uploads_root(tmp_path: Path) -> None:
    root = tmp_path / "uploads" / "web"
    root.mkdir(parents=True, exist_ok=True)
    assert _path_within("/etc/passwd", root) is False


def test_rejects_traversal_escape(tmp_path: Path) -> None:
    root = tmp_path / "uploads" / "web"
    root.mkdir(parents=True, exist_ok=True)
    escape = str(root / ".." / ".." / "secret.png")
    assert _path_within(escape, root) is False


def test_rejects_when_root_missing() -> None:
    assert _path_within("/anything", None) is False
