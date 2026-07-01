---
name: mimo-subagent
description: Reusable MiMo CLI orchestration skill for delegating work to MiMo across any project. Use this skill whenever the user asks to use mimo, MiMo CLI, mimo run, mimo-auto, MiMo as a subagent, an external autonomous agent, or wants a task delegated to MiMo for research, coding, or summarization. Prefer this skill even when the user does not explicitly mention a skill but clearly wants work routed through MiMo.
---

# MiMo Subagent

## Purpose
Use MiMo CLI as a reusable external agent from any project directory.

This skill is for:
- launching MiMo reliably on Windows
- checking provider and model availability before a run
- choosing a sensible default model
- saving MiMo outputs into the current project instead of hiding them in transient terminal history
- making MiMo delegation consistent across repositories

## Default behavior
1. Treat `mimo/mimo-auto` as the default model unless the user explicitly asks for a different model.
2. Verify MiMo is available before delegating:
   - `mimo --help` if command resolution works
   - otherwise use the Windows shim path `C:\Users\misha\AppData\Roaming\npm\mimo.cmd`
3. Check login state before substantive runs:
   - `mimo providers whoami`
4. If the task depends on a specific model family, inspect:
   - `mimo models mimo`
5. Persist results in the active project under `docs/mimo-runs/YYYYMMDD/<slug>/`.

## When to choose MiMo
MiMo is a good fit when the user wants:
- an external autonomous agent
- a second opinion from another model
- web research through MiMo
- a delegated coding or summarization subtask
- a reproducible CLI-based workflow they can rerun themselves

MiMo is usually not necessary when:
- the task is trivial and can be completed directly with local tools
- the user wants a purely local action with no external model/provider calls
- provider access is unavailable and there is no acceptable fallback

## Windows launch rules
On this machine, command resolution may lag even after install. Prefer this order:

1. Try `mimo`.
2. If that fails, use:
   - `C:\Users\misha\AppData\Roaming\npm\mimo.cmd`
3. If that fails, verify installation of `@mimo-ai/cli`.

## Standard workflow
1. Identify the goal:
   - research
   - code task
   - review/summary
   - freeform delegation
2. Choose the model:
   - default: `mimo/mimo-auto`
   - explicit user override: use the requested model
3. Build a compact prompt for MiMo:
   - include the task
   - include constraints
   - specify desired output format
   - ask for source URLs if the task needs web research
4. Run MiMo in JSON or normal mode depending on whether structured capture matters.
5. Save useful output artifacts into the current repo.
6. Summarize what MiMo produced and note any provider/runtime failures.

## Output conventions
For project artifacts, create:

`docs/mimo-runs/YYYYMMDD/<task-slug>/`

Suggested files:
- `00_prompt.txt` — the prompt sent to MiMo
- `10_raw_output.jsonl` — raw JSON event stream if `--format json` is used
- `20_summary.md` — cleaned summary for humans
- `sources.md` — extracted URLs when MiMo performs research

## Safety and confirmation
MiMo calls may send prompts and context to an external provider. For tasks involving:
- proprietary code
- secrets
- confidential documents
- large workspace context

pause and make that risk explicit before sending the task to MiMo.

For harmless public-web research or generic documentation lookup, proceed when the user has already asked to use MiMo.

## Recommended commands
Read `references/models.md` for model-selection guidance.

Use `scripts/run_mimo.ps1` on Windows when you want a stable launcher that:
- resolves the shim path
- writes prompt/output files
- supports model selection

## Prompting guidance
When delegating to MiMo:
- be specific about the deliverable
- ask for concise outputs first
- request citations or URLs for web tasks
- avoid dumping unnecessary repo context
- if asking for coding help, point MiMo at only the files or subproblem it needs

## Example delegations
Research:
"Find official documentation for Python argparse. Use authoritative sources only. Return a short summary and source URLs."

Code review:
"Review this module for likely bugs and behavioral regressions. Return findings first, ordered by severity."

Coding subtask:
"Propose a minimal patch plan for adding retry logic around this HTTP client. Keep it framework-consistent."

## Checklist
- [ ] Confirm MiMo CLI is callable
- [ ] Confirm provider login state when needed
- [ ] Choose model, defaulting to `mimo/mimo-auto`
- [ ] Create `docs/mimo-runs/YYYYMMDD/<slug>/`
- [ ] Save prompt and output artifacts
- [ ] Report MiMo result clearly, including failures and source URLs
