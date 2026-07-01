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

## How to Invoke This Skill

**This skill is a markdown file that gets loaded as instructions when called.**

### Codex (OpenAI)

Codex reads `.codex/instructions.md` at start. To invoke this skill:

```
/mimo-subagent
```

Codex loads `.agents/skills/mimo-subagent/SKILL.md` into context.

### Claude Code

Claude Code reads `.claude/CLAUDE.md` at start. To invoke:

```
/mimo-subagent
```

Claude loads the skill file as additional instructions.

### Cursor

Cursor reads `.cursor/rules/*.mdc`. To invoke, ask the agent:

```
Use the mimo-subagent skill to review this code
```

Cursor loads `.agents/skills/mimo-subagent/SKILL.md`.

### MiMo (MiMoCode)

MiMo has a `skill()` tool. To invoke:

```javascript
skill({ name: "mimo-subagent" })
```

MiMo loads `.agents/skills/mimo-subagent/SKILL.md` into context.

### Any Agent via AGENTS.md

AGENTS.md has a skills table. The agent reads it and decides:

```
When to load: Delegating tasks to MiMo
```

Agent calls `Read(file_path=".agents/skills/mimo-subagent/SKILL.md")`.

### Manual (bash)

Any agent can read the file directly:

```bash
cat .agents/skills/mimo-subagent/SKILL.md
```

### Quick Reference

| Agent | Method | Command |
|-------|--------|---------|
| Codex | Slash command | `/mimo-subagent` |
| Claude Code | Slash command | `/mimo-subagent` |
| Cursor | Natural language | "Use mimo-subagent skill" |
| MiMo | Tool call | `skill({name: "mimo-subagent"})` |
| Any | Read file | `Read(".agents/skills/mimo-subagent/SKILL.md")` |

## Built-in Slash Commands

MiMoCode has built-in skills invocable via `/` prefix in chat.

### Available Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/imagegen` | Generate or edit raster images (photos, illustrations, textures, mockups, sprites) | `/imagegen a 3D isometric server room` |
| `/impeccable` | Design, redesign, polish frontend UI — websites, dashboards, components, theming, accessibility, UX | `/impeccable redesign the login page` |
| `/mimo-subagent` | Delegate tasks to MiMo as a subagent for research, coding, or summarization | `/mimo-subagent review this code` |
| `/openai-docs` | Get help with OpenAI products, APIs, models, Codex itself | `/openai-docs which model for code gen` |
| `/plugin-creator` | Create and scaffold Codex plugin directories | `/plugin-creator create a plugin` |
| `/self-extend` | Evolve your own capabilities — new tools, hooks, skills | `/self-extend add a hook` |
| `/skill-creator` | Guide for creating effective skills | `/skill-creator make a new skill` |
| `/skill-installer` | Install skills from curated list or GitHub repo | `/skill-installer install web-search` |
| `/web-search` | Multi-source web research with anti-bot resilience and cited outputs | `/web-search latest GPT-5 benchmarks` |

### How Commands Work

1. User types `/command-name arguments` in chat
2. MiMoCode loads the skill's `SKILL.md` into context
3. Skill body becomes additional instructions for that scope
4. Skill does NOT change the tool set — only behavior and guidance

### Built-in Workflows (via agent tool)

These are invoked programmatically by the agent, not as slash commands:

| Workflow | Description | When to use |
|----------|-------------|-------------|
| `compose` | Full autonomous pipeline: brainstorm → design → implement → verify → review → report → merge | Feature, bugfix, refactor, or review tasks end-to-end |
| `deep-research` | Parallel web searches → read sources → cross-check facts → cited report | Thorough multi-source research on any topic |

**Invoke compose:**
```javascript
workflow({ operation: "run", name: "compose", args: { task: "implement feature X", type: "feature" } })
```

**Invoke deep-research:**
```javascript
workflow({ operation: "run", name: "deep-research", args: "latest research on quantum computing applications" })
```

### Skill vs Workflow

| Aspect | Slash Command (`/`) | Workflow (`workflow()`) |
|--------|---------------------|------------------------|
| Invocation | User types in chat | Agent calls programmatically |
| Scope | Single skill loaded as context | Multi-phase orchestration |
| Subagents | No | Yes — parallel subagents |
| Use case | Guidance for specific domain | Complex multi-step automation |

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
