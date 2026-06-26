---
name: materials-knowledge-graph
description: Use for materials science knowledge graph tasks — extracting entities, building graph, querying by material/mode/property, finding data gaps, or any task involving the kg_engine/graph/ module. Triggers on materials science queries, alloy/property extraction, graph construction, gap analysis, or hybrid search.
---

# Materials Knowledge Graph Skill

Enables building and querying a knowledge graph for materials science from document corpora.

## Architecture Overview

```
materials-kg/
  kg_engine/
    graph/          # Knowledge graph module
      __init__.py   # Public exports
      schemas.py    # EntityType (8), RelationType (12), GraphEntity, GraphRelation
      store.py      # Thread-safe NetworkX MultiDiGraph + JSON save/load
      extractor.py  # Regex + LLM entity/relation extraction
      builder.py    # Document → graph construction
      query.py      # Query engine (by material+mode, by property, related entities, gaps)
      search.py     # Hybrid vector + graph search
      pipeline.py   # End-to-end pipeline: index → ask → find_gaps → save/load
      tools.py      # 5 LangChain tools for agent integration
    retrieval/      # Vector search (ChromaDB, reranking, embeddings)
    llm/            # LLM manager, agent factory, fallback
    agent/          # LangChain agent, streaming, session
    api/            # Gradio UI + REST API
    core/           # Document processing, chunking, indexing
    storage/        # Vector store adapters
    tools/          # LangChain tools for RAG
    config/         # Settings, model registry
    utils/          # Shared utilities
    scripts/        # Build scripts for knowledge graph
    tests/          # Test suite
```

## Entity Types

| Type | Description | Example |
|------|-------------|---------|
| `material` | Metals, alloys, ceramics, polymers, composites | Ti6Al4V, Al6061, Al2O3 |
| `property` | Mechanical, thermal, electrical, physical | tensile_strength, hardness |
| `experiment` | Test name, experiment description | tensile_test, fatigue_test |
| `mode` | Processing mode, test conditions | annealing, heat_treatment |
| `equipment` | Devices, machines, instruments | SEM, XRD, tensile_machine |
| `team` | Research groups, labs, universities | MIT_Materials_Lab |
| `article` | Publication, report, document | doi:10.1000/xyz |
| `conclusion` | Findings, results, observations | Strength increased by 15% |

## Relationship Types

| Type | Direction | Description |
|------|-----------|-------------|
| `has_property` | material → property | Material possesses a property (with value/unit) |
| `used_in` | material → experiment | Material was used in an experiment |
| `measures` | experiment → property | Experiment measures a property |
| `uses_equipment` | experiment → equipment | Experiment uses specific equipment |
| `has_mode` | material/experiment → mode | Material processed under a mode |
| `conducted_by` | experiment → team | Experiment conducted by a team |
| `described_in` | experiment → article | Experiment described in a document |
| `has_conclusion` | experiment → conclusion | Experiment produced a conclusion |
| `depends_on` | general dependency | Generic dependency between entities |
| `composed_of` | material → material | Composite/alloy composition |
| `compared_to` | entity → entity | Comparison between entities |
| `optimized_for` | material/experiment → property | Optimized for a specific property |

## Query Examples

### By material and mode
```python
pipeline = GraphPipeline()
result = pipeline.ask(query="Ti6Al4V", mode="annealing")
# Returns: properties, experiments, modes, conclusions
```

### By property with value filter
```python
from kg_engine.graph.query import KnowledgeGraphQuery
query = KnowledgeGraphQuery(store)
results = query.query_by_property("tensile_strength", min_value=800)
```

### Data gaps
```python
gaps = pipeline.find_gaps()
# Returns missing material-mode and material-property combinations
```

## Command Reference

```bash
# Venv
.venv\Scripts\Activate.ps1                   # Windows PowerShell
source .venv/bin/activate                     # Linux/WSL

# Install
pip install -r kg_engine/requirements.txt

# Build knowledge graph from document chunks
python kg_engine/scripts/build_knowledge_graph.py --source chunks.json --output graph.json

# Build with LLM extraction
python kg_engine/scripts/build_knowledge_graph.py --source chunks.json --output graph.json --use-llm

# Test
python -m pytest kg_engine/tests/test_graph.py -v

# Lint
ruff check kg_engine/graph/
ruff check --fix --unsafe-fixes kg_engine/graph/
```

## Code References

- `kg_engine/graph/schemas.py` — Entity/relation type definitions
- `kg_engine/graph/store.py` — Graph storage with NetworkX
- `kg_engine/graph/extractor.py` — Regex + LLM extraction
- `kg_engine/graph/query.py` — Query engine
- `kg_engine/graph/tools.py` — LangChain tools

## Agent Files Reference

All 5 agent-facing files in this project must stay consistent. If one is overwritten, check the others:

| File | Purpose |
|------|---------|
| [`AGENTS.md`](../../AGENTS.md) | **Source of truth** — full conventions, dev commands, structure |
| `.agents/skills/materials-knowledge-graph/SKILL.md` (this file) | Domain skill — architecture, entity/relation types, query examples |
| [`.cursor/rules/materials-kg-agent.mdc`](../../.cursor/rules/materials-kg-agent.mdc) | Coding rules, domain overview, key patterns |
| [`.cursor/rules/terminal.mdc`](../../.cursor/rules/terminal.mdc) | Terminal setup, venv, common commands |
| [`.cursor/rules/commit.mdc`](../../.cursor/rules/commit.mdc) | Commit message format and guidelines |
