from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from kg_engine.retrieval.vector_search import top_k_search_async


@pytest.mark.asyncio
async def test_top_k_search_async_delegates_to_store():
    """Test that top_k_search_async delegates to store.similarity_search_async."""
    store = Mock()
    store.similarity_search_async = AsyncMock(return_value=["result"])

    results = await top_k_search_async(store, embedding=[0.1, 0.2], k=3)

    store.similarity_search_async.assert_called_once_with(query_embedding=[0.1, 0.2], k=3)
    assert results == ["result"]
