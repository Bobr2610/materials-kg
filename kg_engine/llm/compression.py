"""Compression utilities for managing context limits dynamically."""
from __future__ import annotations

import json
import logging

from kg_engine.config.settings import settings
from kg_engine.llm.summarization import summarize_to_tokens
from kg_engine.llm.token_utils import count_tokens
from kg_engine.utils.message_utils import (
    extract_user_question,
    get_message_content,
    is_tool_message,
    update_tool_message_content,
)

logger = logging.getLogger(__name__)


def compress_all_articles_proportionally_by_rank(
    articles: list[dict],
    target_tokens: int,
    guidance: str | None = None,
    llm_manager=None,
) -> tuple[list[dict], int]:
    """Compress articles proportionally to their ranks to fit target_tokens.

    Allocates target_tokens budget proportionally:
    - Higher-ranked articles (lower normalized_rank) get larger share of budget
    - Lower-ranked articles (higher normalized_rank) get smaller share of budget

    The sum of all compressed articles will equal target_tokens (within rounding).

    Args:
        articles: List of article dicts with 'content', 'metadata.normalized_rank'
        target_tokens: Target total tokens for ALL articles after compression
        guidance: User question for summarization guidance
        llm_manager: LLMManager for summarization

    Returns:
        Tuple of (compressed_articles, tokens_saved)
    """
    if not articles or not llm_manager:
        return articles, 0

    # Validate and prepare ranks
    for article in articles:
        rank = article.get("metadata", {}).get("normalized_rank")
        if rank is not None:
            article.setdefault("metadata", {})["normalized_rank"] = max(0.0, min(1.0, float(rank)))
        else:
            article.setdefault("metadata", {})["normalized_rank"] = 1.0

    # Calculate allocation weights based on rank
    # Higher rank (lower normalized_rank) = higher weight = more budget
    # Formula: weight = 1.0 - (normalized_rank * 0.7) gives range [0.3, 1.0]
    # Best rank (0.0) gets weight 1.0, worst (1.0) gets weight 0.3
    total_weight = 0.0
    article_weights = []

    for article in articles:
        normalized_rank = article.get("metadata", {}).get("normalized_rank", 1.0)
        # Weight: 1.0 for best rank (0.0), 0.3 for worst rank (1.0)
        weight = 1.0 - (normalized_rank * 0.7)
        article_weights.append(weight)
        total_weight += weight

    if total_weight == 0:
        # Fallback: equal distribution
        article_weights = [1.0] * len(articles)
        total_weight = float(len(articles))

    # Allocate target_tokens proportionally to each article
    min_tokens_per_article = getattr(settings, "llm_compression_min_tokens", 300)
    article_allocations = []

    for i, article in enumerate(articles):
        # Proportional allocation based on weight
        proportional_share = article_weights[i] / total_weight
        allocated_tokens = int(target_tokens * proportional_share)

        # Ensure minimum tokens per article and don't exceed original size
        original_tokens = count_tokens(article.get("content", ""))
        article_target_tokens = max(min_tokens_per_article, min(allocated_tokens, original_tokens))

        article_allocations.append((i, article, article_target_tokens))

    # Adjust if allocations exceed target (due to min_tokens constraint)
    total_allocated = sum(alloc[2] for alloc in article_allocations)
    if total_allocated > target_tokens:
        # Need to reduce allocations, starting with worst-ranked articles
        # Sort by normalized_rank descending (worst first)
        article_allocations.sort(
            key=lambda x: x[1].get("metadata", {}).get("normalized_rank", 1.0),
            reverse=True,
        )

        excess = total_allocated - target_tokens
        for i, (orig_idx, article, allocated) in enumerate(article_allocations):
            if excess <= 0:
                break

            reduction = min(excess, allocated - min_tokens_per_article)
            if reduction > 0:
                article_allocations[i] = (orig_idx, article, allocated - reduction)
                excess -= reduction

    # Now compress each article to its allocated target
    compressed_articles = list(articles)
    tokens_saved = 0

    for orig_idx, article, article_target_tokens in article_allocations:
        original_content = article.get("content", "")
        if not original_content:
            continue

        original_tokens = count_tokens(original_content)

        # If already fits, no compression needed
        if original_tokens <= article_target_tokens:
            continue

        try:
            compressed = summarize_to_tokens(
                title=article.get("title", "Article"),
                url=article.get("url", ""),
                matched_chunks=[original_content],
                full_body=None,
                target_tokens=article_target_tokens,
                guidance=guidance,
                llm=llm_manager,
                max_retries=1,
            )

            compressed_tokens = count_tokens(compressed)
            compressed_articles[orig_idx]["content"] = compressed
            if "metadata" not in compressed_articles[orig_idx]:
                compressed_articles[orig_idx]["metadata"] = {}
            compressed_articles[orig_idx]["metadata"]["compressed"] = True

            tokens_saved += original_tokens - compressed_tokens

            logger.debug(
                "Compressed article '%s' (rank=%.2f): %d → %d tokens (allocated=%d)",
                article.get("title", "")[:50],
                article.get("metadata", {}).get("normalized_rank", 1.0),
                original_tokens,
                compressed_tokens,
                article_target_tokens,
            )
        except Exception as exc:
            logger.warning("Failed to compress article at index %d: %s", orig_idx, exc)
            continue

    return compressed_articles, tokens_saved


