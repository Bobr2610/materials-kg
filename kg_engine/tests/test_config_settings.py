from __future__ import annotations

from pathlib import Path

from kg_engine.config.settings import Settings, get_collection_name
from kg_engine.config.settings import settings as rag_settings


def test_settings_loads_from_env_file():
    """Test that settings load from the actual .env file."""
    # Load from the actual .env file in repo root
    repo_root = Path(__file__).parent.parent.parent
    env_file = repo_root / ".env"

    # This test verifies behavior: settings load correctly from real .env
    settings = Settings(_env_file=env_file)

    # Verify Guardian settings from .env implementation
    assert isinstance(settings.guard_enabled, bool)
    assert isinstance(settings.guard_block_threshold, str)
    assert isinstance(settings.guard_provider_type, str)
    assert isinstance(settings.guard_mosec_port, int)
    assert isinstance(settings.guard_timeout, float)
    assert isinstance(settings.guard_max_retries, int)

    # Verify other settings load correctly
    assert isinstance(settings.top_k_retrieve, int)
    assert isinstance(settings.chunk_overlap, int)
    assert isinstance(settings.rerank_enabled, bool)
    assert isinstance(settings.gradio_server_port, int)


def test_guardian_settings_from_env():
    """Test that Guardian settings match .env configuration."""
    repo_root = Path(__file__).parent.parent.parent
    env_file = repo_root / ".env"
    settings = Settings(_env_file=env_file)

    # Test Guardian configuration matches .env values
    assert settings.guard_enabled in (True, False)
    assert settings.guard_block_threshold in ("unsafe", "controversial")
    assert settings.guard_provider_type in ("mosec", "vllm")
    assert settings.guard_mosec_url in ("http://localhost", "https://localhost", "")
    assert settings.guard_mosec_port in range(1, 65536)
    assert settings.guard_mosec_path.startswith("/") if settings.guard_mosec_path else True


def test_environment_overrides_take_precedence(monkeypatch):
    """Test that environment variables override .env file values."""
    repo_root = Path(__file__).parent.parent.parent
    env_file = repo_root / ".env"

    # Override via environment variable
    monkeypatch.setenv("TOP_K_RETRIEVE", "999")
    settings = Settings(_env_file=env_file)

    # Environment should override .env
    assert settings.top_k_retrieve == 999


def test_get_collection_name_v5_falls_back_to_default_suffix():
    """v5 collection name falls back to {CHROMADB_COLLECTION}_v5 when no override."""
    rag_settings.chromadb_collection = "mkdocs_kb"
    rag_settings.chromadb_collection_v5 = ""

    assert get_collection_name("v5") == "mkdocs_kb_v5"


def test_get_collection_name_v6_falls_back_to_default_suffix():
    """v6 collection name falls back to {CHROMADB_COLLECTION}_v6 when no override."""
    rag_settings.chromadb_collection = "test_coll"
    rag_settings.chromadb_collection_v6 = ""

    assert get_collection_name("v6") == "test_coll_v6"


def test_get_collection_name_override_takes_precedence():
    """Explicit env override wins over fallback suffix."""
    rag_settings.chromadb_collection = "mkdocs_kb"
    rag_settings.chromadb_collection_v5 = "my_custom_v5"

    assert get_collection_name("v5") == "my_custom_v5"


def test_get_collection_name_unknown_version_returns_default():
    """Unknown or missing version key returns the base CHROMADB_COLLECTION."""
    rag_settings.chromadb_collection = "mkdocs_kb"

    assert get_collection_name("v7") == "mkdocs_kb"
    assert get_collection_name("") == "mkdocs_kb"
