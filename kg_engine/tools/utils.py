"""Utility functions for working with LangChain tool results.

This module contains utilities specific to parsing and processing tool results.
For generic message handling utilities (content extraction, type checking, etc.),
see kg_engine.utils.message_utils.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from kg_engine.retrieval.retriever import Article

logger = logging.getLogger(__name__)


def parse_tool_result_to_articles(tool_result: str) -> list[Article]:
    """Parse retrieve_context tool JSON result into Article objects.

    Args:
        tool_result: JSON string from retrieve_context tool

    Returns:
        List of Article objects

    Example:
        >>> result_json = retrieve_context.invoke({"query": "test"})
        >>> articles = parse_tool_result_to_articles(result_json)
        >>> # Use articles with LLM or format_with_citations
    """
    # Defensive check for empty or None tool results
    if not tool_result or not tool_result.strip():
        logger.debug("Empty tool result")
        return []

    try:
        result = json.loads(tool_result)
    except json.JSONDecodeError as e:
        logger.debug(
            "Partial JSON (len=%d, pos=%d): %.30r...", len(tool_result), e.pos, tool_result
        )
        return []

    if not isinstance(result, dict):
        logger.warning(
            "Tool result for article extraction is not a JSON object "
            "(expected retrieve_context shape), got %s: %.60r",
            type(result).__name__,
            result,
        )
        return []

    articles = []
    for article_data in result.get("articles", []):
        try:
            articles.append(
                Article(
                    kb_id=article_data["kb_id"],
                    content=article_data["content"],
                    metadata=article_data["metadata"],
                )
            )
        except KeyError as e:
            logger.warning("Skip malformed article (missing '%s'): %.60r", e.args[0], article_data)
    return articles


def accumulate_articles_from_tool_results(tool_results: list[str]) -> list[Article]:
    """Accumulate articles from multiple retrieve_context tool calls.

    This function collects articles from multiple tool invocations and deduplicates
    them by kb_id to prevent the LLM from seeing the same article content multiple times.
    This is critical when the agent makes similar queries that return overlapping results.

    Deduplication strategy:
    - Primary key: kb_id (unique article identifier)
    - When duplicate found, keeps article with highest rerank_score
    - Maintains ordering by best score first

    Args:
        tool_results: List of JSON strings from retrieve_context tool calls

    Returns:
        Deduplicated list of Article objects from all tool calls

    Example:
        >>> # LLM makes multiple tool calls with overlapping results
        >>> result1 = retrieve_context.invoke({"query": "authentication"})
        >>> # Returns: Article A (score: 0.8), B, C
        >>> result2 = retrieve_context.invoke({"query": "user authentication"})
        >>> # Returns: Article A (score: 0.9), D, E (A is duplicate with better score!)
        >>>
        >>> # Accumulate and deduplicate
        >>> all_articles = accumulate_articles_from_tool_results([result1, result2])
        >>> # Returns: Article A (score: 0.9), B, C, D, E (A with best score kept!)
        >>>
        >>> # Use with LLM - no duplicate content in context
        >>> answer = llm_manager.generate(question, all_articles)
        >>> final = format_with_citations(answer, all_articles)
    """
    # Use dict to track best article per kb_id (by rerank_score)
    articles_dict: dict[str, Article] = {}

    for tool_result in tool_results:
        articles = parse_tool_result_to_articles(tool_result)

        for article in articles:
            if not article.kb_id:
                # If no kb_id, preserve the article (rare edge case)
                # Use a unique key to avoid collisions
                unique_key = f"_no_kbid_{len(articles_dict)}"
                articles_dict[unique_key] = article
                continue

            existing = articles_dict.get(article.kb_id)
            if existing is None:
                # First occurrence - keep it
                articles_dict[article.kb_id] = article
            else:
                # Duplicate found - keep article with higher rerank_score
                existing_score = (existing.metadata or {}).get("rerank_score", -float("inf"))
                new_score = (article.metadata or {}).get("rerank_score", -float("inf"))
                logger.debug(
                    "Deduplication: kb_id=%s, existing_score=%.4f, new_score=%.4f",
                    article.kb_id,
                    existing_score,
                    new_score,
                )
                if new_score > existing_score:
                    articles_dict[article.kb_id] = article

    total_articles = sum(len(parse_tool_result_to_articles(r)) for r in tool_results)
    duplicates_removed = total_articles - len(articles_dict)

    # Sort by rerank_score (best first) to maintain quality ordering
    accumulated = list(articles_dict.values())
    accumulated.sort(
        key=lambda a: (a.metadata or {}).get("rerank_score", -float("inf")),
        reverse=True,
    )

    logger.info(
        "Accumulated %d unique articles from %d tool call(s) (removed %d duplicates)",
        len(accumulated),
        len(tool_results),
        duplicates_removed,
    )

    return accumulated


def extract_metadata_from_tool_result(tool_result: str) -> dict[str, Any]:
    """Extract metadata from retrieve_context tool result.

    Args:
        tool_result: JSON string from retrieve_context tool

    Returns:
        Metadata dict containing query, articles_count, has_results, etc.

    Example:
        >>> result = retrieve_context.invoke({"query": "test"})
        >>> meta = extract_metadata_from_tool_result(result)
        >>> print(f"Found {meta['articles_count']} articles")
    """
    try:
        result = json.loads(tool_result)
    except json.JSONDecodeError:
        logger.error(
            "Failed to parse retrieve_context tool result metadata (invalid JSON)"
        )
        return {}

    if not isinstance(result, dict):
        logger.warning(
            "Tool result for metadata extraction is not a JSON object "
            "(expected retrieve_context shape), got %s: %.60r",
            type(result).__name__,
            result,
        )
        return {}

    return result.get("metadata", {})
