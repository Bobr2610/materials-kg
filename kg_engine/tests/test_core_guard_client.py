"""Tests for GuardClient."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from kg_engine.core.guard_client import GuardClient


@pytest.fixture(autouse=True)
def _patch_settings():
    """Provide minimal settings values needed by GuardClient."""
    mock_settings = MagicMock()
    mock_settings.guard_provider_type = "mosec"
    mock_settings.guard_timeout = 5.0
    mock_settings.guard_max_retries = 2
    mock_settings.guard_mosec_endpoint = "http://localhost:8000/moderate"
    mock_settings.guard_vllm_url = "http://localhost:8001/v1"
    mock_settings.guard_vllm_model = "Qwen3Guard"
    mock_settings.guard_block_threshold = "unsafe"
    with patch("kg_engine.core.guard_client.settings", mock_settings):
        yield mock_settings


class TestGuardClientInit:
    def test_default_provider(self) -> None:
        client = GuardClient()
        assert client._provider_type == "mosec"

    def test_override_provider(self) -> None:
        client = GuardClient(provider_type="vllm")
        assert client._provider_type == "vllm"

    def test_invalid_provider_raises(self, _patch_settings) -> None:
        _patch_settings.guard_provider_type = "invalid"
        with pytest.raises(ValueError, match="Invalid GUARD_PROVIDER_TYPE"):
            GuardClient()


class TestClassifyMosec:
    @pytest.mark.asyncio
    async def test_successful_classification(self, _patch_settings) -> None:
        result = {"safety_level": "Safe", "categories": [], "is_safe": True}
        mock_resp = MagicMock()
        mock_resp.json.return_value = result
        mock_resp.raise_for_status = MagicMock()

        with patch("kg_engine.core.guard_client.requests") as mock_requests:
            mock_requests.post.return_value = mock_resp
            mock_requests.RequestException = Exception
            client = GuardClient()
            out = await client.classify("hello")

        assert out["safety_level"] == "Safe"
        assert out["provider"] == "mosec"

    @pytest.mark.asyncio
    async def test_retries_on_failure(self, _patch_settings) -> None:
        import requests as _req

        with patch("kg_engine.core.guard_client.requests") as mock_requests:
            mock_requests.post.side_effect = _req.ConnectionError("fail")
            mock_requests.RequestException = _req.ConnectionError
            client = GuardClient(max_retries=2)
            with pytest.raises(_req.ConnectionError):
                await client.classify("bad input")
            assert mock_requests.post.call_count == 2


class TestIsSafe:
    def test_safe_result(self) -> None:
        client = GuardClient()
        assert client.is_safe({"safety_level": "Safe", "is_safe": True}) is True

    def test_unsafe_result(self) -> None:
        client = GuardClient()
        assert client.is_safe({"safety_level": "Unsafe", "is_safe": False}) is False

    def test_empty_result(self) -> None:
        client = GuardClient()
        assert client.is_safe({}) is True

    def test_none_result(self) -> None:
        client = GuardClient()
        assert client.is_safe(None) is True  # type: ignore[arg-type]


class TestGetSafetyLevel:
    def test_returns_level(self) -> None:
        client = GuardClient()
        assert client.get_safety_level({"safety_level": "Controversial"}) == "Controversial"

    def test_missing_returns_safe(self) -> None:
        client = GuardClient()
        assert client.get_safety_level({}) == "Safe"


class TestGetCategories:
    def test_returns_categories(self) -> None:
        client = GuardClient()
        result = {"categories": ["Violent", "PII"]}
        assert client.get_categories(result) == ["Violent", "PII"]

    def test_empty_returns_empty(self) -> None:
        client = GuardClient()
        assert client.get_categories({}) == []


class TestShouldBlock:
    def test_blocks_unsafe(self, _patch_settings) -> None:
        _patch_settings.guard_block_threshold = "unsafe"
        client = GuardClient()
        assert client.should_block({"safety_level": "Unsafe"}) is True

    def test_safe_not_blocked(self, _patch_settings) -> None:
        _patch_settings.guard_block_threshold = "unsafe"
        client = GuardClient()
        assert client.should_block({"safety_level": "Safe"}) is False

    def test_controversial_blocked_when_threshold_controversial(self, _patch_settings) -> None:
        _patch_settings.guard_block_threshold = "controversial"
        client = GuardClient()
        assert client.should_block({"safety_level": "Controversial"}) is True

    def test_empty_not_blocked(self, _patch_settings) -> None:
        client = GuardClient()
        assert client.should_block({}) is False
