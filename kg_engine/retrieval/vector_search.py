"""Vector search wrapper (async only)."""

from __future__ import annotations

from typing import Any, List


async def top_k_search_async(store, embedding: List[float], k: int) -> List[Any]:
    """Async: return top-k results from the vector store by query embedding."""
    return await store.similarity_search_async(query_embedding=embedding, k=k)
