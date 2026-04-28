"""StuckDetector unit tests — exercise the three takeover triggers."""

from __future__ import annotations

from tokenmind.browser_agent.stuck_detector import StuckDetector, StuckReason


def test_first_snapshot_never_triggers() -> None:
    det = StuckDetector(max_unchanged_snapshots=2)
    assert det.observe_snapshot("foo") is None


def test_unchanged_snapshots_trigger_after_threshold() -> None:
    det = StuckDetector(max_unchanged_snapshots=3)
    assert det.observe_snapshot("a") is None  # streak 0
    assert det.observe_snapshot("a") is None  # streak 1
    assert det.observe_snapshot("a") is None  # streak 2
    event = det.observe_snapshot("a")           # streak 3 → trigger
    assert event is not None
    assert event.reason is StuckReason.NO_CHANGE


def test_change_resets_unchanged_streak() -> None:
    det = StuckDetector(max_unchanged_snapshots=2)
    det.observe_snapshot("a")
    det.observe_snapshot("a")  # streak 1
    det.observe_snapshot("b")  # different → reset
    assert det.observe_snapshot("b") is None  # streak 1 again
    assert det.observe_snapshot("b").reason is StuckReason.NO_CHANGE  # streak 2


def test_consecutive_failures_trigger() -> None:
    det = StuckDetector(max_consecutive_failures=2)
    assert det.observe_action(action="click", args={"selector": "@e1"}, success=False) is None
    event = det.observe_action(action="click", args={"selector": "@e2"}, success=False)
    assert event is not None
    assert event.reason is StuckReason.REPEATED_FAILURE


def test_success_resets_failure_streak() -> None:
    det = StuckDetector(max_consecutive_failures=2)
    det.observe_action(action="x", args={}, success=False)
    det.observe_action(action="x", args={}, success=True)  # reset
    assert det.observe_action(action="x", args={}, success=False) is None


def test_repeated_action_signature_triggers_instability() -> None:
    det = StuckDetector(max_repeat_action=3, max_consecutive_failures=99)
    args = {"selector": "@e1"}
    # Same signature 3 times — even if successful, it's a stuck signal.
    det.observe_action(action="click", args=args, success=True)
    det.observe_action(action="click", args=args, success=True)
    event = det.observe_action(action="click", args=args, success=True)
    assert event is not None
    assert event.reason is StuckReason.DECISION_INSTABILITY


def test_different_action_resets_repeat_counter() -> None:
    det = StuckDetector(max_repeat_action=2, max_consecutive_failures=99)
    det.observe_action(action="click", args={"x": 1}, success=True)
    det.observe_action(action="scroll", args={"d": "down"}, success=True)
    # First repeat-counter reset by different action.
    assert det.observe_action(action="click", args={"x": 1}, success=True) is None


def test_reset_clears_all_counters() -> None:
    det = StuckDetector(max_unchanged_snapshots=2, max_consecutive_failures=2, max_repeat_action=2)
    det.observe_snapshot("a")
    det.observe_snapshot("a")
    det.observe_action(action="x", args={}, success=False)
    det.reset()
    # All counters back to zero — should take full threshold to trigger again.
    assert det.observe_snapshot("a") is None
    assert det.observe_snapshot("a") is None
    assert det.observe_snapshot("a").reason is StuckReason.NO_CHANGE
