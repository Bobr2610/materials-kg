# План: Настройка проекта Materials Knowledge Graph

> **⚠️ This is `materials-kg` repository. References to source codebases below are generic examples — the code was ported from internal RAG/agent projects but this repo is fully standalone under `kg_engine/`.**

> **Created:** 2026-06-26  
> **Status:** ✅ COMPLETE  
> **Goal:** Инициализировать git-репозиторий, создать структуру правил для агентов, отвязать от других проектов

---

## Executive Summary

Проект `materials-kg` создан на основе кода из внутренних RAG и agent-проектов. Задача — сделать его самостоятельным, независимым проектом с собственной документацией, git-историей и правилами для агентов.

### Что сделано

| Задача | Статус | Коммит |
|--------|--------|--------|
| `git init` | ✅ | `b225a06` |
| `.gitignore` | ✅ | `b225a06` |
| Knowledge graph module (9 файлов) | ✅ | `d98b2cd` |
| 26 тестов graph module | ✅ | `d98b2cd` |
| README.md (переписан под materials-kg) | ✅ | ~ (no commit, direct edit) |
| AGENTS.md (переписан) | ✅ | `541ceff` |
| `.agents/skills/materials-knowledge-graph/SKILL.md` | ✅ | `541ceff` |
| `.cursor/rules/` (3 rules files) | ✅ | `541ceff` |
| `.cursor/plans/README.md` | ✅ | `3cdae51` |
| `.opencode/.gitignore`, `plans/`, `chats/` | ✅ | `3cdae51` |
| Удалён `.git` из исходных проектов | ✅ | direct |

### Структура проекта

```
materials-kg/
  AGENTS.md                         # Главный гайд для агентов
  README.md                         # Описание проекта
  .gitignore
  .agents/
    skills/
      materials-knowledge-graph/
        SKILL.md                    # Основной скилл
  .cursor/
    rules/
      materials-kg-agent.mdc        # Правила кодинга
      terminal.mdc                  # Правила терминала
      commit.mdc                    # Правила коммитов
    plans/
      20260626-knowledge-graph-implementation.plan.md
  .opencode/
    .gitignore
    plans/
      README.md
    chats/
      README.md
    kg_engine/
    graph/          # Знаниевый граф (schemas, store, extractor, query, search, tools)
    retrieval/      # Векторный поиск (ChromaDB)
    agent/          # LangChain-агент
    api/            # Gradio UI
    core/           # Обработка документов
    llm/            # LLM manager
    tools/          # LangChain tools
    config/         # Настройки
    utils/          # Shared utilities
    storage/        # Vector store adapters
    scripts/        # Build scripts
    tests/          # Тесты
```

---

## Детали реализации

### git init
```bash
git init
git add -A
git commit -m "Initial commit: Materials Knowledge Graph engine"
```

### Knowledge Graph module
Создан как `kg_engine/graph/` с 9 файлами:
- `__init__.py` — публичные экспорты
- `schemas.py` — Pydantic-модели (8 EntityType, 12 RelationType)
- `store.py` — NetworkX-хранилище с JSON-сериализацией
- `extractor.py` — Regex + LLM извлечение
- `builder.py` — построитель графа из документов
- `query.py` — движок запросов
- `search.py` — гибридный поиск
- `pipeline.py` — сквозной пайплайн
- `tools.py` — 5 LangChain tools

### Правила для агентов
Созданы по образу исходных проектов:
- `AGENTS.md` — comprehensive guide
- `.agents/skills/` — skill definition
- `.cursor/rules/` — cursor-specific rules
- `.cursor/plans/` — plan storage
- `.opencode/` — opencode storage

---

## Веррификация

```bash
# Проверить git
git log --oneline
git status

# Запустить тесты
python -m pytest kg_engine/tests/test_graph.py -v
```
