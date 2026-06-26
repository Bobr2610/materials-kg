<!-- a9035e3d-c636-459d-b46d-cde7ec90e22d ffe1c87f-f6da-4886-8bee-a7e08b76b94c -->
# Multi-vector + LLM Query Decomposition Retrieval

## Goals

- Add query-time multi-vector retrieval by token-aware splitting (reuse indexer splitter).
- Optionally add LLM-based query decomposition; union candidates with multi-vector.
- Global rerank caps candidate size; rest of pipeline unchanged.
- Configurable via .env variables.

## Files to Change

- `rag_engine/config/settings.py`
- `rag_engine/retrieval/retriever.py`
- Optional: `rag_engine/llm/prompts.py` (if adding a fixed tiny prompt constant for decomposition)
- Tests: `rag_engine/tests/test_retriever.py` (and/or new tests)

## Steps

1) Config: add settings for multi-vector and decomposition

- In `settings.py`, add:
  - `retrieval_multiquery_enabled: bool = env RETRIEVAL_MULTIQUERY_ENABLED`
  - `retrieval_multiquery_max_segments: int = env RETRIEVAL_MULTIQUERY_MAX_SEGMENTS`
  - `retrieval_multiquery_segment_tokens: int = env RETRIEVAL_MULTIQUERY_SEGMENT_TOKENS`
  - `retrieval_multiquery_segment_overlap: int = env RETRIEVAL_MULTIQUERY_SEGMENT_OVERLAP`
  - `retrieval_multiquery_pre_rerank_limit: int = env RETRIEVAL_MULTIQUERY_PRE_RERANK_LIMIT`
  - `retrieval_query_decomp_enabled: bool = env RETRIEVAL_QUERY_DECOMP_ENABLED`
  - `retrieval_query_decomp_max_subqueries: int = env RETRIEVAL_QUERY_DECOMP_MAX_SUBQUERIES`

2) Retriever: implement multi-vector chunking (reuse indexer splitter)

- In `retriever.py`, import `split_text` from `rag_engine/core/chunker.py`.
- Add helpers:
  - `_toklen(enc, s)` to count tokens via existing `self._encoding`.
  - `_split_query_segments(enc, query, max_seg_tokens, overlap, max_segments)` that calls `split_text` and trims hard overflows.
- In `retrieve()`, before reranking, build candidates:
  - If `multiquery_enabled` and question token length > `segment_tokens`, split into segments and run vector search per segment; de-duplicate by `stable_id`.
  - Else, run single vector search.
  - Apply `pre_rerank_limit` to cap candidate list size.

3) Optional LLM decomposition (additive)

- Add `_llm_decompose_query(llm_manager, query, max_subq)` that calls `llm_manager.generate(question=prompt, context_docs=[])` with a tiny deterministic prompt to output ≤N lines. On error, return empty.
- If `retrieval_query_decomp_enabled`, generate sub-queries, retrieve for each, union into the candidate set with de-duplication, then apply the same pre-rerank cap.

4) Rerank and continue (unchanged)

- Feed the merged candidates into the existing reranker path.
- Proceed with reading full articles and context budgeting as today.

5) Tests

- Add/extend tests in `rag_engine/tests/test_retriever.py`:
  - Multi-vector path: simulate a long query (token-counted) → ensure multiple segment searches are triggered and merged; verify dedup and pre-rerank cap behavior.
  - Single-query path: ensure exact current behavior remains when below token threshold.
  - Decomposition path: monkeypatch `LLMManager.generate` to return 2-3 sub-queries; ensure additive retrieval and dedup; verify guarded by flag.
  - Ensure reranker receives the combined candidate list; you can monkeypatch reranker to assert input size.

6) Linting

- Run Ruff on changed files only; address necessary warnings.

7) Rollout

- Default `RETRIEVAL_QUERY_DECOMP_ENABLED=false` to avoid cost unless enabled.
- Keep `RETRIEVAL_MULTIQUERY_ENABLED=true` given added caps.

8) Docs

- Update `README.md` with:
  - Overview of multi-vector retrieval and optional LLM query decomposition.
  - New .env flags, recommended ranges and defaults:
    - segment_tokens: 384–512 (default 448)
    - overlap: 32–96 (default 64)
    - max_segments: ≤ 4 (default 4)
    - pre_rerank_limit: ≈ 3×TOP_K_RETRIEVE (default 60)
  - Candidate union + rerank flow and latency caps.
  - Note that we reuse the indexer splitter for query segmentation.
  - Testing instructions for new paths.

## Robustness and Caveats

- Edge-case guards:
  - If segmentation yields exactly one segment identical to the original, skip multi-vector and run single-query path.
  - If the unioned candidate set is empty, retry once with single-query retrieval, then continue.
- Token/window safety:
  - Ensure `RETRIEVAL_MULTIQUERY_SEGMENT_TOKENS <= 512` (FRIDA limit); validate and clip in settings.
  - Use `tiktoken cl100k_base` for token counts (already present in retriever).
- Dedup keys:
  - Prefer `metadata.stable_id`; fallback to `doc.id` or `str(id(doc))` to avoid duplicates.
- Latency control:
  - Enforce `RETRIEVAL_MULTIQUERY_MAX_SEGMENTS` and `RETRIEVAL_MULTIQUERY_PRE_RERANK_LIMIT` before rerank.
  - CrossEncoder batch size unchanged; pre-cap protects inference time.
- LLM decomposition:
  - Deterministic, one-line-per-subquery prompt; catch exceptions and degrade to empty list.
  - Use `llm_manager.generate(question=..., context_docs=[])` to avoid context blow-ups; feature off by default.
- Import safety:
  - Import `split_text` from `rag_engine.core.chunker` only in `retriever.py` to avoid cycles.
- Backward compatibility:
  - With both features disabled, behavior remains unchanged.

## Key Snippets (illustrative)

- Segment split (uses our splitter):
```python
from rag_engine.core.chunker import split_text as chunker_split

def _split_query_segments(enc, query, max_seg_tokens, overlap, max_segments):
    segs = list(chunker_split(query, chunk_size=max_seg_tokens, chunk_overlap=overlap))
    out = []
    for seg in segs:
        seg = (seg or '').strip()
        if not seg:
            continue
        ids = enc.encode(seg)
        if len(ids) > max_seg_tokens:
            seg = enc.decode(ids[:max_seg_tokens])
        out.append(seg)
        if len(out) >= max_segments:
            break
    return out or [query]
```

- Candidate aggregation with pre-rerank cap:
```python
candidates, seen = [], set()

def _add_candidates_for(text):
    qv = self.embedder.embed_query(text)
    hits = top_k_search(self.store, qv, k=self.top_k_retrieve)
    for doc in hits:
        sid = getattr(doc, 'metadata', {}).get('stable_id') or getattr(doc, 'id', None) or str(id(doc))
        if sid in seen:
            continue
        seen.add(sid)
        candidates.append(doc)
```

- LLM decomposition (optional):
```python
prompt = f"Decompose the user question into at most {n} concise sub-queries (one per line). No numbering.\n\nQuestion:\n{query}\n"
subqs = llm_manager.generate(question=prompt, context_docs=[])
```

### To-dos

- [ ] Add new retrieval flags and ints in settings.py
- [ ] Implement query segmentation, multi-vector retrieval, dedup, cap
- [ ] Add optional LLM query decomposition and union retrievals
- [ ] Feed merged candidates to reranker; keep rest unchanged
- [ ] Add tests for multi-vector path and pre-rerank cap
- [ ] Add tests for LLM decomposition path (monkeypatch generate)
- [ ] Run Ruff on changed files and fix necessary issues