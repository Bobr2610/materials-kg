# Deep Research Report: Materials KG Conversion

**Date:** 2026-06-27  
**Scope:** Full project analysis — converting CMW/Comindware-based repository into a Materials Knowledge Graph / search-analytics system  
**Constraint:** Analysis only, no file edits.

---

## Executive Summary

The repository contains two parallel systems sharing the `kg_engine` package:

**New graph-first core** (the target architecture) — `domain/` → `repositories/` → `services/` → `api/materials_core.py`. This is clean, tested, and follows a repository pattern with in-memory and Postgres/pgvector backends.

**Legacy CMW/Comindware RAG stack** (the donor) — a 4800-line Gradio app, LangChain agent, ChromaDB retrieval, and Comindware-specific tooling occupying most of the package.

The new core satisfies roughly 60% of the assignment. It handles structured ingestion (reference data, experiments, documents), typed query (material+mode, property, related entities, decision history, data gaps), and provenance tracking. Missing: LLM extraction integration in the new path, embedding-based search in the service layer, coverage rule seeding, and data import scripts for real materials data.

The legacy system is deeply entangled: `config/settings.py` requires CMW credentials at import time, and ~30 source files reference `kb.comindware.ru`, `PlatformConnector`, or CMW-specific utilities.

---

## Architecture Map

### New Core Path (target)

```
kg_engine/domain/
  models.py          Entity, Relation, Observation, DecisionTrace, DataGap, Evidence, SearchTextUnit
  resolution.py      normalize_name(), ReferenceResolver

kg_engine/repositories/
  protocols.py       MaterialsKGRepository (Protocol)
  memory.py          InMemoryMaterialsKGRepository
  postgres.py        PostgresMaterialsKGRepository (pgvector TEXT search)
  factory.py         create_materials_repository()

kg_engine/services/
  materials_kg.py    MaterialsKGService — ingest_reference_data, ingest_experiments,
                     ingest_documents, query_material_mode, query_property,
                     query_related, query_decision_history, query_data_gaps

kg_engine/api/
  materials_core.py  FastAPI app: /health, /ingest/*, /query/*

kg_engine/ingestion/
  adapters.py        ReferenceDataAdapter, ExperimentCatalogAdapter,
                     DocumentCorpusAdapter, StaffDirectoryAdapter, TagCatalogAdapter

kg_engine/scripts/
  ingest_materials_kg.py   CLI ingestion (reference, experiments, documents, staff, tags)
  run_materials_api.py     Uvicorn launcher
```

### Legacy Graph Module (self-contained NetworkX prototype)

```
kg_engine/graph/
  schemas.py     EntityType (8 values), GraphRelation, ExtractionResult
  store.py       GraphStore (NetworkX MultiDiGraph, JSON serialize)
  extractor.py   EntityExtractor (regex + LLM extraction)
  builder.py     KnowledgeGraphBuilder
  query.py       KnowledgeGraphQuery
  search.py      HybridSearch
  pipeline.py    GraphPipeline
  tools.py       LangChain @tool functions (query_material, query_property, etc.)
```

### Legacy CMW/RAG Stack (donor)

```
kg_engine/api/app.py           4811-line Gradio UI + CMW webhook endpoints
kg_engine/llm/                 LLM manager, prompts (Comindware-specific), schemas
kg_engine/retrieval/           ChromaDB vector search, embeddings, reranker
kg_engine/agent/               LangChain agent orchestration
kg_engine/tools/               retrieve_context (KB articles), web_search, PDF, math
kg_engine/utils/cmw_webapi.py  CMW WebAPI response helpers
kg_engine/utils/platform_record_image.py
kg_engine/utils/platform_record_document.py
kg_engine/utils/platform_entity_resolver.py
kg_engine/config/settings.py   Mixed CMW_* and materials_* settings
```

---

## CMW Cleanup Inventory

### Group A — Active Runtime (blocks import/startup if not cleaned)

| File | Lines | Issue |
|------|-------|-------|
| `config/settings.py` | 237–245 | Six `cmw_*` fields are **required** — `cmw_base_url`, `cmw_login`, `cmw_password`, `cmw_api_key` have no default; Pydantic `BaseSettings` raises `ValidationError` if `.env` lacks them |
| `config/settings.py` | 121–131 | `.env.example` has `CMW_BASE_URL`, `CMW_LOGIN`, `CMW_PASSWORD`, `CMW_TIMEOUT` — any new deploy must set these even if unused |
| `api/app.py` | 70 | `_article_to_dict` hardcodes `kb.comindware.ru` URL fallback |
| `api/app.py` | 3450–4742 | `ask_comindware()`, `ask_comindware_structured()`, CMW process-support endpoints — imported at module level |
| `llm/schemas.py` | 16 | `from kg_engine.cmw_platform.category_enum import ...` inside `TYPE_CHECKING` — safe but still a dead import |
| `llm/prompts.py` | 12–286 | 30+ lines of Comindware self-description, `kb.comindware.ru` link templates, platform terminology blocks |
| `llm/llm_manager.py` | 310 | Citation builder returns `kb.comindware.ru` URLs |
| `tools/retrieve_context.py` | 330 | Article URL fallback to `kb.comindware.ru` |
| `utils/formatters.py` | 86 | Citation formatter uses `kb.comindware.ru` |
| `retrieval/retriever.py` | 289 | Article URL in retriever output |
| `tests/test_llm_prompts.py` | 10 | Asserts `"kb.comindware.ru" in prompt` |
| `tests/test_utils_formatters.py` | 32–39 | Uses `kb.comindware.ru` URLs in test data |

