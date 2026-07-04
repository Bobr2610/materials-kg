from __future__ import annotations

import pytest

from kg_engine.config.settings import Settings
from kg_engine.llm_core.provider import create_agent_chat_model_from_settings
from kg_engine.llm_core.provider import create_provider_from_settings
from kg_engine.llm_core.provider import resolve_chat_completions_cascade
from kg_engine.llm_core.provider import resolve_vision_completions_cascade
from kg_engine.llm_core.provider import LLMProvider


@pytest.fixture(autouse=True)
def _clear_cascade_env(monkeypatch) -> None:
    prefixes = ("LLM_CASCADE", "MATERIALS_VISION_CASCADE")
    for prefix in prefixes:
        monkeypatch.delenv(f"{prefix}_ENABLED", raising=False)
        for index in range(1, 9):
            for suffix in (
                "PROVIDER",
                "MODEL",
                "BASE_URL",
                "API_KEY",
                "EMBEDDING_MODEL",
            ):
                monkeypatch.delenv(f"{prefix}_{index}_{suffix}", raising=False)


def test_configured_provider_ignores_provider_specific_env(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PROVIDER_A_API_KEY", "provider-a-key")
    monkeypatch.setenv("PROVIDER_A_BASE_URL", "https://provider-a.example/api/v1")
    settings = Settings(
        default_llm_provider="provider-a",
        default_model="chat-a",
        default_embedding_model="embed-a",
        llm_api_key="generic-key",
        llm_base_url="https://generic.example/v1",
    )

    provider = create_provider_from_settings(settings)

    assert provider is not None
    assert provider.base_url == "https://generic.example"
    assert provider.api_key == "generic-key"
    assert provider.chat_model == "chat-a"
    assert provider.embedding_model == "embed-a"
    provider.close()


def test_configured_provider_can_use_generic_endpoint_settings() -> None:
    settings = Settings(
        default_llm_provider="any-provider",
        default_model="any-chat",
        default_embedding_model="any-embed",
        llm_api_key="generic-key",
        llm_base_url="https://generic.example/v1",
    )

    provider = create_provider_from_settings(settings)

    assert provider is not None
    assert provider.base_url == "https://generic.example"
    assert provider.api_key == "generic-key"
    assert provider.chat_model == "any-chat"
    assert provider.embedding_model == "any-embed"
    provider.close()


def test_empty_provider_does_not_auto_detect_spare_keys() -> None:
    settings = Settings(
        default_llm_provider="",
        default_model="chat",
        default_embedding_model="embed",
        llm_api_key="generic-key",
        llm_base_url="https://generic.example/v1",
    )

    assert create_provider_from_settings(settings) is None


def test_agent_provider_alias_selects_provider_when_default_is_empty(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENT_PROVIDER", "provider-b")
    monkeypatch.setenv("AGENT_DEFAULT_MODEL", "agent-chat")
    monkeypatch.setenv("PROVIDER_B_API_KEY", "provider-b-key")
    monkeypatch.setenv("PROVIDER_B_BASE_URL", "https://provider-b.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "generic-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://generic-agent.example/v1")
    settings = Settings(
        default_llm_provider="",
        default_model="",
        default_embedding_model="agent-embed",
    )

    provider = create_provider_from_settings(settings)

    assert provider is not None
    assert provider.base_url == "https://generic-agent.example"
    assert provider.api_key == "generic-key"
    assert provider.chat_model == "agent-chat"
    provider.close()


def test_configured_provider_without_endpoint_returns_none() -> None:
    settings = Settings(
        default_llm_provider="provider-c",
        default_model="chat-c",
        llm_api_key="",
        llm_base_url="",
    )

    assert create_provider_from_settings(settings) is None


def test_agent_chat_model_uses_generic_provider_config(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "any-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://any-provider.example/v1")
    settings = Settings(
        default_llm_provider="any-provider",
        default_model="any-model",
    )

    _model, label = create_agent_chat_model_from_settings(settings)

    assert label == "any-provider:any-model"


def test_cascade_skips_incomplete_yandex_and_keeps_openrouter_priority() -> None:
    settings = Settings(
        llm_cascade_enabled=True,
        llm_cascade_1_provider="yandex",
        llm_cascade_1_model="deepseek-v4-flash",
        llm_cascade_1_base_url="",
        llm_cascade_1_api_key="",
        llm_cascade_2_provider="openrouter",
        llm_cascade_2_model="google/gemma-4-31b-it:free",
        llm_cascade_2_base_url="https://openrouter.ai/api",
        llm_cascade_2_api_key="openrouter-key",
        llm_cascade_3_provider="openrouter",
        llm_cascade_3_model="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        llm_cascade_3_base_url="https://openrouter.ai/api",
        llm_cascade_3_api_key="openrouter-key",
    )

    configs = resolve_chat_completions_cascade(settings)
    provider = create_provider_from_settings(settings)

    assert [config.chat_model for config in configs] == [
        "google/gemma-4-31b-it:free",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    ]
    assert provider is not None
    assert list(provider.get_status()) == [
        "openrouter:google/gemma-4-31b-it:free",
        "openrouter:nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    ]


def test_agent_chat_model_reports_cascade_label() -> None:
    settings = Settings(
        llm_cascade_enabled=True,
        llm_cascade_1_provider="yandex",
        llm_cascade_1_model="deepseek-v4-flash",
        llm_cascade_1_base_url="https://yandex.example/api",
        llm_cascade_1_api_key="yandex-key",
        llm_cascade_2_provider="openrouter",
        llm_cascade_2_model="google/gemma-4-31b-it:free",
        llm_cascade_2_base_url="https://openrouter.ai/api",
        llm_cascade_2_api_key="openrouter-key",
    )

    _model, label = create_agent_chat_model_from_settings(settings)

    assert label == (
        "cascade:yandex:deepseek-v4-flash>"
        "openrouter:google/gemma-4-31b-it:free"
    )


def test_vision_cascade_uses_dedicated_priority_order() -> None:
    settings = Settings(
        materials_vision_cascade_enabled=True,
        materials_vision_cascade_1_provider="yandex",
        materials_vision_cascade_1_model="qwen3.6-35b-a3b",
        materials_vision_cascade_1_base_url="",
        materials_vision_cascade_1_api_key="",
        materials_vision_cascade_2_provider="openrouter",
        materials_vision_cascade_2_model="google/gemma-4-31b-it:free",
        materials_vision_cascade_2_base_url="https://openrouter.ai/api",
        materials_vision_cascade_2_api_key="openrouter-key",
        materials_vision_cascade_3_provider="openrouter",
        materials_vision_cascade_3_model=(
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
        ),
        materials_vision_cascade_3_base_url="https://openrouter.ai/api",
        materials_vision_cascade_3_api_key="openrouter-key",
    )

    configs = resolve_vision_completions_cascade(settings)

    assert [config.chat_model for config in configs] == [
        "google/gemma-4-31b-it:free",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    ]


def test_agent_chat_model_supports_bind_tools() -> None:
    settings = Settings(
        llm_cascade_enabled=True,
        llm_cascade_1_provider="openrouter",
        llm_cascade_1_model="google/gemma-4-31b-it:free",
        llm_cascade_1_base_url="https://openrouter.ai/api",
        llm_cascade_1_api_key="test-key",
    )

    model, _label = create_agent_chat_model_from_settings(settings)
    bound = model.bind_tools(
        [
            {
                "type": "function",
                "function": {
                    "name": "kg_search",
                    "description": "Search graph evidence",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            }
        ]
    )

    assert bound is not None
    # bind_tools should not raise NotImplementedError
    assert hasattr(bound, "invoke")
