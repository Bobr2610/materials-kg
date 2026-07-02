from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv

    _env_file = Path(__file__).resolve().parents[2] / ".env"
    if _env_file.exists():
        load_dotenv(_env_file, override=True)
except ImportError:
    pass

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:
    from pydantic import BaseModel

    def SettingsConfigDict(**kwargs: Any) -> dict[str, Any]:
        return kwargs

    class BaseSettings(BaseModel):
        """Small fallback when pydantic-settings is not installed."""

        def __init__(self, **data: Any) -> None:
            env_data = {
                name: os.environ[env_name]
                for name in self.__class__.model_fields
                if (env_name := name.upper()) in os.environ
            }
            env_data.update(data)
            super().__init__(**env_data)


class Settings(BaseSettings):
    """Application settings loaded from .env file.

    Materials KG core settings — Neo4j-first, LLM providers, and API config.
    """

    # LLM (used by llm_core for extraction and answer generation)
    openrouter_api_key: str = ""
    openrouter_base_url: str = ""
    openai_api_key: str | None = None
    openai_base_url: str = ""
    polza_api_key: str = ""
    polza_base_url: str = ""
    groq_api_key: str = ""
    groq_base_url: str = ""
    mistral_api_key: str = ""
    mistral_base_url: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    vllm_base_url: str = ""
    vllm_api_key: str = ""
    default_llm_provider: str = ""
    default_model: str = ""
    default_embedding_model: str = ""
    llm_temperature: float = 0.7

    # Materials KG core API / storage
    materials_neo4j_uri: str = ""
    materials_neo4j_user: str = "neo4j"
    materials_neo4j_password: str = ""
    materials_neo4j_database: str = ""
    materials_require_graph_db: bool = False
    materials_api_host: str = "0.0.0.0"
    materials_api_port: int = 8090
    materials_api_title: str = "Materials KG Core API"
    materials_api_ensure_schema: bool = False
    materials_enable_destructive_api: bool = False

    # LLM context management
    llm_context_window: int = 128000
    llm_safety_margin_tokens: int = 500
    llm_embedding_truncation_chars: int = 8000
    llm_max_retries: int = 3
    llm_retry_base_delay: float = 1.0

    # Hypothesis Factory orchestration
    materials_hypothesis_engine: str = "deepagents"
    materials_deepagents_enabled: bool = True
    materials_deepagents_max_tool_steps: int = 12

    # Document parsing / Vision-Language interpretation
    materials_document_vision_enabled: bool = False
    materials_vision_model: str = ""
    materials_pdf_render_dpi: int = 180
    materials_pdf_max_pages: int | None = None

    # Session management
    session_ttl_seconds: int = 3600
    session_max_messages: int = 50
    session_history_turns: int = 10

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )


_settings_instance: Settings | None = None


def _get_settings() -> Settings:
    global _settings_instance  # noqa: PLW0603
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


class _SettingsProxy:
    """Lazy proxy that defers Settings() instantiation until first attribute access."""

    def __getattr__(self, name: str):
        return getattr(_get_settings(), name)

    def __repr__(self) -> str:
        return repr(_get_settings())


settings: Settings = _SettingsProxy()  # type: ignore[assignment]
