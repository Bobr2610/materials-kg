"""Tests for RAG indexer."""
from __future__ import annotations

import os
from hashlib import sha1
from unittest.mock import MagicMock

import pytest

from kg_engine.core.indexer import RAGIndexer
from kg_engine.utils.metadata_utils import extract_numeric_kbid


@pytest.fixture
def mock_embedder():
    """Mock embedder for tests."""
    embedder = MagicMock()
    return embedder


@pytest.fixture
def mock_vector_store():
    """Mock vector store for tests."""
    store = MagicMock()
    store.collection = MagicMock()
    return store


class TestRAGIndexer:
    """Tests for RAGIndexer class."""

    def test_index_documents_enriches_metadata(self, mock_embedder, mock_vector_store):
        """Test that metadata is properly enriched during indexing."""
        doc = MagicMock()
        doc.content = "# Title\n\n```python\nprint('hi')\n```"
        doc.metadata = {"kbId": "doc1", "title": "Doc"}
        doc.metadata["source_file"] = "/tmp/test.md"

        mock_embedder.embed_documents.return_value = [[0.1] * 3]
        mock_vector_store.get_any_doc_meta.return_value = None

        indexer = RAGIndexer(embedder=mock_embedder, vector_store=mock_vector_store)
        indexer.index_documents([doc], chunk_size=500, chunk_overlap=150)

        assert mock_vector_store.add.called
        call_kwargs = mock_vector_store.add.call_args.kwargs
        assert call_kwargs["metadatas"][0]["has_code"] is True
        assert call_kwargs["metadatas"][0]["chunk_index"] == 0
        # New metadata fields
        assert "stable_id" in call_kwargs["metadatas"][0]
        # Verify normalized kbId is stored
        numeric_kb_id = extract_numeric_kbid("doc1") or "doc1"
        assert call_kwargs["metadatas"][0]["kbId"] == numeric_kb_id
        assert "doc_stable_id" in call_kwargs["metadatas"][0]

    def test_index_documents_skips_unchanged(self, mock_embedder, mock_vector_store, tmp_path):
        """If stored mtime >= current mtime, document is skipped and not added."""
        file_path = tmp_path / "doc.md"
        file_path.write_text("Content")
        # Set file mtime to 200
        os.utime(file_path, (200, 200))

        # Use normalized kbId for doc_stable_id (new behavior)
        numeric_kb_id = extract_numeric_kbid("k1") or "k1"
        doc_stable_id = sha1(numeric_kb_id.encode("utf-8")).hexdigest()[:12]
        mock_vector_store.get_any_doc_meta.return_value = {"file_mtime_epoch": 200, "doc_stable_id": doc_stable_id}

        indexer = RAGIndexer(embedder=mock_embedder, vector_store=mock_vector_store)

        doc = MagicMock()
        doc.content = "# T\nBody"
        doc.metadata = {"kbId": "k1", "source_file": str(file_path)}

        indexer.index_documents([doc], chunk_size=50, chunk_overlap=10, max_files=10)

        mock_vector_store.add.assert_not_called()
        mock_vector_store.delete_where.assert_not_called()

    def test_index_documents_replaces_updated(self, mock_embedder, mock_vector_store, tmp_path):
        """If stored mtime < current mtime, delete_where then add is called."""
        file_path = tmp_path / "doc.md"
        file_path.write_text("Content")
        # Current file mtime 300
        os.utime(file_path, (300, 300))

        # Use normalized kbId for doc_stable_id (new behavior)
        numeric_kb_id = extract_numeric_kbid("k2") or "k2"
        doc_stable_id = sha1(numeric_kb_id.encode("utf-8")).hexdigest()[:12]
        # Existing older epoch 200 triggers reindex
        mock_vector_store.get_any_doc_meta.return_value = {"file_mtime_epoch": 200, "doc_stable_id": doc_stable_id}

        indexer = RAGIndexer(embedder=mock_embedder, vector_store=mock_vector_store)

        doc = MagicMock()
        doc.content = "# T\nBody"
        doc.metadata = {"kbId": "k2", "source_file": str(file_path)}

        indexer.index_documents([doc], chunk_size=50, chunk_overlap=10, max_files=None)

        # delete_where called with normalized doc_stable_id
        mock_vector_store.delete_where.assert_called_once_with({"doc_stable_id": doc_stable_id})
        mock_vector_store.add.assert_called_once()
        # Verify normalized kbId is stored
        call_kwargs = mock_vector_store.add.call_args.kwargs
        assert call_kwargs["metadatas"][0]["kbId"] == numeric_kb_id

    def test_max_files_counts_only_indexed(self, mock_embedder, mock_vector_store, tmp_path):
        """max_files should limit actual indexed docs, not scanned docs."""
        # Prepare three files: two unchanged (skip), one updated (index)
        f1 = tmp_path / "a.md"; f1.write_text("A"); os.utime(f1, (200, 200))
        f2 = tmp_path / "b.md"; f2.write_text("B"); os.utime(f2, (200, 200))
        f3 = tmp_path / "c.md"; f3.write_text("C"); os.utime(f3, (300, 300))

        # For first two docs, existing epoch equals current → skip
        # Use normalized kbId for doc_stable_id calculations
        numeric_kb_a = extract_numeric_kbid("kb_a") or "kb_a"
        numeric_kb_b = extract_numeric_kbid("kb_b") or "kb_b"
        numeric_kb_c = extract_numeric_kbid("kb_c") or "kb_c"
        doc_stable_id_a = sha1(numeric_kb_a.encode("utf-8")).hexdigest()[:12]
        doc_stable_id_b = sha1(numeric_kb_b.encode("utf-8")).hexdigest()[:12]
        doc_stable_id_c = sha1(numeric_kb_c.encode("utf-8")).hexdigest()[:12]

        def get_meta(where):
            if where.get("doc_stable_id") in {doc_stable_id_a, doc_stable_id_b}:
                return {"file_mtime_epoch": 200}
            if where.get("doc_stable_id") == doc_stable_id_c:
                return {"file_mtime_epoch": 200}  # older than current 300 → reindex
            return None

        mock_vector_store.get_any_doc_meta.side_effect = get_meta

        indexer = RAGIndexer(embedder=mock_embedder, vector_store=mock_vector_store)

        docs = []
        for kb, fp in [("kb_a", f1), ("kb_b", f2), ("kb_c", f3)]:
            d = MagicMock()
            d.content = "# H\nX"
            d.metadata = {"kbId": kb, "source_file": str(fp)}
            docs.append(d)

        # Request max_files=1; should skip a and b, index only c and stop
        indexer.index_documents(docs, chunk_size=50, chunk_overlap=10, max_files=1)

        mock_vector_store.add.assert_called_once()
        # Ensure we deleted outdated for c only (using normalized kbId)
        mock_vector_store.delete_where.assert_called_once_with({"doc_stable_id": doc_stable_id_c})

    def test_stable_id_disambiguates_by_source_file(self, mock_embedder, mock_vector_store, tmp_path):
        """Chunks from different files with same kbId/content get different IDs."""
        # Two files with identical content and same kbId
        f1 = tmp_path / "same.md"; f1.write_text("# H\nSame body"); os.utime(f1, (100, 100))
        f2 = tmp_path / "same_copy.md"; f2.write_text("# H\nSame body"); os.utime(f2, (100, 100))

        # Force embedder to return deterministic embeddings
        mock_embedder.embed_documents.return_value = [[0.1, 0.2, 0.3]]

        indexer = RAGIndexer(embedder=mock_embedder, vector_store=mock_vector_store)

        d1 = MagicMock(); d1.content = "# H\nSame body"; d1.metadata = {"kbId": "kb_same", "source_file": str(f1)}
        d2 = MagicMock(); d2.content = "# H\nSame body"; d2.metadata = {"kbId": "kb_same", "source_file": str(f2)}

        # Capture IDs from consecutive add() calls
        captured_ids = []
        def capture_add(texts=None, metadatas=None, ids=None, embeddings=None):  # noqa: ANN001
            captured_ids.append(tuple(ids))
        mock_vector_store.add.side_effect = capture_add
        mock_vector_store.get_any_doc_meta.return_value = None

        indexer.index_documents([d1, d2], chunk_size=50, chunk_overlap=10, max_files=None)

        assert len(captured_ids) == 2
        # Each call has 1 chunk id; they should differ
        assert captured_ids[0][0] != captured_ids[1][0]

    def test_index_documents_normalizes_kbid(self, mock_embedder, mock_vector_store, tmp_path):
        """Test that numeric kbId is extracted and used for doc_stable_id."""
        file_path = tmp_path / "doc.md"
        file_path.write_text("Content")
        os.utime(file_path, (200, 200))

        # Document with kbId that has suffix
        doc = MagicMock()
        doc.content = "# Title\nBody"
        doc.metadata = {"kbId": "4578-toc", "source_file": str(file_path)}

        numeric_kb_id = extract_numeric_kbid("4578-toc") or "4578-toc"
        doc_stable_id = sha1(numeric_kb_id.encode("utf-8")).hexdigest()[:12]
        mock_vector_store.get_any_doc_meta.return_value = None
        mock_embedder.embed_documents.return_value = [[0.1] * 3]

        indexer = RAGIndexer(embedder=mock_embedder, vector_store=mock_vector_store)

        indexer.index_documents([doc], chunk_size=50, chunk_overlap=10, max_files=None)

        # Verify normalized kbId is stored (numeric part only)
        call_kwargs = mock_vector_store.add.call_args.kwargs
        assert call_kwargs["metadatas"][0]["kbId"] == "4578"
        assert call_kwargs["metadatas"][0]["doc_stable_id"] == doc_stable_id

    def test_index_documents_requires_kbid(self, mock_embedder, mock_vector_store):
        """Test that indexer skips documents without kbId (no fallback to source_file)."""
        doc = MagicMock()
        doc.content = "# Title\nBody"
        doc.metadata = {"title": "Test", "source_file": "/path/to/file.md"}  # Missing kbId

        mock_vector_store.get_any_doc_meta.return_value = None

        indexer = RAGIndexer(embedder=mock_embedder, vector_store=mock_vector_store)

        indexer.index_documents([doc], chunk_size=50, chunk_overlap=10, max_files=None)

        # Should not index documents without kbId
        mock_vector_store.add.assert_not_called()

