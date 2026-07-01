---
name: team-coordination
description: Team workflow rules. Use at conversation start to check TEAM_STATUS.md, ask user role, and prevent duplicate work.
---

# Team Coordination

## At Conversation Start

1. Read `TEAM_STATUS.md`
2. Show current team status to user
3. Ask: "What is your role in the team?"
4. Ask: "What task would you like to work on?"
5. Check: does this overlap with other team members?

## Team Roles

| Role | Focus |
|------|-------|
| ML / NLP / Knowledge Graphs | Embeddings, graph algorithms, entity extraction |
| Data Scientist | Metrics, benchmarks, experiments |
| Архитектор | Architecture, API contracts, system design |
| Материаловед | Domain knowledge, scientific accuracy |
| Product | Requirements, user stories, prioritization |

## When Starting Work

Update `TEAM_STATUS.md`:
```markdown
| ML / NLP | YourName | Task description | в работе | feat/your-branch | 2026-07-01 |
```

## When Finishing Work

Move your row to "История выполненных задач", set status to `готово`.

## Rules

1. **NEVER duplicate** work from other team members
2. **ALWAYS read** `TEAM_STATUS.md` before starting
3. **ALWAYS update** `TEAM_STATUS.md` when starting/finishing
4. **NEVER delete** other participants' entries
5. **Statuses:** `открыта` | `в работе` | `ожидает проверки` | `готово` | `заблокировано`
