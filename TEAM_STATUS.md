# TEAM_STATUS.md — Командный статус проекта Materials KG

**Агенты ОБЯЗАНЫ читать этот файл перед началом работы и обновлять его.**

---

## Роли и зоны ответственности

### ML / NLP / Knowledge Graphs
**Направление:** Улучшить качество извлечения данных и генерации гипотез

| # | Задача | Статус | Участник | Ветка |
|---|--------|--------|----------|-------|
| 1 | Разбить extraction на последовательные шаги: сущности → связи → числовые значения | готово | Codex | feat/agents-grounded-extraction |
| 2 | Промпты extraction должны работать с любым LLM-провайдером | готово | Codex | feat/agents-grounded-extraction |
| 3 | Добавить агенту больше tools для чтения из графа (сейчас 5, сервис умеет ещё 4) | готово | Codex | feat/agents-grounded-extraction |
| 4 | System prompt агента адаптируется под входные данные (не статичный) | готово | Codex | feat/agents-grounded-extraction |
| 5 | После генерации гипотез — проверять привязку к конкретным данным из графа (антигаллюцинация) | готово | Codex | feat/agents-grounded-extraction |
| 6 | Расширить extraction agent — выбор стратегии обработки документа | готово | Codex | feat/agents-grounded-extraction |

### Data Scientist
**Направление:** Метрики и оценка качества

| # | Задача | Статус | Участник | Ветка |
|---|--------|--------|----------|-------|
| 1 | Создать модуль метрик: точность извлечения, полнота контекста, покрытие сущностей, достоверность, новизна | готово | Codex | feat/agents-grounded-extraction |
| 2 | Всё работает offline без LLM | готово | Codex | feat/agents-grounded-extraction |
| 3 | Heat map покрытия: материалы × режимы × свойства | готово | Codex | feat/agents-grounded-extraction |
| 4 | Сравнение двух запусков (deterministic vs agent) по всем метрикам | готово | Codex | feat/agents-grounded-extraction |
| 5 | Обратная связь эксперта: оценка гипотез 1-5, сохранение, перекалибровка весов | готово | Codex | feat/agents-grounded-extraction |
| 6 | Корреляция между автоматическими оценками и экспертными (когда будет датасет) | готово | Codex | feat/agents-grounded-extraction |

### Системный аналитик / архитектор
**Направление:** Расширить входные форматы и API

| # | Задача | Статус | Участник | Ветка |
|---|--------|--------|----------|-------|
| 1 | Парсинг PDF (научные статьи с таблицами) | открыта | — | — |
| 2 | Парсинг DOCX | открыта | — | — |
| 3 | Парсинг XLSX | открыта | — | — |
| 4 | Ingestion по URL — скачать и обработать статью по ссылке | открыта | — | — |
| 5 | CRUD для гипотез — сохранять, просматривать, фильтровать, удалять | открыта | — | — |
| 6 | Export результатов в CSV/JSON/PDF | открыта | — | — |
| 7 | Обновить docker-compose — поднимать всё вместе, не только Neo4j | открыта | — | — |

### Исследователь материаловедения
**Направление:** Domain knowledge и тесты

| # | Задача | Статус | Участник | Ветка |
|---|--------|--------|----------|-------|
| 1 | Расширить промпты extraction materials-специфичными терминами (LPBF, HIP, aging, annealing и т.д.) | открыта | — | — |
| 2 | Единицы измерения в промптах (MPa, HRC, %IACS) | открыта | — | — |
| 3 | Тесты парсеров: корректное извлечение чисел с единицами из разных форматов | открыта | — | — |
| 4 | Проверка что гипотезы не содержат зашёппых placeholder-ов | открыта | — | — |
| 5 | Coverage rules для сплавов: Ti-6Al-4V, CuCrZr, 316L, IN718 | открыта | — | — |
| 6 | Подготовить интерфейс для приёма датасета | открыта | — | — |

### Product-менеджер
**Направление:** Интерфейс и документация

| # | Задача | Статус | Участник | Ветка |
|---|--------|--------|----------|-------|
| 1 | Переписать UI на Gradio — три вкладки: загрузка файлов, запросы к графу, генерация гипотез | открыта | — | — |
| 2 | Карточки гипотез с разбивкой score и привязкой к источникам | открыта | — | — |
| 4 | Dashboard метрик | открыта | — | — |
| 5 | API documentation с примерами запросов | открыта | — | — |

---

## Общая миссия проекта

**Фабрика гипотез** — инструмент на базе ИИ для автоматизации генерации и ранжирования научно-исследовательских гипотез для материаловедческих и технологических проектов.

Система принимает на вход:
- Целевой показатель (KPI)
- Базу знаний (литература, исторические отчёты, эксперименты)

