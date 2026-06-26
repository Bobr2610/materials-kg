"""Configuration loader - compatibility layer for ModelRegistry.

This module is deprecated. Use ModelRegistry from kg_engine.config.schemas directly.
"""

from __future__ import annotations

import warnings
from typing import Any

from kg_engine.config.schemas import (
    DirectEmbeddingConfig,
    DirectRerankerConfig,
    ModelRegistry,
    OpenAIEmbeddingConfig,
    ServerRerankerConfig,
)


def load_embedding_config(provider_key: str) -> Any:
    """Load configuration for an embedding provider (deprecated).

    This function is maintained for backward compatibility.
    Use ModelRegistry.get_provider_config() instead.
    """
    warnings.warn(
        "load_embedding_config is deprecated. Use ModelRegistry.get_provider_config() instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    # Map old provider keys to new (model_slug, provider_type) format
    provider_map = {
        "direct_frida": ("ai-forever/FRIDA", "direct"),
        "infinity_frida": ("ai-forever/FRIDA", "infinity"),
        "openrouter_qwen3": ("Qwen/Qwen3-Embedding-8B", "openrouter"),
        "infinity_qwen3_8b": ("Qwen/Qwen3-Embedding-8B", "infinity"),
        "infinity_qwen3_4b": ("Qwen/Qwen3-Embedding-4B", "infinity"),
        "infinity_qwen3_0_6b": ("Qwen/Qwen3-Embedding-0.6B", "infinity"),
    }

    if provider_key not in provider_map:
        raise ValueError(f"Unknown provider: {provider_key}")

    model_slug, provider_type = provider_map[provider_key]
    registry = ModelRegistry()

    try:
        model_data = registry.get_model(model_slug)
        provider_config = registry.get_provider_config(model_slug, provider_type)
    except ValueError as e:
        raise ValueError(f"Failed to load config: {e}") from e

    # Construct config based on provider type
    if provider_type == "direct":
        return DirectEmbeddingConfig(
            type="direct",
            model=model_slug,
            device=provider_config.get("device", "auto"),
            max_seq_length=provider_config.get("max_seq_length", 512),
        )
    elif provider_type == "infinity":
        model_instruction = registry.get_default_instruction(model_slug)
        return OpenAIEmbeddingConfig(
            type="openai_compatible",
            provider="infinity",
            endpoint=f"http://localhost:7997/v1/embeddings",  # Default, should come from settings
            model=model_slug,
            dimensions=registry.get_dimension(model_slug),
            local=True,
            query_prefix=provider_config.get("query_prefix"),
            doc_prefix=provider_config.get("doc_prefix"),
            default_instruction=model_instruction,
        )
    elif provider_type == "openrouter":
        model_instruction = registry.get_default_instruction(model_slug)
        return OpenAIEmbeddingConfig(
            type="openai_compatible",
            provider="openrouter",
            endpoint="https://openrouter.ai/api/v1",
            model=provider_config.get("model_id", model_slug.lower()),
            dimensions=registry.get_dimension(model_slug),
            local=False,
            default_instruction=model_instruction,
        )
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")


def load_reranker_config(provider_key: str) -> Any:
    """Load configuration for a reranker provider (deprecated).

    This function is maintained for backward compatibility.
    Use ModelRegistry.get_provider_config() instead.
    """
    warnings.warn(
        "load_reranker_config is deprecated. Use ModelRegistry.get_provider_config() instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    # Map old provider keys to new format
    provider_map = {
        "direct_crossencoder": ("DiTy/cross-encoder-russian-msmarco", "direct"),
        "infinity_dity": ("DiTy/cross-encoder-russian-msmarco", "infinity"),
        "infinity_bge_reranker": ("BAAI/bge-reranker-v2-m3", "infinity"),
        "infinity_qwen3_reranker_8b": ("Qwen/Qwen3-Reranker-8B", "infinity"),
        "infinity_qwen3_reranker_4b": ("Qwen/Qwen3-Reranker-4B", "infinity"),
        "infinity_qwen3_reranker_0_6b": ("Qwen/Qwen3-Reranker-0.6B", "infinity"),
    }

    if provider_key not in provider_map:
        raise ValueError(f"Unknown provider: {provider_key}")

    model_slug, provider_type = provider_map[provider_key]
    registry = ModelRegistry()

    try:
        provider_config = registry.get_provider_config(model_slug, provider_type)
    except ValueError as e:
        raise ValueError(f"Failed to load config: {e}") from e

    if provider_type == "direct":
        return DirectRerankerConfig(
            type="direct",
            model=model_slug,
            device=provider_config.get("device", "auto"),
            batch_size=provider_config.get("batch_size", 16),
        )
    elif provider_type == "infinity":
        reranker_type = registry.get_model(model_slug).get("reranker_type", "cross_encoder")
        model_instruction = registry.get_default_instruction(model_slug)
        return ServerRerankerConfig(
            type="server",
            provider="infinity",
            endpoint="http://localhost:7998/v1/rerank",  # Default, should come from settings
            reranker_type=reranker_type,
            default_instruction=model_instruction,
        )
    elif provider_type == "mosec":
        reranker_type = registry.get_model(model_slug).get("reranker_type", "cross_encoder")
        model_instruction = registry.get_default_instruction(model_slug)
        return ServerRerankerConfig(
            type="server",
            provider="mosec",
            endpoint="http://localhost:7998/v1/rerank",  # Default, should come from settings
            reranker_type=reranker_type,
            default_instruction=model_instruction,
        )
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")


def list_embedding_providers() -> list[str]:
    """List all available embedding providers (deprecated)."""
    warnings.warn(
        "list_embedding_providers is deprecated. Use ModelRegistry.list_models() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return [
        "direct_frida",
        "infinity_frida",
        "openrouter_qwen3",
        "infinity_qwen3_8b",
        "infinity_qwen3_4b",
        "infinity_qwen3_0_6b",
    ]


def list_reranker_providers() -> list[str]:
    """List all available reranker providers (deprecated)."""
    warnings.warn(
        "list_reranker_providers is deprecated. Use ModelRegistry.list_models() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return [
        "direct_crossencoder",
        "infinity_dity",
        "infinity_bge_reranker",
        "infinity_qwen3_reranker_8b",
        "infinity_qwen3_reranker_4b",
        "infinity_qwen3_reranker_0_6b",
    ]
