# Architecture Discussion — Materials Knowledge Graph

> **⚠️ This is `materials-kg` repository. References to source codebases below are generic examples — comparisons with those projects informed decisions. This repo is fully standalone under `kg_engine/`.**

> **Date:** 2026-06-26  
> **Context:** Выбор архитектуры для материаловедческого knowledge graph  
> **Participants:** Agent + User

---

## Decision: Hybrid Graph + Vector Search

**Problem:** Нужна система, которая отвечает на вопросы вида «что делали по сплаву X при режиме Y и какой эффект на свойство Z».

**Options considered:**

| Approach | Pros | Cons |
|----------|------|------|
| Pure RAG (vector search only) | Уже есть инфраструктура | Не связывает сущности, нет графовых запросов |
| Pure Graph DB (Neo4j) | Естественные графовые запросы | Нужен отдельный сервер, нет текстового поиска |
| **Hybrid (NetworkX + ChromaDB)** | **Лучшее из двух миров, in-memory, портативно** | **NetworkX не production-ready** |

**Decision:** Гибрид — NetworkX in-memory для прототипа, ChromaDB для текстового поиска. Замена NetworkX на Neo4j в фазе 3.

---

## Decision: Entity Extraction Strategy

**Problem:** Как извлекать сущности (материалы, свойства, режимы) из текстов статей?

**Options considered:**

| Approach | Pros | Cons |
|----------|------|------|
| Regex only | Быстро, 0 latency | Только грубые паттерны |
| LLM only | Точное извлечение | Медленно, дорого |
| **Regex → LLM fallback** | **Быстрый path для грубого, LLM для точного** | **Сложнее реализация** |

**Decision:** Двухуровневое извлечение: regex для быстрого поиска материалов/свойств, LLM для точного структурированного извлечения с падением на regex при ошибке LLM.

---

## Decision: Tool Pattern

**Problem:** Как интегрировать графовые запросы в существующего LangChain-агента?

**Decision:** Использовать `@tool` декоратор с Pydantic `args_schema` (паттерн из исходного agent-проекта). 5 tools:
1. `query_material` — основной запрос по материалу и режиму
2. `query_property` — поиск по свойству с фильтром значений
3. `query_related` — связанные сущности через BFS
4. `graph_data_gaps` — анализ пробелов
5. `graph_stats` — статистика

---

## Decision: Data Gap Analysis

**Problem:** Как определить, каких данных не хватает?

**Approach:** Сравнение известных типов свойств и режимов с теми, что привязаны к каждому материалу. Если материал не имеет эксперимента в каком-то режиме — это пробел.

```python
gaps = pipeline.find_gaps()
# Returns: [{"type": "missing_mode", "material": "Ti6Al4V", "missing": "annealing"}, ...]
```

---

## References

- Source RAG project: `rag_engine/` — RAG pipeline, ChromaDB storage (for reference)
- Source agent project: `agent_ng/` — LangChain agent, tools, streaming (for reference)
- NetworkX docs: https://networkx.org/documentation/stable/
- Pydantic v2: https://docs.pydantic.dev/latest/
