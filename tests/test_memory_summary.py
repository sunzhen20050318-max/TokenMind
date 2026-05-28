"""Tests for the two-tier memory: injected summary + periodic purification.

MEMORY.md is the append-only source of truth and is NOT injected into the
system prompt. Instead consolidation folds out a compressed summary (capped at
``summary_max_tokens``) which is what gets injected, and MEMORY.md is purified
back under ``purify_max_tokens`` on a time gate.
"""

import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from tokenmind.agent.memory import MemoryStore
from tokenmind.config.schema import MemoryConfig
from tokenmind.providers.base import LLMResponse, ToolCallRequest

# Small caps so "big" memory is only a few hundred chars in tests.
_CFG = MemoryConfig(summary_max_tokens=50, purify_max_tokens=100, purify_interval_days=7)
_BIG = "alpha beta gamma delta epsilon zeta eta theta " * 40  # > 100 tokens


def _messages(n: int = 30):
    return [
        {"role": "user", "content": f"msg{i}", "timestamp": "2026-01-01 00:00"}
        for i in range(n)
    ]


def _save_response(history_entry, memory_update, memory_summary=None):
    args = {"history_entry": history_entry, "memory_update": memory_update}
    if memory_summary is not None:
        args["memory_summary"] = memory_summary
    return LLMResponse(
        content=None,
        tool_calls=[ToolCallRequest(id="c1", name="save_memory", arguments=args)],
    )


def _purify_response(purified_memory, memory_summary=None):
    args = {"purified_memory": purified_memory}
    if memory_summary is not None:
        args["memory_summary"] = memory_summary
    return LLMResponse(
        content=None,
        tool_calls=[ToolCallRequest(id="c1", name="purify_memory", arguments=args)],
    )


class TestGetMemoryContext:
    def test_returns_fresh_summary(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path, memory_config=_CFG)
        store.write_long_term(_BIG)
        store.write_summary("SHORT SUMMARY")
        store._update_meta(summary_source_hash=store._content_hash(_BIG))

        ctx = store.get_memory_context()
        assert "SHORT SUMMARY" in ctx
        assert "alpha beta gamma" not in ctx  # full memory NOT injected

    def test_injects_full_when_small_and_no_summary(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path, memory_config=_CFG)
        store.write_long_term("tiny memory")
        ctx = store.get_memory_context()
        assert "tiny memory" in ctx
        assert "pending" not in ctx

    def test_truncates_when_big_and_no_summary(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path, memory_config=_CFG)
        store.write_long_term(_BIG)
        ctx = store.get_memory_context()
        assert "summary pending" in ctx
        # bounded — fewer tokens than the full file
        from tokenmind.utils.helpers import estimate_text_tokens

        assert estimate_text_tokens(ctx) < estimate_text_tokens(_BIG)

    def test_serves_stale_summary_until_refresh(self, tmp_path: Path) -> None:
        # Out-of-band edit: keep serving the last-known-good summary (bounded,
        # mostly still valid) rather than a truncated head, until the
        # background refresh produces a fresh one.
        store = MemoryStore(tmp_path, memory_config=_CFG)
        store.write_long_term(_BIG)
        store.write_summary("LAST GOOD SUMMARY")
        store._update_meta(summary_source_hash="stale")
        ctx = store.get_memory_context()
        assert "LAST GOOD SUMMARY" in ctx
        assert "summary pending" not in ctx

    def test_truncated_head_only_when_no_summary_exists(self, tmp_path: Path) -> None:
        # Big memory that was NEVER summarized (no summary file) → truncated head.
        store = MemoryStore(tmp_path, memory_config=_CFG)
        store.write_long_term(_BIG)
        ctx = store.get_memory_context()
        assert "summary pending" in ctx

    def test_summary_disabled_injects_full(self, tmp_path: Path) -> None:
        cfg = MemoryConfig(summary_enabled=False, summary_max_tokens=50)
        store = MemoryStore(tmp_path, memory_config=cfg)
        store.write_long_term(_BIG)
        store.write_summary("SHOULD BE IGNORED")
        ctx = store.get_memory_context()
        assert "alpha beta gamma" in ctx
        assert "SHOULD BE IGNORED" not in ctx

    def test_empty_memory_returns_empty(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path, memory_config=_CFG)
        assert store.get_memory_context() == ""


