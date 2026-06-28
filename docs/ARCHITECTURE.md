# Architecture Guide - Materials Knowledge Graph

This repository now has a graph-first core built around domain models, repository interfaces, and a small service layer. The older `kg_engine/graph/` and `kg_engine/agent/` stack remains as a prototype/donor implementation, but the canonical path for new work is the `domain -> repositories -> services -> api` flow.

---

## 1. Layer Model

```text
Clients / API / UI
        |
        v
kg_engine/api
        |
        v
kg_engine/services/materials_kg.py
        |
        v
kg_engine/repositories/protocols.py
        |
        +--> kg_engine/repositories/postgres.py
        |
        +--> kg_engine/repositories/memory.py
        |
        v
kg_engine/domain/models.py
```

### Domain

`kg_engine/domain/models.py` defines the typed graph vocabulary:

- entities: `MATERIAL`, `EXPERIMENT`, `PROPERTY`, `MODE`, `EQUIPMENT`, `TEAM`, `DOCUMENT`, `TAG`
- relations: typed edges such as `EVALUATES_MATERIAL`, `USES_MODE`, `MEASURES_PROPERTY`, `DOCUMENTED_IN`
- evidence and source spans for provenance
- observations for measured values
- decision traces for explainability and historical reasoning
- coverage rules and gap outputs
- typed query result envelopes

This layer is the source of truth for business semantics. It is intentionally independent from a concrete storage engine.

### Repositories

`kg_engine/repositories/protocols.py` defines the persistence contract used by the service layer:

- entity upsert and resolution
- evidence and relation persistence
- observation and decision-trace storage
- coverage-rule storage
- text-unit persistence and search

Current implementations:

- `InMemoryMaterialsKGRepository` for tests and local validation
- `PostgresMaterialsKGRepository` for durable storage in Postgres with `pgvector`

### Services

`kg_engine/services/materials_kg.py` contains the public graph-first application logic:

- ingestion orchestration
- canonical entity resolution
- relation construction
- provenance creation
- typed query assembly
- coverage-rule-based gap detection

The service layer is the preferred integration point for API handlers, scripts, and future orchestration code.

### API and Adapters

`kg_engine/api/` remains the application-facing surface. It should depend on service methods and typed DTOs instead of reaching directly into legacy graph internals.

---

## 2. Persistence: Postgres + pgvector

`kg_engine/repositories/postgres.py` is the primary durable backend for the new core.

### Schema Responsibilities

The repository bootstraps:

- `kg_entities`
- `kg_entity_aliases`
- `kg_evidence`
- `kg_relations`
- `kg_observations`
- `kg_decision_traces`
- `kg_coverage_rules`
- `kg_text_units`

It also enables:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Why Postgres

- structured persistence for canonical graph objects
- transactional upserts for incremental ingestion
- flexible `JSONB` payloads for metadata and evolving annotations
- straightforward alias resolution and provenance storage
- good fit for service-oriented APIs

### Why pgvector

`kg_text_units.embedding VECTOR(1536)` stores optional embeddings for searchable evidence fragments and document chunks. The current repository already persists vector-capable text units, which makes it the natural place to grow hybrid retrieval beyond basic text matching.

---

## 3. Ingestion API

The main write path is `MaterialsKGService`.

### 3.1 Reference Data

```python
service.ingest_reference_data(batch)
```

Use this to seed:

- canonical dictionaries
- aliases for noisy material or mode names
- coverage rules used by gap analysis

### 3.2 Experiments

```python
service.ingest_experiments(batch)
```

This flow:

1. resolves or creates canonical entities
2. links experiments to materials, modes, teams, equipment, and documents
3. creates observations with units, values, comparators, and provenance
4. stores findings as decision traces
5. stores experiment text units for search

### 3.3 Documents

```python
service.ingest_documents(batch)
```

This flow:

1. creates or updates document entities
2. links documents to referenced materials, properties, modes, equipment, teams, experiments, and tags
3. stores full-document and chunk-level text units
4. records extracted findings as decision traces

---

## 4. Query API

The read side also hangs off `MaterialsKGService`.

### Material and mode context

```python
result = service.query_material_mode("Material-A", "Mode-A", "Hardness")
```

Returns:

- canonical material and mode entities
- matching experiments
- matching observations
- decision traces
- evidence records
- search hits from indexed text units

### Property lookup

```python
result = service.query_property("Yield strength", filters=...)
```

Supports material, mode, and numeric range filtering through `PropertyFilters`.

### Related-entity traversal

```python
result = service.query_related("Material-B", depth=2)
```

Returns:

- related entities
- traversed relations
- explainable evidence paths
- collected evidence

### Decision history

```python
result = service.query_decision_history("exp-mm")
```

Returns a typed history of decision traces and linked evidence for an entity or experiment.

### Data-gap analysis

```python
gaps = service.query_data_gaps(filters=...)
```

Gap detection is rule-driven. It compares observed material/mode/property combinations against explicit coverage rules instead of exploring an uncontrolled cartesian space.

---

## 5. Example Wiring

```python
from kg_engine.repositories.postgres import PostgresMaterialsKGRepository
from kg_engine.services.materials_kg import MaterialsKGService

repository = PostgresMaterialsKGRepository(connection)
repository.ensure_schema()

service = MaterialsKGService(repository)

service.ingest_reference_data(reference_batch)
service.ingest_experiments(experiment_batch)
service.ingest_documents(document_batch)

answer = service.query_material_mode("Material-A", "Mode-A")
```

For tests and local checks, the same service can be wired to `InMemoryMaterialsKGRepository`.

---

## 6. Legacy Prototype / Donor Stack

The repository still contains earlier graph and agent-oriented modules:

- `kg_engine/graph/`
- `kg_engine/agent/`

Treat them as:

- prototype code that helped validate the problem space
- donor code for extraction ideas, tool ergonomics, and migration references
- non-canonical surfaces relative to the new service-backed core

They should not be documented as the primary architecture anymore. New documentation, examples, and integration work should point first to `domain`, `repositories`, `services`, and the Postgres-backed path.

---

## 7. Current Module Map

```text
kg_engine/
├── domain/
│   ├── models.py          Typed graph/domain models and query DTOs
│   └── resolution.py      Name normalization and canonical resolution helpers
├── repositories/
│   ├── protocols.py       Persistence interface for the service layer
│   ├── postgres.py        Postgres + pgvector implementation
│   └── memory.py          In-memory implementation for tests
├── services/
│   └── materials_kg.py    Ingestion and query orchestration
├── api/                   App-facing entrypoints and adapters
├── core/                  Chunking, indexing, and document-processing helpers
├── retrieval/             Embeddings, reranking, and search helpers
├── graph/                 Legacy prototype graph pipeline
└── agent/                 Legacy prototype agent stack
```

---

## 8. Positioning Summary

- The new core is graph-first, but service-backed rather than graph-module-centric.
- Domain models define the contract.
- Repositories isolate persistence and make Postgres the main backend.
- `pgvector` is part of the storage story for searchable text units and hybrid retrieval growth.
- Ingestion and query flows should go through `MaterialsKGService`.
- The old graph/agent stack is retained as prototype/donor material, not as the primary architecture.

**Related files:** [README.md](../README.md), [AGENTS.md](../AGENTS.md), [`.agents/skills/materials-knowledge-graph/SKILL.md`](../.agents/skills/materials-knowledge-graph/SKILL.md)
