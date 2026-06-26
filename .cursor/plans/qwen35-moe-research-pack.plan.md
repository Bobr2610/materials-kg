---
name: Qwen35 MoE research pack
overview: "Re-validated 2026-03-27: sizing report still contains the full Qwen3.5 community block + Источники; methodology, appendix D bridge, and appendix A FinOps registry entries are still missing. Optional hygiene unchanged."
todos:
  - id: appendix-a-sources
    content: "Add Medium + apxml + HF Qwen3.5-35B-A3B after PitchGrade in BOTH FinOps subsubsections: «Использовано в комплекте» (~376–386) and «без сокращений» (~792–802) in appendix A"
    status: completed
  - id: methodology-qwen35
    content: "Extend Cloud.ru Qwen bullet (~276) and HF matrix row (~329) with Qwen3.5-* + сверка каталога/прайса; add new URLs to methodology ## Источники if first citation"
    status: completed
  - id: appendix-d-throughput-bridge
    content: After server metrics bullet (~51 in appendix D), add 1–2 sentences linking community t/s claims to gen_ai.server.time_per_output_token and sizing doc by title
    status: pending
  - id: optional-appendix-a-toc
    content: "Optional: add `### Ориентиры сообщества…` / `### Бенчмарки RTX 4090…` rows to appendix A heading→document map under «Промежуточное заключение по сайзингу»"
    status: pending
  - id: optional-crosslink-397b
    content: "Optional: one-line cross-link between `### Qwen3.5-397B на M3 Max 48GB` (~922 sizing) and `### Ориентиры сообщества: Qwen3.5-35B-A3B…` (~651)"
    status: pending
  - id: optional-rtx4090-vram
    content: "Optional: correct consumer RTX 4090 VRAM (24 ГБ) where doc still says 48 ГБ (e.g. sizing ~628–631, scenario table, etc.)"
    status: pending
isProject: false
---

# Qwen3.5 MoE / local inference — plan status (validated against repo)

## Re-validation (2026-03-27)

- `rg 'apxml|Qwen3\\.5'` on the six `20260325-*.md` files: hits only in **sizing** (body + `## Источники`); **no** hits in appendix A, methodology, B, or C; appendix D has only the pre-existing `gen_ai.server.`* line (~51), **no** added throughput bridge paragraph yet.
- Stable anchor for the new sizing subsection: `#sizing_community_qwen_consumer_hardware` (use in appendix A heading map / deep links if desired).

## Validation snapshot

Validated against:

- [docs/research/20260325-research-report-sizing-economics-main-ru.md](docs/research/20260325-research-report-sizing-economics-main-ru.md) (~1 563 lines)
- [docs/research/20260325-research-report-methodology-main-ru.md](docs/research/20260325-research-report-methodology-main-ru.md) (~1 357 lines)
- [docs/research/20260325-research-appendix-d-security-observability-ru.md](docs/research/20260325-research-appendix-d-security-observability-ru.md)
- [docs/research/20260325-research-appendix-a-index-ru.md](docs/research/20260325-research-appendix-a-index-ru.md) (~1 033 lines)
- [docs/research/20260325-research-appendix-b-ip-code-alienation-ru.md](docs/research/20260325-research-appendix-b-ip-code-alienation-ru.md)
- [docs/research/20260325-research-appendix-c-cmw-existing-work-ru.md](docs/research/20260325-research-appendix-c-cmw-existing-work-ru.md)

## Implemented (no further action for original sizing scope)

In **основной отчёт: сайзинг и экономика**:

- `### Ориентиры сообщества: Qwen3.5-35B-A3B и потребительское железо (март 2026)` (~651–680): MoE framing, Medium link with marketing caveat, CapEx 800 USD → ~68 000 руб., community t/s table (incl. UD-Q4_K_XL, MLX M3 Ultra), R9700 naming caveat, HF `Qwen/Qwen3.5-35B-A3B`.
- `## Источники`: Medium, apxml VRAM calculator, HF Qwen3.5-35B-A3B (~1525–1527).
- Separate mention of apxml calculator later (~1140) for capacity planning.

Appendix **B** and **C**: no Qwen3.5-specific lines (still consistent with «out of scope» unless you add HF card under C later).

## Gaps vs original cross-file plan

1. **Appendix A** — `apxml`, Medium, and the new HF card are **not** listed under «Финансовая и инфраструктурная база» (duplicate blocks ~376–386 and ~792–802). Grep: no `apxml` / `agentnativedev` in appendix A.
2. **Methodology** — Cloud.ru Qwen catalog line (~~276) and HF table row (~~329) still list **Qwen3** families only; no explicit **Qwen3.5-*** / прайс-сверка wording.
3. **Appendix D** — `gen_ai.server.`* bullets (~51) present; **no** explicit bridge from «токенов/с из сообщества» to these metrics and the sizing report by title.

## Optional hygiene (not blocking)

- **Heading map (appendix A):** table under «Сайзинг…» does not list new `###` anchors (`Бенчмарки RTX 4090`, `Ориентиры сообщества…`); add if you want parity with other mapped subsections.
- **Two Qwen3.5 threads:** `### Ориентиры сообщества…` (~~651) vs `### Qwen3.5-397B на M3 Max 48GB` (~~922) are still unlinked; optional one-line mutual cross-reference.
- **RTX 4090 «48 ГБ»** still appears (~628–631) vs consumer 24 ГБ VRAM — pre-existing inconsistency.

## Execution note

Original plan file from the earlier session was not in this repo; this file is the **canonical updated plan** for any remaining edits.

When appendix A is updated, keep **both** FinOps duplicate lists in sync (same three URLs in the same order relative to neighbors), matching the existing pattern for Runpod / PitchGrade.