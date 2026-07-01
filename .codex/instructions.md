# Codex Instructions — Materials KG

## CRITICAL: Read Before ANY Work

You are working in the Materials Knowledge Graph project. These rules protect the repository.

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

### Branch Naming

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feat/<short-desc>` | `feat/add-neo4j-connection` |
| Fix | `fix/<short-desc>` | `fix/null-pointer-in-extraction` |
| Refactor | `refactor/<short-desc>` | `refactor/simplify-repository-layer` |
| Docs | `docs/<short-desc>` | `docs/update-api-examples` |
| Test | `test/<short-desc>` | `test/add-hypothesis-coverage` |

### What You MUST Do

- [ ] Read `AGENTS.md` before starting
- [ ] Verify you are on a feature branch (not main/master)
- [ ] Run linter: `ruff check kg_engine/`
- [ ] Run tests: `python -m pytest kg_engine/tests/ -v`
- [ ] Keep changes minimal and focused on the task

### What You MUST NOT Do

- [ ] NEVER work directly on `main` or `master`
- [ ] NEVER force push (`git push --force`)
- [ ] NEVER `git reset --hard`
- [ ] NEVER delete files unless explicitly told
- [ ] NEVER modify `.gitignore`, `.env`, secrets, or CI config
- [ ] NEVER commit or push unless a human explicitly asks
- [ ] NEVER install new dependencies without approval
- [ ] NEVER create new files unless the task requires it

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

**Remember: You are an assistant, not the owner. Treat the repository as read-only until you create a branch.**
