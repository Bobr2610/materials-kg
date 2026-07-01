# Architecture Guide - Materials Knowledge Graph

Neo4j-backed Materials Hypothesis Factory. Domain → Repositories → Services → API.

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

---

## 2. Full File Structure

### Root

| File | Purpose |
|------|---------|
| `README.md` | Project overview: layer model, entity/relation types, Neo4j storage |
| `AGENTS.md` | **Source of truth** for agent rules. Pre-flight gate, git flow, prohibited actions |
| `TEAM_STATUS.md` | Shared task board: ML/NLP, Data Science, System Analyst tracks |
| `pyproject.toml` | Package config: name, deps (fastapi, neo4j, langchain, pydantic), ruff settings |
| `requirements_core.txt` | Minimal deps for graph-first core (fastapi, pydantic, neo4j, pytest) |
| `packages.txt` | System packages: `tesseract-ocr` |
| `lint.py` | Colored ruff check/format wrapper with summary |
| `Dockerfile` | Python 3.11-slim build, exposes 8090 |
| `docker-compose.yml` | Two services: `materials-neo4j` (Neo4j 5) + `materials-api` (FastAPI) |
| `ui-page.html` | Single-page Russian UI "Фабрика гипотез" |
| `.env` | Live env vars (gitignored) |
| `.env.example` | Template: Neo4j, API, LLM provider config (82 lines) |
| `.gitignore` | Ignores .env, .venv, __pycache__, caches |
| `.dockerignore` | Strips .git, .venv, caches, .env, .agents from Docker context |

---

### `kg_engine/` — Core Python Package

#### `kg_engine/__init__.py`
Exports `MaterialsKGService`. Engine with legacy RAG + graph-first core.

#### `kg_engine/requirements.txt`
Full 30-line deps: deepagents, langchain, neo4j, networkx, openai, tiktoken, fastapi.

---

#### `kg_engine/config/` — Application Settings

| File | Purpose |
|------|---------|
| `__init__.py` | Exports `Settings`, `settings` singleton, config types |
| `settings.py` | Pydantic `BaseSettings` from `.env`: Neo4j, API, LLM provider, embedding, hypothesis mode |

---

#### `kg_engine/domain/` — Canonical Business Objects

| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports all public domain types from `models.py` |
| `models.py` | **499 lines.** All typed objects: `EntityKind` (8), `RelationType` (9), Pydantic models for entities, relations, evidence, observations, findings, hypotheses, queries, DTOs |
| `resolution.py` | `normalize_name()` + `ReferenceResolver`: alias index for canonical entity resolution |

---

#### `kg_engine/repositories/` — Persistence Layer

| File | Purpose |
|------|---------|
| `__init__.py` | Exports `create_materials_repository`, `InMemoryMaterialsKGRepository`, `MaterialsKGRepository`, `Neo4jMaterialsKGRepository` |
| `protocols.py` | `MaterialsKGRepository` Protocol: upsert, get, list, search, coverage rules, decision traces |
| `neo4j.py` | **532 lines.** Primary production backend. Neo4j driver, schema creation, fulltext search, alias resolution |
| `memory.py` | **300 lines.** In-memory dict-based repo for unit tests. Keyword scoring search |
| `factory.py` | `create_materials_repository()`: Neo4j if URI configured, else in-memory |

---

#### `kg_engine/services/` — Business Logic

| File | Purpose |
|------|---------|
| `__init__.py` | Exports `MaterialsKGService` and offline metrics APIs |
| `materials_kg.py` | **2331 lines.** Main service. Ingestion, query, gap analysis, hypothesis generation, streaming answers, decision traces, coverage rules |
| `hypothesis_adjustments.py` | Expert override helpers: `apply_expert_adjustments()`, schema for reject/note/score adjustments |
| `metrics.py` | **681 lines.** Offline quality metrics: Entity/Relation F1, context recall, groundedness, novelty, coverage heatmap, full run comparison, expert feedback persistence/calibration/correlation |
| `session.py` | Thread-safe in-memory session store with TTL expiry. `SessionStore` manages `ConversationSession` objects |

---

#### `kg_engine/agents/` — LLM Agent Orchestration

| File | Purpose |
|------|---------|
| `__init__.py` | Exports `extract_and_resolve`, `resolve_relation_type`, `generate_hypotheses_with_deep_agent` |
| `hypothesis_factory.py` | **245 lines.** Deep Agents for hypothesis generation. Read-only graph tools, LangChain model, workflow orchestration |
| `hypothesis_tools.py` | **135 lines.** Read-only tool set for hypothesis workflow: query, search, entity lookup, gap listing. Call counting, step limits |
| `extraction_agent.py` | **95 lines.** Deep Agents for document entity extraction. Calls `extract_entities_from_document()`, resolves to `EntityKind` |

