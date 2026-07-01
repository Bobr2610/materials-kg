---
name: code-style
description: Python code style and knowledge graph conventions for materials-kg. Use when writing or reviewing Python code.
---

# Code Style & Conventions

## Formatting

- **Ruff (pyproject.toml):** Line length 88, Python 3.11+, double quotes
- **Imports:** standard → third-party → local
- **Type hints:** on ALL function signatures

## Naming

| Element | Convention | Example |
|---------|------------|---------|
| Classes | PascalCase | `MaterialsKGService` |
| Functions | snake_case | `resolve_entity` |
| Variables | snake_case | `entity_id` |
| Constants | UPPER_SNAKE | `MAX_RETRIES` |
| Private | _prefix | `_internal_state` |

## Module Pattern

```python
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

class MyService:
    """Service description."""

    def __init__(self, repo: MaterialsKGRepository) -> None:
        self._repo = repo
```

## Entity Types (8)

`MATERIAL`, `EXPERIMENT`, `PROPERTY`, `MODE`, `EQUIPMENT`, `TEAM`, `DOCUMENT`, `TAG`

## Relation Types (9)

`EVALUATES_MATERIAL`, `USES_MODE`, `MEASURES_PROPERTY`, `USES_EQUIPMENT`, `PERFORMED_BY`, `DOCUMENTED_IN`, `TAGGED_WITH`, `REFERENCES`, `RELATED_TO`

## Error Handling

- No silent exceptions: always log, never `except: pass`
- No hardcoded fallbacks
- Safe defaults: `None`, `[]`, `{}`

## Testing

- **TDD:** тест → код → рефакторинг (никогда код без теста)
- Location: `kg_engine/tests/`
- Test behavior, not implementation
- **Permanent** (`test_*.py`): регрессия, контракты — навсегда
- **Temporary** (`test_tmp_*.py`): отладка, эксперименты — удалить после задачи
- Один тест = одно поведение, не дублируй
- Запуск: `python -m pytest kg_engine/tests/ -v`
- Без tmp: `python -m pytest -m "not tmp" kg_engine/tests/ -v`

## DRY, Lean, Modular, Pythonic
