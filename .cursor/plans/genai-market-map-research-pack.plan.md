---
name: GenAI market map research pack
overview: Final validation 2026-03-27 — integrate red_mad_robot «Карта российского рынка GenAI» (PDF, ноябрь 2025) and stable public siblings into the six-file 20260325 pack; coordinate with existing Redmadrobot/Skolkovo plans to avoid triple duplication.
todos:
  - id: primary-urls
    content: Lock per-metric primary URLs from PDF bibliography; use redmadrobot.ru + Habr + Skolkovo only as publication context
    status: pending
  - id: dedupe-appendix-a
    content: Appendix A — add RU market / rmr entries without duplicating McKinsey/BCG/Deloitte blocks already in vitrine
    status: pending
  - id: sizing-russia-trism
    content: Sizing — subsection under ИИ-рынок России + AI TRiSM OpEx; reconcile vs IMARC row in same chapter
    status: pending
  - id: methodology-ontology-scenarios
    content: Methodology — ontology + 2030 scenarios + change-mgmt (source each claim); preserve {: #... } anchors
    status: pending
  - id: appendix-b-kt
    content: Appendix B — optional KT bullets tied to primary sources
    status: pending
  - id: appendix-c-market-practice
    content: Appendix C — neutral integrator RAG stack paragraph after MCP/sandbox block
    status: pending
  - id: appendix-d-trism-mcp
    content: Appendix D — AI TRiSM + Gartner glossary; MCP = Model Context Protocol everywhere
    status: pending
  - id: final-agents-pass
    content: Cross-file numbers/terms; AGENTS.md typography; internal link sanity
    status: pending
isProject: false
---

# Plan: GenAI market map (red_mad_robot) → 20260325 research pack

## Final validation vs current repo (2026-03-27)

### What is still **not** in the six-pack

Grep across `docs/research/20260325-*.md` finds **no** occurrences of: `AI TRiSM`, `AI-TRISM`, `17,1 млрд`, `35 млрд` (MTS B2B LLM), `онтологич` (market ontology), `Карта рынка`, Habr `879750`, `issledovaniya-1`, `trend-report-rynok`, `Ген ИИ`, `консервативн` / `индустриализац` (2030 scenarios), `DCD`, `HyDE`, `Query Decomposition`, `Финансовый университет` (as market cite).

**Conclusion:** the GenAI **map / PDF synthesis** described in earlier iterations is **still unimplemented**. The pack has grown elsewhere (e.g. methodology ~1417 lines, sizing ~1610, appendix A ~1099, Claude 4.6, RTX wording) but **not** this thread.

### What is already covered (do not duplicate)

- **MCP Tool Registry**, Ведомости CTO, Habr ФСК/MCP, CMO Club stub — present.
- **TOM:** `### Публичные ориентиры рынка (@Redmadnews, 2026)` — see [r-d-2026-market-signals-redmadrobot.plan.md](r-d-2026-market-signals-redmadrobot.plan.md) (R&D / AI-first / China “three worlds”). **GenAI map work should not repeat those Telegram bullets.**
- **[Приложение A](docs/research/20260325-research-appendix-a-index-ru.md):** large **global** enterprise GenAI list (McKinsey Rewiring, BCG Stairway, Deloitte State of GenAI, etc.). New rows must be **Russia-specific or rmr-primary**; do not add second McKinsey/BCG line for the same report.

### Coordination with other workspace plans

| Plan | Overlap with GenAI map plan | Rule |
| --- | --- | --- |
| [r-d-2026-market-signals-redmadrobot.plan.md](r-d-2026-market-signals-redmadrobot.plan.md) | Same vendor, different artifact (posts, podcast) | GenAI map = **PDF + stats + ontology**; Redmadnews block = **signals**. Cross-link by name only. |
| [research-org-strategy-skolkovo-redmadrobot.plan.md](research-org-strategy-skolkovo-redmadrobot.plan.md) | Skolkovo + org maturity, change, pilots | If both execute: **Skolkovo CDTO** and **change-management** depth live in **org-strategy** plan; GenAI map keeps **one** short forward reference + PDF/survey stats. |
| [cmo_genai_research_sync_1b15a97b.plan.md](cmo_genai_research_sync_1b15a97b.plan.md) / CMO pack | Marketing GenAI | Orthogonal unless citing same CMO study numbers. |

---

## Deep research — public citation ladder

| Layer | URL | Use |
| --- | --- | --- |
| Исследования (листинг) | [redmadrobot.ru/issledovaniya-1](https://redmadrobot.ru/issledovaniya-1) | «Тренд-репорт: рынок GenAI в 2025 году» (5_02_2025) |
| Мероприятие | [redmadrobot.ru/meropriyatiya/trend-report-rynok-gen-ai-v-2025-godu](https://redmadrobot.ru/meropriyatiya/trend-report-rynok-gen-ai-v-2025-godu) | Контекст презентации 12 февраля 2025, Сколково |
| Habr (анонс) | [habr.com/.../879750](https://habr.com/ru/companies/redmadrobot/articles/879750/) | Не полный PDF карты; анонс события |
| Сколково (событие) | [skolkovo.ru/events/120225-sostoyanie-rynka-genai-v-rossii-i-v-mire](https://www.skolkovo.ru/events/120225-sostoyanie-rynka-genai-v-rossii-i-v-mire/) | Регистрация/описание (UTM от rmr) |
| PDF «Карта…» (ноябрь 2025) | Часто **Яндекс.Диск** или рассылка; стабильность ниже корп. домена | В репозитории: **цифры только с первоисточника из библиографии PDF** (Финуниверситет, РБК, VK, TAdviser, Forbes, MWS, …). Не вставлять локальные пути `D:\...` ([AGENTS.md](docs/research/AGENTS.md)). |
| AI TRiSM (канон) | [Gartner glossary — AI TRiSM](https://www.gartner.com/en/information-technology/glossary/ai-trism) | В PDF встречается «AI-TRISM» — в тексте пояснить соответствие **AI TRiSM** (Gartner). |

**Artifact note:** февральский **тренд-репорт 2025** и ноябрьская **«Карта» 2025** — смежные, но **разные** выпуски; в prose не сливать в один «отчёт» без даты и типа документа.

---

## File-by-file actions

### 1. [20260325-research-appendix-a-index-ru.md](docs/research/20260325-research-appendix-a-index-ru.md)

- Строка навигации: ландшафт сегментов GenAI РФ → методология + сайзинг.
- Реестр: новые URL только под фактически процитированные тезисы; дедуп с существующими McKinsey/BCG.

### 2. [20260325-research-report-sizing-economics-main-ru.md](docs/research/20260325-research-report-sizing-economics-main-ru.md)

- После [`## ИИ-рынок России: Статистика и прогнозы`](docs/research/20260325-research-report-sizing-economics-main-ru.md) (`#sizing_russia_ai_market_stats_forecasts`): подпункт с **ограниченным** набором метрик (GPU inference Финуниверситет; B2B LLM MTS AI / РБК — по цепочке из PDF); оговорка против смешения с IMARC в том же `##`.
- OpEx: одна строка на класс **AI TRiSM** (Gartner) рядом с существующим OpEx безопасности GenAI.
- Источники: добавить использованные ссылки.

### 3. [20260325-research-report-methodology-main-ru.md](docs/research/20260325-research-report-methodology-main-ru.md)

- Внутри [`## Российский рынок ИИ: Текущее состояние и Прогнозы`](docs/research/20260325-research-report-methodology-main-ru.md) (`#method_russian_ai_market_state_forecasts`): короткая **онтология сегментов** + отсылка к карте (ноябрь 2025) как стейкхолдерской рамке.
- Три **сценария до 2030** из PDF — сжато, с дисклеймером «сценарный контур автора обзора».
- Change management (80/20, шаги): **только** с первоисточником; если выполняется [research-org-strategy-skolkovo-redmadrobot.plan.md](research-org-strategy-skolkovo-redmadrobot.plan.md) — не раздувать дублем; достаточно кросс-ссылки по названию раздела.

### 4. [20260325-research-appendix-b-ip-code-alienation-ru.md](docs/research/20260325-research-appendix-b-ip-code-alienation-ru.md)

- KT: опциональные модули (психобезопасность, треки зрелости) — коротко + источник.

### 5. [20260325-research-appendix-c-cmw-existing-work-ru.md](docs/research/20260325-research-appendix-c-cmw-existing-work-ru.md)

- После блока MCP + E2B/Modal/Daytona: **нейтральный** абзац про рыночные **собственные** RAG-конвейеры (пример из карты: декомпозиция/расширение запроса, HyDE, DCD, SGR, Marker, Postgres + Qdrant/Chroma) — не как SKU CMW.

### 6. [20260325-research-appendix-d-security-observability-ru.md](docs/research/20260325-research-appendix-d-security-observability-ru.md)

- Связка **AI TRiSM** ↔ OWASP / red team / OpEx.
- Везде **Model Context Protocol** (не «Model Communication Protocol»).

---

## Quality gates

- [docs/research/AGENTS.md](docs/research/AGENTS.md): traceable numbers, `«»`, thousands spacing, `руб.`.
- Не трогать `20260323-*` эталоны и `_restructure_audit` без отдельной задачи.
- После правок: проверка внутренних ссылок и якорей; Ruff N/A для markdown-only.

---

## Execution order (recommended)

1. Собрать минимальный список **первоисточников** для каждой цифры (из PDF bibliography или прямой fetch).
2. Sizing + methodology (цифры и рамка), затем D (TRiSM), затем C, B, A (реестр последним).
3. Финальная вычитка на согласованность с IMARC и с существующим блоком @Redmadnews в TOM.
