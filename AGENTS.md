# AGENTS.md - Materials Knowledge Graph

**Source of truth.** Concise rules. Details live in skills.

## MANDATORY: Pre-Flight Gate (BEFORE ANY WORK)

**Before ANY file edit, commit, or code change — the agent MUST verify ALL of these:**

```
=== PRE-FLIGHT GATE ===

1. git fetch origin — синхронизация с remote
2. git log origin/master..origin/staging — staging впереди master?
3. Если staging впереди → ветка от staging. Если master впереди → от master.
4. TEAM_STATUS.md прочитан? Задачи других участников проверены?
5. Правила из AGENTS.md прочитаны? (ты сейчас их читаешь)
6. **MiMo CLI доступен?** → `mimo --help` + `mimo providers whoami` → показать статус
7. Никаких коммитов без запроса человека.
8. Никаких push без явного согласия.
9. Перед merge в master — ОБЯЗАТЕЛЬНО спроси человека.

ВСЕ 9 пунктов = OK → продолжай.
ЛЮБОЙ пункт = NO → исправь ПЕРЕД работой.

=== GATE PASSED ===
```

**Нарушение gate = немедленная остановка и исправление.**

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
9. Используй Docker для запуска: docker compose up -d

⚠️  ПЕРЕД ЛЮБОЙ РАБОТОЙ: пройди Pre-Flight Gate (выше).
    Если ты на master/main — создай feature-ветку ПЕРВЫМ ДЕЛОМ.

=== MiMo CHECK (ОБЯЗАТЕЛЕН) ===
Выполни:
  mimo --help
  mimo providers whoami

Покажи результат:
=== MiMo Status ===
CLI: [available / not found]
Provider: [logged in / not logged in / error]
Model: mimo/mimo-auto (default)
====================

Если MiMo недоступен — предупреди и продолжай без delegation.
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

## Git Enforcement Flow

```
ЛЮБАЯ РАБОТА
    │
    ├─ git fetch origin (всегда первым делом)
    │
    ├─ Pre-Flight Gate (выше) → FAIL? → СТОП, исправь
    │
    ├─ git log origin/master..origin/staging → staging впереди?
    │   ├─ ДА → git checkout -b feat/... origin/staging (ветка от staging)
    │   └─ НЕТ (master впереди) → git checkout -b feat/... origin/master
    │
    ├─ git pull origin <ветка> (после checkout — синхронизация)
    │
    ├─ Работа (edit, code, etc.)
    │
    ├─ git add + git commit (только по запросу человека)
    │
    ├─ git fetch origin (перед push — проверить что нет новых коммитов)
    │
    ├─ git checkout staging && git merge origin/staging && git merge feat/...
    │
    ├─ git push origin staging (только с согласия)
    │
    ├─ git checkout master && git merge origin/master && git merge staging
    │       │
    │       └─ ⚠️  СПРОСИ ЧЕЛОВЕКА: "Точно смержить в master?"
    │          Человек сказал "да" → git push origin master
    │          Человек сказал "нет" или сомневается → СТОП
    │
    └─ ГОТОВО
```

### Confirmation Required Before Every Main Merge

**Перед `git merge staging → master` агент ОБЯЗАН:**

1. Показать что будет смержено (diff summary)
2. Спросить явно: **"Точно смержить в master?"**
3. **НЕ push'ить пока человек не ответит "да" / "yes" / "погнали"**
4. Если человек ответил "нет" / "подожди" / сомневается → СТОП, ждать

**Это НЕ опционально. Даже если человек сказал "запушь в master" ранее — уточняй ПЕРЕД каждым мерджем.**

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
- **Работать без Pre-Flight Gate — NEVER (нарушение = стоп)**

## .env.example Sync Rule

**При изменении `.env.example` агент ОБЯЗАН:**

1. **Сравнить** `.env.example` с `.env`
2. **Найти** все переменные, которых нет в `.env`
3. **Показать** пользователю список недостающих переменных
4. **Предложить** добавить их в `.env` (с пустыми значениями или с теми, что уже есть)

```
=== .env.example CHECK ===

Изменения в .env.example:
+ NEW_API_KEY=           ← отсутствует в .env
+ DATABASE_URL=          ← отсутствует в .env
  EXISTING_VAR=value     ← уже есть в .env

Добавить недостающие в .env? (да/нет)
=== END CHECK ===
```

**Правила:**
- НЕ коммить `.env` — он в .gitignore
- НЕ перезаписывай существующие значения в `.env`
- НЕ добавляй секреты в `.env.example` — только плейсхолдеры
- Всегда показывай diff перед изменением `.env`

## Branch Naming

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feat/<module>-<desc>` | `feat/domain-add-crystal` |
| Fix | `fix/<module>-<desc>` | `fix/services-null-check` |
| Refactor | `refactor/<module>-<desc>` | `refactor/repositories-async` |
| Docs | `docs/<desc>` | `docs/update-api` |
| Test | `test/<module>-<desc>` | `test/services-coverage` |

Modules: `domain`, `repositories`, `services`, `agents`, `api`, `ingestion`, `llm_core`, `config`

**Branch from:** `origin/staging` (по умолчанию). Только если master впереди staging → от `origin/master`.

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
