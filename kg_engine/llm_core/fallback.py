"""Fallback chain with circuit breaker for LLM providers."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from kg_engine.llm_core.provider import LLMProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Track provider failures and prevent cascading calls.

    States:
    - closed: normal operation, requests pass through
    - open: provider is failing, requests blocked
    - half_open: after recovery timeout, allow one probe request
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._state = "closed"

    @property
    def state(self) -> str:
        if self._state == "open" and time.monotonic() - self._last_failure_time >= self._recovery_timeout:
            self._state = "half_open"
        return self._state

    def allow_request(self) -> bool:
        state = self.state
        return state in ("closed", "half_open")

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self._failure_threshold:
            self._state = "open"
            logger.warning(
                "Circuit breaker opened after %d failures (recovery in %.0fs)",
                self._failure_count, self._recovery_timeout,
            )

    @property
    def failure_count(self) -> int:
        return self._failure_count


class FallbackChain:
    """Try multiple LLM providers in order with circuit breaker protection.

    Usage::

        chain = FallbackChain([
            ("openai", openai_provider),
            ("vllm", vllm_provider),
        ])
        result = await chain.chat_stream_collected(messages)
    """

    def __init__(
        self,
        providers: list[tuple[str, LLMProvider]],
        circuit_breaker_threshold: int = 3,
        circuit_breaker_recovery: float = 60.0,
    ) -> None:
        self._providers = providers
        self._breakers = {
            name: CircuitBreaker(circuit_breaker_threshold, circuit_breaker_recovery)
            for name, _ in providers
        }

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream from the first available provider."""
        for name, provider in self._providers:
            breaker = self._breakers[name]
            if not breaker.allow_request():
                logger.debug("Skipping %s (circuit open)", name)
                continue
            try:
                async for chunk in provider.chat_stream(messages, **kwargs):
                    yield chunk
                breaker.record_success()
                return
            except Exception as exc:
                breaker.record_failure()
                logger.warning("Provider %s failed: %s", name, exc)
        logger.error("All providers in fallback chain failed")

    async def chat_stream_collected(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> str:
        """Collect streaming response from the first available provider."""
        chunks: list[str] = []
        async for chunk in self.chat_stream(messages, **kwargs):
            chunks.append(chunk)
        return "".join(chunks)

    def chat(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> str:
        """Sync chat from the first available provider."""
        for name, provider in self._providers:
            breaker = self._breakers[name]
            if not breaker.allow_request():
                continue
            try:
                result = provider.chat(messages, **kwargs)
                if result:
                    breaker.record_success()
                    return result
                breaker.record_failure()
            except Exception as exc:
                breaker.record_failure()
                logger.warning("Provider %s failed: %s", name, exc)
        logger.error("All providers in fallback chain failed")
        return ""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Sync embed from the first available provider."""
        for name, provider in self._providers:
            breaker = self._breakers[name]
            if not breaker.allow_request():
                continue
            try:
                result = provider.embed(texts)
                if result and result[0]:
                    breaker.record_success()
                    return result
                breaker.record_failure()
            except Exception as exc:
                breaker.record_failure()
                logger.warning("Provider %s embed failed: %s", name, exc)
        return [[] for _ in texts]

    def get_status(self) -> dict[str, Any]:
        """Return status of all providers in the chain."""
        return {
            name: {
                "state": self._breakers[name].state,
                "failures": self._breakers[name].failure_count,
            }
            for name, _ in self._providers
        }

    async def close(self) -> None:
        for _, provider in self._providers:
            await provider.aclose()
