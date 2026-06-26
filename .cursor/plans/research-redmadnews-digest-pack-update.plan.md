---
name: research-redmadnews-digest-pack-update
overview: Redmadnews / red_mad_robot alignment for the 20260325 corpus — **complete** (2026-03-27). Appendix A includes MCP under methodology + open projects, Redmad permalinks, condensed and full «Исследования рынка» (CMO × RB), and an explicit note that 20260323 monoliths omit post-baseline URLs.
todos:
  - id: appendix-a-mcp-and-posts
    content: "Appendix A: Habr 982004 + GitHub mcp-registry under «Методологии…»; «Посты @Redmadnews» + mirror in «Telegram-каналы и посты»"
    status: completed
  - id: appendix-a-cmo-issledovaniya-rynka
    content: "Appendix A: «Исследования рынка» (cmoclub/197 + RB.RU) condensed before #app_a_observability_telemetry; full block #app_a_market_research_genai_maturity_2 before Telegram"
    status: completed
  - id: appendix-a-open-projects-mcp-optional
    content: Parity with Appendix D — Habr + mcp-registry after openapi-to-cli under open projects
    status: completed
  - id: methodology-tier-b
    content: "Methodology main: framed bullets + Источники for 5145/5146/5170"
    status: completed
  - id: sizing-tier-b-china
    content: "Sizing main: 5159 near «Три мира» + Источники"
    status: completed
  - id: cross-check-b-c-d
    content: Appendix A CMO/MCP edits — B/C/D unchanged; AGENTS.md list rules respected
    status: completed
  - id: policy-20260323
    content: "Обзор комплекта (Appendix A): монолиты 20260323 без дублирования ссылок из сплит-комплекта 20260325"
    status: completed
  - id: optional-tier-c
    content: 5167/5176/YouTube — expand only with primary technical sources
    status: cancelled
isProject: false
---

# Redmadnews digest — plan (complete, workspace repo)

## External sanity check (reference)

- [Habr — MCP Tool Registry](https://habr.com/ru/companies/redmadrobot/articles/982004/)
- [GitHub — redmadrobot-rnd/mcp-registry](https://github.com/redmadrobot-rnd/mcp-registry)

Telegram permalinks remain volatile; replace labels only after manual 404 check.

---

## Validation snapshot (`docs/research/20260325-*.md`, Appendix A ~1141 lines)


| Check                                                                            | Result                                                                                             |
| -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Appendix A: Habr `982004` + GitHub `mcp-registry` under «Методологии внедрения…» | **Present**                                                                                        |
| Appendix A: `#### Посты @Redmadnews` with `/5132`+                               | **Present**                                                                                        |
| Appendix A: «Telegram-каналы и посты» Redmad permalinks                          | **Present**                                                                                        |
| Appendix A: `#### Исследования рынка` + cmoclub/197 + RB.RU (condensed + full)   | **Present** (`#app_a_market_research_genai_maturity`, `#…_genai_2`)                                |
| Appendix A: duplicate MCP after `openapi-to-cli`                                 | **Present**                                                                                        |
| Appendix B/C/D: MCP + body where applicable                                      | **Present**                                                                                        |
| Methodology / Sizing: Tier B hooks                                               | **Present**                                                                                        |
| `20260323-`* monoliths: new URLs                                                 | **Omitted by design**; Appendix A «Обзор комплекта» states split-pack is canonical for added links |


---

## Quality gates (on future edits)

1. [docs/research/AGENTS.md](docs/research/AGENTS.md): empty line before lists; plain links in final `## Источники`; no uncited CMO KPIs.
2. GenAI in marketing = demand signal in sizing narrative, not GPU line item.
3. No Python changes → no Ruff unless code touched.

```mermaid
flowchart LR
  doneA[MCP_Redmad_CMO_in_A]
  doneB[Methodology_5145_5146_5170]
  doneC[Sizing_5159_and_CMO]
  policy[20260323_baseline_note]
  doneA --> policy
```



