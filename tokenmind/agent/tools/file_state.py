"""Per-session tracking of which files have been read.

Used by ``read_file`` and ``edit_file`` to enforce a read-before-edit
discipline: the agent must view a file (so it has the surrounding
context) before mutating it. This catches a common failure mode where
the model edits based on what it *thinks* the file contains, not what
it actually contains.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock


@dataclass
class ReadState:
    """A snapshot of a file at the time it was read by the agent."""

    mtime: float
    size: int
    last_read_at: float


class FileStates:
    """Tracks per-session file read records.

    Keys are (session_key, absolute_path_str). The class is thread-safe
    because tools may execute concurrently across asyncio tasks that
    share the same event loop thread, but defensive locking keeps the
    invariant simple.
    """

    def __init__(self) -> None:
        self._by_session: dict[str, dict[str, ReadState]] = {}
        self._lock = Lock()

    def record_read(self, session_key: str, path: Path) -> None:
        """Record that the given file was read in this session."""
        try:
            st = path.stat()
        except OSError:
            return
        key = str(path)
        with self._lock:
            self._by_session.setdefault(session_key, {})[key] = ReadState(
                mtime=st.st_mtime,
                size=st.st_size,
                last_read_at=time.time(),
            )

    def check_before_edit(self, session_key: str, path: Path) -> str | None:
        """Return a warning string if the agent should re-read the file.

        Returns None when the edit is safe to proceed.
        """
        key = str(path)
        with self._lock:
            recorded = self._by_session.get(session_key, {}).get(key)
        if recorded is None:
            return (
                f"You haven't read {path} in this session yet. "
                "Use read_file to view it before editing — this prevents "
                "edits based on assumed (rather than actual) file content."
            )
        try:
            st = path.stat()
        except OSError:
            return None
        if st.st_mtime > recorded.mtime + 1e-6:
            return (
                f"{path} was modified after you last read it. "
                "Use read_file again to see the current content before editing."
            )
        return None

    def clear_session(self, session_key: str) -> None:
        """Drop all recorded reads for a session (e.g. on session reset)."""
        with self._lock:
            self._by_session.pop(session_key, None)
