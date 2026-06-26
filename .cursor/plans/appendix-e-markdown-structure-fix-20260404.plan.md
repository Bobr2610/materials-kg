# Appendix E Markdown structure fix plan

## Goal

Apply the smallest possible structural cleanup to `20260325-research-appendix-e-market-technical-signals-ru.md` so the document renders predictably and reads cleanly without changing its substantive research content.

## Scope

- Remove the stray fenced-code marker in the `llm_under_hood` subsection.
- Replace the malformed grouped table in `Модели и ценообразование` with valid Markdown structure.
- Remove the empty heading before `Практический опыт внедрения ИИ`.

## Planned edits

1. Update `docs/research/executive-research-technology-transfer/report-pack/20260325-research-appendix-e-market-technical-signals-ru.md`
   - Delete the orphan ````` line after the `llm_under_hood` bullet list.
   - Split the model pricing block into category subheadings with valid tables.
   - Remove the empty `## Справочные блоки из отчёта по методологии внедрения` heading.

## Verification

- Re-read the edited sections in context.
- Check `git diff --stat` and targeted `git diff`.
- Run `ReadLints` for the edited file.
