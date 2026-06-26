# AGENTS.md - Materials Knowledge Graph

Repo-specific guidance for this Python 3.11+ project.

**Implementations follow:** TDD, SDD, @AGENTS.md, lean, dry, modular, pythonic, non-breaking.

## Research & Planning

Before any coding or changes:
- Deep codebase research
- Deep web research for reference documentation on frameworks, libraries, best practices
- Gather all information before planning course of action
- Write a concise plan file: actionable, detailed, TDD, step-by-step tasks, checkpoints, expected verification commands

## Common Engineering Baseline

- **SDD:** Scope/contract clarity before coding
- **TDD:** Tests first, define behavior contracts
- **Non-breaking:** Never break existing functionality
- **Lean:** Minimal code, no overengineering
- **Pythonic:** Type hints, explicit data contracts, clear idioms
- **Modular:** Single responsibility per module/class
- **DRY:** 2+ uses → extract helper
- Validate external data; no silent exception handling (`except: pass` forbidden)
- Always lint + test before completion
- Never hardcode secrets; use `.env` + `.env.example`

## Dev Commands

```bash
# Venv
.venv\Scripts\Activate.ps1              # Windows PowerShell
source .venv/bin/activate                # Linux/WSL

# Install
pip install -r kg_engine/requirements.txt

# Test
python -m pytest kg_engine/tests/ -v
python -m pytest kg_engine/tests/test_graph.py -v

# Lint
ruff check kg_engine/
ruff check --fix --unsafe-fixes kg_engine/
ruff check kg_engine/graph/          # specific module

# Build knowledge graph
python kg_engine/scripts/build_knowledge_graph.py --source chunks.json --output graph.json
python kg_engine/scripts/build_knowledge_graph.py --source chunks.json --output graph.json --use-llm
```

## Project Structure

```
kg_engine/
  graph/          # Knowledge graph: entities, extraction, store, query, search, tools
  retrieval/      # Vector search (ChromaDB, embeddings, reranker)
  llm/            # LLM manager, agent factory, fallback
  agent/          # LangChain agent, streaming, session management
  api/            # Gradio UI + REST API
  core/           # Document processing, chunking, indexing
  storage/        # Vector store adapters
  tools/          # LangChain tools for RAG
  config/         # Settings, model registry
  utils/          # Shared utilities (context tracker, thread pool, path utils)
  scripts/        # Build/build_index/knowledge_graph scripts
  tests/          # Test suite
```

## Code Style & Conventions

- **Ruff (pyproject.toml):** Line length 88, Python 3.11+, double quotes
- **Imports:** standard → third-party → local (no try/except fallback within project)
- **Naming:** `PascalCase` classes, `snake_case` functions/vars, `UPPER_SNAKE` constants, `_prefixed` private
- **Docstrings:** Module docstrings describing purpose, Google-style for functions (Args, Returns, Raises)
- **Module pattern:**
  - `from __future__ import annotations`
  - `import logging` + `logger = logging.getLogger(__name__)`
  - Pydantic `BaseModel`/`Field` for data schemas
  - Classes with clear constructor and docstrings

## Knowledge Graph Conventions

### Entity types (8)
`MATERIAL`, `PROPERTY`, `EXPERIMENT`, `MODE`, `EQUIPMENT`, `TEAM`, `ARTICLE`, `CONCLUSION`

### Relation types (12)
`HAS_PROPERTY`, `USED_IN`, `MEASURES`, `USES_EQUIPMENT`, `HAS_MODE`, `CONDUCTED_BY`, `DESCRIBED_IN`, `HAS_CONCLUSION`, `DEPENDS_ON`, `COMPOSED_OF`, `COMPARED_TO`, `OPTIMIZED_FOR`

### Module responsibilities
- **schemas.py:** Pydantic models only — `GraphEntity`, `GraphRelation`, enums
- **store.py:** NetworkX-backed thread-safe storage, JSON serialization
- **extractor.py:** Regex + LLM extraction — separate regex from LLM path
- **query.py:** Read-only query interface over store (no mutation)
- **search.py:** Hybrid search combining vector + graph results
- **builder.py:** Document → graph transformation
- **pipeline.py:** Orchestration — index → ask → find_gaps → save/load
- **tools.py:** LangChain `@tool` decorated functions with Pydantic `args_schema`

## Error Handling

- No silent exceptions: always log, never `except: pass`
- Avoid unnecessary try-catches; use robust explicit logic
- No hardcoded fallbacks
- Validate external data: check structure, handle missing fields
- Safe defaults: `None`, `[]`, `{}` where appropriate

## Testing Guidelines

- Test **behavior**, not implementation details
- Use classes to organize by module (`TestGraphStore`, `TestEntityExtractor`, etc.)
- Focus on error handling, data integrity, edge cases
- Location: `kg_engine/tests/`
- Parametrize for cross-config/model testing
- Prefer integration tests for endpoint-level behavior
- References: https://google.github.io/googletest/primer.html

### Example Pattern
```python
class TestGraphStore:
    def test_add_and_get_entity(self) -> None:
        store = GraphStore()
        entity = GraphEntity(id="mat_1", type=EntityType.MATERIAL, name="Ti6Al4V")
        store.add_entity(entity)
        retrieved = store.get_entity("mat_1")
        assert retrieved is not None
        assert retrieved.name == "Ti6Al4V"
```

## Documentation Guidelines

- Clear heading hierarchy (single H1 per file)
- Front-load conclusions and recommendations
- Actionable, chunked sections
- Documentation → `docs/`
- Progress reports → `docs/progress_reports/` with `YYYYMMDD_` prefix

## Security & Secrets

- `.env` for local config, never commit
- `.env.example` with placeholders only
- Never hardcode keys, passwords, or personal data
- Load secrets via dotenv in tests and code

## Commit Guidelines

- Only create commits when explicitly asked
- Concise message, strictly relevant to changes
- No blabber — keep to necessary minimum

## Verification Checklist

1. `ruff check` on modified files
2. Tests pass: `python -m pytest kg_engine/tests/ -v`
3. No regressions (non-breaking behavior)
4. Shared logic is DRY (extract helpers for 2+ uses)
5. README/docs updated if behavior changed

## Related Instruction Files

- `.agents/skills/materials-knowledge-graph/SKILL.md` — Main skill with architecture, entity types, examples
- `.cursor/rules/materials-kg-agent.mdc` — Agent coding rules
- `.cursor/rules/terminal.mdc` — Terminal command rules
- `.cursor/rules/commit.mdc` — Commit message rules

---

**Remember:** DRY, lean, modular, pythonic. Research first, plan, produce flawless code.
