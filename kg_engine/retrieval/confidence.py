"""Retrieval confidence metrics from reranker scores.

This module is intentionally lightweight: it returns plain dicts (no extra schemas)
so we can attach small numeric signals to trace outputs without bloating payloads.
"""

from __future__ import annotations

from statistics import median
from typing import Any


def compute_retrieval_confidence(
    scored_chunks: list[tuple[Any, float]],
    *,
    relevance_threshold: float | None = None,
    mean_top_k: int = 5,
) -> dict[str, Any]:
    """Compute query-level confidence metrics from reranker scores.

    Args:
        scored_chunks: List of (chunk, rerank_score) tuples (typically already top-k).
        relevance_threshold: Score above which a chunk is considered likely relevant.
            If None, defaults to 0.5.
        mean_top_k: How many top scores to average for mean_top_k metric.

    Returns:
        Dict with:
        - top_score: max score
        - mean_top_k: average of top-N scores
        - score_gap: top_score - median_score
        - n_above_threshold: count of scores >= relevance_threshold
        - likely_relevant: heuristic boolean
    """
    threshold = 0.5 if relevance_threshold is None else float(relevance_threshold)

    scores = [float(s) for _, s in scored_chunks if s is not None]
    if not scores:
        return {
            "top_score": 0.0,
            "mean_top_k": 0.0,
            "score_gap": 0.0,
            "n_above_threshold": 0,
            "likely_relevant": False,
        }

    scores_sorted = sorted(scores, reverse=True)
    top_score = scores_sorted[0]
    top_n = scores_sorted[: max(1, int(mean_top_k))]
    mean_top = sum(top_n) / len(top_n) if top_n else 0.0
    med = float(median(scores_sorted))
    gap = top_score - med
    n_above = sum(1 for s in scores_sorted if s >= threshold)

    # Conservative heuristic: require at least one above threshold and some separation.
    likely = bool(top_score >= threshold and (gap >= 0.05 or n_above >= 2))

    return {
        "top_score": top_score,
        "mean_top_k": mean_top,
        "score_gap": gap,
        "n_above_threshold": n_above,
        "likely_relevant": likely,
    }


def compute_normalized_confidence_from_traces(query_traces: list[dict]) -> float | None:
    """Compute normalized average confidence from query traces.

    Extracts top_score from each query trace's confidence dict, normalizes
    them to 0.0-1.0 range (preserving relative differences), and returns
    the average. This handles reranker scores that can exceed 1.0 due to
    metadata boosts.

    Args:
        query_traces: List of query trace dicts with 'confidence' key containing
                     dict with 'top_score' value.

    Returns:
        Normalized average confidence (0.0-1.0) or None if no valid scores found.

    Example:
        >>> traces = [
        ...     {"confidence": {"top_score": 0.8}},
        ...     {"confidence": {"top_score": 1.0}},
        ...     {"confidence": {"top_score": 1.2}},
        ... ]
        >>> compute_normalized_confidence_from_traces(traces)
        0.5  # Normalized: [0.0, 0.5, 1.0] -> avg = 0.5
    """
    if not query_traces:
        return None

    raw_scores = []
    for trace in query_traces:
        conf = trace.get("confidence") if isinstance(trace, dict) else None
        if isinstance(conf, dict):
            top_score = conf.get("top_score")
            if isinstance(top_score, (int, float)):
                raw_scores.append(float(top_score))

    if not raw_scores:
        return None

    # Normalize scores to 0.0-1.0 range while preserving relative differences
    min_score = min(raw_scores)
    max_score = max(raw_scores)

    if max_score > min_score:
        # Normalize: (score - min) / (max - min)
        normalized_scores = [(s - min_score) / (max_score - min_score) for s in raw_scores]
    else:
        # All scores are the same, use 0.5 as neutral value
        normalized_scores = [0.5] * len(raw_scores)

    return sum(normalized_scores) / len(normalized_scores)

