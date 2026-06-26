from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from kg_engine.utils.metadata_utils import extract_numeric_kbid


def _normalize_url(url: str | None) -> str:
    if not url:
        return ""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(str(url).strip())
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = (parsed.path or "").rstrip("/")
        # Keep query (contains kbId), drop only fragment for dedup
        query = f"?{parsed.query}" if parsed.query else ""
        return f"{scheme}://{netloc}{path}{query}"
    except Exception:
        return str(url or "").strip()


def _deduplicate_articles(articles: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """Deduplicate articles by kbId/URL, preserving order.

    Returns:
        Dict mapping normalized kbId/URL to article metadata.
    """
    seen_kbids: dict[str, dict[str, Any]] = {}
    seen_urls: set[str] = set()
    for d in articles:
        meta: dict[str, Any] = getattr(d, "metadata", {}) or {}
        kbid = meta.get("kbId") or getattr(d, "kb_id", None)
        url = meta.get("url") or meta.get("article_url")
        norm_url = _normalize_url(url)

        # Always deduplicate by normalized URL first (prevents identical links repeating)
        if norm_url:
            if norm_url in seen_urls:
                continue
            seen_urls.add(norm_url)

        if kbid:
            # Normalize kbId for consistent deduplication (handles suffixed kbIds)
            normalized_kbid = extract_numeric_kbid(str(kbid)) or str(kbid)
            if normalized_kbid not in seen_kbids:
                seen_kbids[normalized_kbid] = meta
        else:
            if norm_url:
                # Use a synthetic key to preserve ordering when kbId is missing
                if norm_url not in seen_kbids:
                    seen_kbids[norm_url] = meta
    return seen_kbids


def format_sources_list(articles: Iterable[Any]) -> str:
    """Format articles as numbered markdown list with titles and URLs.

    Deduplicates by kbId to ensure each article is cited only once.

    Assumptions:
    - metadata contains numeric kbId (enforced by indexer)
    - metadata may already contain a canonical 'url' or precomputed 'article_url'

    Returns:
        "\\n\\n## Источники:\\n\\n1. [title](url)\\n2. [title](url)..." or empty string.
    """
    seen_kbids = _deduplicate_articles(articles)

    citations: list[str] = []
    for i, (kbid, meta) in enumerate(seen_kbids.items(), 1):
        title = meta.get("title") or kbid or f"Source {i}"

        # 1) explicit URL from frontmatter/metadata
        url = meta.get("url")
        # 2) or precomputed article_url
        if not url:
            url = meta.get("article_url")
        # 3) or construct from numeric kbId (normalize to handle edge cases)
        if not url and kbid:
            normalized_kbid = extract_numeric_kbid(str(kbid))
            if normalized_kbid:
                url = f"https://kb.comindware.ru/article.php?id={normalized_kbid}"

        # Append anchor only if we have a base URL and the base doesn't already include one
        anchor = meta.get("section_anchor") or ""
        full_url = f"{url}{anchor}" if (url and ("#" not in str(url))) else (url or "")

        link = f"[{title}]({full_url})" if full_url else title
        citations.append(f"{i}. {link}")

    if citations:
        return "\n\n## Источники:\n\n" + "\n".join(citations)
    return ""


def format_with_citations(answer: str, articles: Iterable[Any]) -> str:
    """Format answer with sources list appended.

    Returns answer with "## Источники:" section if articles exist.
    """
    sources = format_sources_list(articles)
    return answer + sources if sources else answer
