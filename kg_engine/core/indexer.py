"""RAG indexer: chunk, embed, and write documents to vector store (async only)."""

from __future__ import annotations

import asyncio
import json
import logging
from hashlib import sha1
from typing import Any

from kg_engine.core.chunker import split_text
from kg_engine.core.metadata_enricher import enrich_metadata
from kg_engine.utils.git_utils import get_file_timestamp
from kg_engine.utils.metadata_utils import extract_numeric_kbid

logger = logging.getLogger(__name__)


def _stable_id(kb_id: str, chunk_index: int, content: str, source_file: str | None = None) -> str:
    """Generate a globally unique but stable ID for a chunk.

    Uses a document seed derived from source_file (preferred) or kb_id to
    disambiguate chunks from different documents that might otherwise share
    kbId and chunk content at the same index.
    """
    doc_seed = (source_file or kb_id).encode("utf-8")
    doc_hash = sha1(doc_seed).hexdigest()[:8]
    text_hash = sha1(content.encode("utf-8")).hexdigest()[:10]
    return f"{doc_hash}:{chunk_index}:{text_hash}"


class RAGIndexer:
    """Indexes documents into vector store with incremental processing and timestamp-based deduplication."""

    def __init__(self, embedder, vector_store):
        """Initialize RAG indexer.

        Args:
            embedder: Embedder instance for generating embeddings
            vector_store: Vector store instance (e.g., ChromaStore) for storing chunks
        """
        self.embedder = embedder
        self.store = vector_store
        logger.info("RAGIndexer initialized")

    @staticmethod
    def _assert_embedding_batch_sizes(
        texts: list[str],
        embeddings: list[list[float]],
        kb_id: str,
        doc_stable_id: str,
        *,
        async_mode: bool,
    ) -> None:
        """Ensure 1:1 mapping between input texts and embedding vectors."""
        if len(embeddings) != len(texts):
            mode = "async" if async_mode else "sync"
            raise ValueError(
                "Embedding provider returned mismatched batch sizes "
                f"({mode} mode): embeddings={len(embeddings)} vs texts={len(texts)} "
                f"(kbId={kb_id}, doc_stable_id={doc_stable_id})"
            )

    def index_documents(
        self,
        documents: list[Any],
        chunk_size: int,
        chunk_overlap: int,
        max_files: int | None = None,
        force_reindex: bool = False,
        start_index: int | None = None,
    ) -> dict[str, int]:
        """Index documents incrementally with immediate database writes.

        Processes documents one at a time: chunk → embed → write to vector store.
        This enables partial progress recovery and reduces memory usage.
        Uses timestamp-based incremental reindexing to skip unchanged documents.

        Features:
        - Three-tier timestamp detection: frontmatter → Git → file modification date
        - Incremental reindexing: skips unchanged docs, replaces outdated ones
        - Numeric kbId normalization for consistent document identification
        - Automatic deduplication via stable IDs

        Args:
            documents: List of document objects with content and metadata
            chunk_size: Size of text chunks in tokens
            chunk_overlap: Overlap between chunks in tokens
            max_files: Maximum number of documents to index (None = no limit)
        """
        total_docs = len(documents)
        processed_docs = 0
        total_chunks_indexed = 0
        skipped_docs = 0
        empty_docs = 0
        no_chunk_docs = 0
        reindexed_docs = 0
        new_docs = 0

        for doc_idx, doc in enumerate(documents, start=1):
            if start_index is not None and doc_idx < start_index:
                logger.info(
                    "Skipping document %d/%d due to start_index=%d",
                    doc_idx,
                    total_docs,
                    start_index,
                )
                continue
            base_meta = dict(getattr(doc, "metadata", {}))
            kb_id = base_meta.get("kbId")
            if not kb_id:
                logger.error(
                    "Missing kbId in metadata for document %d/%d (source: %s)",
                    doc_idx,
                    total_docs,
                    base_meta.get("source_file", "unknown"),
                )
                continue
            content = getattr(doc, "content", "")

            # Skip empty documents
            if not content or not content.strip():
                logger.warning(
                    "Skipping empty document %d/%d (kbId: %s)", doc_idx, total_docs, kb_id
                )
                empty_docs += 1
                continue

            # Respect max_files limit as a safety check
            # Note: max_files is primarily applied at DocumentProcessor level,
            # but this serves as a secondary check for documents actually indexed
            if max_files is not None and processed_docs >= max_files:
                logger.info("Max files limit reached: %d", max_files)
                break

            # Generate chunks for this document
            chunks = list(split_text(content, chunk_size, chunk_overlap))
            if not chunks:
                logger.warning(
                    "No chunks generated for document %d/%d (kbId: %s)", doc_idx, total_docs, kb_id
                )
                no_chunk_docs += 1
                continue

            # Prepare chunk data
            texts: list[str] = []
            metadatas: list[dict[str, Any]] = []
            ids: list[str] = []

            # Compute per-document invariants
            # Normalize kbId to numeric for consistent doc_stable_id and storage
            numeric_kb_id = extract_numeric_kbid(kb_id) or str(kb_id)
            doc_stable_id = sha1(numeric_kb_id.encode("utf-8")).hexdigest()[:12]
            source_file = base_meta.get("source_file")
            # Three-tier fallback: frontmatter → Git → file stat
            file_mtime_epoch, file_modified_at_iso, _timestamp_source = get_file_timestamp(
                source_file, base_meta
            )

            # Incremental reindexing: skip unchanged docs, replace outdated (or force reindex)
            _was_reindex = False
            _had_existing = False
            if force_reindex or file_mtime_epoch is not None:
                existing = self.store.get_any_doc_meta({"doc_stable_id": doc_stable_id})

                # Only skip if we found an exact match (same doc_stable_id) and it's up to date
                if existing is not None:
                    _had_existing = True
                    if force_reindex:
                        try:
                            self.store.delete_where({"doc_stable_id": doc_stable_id})
                            logger.info(
                                "Force reindex: deleted existing chunks for kbId=%s (doc_stable_id=%s)",
                                kb_id,
                                doc_stable_id,
                            )
                            _was_reindex = True
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "Force reindex: failed to delete for kbId=%s: %s", kb_id, exc
                            )
                    else:
                        existing_epoch = existing.get("file_mtime_epoch")
                        if (
                            isinstance(existing_epoch, int)
                            and file_mtime_epoch is not None
                            and existing_epoch >= file_mtime_epoch
                        ):
                            logger.info(
                                "Skipping unchanged document %d/%d (kbId: %s)",
                                doc_idx,
                                total_docs,
                                kb_id,
                            )
                            skipped_docs += 1
                            continue
                        # Delete outdated chunks for this document before re-adding
                        try:
                            self.store.delete_where({"doc_stable_id": doc_stable_id})
                            logger.info(
                                "Deleted outdated chunks for kbId=%s (doc_stable_id=%s)",
                                kb_id,
                                doc_stable_id,
                            )
                            _was_reindex = True
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "Failed to delete outdated chunks for kbId=%s: %s", kb_id, exc
                            )

            for idx, chunk in enumerate(chunks):
                # Generate stable ID using normalized kbId
                stable_id = _stable_id(numeric_kb_id, idx, chunk, base_meta.get("source_file"))

                meta = enrich_metadata(base_meta, chunk, idx)
                # Store normalized kbId in vector store
                meta["kbId"] = numeric_kb_id
                meta["stable_id"] = stable_id
                meta["doc_stable_id"] = doc_stable_id
                if file_modified_at_iso is not None:
                    meta["file_modified_at"] = file_modified_at_iso
                if file_mtime_epoch is not None:
                    meta["file_mtime_epoch"] = file_mtime_epoch

                texts.append(chunk)
                metadatas.append(meta)
                ids.append(stable_id)

            # Sanitize metadata values for vector store (drop None, stringify lists/dicts)
            def _sanitize_metadata(m: dict[str, Any]) -> dict[str, Any]:
                out: dict[str, Any] = {}
                for k, v in (m or {}).items():
                    if v is None:
                        continue
                    if isinstance(v, (str, int, float, bool)):
                        out[k] = v
                    elif isinstance(v, list):
                        if not v:
                            continue
                        out[k] = ", ".join(str(x) for x in v)
                    else:
                        try:
                            out[k] = json.dumps(v, ensure_ascii=False)
                        except Exception:  # noqa: BLE001
                            out[k] = str(v)
                return out

            # Deduplicate by ID within this document batch before embedding
            seen_ids: set[str] = set()
            dedup_texts: list[str] = []
            dedup_metadatas: list[dict[str, Any]] = []
            dedup_ids: list[str] = []
            for t, m, i in zip(texts, metadatas, ids):
                if i in seen_ids:
                    continue
                seen_ids.add(i)
                dedup_texts.append(t)
                dedup_metadatas.append(_sanitize_metadata(m))
                dedup_ids.append(i)

            # Embed chunks for this (deduplicated) document
            embeddings = self.embedder.embed_documents(dedup_texts, show_progress=False)
            self._assert_embedding_batch_sizes(
                dedup_texts,
                embeddings,
                kb_id=str(kb_id),
                doc_stable_id=doc_stable_id,
                async_mode=False,
            )

            # Write immediately to vector store
            self.store.add(
                texts=dedup_texts, metadatas=dedup_metadatas, ids=dedup_ids, embeddings=embeddings
            )

            total_chunks_indexed += len(chunks)
            processed_docs += 1
            if _was_reindex:
                reindexed_docs += 1
            elif not _had_existing:
                new_docs += 1
            logger.info(
                "Indexed document %d/%d: %d chunks (kbId: %s, total chunks: %d)",
                doc_idx,
                total_docs,
                len(chunks),
                kb_id,
                total_chunks_indexed,
            )

        return {
            "total_docs": total_docs,
            "processed_docs": processed_docs,
            "new_docs": new_docs,
            "reindexed_docs": reindexed_docs,
            "skipped_docs": skipped_docs,
            "empty_docs": empty_docs,
            "no_chunk_docs": no_chunk_docs,
            "total_chunks_indexed": total_chunks_indexed,
        }

    async def index_documents_async(
        self,
        documents: list[Any],
        chunk_size: int,
        chunk_overlap: int,
        max_files: int | None = None,
        force_reindex: bool = False,
        start_index: int | None = None,
    ) -> dict[str, int]:
        """Async: index documents incrementally with immediate database writes.

        Same logic as sync index_documents(), but uses async store methods:
        - await self.store.get_any_doc_meta_async()
        - await self.store.delete_where_async()
        - await self.store.add_async()

        Args:
            documents: List of document objects with content and metadata
            chunk_size: Size of text chunks in tokens
            chunk_overlap: Overlap between chunks in tokens
            max_files: Maximum number of documents to index (None = no limit)
            force_reindex: Force reindex all documents

        Returns:
            Dict with indexing statistics (same format as sync version)
        """
        total_docs = len(documents)
        processed_docs = 0
        total_chunks_indexed = 0
        skipped_docs = 0
        empty_docs = 0
        no_chunk_docs = 0
        reindexed_docs = 0
        new_docs = 0

        for doc_idx, doc in enumerate(documents, start=1):
            if start_index is not None and doc_idx < start_index:
                logger.info(
                    "Skipping document %d/%d due to start_index=%d",
                    doc_idx,
                    total_docs,
                    start_index,
                )
                continue
            base_meta = dict(getattr(doc, "metadata", {}))
            kb_id = base_meta.get("kbId")
            if not kb_id:
                logger.error(
                    "Missing kbId in metadata for document %d/%d (source: %s)",
                    doc_idx,
                    total_docs,
                    base_meta.get("source_file", "unknown"),
                )
                continue
            content = getattr(doc, "content", "")

            # Skip empty documents
            if not content or not content.strip():
                logger.warning(
                    "Skipping empty document %d/%d (kbId: %s)", doc_idx, total_docs, kb_id
                )
                empty_docs += 1
                continue

            # Respect max_files limit as a safety check
            if max_files is not None and processed_docs >= max_files:
                logger.info("Max files limit reached: %d", max_files)
                break

            # Generate chunks for this document
            chunks = list(split_text(content, chunk_size, chunk_overlap))
            if not chunks:
                logger.warning(
                    "No chunks generated for document %d/%d (kbId: %s)", doc_idx, total_docs, kb_id
                )
                no_chunk_docs += 1
                continue

            # Prepare chunk data
            texts: list[str] = []
            metadatas: list[dict[str, Any]] = []
            ids: list[str] = []

            # Compute per-document invariants
            numeric_kb_id = extract_numeric_kbid(kb_id) or str(kb_id)
            doc_stable_id = sha1(numeric_kb_id.encode("utf-8")).hexdigest()[:12]
            source_file = base_meta.get("source_file")
            file_mtime_epoch, file_modified_at_iso, _timestamp_source = get_file_timestamp(
                source_file, base_meta
            )

            # Incremental reindexing: skip unchanged docs, replace outdated (or force reindex)
            _was_reindex = False
            _had_existing = False
            if force_reindex or file_mtime_epoch is not None:
                existing = await self.store.get_any_doc_meta_async({"doc_stable_id": doc_stable_id})

                # Only skip if we found an exact match (same doc_stable_id) and it's up to date
                if existing is not None:
                    _had_existing = True
                    if force_reindex:
                        try:
                            await self.store.delete_where_async({"doc_stable_id": doc_stable_id})
                            logger.info(
                                "Force reindex: deleted existing chunks for kbId=%s (doc_stable_id=%s)",
                                kb_id,
                                doc_stable_id,
                            )
                            _was_reindex = True
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "Force reindex: failed to delete for kbId=%s: %s", kb_id, exc
                            )
                    else:
                        existing_epoch = existing.get("file_mtime_epoch")
                        if (
                            isinstance(existing_epoch, int)
                            and file_mtime_epoch is not None
                            and existing_epoch >= file_mtime_epoch
                        ):
                            logger.info(
                                "Skipping unchanged document %d/%d (kbId: %s)",
                                doc_idx,
                                total_docs,
                                kb_id,
                            )
                            skipped_docs += 1
                            continue
                        # Delete outdated chunks for this document before re-adding
                        try:
                            await self.store.delete_where_async({"doc_stable_id": doc_stable_id})
                            logger.info(
                                "Deleted outdated chunks for kbId=%s (doc_stable_id=%s)",
                                kb_id,
                                doc_stable_id,
                            )
                            _was_reindex = True
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "Failed to delete outdated chunks for kbId=%s: %s", kb_id, exc
                            )

            for idx, chunk in enumerate(chunks):
                # Generate stable ID using normalized kbId
                stable_id = _stable_id(numeric_kb_id, idx, chunk, base_meta.get("source_file"))

                meta = enrich_metadata(base_meta, chunk, idx)
                # Store normalized kbId in vector store
                meta["kbId"] = numeric_kb_id
                meta["stable_id"] = stable_id
                meta["doc_stable_id"] = doc_stable_id
                if file_modified_at_iso is not None:
                    meta["file_modified_at"] = file_modified_at_iso
                if file_mtime_epoch is not None:
                    meta["file_mtime_epoch"] = file_mtime_epoch

                texts.append(chunk)
                metadatas.append(meta)
                ids.append(stable_id)

            # Sanitize metadata values for vector store (drop None, stringify lists/dicts)
            def _sanitize_metadata(m: dict[str, Any]) -> dict[str, Any]:
                out: dict[str, Any] = {}
                for k, v in (m or {}).items():
                    if v is None:
                        continue
                    if isinstance(v, (str, int, float, bool)):
                        out[k] = v
                    elif isinstance(v, list):
                        if not v:
                            continue
                        out[k] = ", ".join(str(x) for x in v)
                    else:
                        try:
                            out[k] = json.dumps(v, ensure_ascii=False)
                        except Exception:  # noqa: BLE001
                            out[k] = str(v)
                return out

            # Deduplicate by ID within this document batch before embedding
            seen_ids: set[str] = set()
            dedup_texts: list[str] = []
            dedup_metadatas: list[dict[str, Any]] = []
            dedup_ids: list[str] = []
            for t, m, i in zip(texts, metadatas, ids):
                if i in seen_ids:
                    continue
                seen_ids.add(i)
                dedup_texts.append(t)
                dedup_metadatas.append(_sanitize_metadata(m))
                dedup_ids.append(i)

            # Embed chunks for this (deduplicated) document (keep sync - CPU-bound)
            embeddings = self.embedder.embed_documents(dedup_texts, show_progress=False)
            self._assert_embedding_batch_sizes(
                dedup_texts,
                embeddings,
                kb_id=str(kb_id),
                doc_stable_id=doc_stable_id,
                async_mode=True,
            )

            # Write immediately to vector store (async)
            await self.store.add_async(
                texts=dedup_texts, metadatas=dedup_metadatas, ids=dedup_ids, embeddings=embeddings
            )

            total_chunks_indexed += len(chunks)
            processed_docs += 1
            if _was_reindex:
                reindexed_docs += 1
            elif not _had_existing:
                new_docs += 1
            logger.info(
                "Indexed document %d/%d: %d chunks (kbId: %s, total chunks: %d)",
                doc_idx,
                total_docs,
                len(chunks),
                kb_id,
                total_chunks_indexed,
            )

        return {
            "total_docs": total_docs,
            "processed_docs": processed_docs,
            "new_docs": new_docs,
            "reindexed_docs": reindexed_docs,
            "skipped_docs": skipped_docs,
            "empty_docs": empty_docs,
            "no_chunk_docs": no_chunk_docs,
            "total_chunks_indexed": total_chunks_indexed,
        }
