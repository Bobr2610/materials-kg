---
name: CMO GenAI research pack update (validated)
overview: "Re-validated 2026-03-27 after repo sync: core CMO Club × red_mad_robot integration is **implemented** (sizing «Российский рынок», methodology subsections, Appendix D bridges, Appendix A nav/registry). This file is reconciled with [.cursor/plans/cmo_genai_research_sync_1b15a97b.plan.md](cmo_genai_research_sync_1b15a97b.plan.md). Optional hooks in Appendix B/C remain **out of scope** unless requested."
todos:
  - id: citations-stack
    content: Primary t.me/cmoclub/197 + RB.RU corroboration in sizing/methodology/D/A; PDF/full study for contract-grade claims — locked in repo
    status: completed
  - id: methodology-cmo-subsection
    content: "### GenAI в маркетинговых командах… + Источники (зрелость GenAI…); cross-ref sizing #sizing_russian_market"
    status: completed
  - id: sizing-canonical-metrics
    content: "Canonical bullets under ### Российский рынок (#sizing_russian_market): 93%, budget 64%/1–5%, tools 91%/59%, barriers, RB.RU cross-check"
    status: completed
  - id: appendix-d-market-risks
    content: "### Организационные барьеры… (#app_d__org_barriers_risk_survey_2025); duplicate ### Зрелость GenAI… + Источники"
    status: completed
  - id: appendix-a-nav
    content: Nav bullet L82 area; CMO Club posts + Исследования рынка registry
    status: completed
  - id: appendix-b-tools-optional
    content: "OPTIONAL: Appendix B — ChatGPT/Midjourney concentration + sovereign/IP tie-in (not done; sync plan scoped out)"
    status: pending
  - id: appendix-c-cmo-sentence-optional
    content: "OPTIONAL: Appendix C — one sentence CMO Club joint study + link to methodology anchor (not done)"
    status: pending
isProject: false
---

# CMO GenAI study — validated plan (reconciled with repo)

## Status

Пакет **20260325** уже содержит интеграцию опроса **red_mad_robot × CMO Club Russia (2025)**. Прежняя версия этого файла с тезисом «реализация не продвинулась» **устарела** и заменена этой сводкой.

**Аудит-трейл выполнения:** см. [.cursor/plans/cmo_genai_research_sync_1b15a97b.plan.md](cmo_genai_research_sync_1b15a97b.plan.md).

## Где что лежит (якоря)


| Назначение                                 | Документ                                                                              | Якорь                                                                                       |
| ------------------------------------------ | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| **Канон по долям и формулировкам** опроса  | [sizing-main](docs/research/20260325-research-report-sizing-economics-main-ru.md)     | `#sizing_russian_market` (подраздел **GenAI в маркетинге** внутри **Российский рынок**)     |
| Управленческий смысл + перекрёстные ссылки | [methodology-main](docs/research/20260325-research-report-methodology-main-ru.md)     | `#method_genai_marketing_teams`; Источники — `#method_genai_marketing_maturity_russia_2025` |
| Орг. барьеры, LLM02 vs две линии **43%**   | [appendix-d](docs/research/20260325-research-appendix-d-security-observability-ru.md) | `#app_d__org_barriers_risk_survey_2025`; также `#app_d__genai_marketing_maturity_russia`    |
| Навигация «вопрос → документ» + реестр     | [appendix-a](docs/research/20260325-research-appendix-a-index-ru.md)                  | пункт про CMO (~L82); `#### Посты CMO Club Russia`                                          |


**Источники в комплекте:** [t.me/cmoclub/197](https://t.me/cmoclub/197); [RB.RU — 93% команд…](https://rb.ru/news/93-komand-v-marketinge-ispolzuyut-ii-nejroseti-pomogayut-s-kontentom-no-im-pochti-ne-doveryayut-strategiyu-i-byudzhety/).

## Deep research (кратко)

- **Первичка для договоров:** полный текст/PDF исследования у авторов; в репо — открытые анонс и СМИ.
- **RB.RU** используется как **перекрёстная сверка** чисел с Telegram/дайджестом (уже отражено в sizing).
- **Не смешивать** с отдельным [Habr trend-report GenAI 2025](https://habr.com/ru/companies/redmadrobot/articles/879750), если там **нет** явного пересказа **этого** опроса CMO Club.
- Дополнительные СМИ ([CNews](https://cnews.ru/link/n667050), [vc.ru](https://vc.ru/marketing/2648606-top-7-neyrosetey-dlya-marketinga-v-2025)) — **опционально** в `## Источники`, если понадобится третья независимая ссылка.

## Не сделано намеренно (optional)


| Элемент                                      | Файл       | Заметка                                                                                   |
| -------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------- |
| Концентрация инструментов → суверенитет/ИС   | Appendix B | В sync-плане помечено **out of scope**; оставить как опцию при доработке IP/теневого SaaS |
| Одно предложение про совместное исследование | Appendix C | Опция для связи MCP-блока с рыночным бенчмарком                                           |


## Правила согласованности (актуальные)

- Числа и формулировки опроса **ведут** из sizing `#sizing_russian_market`; methodology и D **ссылаются** или дублируют с тем же смыслом и ссылками на Telegram/RB.RU.
- Две доли **43%** (галлюцинации/ошибки vs утечки) в sizing **разведены**; в D — связь утечек с **LLM02** без смешения с другой **43%**.

## Дальнейшие действия

- **Нет обязательных задач** по этому плану, пока не изменится первоисточник или политика цитирования.
- При желании закрыть optional — выполнить два pending todo (B и C) отдельным микро-PR.

