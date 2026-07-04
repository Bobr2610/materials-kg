from __future__ import annotations

from kg_engine.config.settings import Settings
from kg_engine.llm_core.provider import create_agent_chat_model_from_settings
from kg_engine.llm_core.provider import create_provider_from_settings


def test_configured_provider_uses_matching_env_without_builtin_shortcuts(
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
    assert provider.base_url == "https://provider-a.example/api"
    assert provider.api_key == "provider-a-key"
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
    settings = Settings(
        default_llm_provider="",
        default_model="",
        default_embedding_model="agent-embed",
    )

    provider = create_provider_from_settings(settings)

    assert provider is not None
    assert provider.base_url == "https://provider-b.example"
    assert provider.api_key == "provider-b-key"
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
    monkeypatch.setenv("ANY_PROVIDER_API_KEY", "any-key")
    monkeypatch.setenv("ANY_PROVIDER_BASE_URL", "https://any-provider.example/v1")
    settings = Settings(
        default_llm_provider="any-provider",
        default_model="any-model",
    )

    _model, label = create_agent_chat_model_from_settings(settings)

    assert label == "any-provider:any-model"