def compress_tool_messages(
    messages: list,
    runtime,
    llm_manager,
    threshold_pct: float = 0.85,
    target_pct: float = 0.80,
) -> list | None:
    """Compress tool messages if context exceeds threshold.

    NEW BEHAVIOR:
    1. Extracts ALL articles from ALL tool messages
    2. Deduplicates by kb_id (preserves highest rerank_score)
    3. Re-normalizes ranks after deduplication
    4. Compresses proportionally by rank across all articles
    5. Updates tool messages with compressed articles

    This runs in @before_model middleware AFTER all tool calls complete.

    Args:
        messages: List of message objects
        runtime: Runtime object with access to model config
        llm_manager: LLMManager instance for compression
        threshold_pct: Threshold percentage for triggering compression (default: 0.85)
        target_pct: Target percentage after compression (default: 0.80)

    Returns:
        Updated list of messages if compression occurred, None otherwise

    Example:
        >>> from kg_engine.llm.compression import compress_tool_messages
        >>> # ... setup messages, runtime, llm_manager ...
        >>> compressed = compress_tool_messages(messages, runtime, llm_manager)
    """
    from kg_engine.config.settings import settings
    from kg_engine.llm.llm_manager import get_context_window
    from kg_engine.llm.token_utils import count_messages_tokens

    if not messages:
        return None

    # Get current model's context window
    current_model = getattr(runtime, "model", None) or settings.default_model
    context_window = get_context_window(current_model)
    threshold = int(context_window * threshold_pct)

    # Count total tokens in messages
    # Note: count_messages_tokens may underestimate JSON serialization overhead
    total_tokens = count_messages_tokens(messages)

    # Add safety margin for JSON serialization overhead (tool messages are JSON strings)
    # Tool message content is JSON, which adds configurable overhead percentage vs raw content
    tool_message_count = sum(1 for m in messages if is_tool_message(m))
    if tool_message_count > 0:
        # Estimate JSON overhead: count tool message content separately and add configurable overhead
        tool_tokens_raw = sum(
            count_tokens(get_message_content(m) or "") for m in messages if is_tool_message(m)
        )
        from kg_engine.config.settings import settings

        json_overhead_pct = getattr(settings, "llm_tool_results_json_overhead_pct", 0.30)
        json_overhead = int(tool_tokens_raw * json_overhead_pct)
        total_tokens_adjusted = total_tokens + json_overhead
    else:
        total_tokens_adjusted = total_tokens

    # Log token count for debugging
    logger.info(
        "Compression check: total=%d tokens (adjusted=%d with JSON overhead), threshold=%d (%.1f%% of %d window)",
        total_tokens,
        total_tokens_adjusted,
        threshold,
        threshold_pct * 100,
        context_window,
    )

    # Check if we need compression - use adjusted count for more accurate check
    if total_tokens_adjusted <= threshold:
        return None  # All good, no changes needed

    # Find all tool message indices
    tool_message_indices = []
    for idx, msg in enumerate(messages):
        if is_tool_message(msg):
            tool_message_indices.append(idx)

    if not tool_message_indices:
        return None  # No tool messages to compress

    logger.warning(
        "Context at %d tokens (adjusted=%d, %.1f%% of %d window), compressing articles proportionally by rank",
        total_tokens,
        total_tokens_adjusted,
        100 * total_tokens_adjusted / context_window,
        context_window,
    )

    # Extract ALL articles from ALL tool messages (with deduplication by kb_id)
    all_articles_dict: dict[str, dict] = {}  # kb_id -> article dict (preserve highest rank)

    for idx in tool_message_indices:
        msg = messages[idx]
        content = get_message_content(msg)
        if not content:
            continue

        try:
            result = json.loads(content)
            articles = result.get("articles", [])

            for article in articles:
                kb_id = article.get("kb_id")
                if not kb_id:
                    continue

                # Deduplicate: keep article with highest rerank_score
                existing = all_articles_dict.get(kb_id)
                existing_score = (
                    existing.get("metadata", {}).get("rerank_score", -float("inf")) if existing else -float("inf")
                )
                new_score = article.get("metadata", {}).get("rerank_score", -float("inf"))

                if not existing or new_score > existing_score:
                    all_articles_dict[kb_id] = article

        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Failed to parse tool message %d: %s", idx, exc)
            continue

    if not all_articles_dict:
        return None

    # Convert to list and sort by rank (best first)
    all_articles = list(all_articles_dict.values())
    all_articles.sort(
        key=lambda a: a.get("metadata", {}).get("rerank_score", -float("inf")),
        reverse=True,
    )

    # Re-normalize ranks after deduplication
    if len(all_articles) > 1:
        for idx, article in enumerate(all_articles):
            # Normalized rank: 0.0 = first (best), 1.0 = last (worst)
            normalized_rank = idx / (len(all_articles) - 1)
            article.setdefault("metadata", {})["normalized_rank"] = normalized_rank
            article.setdefault("metadata", {})["article_rank"] = idx
    else:
        if all_articles:
            all_articles[0].setdefault("metadata", {})["normalized_rank"] = 0.0
            all_articles[0].setdefault("metadata", {})["article_rank"] = 0

    # Calculate target tokens - use more aggressive target to ensure we fit
    target_tokens = int(context_window * target_pct)

    # Count non-tool message tokens (conversation + system prompts)
    non_tool_tokens = sum(count_messages_tokens([m]) for m in messages if not is_tool_message(m))

    # Reserve space for LLM output/reasoning using actual system prompt and tool schemas
    from kg_engine.utils.context_tracker import compute_overhead_tokens  # noqa: I001
    from kg_engine.tools.retrieve_context import retrieve_context  # noqa: I001

    overhead_tokens = compute_overhead_tokens(tools=[retrieve_context])

    # Available budget for articles = target - conversation - LLM overhead
    available_for_articles = max(0, int(target_tokens - non_tool_tokens - overhead_tokens))

    # Log budget calculation for debugging
    logger.info(
        "Compression budget: target=%d, non_tool=%d, overhead=%d, available_for_articles=%d",
        target_tokens,
        non_tool_tokens,
        overhead_tokens,
        available_for_articles,
    )

    # If available budget is too small, reduce target more aggressively
    if available_for_articles <= 0:
        logger.warning(
            "Available budget is zero or negative (%d). Using aggressive fallback: 10%% of context window",
            available_for_articles,
        )
        available_for_articles = max(300 * len(all_articles), int(context_window * 0.10))

    # Get user question for summarization guidance
    user_question = extract_user_question(messages)

    # Log current article sizes before compression
    current_article_tokens = sum(count_tokens(a.get("content", "")) for a in all_articles)

    # Calculate tool message tokens (includes JSON structure, metadata, etc.)
    tool_message_tokens = total_tokens - non_tool_tokens

    # Count raw article content from ALL tool messages to detect any remaining duplicates
    # (Tool-level filtering should prevent duplicates, but this serves as a safety net check)
    all_raw_article_tokens = 0
    total_articles_in_tool_messages = 0
    for idx in tool_message_indices:
        msg = messages[idx]
        content = get_message_content(msg)
        if not content:
            continue
        try:
            result = json.loads(content)
            articles = result.get("articles", [])
            total_articles_in_tool_messages += len(articles)
            for article in articles:
                all_raw_article_tokens += count_tokens(article.get("content", ""))
        except (json.JSONDecodeError, Exception):
            continue

    # Calculate overhead breakdown
    # duplicate_tokens should be 0 with tool-level filtering, but useful as diagnostic
    duplicate_tokens = max(0, all_raw_article_tokens - current_article_tokens)
    json_structure_overhead = max(0, tool_message_tokens - all_raw_article_tokens)

    logger.info(
        "Articles before compression: %d unique articles (%d total in %d tool messages), "
        "%d raw content tokens (after deduplication), tool messages=%d tokens "
        "(%d remaining duplicate tokens + %d JSON/metadata overhead), target=%d tokens",
        len(all_articles),
        total_articles_in_tool_messages,
        len(tool_message_indices),
        current_article_tokens,
        tool_message_tokens,
        duplicate_tokens,
        json_structure_overhead,
        available_for_articles,
    )

    # Compress ALL articles proportionally by rank
    compressed_articles, tokens_saved = compress_all_articles_proportionally_by_rank(
        articles=all_articles,
        target_tokens=available_for_articles,
        guidance=user_question,
        llm_manager=llm_manager,
    )

    # Log compression results
    if tokens_saved > 0:
        compressed_article_tokens = sum(count_tokens(a.get("content", "")) for a in compressed_articles)
        # Calculate full context after compression (articles + non-tool messages + overhead)
        full_context_after = total_tokens - tokens_saved
        logger.info(
            "Compression result: saved %d tokens, compressed_articles=%d tokens (target was %d), "
            "full context after compression ~%d tokens",
            tokens_saved,
            compressed_article_tokens,
            available_for_articles,
            full_context_after,
        )
    else:
        logger.warning(
            "Compression saved 0 tokens. Articles may already fit or compression failed. "
            "Current: %d tokens, target: %d tokens",
            current_article_tokens,
            available_for_articles,
        )

    if tokens_saved == 0:
        # If compression didn't help but we're still over limit, force more aggressive compression
        if current_article_tokens > available_for_articles:
            logger.warning(
                "Compression didn't help but still over budget. "
                "Forcing aggressive compression to 50%% of target: %d tokens",
                int(available_for_articles * 0.5),
            )
            # Try again with even more aggressive target
            compressed_articles, tokens_saved = compress_all_articles_proportionally_by_rank(
                articles=all_articles,
                target_tokens=int(available_for_articles * 0.5),
                guidance=user_question,
                llm_manager=llm_manager,
            )
            if tokens_saved == 0:
                return None  # Still failed

    # Create mapping: kb_id -> compressed article
    compressed_by_kb_id = {a["kb_id"]: a for a in compressed_articles}

    # Track which articles we've already included to avoid duplicates across tool messages
    seen_kb_ids_in_output = set()

    # Update tool messages with compressed articles (deduplicated across all messages)
    updated_messages = list(messages)
    for idx in tool_message_indices:
        msg = updated_messages[idx]
        content = get_message_content(msg)
        if not content:
            continue

        try:
            result = json.loads(content)
            original_articles = result.get("articles", [])

            # Replace with compressed versions if available, but skip duplicates
            compressed_result_articles = []
            for orig_article in original_articles:
                kb_id = orig_article.get("kb_id")
                if not kb_id:
                    # Keep articles without kb_id (shouldn't happen, but be safe)
                    compressed_result_articles.append(orig_article)
                    continue

                # Skip if we've already included this article in a previous tool message
                if kb_id in seen_kb_ids_in_output:
                    continue  # Skip duplicate

                # Add to seen set and include compressed version
                seen_kb_ids_in_output.add(kb_id)
                if kb_id in compressed_by_kb_id:
                    compressed_result_articles.append(compressed_by_kb_id[kb_id])
                else:
                    compressed_result_articles.append(orig_article)

            result["articles"] = compressed_result_articles
            if "metadata" not in result:
                result["metadata"] = {}
            result["metadata"]["compressed_articles_count"] = sum(
                1 for a in compressed_result_articles if a.get("metadata", {}).get("compressed")
            )
            result["metadata"]["tokens_saved_by_compression"] = tokens_saved
            result["metadata"]["deduplicated"] = len(original_articles) != len(compressed_result_articles)

            # Create new compact JSON
            new_content = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
            updated_messages = update_tool_message_content(updated_messages, idx, new_content)

        except Exception as exc:
            logger.warning("Failed to update tool message %d: %s", idx, exc)
            continue

    if tokens_saved > 0:
        logger.info(
            "Proportional compression by rank complete: saved %d tokens (%.1f%% reduction), "
            "new total ~%d (%.1f%% of window)",
            tokens_saved,
            100 * tokens_saved / total_tokens,
            total_tokens - tokens_saved,
            100 * (total_tokens - tokens_saved) / context_window,
        )
        return updated_messages

    return None

