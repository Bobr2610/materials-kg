"""Tests for VLLMGuardAdapter."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from kg_engine.core.vllm_guard_adapter import VLLMGuardAdapter


@pytest.fixture(autouse=True)
def _patch_settings():
    mock_settings = MagicMock()
    mock_settings.guard_vllm_model = "Qwen3Guard-8B"
    mock_settings.guard_vllm_url = "http://localhost:8001/v1"
    mock_settings.guard_timeout = 10.0
    with patch("kg_engine.core.vllm_guard_adapter.settings", mock_settings):
        yield mock_settings


class TestParseSafetyLevel:
    def test_safe(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter._parse_safety_level("Safety: Safe") == "Safe"

    def test_unsafe(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter._parse_safety_level("Safety: Unsafe") == "Unsafe"

    def test_controversial(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter._parse_safety_level("Safety: controversial") == "Controversial"

    def test_unknown_when_missing(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter._parse_safety_level("no safety info") == "Unknown"

    def test_case_insensitive(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter._parse_safety_level("safety: SAFE") == "Safe"


class TestParseCategories:
    def test_single_category(self) -> None:
        adapter = VLLMGuardAdapter()
        result = adapter._parse_categories("Categories: Violent")
        assert result == ["Violent"]

    def test_multiple_categories(self) -> None:
        adapter = VLLMGuardAdapter()
        text = "Safety: Unsafe\nCategories: Violent, PII"
        result = adapter._parse_categories(text)
        assert "Violent" in result
        assert "PII" in result

    def test_none_category(self) -> None:
        adapter = VLLMGuardAdapter()
        result = adapter._parse_categories("Safety: Safe\nCategories: None")
        assert result == ["None"]

    def test_no_match_returns_none(self) -> None:
        adapter = VLLMGuardAdapter()
        result = adapter._parse_categories("Safety: Safe")
        assert result == ["None"]


class TestParseRefusal:
    def test_yes(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter._parse_refusal("Refusal: Yes") == "Yes"

    def test_no(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter._parse_refusal("Refusal: No") == "No"

    def test_missing(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter._parse_refusal("Safety: Safe") is None


class TestBuildPrompt:
    def test_prompt_mode(self) -> None:
        adapter = VLLMGuardAdapter()
        messages = adapter._build_prompt("hello", moderation_type="prompt")
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "hello"

    def test_response_mode_with_context(self) -> None:
        adapter = VLLMGuardAdapter()
        messages = adapter._build_prompt(
            "response text", context="user question", moderation_type="response",
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    def test_response_mode_without_context(self) -> None:
        adapter = VLLMGuardAdapter()
        messages = adapter._build_prompt("content", moderation_type="response")
        assert len(messages) == 1


class TestConvertToMosecFormat:
    def test_safe_output(self) -> None:
        adapter = VLLMGuardAdapter()
        raw = "Safety: Safe\nRefusal: No\nCategories: None"
        result = adapter._convert_to_mosec_format(raw, "model")
        assert result["safety_level"] == "Safe"
        assert result["is_safe"] is True
        assert result["provider"] == "vllm"
        assert result["model"] == "model"
        assert result["raw_output"] == raw

    def test_unsafe_output(self) -> None:
        adapter = VLLMGuardAdapter()
        raw = "Safety: Unsafe\nRefusal: Yes\nCategories: Violent"
        result = adapter._convert_to_mosec_format(raw, "m")
        assert result["safety_level"] == "Unsafe"
        assert result["is_safe"] is False
        assert result["refusal"] == "Yes"


class TestIsSafe:
    def test_safe(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter.is_safe({"safety_level": "Safe", "is_safe": True}) is True

    def test_unsafe(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter.is_safe({"safety_level": "Unsafe", "is_safe": False}) is False

    def test_empty(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter.is_safe({}) is True

    def test_none(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter.is_safe(None) is True  # type: ignore[arg-type]


class TestGetSafetyLevel:
    def test_returns_level(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter.get_safety_level({"safety_level": "Unsafe"}) == "Unsafe"

    def test_missing_returns_unknown(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter.get_safety_level({}) == "Unknown"


class TestGetCategories:
    def test_returns_list(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter.get_categories({"categories": ["PII"]}) == ["PII"]

    def test_missing_returns_none_list(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter.get_categories({}) == ["None"]


class TestShouldBlock:
    def test_blocks_unsafe(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter.should_block({"safety_level": "Unsafe"}) is True

    def test_safe_not_blocked(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter.should_block({"safety_level": "Safe"}) is False

    def test_empty_not_blocked(self) -> None:
        adapter = VLLMGuardAdapter()
        assert adapter.should_block({}) is False


class TestClassify:
    @pytest.mark.asyncio
    async def test_classify_calls_api(self) -> None:
        mock_message = MagicMock()
        mock_message.content = "Safety: Safe\nRefusal: No\nCategories: None"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        adapter = VLLMGuardAdapter()
        adapter._client = mock_client

        result = await adapter.classify("hello world")
        assert result["safety_level"] == "Safe"
        assert result["is_safe"] is True
        assert result["provider"] == "vllm"
        mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_classify_returns_safe_fallback_on_error(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("connection lost")

        adapter = VLLMGuardAdapter()
        adapter._client = mock_client

        result = await adapter.classify("test")
        assert result["is_safe"] is True
        assert result["safety_level"] == "Unknown"
        assert "Error:" in result["raw_output"]
