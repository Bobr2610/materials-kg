"""VLLM Guardian Adapter for Qwen3Guard models.

This adapter provides a unified interface for content moderation using VLLM-served
Qwen3Guard models. It parses raw text output from VLLM's OpenAI-compatible API
and converts it to the same JSON structure as MOSEC guardian.

Usage:
    from kg_engine.core.vllm_guard_adapter import VLLMGuardAdapter

    adapter = VLLMGuardAdapter()
    result = await adapter.classify("How can I make a bomb?")
    # Returns: {"safety_level": "Unsafe", "categories": ["Violent"], ...}
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import openai

from kg_engine.config.settings import settings

logger = logging.getLogger(__name__)


class VLLMGuardAdapter:
    """Adapter for VLLM-served Qwen3Guard models.

    Converts raw text output from VLLM/OpenAI-compatible API to structured
    JSON format matching MOSEC guardian output.
    """

    # Safety levels from Qwen3Guard documentation
    SAFETY_LEVELS = ["Safe", "Unsafe", "Controversial"]

    # Safety categories from Qwen3Guard documentation
    SAFETY_CATEGORIES = [
        "Violent",
        "Non-violent Illegal Acts",
        "Sexual Content or Sexual Acts",
        "PII",
        "Suicide & Self-Harm",
        "Unethical Acts",
        "Politically Sensitive Topics",
        "Copyright Violation",
        "Jailbreak",
        "None",
    ]

    def __init__(self) -> None:
        """Initialize the VLLM guard adapter."""
        self._client: openai.OpenAI | None = None
        self._model_name = settings.guard_vllm_model
        self._base_url = settings.guard_vllm_url
        self._timeout = settings.guard_timeout

    def _get_client(self) -> openai.OpenAI:
        """Get or create OpenAI client for VLLM server."""
        if self._client is None:
            self._client = openai.OpenAI(
                base_url=self._base_url,
                api_key="EMPTY",  # VLLM doesn't require auth
                timeout=self._timeout,
            )
        return self._client

    def _parse_safety_level(self, content: str) -> str:
        """Extract safety level from raw output.

        Args:
            content: Raw text output from guard model

        Returns:
            Safety level: "Safe", "Unsafe", "Controversial", or "Unknown"
        """
        pattern = r"Safety:\s*(Safe|Unsafe|Controversial)"
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return match.group(1).capitalize()
        return "Unknown"

    def _parse_categories(self, content: str) -> list[str]:
        """Extract safety categories from raw output.

        Args:
            content: Raw text output from guard model

        Returns:
            List of matched categories
        """
        # Build pattern from known categories
        escaped_categories = [re.escape(cat) for cat in self.SAFETY_CATEGORIES]
        pattern = "(" + "|".join(escaped_categories) + ")"

        matches = re.findall(pattern, content, re.IGNORECASE)

        # Normalize to official category names
        normalized = []
        for match in matches:
            for official in self.SAFETY_CATEGORIES:
                if official.lower() == match.lower():
                    normalized.append(official)
                    break
            else:
                # Keep unmatched but capitalize
                normalized.append(match.capitalize())

        return normalized if normalized else ["None"]

    def _parse_refusal(self, content: str) -> str | None:
        """Extract refusal indicator from raw output.

        Args:
            content: Raw text output from guard model

        Returns:
            "Yes", "No", or None if not found
        """
        pattern = r"Refusal:\s*(Yes|No)"
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return match.group(1).capitalize()
        return None

    def _build_prompt(
        self,
        content: str,
        context: str | None = None,
        moderation_type: str = "prompt",
    ) -> list[dict[str, str]]:
        """Build chat messages for guard model.

        Args:
            content: Content to moderate
            context: Optional context (for response moderation)
            moderation_type: "prompt" or "response"

        Returns:
            List of message dicts for chat completion
        """
        if moderation_type == "response" and context:
            return [
                {"role": "user", "content": context},
                {"role": "assistant", "content": content},
            ]
        else:
            return [{"role": "user", "content": content}]

    def _convert_to_mosec_format(
        self,
        raw_output: str,
        model_name: str,
    ) -> dict[str, Any]:
        """Convert raw VLLM output to MOSEC-compatible JSON format.

        Args:
            raw_output: Raw text from VLLM model
            model_name: Name of the guard model used

        Returns:
            Dictionary matching MOSEC output structure
        """
        safety_level = self._parse_safety_level(raw_output)
        categories = self._parse_categories(raw_output)
        refusal = self._parse_refusal(raw_output)

        return {
            "safety_level": safety_level,
            "categories": categories,
            "refusal": refusal,
            "is_safe": safety_level == "Safe",
            "raw_output": raw_output,
            "model": model_name,
            "provider": "vllm",
        }

    async def classify(
        self,
        content: str,
        context: str | None = None,
        moderation_type: str = "prompt",
    ) -> dict[str, Any]:
        """Classify content using VLLM-served guard model.

        Args:
            content: Content to moderate
            context: Optional context for response moderation
            moderation_type: "prompt" or "response"

        Returns:
            Dictionary with safety assessment matching MOSEC format:
            {
                "safety_level": "Safe" | "Unsafe" | "Controversial",
                "categories": ["Violent", ...],
                "refusal": "Yes" | "No" | None,
                "is_safe": bool,
                "raw_output": str,
                "model": str,
                "provider": "vllm",
            }
        """
        client = self._get_client()
        messages = self._build_prompt(content, context, moderation_type)

        try:
            response = client.chat.completions.create(
                model=self._model_name,
                messages=messages,
                max_tokens=128,
                temperature=0,
            )

            raw_output = response.choices[0].message.content
            logger.debug("VLLM guard raw output: %s", raw_output)

            return self._convert_to_mosec_format(raw_output, self._model_name)

        except Exception as exc:
            logger.error("VLLM guard classification failed: %s", exc)
            # Return safe fallback on error to avoid blocking legitimate requests
            return {
                "safety_level": "Unknown",
                "categories": ["None"],
                "refusal": None,
                "is_safe": True,
                "raw_output": f"Error: {exc}",
                "model": self._model_name,
                "provider": "vllm",
            }

    def is_safe(self, result: dict[str, Any]) -> bool:
        """Check if content is safe based on classification result.

        Args:
            result: Classification result from classify()

        Returns:
            True if content is safe
        """
        if not result:
            return True
        return result.get("safety_level") == "Safe" and result.get("is_safe", True)

    def get_safety_level(self, result: dict[str, Any]) -> str:
        """Extract safety level from result.

        Args:
            result: Classification result from classify()

        Returns:
            Safety level string
        """
        return result.get("safety_level", "Unknown") if result else "Unknown"

    def get_categories(self, result: dict[str, Any]) -> list[str]:
        """Extract categories from result.

        Args:
            result: Classification result from classify()

        Returns:
            List of category strings
        """
        return result.get("categories", ["None"]) if result else ["None"]

    def should_block(self, result: dict[str, Any]) -> bool:
        """Check if content should be blocked.

        Args:
            result: Classification result from classify()

        Returns:
            True if content should be blocked (Unsafe)
        """
        if not result:
            return False
        return result.get("safety_level") == "Unsafe"
