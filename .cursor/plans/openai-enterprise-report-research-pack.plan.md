---
name: ""
overview: ""
todos: []
isProject: false
---

# OpenAI State of Enterprise AI — research pack update

**Final validation:** 2026-03-27 — repo line anchors + OpenAI landing page re-fetched; **execution still not applied** to target markdown (no `the-state-of-enterprise-ai` / `### Эмпирика…` in `20260325-`* research files).

---

## 1. Validation snapshot (current repo)


| Check         | Result                                                                                                                                                                                                                                                                                                                                                                                               |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Body / URLs   | **No** `the-state-of-enterprise-ai`, **no** `### Эмпирика корпоративного внедрения`, **no** `empirika_korporativnogo` in [docs/research/20260325-research-report-methodology-main-ru.md](docs/research/20260325-research-report-methodology-main-ru.md) or [docs/research/20260325-research-report-sizing-economics-main-ru.md](docs/research/20260325-research-report-sizing-economics-main-ru.md). |
| Larridin      | Still **third-party**; methodology `### Экономика, рынок, enterprise AI` — **line 1196**; sizing `### Рынок, ROI, эффект для экономики` — **line 1585**, Larridin entry — **line 1593**. **Keep**; add OpenAI **primary** next to Larridin.                                                                                                                                                          |
| Heading IDs   | Kramdown `{: #research_*_20260325_* }` on headings. New `###` needs a **new unique** slug.                                                                                                                                                                                                                                                                                                           |
| IBM list typo | [Методология внедрения ИИ (IBM Sovereign Core)](docs/research/20260325-research-report-methodology-main-ru.md) **line 960**: `Governanced AI inference…` still **missing** leading `-`. **Optional fix** when editing that region.                                                                                                                                                                   |


**Sizing note:** `### Рынок, ROI, эффект для экономики` now includes extra RU/market rows (e.g. Ведомости, РБК, Gartner) **before** Larridin; OpenAI links should sit **immediately adjacent to** Larridin (**1593**) to preserve “global vendor empirics vs third-party blog” pairing.

---

## 2. Primary sources (execution: cite these; numbers from here + PDF if needed)

**A. State of Enterprise AI (report, Dec 8, 2025)**

