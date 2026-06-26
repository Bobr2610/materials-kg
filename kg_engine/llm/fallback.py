"""Fallback management for model switching based on context requirements."""
from __future__ import annotations

import logging

from kg_engine.config.settings import get_allowed_fallback_models, settings
from kg_engine.llm.llm_manager import get_context_window, get_model_config
from kg_engine.llm.token_utils import count_messages_tokens
from kg_engine.utils.context_tracker import compute_thresholds, estimate_accumulated_context

logger = logging.getLogger(__name__)


def find_fallback_model(required_tokens: int, allowed: list[str] | None = None) -> str | None:
    """Find a model that can handle the required token count.

    Scans allowed fallback models and returns the first one with sufficient
    context window. Adds 10% buffer to required tokens for safety.

    Args:
        required_tokens: Minimum token capacity needed
        allowed: Optional list of allowed fallback models (defaults to settings)

    Returns:
        Model name if found, None otherwise

    Example:
        >>> from kg_engine.llm.fallback import find_fallback_model
        >>> model = find_fallback_model(100000)
        >>> model is None or isinstance(model, str)
        True
    """
    if allowed is None:
        allowed = get_allowed_fallback_models()

    if not allowed:
        return None

    # Add 10% buffer
    required_tokens_with_buffer = int(required_tokens * 1.1)

    for candidate in allowed:
        if candidate == settings.default_model:
            continue

        candidate_config = get_model_config(candidate)
        candidate_window = candidate_config.get("token_limit", 0)

        if candidate_window >= required_tokens_with_buffer:
            logger.info(
                "Found model %s with capacity %d tokens (required: %d)",
                candidate,
                candidate_window,
                required_tokens_with_buffer,
            )
            return candidate

    logger.error("No model found with capacity for %d tokens", required_tokens_with_buffer)
    return None


def check_context_fallback(messages: list[dict], overhead: int | None = None) -> str | None:
    """Check if context fallback is needed and return fallback model.

    Estimates token usage for the conversation and checks against the current
    model's context window. If approaching limit (90%), selects a larger model
    from allowed fallbacks.

    Args:
        messages: List of message dicts with 'content' field
        overhead: Buffer for system prompt and output (default: 35000)

    Returns:
        Fallback model name if needed, None otherwise

    Example:
        >>> from kg_engine.llm.fallback import check_context_fallback
        >>> messages = [{"role": "user", "content": "..."}]
        >>> model = check_context_fallback(messages)
    """
    # Get current model config and context window
    model_config = get_model_config(settings.default_model)
    current_window = model_config["token_limit"]

    # Estimate tokens using centralized utility
    total_tokens = count_messages_tokens(messages)

    # Add buffer for system prompt and tool schemas (actual counts)
    from kg_engine.tools.retrieve_context import retrieve_context
    from kg_engine.utils.context_tracker import compute_overhead_tokens

    # Overhead parameter is ignored (kept for backward compatibility)
    overhead_tokens = compute_overhead_tokens(tools=[retrieve_context])
    total_tokens += overhead_tokens

    # Check if approaching limit (pre-agent threshold)
    pre = float(getattr(settings, "llm_pre_context_threshold_pct", 0.90))
    # Use compression threshold for post-tool checks (kept for future use)
    post = float(getattr(settings, "llm_compression_threshold_pct", 0.85))
    pre_threshold, _ = compute_thresholds(current_window, pre_pct=pre, post_pct=post)

    if total_tokens > pre_threshold:
        logger.warning(
            "Context size %d tokens exceeds %.1f%% threshold (%d) of %d window for %s",
            total_tokens,
            90.0,
            pre_threshold,
            current_window,
            settings.default_model,
        )

        # Find fallback model with sufficient capacity
        allowed = get_allowed_fallback_models()
        if not allowed:
            logger.warning("No fallback models configured")
            return None

        # Add 10% buffer
        required_tokens = int(total_tokens * 1.1)
        fallback_model = find_fallback_model(required_tokens, allowed)

        if fallback_model:
            logger.warning(
                "Falling back from %s to %s (window: %d → %d tokens)",
                settings.default_model,
                fallback_model,
                current_window,
                get_context_window(fallback_model),
            )
            return fallback_model

        logger.error("No fallback model found with capacity for %d tokens", required_tokens)

    return None


def select_mid_turn_fallback_model(
    current_model: str,
    messages: list[dict],
    tool_results: list[str],
    allowed_fallbacks: list[str] | None = None,
) -> str | None:
    """Check if model switch is needed mid-turn based on accumulated context.

    This is called after tool results are accumulated to check if the total
    context (messages + tool results) exceeds the safe threshold (80%). If so,
    returns a fallback model that can handle the accumulated context.

    Args:
        current_model: Current model name
        messages: Conversation messages
        tool_results: Accumulated tool result JSON strings
        allowed_fallbacks: Optional list of allowed fallback models

    Returns:
        Fallback model name if switch needed, None otherwise

    Example:
        >>> from kg_engine.llm.fallback import select_mid_turn_fallback_model
        >>> model = select_mid_turn_fallback_model("model", messages, tool_results)
    """
    # Estimate total accumulated context
    accumulated_tokens = estimate_accumulated_context(messages, tool_results)

    # Get current model's context window
    context_window = get_context_window(current_model)

    # Use env-driven thresholds: pre for agent start, compression for post-tool check
    pre_pct = float(getattr(settings, "llm_pre_context_threshold_pct", 0.90))
    post_pct = float(getattr(settings, "llm_compression_threshold_pct", 0.85))
    _, post_threshold = compute_thresholds(context_window, pre_pct=pre_pct, post_pct=post_pct)

    if accumulated_tokens > post_threshold:
        logger.warning(
            "Accumulated context (%d tokens) exceeds %.1f%% threshold (%d) after tool calls. "
            "Checking for model fallback before final answer generation.",
            accumulated_tokens,
            post_pct * 100.0,
            post_threshold,
        )

        # Find fallback model
        fallback_model = find_fallback_model(accumulated_tokens, allowed_fallbacks)

        if fallback_model and fallback_model != current_model:
            logger.warning(
                "⚠️ Switching from %s to %s mid-turn due to accumulated tool results (%d tokens)",
                current_model,
                fallback_model,
                accumulated_tokens,
            )
            return fallback_model

    return None

