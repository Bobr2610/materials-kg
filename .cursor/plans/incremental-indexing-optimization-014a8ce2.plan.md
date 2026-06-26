<!-- 014a8ce2-81a7-4ff9-8cc6-784cc4c98470 85de00b6-8645-49b4-8548-b5da11a368d6 -->
# Incremental Indexing Optimization

## Goal

Modify `index_documents()` to process and write embeddings incrementally (per document or per batch) instead of collecting all chunks, embedding everything, then writing at once. This will:

- Reduce memory footprint
- Enable partial progress recovery if indexing is interrupted
- Provide real-time database updates
- Leverage ChromaDB's automatic deduplication (via stable IDs)

## Current Architecture

**File**: `rag_engine/retrieval/retriever.py:77-97`

Current flow:

1. Collect all chunks from all documents into lists (lines 83-94)
2. Embed all chunks at once via `embed_documents()` (line 96)
3. Write everything to ChromaDB at once (line 97)

**Issues:**

- Holds all chunks in memory during embedding phase
- No partial progress if process fails
- Database remains empty until all embeddings complete

## Implementation Strategy

### Option: Document-Level Incremental Processing

Process documents one at a time: chunk → embed → write immediately. This provides:

- Clear progress tracking per document
- Maximum memory efficiency
- Natural granularity for recovery
- Minimal code changes

### ChromaDB Deduplication

**No custom deduplication needed.** ChromaDB's `add()` method automatically handles duplicates via stable IDs:

- Same content → same ID (from `_stable_id()`) → ChromaDB updates/replaces
- Different content → different ID → ChromaDB inserts new entry
- Re-running indexing is safe (idempotent)

See `rag_engine/retrieval/retriever.py:20-22` for stable ID generation.

## Implementation Plan

### 1. Modify `index_documents()` Method

**File**: `rag_engine/retrieval/retriever.py`

**Changes**:

- Replace batch collection with per-document processing loop
- For each document:

  1. Generate chunks
  2. Enrich metadata
  3. Generate stable IDs
  4. Embed chunks (using existing `embed_documents()`)
  5. Write to ChromaDB immediately

- Add progress logging per document

**Location**: Lines 77-97

**New structure**:

```python
def index_documents(self, documents, chunk_size, chunk_overlap):
    total_docs = len(documents)
    for doc_idx, doc in enumerate(documents):
        # Process document chunks
        # Embed chunks
        # Write immediately
        logger.info(f"Indexed document {doc_idx+1}/{total_docs}")
```

### 2. Update Embedder Method (Optional Enhancement)

**File**: `rag_engine/retrieval/embedder.py`

**Current**: `embed_documents()` processes all texts at once with sentence_transformers batch processing

**Enhancement** (optional, can skip):

- Keep current method (works fine with smaller batches)
- OR add `embed_batch()` helper for explicit batch control

**Recommendation**: Keep `embed_documents()` as-is; it already handles batching internally via sentence_transformers.

### 3. Add Progress Logging

**File**: `rag_engine/retrieval/retriever.py`

**Add**:

- Log document progress (e.g., "Processing document 5/100")
- Log chunks per document
- Log total chunks indexed so far

**Use existing logger**: `logger = logging.getLogger(__name__)` (line 17)

### 4. Handle Edge Cases

- **Empty documents**: Skip documents with no content
- **Large documents**: Document-level processing already handles this
- **Interruptions**: Partial progress persists (ChromaDB writes immediately)

### 5. Maintain Test Compatibility

**File**: `rag_engine/tests/test_retriever.py:69-82`

**Ensure**:

- Method signature unchanged
- Behavior identical from external perspective
- Mocks continue to work (they intercept `embed_documents()` and `store.add()`)

**Note**: Tests use mocks, so internal processing changes won't affect them.

### 6. Update Documentation/Comments

**File**: `rag_engine/retrieval/retriever.py`

**Update**:

- Docstring to mention incremental processing
- Inline comments to reflect new flow

## Files to Modify

1. `rag_engine/retrieval/retriever.py` - Main implementation (lines 77-97)

   - Refactor `index_documents()` to process incrementally
   - Add progress logging

## Files to Verify (No Changes Expected)

1. `rag_engine/tests/test_retriever.py` - Ensure tests still pass
2. `rag_engine/scripts/build_index.py` - No changes needed (uses same interface)
3. `rag_engine/retrieval/embedder.py` - Keep as-is (batch processing already optimized)

## Benefits

1. **Memory Efficiency**: Process one document at a time instead of holding all chunks
2. **Fault Tolerance**: Partial progress saved if indexing fails
3. **Real-Time Updates**: Database populated as documents are processed
4. **Progress Visibility**: Can track progress per document
5. **No Breaking Changes**: Same method signature, tests unchanged

## Implementation Notes

- **Deduplication**: Automatic via ChromaDB stable IDs (no code changes needed)
- **Batch Processing**: sentence_transformers already handles batching internally
- **Backward Compatibility**: Same interface, internal optimization only

## Testing Strategy

1. **Unit Tests**: Existing tests should pass (mocks unchanged)
2. **Integration Test**: Run `build_index.py` with sample data to verify:

   - Documents indexed incrementally
   - Database populated progressively
   - Can resume after interruption (re-run indexes remaining documents)

_{

"id": "refactor-index-documents",

"content": "Refactor index_documents() in retriever.py to process documents incrementally (chunk → embed → write per document) instead of batch processing",

"dependencies": []

}

{

"id": "add-progress-logging",

"content": "Add progress logging to index_documents() to track document indexing progress",

"dependencies": ["refactor-index-documents"]

}

{

"id": "verify-tests-pass",

"content": "Run existing tests to ensure backward compatibility is maintained",

"dependencies": ["refactor-index-documents"]

}

_

### To-dos

- [ ] Refactor index_documents() in retriever.py to process documents incrementally (chunk → embed → write per document) instead of batch processing
- [ ] Add progress logging to index_documents() to track document indexing progress
- [ ] Run existing tests to ensure backward compatibility is maintained