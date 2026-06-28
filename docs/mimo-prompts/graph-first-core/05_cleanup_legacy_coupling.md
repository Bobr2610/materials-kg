# Prompt 05: Cleanup Legacy Coupling Around the New Core

You are working in the `materials-kg` repo. Reduce accidental coupling between the new graph-first core and the legacy donor stack, without deleting or rewriting the legacy modules themselves.

## Goal

Find and remove the most harmful coupling points where new-core code paths, tests, or startup surfaces unnecessarily depend on legacy `graph`, `agent`, or heavyweight API runtime code. Keep the new core runnable and testable in isolation.

## Files to inspect first

- `kg_engine/api/materials_core.py`
- `kg_engine/api/__init__.py`
- `kg_engine/api/app.py`
- `kg_engine/api/server.py`
- `kg_engine/scripts/ingest_materials_kg.py`
- `kg_engine/scripts/build_knowledge_graph.py`
- `kg_engine/repositories/factory.py`
- `kg_engine/services/materials_kg.py`
- `kg_engine/tests/test_materials_api_smoke.py`
- `kg_engine/tests/test_materials_kg_core.py`

## Known context

- The new canonical path is `domain -> repositories -> services -> api`.
- `kg_engine/graph/` and `kg_engine/agent/` are still present as prototype/donor code.
- `kg_engine/api/app.py` is a very large legacy application surface with retrieval, Gradio, and runtime initialization side effects.
- The new core should not need that legacy surface just to import, test, ingest, or query.

## Desired work

- Reduce import-time side effects on new-core paths.
- Decouple standalone graph-first API and ingestion flows from legacy runtime initialization.
- Where there is ambiguous ownership, bias new code toward `materials_core.py`, `repositories/factory.py`, and `services/materials_kg.py`.
- Keep legacy modules available, but stop making them implicit prerequisites for the new core.

## Constraints

- Do not delete `kg_engine/graph/` or `kg_engine/agent/`.
- Do not break existing legacy entrypoints unless they are already broken and the fix is obviously compatible.
- Avoid broad renames or directory moves.
- Prefer isolation, lazy import, or explicit entrypoint separation over large rewrites.

## Acceptance criteria

- The new graph-first core can be imported and tested without triggering heavyweight legacy startup paths.
- No new-core module adds direct imports from `kg_engine.graph.*` or `kg_engine.agent.*`.
- Any coupling cleanup is backed by focused tests or smoke checks.
- Legacy surfaces remain present, but new-core flows no longer depend on them transitively.

## Verification commands

```bash
ruff check kg_engine/api kg_engine/scripts kg_engine/tests
python -m pytest kg_engine/tests/test_materials_api_smoke.py kg_engine/tests/test_materials_kg_core.py -v
python -c "import kg_engine.api.materials_core; print('materials_core import ok')"
python -c "from kg_engine.scripts.ingest_materials_kg import main; print('ingest script import ok')"
```

## What not to touch

- Do not convert this into a repo-wide cleanup of all legacy code.
- Do not rewrite the entire Gradio app.
- Do not modify old graph extraction behavior unless a tiny compatibility shim is absolutely necessary.
- Do not spend effort on documentation-only changes.

## Output expected from you

- Implement the patch.
- Name the exact coupling points you removed or isolated.
- Report the verification commands you ran and any remaining legacy dependency you intentionally left in place.