На выходе формирует:
- Структурированный список проверяемых гипотез
- Обоснование каждой гипотезы
- Оценку новизны, рисков, потенциальной ценности

**Принципы:**
- Интерпретируемость — прозрачная логика формирования рекомендаций
- Возможность экспертной корректировки
- Ускорение старт НИОКР-проектов
- Снижение зависимости от субъективного опыта отдельных сотрудников

---

## Текущий статус участников

<!-- Агенты обновляют эту секцию при начале и завершении работы -->
<!-- Формат: | Роль | Имя/ID | Задача | Статус | Ветка | Дата | -->

| Роль | Участник | Задача | Статус | Ветка | Обновлено |
|------|----------|--------|--------|-------|-----------|
| _(пусто)_ | — | — | — | — | — |

## История выполненных задач

<!-- Завершённые задачи переносятся сюда -->

| Роль | Участник | Задача | Результат | Дата |
|------|----------|--------|-----------|------|
| ML / NLP / Knowledge Graphs | Codex | Deep Agent + graph-grounded extraction | Добавлены phased LLM extraction entities→relationships→measurements, provider-neutral prompts, provenance для LLM relationships/observations, 9 read-only graph tools для Deep Agent, adaptive system prompt, post-generation grounding validation, regression tests; полный suite 89 passed | 2026-07-02 |
| Product / Coordination | Codex | Координационный файл для Task 1 | Добавлен `docs/TASK1_AGENT_COORDINATION.md`: зоны ответственности Agent 1/2/3, правила конфликтов вокруг `data/`, `sample_sources`, grounding и acceptance checklist | 2026-07-02 |
| ML / NLP / Knowledge Graphs | Codex + MiMo | Agent 3 audit/refinement ML/KG core | MiMo с repo context заблокирован политикой, выполнен safe abstract review; локально усилен grounding filter: supporting_entity_ids больше не считаются достаточным grounding без evidence/observation/text/data_gap IDs; добавлен regression test; исправлен ruff issue в chunk merge; targeted checks passed, полный suite 99 passed | 2026-07-02 |
| ML / NLP / Knowledge Graphs | Codex | Исправление 7 gaps в агентской логике | chunked_phased extraction (чанкинг длинных документов), N+1 fix в query_data_gaps, parallel LLM+explicit extraction, adaptive embedding truncation (8000), Neo4j fulltext index, transaction batching, lenient grounding check (trace+matched_entities IDs); полный suite 89 passed | 2026-07-02 |
| Data Scientist | Codex | Метрики и оценка качества гипотез offline | Добавлены offline metrics module и API: Entity/Relation F1, Context Recall, Context Entities Recall, Faithfulness/Groundedness, Novelty, repository coverage heatmap, deterministic-vs-agent full comparison, экспертный JSONL feedback, recalibrated ranking weights, auto/expert correlation, regression tests, MiMo review без blockers | 2026-07-01 |
| Data Scientist | Codex | Аудит метрик — проверка корректности | Полный аудит metrics.py (681 строк): 8 метрик проверены, найдены issues: novelty binary override (0/1), weight recalibration degenerate с 2 entries, coverage ratio misleading для sparse spaces, нет тестов для text_unit_ids不在 context | 2026-07-02 |
| Product / API / Export / UX | Codex Agent 2 | Task 1 product flow and exports | Добавлены `/demo/load-task-materials` с fallback на packaged `sample_sources`, `/hypotheses/export` JSON/CSV, UI загрузки Task 1, карточки гипотез с provenance IDs, сохранение expert feedback; документация синхронизирована с фактическим corpus flow; ruff OK, pytest 100 passed; локальный Uvicorn health + demo loader OK; Docker build не подтверждён из-за DNS к Docker registry | 2026-07-02 |
| Архитектор/QA | Codex | Full Docker pipeline verification with Yandex AI Studio | Docker/Neo4j/API подняты; Task 1 corpus загружен через Yandex config; query/answer, graph/state, deterministic hypotheses and JSON/CSV export OK; исправлены resolver/tool-contract/env propagation issues; pytest 117 passed; Deep Agents runtime остаётся заблокирован tool-loop/rate-limit behavior | 2026-07-03 |

---

## Правила работы с файлом

1. **При начале работы** — агент добавляет строку в "Текущий статус"
2. **При завершении работы** — агент переносит задачу в "История выполненных задач"
3. **При смене задачи** — агент обновляет строку (задача + статус + ветка)
4. **НЕ удаляйте** записи других участников — только свои
5. **Статусы:** `открыта` | `в работе` | `ожидает проверки` | `готово` | `заблокировано`
6. **Нумерация задач** — соответствует номерам в таблицах ролей выше