### Group B — Legacy Utility Files (donor-only, not imported by new core)

| File | Purpose |
|------|---------|
| `utils/cmw_webapi.py` | WebAPI payload unwrap, ID extraction |
| `utils/platform_record_image.py` | CMW image record operations |
| `utils/platform_record_document.py` | CMW document record operations |
| `utils/platform_entity_resolver.py` | CMW entity resolution |
| `utils/browser_tools.py` | Browser automation for CMW UI |
| `utils/asset_extractor.py` | Asset extraction from CMW pages |

### Group C — CMW Skills and Scripts (outside materials-kg scope, safe to ignore)

| Path | Count |
|------|-------|
| `.agents/skills/cmw-platform/scripts/` | 12 Python files (apply_renames, extract_ctf, etc.) |
| `.agents/skills/cmw-platform-account-bootstrap/` | Account creation workflows |
| `.agents/skills/cmw-platform-backup-launch/` | Backup launch scripts |
| `.agents/skills/cmw-platform-instance-switch/` | Instance switching |
| `.agents/skills/cmw-platform-process-record-fill/` | Record fill workflows |
| `.agents/skills/cmw-platform-staff-account-link/` | Staff account linking |

These live in `.agents/skills/` — outside `kg_engine/` — and are agent orchestration resources, not runtime code.

### Group D — Documentation/Config Artifacts

| File | Issue |
|------|-------|
| `.env.example` | 15+ CMW-specific variables (lines 56–141) |
| `README.md` | References legacy graph/ as "Legacy prototype" but lacks new-core documentation |
| `pyproject.toml` | No `[project]` section — package metadata absent |
| `requirements_agent.txt` | 204-line pinned dependencies for the legacy agent stack |
| `requirements_core.txt` | Clean, 13 lines — only new-core dependencies |

---

## Completion Gaps Against the Assignment

The assignment specifies: *connect articles, experiments, materials, properties, modes, equipment, teams, conclusions, decision history, data gaps.*

### Covered by New Core

| Capability | Status | Evidence |
|------------|--------|----------|
| Materials | ✅ | `EntityKind.MATERIAL`, ingest, query |
| Properties | ✅ | `EntityKind.PROPERTY`, property query with range filters |
| Experiments | ✅ | `EntityKind.EXPERIMENT`, structured ingestion with observations |
| Modes | ✅ | `EntityKind.MODE`, material+mode query |
| Equipment | ✅ | `EntityKind.EQUIPMENT`, linked via experiments |
| Teams | ✅ | `EntityKind.TEAM`, staff directory adapter |
| Conclusions/Findings | ✅ | `DecisionTrace` model, finding ingestion |
| Decision History | ✅ | `query_decision_history()`, trace chain via `changed_from_trace_id` |
| Data Gaps | ✅ | `query_data_gaps()` with coverage rules |
| Provenance | ✅ | `Evidence` model with source spans, extraction methods, confidence |

### Missing / Incomplete

| Gap | Severity | Details |
|-----|----------|---------|
| **Articles/Documents as first-class entities** | Medium | `EntityKind.DOCUMENT` exists but `ARTICLE` (from old schemas) is not in new `EntityKind` enum. Assignment asks for article connectivity. |
| **LLM extraction in new path** | High | `graph/extractor.py` has regex+LLM extraction but targets old `GraphEntity` schema. New `domain/models.py` has no extraction pipeline — ingestion is structured-only. |
| **Embedding-based text search** | Medium | Postgres repo uses `ILIKE` for `search_text_units()`. pgvector column exists (`VECTOR(1536)`) but no cosine search implemented. |
| **Coverage rule seeding** | Medium | `CoverageRuleInput` model exists, API supports it, but no script or sample data to seed rules for real material-mode-property matrices. |
| **Real data ingestion scripts** | High | `ingest_materials_kg.py` accepts JSON files but no sample/reference JSON data exists in the repo. |
| **Hybrid search (vector + graph)** | Medium | `graph/search.py` has `HybridSearch` targeting old `GraphStore`. New path has no equivalent combining pgvector similarity with graph traversal. |
| **API documentation** | Low | No OpenAPI descriptions on `materials_core.py` endpoints beyond default. |
| **Migration bridge** | Low | No script to migrate data from old `GraphStore` JSON to new Postgres schema. |

