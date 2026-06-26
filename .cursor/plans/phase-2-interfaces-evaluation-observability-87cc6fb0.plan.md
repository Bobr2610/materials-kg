<!-- 87cc6fb0-b881-4f6e-bef9-15664783d54d 3d9ddc7c-5b54-4c0e-9e64-cb6ccb2d4574 -->
# Phase 2: Abstract Interfaces, Evaluation, and Observability

## Overview

Extend the RAG engine with:

1. **Protocol-based interfaces** for pluggable backends (VectorStore, Embedder, Chunker, MetadataEnricher)
2. **Evaluation framework** with test query dataset and metrics
3. **Observability infrastructure** (LangSmith/Langfuse) for production monitoring
4. **Code organization** (input_modes config, provider adapters)

All changes maintain backward compatibility with Phase 1 implementations.

## Phase 2.1: Abstract Interfaces

### Goal

Define Protocol-based interfaces enabling backend swapping without breaking existing code.

### Implementation

#### 1. Create Core Interfaces (`rag_engine/core/interfaces.py` - NEW)

```python
"""Protocol-based interfaces for pluggable RAG components."""
from __future__ import annotations
from typing import Any, Dict, Iterable, Protocol

class Chunker(Protocol):
    def split_text(self, text: str, chunk_size: int, chunk_overlap: int) -> Iterable[str]: ...
    
class MetadataEnricher(Protocol):
    def enrich_metadata(self, base_meta: Dict[str, Any], content: str, chunk_index: int) -> Dict[str, Any]: ...
```

#### 2. Create Retrieval Interfaces (`rag_engine/retrieval/interfaces.py` - NEW)

```python
"""Protocol-based interfaces for retrieval components."""
from typing import Any, Dict, List, Protocol

class Embedder(Protocol):
    def embed_query(self, query: str) -> List[float]: ...
    def embed_documents(self, texts: List[str], batch_size: int = 8, show_progress: bool = True) -> List[List[float]]: ...
    def get_embedding_dim(self) -> int: ...

class Reranker(Protocol):
    def rerank(self, query: str, candidates: List[tuple[Any, float]], top_k: int, metadata_boost_weights: Dict[str, float] | None = None) -> List[tuple[Any, float]]: ...
```

#### 3. Create Storage Interfaces (`rag_engine/storage/interfaces.py` - NEW)

```python
"""Protocol-based interfaces for vector storage backends."""
from typing import Any, Dict, List, Optional, Protocol

class VectorStore(Protocol):
    def add(self, texts: List[str], metadatas: List[Dict[str, Any]], ids: Optional[List[str]] = None, embeddings: Optional[List[List[float]]] = None) -> None: ...
    def similarity_search(self, query_embedding: List[float], k: int = 5) -> List[Any]: ...
    def get_any_doc_meta(self, where: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...
    def delete_where(self, where: Dict[str, Any]) -> None: ...
```

#### 4. Wrap Existing Implementations (Backward Compatible)

**Modify `rag_engine/core/chunker.py`**:

- Add `CodeSafeChunker` class wrapping `split_text()` function
- Export `default_chunker = CodeSafeChunker()` instance
- Keep existing `split_text()` function for backward compatibility

**Modify `rag_engine/core/metadata_enricher.py`**:

- Add `DefaultMetadataEnricher` class wrapping `enrich_metadata()` function
- Export `default_enricher = DefaultMetadataEnricher()` instance
- Keep existing `enrich_metadata()` function for backward compatibility

**Modify `rag_engine/core/indexer.py`**:

- Update `__init__()` to accept optional `chunker` and `metadata_enricher` parameters
- Default to existing implementations: `chunker or default_chunker`, `enricher or default_enricher`
- Use `self.chunker.split_text()` and `self.enricher.enrich_metadata()` instead of direct function calls
- Add Protocol import comments

**Add Protocol compliance comments** to:

- `rag_engine/storage/vector_store.py` (ChromaStore implements VectorStore)
- `rag_engine/retrieval/embedder.py` (FRIDAEmbedder implements Embedder)
- `rag_engine/retrieval/reranker.py` (CrossEncoderReranker/IdentityReranker implement Reranker)

### Tests

