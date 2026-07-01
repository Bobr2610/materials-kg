---
name: mimo-subagent
description: Reusable MiMo CLI orchestration skill for delegating work to MiMo across any project. Use this skill whenever the user asks to use mimo, MiMo CLI, mimo run, mimo-auto, MiMo as a subagent, an external autonomous agent, or wants a task delegated to MiMo for research, coding, or summarization. Prefer this skill even when the user does not explicitly mention a skill but clearly wants work routed through MiMo.
---

# MiMo Subagent

## Purpose
Use MiMo CLI as a reusable external agent from any project directory.

## AUTOMATIC: MiMo Check at Conversation Start

**At the START of EVERY conversation, the agent MUST check MiMo availability:**

```bash
# Check if MiMo is available
mimo --help 2>$null
if ($LASTEXITCODE -ne 0) {
    $mimoShim = "C:\Users\misha\AppData\Roaming\npm\mimo.cmd"
    if (Test-Path $mimoShim) {
        Write-Host "MiMo available via shim: $mimoShim"
    } else {
        Write-Host "WARNING: MiMo CLI not found. Install @mimo-ai/cli"
    }
} else {
    Write-Host "MiMo CLI available"
}

# Check login state
mimo providers whoami 2>$null
```

**Display result to user:**
```
=== MiMo Status ===
CLI: [available / not found]
Provider: [logged in / not logged in]
Model: mimo/mimo-auto (default)
====================
```

If MiMo is NOT available, inform the user and skip delegation features.

## Work Tree Pattern

**For each MiMo delegation, create an ISOLATED work tree that gets DELETED after use.**

### Why work trees
- MiMo works in its own space — no conflicts with main codebase
- Changes don't leak into your branches
- Report stays separate — never merged into feature/staging/master
- Clean isolation: work tree → output → delete

### How to create work tree

```bash
# 1. Create isolated work tree for MiMo
$taskSlug = "mimo-task-name"
$workTree = ".mimo-worktrees/$taskSlug"
New-Item -ItemType Directory -Force -Path $workTree | Out-Null

# 2. Copy ONLY the files MiMo needs into work tree
Copy-Item "kg_engine/services/materials_kg.py" "$workTree/"

# 3. Run MiMo in the work tree context
mimo run -m "mimo/mimo-auto" "Review materials_kg.py for bugs. Work in: $workTree"

# 4. Collect output (report stays in docs/mimo-runs/)
# 5. DELETE the work tree
Remove-Item -Recurse -Force $workTree
```

### Work tree rules
1. **NEVER** let MiMo work directly in the project root
2. **ALWAYS** create `.mimo-worktrees/<task-slug>/` for each task
3. **ALWAYS** delete work tree after MiMo finishes
4. **NEVER** merge MiMo's work tree branches into main branches
5. **Report** goes to `docs/mimo-runs/` — that's the only output that stays

### Directory structure

```
materials-kg/
  .mimo-worktrees/          # TEMPORARY — deleted after use
    task-slug-1/             # Isolated space for MiMo task 1
    task-slug-2/             # Isolated space for MiMo task 2
  docs/
    mimo-runs/               # PERMANENT — reports stay here
      20260701/
        task-slug/
          00_prompt.txt
          20_summary.md
          sources.md
```

## Prompt Writing Guide

### Structure of a good MiMo prompt

```
[ROLE] You are a [specific role] reviewing/analyzing/building [what].

[TASK] Your task is to [exact action].

[CONTEXT] Here is the relevant code/data:
[paste ONLY what's needed]

[CONSTRAINTS]
- Do NOT modify any files
- Return findings as [format]
- Include source URLs for web research
- Keep response under [length] words

[OUTPUT FORMAT]
Return in this exact structure:
## Summary
[1-2 sentences]

## Findings
1. [finding]
2. [finding]

## Sources (if applicable)
- [URL]
```

### Prompt examples by task type

**Code review:**
```
[ROLE] You are a senior Python developer reviewing code for bugs.

[TASK] Review the following module for logical errors, type issues, and edge cases.

[CONTEXT]
```python
[paste code here]
```

[CONSTRAINTS]
- Do NOT modify files
- Focus on correctness, not style
- Order findings by severity (critical → low)

[OUTPUT FORMAT]
## Critical Issues
- [issue]

## Warnings
- [issue]

## Suggestions
- [issue]
```

**Research:**
```
[ROLE] You are a technical researcher.

[TASK] Find the latest documentation for [technology].

[CONSTRAINTS]
- Use only official documentation
- Include URLs for every claim
- Focus on version [X] and newer

[OUTPUT FORMAT]
## Key Points
- [point]

## Code Examples
[example]

## Sources
- [URL] — [description]
```

**Summarization:**
```
[ROLE] You are a technical writer summarizing complex information.

[TASK] Summarize the following content for a [target audience].

[CONTEXT]
[paste content]

[CONSTRAINTS]
- Max [N] bullet points
- No jargon without explanation
- Actionable items first

[OUTPUT FORMAT]
## TL;DR
[1 sentence]

## Key Takeaways
- [point]

## Action Items
- [item]
```

### Anti-patterns (don't do this)

**BAD — too vague:**
```
Look at this code and tell me if it's good
```

**BAD — too much context:**
```
Here's my entire project (5000 lines). Review everything.
```

**BAD — no output format:**
```
Tell me about Neo4j
```

**GOOD — specific, constrained, structured:**
```
Review kg_engine/services/materials_kg.py lines 45-120.
Focus on: error handling, type safety, edge cases.
Return: Critical → Warning → Suggestion format.
Do NOT modify files.
```

## Standard workflow
1. **Check MiMo availability** (at conversation start)
2. **Identify the goal:** research / code task / review / summary
3. **Create work tree:** `.mimo-worktrees/<task-slug>/`
4. **Copy needed files** into work tree
5. **Build prompt** using the guide above
6. **Run MiMo** in work tree context
7. **Collect report** → `docs/mimo-runs/YYYYMMDD/<slug>/`
8. **Delete work tree**
9. **Summarize** results to user

## Safety and confirmation
- **NEVER** send secrets, API keys, or credentials to MiMo
- **NEVER** send confidential code without user consent
- **NEVER** let MiMo modify files in the main project
- **ALWAYS** use work tree isolation
- **ALWAYS** delete work tree after use
- For public research → proceed when user asks
- For proprietary code → warn the user first

## Checklist
- [ ] MiMo CLI available (checked at conversation start)
- [ ] Provider login state verified
- [ ] Work tree created: `.mimo-worktrees/<slug>/`
- [ ] Only needed files copied to work tree
- [ ] Prompt follows the writing guide
- [ ] MiMo run completed
- [ ] Report saved to `docs/mimo-runs/`
- [ ] Work tree deleted
- [ ] Results summarized to user
