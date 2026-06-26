---
name: Research pack anchor remap (20260325)
overview: "Re-validated: 424 heading IALs unchanged (A96 B43 D85 M100 S100); docs grew in lines (e.g. methodology ~1459, sizing ~1626, appendix A ~1146) without new IALs. Replace all fragments (appendix C + pack). Sync .cursor/plans + this plan file (rg hits ~11 here until rewritten). Fix duplicate research_pkg_d at D lines 19 and 460. Update AGENTS.md."
todos:
  - id: extract-map
    content: Script extract (old_id, file, heading line) from 20260325-research-*.md; emit skeleton JSON + orphan check (links to missing ids)
    status: in_progress
  - id: author-english-map
    content: Fill 20260325-anchor-map.json (r26{a,b,d,m,s}_*); semantic _2/_3/_4; document H1 app_d_ root id + separate step for fenced YAML example (same old string research_pkg_d)
    status: pending
  - id: apply-replace
    content: Ordered replace in six pack MDs; rg repo for research_{methodology_20260325,sizing_20260325,pkg_[abcd]}_ → zero
    status: pending
  - id: sync-cursor-plans
    content: "Update plans embedding #research_* (openai-enterprise, qwen35, r-d-2026, redmadnews, research-org-strategy, cmo-genai-validated, genai-market-map) or banner as historical"
    status: pending
  - id: update-agents-md
    content: docs/research/AGENTS.md consolidated packs replace transliterated_slug with concise English snake_case slugs
    status: pending
isProject: false
---

# Remap 20260325 research pack anchors — validated plan

## Final validation (2026-03-27, repo state)

### Latest re-check (same plan; later repo edits)

- **IAL counts (unchanged):** `rg '{: #[a-z0-9_]+'` on `docs/research/20260325-research-*.md` still yields **A=96, B=43, D=85, methodology=100, sizing=100** → **424** heading IAL lines, **423** distinct id strings.
- **Body growth without new anchors:** open-editor snapshot shows longer narratives ([docs/research/20260325-research-report-methodology-main-ru.md](docs/research/20260325-research-report-methodology-main-ru.md) ~1459 lines, [docs/research/20260325-research-report-sizing-economics-main-ru.md](docs/research/20260325-research-report-sizing-economics-main-ru.md) ~1626, [docs/research/20260325-research-appendix-a-index-ru.md](docs/research/20260325-research-appendix-a-index-ru.md) ~1146) while per-file **100/100/…** IAL totals stayed flat — good sign that recent edits were prose/sources, not new `{: #…}` headings.
- **Appendix D duplicate:** `{: #research_pkg_d }` still at **lines 19 and 460** (H1 + fenced example); collision-handling step remains mandatory.
- `**rg` noise from this plan:** [.cursor/plans/research-pack-anchor-remap-20260325.plan.md](research-pack-anchor-remap-20260325.plan.md) alone accounts for **~11** matches of `research_(methodology|sizing|pkg_)` in prose. **Definition of done** for “zero old slugs”: either rewrite/remove those mentions here last, or `rg --glob '!research-pack-anchor-remap-20260325.plan.md'` until this file is cleaned up.

### What is being changed

