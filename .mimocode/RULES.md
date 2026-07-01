# MiMoCode Rules — Materials KG

**Этот файл читается MiMoCode ПЕРВЫМ ДЕЛОМ при старте сессии.**

---

## 1. Источник правил

**`AGENTS.md`** — source of truth. Все правила оттуда.
Этот файл — MiMoCode-специфичные дополнения и упрощения.

---

## 2. Pre-Flight Gate (ВСЕГДА ПЕРЕД РАБОТОЙ)

```
1. git fetch origin
2. git log origin/master..origin/staging → staging впереди?
3. Ветка от staging (или от master если master впереди)
4. TEAM_STATUS.md прочитан
5. MiMo check: mimo --help + mimo providers whoami → показать статус
6. Нет коммитов без запроса человека
7. Нет push без согласия
8. Перед merge в master — спроси человека
```

**Нарушение gate = стоп.**

---

## 3. Git Flow

```
feature → staging → master
         ↑           ↑
     push только   push только
     с согласия    после вопроса
```

- Ветка от `origin/staging` (по умолчанию)
- Коммиты в feature, мерж в staging, мерж в master
- **Перед merge в master = ВСЕГДА спроси "Точно смержить?"**
- Не работай на master/staging напрямую

---

## 4. Message Clarification

Если сообщение длинное (>3 строк), неформальное ("бро", сленг) или запутанное:
1. Не начинай выполнение
2. Переформулируй: "Ты написал X, я понял так: Y"
3. Покажи пользователю
4. Дождись подтверждения
5. Только потом работай

Когда НЕ нужно: короткие команды, вопросы, продолжение задачи.

---

## 5. TDD: ТЕСТ → КОД → РЕФАКТОРИНГ

```
1. Напиши ТЕСТ (красный — падает)
2. Напиши КОД (зелёный — проходит)
3. Рефактори (оставайся зелёным)
```

- **Permanent** (`test_*.py`) — навсегда, не удалять
- **Temporary** (`test_tmp_*.py`) — удалить после задачи
- Один тест = одно поведение
- После добавления теста — обнови `python_files` в `pyproject.toml`

---

## 6. Plan Files

- Планы в `.plans/YYYYMMDD-<topic>.md`
- Не коммить планы (в .gitignore)
- После реализации можно удалить

---

## 7. ARCHITECTURE.md

При изменении файловой структуры — обнови `docs/ARCHITECTURE.md` в том же коммите.

---

## 8. .env.example

При изменении `.env.example` — сравни с `.env`, покажи недостающие, предложи добавить.

---

## 9. MiMoCode-Specific

### Skill Tool
Для загрузки скиллов используй `skill({ name: "..." })`.

### Workflow Tool
Для сложных задач используй `workflow()`:
```javascript
workflow({ operation: "run", name: "compose", args: { task: "..." } })
workflow({ operation: "run", name: "deep-research", args: "..." })
```

### Actor Tool
Для параллельных задач используй `actor()` с subagent_type.

### Plan Mode
Для не-trivial задач входи в plan mode: `plan_enter()` → исследуй → `plan_exit()`.

---

## 10. Запрещено

- `git push --force`
- `git reset --hard`
- Работа на master без feature-ветки
- Коммиты без запроса
- Push без согласия
- Merge в master без вопроса "Точно смержить?"
- Хардкод секретов
- Temporary тесты в коммите
- Код без теста

---

## 11. Чеклист при старте сессии

```
=== MiMoCode SESSION START ===

1. git fetch origin
2. git branch → на staging? master? → создать feature если нужно
3. Прочитай AGENTS.md (если не в контексте)
4. Прочитай TEAM_STATUS.md
5. MiMo check: mimo --help
6. Покажи статус пользователю

=== READY ===
```
