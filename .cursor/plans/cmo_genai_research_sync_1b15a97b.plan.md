---
name: CMO GenAI research sync
overview: "Integrate red_mad_robot × CMO Club Russia GenAI-in-marketing (2025) into the 20260325 pack — **completed** in repo (2026-03-27). Sizing, methodology, Appendix D, Appendix A (nav, Посты CMO Club, condensed + full «Исследования рынка», RB corroboration) are in place; this plan is retained as audit trail."
todos:
  - id: sizing-canonical-block
    content: Expand GenAI block + Источники in sizing-main; RB.ru corroboration
    status: completed
  - id: methodology-subsection
    content: "### GenAI в маркетинге…" in methodology-main with Kramdown anchor; cross-ref sizing
    status: completed
  - id: appendix-d-bridge
    content: Appendix D org barriers + LLM02 vs hallucinations; Источники
    status: completed
  - id: appendix-a-nav
    content: Appendix A nav + CMO Club channel/posts + registry mirror sizing Источники
    status: completed
isProject: false
---

# CMO Club / red_mad_robot GenAI marketing — plan (archived / complete)

## Scope (files touched)

| File | Role |
|------|------|
| [docs/research/20260325-research-report-sizing-economics-main-ru.md](docs/research/20260325-research-report-sizing-economics-main-ru.md) | Canonical survey percentages; `### Исследования рынка`; RB.RU corroboration |
| [docs/research/20260325-research-report-methodology-main-ru.md](docs/research/20260325-research-report-methodology-main-ru.md) | `### GenAI в маркетинговых командах…` under «Российский рынок ИИ» |
| [docs/research/20260325-research-appendix-d-security-observability-ru.md](docs/research/20260325-research-appendix-d-security-observability-ru.md) | Org barriers; **утечки → LLM02** vs hallucination **43%** |
| [docs/research/20260325-research-appendix-a-index-ru.md](docs/research/20260325-research-appendix-a-index-ru.md) | Nav; `#### Исследования рынка` (condensed + full `_2`); CMO Club posts |

**Out of scope:** Appendices B/C — no CMO hooks (unchanged).

---

## Validation snapshot (post-execution, 2026-03-27)

| Document | State |
|----------|--------|
| **Sizing** | GenAI block + `### Исследования рынка` with cmoclub + RB; metrics cross-checked with RB.RU article. |
| **Methodology** | Anchored `###` for CMO / GenAI marketing maturity; cross-links from Appendix A. |
| **Appendix D** | Organizational barriers + OWASP LLM02 mapping; sources updated. |
| **Appendix A** | Nav bullet (L82 area); `#### Посты CMO Club Russia`; `#### Исследования рынка` before observability (condensed) and before Telegram (full, `#…_genai_2`); ~1141 lines total file. |

**Primary:** [t.me/cmoclub/197](https://t.me/cmoclub/197). **Corroboration:** [RB.RU — 93% команд…](https://rb.ru/news/93-komand-v-marketinge-ispolzuyut-ii-nejroseti-pomogayut-s-kontentom-no-im-pochti-ne-doveryayut-strategiyu-i-byudzhety/).

---

## Quality gates (reference)

- [docs/research/AGENTS.md](docs/research/AGENTS.md): traceable claims; two **43%** barrier lines not conflated with LLM02.
- `rg cmoclub docs/research/20260325-*.md` — hits in sizing, methodology, D, A.

---

## Execution note

Supersedes older plan copies for line anchors. No further work unless primary sources change.
