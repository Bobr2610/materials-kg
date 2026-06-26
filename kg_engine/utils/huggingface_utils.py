"""HuggingFace configuration utilities.

Handles environment variable configuration for HuggingFace-related libraries
(sentence-transformers, huggingface_hub) based on settings from .env file.

Per 12-Factor App principles: all configuration is env-driven with no
hardcoded defaults. This module exports settings to environment variables
that HuggingFace libraries read automatically.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def configure_huggingface_env():
    """Export HuggingFace configuration from settings to environment variables.

    Reads hf_token and hf_hub_disable_remote_validation from settings
    and exports them to os.environ for HuggingFace libraries to use.

    sentence_transformers and huggingface_hub automatically read:
    - HF_TOKEN: For authenticated requests (prevents rate limiting)
    - HF_HUB_DISABLE_REMOTE_VALIDATION: For cache behavior

    This function should be called at application startup, before any
    HuggingFace models are loaded.
    """
    from kg_engine.config.settings import settings

    if settings.hf_token:
        os.environ["HF_TOKEN"] = settings.hf_token
        logger.debug("HF_TOKEN configured from .env")
    else:
        logger.debug("HF_TOKEN not set in .env (using unauthenticated access)")

    if settings.hf_hub_disable_remote_validation:
        os.environ["HF_HUB_DISABLE_REMOTE_VALIDATION"] = "true"
        logger.debug("HF_HUB_DISABLE_REMOTE_VALIDATION enabled")
    else:
        logger.debug("HF_HUB_DISABLE_REMOTE_VALIDATION disabled (will validate cached models)")
