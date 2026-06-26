# Materials Knowledge Graph

Knowledge graph + search-analytics system for materials science. Links articles, experiments, materials, properties, modes, equipment, research teams, and conclusions into a queryable graph with LLM-powered entity extraction.

### Architecture

```
materials-kg/
  kg_engine/
    graph/          # Knowledge graph: entities, relations, extraction, query, tools
    retrieval/      # Vector search (ChromaDB, reranking, embeddings)
    llm/            # LLM manager, agent factory, fallback
    agent/          # LangChain agent, streaming, session management
    api/            # Gradio UI + REST API
    core/           # Document processing, chunking, indexing
    storage/        # Vector store adapters
    tools/          # LangChain tools for RAG
    config/         # Settings, model registry
    utils/          # Shared utilities
    scripts/        # Build/build_index/knowledge_graph scripts
    tests/          # Test suite
```

### Key Capabilities

- **Entity extraction**: Regex + LLM extraction of materials, properties, experiments, modes, equipment, teams, articles, conclusions
- **Graph query**: `query_by_material_and_mode("Ti6Al4V", "annealing")` → properties, experiments, conclusions
- **Hybrid search**: Combine vector similarity with graph traversal for enriched results
- **Data gap analysis**: Identify materials without measured properties or missing mode combinations
- **5 LangChain tools**: `query_material`, `query_property`, `query_related`, `graph_data_gaps`, `graph_stats`
- **RAG pipeline**: Full retrieval-augmented generation over materials documents

### Quick Start

```bash
# Install
pip install -r kg_engine/requirements.txt

# Build knowledge graph from document chunks
python kg_engine/scripts/build_knowledge_graph.py --source chunks.json --output graph.json

# Run tests
python -m pytest kg_engine/tests/test_graph.py -v
```

### Questions it answers

- *What has been done on alloy X under processing mode Y and what was the effect on property Z?*
- *Which materials have been tested for property P with value > V?*
- *What related entities exist for material M?*
- *Where are the data gaps — which material-mode combinations are unexplored?*

### References

See [AGENTS.md](./AGENTS.md) for full conventions, entity/relation types, dev commands, and [`.agents/skills/materials-knowledge-graph/SKILL.md`](./.agents/skills/materials-knowledge-graph/SKILL.md) for architecture details.
