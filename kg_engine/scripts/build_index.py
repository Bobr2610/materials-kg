from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
import logging

# Add project root to path if not already installed
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from kg_engine.config.settings import settings
from kg_engine.core.document_processor import DocumentProcessor
from kg_engine.core.indexer import RAGIndexer
from kg_engine.retrieval.embedder import create_embedder
from hashlib import sha1

from kg_engine.storage.vector_store import ChromaStore
from kg_engine.utils.git_utils import get_file_timestamp
from kg_engine.utils.metadata_utils import extract_numeric_kbid
from kg_engine.utils.logging_manager import setup_logging

logger = logging.getLogger(__name__)


async def run_async() -> None:
    parser = argparse.ArgumentParser(description="Build RAG index from markdown sources")
    parser.add_argument("--source", required=True, help="Path to folder or file")
    parser.add_argument("--mode", choices=["folder", "file", "mkdocs"], default="folder")
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Force reindex: delete existing chunks per doc and re-embed",
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=None,
        help="1-based document index to start (skip earlier docs in this run)",
    )
    parser.add_argument(
        "--prune-missing",
        action="store_true",
        help="Delete records from vector store whose kbId is not present in the source set",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Limit the number of source files to scan/process (for quick runs)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze timestamps without indexing (shows which source is used for each file)",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="ChromaDB collection name (overrides CHROMADB_COLLECTION env var)",
    )
    args = parser.parse_args()

    setup_logging()

    dp = DocumentProcessor(mode=args.mode)
    # Pass max_files to limit files processed (before indexing)
    docs = dp.process(args.source, max_files=args.max_files)

    # Dry-run mode: analyze timestamps without indexing
    if args.dry_run:
        print("=" * 80)
        print("DRY-RUN MODE: Timestamp Analysis")
        print("=" * 80)
        print(f"{'File':<60} {'Source':<12} {'Epoch':<12} {'ISO String':<25}")
        print("-" * 80)

        store = ChromaStore(
            collection_name=args.collection or settings.chromadb_collection,
        )

        for doc in docs:
            base_meta = getattr(doc, "metadata", {})
            kb_id = base_meta.get("kbId", "unknown")
            source_file = base_meta.get("source_file", "")

            # Get timestamp using three-tier fallback
            epoch, iso_string, source = get_file_timestamp(source_file, base_meta)

            # Check if would be skipped (compare with existing)
            # Normalize kbId to numeric for consistent lookup
            numeric_kb_id = extract_numeric_kbid(kb_id) or str(kb_id)
            doc_stable_id = sha1(numeric_kb_id.encode("utf-8")).hexdigest()[:12]
            existing = (
                await store.get_any_doc_meta_async({"doc_stable_id": doc_stable_id})
                if store
                else None
            )
            existing_epoch = existing.get("file_mtime_epoch") if existing else None

            status = ""
            if existing_epoch is not None:
                if (
                    isinstance(existing_epoch, int)
                    and epoch is not None
                    and existing_epoch >= epoch
                ):
                    status = " [SKIP]"
                elif epoch is not None:
                    status = " [REINDEX]"
                else:
                    status = " [NO_TS]"
            else:
                status = " [NEW]"

            file_display = str(source_file)[-60:] if source_file else "N/A"
            epoch_str = str(epoch) if epoch else "None"
            iso_str = iso_string if iso_string else "None"

            print(f"{file_display:<60} {source:<12} {epoch_str:<12} {iso_str:<25}{status}")

        print("=" * 80)
        print("Dry-run complete. No files were indexed.")
        return

    embedder = create_embedder(settings)
    collection = args.collection or settings.chromadb_collection
    store = ChromaStore(collection_name=collection)

    indexer = RAGIndexer(embedder=embedder, vector_store=store)
    summary = await indexer.index_documents_async(
        docs,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        max_files=args.max_files,
        force_reindex=args.reindex,
        start_index=args.start_index,
    )
    deleted_docs = 0

    # Optional pruning step: remove entries whose kbId is not in current source set
    if args.prune_missing:
        # Build set of normalized kbIds present in source docs
        present_kbids = set()
        for doc in docs:
            base_meta = getattr(doc, "metadata", {}) or {}
            kb = base_meta.get("kbId")
            if kb is None:
                continue
            normalized = extract_numeric_kbid(kb) or str(kb)
            present_kbids.add(normalized)

        # Paginate through all stored metadata and collect delete candidates
        checked_docs = 0
        delete_candidates: list[tuple[str, str]] = []  # (kbId, doc_stable_id)
        offset = 0
        page_size = 1000

        collection = await store.get_collection()
        while True:
            res = await collection.get(limit=page_size, offset=offset, include=["metadatas"])
            metas_batch = res.get("metadatas", [])
            if not metas_batch:
                break
            for meta in metas_batch:
                checked_docs += 1
                meta_kb = (meta or {}).get("kbId")
                meta_doc_id = (meta or {}).get("doc_stable_id")
                if not meta_kb or not meta_doc_id:
                    continue
                if meta_kb not in present_kbids:
                    delete_candidates.append((str(meta_kb), str(meta_doc_id)))
            if len(metas_batch) < page_size:
                break
            offset += page_size

        # Delete with progress logging similar to indexing
        total_to_delete = len(delete_candidates)
        for idx, (kb, doc_id) in enumerate(delete_candidates, start=1):
            await store.delete_where_async({"doc_stable_id": doc_id})
            deleted_docs += 1
            logger.info(
                "Deleted document %d/%d (kbId: %s, doc_stable_id: %s)",
                idx,
                total_to_delete,
                kb,
                doc_id,
            )

        # Prune details are included in the final summary below

    # Single enriched final summary
    if isinstance(summary, dict):
        logger.info(
            "Summary:\nTotal=%d\nProcessed=%d\nNew=%d\nReindexed=%d\nSkipped=%d\nEmpty=%d\nNo_chunks=%d\nChunks=%d\nDeleted=%d",
            summary.get("total_docs", 0),
            summary.get("processed_docs", 0),
            summary.get("new_docs", 0),
            summary.get("reindexed_docs", 0),
            summary.get("skipped_docs", 0),
            summary.get("empty_docs", 0),
            summary.get("no_chunk_docs", 0),
            summary.get("total_chunks_indexed", 0),
            deleted_docs,
        )


if __name__ == "__main__":
    asyncio.run(run_async())
