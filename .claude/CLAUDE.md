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
8. **Master закрыт на GitHub** — push напрямую невозможен, только через PR
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
- **Master закрыт на GitHub** — push напрямую запрещён. Только через Pull Request.

## Merge Workflow

```
feature branch → staging → PR → master
```

1. Work on feature branch
2. Merge to staging, run lint + tests
3. Ask human for approval
4. Create PR staging → master (push в master напрямую запрещён)
5. После мержа PR master обновится автоматически

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

## GitHub Branch Protection

**`master` закрыт на GitHub для прямых коммитов.** Push в master напрямую запрещён.

- Все изменения в master — **только через Pull Request**
- PR из `staging` в `master`
- После мержа staging → master через PR — автоматический push

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
