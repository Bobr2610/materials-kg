# Architecture Guide - Materials Knowledge Graph

This repository now targets a Neo4j-backed Materials Hypothesis Factory built
around domain models, repository interfaces, and a small service layer. The
canonical runtime path is `domain -> repositories -> services -> api` with
Neo4j as the graph engine. Legacy prototype code has been moved to `legacy/`.

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
        +--> kg_engine/repositories/neo4j.py
        |
        +--> kg_engine/repositories/memory.py (tests only)
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
- KPI-driven hypothesis DTOs with transparent ranking fields
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

- `Neo4jMaterialsKGRepository` for runtime graph persistence
- `InMemoryMaterialsKGRepository` for tests only

### Services

`kg_engine/services/materials_kg.py` contains the public graph-first application logic:

- ingestion orchestration
- canonical entity resolution
- relation construction
- provenance creation
- typed query assembly
- coverage-rule-based gap detection
- KPI-driven hypothesis generation and deterministic ranking

The service layer is the preferred integration point for API handlers, scripts, and future orchestration code.

### API and Adapters

`kg_engine/api/` remains the application-facing surface. It should depend on service methods and typed DTOs instead of reaching directly into legacy graph internals.

---

## 2. Persistence: Neo4j

`kg_engine/repositories/neo4j.py` is the primary durable backend for the
Materials Hypothesis Factory runtime.

### Schema Responsibilities

The repository bootstraps constraints for:

- `(:Entity {id})`
- `(:Evidence {id})`
- `(:Observation {id})`
- `(:DecisionTrace {id})`
- `(:CoverageRule {rule_id})`
- `(:TextUnit {id})`
- `()-[:KG_RELATION {id}]->()`

### Why Neo4j

- native graph nodes and relationships;
- readable Cypher query paths for explanations;
- direct fit for evidence paths such as material -> experiment -> mode/property;
- better product story than a custom in-memory graph engine;
- easier UI graph visualization and debugging.

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
from kg_engine.repositories.factory import create_materials_repository
from kg_engine.services.materials_kg import MaterialsKGService

repository = create_materials_repository(settings, ensure_schema=True)

service = MaterialsKGService(repository)

service.ingest_reference_data(reference_batch)
service.ingest_experiments(experiment_batch)
service.ingest_documents(document_batch)

answer = service.query_material_mode("Material-A", "Mode-A")
```

For tests and local checks, the same service can be wired to `InMemoryMaterialsKGRepository`.

---

## 6. Legacy Status

The canonical runtime architecture is Neo4j-first with in-memory storage for
unit tests only. New documentation, examples, and integration work should
point to `domain`, `repositories`, `services`, and the Neo4j-backed path.

---

## 7. Current Module Map

```text
kg_engine/
├── domain/
│   ├── models.py          Typed graph/domain models and query DTOs
│   └── resolution.py      Name normalization and canonical resolution helpers
├── repositories/
│   ├── protocols.py       Persistence interface for the service layer
│   ├── neo4j.py           Neo4j runtime backend
│   ├── memory.py          In-memory implementation for tests
│   └── factory.py         Repository bootstrap from settings
├── services/
│   └── materials_kg.py    Ingestion and query orchestration
├── ingestion/             File parsing and payload adapters
├── llm_core/              LLM provider, extraction, answer generation
├── api/                   App-facing entrypoints and adapters
├── core/                  Chunking, indexing, and document-processing helpers
├── retrieval/             Embeddings, reranking, and search helpers
└── scripts/               CLI entrypoints for ingestion and API launch
```

---

## 8. Positioning Summary

- The core is graph-first, service-backed, and Neo4j-first.
- Domain models define the contract.
- Repositories isolate persistence with Neo4j as the production backend.
- In-memory repository is for unit tests only.
- Ingestion and query flows go through `MaterialsKGService`.
- Legacy prototype code is in `legacy/`, not the primary architecture.

**Related files:** [README.md](../README.md), [AGENTS.md](../AGENTS.md), [`.agents/skills/materials-knowledge-graph/SKILL.md`](../.agents/skills/materials-knowledge-graph/SKILL.md)
