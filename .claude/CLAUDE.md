# Claude Code Instructions — Materials KG

## AUTOMATIC: Rules Display + MiMo Check

**At the START of EVERY conversation:**

1. Display this block BEFORE any other output:
```
=== ПРАВИЛА РАБОТЫ С РЕПОЗИТОРИЕМ ===
1. Никогда не работай на main/master — создавай feature-ветку
2. Ветки: feat/<модуль>-<описание>, fix/<модуль>-<описание>
3. Мерж: feature → staging → PR → master (только с согласия человека)
4. Прочитай TEAM_STATUS.md — проверь задачи других участников
5. Обновляй TEAM_STATUS.md при начале и завершении работы
6. Никогда не коммить/пушь без явного запроса человека
7. Используй Docker: docker compose up -d
8. **Feature-ветки НЕ пушатся на GitHub** — только staging → PR → master
=== КОНЕЦ ПРАВИЛ ===
```

2. **MiMo Check (ОБЯЗАТЕЛЕН):**
```bash
mimo --help
mimo providers whoami
```
Покажи результат:
```
=== MiMo Status ===
CLI: [available / not found]
Provider: [logged in / not logged in / error]
Model: mimo/mimo-auto (default)
====================
```
Если MiMo недоступен — предупреди и продолжай без delegation.

3. Read `TEAM_STATUS.md`, show status, ask user role and task

## Branch Enforcement

- NEVER work on main/master
- **Branch from staging** (default): `git checkout -b feat/<module>-<desc> origin/staging`
- Only if master is ahead of staging → branch from master: `git checkout -b feat/<module>-<desc> origin/master`
- Check: `git log origin/master..origin/staging`
- Modules: domain, repositories, services, agents, api, ingestion, llm_core, config
- **Feature-ветки НЕ пушатся на GitHub** — только staging → PR → master

## Merge Workflow

```
feature branch (локально) → staging → PR → master
```

1. Work on feature branch locally
2. Merge to staging, run lint + tests
3. Ask human for approval
4. Push staging, create PR staging → master
5. Feature-ветки НЕ пушатся на GitHub — только staging и master

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
- Push feature-ветки (`feat/*`, `fix/*`) на GitHub — NEVER
- MiMo in project root — NEVER
- Hardcode secrets — NEVER

## GitHub Branch Protection

**На GitHub только `master` и `staging`.** Все feature-ветки — локально.

- `feat/*`, `fix/*`, `refactor/*`, `docs/*`, `test/*` — **НЕ пушатся на GitHub**
- Пушь в staging только когда готов к PR
- Из staging — PR в master
- **Удаляй feature-ветки после мержа**

## Message Clarification Rule

**Если сообщение длинное (>3 строк), неформальное ("бро", сленг), или запутанное:**
1. НЕ начинай выполнение
2. Переформулируй в чёткий вид
3. Покажи пользователю
4. Дождись подтверждения
5. Только потом работай

**Когда НЕ нужно уточнять:** короткие команды, вопросы, продолжение задачи.

## MiMo Quick Reference

```bash
# Check availability + login
mimo --help
mimo providers whoami

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
