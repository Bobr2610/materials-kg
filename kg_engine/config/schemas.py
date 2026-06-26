"""Pydantic schemas for embedding and reranker provider configurations."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal, Optional, Union

import yaml
from pydantic import BaseModel, Field
from typing_extensions import Annotated

logger = logging.getLogger(__name__)


# ============ EMBEDDING CONFIGS ============


class DirectEmbeddingConfig(BaseModel):
    """Direct sentence-transformers embedder (current implementation)."""

    type: Literal["direct"]
    model: str = Field(..., description="Model name for sentence-transformers")
    device: str = Field(default="auto")
    max_seq_length: int = Field(default=512)


class OpenAIEmbeddingConfig(BaseModel):
    """Config for OpenAI-compatible embedding API. All values from models.yaml + .env."""

    type: Literal["openai_compatible"]
    provider: str = Field(..., description="Provider type: mosec, infinity, or openrouter")
    endpoint: str = Field(..., description="API endpoint URL")
    model: str = Field(default="auto", description="Model name for API requests")
    api_key: str | None = Field(default=None, description="API key (None for local servers)")
    dimensions: int = Field(..., description="Embedding dimension from models.yaml")
    local: bool = Field(..., description="Use direct HTTP (local) or OpenAI SDK (remote)")

    # Model formatting (from models.yaml)
    query_prefix: str | None = Field(
        default=None, description="Prefix for queries (FRIDA: search_query: )"
    )
    doc_prefix: str | None = Field(
        default=None, description="Prefix for documents (FRIDA: search_document: )"
    )
    default_instruction: str | None = Field(
        default=None, description="Default instruction for Qwen3"
    )

    # Request settings
    timeout: float = Field(default=60.0, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Max retries on failure")


# Discriminated union for type-safe config loading
EmbeddingProviderConfig = Annotated[
    Union[DirectEmbeddingConfig, OpenAIEmbeddingConfig],
    Field(discriminator="type"),
]


# ============ RERANKER CONFIGS ============


class RerankerFormatting(BaseModel):
    """Client-side formatting for LLM rerankers.

    Templates use Python format strings with placeholders:
    - {query}: The search query
    - {doc}: The document text
    - {instruction}: The task instruction
    - {prefix}: Query prefix (Qwen3: system prompt)
    - {suffix}: Document suffix (Qwen3: end tokens)
    - {prompt}: Task prompt (BGE-Gemma)
    """

    query_template: str = Field(
        default="{query}",
        description="Query formatting template",
    )
    doc_template: str = Field(
        default="{doc}",
        description="Document formatting template",
    )
    prefix: str = Field(
        default="",
        description="Query prefix (e.g., ChatML system prompt)",
    )
    suffix: str = Field(
        default="",
        description="Document suffix (e.g., end tokens)",
    )
    prompt: str | None = Field(
        default=None,
        description="Task prompt for BGE-Gemma format",
    )


class DirectRerankerConfig(BaseModel):
    """Direct CrossEncoder reranker (current implementation)."""

    type: Literal["direct"]
    model: str = Field(..., description="Model name for CrossEncoder")
    device: str = Field(default="auto")
    batch_size: int = Field(default=16)


class ServerRerankerConfig(BaseModel):
    """HTTP server reranker (Infinity/Mosec). All values from models.yaml + .env."""

    type: Literal["server"]
    provider: str = Field(..., description="Provider type: mosec or infinity")
    endpoint: str = Field(
        ..., description="Complete API endpoint URL (e.g., http://localhost:7998/v1/rerank)"
    )
    reranker_type: Literal["cross_encoder", "llm_reranker"] = Field(
        default="cross_encoder",
        description="Model architecture type",
    )
    formatting: RerankerFormatting | None = Field(
        default=None,
        description="Client-side formatting (LLM rerankers only)",
    )
    default_instruction: str | None = Field(
        default=None,
        description="Default instruction for LLM rerankers",
    )
    timeout: float = Field(default=60.0, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Max retries on failure")


RerankerProviderConfig = Annotated[
    Union[DirectRerankerConfig, ServerRerankerConfig],
    Field(discriminator="type"),
]


# ============ MODEL REGISTRY ============


class ModelRegistry:
    """Registry for model metadata loaded from YAML.

    Supports case-insensitive model slug lookup with canonical normalization.
    All model slugs are stored in HuggingFace format (e.g., "Qwen/Qwen3-Embedding-8B")
    but can be looked up with any case variation (e.g., "qwen/qwen3-embedding-8b").
    """

    _instance = None
    _models: dict[str, dict[str, Any]] = {}
    _defaults: dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_registry()
        return cls._instance

    def _load_registry(self) -> None:
        """Load model registry from YAML file."""
        config_path = Path(__file__).parent / "models.yaml"

        if not config_path.exists():
            raise FileNotFoundError(f"Model registry not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Build case-insensitive lookup table
        for model_slug, model_data in data.get("models", {}).items():
            # Store with normalized (lowercase) key for lookup
            normalized_key = model_slug.lower()
            self._models[normalized_key] = {
                "canonical_slug": model_slug,
                **model_data,
            }

        self._defaults = data.get("defaults", {})
        logger.info(f"Loaded {len(self._models)} models from registry")

    def _normalize_slug(self, model_slug: str) -> str:
        """Normalize model slug to lowercase for case-insensitive lookup."""
        return model_slug.lower().strip()

    def get_model(self, model_slug: str) -> dict[str, Any]:
        """Get model metadata by slug (case-insensitive).

        Args:
            model_slug: Model identifier (e.g., "Qwen/Qwen3-Embedding-8B" or "qwen/qwen3-embedding-8b")

        Returns:
            Model metadata dict with canonical_slug, type, dimensions, provider_formats

        Raises:
            ValueError: If model not found in registry
        """
        normalized = self._normalize_slug(model_slug)
        if normalized not in self._models:
            available = [m["canonical_slug"] for m in self._models.values()]
            raise ValueError(f"Unknown model: {model_slug}. Available: {available}")
        return self._models[normalized]

    def get_canonical_slug(self, model_slug: str) -> str:
        """Get canonical (HuggingFace format) slug from any case variation.

        Args:
            model_slug: Model identifier in any case

        Returns:
            Canonical slug in HuggingFace format (e.g., "Qwen/Qwen3-Embedding-8B")
        """
        return self.get_model(model_slug)["canonical_slug"]

    def get_dimension(self, model_slug: str) -> int:
        """Get embedding dimension for a model.

        Args:
            model_slug: Model identifier

        Returns:
            Embedding dimension (int)

        Raises:
            ValueError: If model not found or not an embedding model
        """
        model = self.get_model(model_slug)
        if model.get("type") != "embedding":
            raise ValueError(f"Model {model_slug} is not an embedding model")
        return model["dimensions"]

    def get_provider_config(self, model_slug: str, provider: str) -> dict[str, Any]:
        """Get provider-specific configuration for a model.

        Args:
            model_slug: Model identifier
            provider: Provider type ("direct", "infinity", "openrouter")

        Returns:
            Provider configuration dict

        Raises:
            ValueError If provider explicitly not supported (supported: false)
        """
        model = self.get_model(model_slug)
        formats = model.get("provider_formats", {})

        # If provider not listed, check if it's implicitly supported
        if provider not in formats:
            # Check if model has this provider type by checking other models
            # Default: all providers supported unless marked supported: false
            return {}  # Empty config = use defaults

        config = formats[provider]
        if config.get("supported", True) is False:
            raise ValueError(f"Provider {provider} is not supported for model {model_slug}")

        return config

    def get_default_endpoint(self, provider: str, model_type: str) -> str:
        """Get default endpoint for a provider.

        Args:
            provider: Provider type ("infinity", "openrouter")
            model_type: "embedding" or "reranker"

        Returns:
            Default endpoint URL
        """
        endpoints = self._defaults.get("endpoints", {})

        if provider == "infinity":
            return endpoints.get("infinity", {}).get(
                model_type, f"http://localhost:{7997 if model_type == 'embedding' else 7998}"
            )
        elif provider == "openrouter":
            return endpoints.get("openrouter", "https://openrouter.ai/api/v1")

        raise ValueError(f"Unknown provider: {provider}")

    def get_timeout(self, provider: str) -> float:
        """Get default timeout for a provider."""
        return self._defaults.get("timeouts", {}).get(provider, 60.0)

    def get_retries(self, provider: str) -> int:
        """Get default retries for a provider."""
        return self._defaults.get("retries", {}).get(provider, 3)

    def get_default_instruction(self, model_slug: str) -> str | None:
        """Get default instruction for a model (e.g., Qwen3 embedding models).

        Args:
            model_slug: Model identifier

        Returns:
            Default instruction string or None if not applicable
        """
        model = self.get_model(model_slug)
        return model.get("default_instruction")

    def list_models(self, model_type: Optional[str] = None) -> list[str]:
        """List available models.

        Args:
            model_type: Filter by type ("embedding" or "reranker"), or None for all

        Returns:
            List of canonical model slugs
        """
        models = self._models.values()
        if model_type:
            models = [m for m in models if m.get("type") == model_type]
        return [m["canonical_slug"] for m in models]


# Convenience function for backward compatibility
def get_model_dimension(model_slug: str) -> int:
    """Get embedding dimension for a model (convenience function)."""
    return ModelRegistry().get_dimension(model_slug)
