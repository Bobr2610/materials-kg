"""RAG retriever: search, rerank chunks, load complete articles (async only)."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

import tiktoken

from kg_engine.config.settings import settings
from kg_engine.core.chunker import split_text
from kg_engine.retrieval.reranker import create_reranker
from kg_engine.retrieval.vector_search import top_k_search_async
from kg_engine.utils.metadata_utils import extract_numeric_kbid
from kg_engine.utils.path_utils import normalize_path

logger = logging.getLogger(__name__)


class Article:
    """Complete article with metadata (loaded from source_file)."""

    def __init__(self, kb_id: str, content: str, metadata: dict[str, Any]):
        self.kb_id = kb_id
        self.content = content
        self.metadata = metadata
        self.matched_chunks: list[Any] = []  # Store matched chunks for reference
        self._is_lightweight: bool = False


class RAGRetriever:
    def __init__(
        self,
        embedder,
        vector_store,
        llm_manager,  # NEW: For dynamic context window
        top_k_retrieve: int,
        top_k_rerank: int,
        rerank_enabled: bool = True,
        rerankers: list[dict[str, Any]] | None = None,
        metadata_boost_weights: dict[str, float] | None = None,
    ):
        self.embedder = embedder
        self.store = vector_store
        self.llm_manager = llm_manager  # For dynamic context budgeting
        self.top_k_retrieve = top_k_retrieve
        self.top_k_rerank = top_k_rerank
        self.reranker = create_reranker(settings) if rerank_enabled else None
        self.metadata_boost_weights = metadata_boost_weights or {
            "tag_match": 0.0,
            "code_presence": 0.0,
            "section_match": 0.0,
        }
        self._encoding = tiktoken.get_encoding("cl100k_base")
        logger.info(
            "RAGRetriever initialized (top_k_retrieve=%d, top_k_rerank=%d, reranker=%s)",
            top_k_retrieve,
            top_k_rerank,
            "enabled" if self.reranker else "disabled",
        )

    # --- Query segmentation helpers (multi-vector retrieval) ---
    def _toklen(self, s: str) -> int:
        return len(self._encoding.encode(s or ""))

    def _split_query_segments(
        self,
        query: str,
        max_seg_tokens: int,
        overlap: int,
        max_segments: int,
    ) -> list[str]:
        # Reuse code-safe, token-aware splitter used by indexer
        segments = list(split_text(query, chunk_size=max_seg_tokens, chunk_overlap=overlap))
        out: list[str] = []
        for seg in segments:
            seg = (seg or "").strip()
            if not seg:
                continue
            ids = self._encoding.encode(seg)
            if len(ids) > max_seg_tokens:
                seg = self._encoding.decode(ids[:max_seg_tokens])
            out.append(seg)
            if len(out) >= max_segments:
                break
        # Edge guard: if we ended with a single segment equal to original, return original only
        if len(out) == 1 and out[0] == query.strip():
            return [query]
        return out or [query]

    def _llm_decompose_query(self, query: str, max_subq: int) -> list[str]:
        """Optionally decompose query via LLM into concise sub-queries.

        Uses current LLM with no context to avoid window pressure. On any
        exception, returns an empty list.
        """
        try:
            max_n = max(1, int(max_subq))
            from kg_engine.llm.prompts import QUERY_DECOMPOSITION_PROMPT

            prompt = QUERY_DECOMPOSITION_PROMPT.format(max_n=max_n, question=query)
            resp = self.llm_manager.generate(question=prompt, context_docs=[])
            if not resp:
                return []
            lines = [ln.strip("- ").strip() for ln in str(resp).splitlines()]
            subqs = [ln for ln in lines if ln]
            return subqs[:max_n]
        except Exception:
            return []

    async def retrieve_async(self, query: str, top_k: int | None = None) -> list[Article]:
        """Async: retrieve complete articles for query using hybrid approach.

        Same logic as sync retrieve(), but with parallel vector searches and
        async-friendly handling of CPU-bound embedder/reranker via asyncio.to_thread.

        Hybrid approach:
        1. Vector search on chunks (top-20) - PARALLEL for multi-query
        2. Rerank chunks (top-10)
        3. Group chunks by kbId and preserve max reranker score
        4. Read complete articles from source_file
        5. Sort by rank and normalize ranks (0.0 = best, 1.0 = worst)
        6. Return ALL articles uncompressed with ranking information

        **Returns uncompressed articles with ranking metadata.**
        **Compression happens in agent middleware (before_model), not here.**

        Args:
            query: User query string
            top_k: Override top_k_rerank if provided

        Returns:
            List of complete Article objects (uncompressed, sorted by rank)
            Each article has metadata["rerank_score"] and metadata["normalized_rank"]
        """
        qk = top_k or self.top_k_rerank

        # 1. Build candidate set via multi-vector query segmentation
        # Build list of texts to search (query segments + LLM subqueries)
        texts_to_search: list[str] = []

        use_multi = settings.retrieval_multiquery_enabled and self._toklen(query) > int(
            settings.retrieval_multiquery_segment_tokens
        )
        if use_multi:
            segs = self._split_query_segments(
                query,
                max_seg_tokens=int(settings.retrieval_multiquery_segment_tokens),
                overlap=int(settings.retrieval_multiquery_segment_overlap),
                max_segments=int(settings.retrieval_multiquery_max_segments),
            )
            # Edge guard: if segmentation collapses to original, do single path
            if len(segs) == 1 and segs[0].strip() == query.strip():
                texts_to_search = [query]
            else:
                texts_to_search = segs
        else:
            texts_to_search = [query]

        # Optional: LLM query decomposition (additive)
        if settings.retrieval_query_decomp_enabled:
            subqs = await asyncio.to_thread(
                self._llm_decompose_query,
                query,
                int(settings.retrieval_query_decomp_max_subqueries),
            )
            texts_to_search.extend(subqs)

        # 2. Embed queries and search in parallel
        # Run embedder in thread (CPU-bound)
        embedding_tasks = [
            asyncio.to_thread(self.embedder.embed_query, text) for text in texts_to_search
        ]
        query_vectors = await asyncio.gather(*embedding_tasks)

        # Run vector searches in parallel (async I/O)
        search_tasks = [
            top_k_search_async(self.store, qv, k=self.top_k_retrieve) for qv in query_vectors
        ]
        search_results = await asyncio.gather(*search_tasks)

        # Merge and dedupe candidates
        candidates: list[Any] = []
        seen_ids: set[str] = set()
        for seg_hits in search_results:
            for doc in seg_hits:
                metadata = getattr(doc, "metadata", None) or {}
                sid = metadata.get("stable_id") or getattr(doc, "id", None) or str(id(doc))
                if sid in seen_ids:
                    continue
                seen_ids.add(sid)
                candidates.append(doc)

        # If nothing found, retry single-query once
        if not candidates and texts_to_search != [query]:
            qv = await asyncio.to_thread(self.embedder.embed_query, query)
            seg_hits = await top_k_search_async(self.store, qv, k=self.top_k_retrieve)
            for doc in seg_hits:
                metadata = getattr(doc, "metadata", None) or {}
                sid = metadata.get("stable_id") or getattr(doc, "id", None) or str(id(doc))
                if sid not in seen_ids:
                    seen_ids.add(sid)
                    candidates.append(doc)

        # Pre-rerank cap to bound latency
        prl = int(getattr(settings, "retrieval_multiquery_pre_rerank_limit", 0) or 0)
        if prl > 0 and len(candidates) > prl:
            candidates = candidates[:prl]

        if not candidates:
            logger.warning("No chunks found for query")
            return []

        logger.info("Retrieved %d chunks from vector store", len(candidates))

        # 3. Rerank chunks (run in thread since reranker is CPU-bound)
        scored_candidates: list[tuple[Any, float]] = [(doc, 0.0) for doc in candidates]
        if self.reranker is not None and candidates:
            scored_candidates = await asyncio.to_thread(
                self.reranker.rerank,
                query,
                scored_candidates,
                top_k=qk,
                metadata_boost_weights=self.metadata_boost_weights,
            )
            logger.info("Reranked to top-%d chunks", len(scored_candidates))
        else:
            scored_candidates = scored_candidates[:qk]
            logger.info("No reranking, using top-%d chunks", len(scored_candidates))

        # 4. Group chunks by kb_id and preserve MAX reranker score as article rank
        articles_map: dict[str, tuple[list[Any], float]] = defaultdict(lambda: ([], -float("inf")))
        for doc, score in scored_candidates:
            metadata = getattr(doc, "metadata", None) or {}
            raw_kb_id = metadata.get("kbId", "")
            if raw_kb_id:
                kb_id = extract_numeric_kbid(raw_kb_id) or str(raw_kb_id)
                chunks, best_score = articles_map[kb_id]
                chunks.append(doc)
                articles_map[kb_id] = (chunks, max(best_score, score))

        logger.info("Top chunks belong to %d unique articles", len(articles_map))

        # Filter by score threshold before loading articles from disk
        # Only apply threshold when reranker is enabled (scores are meaningful)
        if self.reranker is not None:
            threshold = settings.rerank_score_threshold
            if threshold is not None:
                articles_map = {
                    kb_id: (chunks, score)
                    for kb_id, (chunks, score) in articles_map.items()
                    if score >= threshold
                }
                logger.info(
                    "Filtered to %d articles with rerank_score >= %.2f",
                    len(articles_map),
                    threshold,
                )
        else:
            logger.info("Reranker disabled, skipping score threshold filter")

        if not articles_map:
            logger.warning("No articles passed score threshold")
            return []

        # 5. Read complete articles and attach ranking information
        articles: list[Article] = []
        for kb_id, (chunks, max_score) in articles_map.items():
            first_chunk_meta = getattr(chunks[0], "metadata", None) or {}
            source_file = first_chunk_meta.get("source_file")
            if not source_file:
                logger.warning("No source_file for kbId=%s", kb_id)
                continue

            try:
                article_content = await asyncio.to_thread(self._read_article, source_file)
                article_metadata = dict(first_chunk_meta)
                if "article_url" not in article_metadata:
                    frontmatter_url = article_metadata.get("url")
                    if frontmatter_url:
                        article_metadata["article_url"] = str(frontmatter_url)
                    else:
                        raw_kbid = article_metadata.get("kbId") or kb_id
                        kbid = extract_numeric_kbid(raw_kbid) or str(raw_kbid) if raw_kbid else None
                        if kbid is not None:
                            article_metadata["article_url"] = (
                                f"https://kb.comindware.ru/article.php?id={kbid}"
                            )

                article = Article(
                    kb_id=kb_id,
                    content=article_content,
                    metadata=article_metadata,
                )
                article.matched_chunks = chunks
                article.metadata["rerank_score"] = max_score
                articles.append(article)
            except Exception as exc:
                logger.error("Failed to read article %s: %s", source_file, exc)
                continue

        logger.info("Loaded %d complete articles", len(articles))

        # 6. Sort and normalize ranks
        articles.sort(key=lambda a: a.metadata.get("rerank_score", -float("inf")), reverse=True)

        if len(articles) > 1:
            for idx, article in enumerate(articles):
                article.metadata["normalized_rank"] = idx / (len(articles) - 1)
                article.metadata["article_rank"] = idx
        else:
            if articles:
                articles[0].metadata["normalized_rank"] = 0.0
                articles[0].metadata["article_rank"] = 0

        logger.info("Loaded %d complete articles (uncompressed, sorted by rank)", len(articles))
        return articles

    def _read_article(self, source_file: str) -> str:
        """Read complete article from filesystem.

        Args:
            source_file: Absolute or relative path to article file
                         (may contain Windows-style backslashes)

        Returns:
            Complete article content (without frontmatter)
        """
        # Normalize path to handle Windows-style backslashes on POSIX systems
        file_path = normalize_path(source_file)
        if not file_path.exists():
            raise FileNotFoundError(f"Article file not found: {source_file}")

        content = file_path.read_text(encoding="utf-8")

        # Remove YAML frontmatter if present
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()

        return content
