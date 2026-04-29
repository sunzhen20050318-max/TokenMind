"""Detects when the ReAct loop is stuck and should hand control back to the user.

The loop calls :meth:`StuckDetector.observe` after every decision/snapshot
cycle. The detector returns a :class:`StuckReason` (or ``None``) describing
why takeover is warranted — e.g. snapshot hasn't changed for N steps, the
last K actions all failed, or the LLM keeps emitting unparseable output.

The TaskService then flips the task to ``awaiting_user`` and stops the loop
until the user resumes (M3.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class StuckReason(str, Enum):
    NO_CHANGE = "no_change"  # snapshot identical N times in a row
    REPEATED_FAILURE = "repeated_failure"  # action failed K times in a row
    DECISION_INSTABILITY = "decision_instability"  # LLM kept proposing the same failing action
    BROWSER_GUARD = "browser_guard"  # login/captcha/security state needs user help


@dataclass
class StuckEvent:
    reason: StuckReason
    detail: str


class StuckDetector:
    """Sliding-window detector for various flavours of "stuck".

    Defaults are intentionally conservative — we'd rather a slow agent finish
    on its own than nag the user prematurely.
    """

    def __init__(
        self,
        *,
        max_unchanged_snapshots: int = 4,
        max_consecutive_failures: int = 3,
        max_repeat_action: int = 4,
    ) -> None:
        self.max_unchanged_snapshots = max_unchanged_snapshots
        self.max_consecutive_failures = max_consecutive_failures
        self.max_repeat_action = max_repeat_action

        self._unchanged_snapshots = 0
        self._consecutive_failures = 0
        self._last_snapshot: Optional[str] = None
        self._last_action_signature: Optional[str] = None
        self._repeat_action_count = 0

    def reset(self) -> None:
        """Clear all counters — call after a successful user takeover/resume."""
        self._unchanged_snapshots = 0
        self._consecutive_failures = 0
        self._last_snapshot = None
        self._last_action_signature = None
        self._repeat_action_count = 0

    def observe_snapshot(self, snapshot: str) -> Optional[StuckEvent]:
        """Feed a fresh page snapshot. Returns a StuckEvent when threshold hit."""
        if self._last_snapshot is not None and snapshot == self._last_snapshot:
            self._unchanged_snapshots += 1
        else:
            self._unchanged_snapshots = 0
        self._last_snapshot = snapshot

        if self._unchanged_snapshots >= self.max_unchanged_snapshots:
            return StuckEvent(
                reason=StuckReason.NO_CHANGE,
                detail=(
                    f"页面已连续 {self._unchanged_snapshots} 步没有变化，"
                    "AI 可能卡住了，请接管处理。"
                ),
            )
        return None

    def observe_action(
        self,
        *,
        action: str,
        args: dict,
        success: bool,
    ) -> Optional[StuckEvent]:
        """Feed the outcome of an executed action.

        Two kinds of stuck:
        - ``REPEATED_FAILURE`` — K consecutive failures regardless of action
        - ``DECISION_INSTABILITY`` — same action+args repeated K times (success
          or failure), implying the LLM is in a loop
        """
        if success:
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1

        signature = f"{action}::{sorted(args.items())}"
        if signature == self._last_action_signature:
            self._repeat_action_count += 1
        else:
            self._last_action_signature = signature
            self._repeat_action_count = 1

        if self._consecutive_failures >= self.max_consecutive_failures:
            return StuckEvent(
                reason=StuckReason.REPEATED_FAILURE,
                detail=(
                    f"已连续 {self._consecutive_failures} 个动作失败，"
                    "AI 可能无法继续，请接管处理。"
                ),
            )
        if self._repeat_action_count >= self.max_repeat_action:
            return StuckEvent(
                reason=StuckReason.DECISION_INSTABILITY,
                detail=(
                    f"AI 反复执行同一动作 ({action}) {self._repeat_action_count} 次仍未推进，"
                    "请接管处理。"
                ),
            )
        return None
