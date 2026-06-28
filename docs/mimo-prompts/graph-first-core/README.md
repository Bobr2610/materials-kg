# Mimo Prompt Pack: Graph-First Core Repairs

This pack is for Mimo runs focused on code repair and targeted improvements in the new graph-first core of `materials-kg`.

Use the prompts independently:

1. [01_api_wiring.md](./01_api_wiring.md) - wire the standalone graph-first API cleanly
2. [02_postgres_repository_hardening.md](./02_postgres_repository_hardening.md) - harden Postgres persistence behavior
3. [03_tests_and_dependencies.md](./03_tests_and_dependencies.md) - close test and dependency gaps around the new core
4. [04_ingestion_adapters.md](./04_ingestion_adapters.md) - connect document-processing outputs to graph-first ingestion inputs
5. [05_cleanup_legacy_coupling.md](./05_cleanup_legacy_coupling.md) - reduce accidental coupling to the legacy stack

Shared repo context for every prompt:

- Canonical new-core path: `kg_engine/domain/ -> kg_engine/repositories/ -> kg_engine/services/ -> kg_engine/api/`
- Primary new-core files:
  - `kg_engine/services/materials_kg.py`
  - `kg_engine/repositories/protocols.py`
  - `kg_engine/repositories/postgres.py`
  - `kg_engine/repositories/memory.py`
  - `kg_engine/api/materials_core.py`
- Existing targeted tests:
  - `kg_engine/tests/test_materials_kg_core.py`
  - `kg_engine/tests/test_materials_api_smoke.py`
- Legacy donor stack to avoid expanding:
  - `kg_engine/graph/`
  - `kg_engine/agent/`
  - most of `kg_engine/api/app.py`

These prompts are intentionally code-oriented and should not be used for documentation-only work.
