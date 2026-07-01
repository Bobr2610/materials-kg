from __future__ import annotations

from kg_engine.config.settings import Settings
from kg_engine.llm_core.provider import create_langchain_chat_model_from_settings
from kg_engine.llm_core.provider import create_provider_from_settings


def test_configured_openrouter_provider_wins_over_other_available_keys() -> None:
    settings = Settings(
        default_llm_provider="openrouter",
        default_model="qwen/qwen3-235b-a22b",
        default_embedding_model="openai/text-embedding-3-small",
        openai_api_key="openai-key",
        openrouter_api_key="openrouter-key",
        openrouter_base_url="https://openrouter.example/api/v1",
    )

    provider = create_provider_from_settings(settings)

    assert provider is not None
    assert provider.base_url == "https://openrouter.example/api"
    assert provider.api_key == "openrouter-key"
    assert provider.chat_model == "qwen/qwen3-235b-a22b"
    assert provider.embedding_model == "openai/text-embedding-3-small"
    provider.close()


def test_configured_vllm_provider_is_used_when_selected() -> None:
    settings = Settings(
        default_llm_provider="vllm",
        default_model="Qwen/Qwen3-14B",
        default_embedding_model="Qwen/Qwen3-Embedding-0.6B",
        openai_api_key="openai-key",
        vllm_base_url="http://127.0.0.1:8001/v1",
        vllm_api_key="vllm-key",
    )

    provider = create_provider_from_settings(settings)

    assert provider is not None
    assert provider.base_url == "http://127.0.0.1:8001"
    assert provider.api_key == "vllm-key"
    assert provider.chat_model == "Qwen/Qwen3-14B"
    provider.close()


def test_configured_polza_provider_is_openai_compatible() -> None:
    settings = Settings(
        default_llm_provider="polza",
        default_model="x-ai/grok-4.20",
        default_embedding_model="openai/text-embedding-3-small",
        openai_api_key="openai-key",
        polza_api_key="polza-key",
        polza_base_url="https://polza.example/api/v1",
    )

    provider = create_provider_from_settings(settings)

    assert provider is not None
    assert provider.base_url == "https://polza.example/api"
    assert provider.api_key == "polza-key"
    assert provider.chat_model == "x-ai/grok-4.20"
    provider.close()


def test_configured_groq_provider_is_openai_compatible() -> None:
    settings = Settings(
        default_llm_provider="groq",
        default_model="groq/compound",
        groq_api_key="groq-key",
        groq_base_url="https://api.groq.com/openai/v1",
    )

    provider = create_provider_from_settings(settings)

    assert provider is not None
    assert provider.base_url == "https://api.groq.com/openai"
    assert provider.api_key == "groq-key"
    assert provider.chat_model == "groq/compound"
    provider.close()


def test_configured_mistral_provider_is_openai_compatible() -> None:
    settings = Settings(
        default_llm_provider="mistral",
        default_model="mistral-large-latest",
        mistral_api_key="mistral-key",
    )

    provider = create_provider_from_settings(settings)

    assert provider is not None
    assert provider.base_url == "https://api.mistral.ai"
    assert provider.api_key == "mistral-key"
    assert provider.chat_model == "mistral-large-latest"
    provider.close()


def test_empty_provider_keeps_legacy_auto_detection_order() -> None:
    settings = Settings(
        default_llm_provider="",
        default_model="gpt-4o-mini",
        default_embedding_model="text-embedding-3-small",
        openai_api_key="openai-key",
        openrouter_api_key="openrouter-key",
    )

    provider = create_provider_from_settings(settings)

    assert provider is not None
    assert provider.base_url == "https://api.openai.com"
    assert provider.api_key == "openai-key"
    provider.close()


def test_agent_provider_alias_selects_provider_when_default_is_empty(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENT_PROVIDER", "openrouter")
    monkeypatch.setenv("AGENT_DEFAULT_MODEL", "google/gemini-2.5-flash")
    settings = Settings(
        default_llm_provider="",
        default_model="",
        default_embedding_model="text-embedding-3-small",
        openai_api_key="openai-key",
        openrouter_api_key="openrouter-key",
    )

    provider = create_provider_from_settings(settings)

    assert provider is not None
    assert provider.base_url == "https://openrouter.ai/api"
    assert provider.api_key == "openrouter-key"
    assert provider.chat_model == "google/gemini-2.5-flash"
    provider.close()


def test_unknown_configured_provider_without_generic_endpoint_returns_none() -> None:
    settings = Settings(
        default_llm_provider="unknown",
        default_model="gpt-4o-mini",
        openai_api_key="openai-key",
    )

    assert create_provider_from_settings(settings) is None


def test_unknown_configured_provider_uses_provider_specific_env(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CUSTOM_AI_API_KEY", "custom-key")
    monkeypatch.setenv("CUSTOM_AI_BASE_URL", "https://custom.example/v1")
    settings = Settings(
        default_llm_provider="custom-ai",
        default_model="custom-chat",
        default_embedding_model="custom-embed",
    )

    provider = create_provider_from_settings(settings)

    assert provider is not None
    assert provider.base_url == "https://custom.example"
    assert provider.api_key == "custom-key"
    assert provider.chat_model == "custom-chat"
    assert provider.embedding_model == "custom-embed"
    provider.close()


def test_langchain_chat_model_uses_generic_provider_env(monkeypatch) -> None:
    monkeypatch.setenv("ANY_PROVIDER_API_KEY", "any-key")
    monkeypatch.setenv("ANY_PROVIDER_BASE_URL", "https://any-provider.example/v1")
    settings = Settings(
        default_llm_provider="any-provider",
        default_model="any-model",
    )

    _model, label = create_langchain_chat_model_from_settings(settings)

    assert label == "any-provider:any-model"
