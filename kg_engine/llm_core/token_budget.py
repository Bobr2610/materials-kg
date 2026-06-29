"""Token budget management for LLM context window fitting."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_encoder = None


def _get_encoder():
    global _encoder  # noqa: PLW0603
    if _encoder is None:
        import tiktoken

        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def count_tokens(text: str) -> int:
    """Count tokens in a text string using cl100k_base encoding."""
    if not text:
        return 0
    return len(_get_encoder().encode(text))


def count_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """Count total tokens across a list of message dicts."""
    total = 0
    for msg in messages:
        total += count_tokens(msg.get("content", ""))
        total += 4  # message framing overhead
    return total


def fit_context_to_budget(
    context_parts: dict[str, Any],
    budget: int,
    system_prompt_tokens: int = 0,
    safety_margin: int = 500,
) -> dict[str, Any]:
    """Truncate context parts to fit within a token budget.

    Priority order (highest to lowest):
    1. matched_entities, experiments — core query results
    2. observations, evidence — measurements and proof
    3. decision_history, data_gaps — context
    4. search_hits, relations — supplementary

    Each part is serialized to JSON, tokenized, and truncated if needed.
    Returns the same dict with content truncated where necessary.
    """
    import json

    available = budget - system_prompt_tokens - safety_margin
    if available <= 0:
        logger.warning("Token budget exhausted before context: budget=%d, system=%d", budget, system_prompt_tokens)
        return {}

    priority_groups = [
        ["matched_entities", "experiments"],
        ["observations", "evidence"],
        ["decision_history", "data_gaps"],
        ["search_hits", "relations"],
    ]

    allocated: dict[str, int] = {}
    remaining = available

    for group in priority_groups:
        keys_in_group = [k for k in group if context_parts.get(k)]
        if not keys_in_group:
            continue
        group_tokens = sum(
            count_tokens(json.dumps(context_parts[k], ensure_ascii=False, default=str))
            for k in keys_in_group
        )
        if group_tokens <= remaining:
            for k in keys_in_group:
                allocated[k] = count_tokens(
                    json.dumps(context_parts[k], ensure_ascii=False, default=str)
                )
            remaining -= group_tokens
        else:
            per_key_budget = remaining // len(keys_in_group)
            for k in keys_in_group:
                allocated[k] = per_key_budget
            remaining = 0
            break

    result: dict[str, Any] = {}
    for key, value in context_parts.items():
        if not value:
            result[key] = value
            continue
        serialized = json.dumps(value, ensure_ascii=False, default=str)
        token_limit = allocated.get(key)
        if token_limit is None:
            result[key] = value
            continue
        current_tokens = count_tokens(serialized)
        if current_tokens <= token_limit:
            result[key] = value
        else:
            truncated_json = _truncate_json_to_tokens(serialized, token_limit)
            try:
                result[key] = json.loads(truncated_json)
            except json.JSONDecodeError:
                result[key] = value
            logger.debug(
                "Truncated '%s' from %d to ~%d tokens",
                key, current_tokens, token_limit,
            )

    return result


def _truncate_json_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate a JSON string to fit within max_tokens.

    Attempts to keep valid JSON by finding the last complete element.
    """
    if max_tokens <= 0:
        return "[]"

    encoder = _get_encoder()
    tokens = encoder.encode(text)

    if len(tokens) <= max_tokens:
        return text

    truncated_tokens = tokens[:max_tokens]
    truncated = encoder.decode(truncated_tokens)

    for suffix in ("]", "}", ',"', ',"'):
        idx = truncated.rfind(suffix)
        if idx > 0:
            candidate = truncated[: idx + len(suffix)]
            if candidate.rstrip().endswith("]") or candidate.rstrip().endswith("}"):
                return candidate

    return truncated