- Add `test_core_interfaces.py` to verify Protocol compliance via type checking
- Update `test_core_indexer.py` to test with swapped chunker/enricher
- Ensure all existing tests pass unchanged

## Phase 2.2: Evaluation Framework

### Goal

Systematic RAG quality assessment with bilingual test queries and metrics.

### Implementation

#### 1. Create Test Dataset (`rag_engine/tests/test_queries.json` - NEW)

JSON structure:

```json
{
  "version": "1.0",
  "test_sets": [
    {
      "name": "basic_retrieval",
      "queries": [
        {
          "id": "basic_001",
          "question": "Как использовать N3?",
          "language": "ru",
          "expected_kbids": ["4578"],
          "expected_anchors": ["#n3"],
          "expected_answer_contains": ["N3", "тройки", "RDF"]
        }
      ]
    }
  ]
}
```

#### 2. Create Evaluation Script (`rag_engine/scripts/test_queries.py` - NEW)

Features:

- Load test dataset from JSON
- `RAGEvaluator` class with `evaluate_query()` and `evaluate_dataset()` methods
- Metrics: recall@kbId, citation rate, content match rate, latency (avg, p95)
- CLI: `--dataset`, `--test-set`, `--output` options
- Print summary tables and save detailed JSON results

#### 3. Integration

- Initialize RAG components (embedder, vector_store, llm_manager, retriever)
- Evaluate each query in dataset
- Aggregate metrics per test set
- Output formatted results

### Tests

- Add `test_scripts_test_queries.py` with mocked RAG components
- Test metric calculation accuracy
- Test JSON dataset loading and validation

## Phase 2.3: Observability Infrastructure

### Goal

Optional LangSmith/Langfuse integration for production tracing.

### Implementation

#### 1. Create LangSmith Config (`rag_engine/llm/langsmith_config.py` - NEW)

```python
"""LangSmith tracing configuration (optional)."""
def setup_langsmith() -> bool:
    # Check LANGCHAIN_TRACING_V2 and LANGSMITH_API_KEY env vars
    # LangChain automatically uses env vars if set
    # Return True if enabled
```

#### 2. Create Langfuse Config (`rag_engine/llm/langfuse_config.py` - NEW)

```python
"""Langfuse tracing configuration (optional)."""
def setup_langfuse() -> bool:
    # Check LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY env vars
    # Initialize Langfuse client if configured
    # Return True if enabled
```

#### 3. Create Observability Module (`rag_engine/observability/__init__.py` - NEW)

```python
"""Observability infrastructure."""
from rag_engine.llm.langsmith_config import setup_langsmith
from rag_engine.llm.langfuse_config import setup_langfuse

def setup_observability() -> None:
    setup_langsmith()
    setup_langfuse()
```

#### 4. Integrate into App

**Modify `rag_engine/api/app.py`**:

- Import `setup_observability` from `rag_engine.observability`
- Call `setup_observability()` after `setup_logging()`

#### 5. Update Settings (`rag_engine/config/settings.py`)

Add optional fields:

```python
langsmith_tracing: bool = False
langsmith_api_key: str = ""
langsmith_project: str = "cmw-rag"
langfuse_enabled: bool = False
langfuse_public_key: str = ""
langfuse_secret_key: str = ""
langfuse_host: str = "https://cloud.langfuse.com"
```

#### 6. Update Requirements (`rag_engine/requirements.txt`)

Add optional dependency:

```txt
langfuse>=2.0.0  # Optional: for Langfuse tracing
```

### Tests

- Add `test_llm_langsmith_config.py` to test setup (mocked env vars)
- Add `test_llm_langfuse_config.py` to test setup (mocked imports)
- Verify observability is non-blocking if not configured

## Phase 2.4: Code Organization

### Goal

Centralize configuration and extract provider logic.

### Implementation

#### 1. Create Input Modes Config (`rag_engine/config/input_modes.py` - NEW)

```python
"""Input mode configurations for document processing."""
INPUT_MODES = {
    "mkdocs_pipeline": {...},
    "compiled_kb_file": {...},
    "compiled_md_folder": {...},
}
def get_input_mode_config(mode: str) -> Dict[str, Any]: ...
```

#### 2. Create Provider Adapters (`rag_engine/llm/provider_adapters.py` - NEW)

