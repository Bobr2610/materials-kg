# AGENTS.md - Materials Knowledge Graph

Repo-specific guidance for this Python 3.11+ project.

**Implementations follow:** TDD, SDD, @AGENTS.md, lean, dry, modular, pythonic, non-breaking.

## AUTOMATIC: Rules Display at Conversation Start

**At the START of EVERY conversation, the agent MUST automatically display the following block BEFORE any other output:**

```
=== ПРАВИЛА РАБОТЫ С РЕПОЗИТОРИЕМ ===

1. Никогда не работай на main/master — создавай feature-ветку
2. Ветки: feat/<модуль>-<описание>, fix/<модуль>-<описание>, refactor/<модуль>-<описание>
3. Модули: domain, repositories, services, agents, api, ingestion, llm_core, config
4. Мерж: feature → staging → main (только с согласия человека)
5. Прочитай TEAM_STATUS.md — проверь задачи других участников
6. Обновляй TEAM_STATUS.md при начале и завершении работы
7. Никогда не коммить/пушь без явного запроса человека
8. Никогда не дублируй задачи других участников команды

=== КОНЕЦ ПРАВИЛ ===
```

**This output is MANDATORY. Do NOT skip it. Do NOT delay it. It is the FIRST thing the agent outputs.**

## CRITICAL: Branch Protection (MANDATORY)

### Rule 1: NEVER work on `main` or `master` directly

Before ANY code changes:

```bash
# 1. Check current branch
git branch --show-current

# 2. If on main/master → STOP. Create a branch:
git checkout -b feat/short-description

# Branch naming: feat/, fix/, refactor/, docs/, test/
```

### Rule 2: Merge workflow — `staging` is the gateway to `main`

```
feature branch  →  staging  →  main
```

**Step-by-step:**

1. **Work on your feature branch** (`feat/...`, `fix/...`, etc.)
2. **When work is done**, merge into `staging`:
   ```bash
   git checkout staging
   git merge feat/your-branch
   ```
3. **Run ALL checks on staging:**
   ```bash
   ruff check kg_engine/
   python -m pytest kg_engine/tests/ -v
   ```
4. **If checks pass** → ask a human for approval to merge into `main`
5. **Only with explicit human approval** → merge into `main`:
   ```bash
   git checkout main
   git merge staging
   ```

**NEVER merge into `main` without:**
- [ ] All checks passed on `staging`
- [ ] Explicit human approval (verbal, PR approval, or written)
- [ ] Review of `git diff staging...main` before merge

### Rule 3: Branch naming (STRICT)

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feat/<module>-<short-desc>` | `feat/domain-add-crystal-structure` |
| Fix | `fix/<module>-<short-desc>` | `fix/services-null-check-hypothesis` |
| Refactor | `refactor/<module>-<short-desc>` | `refactor/repositories-neo4j-to-async` |
| Docs | `docs/<short-desc>` | `docs/update-api-examples` |
| Test | `test/<module>-<short-desc>` | `test/services-add-ingestion-coverage` |
| Hotfix | `hotfix/<short-desc>` | `hotfix/fix-neo4j-connection-crash` |

**Rules:**
- Module name = `domain`, `repositories`, `services`, `agents`, `api`, `ingestion`, `llm_core`, `config`
- Use kebab-case: `add-neo4j-connection` NOT `addNeo4jConnection`
- Max 3 words after module prefix
- NEVER use random hash suffixes like `feat/xyz-abc-123`

### Rule 4: Prohibited actions

- `git push --force` — PROHIBITED
- `git reset --hard` — PROHIBITED
- Merging into `main` without human approval — PROHIBITED
- Auto-committing without user request — PROHIBITED
- Direct commits to `main`/`master` — PROHIBITED

### Rule 5: Team coordination (MANDATORY)

Before starting ANY work, the agent MUST:

1. **Read `TEAM_STATUS.md`** — see what other team members are working on
2. **Ask the human** if there are tasks from other teammates that overlap
3. **Never duplicate** work already assigned to someone else
4. **Update `TEAM_STATUS.md`** when starting and finishing work

**At conversation start, the agent MUST:**
1. Read `TEAM_STATUS.md`
2. Show current team status
3. Ask: "What is your role in the team?" (see roles below)
4. Ask: "What task would you like to work on?"

### Team roles

| Role | Focus area |
|------|-----------|
| ML / NLP / Knowledge Graphs | Embeddings, graph algorithms, entity extraction, vector search |
| Data Scientist | Data analysis, experiments, benchmarks, metrics |
| Системный аналитик / архитектор | Architecture, design patterns, API contracts, system design |
| Исследователь материаловедения | Domain knowledge, material properties, scientific accuracy |
| Product-менеджер | Requirements, prioritization, user stories, acceptance criteria |

**Agent pre-work checklist:**
1. Read `TEAM_STATUS.md` — check for conflicting tasks
2. Ask human their role and task
3. Read this file (project-specific rules)
4. Verify branch — if on `main`/`master`, create a feature branch first
5. Only commit/push when user explicitly asks
6. When done: update `TEAM_STATUS.md`, merge to `staging`, run checks, ask human for `main` merge

### Rule 6: Critical thinking — do NOT be a yes-man (MANDATORY)

**The agent is a teammate, not a servant. Follow these rules strictly:**

1. **If unsure — say so.** Never guess, never assume. "I'm not sure about X, here's why..."
2. **If the human is wrong — correct them.** Show the weak spots in their reasoning.
3. **If a suggestion brings no real value — say so.** Don't implement things that don't help.
4. **Skip empty compliments.** No "great question!" or "excellent idea!" — get to the point.
5. **Before implementing — check existing code.** Search the codebase first. If functionality already exists, point it out instead of duplicating.
6. **Don't think you're smarter than everyone.** You're a tool. Verify, don't assume.
7. **Check ALL code before claiming it works.** Read it. Trace the logic. Don't trust your memory.
8. **If the human asks for something harmful — refuse and explain why.** (security risks, data loss, breaking changes)

**Before writing ANY code, the agent MUST:**
- Grep/glob for existing implementations of the same feature
- Read the relevant modules to understand current behavior
- If similar code exists → tell the human, suggest reusing/extending it
- If new code is needed → explain why existing code doesn't cover it

**When the human proposes a change, the agent MUST:**
- Evaluate: does this actually solve the problem?
- Identify: what breaks, what's missing, what's redundant?
- Report: "This will work because X, but consider Y risk"
- If bad idea: "I don't recommend this because [reason]. Instead, consider [alternative]"

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
pip install -e ".[dev]"

# Test
python -m pytest kg_engine/tests/ -v

# Lint
ruff check kg_engine/
ruff check --fix --unsafe-fixes kg_engine/

# Ingest data
python kg_engine/scripts/ingest_materials_kg.py --input path/to/data --ensure-schema
```

