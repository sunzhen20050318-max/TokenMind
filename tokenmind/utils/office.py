"""Cross-platform helpers for locating LibreOffice (`soffice`).

Used by both the attachment-preview pipeline and the documents /
presentations skill scripts. Also exported so the ExecTool can prepend
the soffice install directory to ``PATH`` when present — that way the
LLM can call ``soffice ...`` from a shell command on Windows / macOS
even when the binary isn't on the user's PATH.
"""
from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path


# Ordered candidate locations for soffice across platforms. We try PATH
# first (covers Linux distros, macOS Homebrew, and Windows where users
# have explicitly added LibreOffice to PATH); if that fails we fall back
# to well-known install paths.
_KNOWN_LOCATIONS: tuple[str, ...] = (
    # macOS — DMG installer drops the app here.
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    # Windows — MSI installer default.
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    # Linux — non-PATH installs (snap, tarball, /opt).
    "/opt/libreoffice/program/soffice",
    "/snap/bin/libreoffice.soffice",
    "/usr/lib/libreoffice/program/soffice",
)


@lru_cache(maxsize=1)
def find_soffice() -> str | None:
    """Locate ``soffice`` across platforms. Returns the absolute path or ``None``.

    Looks for both ``soffice`` (Linux / macOS) and ``soffice.exe`` (Windows)
    on PATH first, then falls back to platform-specific install paths.
    Cached so repeated calls are free.
    """
    for name in ("soffice", "soffice.exe"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in _KNOWN_LOCATIONS:
        if Path(candidate).is_file():
            return candidate
    return None


def soffice_install_dir() -> str | None:
    """Directory containing the resolved soffice executable, or ``None``.

    Suitable for prepending to ``PATH`` so child processes (e.g. the
    ExecTool's shell commands) can invoke ``soffice`` directly when the
    user has installed LibreOffice but not added it to PATH themselves.
    """
    soffice = find_soffice()
    if not soffice:
        return None
    return str(Path(soffice).parent)


def augmented_path_append(existing: str = "") -> str:
    """Return a PATH suffix string that adds the soffice install dir
    when present and not already on PATH. Returns ``existing`` unchanged
    if soffice is missing or already reachable.
    """
    if shutil.which("soffice") or shutil.which("soffice.exe"):
        return existing  # already on PATH
    extra = soffice_install_dir()
    if not extra:
        return existing
    parts = [p for p in (existing,) if p]
    if extra not in parts:
        parts.append(extra)
    return os.pathsep.join(parts)