Extract from `llm_manager.py`:

- `create_gemini_model()` function
- `create_openrouter_model()` function
- `create_chat_model()` factory function with provider mapping

**Modify `rag_engine/llm/llm_manager.py`**:

- Import provider adapters
- Replace inline provider creation in `_chat_model()` with `create_chat_model()`

### Tests

- Add `test_llm_provider_adapters.py` for provider factory functions
- Update `test_llm_manager.py` to verify provider adapter usage

## Phase 2.5: Documentation Updates

### Files to Modify

#### 1. Update README.md

Add sections:

- **Phase 2 Features**: Abstract interfaces, evaluation, observability
- **Evaluation**: How to run `test_queries.py` and interpret metrics
- **Observability**: LangSmith/Langfuse setup instructions
- **Architecture**: Interface protocols and swappable components

#### 2. Create Architecture Documentation (`docs/ARCHITECTURE.md` - NEW)

Content:

- Protocol-based interface design
- Component dependency graph
- How to implement custom backends (VectorStore, Embedder, etc.)
- Extension points and customization

#### 3. Create Evaluation Guide (`docs/EVALUATION.md` - NEW)

Content:

- Test dataset format
- Running evaluations
- Metric definitions (recall@kbId, citation rate, etc.)
- Adding new test queries
- Interpreting results

#### 4. Create Observability Guide (`docs/OBSERVABILITY.md` - NEW)

Content:

- LangSmith setup and configuration
- Langfuse setup and configuration
- Viewing traces and monitoring
- Production best practices

### Update Existing Docs

- `README.md`: Add Phase 2 sections
- Ensure all examples use latest API

## Phase 2.6: Test Suite Updates

### New Test Files

1. `test_core_interfaces.py` - Protocol compliance verification
2. `test_scripts_test_queries.py` - Evaluation script tests
3. `test_llm_langsmith_config.py` - LangSmith setup tests
4. `test_llm_langfuse_config.py` - Langfuse setup tests
5. `test_llm_provider_adapters.py` - Provider adapter tests

### Updated Test Files

1. `test_core_indexer.py` - Add tests for swappable chunker/enricher
2. `test_core_chunker.py` - Add tests for CodeSafeChunker adapter class
3. `test_core_metadata_enricher.py` - Add tests for DefaultMetadataEnricher adapter
4. `test_storage_vector_store.py` - Add Protocol compliance comment tests
5. `test_retrieval_embedder.py` - Add Protocol compliance comment tests
6. `test_retrieval_reranker.py` - Add Protocol compliance comment tests

### Test Coverage Goals

- All new interfaces have type checking tests
- Evaluation framework has unit tests
- Observability setup is tested (mocked)
- Backward compatibility verified (all Phase 1 tests pass)

## .env Additions

