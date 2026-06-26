"""Formatting helpers for batch (Excel) outputs and UI debug panels."""

from __future__ import annotations

import logging
from typing import Any

from kg_engine.llm.prompts import AI_DISCLAIMER

logger = logging.getLogger(__name__)


def _md_link(label: str, url: str | None) -> str:
    if url:
        return f"[{label}]({url})"
    return label


def format_articles_column_from_trace(
    query_results: list[dict], top_k: int, final_articles: list[dict] | None = None
) -> str:
    """Format 'Статьи' column from per-query trace dicts.

    Args:
        query_results: List of per-query trace dicts with 'query' and 'articles' keys.
        top_k: Maximum number of articles to show per query and in final list.
        final_articles: Optional final deduplicated articles list (from StructuredAgentResult.final_articles).
    """
    lines: list[str] = []
    for qi, qr in enumerate(query_results or [], start=1):
        q = qr.get("query", "")
        lines.append(f"Запрос {qi}: {q}".rstrip())
        arts = (qr.get("articles") or [])[: max(0, int(top_k))]
        for a in arts:
            kb_id = a.get("kb_id", "")
            title = a.get("title", kb_id) or kb_id or "Untitled"
            url = a.get("url", "")
            # Extract relevancy score (rerank_score) from article metadata
            rerank_score = a.get("rerank_score")
            # Use 4 decimal places to show small reranker scores (typically 0.001-0.01 range)
            relevancy_str = f" (релевантность: {rerank_score:.4f})" if rerank_score is not None and isinstance(rerank_score, (int, float)) else ""
            label = f"{kb_id} - {title}{relevancy_str}".strip(" -")
            lines.append(f"- {_md_link(label, url)}")
        lines.append("")

    # Add final deduplicated articles list if provided
    if final_articles:
        lines.extend(["", "Итоговый набор статей:"])
        for a in (final_articles or [])[: max(0, int(top_k))]:
            kb_id = a.get("kb_id", "")
            title = a.get("title", kb_id) or kb_id or "Untitled"
            url = a.get("url") or (a.get("metadata", {}) or {}).get("article_url") or (a.get("metadata", {}) or {}).get("url")
            # Extract relevancy score from metadata - check both direct access and nested metadata
            metadata = a.get("metadata", {}) or {}
            # Try multiple ways to get rerank_score (it might be in different places)
            rerank_score = (
                metadata.get("rerank_score")
                or a.get("rerank_score")  # Direct access (for query_traces format)
                or None
            )
            # Log for debugging if score is missing or zero
            if rerank_score is None:
                logger.debug(
                    "format_articles_column_from_trace: kb_id=%s, rerank_score missing in metadata keys: %s",
                    kb_id,
                    list(metadata.keys()) if isinstance(metadata, dict) else "not a dict",
                )
            elif rerank_score == 0.0:
                logger.debug(
                    "format_articles_column_from_trace: kb_id=%s, rerank_score is 0.0 (metadata keys: %s)",
                    kb_id,
                    list(metadata.keys()) if isinstance(metadata, dict) else "not a dict",
                )
            # Show relevancy score if available (even if 0.0, to help debug)
            # Use 4 decimal places to show small reranker scores (typically 0.001-0.01 range)
            if rerank_score is not None and isinstance(rerank_score, (int, float)):
                relevancy_str = f" (релевантность: {rerank_score:.4f})"
            else:
                relevancy_str = ""
            label = f"{kb_id} - {title}{relevancy_str}".strip(" -")
            lines.append(f"- {_md_link(label, url)}")
    return "\n".join(lines).strip() + "\n"


def format_chunks_column_from_trace(
    query_results: list[dict], max_chars: int = 100, final_articles: list[dict] | None = None
) -> str:
    """Format 'Найденные чанки' column from per-query trace dicts.

    Args:
        query_results: List of per-query trace dicts with 'query', 'articles', and 'chunks' keys.
        max_chars: Maximum characters to show per chunk snippet.
        final_articles: Optional final articles list (used for fallback when query_results is empty).
    """
    #lines: list[str] = ["Найденные чанки:", ""]
    lines: list[str] = []

    if not query_results:
        # Fallback: if no query traces, show a diagnostic message
        if final_articles:
            lines.append("Запросы не зафиксированы в trace (query_traces пуст).")
            lines.append("")
            lines.append("Найденные статьи (без деталей чанков):")
            for a in (final_articles or [])[:10]:  # Show up to 10 articles
                kb_id = a.get("kb_id", "") or ""
                title = a.get("title", kb_id) or kb_id or "Untitled"
                lines.append(f"- kbId {kb_id}: {title}")
        else:
            lines.append("Данные о чанках недоступны (query_traces пуст, final_articles пуст).")
        return "\n".join(lines).strip() + "\n"

    for qi, qr in enumerate(query_results or [], start=1):
        q = qr.get("query", "")
        lines.append(f"Запрос {qi}: {q}".rstrip())

        for a in qr.get("articles", []) or []:
            kb_id = a.get("kb_id", "") or ""
            lines.append(f"- kbId {kb_id}:")
            chunks = a.get("chunks") or []
            if not chunks:
                lines.append("   - [chunk1:0] ...")
                continue

            def _emit(idx: int, ch: dict) -> None:
                snippet = str(ch.get("snippet", "") or "")
                norm = " ".join(snippet.split())
                trimmed = norm[:max_chars]
                suffix = "..." if len(norm) > max_chars else ""
                score = ch.get("rerank_score_raw")
                score_str = f" (score: {score:.3f})" if score is not None else ""
                lines.append(f"   - [chunk{idx}:{max_chars}]{score_str} {trimmed}{suffix}")

            if len(chunks) <= 3:
                for i, ch in enumerate(chunks, 1):
                    _emit(i, ch)
            else:
                for i, ch in enumerate(chunks[:2], 1):
                    _emit(i, ch)
                lines.append("   …")
                _emit(len(chunks), chunks[-1])
        lines.append("")

    #lines.append("Чанки тоже ранжировать")
    return "\n".join(lines).strip() + "\n"


def build_answer_column_from_result(result: Any, top_k: int = 5) -> str:
    """Build 'Ответ на обращение' column from StructuredAgentResult-like object."""
    # result.answer_text is already grounded with citations; we prepend disclaimer and helpful boilerplate.
    articles = getattr(result, "final_articles", []) or []
    lines: list[str] = [AI_DISCLAIMER.strip(), ""]
    lines.append("Если ответ не помог — обратитесь в техподдержку.")
    lines.append("")
    lines.append("Перечень рекомендованных статей:")
    for a in articles[: max(0, int(top_k))]:
        kb_id = a.get("kb_id", "")
        title = a.get("title", kb_id) or kb_id or "Untitled"
        url = a.get("url") or (a.get("metadata", {}) or {}).get("article_url") or (a.get("metadata", {}) or {}).get("url")
        label = f"{kb_id} - {title}".strip(" -")
        lines.append(f"- {_md_link(label, url)}")
    lines.append("")
    lines.append(getattr(result, "answer_text", "") or "")
    return "\n".join(lines).strip() + "\n"

