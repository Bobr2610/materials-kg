# Task 1 Agent Coordination - Materials KG

## Purpose

Этот файл нужен двум оставшимся агентам как общий контракт работ по задаче
"Фабрика гипотез". Он фиксирует текущую картину, зоны ответственности и
правила, чтобы параллельная работа не ломала уже готовый контур
LLM extraction -> graph ingestion -> Deep Agent hypotheses.

## Current State

- ML/KG контур уже доведен до рабочего состояния: phased extraction
  `strategy -> entities -> relationships -> measurements`, 9 read-only tools
  для Deep Agent, adaptive prompt, validation результата как
  `HypothesisGenerationResult`, фильтрация неподкрепленных гипотез.
- Гипотезы нельзя ослаблять: каждая должна ссылаться на конкретные graph IDs
  через `supporting_evidence_ids`, `supporting_observation_ids`,
  `supporting_text_unit_ids` или `data_gap_ids`.
- Endpoint Agent 2 ищет реальный corpus в `Задача 1/`, `task-1/`,
  `task1/`, `task_1/` или `data/task1/`. Если этих папок нет в worktree, он
  загружает packaged fallback `sample_sources/` и возвращает warning в API/UI.
- Папка `data/` пока legacy seed для `/demo/load-sample`; не удалять, пока
  новый demo-flow на материалах `Задача 1/` не готов и не покрыт тестами.
- Папка `sample_sources/` остается временным fallback-корпусом для Agent 2
  smoke/demo flow. Не расширять ее вместо реального ingestion: PDF/DOCX/XLSX/PNG
  readers остаются зоной Agent 1.

## Ownership

### Agent 1 - Data Ingestion / Corpus

Владелец реального ingestion для материалов задания.

Можно менять:

- `kg_engine/ingestion/`
- `kg_engine/scripts/ingest_materials_kg.py`
- reader/helper modules for PDF/DOCX/XLSX/PNG
- API upload parsing only where it connects formats to ingestion
- tests for parsers, metadata, noisy inputs, OCR/table extraction
- documentation sections about ingestion formats

Нельзя менять без согласования:

- grounding validation in `kg_engine/agents/hypothesis_factory.py`
- Deep Agent tool contracts in `kg_engine/agents/hypothesis_tools.py`
- UI/export flow owned by Agent 2

Required work:

1. Add format readers for `.pdf`, `.docx`, `.xlsx`, `.png`.
2. Preserve source metadata: filename, page/sheet/row, fragment, language when
   available.
3. Convert extracted text/tables into `DocumentInput`, `ExperimentInput` or
   canonical entities without breaking public DTOs.
4. Add regression tests for empty, noisy, numeric, table-heavy and long inputs.
5. Provide a repeatable command or API path to ingest `Задача 1/`.

Acceptance:

- Real files from `Задача 1/` load without manual conversion.
- Numeric facts keep value/unit/comparator/fragment provenance.
- LLM-extracted relationships resolve endpoints by graph IDs.
- Tests cover the new readers and at least one end-to-end ingestion path.

### Agent 2 - Product / API / Export / UX

Владелец пользовательского сценария и вывода результата.

Можно менять:

- `kg_engine/api/materials_core.py`
- `ui-page.html` or a replacement UI entry point
- export/report helpers
- README/API docs for user workflows
- tests for API smoke, exports, demo loading, feedback UX

Нельзя менять без согласования:

- low-level PDF/DOCX/XLSX/PNG readers owned by Agent 1
- entity/relation extraction prompts unless Agent 1/3 approve
- grounding filter that removes unbacked hypotheses

Required work:

1. Add `/demo/load-task-materials` or equivalent endpoint/command that loads the
   new `Задача 1/` corpus.
2. Update UI flow: upload data -> inspect graph/query -> generate hypotheses ->
   show evidence -> export.
3. Show hypothesis cards with score breakdown, novelty/risk/value, mechanism,
   roadmap and concrete supporting graph IDs.
4. Add export to JSON/CSV, and preferably DOCX/PDF if dependencies are
   available.
5. Add expert feedback controls: score, reject, comment, and save feedback for
   future ranking calibration.

Acceptance:

- A researcher can start from the provided files and receive a grounded ranked
  hypothesis list.
- Every visible hypothesis exposes links/IDs to evidence, observations, text
  units or data gaps.
- Exports contain enough provenance for expert review outside the app.

### Agent 3 - ML / KG / Deep Agent

Текущий ML/KG контур считается готовой базой. Agent 3 подключается только для
точечных исправлений, если ingestion or product work reveals real extraction
or grounding bugs.

Можно менять:

- `kg_engine/llm_core/extraction.py`
- `kg_engine/agents/hypothesis_factory.py`
- `kg_engine/agents/hypothesis_tools.py`
- graph-service glue in `kg_engine/services/materials_kg.py`
- tests directly covering extraction, tools, prompt adaptation and grounding

Нельзя делать:

- remove post-generation grounding validation
- generate hypotheses from prompt-only context without graph tool reads
- add provider-specific prompt assumptions outside `LLMProvider.chat_json`
- weaken DTO validation to accept malformed agent JSON silently

## Shared Rules

- No ungrounded hypotheses. Any graph claim must trace to evidence,
  observation, text unit or data gap ID.
- Do not break public DTOs unless the human explicitly approves a migration.
- Do not delete `data/` until the new task-materials demo path replaces
  `/demo/load-sample` and tests are green.
- Do not restore `sample_sources/` just to satisfy stale docs. Prefer updating
  docs and tests to the new corpus.
- Preserve provenance aggressively: source file, page/sheet/row, fragment,
  extraction method, warnings and trace events.
- Keep LLM-provider neutrality: extraction and agents must work through
  provider-neutral messages and `LLMProvider.chat_json`.
- No commits or pushes without a separate human command.

## Shared Acceptance Checklist

- `ruff check kg_engine/`
- `python -m pytest kg_engine/tests/ -v`
- Manual flow: ingest `Задача 1/` -> inspect graph -> generate hypotheses ->
  verify evidence IDs -> export results.
- Documentation no longer points users only to obsolete sample inputs.
