"""Live tracking of in-progress file edits, driven by streaming tool-call deltas.

When the model streams arguments for ``write_file`` or ``edit_file``, this
tracker watches the accumulating JSON, snapshots the target file the
moment the path is known, and emits progress events as the body of the
edit takes shape. After the tool actually runs, ``finalize()`` produces a
final ``end`` event with the exact diff stats.

Event payload shape (matches what the WebUI's ToolIndicator will consume
in Stage 4):

    {
        "version": 1,
        "call_id": str,
        "tool": "write_file" | "edit_file",
        "path": str,                 # relative to workspace if possible
        "phase": "start" | "end" | "error",
        "added": int,
        "deleted": int,
        "approximate": bool,         # True while streaming, False at end
        "status": "editing" | "done" | "error",
    }

This is a TokenMind-shaped port of nanobot's ``file_edit_events.py``
(commit ``722b760``), trimmed for our tool set (no ``apply_patch``).
"""

from __future__ import annotations

import difflib
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tokenmind.providers.base import ToolCallDelta

TRACKED_TOOLS = frozenset({"write_file", "edit_file"})

# Throttling: don't spam the WebUI with sub-millisecond updates.
_LIVE_EMIT_INTERVAL_S = 0.18
# Force an immediate emit when added/deleted change by this many lines,
# even before the interval elapses (so big chunks feel instant).
_LIVE_EMIT_LINE_STEP = 24
# Don't snapshot files bigger than this — the cost outweighs the value.
_MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024


EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(slots=True)
class _FileSnapshot:
    """The pre-edit state of the target file."""

    path: Path
    exists: bool
    text: str | None

    @property
    def line_count(self) -> int:
        if not self.text:
            return 0
        return self.text.count("\n") + (0 if self.text.endswith("\n") else 1)


@dataclass(slots=True)
class _CallState:
    """Per-tool-call accumulation state."""

    call_id: str
    tool_name: str = ""
    arguments: str = ""
    path: str | None = None
    resolved_path: Path | None = None
    display_path: str = ""
    before: _FileSnapshot | None = None
    last_emitted_added: int = -1
    last_emitted_deleted: int = -1
    last_emit_at: float = 0.0
    started_emit: bool = False
    finalized: bool = False


class FileEditTracker:
    """Watches streaming tool-call deltas and emits live file-edit events.

    Parameters
    ----------
    workspace
        Used to resolve relative paths and to display them relative to the
        project root in the emitted events.
    emit
        Async callback receiving each event dict. Stage 4 will hook this
        into the WebSocket so the WebUI can render an animated +N/-M
        counter on the in-progress tool entry.
    """

    def __init__(
        self,
        *,
        workspace: Path | None,
        emit: EventCallback,
    ) -> None:
        self._workspace = workspace
        self._emit = emit
        self._states: dict[str, _CallState] = {}

    async def on_delta(self, delta: ToolCallDelta) -> None:
        """Process one streaming tool-call argument delta.

        Records the latest accumulated state per call_id (or per index
        when the id is not yet known) and emits a live progress event
        whenever line counts have changed enough to warrant another frame.
        """
        key = self._key_for(delta)
        state = self._states.get(key)
        if state is None:
            state = _CallState(call_id=delta.get("call_id") or "")
            self._states[key] = state

        # Pick up the call id once it arrives so finalize() can find us.
        if not state.call_id and delta.get("call_id"):
            state.call_id = delta["call_id"]
            # Move the entry to be keyed by call_id when promoted from an
            # index-only placeholder.
            real_key = state.call_id
            if real_key != key:
                self._states[real_key] = state
                self._states.pop(key, None)

        name = delta.get("name")
        if name and not state.tool_name:
            state.tool_name = name

        # OpenAI streaming sends arguments either as an `arguments_delta`
        # increment or as the full accumulated `arguments` snapshot.
        # Trust whichever is longer — that way replaying a missed delta
        # via the snapshot is still safe.
        args_delta = delta.get("arguments_delta", "")
        if args_delta:
            state.arguments += args_delta
        full_args = delta.get("arguments", "")
        if full_args and len(full_args) > len(state.arguments):
            state.arguments = full_args

        if state.tool_name not in TRACKED_TOOLS:
            return
        if state.finalized:
            return

        # Resolve the path as soon as it's complete in the streamed JSON.
        if state.path is None:
            path_val = _extract_complete_json_string(state.arguments, "path")
            if path_val is not None:
                state.path = path_val
                state.resolved_path = self._resolve(path_val)
                state.display_path = self._display(state.resolved_path)
                state.before = _read_snapshot(state.resolved_path)

        if state.path is None:
            return

        if state.tool_name == "write_file":
            added = _scan_string_lines(state.arguments, "content")
            deleted = state.before.line_count if state.before else 0
        else:  # edit_file
            added = _scan_string_lines(state.arguments, "new_text")
            deleted = _scan_string_lines(state.arguments, "old_text")

        now = time.monotonic()
        if not self._should_emit(state, added, deleted, now):
            return
        state.last_emitted_added = added
        state.last_emitted_deleted = deleted
        state.last_emit_at = now
        state.started_emit = True

        await self._emit({
            "version": 1,
            "call_id": state.call_id,
            "tool": state.tool_name,
            "path": state.display_path,
            "phase": "start",
            "added": added,
            "deleted": deleted,
            "approximate": True,
            "status": "editing",
        })

    async def finalize(
        self,
        call_id: str,
        *,
        status: str = "done",
        error: str | None = None,
    ) -> None:
        """Emit the final ``end`` (or ``error``) event with exact diff stats.

        Should be called after the tool has actually executed (or failed).
        Computes the exact added/deleted line counts by diffing the
        pre-edit snapshot against the on-disk file as it stands now.
        """
        state = self._find_state(call_id)
        if state is None or state.finalized:
            return
        state.finalized = True

        added, deleted = 0, 0
        if state.resolved_path is not None and state.before is not None:
            after = _read_snapshot(state.resolved_path)
            if state.before.text is not None and after.text is not None:
                added, deleted = _line_diff_stats(state.before.text, after.text)

        payload: dict[str, Any] = {
            "version": 1,
            "call_id": call_id,
            "tool": state.tool_name,
            "path": state.display_path,
            "phase": "error" if status == "error" else "end",
            "added": added,
            "deleted": deleted,
            "approximate": False,
            "status": status,
        }
        if error:
            payload["error"] = error[:240]
        await self._emit(payload)

    # ── internals ────────────────────────────────────────────────────────

    @staticmethod
    def _key_for(delta: ToolCallDelta) -> str:
        if delta.get("call_id"):
            return str(delta["call_id"])
        return f"idx:{delta.get('index', 0)}"

    def _find_state(self, call_id: str) -> _CallState | None:
        state = self._states.get(call_id)
        if state is not None:
            return state
        for s in self._states.values():
            if s.call_id == call_id:
                return s
        return None

    @staticmethod
    def _should_emit(
        state: _CallState, added: int, deleted: int, now: float,
    ) -> bool:
        if not state.started_emit:
            return True
        if added == state.last_emitted_added and deleted == state.last_emitted_deleted:
            return False
        line_change = max(
            abs(added - state.last_emitted_added),
            abs(deleted - state.last_emitted_deleted),
        )
        if line_change >= _LIVE_EMIT_LINE_STEP:
            return True
        return now - state.last_emit_at >= _LIVE_EMIT_INTERVAL_S

    def _resolve(self, raw: str) -> Path:
        p = Path(raw).expanduser()
        if not p.is_absolute() and self._workspace is not None:
            p = self._workspace / p
        try:
            return p.resolve()
        except OSError:
            return p

    def _display(self, path: Path) -> str:
        if self._workspace is not None:
            try:
                return path.relative_to(self._workspace.resolve()).as_posix()
            except (ValueError, OSError):
                pass
        return path.as_posix()