## Project Structure

```
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
`MATERIAL`, `EXPERIMENT`, `PROPERTY`, `MODE`, `EQUIPMENT`, `TEAM`, `DOCUMENT`, `TAG`

### Relation types (9)
`EVALUATES_MATERIAL`, `USES_MODE`, `MEASURES_PROPERTY`, `USES_EQUIPMENT`, `PERFORMED_BY`, `DOCUMENTED_IN`, `TAGGED_WITH`, `REFERENCES`, `RELATED_TO`

### Module responsibilities
- **domain/models.py:** Pydantic models — entities, evidence, relations, observations, DTOs, query results
- **domain/resolution.py:** Canonical name resolution via alias normalization
- **repositories/protocols.py:** Persistence contract used by the service layer
- **repositories/neo4j.py:** Primary runtime backend, Neo4j nodes and relationships
- **repositories/memory.py:** In-memory storage for unit tests only
- **repositories/factory.py:** Environment-driven repository bootstrap
- **services/materials_kg.py:** Public graph-first ingestion, query, and deterministic hypothesis API
- **services/hypothesis_adjustments.py:** Expert adjustment schema and score recalculation
- **services/session.py:** In-memory conversation session store with TTL
- **agents/hypothesis_factory.py:** Deep Agents orchestration for hypothesis generation
- **agents/hypothesis_tools.py:** Read-only graph tools exposed to the agent
- **agents/extraction_agent.py:** Deep Agents orchestration for document entity extraction
- **api/materials_core.py:** FastAPI app with upload, query, hypothesis, and graph endpoints
- **ingestion/adapters.py:** Normalize raw source-family payloads into domain inputs
- **llm_core/provider.py:** OpenAI-compatible LLM provider with streaming and retry
- **llm_core/extraction.py:** LLM-powered entity extraction and answer generation
- **llm_core/token_budget.py:** Token budget management for context window fitting
- **llm_core/fallback.py:** Fallback chain with circuit breaker for LLM providers
- **config/settings.py:** Pydantic-settings loaded from .env

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
class TestMaterialIngestion:
    def test_reference_entity_is_persisted(self) -> None:
        repo = InMemoryMaterialsKGRepository()
        service = MaterialsKGService(repo)
        service.ingest_reference_data(
            ReferenceDataBatch(
                entities=[CanonicalEntityInput(kind=EntityKind.MATERIAL, name="Ti-6Al-4V")]
            )
        )
        entity = repo.resolve_entity(EntityKind.MATERIAL, "Ti-6Al-4V")
        assert entity is not None
        assert entity.canonical_name == "Ti-6Al-4V"
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

## Agent Files Reference

All 5 agent-facing files in this project must stay consistent. If one is overwritten, check the others:

| File | Purpose |
|------|---------|
| `AGENTS.md` (this file) | **Source of truth** — full conventions, dev commands, structure |
| `.agents/skills/materials-knowledge-graph/SKILL.md` | Domain skill — architecture, entity/relation types, query examples |
| `.cursor/rules/materials-kg-agent.mdc` | Coding rules, domain overview, key patterns |
| `.cursor/rules/terminal.mdc` | Terminal setup, venv, common commands |
| `.cursor/rules/commit.mdc` | Commit message format and guidelines |

---

**Remember:** DRY, lean, modular, pythonic. Research first, plan, produce flawless code.