---

## Test and Dependency Readiness

### Test Inventory

| Test File | Covers | Status |
|-----------|--------|--------|
| `tests/test_materials_kg_core.py` | Service layer: alias resolution, provenance, gap analysis, material+mode query, incremental reingestion | 5 tests, all passing |
| `tests/test_materials_api_smoke.py` | FastAPI health + ingest + query flow | 1 test, passing |
| `tests/test_repository_factory.py` | Factory routing (memory vs postgres) | 5 tests, passing |
| `tests/test_ingestion_adapters.py` | All 5 adapter classes | 4 tests, passing |
| `tests/test_graph.py` | Old graph schemas, store, query, extractor | 294 lines, self-contained |
| `tests/test_core_*.py` | Legacy document processing, chunking, indexing | Legacy stack tests |
| `tests/test_retrieval_*.py` | Legacy retrieval, reranker, embedder | Legacy stack tests |
| `tests/test_llm_*.py` | Legacy LLM prompts, token utils | Legacy stack tests |

### Dependency Status

- **pytest 9.0.2** — available in base Python interpreter
- **requirements_core.txt** — clean, 13 packages (fastapi, pydantic, pydantic-settings, uvicorn, pytest, httpx)
- **requirements_agent.txt** — 204 pinned packages for legacy agent (LangChain, Gradio, ChromaDB, etc.)
- **networkx** — required by old `graph/store.py` but not in `requirements_core.txt` (only needed for legacy path)
- **psycopg** — optional for Postgres backend (commented out in `requirements_core.txt`)

### Gap: No `[project]` in pyproject.toml

The `pyproject.toml` only has `[tool.ruff]` and `[tool.mypy]` sections. There is no `[project]` or `[build-system]` section, so the package cannot be installed via `pip install -e .`. This blocks CI/CD and clean virtual environment setup.

---

## Prioritized Subagent Backlog

### T1 — Remove CMW settings requirement (critical, ~30 min)

**Files:** `config/settings.py`, `.env.example`  
**Goal:** Make `cmw_base_url`, `cmw_login`, `cmw_password`, `cmw_api_key` optional with empty defaults so the new core can start without CMW credentials.  
**Acceptance:** `python -c "from kg_engine.config.settings import settings"` succeeds without any CMW env vars set.

### T2 — Decouple app.py from CMW (high, ~2 hr)

**Files:** `api/app.py`  
**Goal:** Guard all `kb.comindware.ru` references, `ask_comindware` functions, and CMW endpoint handlers behind `if settings.cmw_base_url:` checks or move to a separate legacy module.  
**Acceptance:** `api/app.py` imports cleanly; CMW endpoints only register when CMW settings are configured.

### T3 — Add LLM extraction to new ingestion path (high, ~3 hr)

**Files:** New file `kg_engine/ingestion/extractor.py` or extend `services/materials_kg.py`  
**Goal:** Bridge `graph/extractor.py` regex+LLM extraction to produce `domain/models.py` entities and relations, enabling unstructured text ingestion.  
**Acceptance:** A function that takes raw text and produces `Entity` + `Relation` objects storable via the repository.

### T4 — Implement pgvector cosine search (medium, ~2 hr)

**Files:** `repositories/postgres.py`  
**Goal:** Replace `ILIKE` in `search_text_units()` with `1 - (embedding <=> query_embedding)` cosine similarity when embeddings are present.  
**Acceptance:** `search_text_units(query, embedding=vector)` returns ranked results by similarity.

### T5 — Create sample data and ingestion examples (medium, ~2 hr)

**Files:** New `data/` directory, update `scripts/ingest_materials_kg.py`  
**Goal:** Provide JSON fixtures for Ti-6Al-4V, IN718, Al6061 with realistic properties, modes, and coverage rules.  
**Acceptance:** `python kg_engine/scripts/ingest_materials_kg.py --reference data/reference.json --experiments data/experiments.json` populates a working graph.

### T6 — Add pyproject.toml project metadata (medium, ~30 min)

**Files:** `pyproject.toml`  
**Goal:** Add `[project]` section with name, version, dependencies, and `[build-system]`.  
**Acceptance:** `pip install -e .` succeeds; `python -m pytest kg_engine/tests/test_materials_kg_core.py` passes.

### T7 — Write Postgres integration tests (low, ~2 hr)

**Files:** New `tests/test_postgres_repository.py`  
**Goal:** Test full repository CRUD against a real Postgres instance (skipped when `MATERIALS_PG_DSN` unset).  
**Acceptance:** `MATERIALS_PG_DSN=... python -m pytest tests/test_postgres_repository.py` passes all CRUD and query operations.