---

#### `kg_engine/api/` — HTTP Entrypoints

| File | Purpose |
|------|---------|
| `__init__.py` | Docstring: "API entry points for the materials core API" |
| `materials_core.py` | **834 lines.** FastAPI app factory `create_materials_app()`. Endpoints: health, ingest (reference/experiments/documents/canonical), query (material-mode-property/search), entities, hypotheses (deterministic+agent), metrics, expert feedback, adjustments, decision traces, coverage rules, destructive wipe, UI |

---

#### `kg_engine/ingestion/` — Source Data Adapters

| File | Purpose |
|------|---------|
| `__init__.py` | Exports 5 adapters: `DocumentCorpusAdapter`, `ExperimentCatalogAdapter`, `ReferenceDataAdapter`, `StaffDirectoryAdapter`, `TagCatalogAdapter` |
| `adapters.py` | **478 lines.** Normalizes raw JSON/CSV payloads → domain DTOs. Each adapter handles one source type |

---

#### `kg_engine/llm_core/` — LLM Integration

| File | Purpose |
|------|---------|
| `__init__.py` | Docstring: "LLM integration layer for materials KG" |
| `provider.py` | **532 lines.** `LLMProvider` + factory. OpenAI-compatible: openrouter, polza, vllm, openai, groq, mistral. Async streaming, retry, LangChain model creation |
| `extraction.py` | **550 lines.** Entity/relationship extraction from documents. `extract_entities_from_document()`, `generate_streaming_answer()`. Limits: 50 entities, 20 experiments, 30 relations |
| `token_budget.py` | **150 lines.** Token counting (tiktoken cl100k_base), context truncation, budget fitting |
| `fallback.py` | **178 lines.** `CircuitBreaker` + `FallbackChain` for multi-provider failover |

---

#### `kg_engine/scripts/` — CLI Tools

| File | Purpose |
|------|---------|
| `ingest_materials_kg.py` | **426 lines.** CLI ingestion: JSON/CSV/JSONL from reference/experiment/document dirs |
| `run_materials_api.py` | **28 lines.** Standalone launcher: load `.env`, create app, run uvicorn |

---

#### `kg_engine/tests/` — Test Suite

| File | Purpose |
|------|---------|
| `conftest.py` | Adds project root to `sys.path` |
| `test_materials_kg_core.py` | **903 lines.** Comprehensive service tests: ingestion, queries, gaps, hypotheses, streaming |
| `test_materials_graph_database_behavior.py` | **255 lines.** Behavioral tests: adapter → service → repository path |
| `test_materials_api_smoke.py` | **626 lines.** FastAPI TestClient smoke tests for every endpoint, including offline metrics endpoints |
| `test_deepagents_hypothesis_factory.py` | **430 lines.** Deep Agents hypothesis workflow tests |
| `test_neo4j_repository.py` | **90 lines.** Neo4j repo with `FakeSession` mock |
| `test_repository_factory.py` | **79 lines.** Factory: memory vs Neo4j selection |
| `test_ingestion_adapters.py` | **141 lines.** Unit tests for each adapter |
| `test_ingest_materials_cli_loading.py` | **113 lines.** CLI `_load_bundle()` and `_load_payload()` tests |
| `test_llm_provider_selection.py` | **179 lines.** LLM provider detection and creation |
| `test_metrics_evaluation.py` | **485 lines.** Offline metrics tests: extraction F1, context recall, repository coverage heatmap, full run comparison, calibrated reranking, expert feedback calibration, edge cases |
| `test_no_donor_brand_in_core.py` | **133 lines.** Isolation guard: scans for forbidden legacy brand references |

---

### `data/` — Seed Data (used by `/demo/load-sample`)

| File | Purpose |
|------|---------|
| `reference.json` | 3 materials (Ti-6Al-4V, IN718, Al6061), 5 properties, equipment, modes, teams, coverage rules |
| `experiments.json` | 4 experiments: SLM Ti-6Al-4V, annealing, IN718. Observations with measured values |
| `documents.json` | 2 scientific reviews: AM titanium, IN718. Linked to experiments, findings, text units |

---

### `sample_sources/` — Example Input Files

| File | Purpose |
|------|---------|
| `reference_pack.json` | Sample reference batch: 2 materials (CuCrZr, 316L), properties, equipment |
| `experiment_rows.csv` | 4 CSV experiment rows: CuCrZr conductivity, 316L density |
| `process_notes.md` | Free-text meeting notes from Thermal Processing Group |

