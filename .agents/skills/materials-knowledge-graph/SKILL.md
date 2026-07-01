---
name: materials-knowledge-graph
description: Use for materials science knowledge graph tasks — extracting entities, building graph, querying by material/mode/property, finding data gaps, or any task involving the kg_engine/ module. Triggers on materials science queries, alloy/property extraction, graph construction, gap analysis, or hybrid search.
---

# Materials Knowledge Graph Skill

Enables building and querying a knowledge graph for materials science from document corpora.

## Architecture Overview

```
materials-kg/
  kg_engine/
    domain/          # Typed entities, relations, observations, traces, query DTOs
    repositories/    # Persistence protocol + Neo4j runtime, test memory
    services/        # Ingestion/query/hypothesis API
    agents/          # Deep Agents orchestration over read-only graph tools
    api/             # Application-facing HTTP/UI entrypoints
    ingestion/       # File parsing and payload adapters
    llm_core/        # LLM provider, extraction, answer generation
    config/          # Settings, env-driven configuration
    scripts/         # CLI ingestion and API startup scripts
    tests/           # Test suite
```

## Entity Types (8)

| Type | Description | Example |
|------|-------------|---------|
| `MATERIAL` | Metals, alloys, ceramics, polymers, composites | Ti-6Al-4V, CuCrZr, 316L, IN718 |
| `EXPERIMENT` | Test name, experiment description | tensile_test, fatigue_test |
| `PROPERTY` | Mechanical, thermal, electrical, physical | tensile_strength, hardness, conductivity |
| `MODE` | Processing mode, test conditions | annealing, HIP, LPBF, aging |
| `EQUIPMENT` | Devices, machines, instruments | SEM, XRD, tensile_machine |
| `TEAM` | Research groups, labs, universities | MIT_Materials_Lab |
| `DOCUMENT` | Publication, report, document | doi:10.1000/xyz |
| `TAG` | Findings, results, observations | Strength increased by 15% |

## Relation Types (9)

| Type | Description |
|------|-------------|
| `EVALUATES_MATERIAL` | Experiment evaluates a material |
| `USES_MODE` | Material/experiment uses a processing mode |
| `MEASURES_PROPERTY` | Experiment measures a property |
| `USES_EQUIPMENT` | Experiment uses specific equipment |
| `PERFORMED_BY` | Experiment conducted by a team |
| `DOCUMENTED_IN` | Experiment described in a document |
| `TAGGED_WITH` | Entity tagged with a finding/conclusion |
| `REFERENCES` | Entity references another entity |
| `RELATED_TO` | Generic relation between entities |

## Module Responsibilities

| Module | File | Purpose |
|--------|------|---------|
| domain | `models.py` | Pydantic models — entities, evidence, relations, observations, DTOs |
| domain | `resolution.py` | Canonical name resolution via alias normalization |
| repositories | `protocols.py` | Persistence contract used by the service layer |
| repositories | `neo4j.py` | Primary runtime backend, Neo4j nodes and relationships |
| repositories | `memory.py` | In-memory storage for unit tests only |
| repositories | `factory.py` | Environment-driven repository bootstrap |
| services | `materials_kg.py` | Public graph-first ingestion, query, and deterministic hypothesis API |
| services | `hypothesis_adjustments.py` | Expert adjustment schema and score recalculation |
| services | `session.py` | In-memory conversation session store with TTL |
| agents | `hypothesis_factory.py` | Deep Agents orchestration for hypothesis generation |
| agents | `hypothesis_tools.py` | Read-only graph tools exposed to the agent |
| agents | `extraction_agent.py` | Deep Agents orchestration for document entity extraction |
| api | `materials_core.py` | FastAPI app with upload, query, hypothesis, and graph endpoints |
| ingestion | `adapters.py` | Normalize raw source-family payloads into domain inputs |
| llm_core | `provider.py` | OpenAI-compatible LLM provider with streaming and retry |
| llm_core | `extraction.py` | LLM-powered entity extraction and answer generation |
| llm_core | `token_budget.py` | Token budget management for context window fitting |
| llm_core | `fallback.py` | Fallback chain with circuit breaker for LLM providers |
| config | `settings.py` | Pydantic-settings loaded from .env |

## Query Examples

### Ingest reference data
```python
from kg_engine.services.materials_kg import MaterialsKGService
from kg_engine.domain.models import ReferenceDataBatch, CanonicalEntityInput, EntityKind

service = MaterialsKGService(repo)
service.ingest_reference_data(
    ReferenceDataBatch(
        entities=[CanonicalEntityInput(kind=EntityKind.MATERIAL, name="Ti-6Al-4V")]
    )
)
```

### Resolve entity
```python
entity = repo.resolve_entity(EntityKind.MATERIAL, "Ti-6Al-4V")
# Returns: CanonicalEntity with canonical_name, aliases, kind
```

## Command Reference

```bash
# Venv
.venv\Scripts\Activate.ps1                   # Windows PowerShell
source .venv/bin/activate                     # Linux/WSL

# Install
pip install -e ".[dev]"

# Test
python -m pytest kg_engine/tests/ -v

# Lint
ruff check kg_engine/
ruff check --fix --unsafe-fixes kg_engine/

# Ingest data
python kg_engine/scripts/ingest_materials_kg.py --input path/to/data --ensure-schema
```

## Code References

- `kg_engine/domain/models.py` — Entity/relation type definitions
- `kg_engine/repositories/neo4j.py` — Graph storage with Neo4j
- `kg_engine/llm_core/extraction.py` — Entity extraction
- `kg_engine/services/materials_kg.py` — Query and ingestion API
- `kg_engine/agents/hypothesis_tools.py` — LangChain tools

## Agent Files Reference

All agent-facing files in this project must stay consistent:

| File | Purpose |
|------|---------|
| `AGENTS.md` | **Source of truth** — full conventions, dev commands, structure |
| `.agents/skills/materials-knowledge-graph/SKILL.md` (this file) | Domain skill — architecture, entity/relation types, query examples |
| `.cursor/rules/materials-kg-agent.mdc` | Coding rules, domain overview, key patterns |
| `.cursor/rules/terminal.mdc` | Terminal setup, venv, common commands |
| `.cursor/rules/commit.mdc` | Commit message format and guidelines |