# ─── streaming JSON string scanners ──────────────────────────────────────


def _extract_complete_json_string(source: str, key: str) -> str | None:
    """Return the fully-decoded value for ``"key": "..."``, or ``None``
    if the closing quote hasn't streamed in yet."""
    m = re.search(rf'"{re.escape(key)}"\s*:\s*"', source)
    if m is None:
        return None
    out: list[str] = []
    i = m.end()
    escape = False
    while i < len(source):
        ch = source[i]
        if escape:
            escape = False
            if ch == "n":
                out.append("\n")
            elif ch == "t":
                out.append("\t")
            elif ch == "r":
                out.append("\r")
            elif ch == "u":
                digits = source[i + 1 : i + 5]
                if len(digits) < 4:
                    return None
                try:
                    out.append(chr(int(digits, 16)))
                except ValueError:
                    return None
                i += 4
            else:
                out.append(ch)
            i += 1
            continue
        if ch == "\\":
            escape = True
            i += 1
            continue
        if ch == '"':
            return "".join(out)
        out.append(ch)
        i += 1
    return None


def _scan_string_lines(source: str, key: str) -> int:
    """Count the lines that the streaming value at ``key`` would produce.

    "Lines" follows the convention that a non-empty value contributes at
    least 1; each ``\\n`` (whether literal or as an escape sequence) bumps
    the count. Stops at the closing quote if present, otherwise stops
    when the buffer ends — that's the whole point of streaming.
    """
    m = re.search(rf'"{re.escape(key)}"\s*:\s*"', source)
    if m is None:
        return 0
    chars_seen = 0
    newlines = 0
    last_was_newline = False
    i = m.end()
    escape = False
    while i < len(source):
        ch = source[i]
        if escape:
            escape = False
            chars_seen += 1
            if ch == "n":
                newlines += 1
                last_was_newline = True
            else:
                last_was_newline = False
            i += 1
            continue
        if ch == "\\":
            escape = True
            i += 1
            continue
        if ch == '"':
            break
        chars_seen += 1
        if ch == "\n":
            newlines += 1
            last_was_newline = True
        else:
            last_was_newline = False
        i += 1

    if chars_seen == 0:
        return 0
    return newlines + (0 if last_was_newline else 1)


# ─── disk I/O ────────────────────────────────────────────────────────────


def _read_snapshot(path: Path) -> _FileSnapshot:
    try:
        if not path.exists() or not path.is_file():
            return _FileSnapshot(path=path, exists=False, text="")
        size = path.stat().st_size
        if size > _MAX_SNAPSHOT_BYTES:
            return _FileSnapshot(path=path, exists=True, text=None)
        raw = path.read_bytes()
    except OSError:
        return _FileSnapshot(path=path, exists=path.exists(), text=None)
    if b"\x00" in raw:
        return _FileSnapshot(path=path, exists=True, text=None)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return _FileSnapshot(path=path, exists=True, text=None)
    return _FileSnapshot(path=path, exists=True, text=text.replace("\r\n", "\n"))


def _line_diff_stats(before: str, after: str) -> tuple[int, int]:
    """Return ``(added, deleted)`` for a line-level diff."""
    before_lines = before.replace("\r\n", "\n").splitlines()
    after_lines = after.replace("\r\n", "\n").splitlines()
    matcher = difflib.SequenceMatcher(
        a=before_lines, b=after_lines, autojunk=False,
    )
    added = 0
    deleted = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("replace", "delete"):
            deleted += i2 - i1
        if tag in ("replace", "insert"):
            added += j2 - j1
    return added, deleted
