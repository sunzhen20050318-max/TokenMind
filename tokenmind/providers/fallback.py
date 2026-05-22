"""Provider wrapper that transparently fails over to fallback models on error.

When a primary model returns a fatal error (`finish_reason == "error"`),
the wrapper transparently retries the request against each model in
`fallback_models` until one succeeds or all are exhausted. A simple
circuit breaker pauses the primary after N consecutive failures so a
flapping endpoint doesn't slow every request.

National providers (Moonshot / MiniMax / DashScope / Zhipu) are often
the first to rate-limit during peak hours — a single line of config
turns that from "conversation broken" into "this turn used a backup
model, please proceed". Adapted from nanobot's design (HKUDS/nanobot
913b077) to TokenMind's non-streaming provider interface.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from tokenmind.providers.base import GenerationSettings, LLMProvider, LLMResponse

# Trip the primary after this many consecutive `finish_reason="error"`
# responses to stop wasting turns on a known-bad endpoint.
_PRIMARY_FAILURE_THRESHOLD = 3
# How long the primary stays "tripped" before we probe it again.
_PRIMARY_COOLDOWN_S = 60.0


ProviderFactory = Callable[[str], LLMProvider]


class FallbackProvider(LLMProvider):
    """Wrap a primary :class:`LLMProvider` with ordered failover.

    Parameters
    ----------
    primary
        The provider used for every request that the primary endpoint can
        actually fulfil.
    fallback_models
        Ordered list of fully-qualified model strings (e.g.
        ``"deepseek/deepseek-chat"``, ``"anthropic/claude-haiku-4-5"``).
        Each entry is materialised on demand via ``provider_factory``.
    provider_factory
        Callable that turns a model string into a concrete
        :class:`LLMProvider`. Typically wraps the CLI's existing
        ``_make_provider`` helper so the same provider-detection logic
        (model prefix → provider name → spec) applies to fallbacks.
    """

    def __init__(
        self,
        primary: LLMProvider,
        fallback_models: list[str],
        provider_factory: ProviderFactory,
    ) -> None:
        self._primary = primary
        self._fallback_models = list(fallback_models)
        self._provider_factory = provider_factory
        self._primary_failures = 0
        self._primary_tripped_at: float | None = None

    # ── LLMProvider passthroughs ─────────────────────────────────────────
    def get_default_model(self) -> str:
        return self._primary.get_default_model()

    @property
    def generation(self) -> GenerationSettings:
        return self._primary.generation

    @generation.setter
    def generation(self, value: GenerationSettings) -> None:
        self._primary.generation = value

    # ── circuit breaker helpers ──────────────────────────────────────────
    def _primary_available(self) -> bool:
        if self._primary_tripped_at is None:
            return True
        # After the cooldown elapses, allow a probe attempt (half-open).
        return time.monotonic() - self._primary_tripped_at >= _PRIMARY_COOLDOWN_S

    def _record_primary_failure(self, primary_model: str) -> None:
        self._primary_failures += 1
        if self._primary_failures >= _PRIMARY_FAILURE_THRESHOLD:
            self._primary_tripped_at = time.monotonic()
            logger.warning(
                "Primary model '{}' circuit open after {} consecutive failures "
                "— pausing for {}s",
                primary_model,
                self._primary_failures,
                _PRIMARY_COOLDOWN_S,
            )

    def _record_primary_success(self) -> None:
        self._primary_failures = 0
        self._primary_tripped_at = None

    # ── chat ─────────────────────────────────────────────────────────────
    async def chat(self, **kwargs: Any) -> LLMResponse:
        if not self._fallback_models:
            return await self._primary.chat(**kwargs)

        primary_model = kwargs.get("model") or self._primary.get_default_model()

        # Step 1: try primary (unless circuit is open).
        if self._primary_available():
            response = await self._primary.chat(**kwargs)
            if response.finish_reason != "error":
                self._record_primary_success()
                return response
            logger.warning(
                "Primary model '{}' failed: {}",
                primary_model,
                (response.content or "")[:160],
            )
            self._record_primary_failure(primary_model)
        else:
            logger.debug("Primary model '{}' circuit open; skipping", primary_model)

        # Step 2: walk the fallback list in order.
        last_response: LLMResponse | None = None
        for idx, fallback_model in enumerate(self._fallback_models):
            if idx == 0:
                logger.info(
                    "Failing over to backup model '{}'", fallback_model,
                )
            else:
                logger.info(
                    "Backup '{}' also failed, trying next backup '{}'",
                    self._fallback_models[idx - 1], fallback_model,
                )
            try:
                fallback_provider = self._provider_factory(fallback_model)
            except Exception as exc:
                logger.warning(
                    "Failed to construct provider for '{}': {}", fallback_model, exc,
                )
                continue

            original_model = kwargs.get("model")
            kwargs["model"] = fallback_model
            try:
                fallback_response = await fallback_provider.chat(**kwargs)
            finally:
                if original_model is None:
                    kwargs.pop("model", None)
                else:
                    kwargs["model"] = original_model

            if fallback_response.finish_reason != "error":
                logger.info(
                    "Backup model '{}' succeeded after primary '{}' failed",
                    fallback_model, primary_model,
                )
                return fallback_response

            last_response = fallback_response
            logger.warning(
                "Backup '{}' also failed: {}",
                fallback_model,
                (fallback_response.content or "")[:160],
            )

        # All exhausted — return the last error so the caller still sees a
        # message instead of an exception trace.
        if last_response is not None:
            return last_response
        return LLMResponse(
            content=(
                f"Primary model '{primary_model}' circuit open and no usable "
                "backup models available."
            ),
            finish_reason="error",
        )
