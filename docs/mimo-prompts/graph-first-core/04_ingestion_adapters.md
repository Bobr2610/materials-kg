# Prompt 04: Ingestion Adapters Into the Graph-First Core

You are working in the `materials-kg` repo. Build or repair ingestion adapters so outputs from the existing document-processing pipeline can flow into the new graph-first core without ad hoc glue code.

## Goal

Connect the current preprocessing/document pipeline to `MaterialsKGService` by introducing a minimal adapter layer that turns parsed document artifacts into typed `DocumentInput`, `ExperimentInput`, `TextUnitInput`, or other existing graph-first input models.

## Files to inspect first

- `kg_engine/core/document_processor.py`
- `kg_engine/core/chunker.py`
- `kg_engine/core/indexer.py`
- `kg_engine/scripts/ingest_materials_kg.py`
- `kg_engine/domain/models.py`
- `kg_engine/services/materials_kg.py`
- `kg_engine/tests/test_core_indexer.py`
- `kg_engine/tests/test_materials_kg_core.py`
- `docs/ARCHITECTURE.md`

## Desired work

- Reuse existing typed input models instead of pushing raw dicts through the service layer.
- Preserve provenance-rich metadata already emitted by `DocumentProcessor`, especially `kbId`, `title`, `source_file`, `source_type`, and `section_index`.
- Add a small adapter module or helper functions in the most natural place near the ingestion path.
- Make `kg_engine/scripts/ingest_materials_kg.py` able to consume adapted document payloads with less manual JSON reshaping where appropriate.
- Keep the boundary explicit: preprocessing/chunking prepares artifacts, adapter maps them, service ingests typed models.

## Constraints

- Do not invent a second service API; use `MaterialsKGService`.
- Do not pull in legacy `kg_engine.graph.pipeline` code for the adapter path.
- Do not over-design a generic ETL framework.
- Prefer typed Pydantic model construction over free-form dictionaries.
- Keep file movement minimal; additive helpers are fine.

## Acceptance criteria

- There is a clear, typed path from document-processing output into graph-first ingestion models.
- Adapter code preserves source metadata needed for evidence/provenance later.
- New or updated tests demonstrate at least one end-to-end adapted ingestion flow using the in-memory repository.
- The ingestion script remains usable for JSON batch input and gains a clean path for adapted local document inputs if you add that capability.
- No new direct dependency on `kg_engine.graph.*` or `kg_engine.agent.*` is introduced.

## Verification commands

```bash
ruff check kg_engine/core kg_engine/scripts/ingest_materials_kg.py kg_engine/tests
python -m pytest kg_engine/tests/test_materials_kg_core.py -v
python -m pytest kg_engine/tests/test_core_indexer.py -v
```

If you add a new adapter-focused test file, run it explicitly as well.

## What not to touch

- Do not replace `DocumentProcessor` with a new parser.
- Do not change the canonical domain input model names without a compelling compatibility reason.
- Do not rewrite vector indexing or retrieval logic as part of this task.
- Do not remove the existing JSON batch ingestion path from `ingest_materials_kg.py`.

## Output expected from you

- Implement the patch.
- Describe the adapter boundary you introduced.
- List preserved metadata fields and the verification commands you ran.