---

### `docs/` — Documentation

| File | Purpose |
|------|---------|
| `ARCHITECTURE.md` | **This file.** Full architecture, file structure, deployment, development |
| `mimo-runs/` | MiMo delegation reports and prompts. Runs are stored by date/task and may include failure summaries when MiMo cannot start |

---

### `.agents/skills/` — Agent Skill Definitions

| Skill | Purpose |
|-------|---------|
| `materials-knowledge-graph/SKILL.md` | Domain skill: architecture, entities, relations, ingestion, query, hypotheses |
| `mimo-subagent/SKILL.md` | MiMo CLI delegation: availability check, work trees, prompt guide, built-in commands |
| `mimo-subagent/scripts/run_mimo.ps1` | PowerShell wrapper for `mimo run` with validation and output capture |
| `mimo-subagent/references/models.md` | MiMo model selection notes |
| `team-coordination/SKILL.md` | Team workflow: TEAM_STATUS.md, roles, task overlap check |
| `docker-workflow/SKILL.md` | Docker commands: compose, health, rebuild, test in containers |
| `critical-thinking/SKILL.md` | Anti-yes-man: say when unsure, correct wrong human, verify before writing |
| `code-style/SKILL.md` | Python conventions: Ruff 88 chars, PascalCase/snake_case, type hints |

---

### `.claude/` — Claude Code Configuration

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Session instructions: rules display, MiMo check, pre-flight gate, prohibited actions |

---

### `.codex/` — OpenAI Codex Configuration

| File | Purpose |
|------|---------|
| `instructions.md` | Session instructions: rules display, MiMo check, pre-flight gate, prohibited actions |

---

### `.cursor/` — Cursor IDE Rules

| File | Purpose |
|------|---------|
| `rules/terminal.mdc` | Terminal execution: venv activation, dev commands |
| `rules/materials-kg-agent.mdc` | Agent behavior: research-before-code, code style, entity reference |
| `rules/commit.mdc` | Commit message format: concise, structured |

---

### `.opencode/` — Plans and Chat History

| Path | Purpose |
|------|---------|
| `plans/README.md` | Plan format: `YYYYMMDD-<topic>/plan.md` with goal, steps, TDD |
| `plans/*.md` | 19+ implementation plans (setup, MarkItDown, Gradio, CMW, etc.) |
| `chats/README.md` | Chat export format |
| `chats/*.md` | 2 saved session transcripts |

---

## 3. Entity Types (8)

`MATERIAL`, `EXPERIMENT`, `PROPERTY`, `MODE`, `EQUIPMENT`, `TEAM`, `DOCUMENT`, `TAG`

## 4. Relation Types (9)

`EVALUATES_MATERIAL`, `USES_MODE`, `MEASURES_PROPERTY`, `USES_EQUIPMENT`, `PERFORMED_BY`, `DOCUMENTED_IN`, `TAGGED_WITH`, `REFERENCES`, `RELATED_TO`

---

## 5. Persistence: Neo4j

Schema constraints: `Entity {id}`, `Evidence {id}`, `Observation {id}`, `DecisionTrace {id}`, `CoverageRule {rule_id}`, `TextUnit {id}`, `()-[:KG_RELATION {id}]->()`

---

## 6. Ingestion Pipeline

```
JSON/CSV/JSONL → Adapters → Service → Repository → Neo4j
```

Three flows:
1. **Reference** → canonical entities, aliases, coverage rules
2. **Experiments** → entities, observations, findings, text units
3. **Documents** → entities, links, text units, findings

---

## 7. Query API

- `query_material_mode_property` — gap-aware material/mode/property query
- `search_graph_text` — full-text graph search
- `get_entity_detail` — entity with graph neighborhood
- `get_entity_graph` — graph visualization data
- `query_data_gaps` — rule-driven gap detection

---

## 8. Deployment

```bash
docker compose up -d --build    # Start Neo4j + API
docker compose ps               # Status
docker compose logs -f          # Logs
```

API on port 8090. Neo4j on port 7687 (bolt).

---

## 9. Development

```bash
# Install
pip install -e ".[dev]"

# Lint
ruff check kg_engine/
ruff format kg_engine/

# Test
python -m pytest kg_engine/tests/ -v

# Ingest CLI
python -m kg_engine.scripts.ingest_materials_kg --reference-dir data/ --experiment-dir data/ --document-dir data/
```

---

**Related:** [README.md](../README.md), [AGENTS.md](../AGENTS.md), [`.agents/skills/materials-knowledge-graph/SKILL.md`](../.agents/skills/materials-knowledge-graph/SKILL.md)
