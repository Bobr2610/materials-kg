"""Tests for RAG retriever with async implementation."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from kg_engine.retrieval.retriever import Article, RAGRetriever


class TestArticle:
    """Tests for Article class."""

    def test_article_initialization(self):
        article = Article(
            kb_id="test_article",
            content="Full article content here",
            metadata={"title": "Test", "source_file": "/path/to/file.md"},
        )
        assert article.kb_id == "test_article"
        assert article.content == "Full article content here"
        assert article.metadata["title"] == "Test"
        assert article.matched_chunks == []


class TestRAGRetrieverAsync:
    """Tests for async RAG retriever with complete article loading."""

    @pytest.fixture
    def mock_llm_manager(self):
        """Mock LLM manager with dynamic token limits."""
        manager = Mock()
        manager.get_current_llm_context_window.return_value = 100000
        manager.get_max_output_tokens.return_value = 32768
        manager.get_system_prompt.return_value = "SYS"

        class _FakeModel:
            def invoke(self, messages):  # noqa: ANN001
                return type("Resp", (), {"content": "summary"})()

        manager._chat_model.return_value = _FakeModel()
        return manager

    @pytest.fixture
    def mock_embedder(self):
        """Mock embedder with async support."""
        embedder = Mock()
        embedder.embed_query.return_value = [0.1] * 768
        embedder.embed_documents.return_value = [[0.1] * 768]
        return embedder

    @pytest.fixture
    def mock_vector_store(self):
        """Mock vector store with async methods."""
        store = Mock()
        store.similarity_search_async = AsyncMock()
        return store

    @pytest.fixture
    def retriever(self, mock_embedder, mock_vector_store, mock_llm_manager):
        """Create retriever with mocks."""
        return RAGRetriever(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
            llm_manager=mock_llm_manager,
            top_k_retrieve=20,
            top_k_rerank=10,
            rerank_enabled=False,
        )

    def test_initialization(self, retriever, mock_llm_manager):
        """Test retriever initializes correctly."""
        assert retriever.llm_manager == mock_llm_manager
        assert retriever.top_k_retrieve == 20
        assert retriever.top_k_rerank == 10
        assert retriever.reranker is None

    @pytest.mark.asyncio
    async def test_retrieve_async_returns_articles(self, retriever, tmp_path):
        """Test async retrieve returns Article objects."""
        # Create test file
        test_file = tmp_path / "article.md"
        test_file.write_text("Complete article content")

        # Mock chunk results
        mock_chunk = Mock()
        mock_chunk.metadata = {
            "kbId": "test_article",
            "source_file": str(test_file),
            "title": "Test Article",
        }
        mock_chunk.page_content = "chunk content"

        # Setup async mock
        retriever.store.similarity_search_async = AsyncMock(return_value=[mock_chunk])

        # Retrieve using async
        articles = await retriever.retrieve_async("test query")

        # Verify
        assert len(articles) >= 1
        assert isinstance(articles[0], Article)
        assert articles[0].content == "Complete article content"
        assert articles[0].kb_id == "test_article"

    @pytest.mark.asyncio
    async def test_retrieve_async_no_results(self, retriever):
        """Test async retrieve returns empty list when no chunks found."""
        retriever.store.similarity_search_async = AsyncMock(return_value=[])

        articles = await retriever.retrieve_async("test query")

        assert articles == []

    @pytest.mark.asyncio
    async def test_retrieve_async_groups_by_kbid(self, retriever, tmp_path):
        """Test async chunks from same article are grouped."""
        # Create test file
        test_file = tmp_path / "article.md"
        test_file.write_text("Article content")

        # Mock 3 chunks from same article
        chunks = []
        for i in range(3):
            chunk = Mock()
            chunk.metadata = {
                "kbId": "article_1",
                "source_file": str(test_file),
                "chunk_index": i,
            }
            chunk.page_content = f"chunk {i}"
            chunks.append(chunk)

        retriever.store.similarity_search_async = AsyncMock(return_value=chunks)

        # Retrieve
        articles = await retriever.retrieve_async("test query")

        # Should return 1 article (not 3 chunks)
        assert len(articles) == 1
        assert isinstance(articles[0], Article)
        assert len(articles[0].matched_chunks) == 3

    @pytest.mark.asyncio
    async def test_retrieve_async_multiple_articles(self, retriever, tmp_path):
        """Test async retrieving multiple articles from different sources."""
        # Create 2 test files
        file1 = tmp_path / "article1.md"
        file1.write_text("Article 1 content")
        file2 = tmp_path / "article2.md"
        file2.write_text("Article 2 content")

        # Mock chunks from different articles
        chunk1 = Mock()
        chunk1.metadata = {
            "kbId": "article_1",
            "source_file": str(file1),
        }
        chunk1.page_content = "chunk1"

        chunk2 = Mock()
        chunk2.metadata = {
            "kbId": "article_2",
            "source_file": str(file2),
        }
        chunk2.page_content = "chunk2"

        retriever.store.similarity_search_async = AsyncMock(return_value=[chunk1, chunk2])

        # Retrieve
        articles = await retriever.retrieve_async("test query")

        # Should have 2 distinct articles
        assert len(articles) == 2
        kb_ids = {a.kb_id for a in articles}
        assert kb_ids == {"article_1", "article_2"}

    @pytest.mark.asyncio
    async def test_retrieve_async_normalizes_kbid(self, retriever, tmp_path):
        """Test that async chunks with suffixed kbIds are normalized and grouped."""
        # Create test file
        test_file = tmp_path / "article.md"
        test_file.write_text("Article content")

        # Mock chunks with suffixed kbIds that should normalize to the same kbId
        chunk1 = Mock()
        chunk1.metadata = {
            "kbId": "4578-toc",
            "source_file": str(test_file),
        }
        chunk1.page_content = "chunk1"

        chunk2 = Mock()
        chunk2.metadata = {
            "kbId": "4578",
            "source_file": str(test_file),
        }
        chunk2.page_content = "chunk2"

        retriever.store.similarity_search_async = AsyncMock(return_value=[chunk1, chunk2])

        # Retrieve
        articles = await retriever.retrieve_async("test query")

        # Should group both chunks into 1 article with normalized kbId
        assert len(articles) == 1
        assert articles[0].kb_id == "4578"
        assert len(articles[0].matched_chunks) == 2

    @pytest.mark.asyncio
    async def test_retrieve_async_preserves_ranks(self, retriever, tmp_path):
        """Test that async retrieve() preserves reranker scores and ranks."""
        # Create test files
        file1 = tmp_path / "article1.md"
        file1.write_text("Article content")

        # Create chunks with different scores
        chunk1 = Mock()
        chunk1.metadata = {
            "kbId": "123",
            "source_file": str(file1),
            "title": "Article 1",
        }
        chunk1.page_content = "chunk 1"

        chunk2 = Mock()
        chunk2.metadata = {
            "kbId": "456",
            "source_file": str(file1),
            "title": "Article 2",
        }
        chunk2.page_content = "chunk 2"

        retriever.store.similarity_search_async = AsyncMock(return_value=[chunk1, chunk2])

        # Mock reranker
        if retriever.reranker is None:
            retriever.reranker = MagicMock()

        # Mock reranker to return different scores
        with patch.object(retriever.reranker, "rerank") as mock_rerank:
            mock_rerank.return_value = [
                (chunk2, 0.9),
                (chunk1, 0.7),
            ]

            articles = await retriever.retrieve_async("test query")

            # Should have 2 articles
            assert len(articles) == 2

            # Articles should be sorted by rerank_score
            assert articles[0].metadata["rerank_score"] == 0.9
            assert articles[1].metadata["rerank_score"] == 0.7

            # Normalized ranks should be calculated
            assert articles[0].metadata["normalized_rank"] == 0.0
            assert articles[1].metadata["normalized_rank"] == 1.0

    def test_read_article_success(self, retriever, tmp_path):
        """Test reading article from file."""
        test_file = tmp_path / "test_article.md"
        test_file.write_text("---\ntitle: Test\n---\n\nArticle content here")

        content = retriever._read_article(str(test_file))

        assert content == "Article content here"
        assert "---" not in content

    def test_read_article_no_frontmatter(self, retriever, tmp_path):
        """Test reading article without frontmatter."""
        test_file = tmp_path / "simple.md"
        test_file.write_text("Just content")

        content = retriever._read_article(str(test_file))

        assert content == "Just content"

    def test_read_article_file_not_found(self, retriever):
        """Test error handling for missing file."""
        with pytest.raises(FileNotFoundError):
            retriever._read_article("/nonexistent/file.md")


class TestRAGRetrieverScoreThreshold:
    """Tests for rerank score threshold filtering."""

    @pytest.fixture
    def mock_llm_manager(self):
        """Mock LLM manager."""
        manager = Mock()
        manager.get_current_llm_context_window.return_value = 100000
        return manager

    @pytest.fixture
    def mock_embedder(self):
        """Mock embedder."""
        embedder = Mock()
        embedder.embed_query.return_value = [0.1] * 768
        return embedder

    @pytest.fixture
    def mock_vector_store(self):
        """Mock vector store."""
        store = Mock()
        store.similarity_search_async = AsyncMock()
        return store

    @pytest.fixture
    def retriever_with_threshold(self, mock_embedder, mock_vector_store, mock_llm_manager):
        """Create retriever with score threshold enabled."""
        import kg_engine.retrieval.retriever as retriever_module

        retriever = RAGRetriever(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
            llm_manager=mock_llm_manager,
            top_k_retrieve=20,
            top_k_rerank=10,
            rerank_enabled=True,
        )
        retriever.reranker = MagicMock()

        original_threshold = retriever_module.settings.rerank_score_threshold
        retriever_module.settings.rerank_score_threshold = 0.5

        yield retriever

        retriever_module.settings.rerank_score_threshold = original_threshold

    @pytest.mark.asyncio
    async def test_threshold_filters_low_scores(self, retriever_with_threshold, tmp_path):
        """Test that articles below threshold are filtered out."""
        file1 = tmp_path / "article1.md"
        file1.write_text("Article 1 content")
        file2 = tmp_path / "article2.md"
        file2.write_text("Article 2 content")
        file3 = tmp_path / "article3.md"
        file3.write_text("Article 3 content")

        chunk1 = Mock()
        chunk1.metadata = {"kbId": "high_score", "source_file": str(file1)}
        chunk1.page_content = "chunk1"

        chunk2 = Mock()
        chunk2.metadata = {"kbId": "low_score", "source_file": str(file2)}
        chunk2.page_content = "chunk2"

        chunk3 = Mock()
        chunk3.metadata = {"kbId": "medium_score", "source_file": str(file3)}
        chunk3.page_content = "chunk3"

        retriever_with_threshold.store.similarity_search_async = AsyncMock(
            return_value=[chunk1, chunk2, chunk3]
        )

        async def mock_rerank(*args, **kwargs):
            return [
                (chunk1, 0.9),
                (chunk2, 0.1),
                (chunk3, 0.5),
            ]

        original_to_thread = asyncio.to_thread

        async def patched_to_thread(func, *args, **kwargs):
            if func == retriever_with_threshold.reranker.rerank:
                return await mock_rerank(*args, **kwargs)
            return await original_to_thread(func, *args, **kwargs)

        asyncio.to_thread = patched_to_thread

        try:
            articles = await retriever_with_threshold.retrieve_async("test query")

            assert len(articles) == 2
            kb_ids = {a.kb_id for a in articles}
            assert "high_score" in kb_ids
            assert "medium_score" in kb_ids
            assert "low_score" not in kb_ids
        finally:
            asyncio.to_thread = original_to_thread

    @pytest.mark.asyncio
    async def test_threshold_edge_case_all_filtered(self, retriever_with_threshold, tmp_path):
        """Test behavior when all articles are below threshold."""
        file1 = tmp_path / "article1.md"
        file1.write_text("Article 1")

        chunk1 = Mock()
        chunk1.metadata = {"kbId": "123", "source_file": str(file1)}
        chunk1.page_content = "chunk1"

        retriever_with_threshold.store.similarity_search_async = AsyncMock(return_value=[chunk1])

        async def mock_rerank(*args, **kwargs):
            return [
                (chunk1, 0.1),
            ]

        original_to_thread = asyncio.to_thread

        async def patched_to_thread(func, *args, **kwargs):
            if func == retriever_with_threshold.reranker.rerank:
                return await mock_rerank(*args, **kwargs)
            return await original_to_thread(func, *args, **kwargs)

        asyncio.to_thread = patched_to_thread

        try:
            articles = await retriever_with_threshold.retrieve_async("test query")

            assert len(articles) == 0
        finally:
            asyncio.to_thread = original_to_thread

    @pytest.mark.asyncio
    async def test_threshold_0_5_includes_edge_cases(self, retriever_with_threshold, tmp_path):
        """Test that articles with score exactly at threshold are included."""
        file1 = tmp_path / "article1.md"
        file1.write_text("Article 1")
        file2 = tmp_path / "article2.md"
        file2.write_text("Article 2")

        chunk1 = Mock()
        chunk1.metadata = {"kbId": "exact_threshold", "source_file": str(file1)}
        chunk1.page_content = "chunk1"

        chunk2 = Mock()
        chunk2.metadata = {"kbId": "above_threshold", "source_file": str(file2)}
        chunk2.page_content = "chunk2"

        retriever_with_threshold.store.similarity_search_async = AsyncMock(
            return_value=[chunk1, chunk2]
        )

        async def mock_rerank(*args, **kwargs):
            return [
                (chunk1, 0.5),
                (chunk2, 0.51),
            ]

        original_to_thread = asyncio.to_thread

        async def patched_to_thread(func, *args, **kwargs):
            if func == retriever_with_threshold.reranker.rerank:
                return await mock_rerank(*args, **kwargs)
            return await original_to_thread(func, *args, **kwargs)

        asyncio.to_thread = patched_to_thread

        try:
            articles = await retriever_with_threshold.retrieve_async("test query")

            assert len(articles) == 2
            kb_ids = {a.kb_id for a in articles}
            assert "exact_threshold" in kb_ids
            assert "above_threshold" in kb_ids
        finally:
            asyncio.to_thread = original_to_thread