- **Syntax:** Kramdown inline attribute lists on headings: `## Заголовок {: #anchor_id }` ([Kramdown quick reference](https://kramdown.gettalong.org/quickref.html)). This is **not** GitHub-flavored Markdown core; GitHub’s web preview often **ignores** IALs and auto-derives heading anchors from visible text (problematic for Cyrillic). English ids still help **Kramdown/Jekyll/MkDocs** stacks that enable **attr_list** / compatible extensions (e.g. [Python-Markdown attr_list](https://python-markdown.github.io/extensions/attr_list/) when used with heading handling) and keep URLs short where explicit ids are honored.
- **Primary corpus:** Five files **define** anchors; one file links only (counts = `rg '{: #[a-z0-9_]+'` on `20260325-research-*.md`):
  - [docs/research/20260325-research-appendix-a-index-ru.md](docs/research/20260325-research-appendix-a-index-ru.md) — **96** heading IALs.
  - [docs/research/20260325-research-appendix-b-ip-code-alienation-ru.md](docs/research/20260325-research-appendix-b-ip-code-alienation-ru.md) — **43**.
  - [docs/research/20260325-research-appendix-d-security-observability-ru.md](docs/research/20260325-research-appendix-d-security-observability-ru.md) — **85**.
  - [docs/research/20260325-research-report-methodology-main-ru.md](docs/research/20260325-research-report-methodology-main-ru.md) — **100**.
  - [docs/research/20260325-research-report-sizing-economics-main-ru.md](docs/research/20260325-research-report-sizing-economics-main-ru.md) — **100**.
  - [docs/research/20260325-research-appendix-c-cmw-existing-work-ru.md](docs/research/20260325-research-appendix-c-cmw-existing-work-ru.md) — **0** heading IALs; **multiple** paragraphs/tables link into methodology, sizing, D, and A (e.g. GPU rental subsection `research_sizing_20260325_arenda_gpu_iaas_rf_`*, org maturity `research_methodology_20260325_strategiya_vnedreniya_ii_i_organizatsionnaya_zrelost`, CMO GenAI `research_methodology_20260325_genai_v_marketingovyh_komandah_`*, RAG/MCP deep links into appendix D). **Every** `20260325-research-*.md#research_`* fragment in C must be rewritten with the shared map.
- **Total heading IAL lines:** **424** (96+43+85+100+100). **Distinct `old_id` strings:** **423** — the string `research_pkg_d` appears **twice** (real H1 and fenced YAML example ~line 460). A flat `old→new` JSON cannot assign **two** different new ids to the **same** key; execution must either (1) **pre-edit** the example line to a temporary unique old id, then map both, or (2) **bulk-replace** all `{: #research_pkg_d }` → `{: #app_d__… }` for the document H1, then **one targeted replace** on the example line only to `app_d__ex_skill_yaml` (or strip IAL there).

### Cross-link and repo-wide references (beyond the six files)

- **Pack-internal links** appear in body text, tables (e.g. appendix A mapping rows for GPU / RTX / Qwen subsections), and “Связанные документы” blocks. **Methodology** links to sizing for **on-prem GPU profile** and related anchors; **appendix C** adds **cross-doc** anchors (GPU IaaS rental, org strategy, marketing GenAI survey, industrial RAG / MCP sections in D). The extractor must run on the **current** files — do not reuse anchor lists from earlier plan revisions.
- `**.cursor/plans/*.md`** still embed **concrete** old anchors. Command used: `rg 'research_(methodology_20260325|sizing_20260325|pkg_[abcd])_'` over repo `*.md` (2026-03-27). Files hit include at least:
  - [.cursor/plans/openai-enterprise-report-research-pack.plan.md](.cursor/plans/openai-enterprise-report-research-pack.plan.md)
  - [.cursor/plans/qwen35-moe-research-pack.plan.md](.cursor/plans/qwen35-moe-research-pack.plan.md)
  - [.cursor/plans/r-d-2026-market-signals-redmadrobot.plan.md](.cursor/plans/r-d-2026-market-signals-redmadrobot.plan.md)
  - [.cursor/plans/research-redmadnews-digest-pack-update.plan.md](.cursor/plans/research-redmadnews-digest-pack-update.plan.md)
  - [.cursor/plans/research-org-strategy-skolkovo-redmadrobot.plan.md](.cursor/plans/research-org-strategy-skolkovo-redmadrobot.plan.md)
  - [.cursor/plans/cmo-genai-research-pack-update-validated.plan.md](.cursor/plans/cmo-genai-research-pack-update-validated.plan.md)
  - [.cursor/plans/genai-market-map-research-pack.plan.md](.cursor/plans/genai-market-map-research-pack.plan.md)
  - This plan file [research-pack-anchor-remap-20260325.plan.md](research-pack-anchor-remap-20260325.plan.md) (mentions old prefixes in prose — update or leave a single “retired slug pattern” note after execution).
  After migration, either **update** those fragments to new ids or add an explicit **historical** banner (line numbers in plans drift continuously).
- **docs/research/20260324-research-task.md** — no `research_`* anchor matches (no change required there).

### HTML correctness: duplicate id in appendix D

- [docs/research/20260325-research-appendix-d-security-observability-ru.md](docs/research/20260325-research-appendix-d-security-observability-ru.md): document H1 (~~line 19) uses `{: #research_pkg_d }` and a **fenced** example (~~line 460) repeats `# Skill Name {: #research_pkg_d }`, duplicating the H1 id. When remapping, assign the example a **unique** id (e.g. `app_d__ex_skill_yaml`) or **strip** the IAL from the example line.

### Plausible vs live anchors in plans

- Some **Cursor plans** describe headings that are **not yet** in the repo (e.g. proposed `research_methodology_20260325_empirika_`*). The extractor’s source of truth is **only** ids present in the five research files; plan text that references non-existent ids should be cleaned up separately or left as prose without claiming a live fragment.

## Naming convention (concise English)


| File        | Prefix    | Notes                                 |
| ----------- | --------- | ------------------------------------- |
| Appendix A  | `app_a_`  | Index / registry / navigation         |
| Appendix B  | `app_b_`  | IP / KT / alienation                  |
| Appendix D  | `app_d__` | Security / compliance / observability |
| Methodology | `method_` | Main methodology report               |
| Sizing      | `sizing_` | Economics / sizing                    |


Rules: lowercase ASCII `snake_case`, digits allowed; **unique within each file** (AGENTS requirement); prefer **globally** unique across the pack for simpler `rg`. Replace numeric `_2`/`_3`/`_4` tails with **semantic** disambiguators (e.g. `app_a_src_wrap_engineering` vs `app_a_src_full_registry_engineering`).

## Implementation steps

1. **Extractor** — Scan the six `20260325-research-*.md` paths; emit `(old_id, path, line_no, heading_text)` and a list of **link targets** `#old_id` that have **no** matching definition in the target file (orphan report).
2. **Dictionary** — Commit `docs/research/20260325-anchor-map.json` (or `.yaml`): `{ "old_id": "new_id" }` with **full coverage** of every extracted `old_id`. Authoring: fill from CSV/JSON skeleton; avoid fully automatic Russian→English without review (**~420+** rows, exact = distinct ids).
3. **Replace** — Load map; sort keys by **length descending**; for each file replace `{: #old }` → `{: #new }` and every `(…#old)` / `(#old)` fragment. Include appendix C and all pack files. **Exception:** handle `research_pkg_d` on the **H1 vs code-fence** duplicate via a dedicated step (see distinct-id note above) so the example does not share the document root id.
4. **Repo-wide verify** — `rg 'research_(methodology_20260325|sizing_20260325|pkg_[abcd])_'` over `*.md` should end at **zero** after migration (include **this** anchor-remap plan in the sweep, or delete retired examples once). Optionally allow the committed `20260325-anchor-map.json` **only** if it stores old keys for audit — otherwise keep old prefixes out of the repo entirely.
5. **Cursor plans** — Update the **seven** sibling plans listed under cross-links (or document staleness), **then** scrub or replace slug examples in **this** file so the verify command is unambiguous.
6. **AGENTS.md** — [docs/research/AGENTS.md](docs/research/AGENTS.md) **Consolidated packs**: change “`prefix_transliterated_slug`” to **concise English slug** after the file prefix.

## Optional hardening

- Small script in CI or `rag_engine/scripts/` that fails if a link `20260325-research-*.md#` points to an id not defined in that file.
- Spot-check export pipeline (if any) that uses Kramdown vs GFM.

## Out of scope

- Renaming the six filenames; changing Russian heading **titles**; translating body text.

