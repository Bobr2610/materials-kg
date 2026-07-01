# Claude Code Instructions — Materials KG

## AUTOMATIC: Rules Display + MiMo Check

**At the START of EVERY conversation:**

1. Display this block BEFORE any other output:
```
=== ПРАВИЛА РАБОТЫ С РЕПОЗИТОРИЕМ ===
1. Никогда не работай на main/master — создавай feature-ветку
2. Ветки: feat/<модуль>-<описание>, fix/<модуль>-<описание>
3. Мерж: feature → staging → main (только с согласия человека)
4. Прочитай TEAM_STATUS.md — проверь задачи других участников
5. Обновляй TEAM_STATUS.md при начале и завершении работы
6. Никогда не коммить/пушь без явного запроса человека
7. Используй Docker: docker compose up -d
=== КОНЕЦ ПРАВИЛ ===
```

2. Check MiMo: `mimo --help 2>$null; mimo providers whoami 2>$null`
3. Read `TEAM_STATUS.md`, show status, ask user role and task

## Branch Enforcement

- NEVER work on main/master
- Create: `git checkout -b feat/<module>-<desc>`
- Modules: domain, repositories, services, agents, api, ingestion, llm_core, config

## Merge Workflow

```
feature branch → staging → main
```

1. Work on feature branch
2. Merge to staging, run lint + tests
3. Ask human for approval
4. Only then merge to main

## Mandatory Skills

Read these when needed:

| Skill | When |
|-------|------|
| `docker-workflow` | Running app, testing |
| `mimo-subagent` | Delegating to MiMo |
| `team-coordination` | Starting work |
| `critical-thinking` | Before coding |
| `code-style` | Writing Python |

## Prohibited

- `git push --force`, `git reset --hard` — NEVER
- Merge to main without human approval — NEVER
- Auto-commit without user request — NEVER
- MiMo in project root — NEVER
- Hardcode secrets — NEVER

## MiMo Quick Reference

```bash
# Check availability
mimo --help

# Work tree pattern
$wt = ".mimo-worktrees/<slug>"
New-Item -ItemType Directory -Force -Path $wt
Copy-Item "file.py" "$wt/"
mimo run -m "mimo/mimo-auto" "task. Files in: $wt"
Remove-Item -Recurse -Force $wt

# Call
mimo run -m "mimo/mimo-auto" "Your task"
```

## Docker Quick Reference

```bash
docker compose up -d --build    # start/rebuild
docker compose ps               # status
docker compose logs -f          # logs
docker compose down             # stop
```
