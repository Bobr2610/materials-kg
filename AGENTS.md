# AGENTS.md - Materials Knowledge Graph

**Source of truth.** Concise rules. Details live in skills.

## AUTOMATIC: Rules Display at Conversation Start

**At the START of EVERY conversation, the agent MUST display BEFORE any other output:**

```
=== ПРАВИЛА РАБОТЫ С РЕПОЗИТОРИЕМ ===

1. Никогда не работай на main/master — создавай feature-ветку
2. Ветки: feat/<модуль>-<описание>, fix/<модуль>-<описание>
3. Модули: domain, repositories, services, agents, api, ingestion, llm_core, config
4. Мерж: feature → staging → main (только с согласия человека)
5. Прочитай TEAM_STATUS.md — проверь задачи других участников
6. Обновляй TEAM_STATUS.md при начале и завершении работы
7. Никогда не коммить/пушь без явного запроса человека
8. Никогда не дублируй задачи других участников команды
9. MiMo доступен? Проверь: mimo --help
10. Используй Docker для запуска: docker compose up -d

=== КОНЕЦ ПРАВИЛ ===
```

## Quick Reference

| What | How |
|------|-----|
| Branch | `git checkout -b feat/<module>-<desc>` |
| Merge | feature → staging → main (human approval) |
| Lint | `ruff check kg_engine/` |
| Test | `python -m pytest kg_engine/tests/ -v` |
| Docker | `docker compose up -d --build` |
| MiMo | `mimo run -m "mimo/mimo-auto" "task"` |

## Mandatory Skills

**Read these skills when the task requires them:**

| Skill | When to load |
|-------|-------------|
| `docker-workflow` | Running the app, testing in containers |
| `mimo-subagent` | Delegating tasks to MiMo |
| `team-coordination` | Starting work, checking TEAM_STATUS.md |
| `critical-thinking` | Before writing code, reviewing proposals |
| `code-style` | Writing Python, following conventions |

## Prohibited Actions

- `git push --force` — NEVER
- `git reset --hard` — NEVER
- Merge to `main` without human approval — NEVER
- Auto-commit without user request — NEVER
- Direct commits to `main`/`master` — NEVER
- Let MiMo work in project root — NEVER
- Hardcode secrets — NEVER

## Branch Naming

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feat/<module>-<desc>` | `feat/domain-add-crystal` |
| Fix | `fix/<module>-<desc>` | `fix/services-null-check` |
| Refactor | `refactor/<module>-<desc>` | `refactor/repositories-async` |
| Docs | `docs/<desc>` | `docs/update-api` |
| Test | `test/<module>-<desc>` | `test/services-coverage` |

Modules: `domain`, `repositories`, `services`, `agents`, `api`, `ingestion`, `llm_core`, `config`

## Project Structure

```
kg_engine/
  domain/          # Entities, relations, DTOs
  repositories/    # Neo4j, memory, factory
  services/        # Ingestion, query, hypotheses
  agents/          # Deep Agents orchestration
  api/             # FastAPI app
  ingestion/       # File parsers
  llm_core/        # LLM providers, extraction
  config/          # Settings
  scripts/         # CLI tools
  tests/           # Test suite
```

## Entity Types (8)

`MATERIAL`, `EXPERIMENT`, `PROPERTY`, `MODE`, `EQUIPMENT`, `TEAM`, `DOCUMENT`, `TAG`

## Relation Types (9)

`EVALUATES_MATERIAL`, `USES_MODE`, `MEASURES_PROPERTY`, `USES_EQUIPMENT`, `PERFORMED_BY`, `DOCUMENTED_IN`, `TAGGED_WITH`, `REFERENCES`, `RELATED_TO`

## Module Responsibilities

| Module | Key file | Purpose |
|--------|----------|---------|
| domain | `models.py` | Pydantic models — entities, relations, DTOs |
| repositories | `neo4j.py` | Primary Neo4j backend |
| services | `materials_kg.py` | Graph ingestion and query API |
| agents | `hypothesis_factory.py` | Hypothesis generation |
| agents | `hypothesis_tools.py` | Read-only graph tools |
| agents | `extraction_agent.py` | Document entity extraction |
| api | `materials_core.py` | FastAPI app |
| llm_core | `provider.py` | LLM provider with streaming |
| llm_core | `extraction.py` | Entity extraction |

## Agent Files

| File | Purpose |
|------|---------|
| `AGENTS.md` | **This file** — source of truth |
| `.agents/skills/materials-knowledge-graph/SKILL.md` | Domain skill |
| `.agents/skills/mimo-subagent/SKILL.md` | MiMo delegation |
| `.agents/skills/docker-workflow/SKILL.md` | Docker commands |
| `.agents/skills/team-coordination/SKILL.md` | Team workflow |
| `.agents/skills/critical-thinking/SKILL.md` | Anti-yes-man rules |
| `.agents/skills/code-style/SKILL.md` | Python conventions |

---

**Remember:** DRY, lean, modular, pythonic. Research first, plan, produce flawless code.