### T8 — Build hybrid search for new path (low, ~3 hr)

**Files:** New `kg_engine/services/search.py` or extend `services/materials_kg.py`  
**Goal:** Combine pgvector similarity search with graph traversal (BFS from matched entities) for enriched results.  
**Acceptance:** A `hybrid_search(query, top_k)` method returning ranked results with graph context.

### T9 — Clean legacy graph/ module (low, ~1 hr)

**Files:** `graph/__init__.py`, `graph/tools.py`  
**Goal:** Either remove old `graph/` module entirely or clearly mark it as deprecated with a README note. If keeping, ensure it does not shadow new core imports.  
**Acceptance:** `from kg_engine.graph import *` only exposes legacy types; new core is unaffected.

### T10 — CMW skill scripts audit (defer)

**Files:** `.agents/skills/cmw-platform/scripts/*.py`  
**Goal:** Verify these scripts are agent-orchestration resources (not runtime code) and confirm they are safe to keep as-is.  
**Acceptance:** No `kg_engine` imports from `.agents/skills/` scripts.

---

## Risks and Recommended Sequencing

### Risk 1 — Settings import crash (Critical)

The `Settings` class in `config/settings.py` has no defaults for `cmw_base_url`, `cmw_login`, `cmw_password`, `cmw_api_key`. Any import of `kg_engine.config.settings` without these env vars raises `ValidationError`. This blocks every module that uses `settings` — including the new core scripts.

**Mitigation:** T1 must be completed first. Give CMW fields empty-string defaults.

### Risk 2 — Dual schema confusion (High)

`graph/schemas.py` defines `EntityType` (8 values: MATERIAL, PROPERTY, EXPERIMENT, MODE, EQUIPMENT, TEAM, ARTICLE, CONCLUSION) and `domain/models.py` defines `EntityKind` (8 values: MATERIAL, EXPERIMENT, PROPERTY, MODE, EQUIPMENT, TEAM, DOCUMENT, TAG). The enums overlap but differ — `ARTICLE` vs `DOCUMENT`, `CONCLUSION` vs `TAG`. Contributors may import the wrong one.

**Mitigation:** T9 (clean legacy graph module) or add explicit `__all__` restrictions and docstring warnings.

### Risk 3 — No package installability (Medium)

Without `[project]` in `pyproject.toml`, the package cannot be `pip install -e .`. This forces `sys.path` hacks in every script and makes CI setup fragile.

**Mitigation:** T6 (add project metadata).

### Risk 4 — pgvector search gap (Medium)

The Postgres repository stores embeddings in `VECTOR(1536)` columns but queries use text `ILIKE`. This means vector search is silently degraded to keyword matching — embeddings are stored but never used for similarity.

**Mitigation:** T4 (implement cosine search).

### Risk 5 — Large app.py blast radius (Low for new core)

`api/app.py` is 4811 lines and contains the entire legacy Gradio UI. Importing it pulls in Gradio, LangChain, ChromaDB, and all CMW modules. The new `api/materials_core.py` is clean and independent, but any future shared code between the two will create dependency tangles.

**Mitigation:** T2 (decouple CMW from app.py) and keep `materials_core.py` as the sole entrypoint for the new system.

### Recommended Sequencing

```
Phase 1 (unblock new core):
  T1 → T6 → T5

Phase 2 (enrich new core):
  T3 → T4 → T8

Phase 3 (cleanup):
  T2 → T9 → T7 → T10
```

Phase 1 removes blockers and makes the new core installable and runnable with sample data. Phase 2 adds the missing product capabilities. Phase 3 cleans up legacy code and adds integration tests.

---

## Summary Table

| Dimension | Status | Notes |
|-----------|--------|-------|
| Domain models | ✅ Complete | 8 entity kinds, 9 relation types, evidence, observations, traces, gaps |
| Repository pattern | ✅ Complete | Protocol + in-memory + Postgres implementations |
| Service layer | ✅ Complete | 6 public methods covering all query types |
| REST API | ✅ Complete | 7 endpoints (health + 3 ingest + 3 query + 1 gap) |
| Ingestion adapters | ✅ Complete | 5 adapters for different source families |
| CLI scripts | ✅ Complete | Ingestion + API server launcher |
| Tests (new core) | ✅ Good | 15 tests across service, API, factory, adapters |
| LLM extraction | ❌ Missing | Old extractor targets different schema |
| Vector search | ❌ Degraded | pgvector column exists but not used for similarity |
| Package metadata | ❌ Missing | No [project] in pyproject.toml |
| Sample data | ❌ Missing | No reference JSON fixtures |
| CMW decoupling | ❌ Not done | 6 required settings fields, 30+ source references |
