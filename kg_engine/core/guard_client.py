"""Guardian client for content moderation.

Provides unified interface for content moderation supporting multiple providers:
- mosec: HTTP server via MOSEC (native JSON output)
- vllm: VLLM-served Qwen3Guard models (raw text output, parsed to JSON)

Both providers return identical JSON structure for seamless interchangeability.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests

from kg_engine.config.settings import settings
from kg_engine.core.vllm_guard_adapter import VLLMGuardAdapter

logger = logging.getLogger(__name__)


class GuardClient:
    """Unified content moderation client supporting MOSEC and VLLM providers.

    Attributes:
        provider_type: Type of provider ("mosec" or "vllm")
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts on failure
    """

    SUPPORTED_PROVIDERS = ["mosec", "vllm"]

    def __init__(
        self,
        provider_type: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        """Initialize the guard client.

        Args:
            provider_type: Override for provider type (defaults to settings)
            timeout: Override for timeout (defaults to settings)
            max_retries: Override for max retries (defaults to settings)
        """
        self._provider_type = provider_type or settings.guard_provider_type
        self._timeout = timeout or settings.guard_timeout
        self._max_retries = max_retries or settings.guard_max_retries
        self._executor = ThreadPoolExecutor(max_workers=2)

        # Initialize VLLM adapter if needed
        self._vllm_adapter: VLLMGuardAdapter | None = None

        # Validate provider type - fail explicitly on invalid configuration
        if self._provider_type not in self.SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Invalid GUARD_PROVIDER_TYPE: '{self._provider_type}'. "
                f"Must be one of: {', '.join(self.SUPPORTED_PROVIDERS)}. "
                f"Please check your .env configuration."
            )

    def _get_vllm_adapter(self) -> VLLMGuardAdapter:
        """Get or create VLLM guard adapter."""
        if self._vllm_adapter is None:
            self._vllm_adapter = VLLMGuardAdapter()
        return self._vllm_adapter

    def _classify_mosec(self, content: str) -> dict[str, Any]:
        """Classify content via Mosec HTTP server.

        Args:
            content: User message to classify

        Returns:
            Dict with safety_level, categories, is_safe, etc.
        """
        url = settings.guard_mosec_endpoint
        payload = {"content": content, "moderation_type": "prompt"}

        last_error = None
        for attempt in range(self._max_retries):
            try:
                response = requests.post(url, json=payload, timeout=self._timeout)
                response.raise_for_status()
                result = response.json()
                # Mark result with provider for debugging
                result["provider"] = "mosec"
                return result
            except requests.RequestException as exc:
                last_error = exc
                logger.warning(
                    "Mosec classification attempt %d/%d failed: %s",
                    attempt + 1,
                    self._max_retries,
                    exc,
                )

        raise last_error

    async def _classify_vllm(self, content: str) -> dict[str, Any]:
        """Classify content via VLLM using the adapter.

        Args:
            content: User message to classify

        Returns:
            Dict with safety_level, categories, is_safe, etc.
        """
        adapter = self._get_vllm_adapter()
        # Run synchronous adapter in executor
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: asyncio.run(adapter.classify(content)),
        )

    async def classify(self, content: str) -> dict[str, Any]:
        """Classify content for safety using configured provider.

        Args:
            content: User message to classify

        Returns:
            Dict with:
            - safety_level: "Safe" | "Controversial" | "Unsafe"
            - categories: list[str]
            - is_safe: bool
            - refusal: "Yes" | "No" | None
            - raw_output: str (original response)
            - provider: "mosec" | "vllm"
        """
        if self._provider_type == "mosec":
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self._executor,
                lambda: self._classify_mosec(content),
            )
        elif self._provider_type == "vllm":
            return await self._classify_vllm(content)
        else:
            # Should never reach here due to validation in __init__
            raise ValueError(f"Unsupported provider: {self._provider_type}")

    def is_safe(self, result: dict[str, Any]) -> bool:
        """Check if content is safe based on moderation result.

        Args:
            result: Response from classify() method

        Returns:
            True if content is safe, False otherwise
        """
        if not result:
            return True
        safety_level = result.get("safety_level", "")
        is_safe_flag = result.get("is_safe", True)
        return safety_level == "Safe" and is_safe_flag

    def get_safety_level(self, result: dict[str, Any]) -> str:
        """Extract safety level from moderation result.

        Args:
            result: Response from classify() method

        Returns:
            Safety level string: "Safe" | "Controversial" | "Unsafe"
        """
        return result.get("safety_level", "Safe") if result else "Safe"

    def get_categories(self, result: dict[str, Any]) -> list[str]:
        """Extract categories from moderation result.

        Args:
            result: Response from classify() method

        Returns:
            List of category strings
        """
        return result.get("categories", []) if result else []

    def should_block(self, result: dict[str, Any]) -> bool:
        """Check if content should be blocked (enforce mode).

        Args:
            result: Response from classify() method

        Returns:
            True if content should be blocked based on threshold
        """
        if not result:
            return False

        from kg_engine.config.settings import settings

        threshold = getattr(settings, "guard_block_threshold", "unsafe")
        safety_level = result.get("safety_level", "Safe")

        if threshold == "controversial":
            return safety_level in ("Unsafe", "Controversial")
        return safety_level == "Unsafe"


guard_client: GuardClient | None = None


def get_guard_client() -> GuardClient:
    global guard_client  # noqa: PLW0603
    if guard_client is None:
        guard_client = GuardClient()
    return guard_client