```env
# Observability (optional)
LANGSMITH_TRACING=false
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=cmw-rag
LANGFUSE_ENABLED=false
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

## Implementation Checklist

### Phase 2.1: Interfaces

- [ ] Create `rag_engine/core/interfaces.py`
- [ ] Create `rag_engine/retrieval/interfaces.py`
- [ ] Create `rag_engine/storage/interfaces.py`
- [ ] Wrap chunker: add `CodeSafeChunker` class, keep `split_text()` function
- [ ] Wrap metadata_enricher: add `DefaultMetadataEnricher` class, keep `enrich_metadata()` function
- [ ] Update `RAGIndexer.__init__()` with optional chunker/enricher parameters
- [ ] Update `RAGIndexer.index_documents()` to use `self.chunker` and `self.enricher`
- [ ] Add Protocol compliance comments to existing implementations
- [ ] Create `test_core_interfaces.py`
- [ ] Update `test_core_indexer.py` with swappable component tests

### Phase 2.2: Evaluation

- [ ] Create `rag_engine/tests/test_queries.json` with sample queries
- [ ] Create `rag_engine/scripts/test_queries.py`
- [ ] Implement `RAGEvaluator` class with metrics
- [ ] Add CLI argument parsing
- [ ] Create `test_scripts_test_queries.py`

### Phase 2.3: Observability

- [ ] Create `rag_engine/llm/langsmith_config.py`
- [ ] Create `rag_engine/llm/langfuse_config.py`
- [ ] Create `rag_engine/observability/__init__.py`
- [ ] Integrate into `rag_engine/api/app.py`
- [ ] Update `rag_engine/config/settings.py` with observability fields
- [ ] Update `rag_engine/requirements.txt` with optional langfuse
- [ ] Create `test_llm_langsmith_config.py`
- [ ] Create `test_llm_langfuse_config.py`

### Phase 2.4: Organization

- [ ] Create `rag_engine/config/input_modes.py`
- [ ] Create `rag_engine/llm/provider_adapters.py`
- [ ] Extract provider logic from `llm_manager.py`
- [ ] Update `llm_manager.py` to use provider adapters
- [ ] Create `test_llm_provider_adapters.py`

### Phase 2.5: Documentation

- [ ] Update `README.md` with Phase 2 features
- [ ] Create `docs/ARCHITECTURE.md`
- [ ] Create `docs/EVALUATION.md`
- [ ] Create `docs/OBSERVABILITY.md`
- [ ] Update existing documentation examples

### Phase 2.6: Tests

- [ ] Create all new test files
- [ ] Update existing test files with interface tests
- [ ] Run full test suite to verify backward compatibility
- [ ] Add type checking (mypy) to CI/CD

## Success Criteria

- All Phase 1 tests pass without modification
- Protocol interfaces enable backend swapping
- Evaluation framework provides systematic metrics
- Observability is optional and non-intrusive
- Documentation covers all Phase 2 features
- Test coverage maintained or improved

### To-dos

- [ ] Create Protocol interfaces for Chunker and MetadataEnricher in rag_engine/core/interfaces.py
- [ ] Create Protocol interfaces for Embedder and Reranker in rag_engine/retrieval/interfaces.py
- [ ] Create Protocol interface for VectorStore in rag_engine/storage/interfaces.py
- [ ] Wrap chunker.py split_text() function in CodeSafeChunker class, maintain backward compatibility
- [ ] Wrap metadata_enricher.py enrich_metadata() function in DefaultMetadataEnricher class, maintain backward compatibility
- [ ] Update RAGIndexer.__init__() to accept optional chunker and metadata_enricher parameters with defaults
- [ ] Update RAGIndexer.index_documents() to use self.chunker.split_text() and self.enricher.enrich_metadata()
- [ ] Add Protocol compliance comments to ChromaStore, FRIDAEmbedder, and reranker classes
- [ ] Create test_core_interfaces.py to verify Protocol compliance via type checking
- [ ] Update test_core_indexer.py to test with swappable chunker/enricher implementations
- [ ] Create rag_engine/tests/test_queries.json with bilingual test query dataset
- [ ] Create rag_engine/scripts/test_queries.py with RAGEvaluator class and CLI
- [ ] Create test_scripts_test_queries.py with mocked RAG components
- [ ] Create rag_engine/llm/langsmith_config.py with setup_langsmith() function
- [ ] Create rag_engine/llm/langfuse_config.py with setup_langfuse() function
- [ ] Create rag_engine/observability/__init__.py with setup_observability() function
- [ ] Integrate setup_observability() into rag_engine/api/app.py
- [ ] Add observability settings fields to rag_engine/config/settings.py
- [ ] Add optional langfuse>=2.0.0 to rag_engine/requirements.txt
- [ ] Create test_llm_langsmith_config.py and test_llm_langfuse_config.py
- [ ] Create rag_engine/config/input_modes.py with INPUT_MODES dict and helper function
- [ ] Create rag_engine/llm/provider_adapters.py with provider factory functions
- [ ] Refactor llm_manager.py to use provider adapters from provider_adapters.py
- [ ] Create test_llm_provider_adapters.py for provider factory functions
- [ ] Update README.md with Phase 2 features: interfaces, evaluation, observability
- [ ] Create docs/ARCHITECTURE.md with interface design and extension points
- [ ] Create docs/EVALUATION.md with test dataset format and metrics guide
- [ ] Create docs/OBSERVABILITY.md with LangSmith/Langfuse setup instructions
- [ ] Update existing test files to add Protocol compliance and interface tests
- [ ] Run full test suite to verify all Phase 1 tests pass without modification