class TestConsolidateFoldsSummary:
    @pytest.mark.asyncio
    async def test_writes_summary_from_field(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path, memory_config=_CFG)
        provider = AsyncMock()
        provider.chat_with_retry = AsyncMock(
            return_value=_save_response(
                "[2026-01-01] talked",
                "# Memory\n" + _BIG,
                memory_summary="MY SUMMARY",
            )
        )
        ok = await store.consolidate(_messages(60), provider, "m")
        assert ok is True
        assert store.read_summary() == "MY SUMMARY"
        # meta hash matches the written memory → summary considered fresh
        assert store.read_meta()["summary_source_hash"] == store._content_hash(
            store.read_long_term()
        )
        assert "MY SUMMARY" in store.get_memory_context()

    @pytest.mark.asyncio
    async def test_falls_back_to_head_when_summary_omitted(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path, memory_config=_CFG)
        provider = AsyncMock()
        provider.chat_with_retry = AsyncMock(
            return_value=_save_response("[2026-01-01] talked", "# Memory\n" + _BIG)
        )
        ok = await store.consolidate(_messages(60), provider, "m")
        assert ok is True
        summary = store.read_summary()
        assert summary  # something was written
        from tokenmind.utils.helpers import estimate_text_tokens

        assert estimate_text_tokens(summary) <= _CFG.summary_max_tokens

    @pytest.mark.asyncio
    async def test_save_tool_advertises_summary_field(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path, memory_config=_CFG)
        provider = AsyncMock()
        provider.chat_with_retry = AsyncMock(
            return_value=_save_response("[2026-01-01] x", "# Memory\nx", "s")
        )
        await store.consolidate(_messages(60), provider, "m")
        _, kwargs = provider.chat_with_retry.await_args
        tool = kwargs["tools"][0]["function"]
        props = tool["parameters"]["properties"]
        assert "memory_summary" in props
        assert "memory_summary" in tool["parameters"]["required"]


class TestOutOfBandRefresh:
    """Hand-edited MEMORY.md triggers a gated background summary refresh."""

    def test_target_none_when_fresh(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path, memory_config=_CFG)
        store.write_long_term(_BIG)
        store.write_summary("S")
        store._update_meta(summary_source_hash=store._content_hash(_BIG))
        assert store.summary_refresh_target() is None

    def test_target_none_when_small(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path, memory_config=_CFG)
        store.write_long_term("small")  # under cap → injected raw, no summary
        assert store.summary_refresh_target() is None

    def test_target_set_when_stale_and_big(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path, memory_config=_CFG)
        store.write_long_term(_BIG)
        store.write_summary("OLD")
        store._update_meta(summary_source_hash="stale")
        assert store.summary_refresh_target() == store._content_hash(_BIG)

    def test_target_gated_after_attempt(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path, memory_config=_CFG)
        store.write_long_term(_BIG)
        store._summary_attempt_hash = store._content_hash(_BIG)
        assert store.summary_refresh_target() is None  # don't re-fire same content

    @pytest.mark.asyncio
    async def test_regenerate_summary_writes_and_stamps(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path, memory_config=_CFG)
        store.write_long_term(_BIG)
        provider = AsyncMock()
        provider.chat_with_retry = AsyncMock(
            return_value=LLMResponse(content="FRESH SUMMARY", tool_calls=[])
        )
        ok = await store.regenerate_summary(provider, "m")
        assert ok is True
        assert store.read_summary() == "FRESH SUMMARY"
        assert store.read_meta()["summary_source_hash"] == store._content_hash(_BIG)
        # Now fresh → no further refresh wanted
        assert store.summary_refresh_target() is None

    @pytest.mark.asyncio
    async def test_regenerate_empty_response_keeps_gate(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path, memory_config=_CFG)
        store.write_long_term(_BIG)
        provider = AsyncMock()
        provider.chat_with_retry = AsyncMock(
            return_value=LLMResponse(content="", tool_calls=[])
        )
        ok = await store.regenerate_summary(provider, "m")
        assert ok is False
        assert not store.summary_file.exists()
        # attempted hash set → won't spam retries for the same content
        assert store.summary_refresh_target() is None


class TestMaybePurify:
    @pytest.mark.asyncio
    async def test_noop_when_recently_purified(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path, memory_config=_CFG)
        store.write_long_term(_BIG)
        store._update_meta(last_purified_at=time.time())
        provider = AsyncMock()
        provider.chat_with_retry = AsyncMock()
        assert await store.maybe_purify(provider, "m") is False
        provider.chat_with_retry.assert_not_called()

    @pytest.mark.asyncio
    async def test_stamps_timer_when_under_cap(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path, memory_config=_CFG)
        store.write_long_term("small")  # under purify cap
        provider = AsyncMock()
        provider.chat_with_retry = AsyncMock()
        assert await store.maybe_purify(provider, "m") is False
        provider.chat_with_retry.assert_not_called()
        assert store.read_meta().get("last_purified_at", 0) > 0

    @pytest.mark.asyncio
    async def test_runs_when_over_cap(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path, memory_config=_CFG)
        store.write_long_term(_BIG)  # over purify cap, never purified
        provider = AsyncMock()
        provider.chat_with_retry = AsyncMock(
            return_value=_purify_response("# Memory\nSMALL CLEAN", memory_summary="S")
        )
        assert await store.maybe_purify(provider, "m") is True
        assert "SMALL CLEAN" in store.read_long_term()
        assert store.read_summary() == "S"
        assert store.read_meta().get("last_purified_at", 0) > 0

    @pytest.mark.asyncio
    async def test_disabled_when_interval_zero(self, tmp_path: Path) -> None:
        cfg = MemoryConfig(purify_interval_days=0)
        store = MemoryStore(tmp_path, memory_config=cfg)
        store.write_long_term(_BIG)
        provider = AsyncMock()
        provider.chat_with_retry = AsyncMock()
        assert await store.maybe_purify(provider, "m") is False
        provider.chat_with_retry.assert_not_called()
