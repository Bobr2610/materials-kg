# Materials Knowledge Graph

Graph-first materials knowledge graph for structured ingestion, explainable query, and gap analysis.

The current core is centered on typed domain models, repository-backed persistence, and a compact service API. Postgres is the primary persistence target, with `pgvector` used for searchable text units and hybrid evidence lookup.

## Current Architecture

```text
materials-kg/
  kg_engine/
    domain/        # Typed entities, relations, observations, traces, query DTOs
    repositories/  # Persistence protocol + Postgres/pgvector and in-memory adapters
    services/      # Graph-first ingestion/query API
    api/           # Application-facing HTTP/UI entrypoints
    core/          # Document processing, chunking, indexing helpers
    retrieval/     # Embeddings, reranking, search helpers
    graph/         # Legacy prototype graph pipeline and agent-facing tools
    agent/         # Legacy/prototype agent stack and orchestration
```

## What Is Source Of Truth

- `kg_engine/domain/` defines the canonical business objects: entities, evidence, relations, observations, decision traces, coverage rules, and query result envelopes.
- `kg_engine/repositories/protocols.py` defines the persistence contract used by the service layer.
- `kg_engine/services/materials_kg.py` is the public graph-first ingestion and query API.
- `kg_engine/repositories/postgres.py` is the primary durable backend and includes schema bootstrap for Postgres + `pgvector`.

## Storage Model

The Postgres repository persists:

- canonical entities and alias resolution
- typed relations between entities
- evidence with source spans and extraction metadata
- observations with measured values and units
- decision traces for explainability and history
- coverage rules for gap analysis
- searchable text units with optional `VECTOR(1536)` embeddings

## Ingestion API

The main service surface is `MaterialsKGService`:

```python
from kg_engine.repositories.memory import InMemoryMaterialsKGRepository
from kg_engine.services.materials_kg import MaterialsKGService

service = MaterialsKGService(InMemoryMaterialsKGRepository())

service.ingest_reference_data(...)
service.ingest_experiments(...)
service.ingest_documents(...)
```

These entrypoints support three complementary flows:

- reference dictionaries and coverage rules
- structured experiment ingestion with observations and findings
- document ingestion with references, findings, tags, and searchable text units
- mixed folder ingestion: one recursive input path can contain JSON, JSONL, CSV, TSV,
  TXT, and Markdown files; explicit structured records are ingested as graph data,
  and unknown rows/files are preserved as source documents instead of being guessed
  from filenames.

## Query API

`MaterialsKGService` exposes graph-first read paths:

- `query_material_mode(material, mode=None, property_name=None)`
- `query_property(property_name, filters=None)`
- `query_related(entity, depth=2, relation_filters=None)`
- `query_decision_history(entity_or_experiment)`
- `query_data_gaps(scope=None, filters=None)`

These return typed result models from `kg_engine/domain/models.py`, not raw graph objects.

## Postgres + pgvector Bootstrap

```bash
docker compose up -d materials-postgres
```

Use:

```bash
set MATERIALS_PG_DSN=postgresql://materials:materials@127.0.0.1:55432/materials_kg
set MATERIALS_API_ENSURE_SCHEMA=true
```

`ensure_schema()` creates the materials KG tables and enables the `vector`
extension required for text-unit embeddings. If `MATERIALS_PG_DSN` is empty,
the service falls back to the in-memory repository for tests and local smoke
checks.

## Quick Start

### Install (editable)

```bash
pip install -e ".[dev]"
```

### Run the core API

```bash
python kg_engine/scripts/run_materials_api.py
# API at http://0.0.0.0:8090, docs at http://0.0.0.0:8090/docs
```

The same process also serves the analytical UI at `http://127.0.0.1:8090/`.
It accepts free-form research questions and shows the answer, matched graph
entities, experiments, measurements, evidence, related entities, decision
history, and data gaps.

### Ingest sample data

```bash
python kg_engine/scripts/ingest_materials_kg.py \
  --reference path/to/reference.json \
  --experiments path/to/experiments.json \
  --documents path/to/documents.json
```

For an unsorted drop folder, use a single input path:

```bash
python kg_engine/scripts/ingest_materials_kg.py --input path/to/drop-folder --ensure-schema
```

The mixed loader does not classify entities from natural-language filenames or
keyword guesses. It accepts explicit schema fields for canonical entities and
experiments, treats raw text files as documents, and preserves unclassified
structured rows as searchable documents with source-path metadata.

The `data/` directory contains fixture data for sample materials covering:
- Reference entities (materials, properties, modes, equipment, teams)
- Coverage rules for gap analysis (mechanical properties × modes)
- Structured experiments with observations and findings
- Internal documents with linked entities and text units

### Run tests

```bash
python -m pytest -q
ruff check kg_engine
```

## Legacy Stack Status

`kg_engine/graph/` and `kg_engine/agent/` remain in the repository as a legacy prototype/donor stack. They are still useful as reference implementations, migration material, and tool/UI experiments, but they are no longer the canonical architecture for the new graph-first core.

## References

- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) for the layer model, storage layout, and API walkthrough
- [AGENTS.md](./AGENTS.md) for repo conventions and developer workflows
- [`.agents/skills/materials-knowledge-graph/SKILL.md`](./.agents/skills/materials-knowledge-graph/SKILL.md) for domain notes and examples
