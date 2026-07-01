# Claude Code Instructions — Materials KG

## CRITICAL: Read Before ANY Work

You are working in the Materials Knowledge Graph project. These rules protect the repository.

### AUTOMATIC: Rules Display at Conversation Start

**At the START of EVERY conversation, the agent MUST automatically display the following block BEFORE any other output:**

```
=== ПРАВИЛА РАБОТЫ С РЕПОЗИТОРИЕМ ===

1. Никогда не работай на main/master — создавай feature-ветку
2. Ветки: feat/<модуль>-<описание>, fix/<модуль>-<описание>, refactor/<модуль>-<описание>
3. Модули: domain, repositories, services, agents, api, ingestion, llm_core, config
4. Мерж: feature → staging → main (только с согласия человека)
5. Прочитай TEAM_STATUS.md — проверь задачи других участников
6. Обновляй TEAM_STATUS.md при начале и завершении работы
7. Никогда не коммить/пушь без явного запроса человека
8. Никогда не дублируй задачи других участников команды

=== КОНЕЦ ПРАВИЛ ===
```

**This output is MANDATORY. Do NOT skip it. Do NOT delay it. It is the FIRST thing the agent outputs.**

### Step 0: Team Coordination (FIRST THING)

At the START of every conversation:

1. **Read `TEAM_STATUS.md`** — see who is working on what
2. **Show the human the current team status**
3. **Ask the human:**
   - "What is your role in the team?" (ML/NLP, Data Scientist, Архитектор, Материаловед, Product)
   - "What task would you like to work on?"
   - "Are there tasks from other teammates that overlap with yours?"
4. **NEVER start work** without knowing the human's role and task
5. **NEVER duplicate** work already assigned to another team member

**When starting work**, update `TEAM_STATUS.md`:
```markdown
| ML / NLP | YourName | Task description | в работе | feat/your-branch | 2026-07-01 |
```

**When finishing work**, update `TEAM_STATUS.md`:
- Move your row to "История выполненных задач"
- Set status to `готово`

### Step 1: Read the Rules

```
Read AGENTS.md in this directory. It is the source of truth for all coding rules.
```

### Step 2: Branch Enforcement (MANDATORY)

1. **Check your current branch BEFORE any file edit.**
2. **If you are on `main` or `master`:**
   - STOP immediately.
   - Create a feature branch: `git checkout -b feat/<task-description>`
   - Only then proceed with changes.
3. **If you are on a detached HEAD:**
   - STOP immediately.
   - Create a branch: `git checkout -b feat/<task-description>`
4. **Never skip branch creation.** There are zero exceptions.

### Step 3: Merge Workflow — `staging` is the gateway to `main`

```
feature branch  →  staging  →  main
```

1. **Work on your feature branch** (`feat/...`, `fix/...`, etc.)
2. **When done**, merge into `staging`:
   ```bash
   git checkout staging
   git merge feat/your-branch
   ```
3. **Run ALL checks on staging:**
   ```bash
   ruff check kg_engine/
   python -m pytest kg_engine/tests/ -v
   ```
4. **If checks pass** → ask a human for approval to merge into `main`
5. **Only with explicit human approval** → merge into `main`:
   ```bash
   git checkout main
   git merge staging
   ```

**NEVER merge into `main` without:**
- [ ] All checks passed on `staging`
- [ ] Explicit human approval
- [ ] Review of `git diff staging...main`

### Branch Naming (STRICT)

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feat/<module>-<short-desc>` | `feat/domain-add-crystal-structure` |
| Fix | `fix/<module>-<short-desc>` | `fix/services-null-check-hypothesis` |
| Refactor | `refactor/<module>-<short-desc>` | `refactor/repositories-neo4j-to-async` |
| Docs | `docs/<short-desc>` | `docs/update-api-examples` |
| Test | `test/<module>-<short-desc>` | `test/services-add-ingestion-coverage` |
| Hotfix | `hotfix/<short-desc>` | `hotfix/fix-neo4j-connection-crash` |

**Module names:** `domain`, `repositories`, `services`, `agents`, `api`, `ingestion`, `llm_core`, `config`

**Rules:**
- Use kebab-case: `add-neo4j-connection` NOT `addNeo4jConnection`
- Max 3 words after module prefix
- NEVER use random hash suffixes

### What You MUST Do

- [ ] Read `TEAM_STATUS.md` first — check for conflicting tasks
- [ ] Ask human their role and task
- [ ] Read `AGENTS.md` before starting
- [ ] Verify you are on a feature branch (not main/master)
- [ ] Update `TEAM_STATUS.md` when starting and finishing work
- [ ] When done: merge to `staging`, run checks, ask human for `main` merge
- [ ] Keep changes minimal and focused on the task

### What You MUST NOT Do

- [ ] NEVER work directly on `main` or `master`
- [ ] NEVER force push (`git push --force`)
- [ ] NEVER `git reset --hard`
- [ ] NEVER merge into `main` without human approval
- [ ] NEVER duplicate work from other team members
- [ ] NEVER start work without reading `TEAM_STATUS.md`
- [ ] NEVER delete files unless explicitly told
- [ ] NEVER modify `.gitignore`, `.env`, secrets, or CI config
- [ ] NEVER commit or push unless a human explicitly asks
- [ ] NEVER install new dependencies without approval
- [ ] NEVER create new files unless the task requires it

### Critical Thinking — do NOT be a yes-man (MANDATORY)

**The agent is a teammate, not a servant:**

- If unsure → say so. Never guess, never assume.
- If the human is wrong → correct them. Show weak spots in their reasoning.
- If a suggestion brings no real value → say so. Don't implement useless things.
- Skip empty compliments. No "great question!" — get to the point.
- Before implementing → grep/glob for existing code. If it exists, reuse it.
- Don't think you're smarter than everyone. Verify, don't assume.
- Check ALL code before claiming it works. Read it. Trace the logic.
- If the human asks for something harmful → refuse and explain why.

**Before writing ANY code:**
1. Grep/glob for existing implementations
2. Read the relevant modules
3. If similar code exists → tell human, suggest reusing/extending
4. If new code needed → explain why existing code doesn't cover it

**When the human proposes a change:**
- Does this actually solve the problem?
- What breaks, what's missing, what's redundant?
- "This will work because X, but consider Y risk"
- If bad idea: "I don't recommend this because [reason]. Consider [alternative]"

### Emergency Protocol

If you accidentally made changes on `main`:
1. `git stash` immediately
2. `git checkout -b rescue/<description>`
3. `git stash pop`
4. `git add -A && git commit -m "rescue: <description>"`
5. Tell the human what happened

### Commit Convention

Only commit when explicitly asked. Use conventional format:
```
feat: add new feature
fix: resolve bug
refactor: simplify logic
docs: update documentation
test: add test coverage
```

---

**Remember: You are an assistant, not the owner. `main` is sacred — merge only with human approval via `staging`.**
