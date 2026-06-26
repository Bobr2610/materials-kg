# Knowledge Graph — Полный план реализации графового модуля

> **Created:** 2026-06-26
> **Status:** Approved — Phase 1 complete
> **Goal:** Построить гибридный knowledge graph для материаловедения: извлечение сущностей из текстов, графовое хранение, семантический поиск, анализ пробелов
> **Git log:** `git log --oneline | head -5`

---

## Executive Summary

Система связывает статьи, эксперименты, материалы, свойства, режимы, установки, исследовательские команды и выводы в единый граф. Отвечает на вопросы вида «что делали по сплаву X при режиме Y и какой эффект на свойство Z», показывает связанные сущности, историю решений и пробелы в данных.

### Архитектура решения

```
Документы → EntityExtractor (regex → LLM) → KnowledgeGraphBuilder → GraphStore (NetworkX) → JSON
                                                                                            ↓
Вопрос пользователя → KnowledgeGraphQuery / HybridSearch → ответ + связанные сущности + пробелы
```

### Ключевые решения

| Решение | Выбор | Обоснование |
|---------|-------|-------------|
| Графовое хранилище | NetworkX (in-memory) | Прототип, не требует БД, JSON-сериализация, замена на Neo4j позже |
| Извлечение сущностей | Regex → LLM fallback | Быстрый regex для грубого поиска, LLM для точного извлечения |
| Поиск | Гибридный (векторный + графовый) | RAG для текста, граф для связей |
| Формат | JSON | Портативность, совместимость с любым графовым БД |

---

## Phase 1: Core Graph Module ✅ (COMPLETE)

### 1.1 Schemas — `kg_engine/graph/schemas.py`

**Сущности (EntityType):**
- `MATERIAL` — металлы, сплавы, керамика, полимеры, композиты
- `PROPERTY` — механические, тепловые, электрические, физические свойства
- `EXPERIMENT` — название теста, описание эксперимента
- `MODE` — режим обработки (термообработка, деформация), условия теста
- `EQUIPMENT` — устройства, машины, инструменты, приборы
- `TEAM` — исследовательские группы, лаборатории, университеты
- `ARTICLE` — публикации, отчёты, документы
- `CONCLUSION` — результаты, выводы, наблюдения

**Связи (RelationType):**
- `HAS_PROPERTY` — material → property (с value/unit)
- `USED_IN` — material → experiment
- `MEASURES` — experiment → property
- `USES_EQUIPMENT` — experiment → equipment
- `HAS_MODE` — material/experiment → mode
- `CONDUCTED_BY` — experiment → team
- `DESCRIBED_IN` → experiment → article
- `HAS_CONCLUSION` → experiment → conclusion
- `DEPENDS_ON`, `COMPOSED_OF`, `COMPARED_TO`, `OPTIMIZED_FOR`

**Pydantic модели:**
```python
class GraphEntity(BaseModel):
    id: str; type: EntityType; name: str
    aliases: list[str]; properties: dict[str, Any]
    source: str | None; confidence: float

class GraphRelation(BaseModel):
    source_id: str; target_id: str; type: RelationType
    properties: dict[str, Any]; source: str | None; confidence: float
```

### 1.2 Store — `kg_engine/graph/store.py`

Thread-safe NetworkX MultiDiGraph с JSON-сериализацией.

**API:**
- `add_entity(entity) / remove_entity(id) / get_entity(id)`
- `find_entities(type, name_contains, limit)`
- `add_relation(relation) / get_relations(entity_id, type)`
- `get_neighbors(entity_id, relation_type, max_depth)` — BFS-обход
- `find_path(source_id, target_id)` — поиск пути (nx.all_simple_paths)
- `find_data_gaps()` — отсутствующие комбинации material-mode и material-property
- `to_json() / from_json() / save(path) / load(path)`

### 1.3 Extractor — `kg_engine/graph/extractor.py`

