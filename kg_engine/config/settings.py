from pydantic_settings import BaseSettings, SettingsConfigDict

# Global configuration constants
# Normalize Unicode escapes (e.g., \u0432\u043e -> воз) in search queries
# Set to False if search engine needs raw Unicode escapes (edge case)
NORMALIZE_SEARCH_QUERIES: bool = False


class Settings(BaseSettings):
    """Application settings loaded from .env file.

    All configuration is env-driven with no hardcoded defaults to ensure
    single source of truth per 12-Factor principles. Secrets and provider
    credentials must be provided via environment variables.

    All variables listed below MUST be configured in environment variables.
    """

    # LLM Providers
    google_api_key: str
    openrouter_api_key: str
    openrouter_base_url: str
    # OpenAI (true API, opt-in via DEFAULT_LLM_PROVIDER=openai)
    openai_api_key: str | None = None
    # vLLM configuration (OpenAI-compatible API)
    vllm_base_url: str
    vllm_api_key: str

    # Embedding Configuration (Model-Slug Based)
    # Provider type: direct | infinity | mosec | openrouter
    embedding_provider_type: str
    # Model slug (e.g., "ai-forever/FRIDA", "Qwen/Qwen3-Embedding-8B")
    # Case insensitive - "qwen/qwen3-embedding-8b" works too
    embedding_model: str
    # Device for direct embedding/reranker when not using factory (e.g. build_index, legacy retriever).
    # Factory path uses device from models.yaml.
    embedding_device: str

    # ChromaDB (HTTP-only: separate server via chroma run or Docker; no embedded PersistentClient)
    chromadb_persist_dir: str
    chromadb_collection: str
    # Versioned collection overrides (v5/v6); empty = fall back to {chromadb_collection}_v{N}
    chromadb_collection_v5: str = ""
    chromadb_collection_v6: str = ""
    # Filesystem corpus root for grep and fallback file reads
    corpora_root: str = ""
    # ChromaDB HTTP client configuration
    # chroma_client_host: RAG agent connects to this address
    # chroma_server_bind: ChromaDB server binds to this address (0.0.0.0 = all interfaces)
    chroma_client_host: str
    chroma_server_bind: str
    chromadb_port: int
    chromadb_ssl: bool
    # How long to keep HTTP connections alive (prevents premature disconnects, e.g., 60.0 seconds)
    # Maps to ChromaDB's CHROMA_HTTP_KEEPALIVE_SECS environment variable
    chroma_http_keepalive_secs: float
    # Maximum number of connections in the pool
    # Maps to ChromaDB's CHROMA_HTTP_MAX_CONNECTIONS environment variable
    chroma_http_max_connections: int

    # Retrieval
    top_k_retrieve: int
    top_k_rerank: int
    rerank_score_threshold: float | None = None
    rerank_enabled: bool
    rerank_boost_code: float = 0.0
    rerank_boost_tag: float = 0.0
    rerank_boost_section: float = 0.0
    chunk_size: int
    chunk_overlap: int

    # Retrieval – multi-vector query and query decomposition
    retrieval_multiquery_enabled: bool
    retrieval_multiquery_max_segments: int
    retrieval_multiquery_segment_tokens: int
    retrieval_multiquery_segment_overlap: int
    retrieval_multiquery_pre_rerank_limit: int

    retrieval_query_decomp_enabled: bool
    retrieval_query_decomp_max_subqueries: int

    # Reranker Provider Selection
    # Options: direct_crossencoder | infinity_dity | infinity_bge_reranker | infinity_qwen3_reranker_8b | infinity_qwen3_reranker_4b | infinity_qwen3_reranker_0_6b
    # Reranker Configuration (Model-Slug Based)
    # Provider type: direct | infinity | openrouter
    reranker_provider_type: str
    # Model slug (e.g., "DiTy/cross-encoder-russian-msmarco", "Qwen/Qwen3-Reranker-8B")
    # Case insensitive
    reranker_model: str

    # Provider Endpoints (optional, have defaults)
    infinity_embedding_endpoint: str | None = None
    infinity_reranker_endpoint: str | None = None
    mosec_embedding_endpoint: str | None = None
    mosec_reranker_endpoint: str | None = None
    vllm_embedding_endpoint: str | None = None
    openrouter_endpoint: str | None = None

    # Request Configuration
    embedding_timeout: float
    embedding_max_retries: int
    embedding_local: bool  # true=direct HTTP (faster), false=OpenAI SDK (auth+retries)
    reranker_timeout: float
    reranker_max_retries: int

    # LLM
    default_llm_provider: str
    default_model: str
    llm_temperature: float
    llm_max_tokens: int | None = (
        None  # Optional override for max_tokens from model config (hard cutoff)
    )
    llm_mild_limit: int | None = (
        None  # Optional soft guidance limit for response length (injected into system prompt)
    )
    # Optional overrides for model config (if set, overrides model_configs.py values)
    llm_token_limit: int | None = None  # Optional override for token_limit from model config

    # Reasoning / thinking tokens (OpenRouter-style)
    # These settings are passed via the unified `reasoning` object for OpenAI-compatible providers.
    llm_reasoning_enabled: bool = False
    llm_reasoning_effort: str | None = None
    llm_reasoning_max_tokens: int | None = None
    llm_reasoning_exclude_from_response: bool = False

    # Reasoning bubble UI (streaming)
    # Number of reasoning lines to show in the UI bubble tail (full trace kept in diagnostics).
    ui_reasoning_tail_lines: int = 4

    # LangChain Configuration
    langchain_recursion_limit: int = 100  # Max steps for LangGraph StateGraph

    # Fallback and summarization
    llm_fallback_enabled: bool
    llm_fallback_provider: str | None = None
    llm_allowed_fallback_models: str
    llm_summarization_enabled: bool
    # vLLM streaming fallback: if True, falls back to invoke() if tool calls aren't detected in stream
    # Set to False to disable fallback and test pure streaming behavior
    vllm_streaming_fallback_enabled: bool
    # Optional legacy/override; dynamic targets are used by default
    llm_summarization_target_tokens_per_article: int | None = None

    # HuggingFace Configuration
    # Token for authenticated downloads (prevents rate limiting)
    # Get token: https://huggingface.co/settings/tokens
    hf_token: str | None = None
    # Trust locally cached models, skip remote validation (faster, offline-friendly)
    # Set to true to skip HEAD requests checking for model updates
    hf_hub_disable_remote_validation: bool = False

    # Gradio
    gradio_server_name: str
    gradio_server_port: int
    # Share link: if True, attempts to create a public shareable link.
    # If share link creation fails (network/service issues), app still runs locally.
    gradio_share: bool
    # Embedded widget mode: if True, uses smaller heights suitable for embedded widget.
    # If False, uses larger heights suitable for standalone app.
    gradio_embedded_widget: bool
    # Queue configuration: concurrency limit for all event listeners
    # Per Gradio docs: https://www.gradio.app/guides/queuing
    gradio_default_concurrency_limit: int

    # Memory compression (conversation history)
    # Percentage of context window at which we trigger compression
    memory_compression_threshold_pct: int
    # Target tokens for the compressed history turn
    memory_compression_target_tokens: int
    # Number of recent messages to keep uncompressed (for agent mode)
    memory_compression_messages_to_keep: int

    # Context thresholds and compression (env-driven)
    # Pre-agent safety threshold as a fraction of the model context window
    llm_pre_context_threshold_pct: float

    # Context overhead safety margin for formatting and message structure
    # Additional tokens reserved beyond actual system prompt and tool schema counts
    # Accounts for: message formatting, JSON structure overhead, output buffer
    # Note: System prompt and tool schemas are counted directly, this is just a safety buffer
    llm_context_overhead_safety_margin: int

    # JSON overhead percentage for tool results (JSON format adds overhead vs raw content)
    # Applied to accumulated tool result tokens to account for JSON serialization overhead
    llm_tool_results_json_overhead_pct: float

    # Tool-results compression controls
    # When total tokens exceed this fraction, trigger compression
    llm_compression_threshold_pct: float
    # After compression, target total tokens to be at/below this fraction
    llm_compression_target_pct: float
    # Minimum tokens to preserve per article during compression
    llm_compression_min_tokens: int

    # Timezone configuration
    # Default timezone for datetime operations (IANA timezone name, e.g., 'Europe/Moscow', 'UTC')
    default_timezone: str

    # Guardian (Content Moderation)
    # All guardian settings must be defined in .env file
    # No hard-coded defaults - .env is single source of truth
    guard_enabled: bool
    guard_block_threshold: str
    guard_provider_type: str

    # MOSEC provider settings (required when provider_type="mosec")
    guard_mosec_endpoint: str

    # VLLM provider settings (required when provider_type="vllm")
    guard_vllm_url: str
    guard_vllm_model: str

    # Reserved settings for future use (must be defined in .env)
    guard_model: str
    guard_device: str
    guard_openrouter_model: str

    # Common settings
    guard_timeout: float
    guard_max_retries: int

    # SRP (Support Resolution Plan)
    # Generates resolution plan for human support engineers after answer generation
    srp_enabled: bool = False
    # When True, inject SRP plan markdown into the answer even when engineer_intervention_needed=False
    srp_always_render_plan: bool = False

    # CMW Platform Integration
    # Comindware Platform API credentials (required for platform integration)
    cmw_base_url: str
    cmw_login: str
    cmw_password: str
    cmw_timeout: int = 30
    # API key for CMW Platform webhook endpoints
    # MANDATORY in .env - must be present (empty = skip auth, present = require it)
    cmw_api_key: str
    # API key for CMW2/Lukoil Platform webhook endpoint
    cmw2_api_key: str = ""

    # Pydantic v2 configuration: accept extra env vars and set env file
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )


settings = Settings()


# Helpers derived from settings (avoid polluting pydantic model with properties)
def get_allowed_fallback_models() -> list[str]:
    raw = settings.llm_allowed_fallback_models or ""
    return [m.strip() for m in raw.split(",") if m and m.strip()]


def get_collection_name(version: str) -> str:
    """Resolve Chroma collection name for a product version.

    Returns the env override for that version if non-empty, otherwise falls back
    to '{chromadb_collection}_v{version}'. Unknown versions return the base
    collection name unchanged.
    """
    base = settings.chromadb_collection
    if version == "v5":
        return settings.chromadb_collection_v5 or f"{base}_v5"
    if version == "v6":
        return settings.chromadb_collection_v6 or f"{base}_v6"
    return base