- Landing: [The state of enterprise AI | OpenAI](https://openai.com/index/the-state-of-enterprise-ai-2025-report)
- PDF: [the-state-of-enterprise-ai_2025-report.pdf](https://cdn.openai.com/pdf/7ef17d82-96bf-4dd1-9df2-228f7f377a29/the-state-of-enterprise-ai_2025-report.pdf)

**B. Related post (optional, one sentence; different publication)**

- [1 million business customers…](https://openai.com/index/1-million-businesses-putting-ai-to-work) (Nov 5, 2025) — **not** (A). Do not merge methodologies.

**Deep research rule:** Landing reproduces headline stats (**§3**). Extra detail only from **PDF**; on conflict, **prefer PDF** for that number.

---

## 3. Canonical claims — *The state of enterprise AI* (OpenAI landing, Dec 8, 2025)

*Re-verified 2026-03-27 via live page; unchanged from prior plan.*

**Data composition:** (1) usage data from enterprise customers of OpenAI; (2) survey **9 000** workers, **almost 100** enterprises; deidentified, aggregated.

**Depth:** ChatGPT Enterprise weekly messages ~**8×** YoY; average worker **+30%** messages; Projects + Custom GPTs **19×** YTD; reasoning tokens per organization ~**320×** in **12** months.

**Sectors / geo (not RF baseline):** fastest-growing — technology, healthcare, manufacturing; largest scale — professional services, finance, technology; AU/BR/NL/FR business bases **>140%** YoY; international API **>70%** in six months; **Japan** largest API base outside **U.S.**

**Survey (self-reported):** **75%** speed/quality; **40–60** min/day saved; heavy **>10** h/week; IT **87%**, marketing/product **85%**, HR **75%**, engineers **73%** (as worded on page); coding messages **+36%** non-technical; **75%** new tasks.

**Frontier gap:** P95 workers **6×** median messages; frontier firms **2×** messages/seat; time savings vs “more intelligence” / more tasks.

**Cadence / bottleneck:** new capability ~**every three days**; constraints = **organizational readiness and implementation** (OpenAI framing).

**Optional context:** **>800 M** weekly ChatGPT users — **consumer**; do not conflate with enterprise survey.

---

## 4. Scope (files)


| File                                                                                                                                               | Action                                    |
| -------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| [docs/research/20260325-research-report-methodology-main-ru.md](docs/research/20260325-research-report-methodology-main-ru.md)                     | New `###` + optional резюме + `Источники` |
| [docs/research/20260325-research-report-sizing-economics-main-ru.md](docs/research/20260325-research-report-sizing-economics-main-ru.md)           | FinOps paragraph + `Источники`            |
| [docs/research/20260325-research-appendix-a-index-ru.md](docs/research/20260325-research-appendix-a-index-ru.md)                                   | Optional FAQ + registry sync              |
| [docs/research/20260325-research-appendix-b-ip-code-alienation-ru.md](docs/research/20260325-research-appendix-b-ip-code-alienation-ru.md)         | No change                                 |
| [docs/research/20260325-research-appendix-c-cmw-existing-work-ru.md](docs/research/20260325-research-appendix-c-cmw-existing-work-ru.md)           | No change                                 |
| [docs/research/20260325-research-appendix-d-security-observability-ru.md](docs/research/20260325-research-appendix-d-security-observability-ru.md) | No change                                 |


---

## 5. Methodology report — line anchors (final)

**Parent:** `## Методология Enterprise AI (Global Best Practices)` — **line 928**.

**Insert** new `###` **after** last «Ключевые метрики» bullet (**line 939**) **before** `### Break-even для инфраструктуры` (**line 941**).

**Heading:**

```markdown
### Эмпирика корпоративного внедрения (отчёт OpenAI, 2025; оговорки по выборке) {: #method_openai_implementation_report }
```

**Body:** subset of **§3**; cross-ref by title to «Инженерия обвязки…» / «Приложение D» per [docs/research/AGENTS.md](docs/research/AGENTS.md).

**Источники:** `### Экономика, рынок, enterprise AI` — **line 1196**. Add plain bullets (landing + PDF), adjacent to Larridin.

---

## 6. Sizing report — line anchors (final)

`**### FinOps и юнит-экономика нагрузки`** — **188**; harness paragraph ends **194**; `**---`** **196**; `**## CapEx / OpEx Модель`** — **198**.

**Insert** reasoning-token / FinOps paragraph **after 194**, **before 196** (~320×, segmented unit economics, OTel, cross-ref to methodology subsection title).

**Avoid** trends `**### Enterprise AI`** — **line 863**.

**Источники:** `### Рынок, ROI, эффект для экономики` — **1585**; Larridin — **1593**. Add same two OpenAI links **next to** Larridin.

---

## 7. Appendix A (final)

- Heading map row for `## Методология Enterprise AI…` — **line 115**. New `###` → **no** new `##` row.
- Registry Larridin clusters — **lines 251** and **525**; add OpenAI (A) URLs beside them.

---

## 8. Quality gates (on execution)

- [docs/research/AGENTS.md](docs/research/AGENTS.md): typography, inline cited titles, plain `Источники` list.
- Do not mix publications (A) vs (B).
- Restate ecosystem-specific caveat vs RF KPIs.

---

## 9. Execution checklist

- Methodology: new `###` between **939** and **941**; slug `empirika_korporativnogo_vnedreniya_otchet_openai_2025`; sources **~1196**.
- Sizing: paragraph after **194**, before **196**; sources **~1585** / Larridin **1593**.
- Appendix A: optional FAQ; OpenAI URLs near **251** and **525**.
- `rg empirika_korporativnogo` — confirm slug unique.
- Optional: IBM list fix **line 960** (`-` before `Governanced…`).

