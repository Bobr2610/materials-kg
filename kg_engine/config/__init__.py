"""Configuration package for kg_engine.

The materials KG core should be able to import settings without pulling in the
legacy model-registry stack and its optional YAML dependency.
"""

from kg_engine.config.settings import Settings, settings

__all__ = [
    "Settings",
    "settings",
    "EmbeddingProviderConfig",
    "RerankerProviderConfig",
    "DirectEmbeddingConfig",
    "OpenAIEmbeddingConfig",
    "DirectRerankerConfig",
    "ServerRerankerConfig",
    "ModelRegistry",
    "get_model_dimension",
]


def __getattr__(name: str):
    if name in {
        "EmbeddingProviderConfig",
        "RerankerProviderConfig",
        "DirectEmbeddingConfig",
        "OpenAIEmbeddingConfig",
        "DirectRerankerConfig",
        "ServerRerankerConfig",
        "ModelRegistry",
        "get_model_dimension",
    }:
        from kg_engine.config import schemas

        return getattr(schemas, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
