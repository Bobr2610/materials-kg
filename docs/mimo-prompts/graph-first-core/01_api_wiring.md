# Prompt 01: API Wiring for the Graph-First Core

You are working in the `materials-kg` repo. Repair and finish API wiring for the new graph-first core so that the standalone FastAPI surface is easy to run, easy to test, and does not depend on the legacy Gradio/agent stack during import.

## Goal

Make the graph-first API a first-class runnable surface around `MaterialsKGService`, using the existing `kg_engine/api/materials_core.py` entrypoint and repository factory. The result should support clean health, ingest, and query flows without importing heavy legacy startup code.

## Files to inspect first

- `kg_engine/api/materials_core.py`
- `kg_engine/api/__init__.py`
- `kg_engine/repositories/factory.py`
- `kg_engine/repositories/memory.py`
- `kg_engine/repositories/postgres.py`
- `kg_engine/config/settings.py`
- `kg_engine/scripts/ingest_materials_kg.py`
- `kg_engine/tests/test_materials_api_smoke.py`
- `kg_engine/tests/test_materials_kg_core.py`
- `kg_engine/api/app.py`
- `kg_engine/api/server.py`

## Desired work

- Keep `create_materials_app()` as the canonical standalone app factory for the new core.
- Ensure repository creation and optional schema bootstrap are wired consistently through `create_materials_repository(...)`.
- If needed, add a minimal runnable script or a minimal mount path for the new core, but keep it separate from the big Gradio app lifecycle.
- Preserve the ability to inject `MaterialsKGService` in tests.
- Avoid any import-time initialization of Chroma, Gradio, LLM managers, or retrieval components when only the materials core API is imported.

## Constraints

- Prefer minimal edits in `kg_engine/api/materials_core.py`, `kg_engine/repositories/factory.py`, and tightly related tests.
- Follow existing FastAPI and Pydantic patterns already used in the repo.
- Do not rewrite the large legacy app in `kg_engine/api/app.py`; isolate the graph-first API instead of merging it into legacy startup code.
- Do not add new framework dependencies unless strictly required.
- Keep backward-compatible request/response shapes for existing `/ingest/*` and `/query/*` routes.

## Acceptance criteria

- `create_materials_app()` can be imported without triggering legacy retrieval/Gradio initialization.
- The standalone API still exposes:
  - `GET /health`
  - `POST /ingest/reference`
  - `POST /ingest/experiments`
  - `POST /ingest/documents`
  - `POST /query/material-mode`
  - `POST /query/property`
  - `POST /query/related`
  - `POST /query/decision-history`
  - `POST /query/data-gaps`
- Test injection via `MaterialsKGService(InMemoryMaterialsKGRepository())` still works.
- If a DSN is configured, repository selection still flows through `create_materials_repository(...)`.
- No new direct imports from `kg_engine.graph.*` or `kg_engine.agent.*` are introduced into the graph-first API path.

## Verification commands

Run these after the patch:

```bash
ruff check kg_engine/api/materials_core.py kg_engine/repositories/factory.py kg_engine/tests/test_materials_api_smoke.py
python -m pytest kg_engine/tests/test_materials_api_smoke.py -v
python -m pytest kg_engine/tests/test_materials_kg_core.py -v
```

If you add a new runnable entrypoint, also verify it imports cleanly:

```bash
python -c "from kg_engine.api.materials_core import create_materials_app; app = create_materials_app(); print(app.title)"
```

## What not to touch

- Do not refactor the legacy UI/agent architecture in `kg_engine/api/app.py` beyond the smallest isolation change that is strictly necessary.
- Do not change `kg_engine/graph/` behavior.
- Do not change `kg_engine/agent/` behavior.
- Do not turn this task into a docs rewrite.
- Do not remove existing API routes from `materials_core.py`.

## Output expected from you

- Implement the patch.
- Add or update focused tests only where the new API path is affected.
- Return a concise summary of changed files, the exact verification commands you ran, and any remaining risk.