Двухуровневое извлечение:
1. **Regex** — быстрый поиск материалов (Ti6Al4V, Al2O3) и свойств (прочность, hardness)
2. **LLM** — структурированный JSON с сущностями и связями через промпт

**LLM Prompt:**
```
Ты — экстрактор материаловедческих сущностей.
Извлеки сущности (material, property, experiment, mode, equipment, team, article, conclusion)
и связи (has_property, used_in, measures, uses_equipment, has_mode, conducted_by, described_in, has_conclusion, depends_on, composed_of, compared_to, optimized_for)
из текста ниже.
Верни ТОЛЬКО JSON без markdown-обёртки.
```

### 1.4 Builder — `kg_engine/graph/builder.py`

Преобразует документ в граф: извлекает сущности, создаёт article-entity, связывает всё через `described_in`.

### 1.5 Query — `kg_engine/graph/query.py`

Три основных запроса:
- `query_by_material_and_mode(name, mode)` — свойства, эксперименты, режимы, выводы
- `query_by_property(name, min, max)` — материалы с value-фильтрацией
- `query_related(name, max_depth)` — BFS-обход соседей

### 1.6 Search — `kg_engine/graph/search.py`

Гибрид: результаты векторного поиска (из retrieval) + графовый обход → дедуплицированный топ-K.

### 1.7 Tools — `kg_engine/graph/tools.py`

5 LangChain tools для интеграции с агентом:
1. `query_material(material_name, mode_name)` — основной запрос
2. `query_property(property_name, min_value, max_value)` — фильтр по свойствам
3. `query_related(entity_name, max_depth)` — связанные сущности
4. `graph_data_gaps()` — анализ пробелов
5. `graph_stats()` — статистика графа

### 1.8 Pipeline — `kg_engine/graph/pipeline.py`

Сквозной пайплайн: `GraphPipeline` объединяет store, extractor, builder, query, search.
Методы: `index_document()`, `index_chunks()`, `ask()`, `find_gaps()`, `stats()`, `save()`, `load()`.

### 1.9 Tests — 26 тестов ✅

```
PASSED: TestEntityType, TestRelationType, TestGraphEntity, TestGraphRelation
PASSED: TestGraphStore (add/get/remove/find/count/serialize/stats)
PASSED: TestKnowledgeGraphQuery (by_material, by_property, related)
PASSED: TestEntityExtractor (regex materials, properties, russian)
```

---

## Phase 2: Интеграция с RAG (NEXT)

### 2.1 Векторное индексирование документов
- Использовать существующий `kg_engine/retrieval/` для Chunking + Embedding + ChromaDB
- Параллельно индексировать чанки в векторное хранилище и сущности в граф

### 2.2 Обогащение поиска
- Результаты векторного поиска → извлечение сущностей → дозапрос графа
- Возвращать: текст чанка + связанные сущности + соседей по графу

### 2.3 CLI-скрипт
```bash
python kg_engine/scripts/build_knowledge_graph.py --source chunks.json --output graph.json
```

---

## Phase 3: Продвинутые возможности (FUTURE)

### 3.1 Neo4j storage
- Заменить NetworkX на Neo4j для production
- Cypher-запросы вместо обхода в Python

### 3.2 Визуализация графа
- Gradio UI с визуализацией графа (pyvis/vis-network)
- Интерактивный просмотр связей между сущностями

### 3.3 API endpoints
- FastAPI эндпоинты: POST /graph/query, GET /graph/entity/{id}, GET /graph/gaps
- Интеграция с существующим REST API

---

## Verification Commands

```bash
# Тесты графового модуля
python -m pytest kg_engine/tests/test_graph.py -v

# Все тесты
python -m pytest kg_engine/tests/ -v

# Линтер
ruff check kg_engine/graph/

# Сборка графа из JSON-чанков
python kg_engine/scripts/build_knowledge_graph.py --source data/chunks.json --output data/graph.json
```
