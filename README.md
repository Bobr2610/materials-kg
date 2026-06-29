# Materials Knowledge Graph

Graph-backed Materials Hypothesis Factory for structured ingestion, explainable
query, gap analysis, and ranked research hypothesis generation.

The current product path is centered on typed domain models, a Neo4j-backed
graph repository, and a compact service/API layer. The runtime graph engine for
the site/API is Neo4j. In-memory storage is used only for unit tests.

## Current Architecture

```text
materials-kg/
  kg_engine/
    domain/        # Typed entities, relations, observations, traces, query DTOs
    repositories/  # Persistence protocol + Neo4j runtime, test memory
    services/      # Ingestion/query/hypothesis API
    api/           # Application-facing HTTP/UI entrypoints
    ingestion/     # File parsing and payload adapters
    llm_core/      # LLM provider, extraction, answer generation
```

## What Is Source Of Truth

- `kg_engine/domain/` defines the canonical business objects: entities, evidence, relations, observations, decision traces, coverage rules, and query result envelopes.
- `kg_engine/repositories/protocols.py` defines the persistence contract used by the service layer.
- `kg_engine/services/materials_kg.py` is the public graph-first ingestion,
  query, and hypothesis-generation API.
- `kg_engine/repositories/neo4j.py` is the primary runtime backend and stores
  graph entities as Neo4j nodes and graph relations as Neo4j relationships.
- `kg_engine/repositories/memory.py` is used only for unit tests.

## Storage Model

The Neo4j repository persists:

- canonical entities and alias resolution
- typed relations between entities
- evidence with source spans and extraction metadata
- observations with measured values and units
- decision traces for explainability and history
- coverage rules for gap analysis
- searchable text units for evidence lookup

## Hypothesis Factory

The `/hypotheses/generate` endpoint accepts a target KPI plus optional material,
mode, and property filters. The service generates interpretable candidates from
graph evidence:

- observed effects become exploitation hypotheses;
- coverage gaps become exploration hypotheses;
- every hypothesis includes rationale, test plan, transparent score components,
  supporting observations/evidence, assumptions, and optional expert notes.

Ranking is deterministic and explainable:

```text
final_score =
  0.35 * value
+ 0.25 * evidence_strength
+ 0.20 * novelty
+ 0.20 * (1 - risk)
```

## Ingestion API

The main service surface is `MaterialsKGService`:

```python
from kg_engine.services.materials_kg import MaterialsKGService
from kg_engine.repositories.factory import create_materials_repository

repository = create_materials_repository(settings, ensure_schema=True)
service = MaterialsKGService(repository)
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

## Neo4j Bootstrap

Start a local Neo4j DBMS in Neo4j Desktop or with Docker:

```bash
docker compose up -d materials-neo4j
```

Set environment variables (see `.env.example`):

```bash
set MATERIALS_NEO4J_URI=bolt://127.0.0.1:7687
set MATERIALS_NEO4J_USER=neo4j
set MATERIALS_NEO4J_PASSWORD=<your-password>
set MATERIALS_NEO4J_DATABASE=neo4j
set MATERIALS_REQUIRE_GRAPH_DB=true
set MATERIALS_API_ENSURE_SCHEMA=true
```

`ensure_schema()` creates Neo4j constraints for entities, relationships,
evidence, observations, decision traces, text units, and coverage rules. If
`MATERIALS_REQUIRE_GRAPH_DB=true` and Neo4j is not configured, startup fails
instead of silently falling back to memory. In-memory storage is intended for
unit tests only.

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

### Destructive API

By default, `DELETE /sources/{name}` and `DELETE /sources` return 403.
To enable, set `MATERIALS_ENABLE_DESTRUCTIVE_API=true` in `.env`.

## Legacy Stack Status

The canonical runtime architecture for the Materials Hypothesis Factory is
Neo4j-first with in-memory storage for unit tests only.

## References

- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) for the layer model, storage layout, and API walkthrough
- [AGENTS.md](./AGENTS.md) for repo conventions and developer workflows
- [`.agents/skills/materials-knowledge-graph/SKILL.md`](./.agents/skills/materials-knowledge-graph/SKILL.md) for domain notes and examples
