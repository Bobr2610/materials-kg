# Architecture Guide — Materials Knowledge Graph

> **Цель:** Связать статьи, эксперименты, материалы, свойства, режимы обработки, оборудование, исследовательские команды и выводы в единый граф знаний, чтобы отвечать на вопросы вида *«что уже делали по сплаву X при режиме Y и какой был эффект на свойство Z»*, а также находить пробелы в данных.

---

## 1. Что такое Knowledge Graph и зачем он нужен materials science?

**Проблема.** В материаловедении данные разбросаны: статьи лежат в PDF, эксперименты записаны в Excel, свойства в справочниках. Исследователь тратит часы, чтобы понять: *«а что уже пробовали по этому сплаву? был ли annealing при 800°C? какой эффект на прочность?»*

**Решение — гибридный граф знаний:**
- **Граф (NetworkX):** Хранит сущности (материалы, свойства) и связи между ними (`Ti6Al4V` → *has_property* → `tensile_strength`). Графовые запросы отвечают на *«что с чем связано»*.
- **Векторный поиск (ChromaDB + embeddings):** Ищет по смыслу. Если пользователь спросит *«жаропрочные титановые сплавы»* — найдёт `Ti6Al4V`, `Ti-6242`, `IMI 834`, даже если точное имя не указано.
- **Гибрид:** Оба результата объединяются — граф даёт точные связи, векторный поиск — семантическую близость.

![Архитектура: Documents -> Extraction (Regex + LLM) -> Graph Store (NetworkX) -> Query Engine -> Hybrid Search -> User]

---

## 2. Модель данных: 8 сущностей и 12 отношений

Всё, что есть в материаловедении, укладывается в 8 типов сущностей:

| Сущность | Что это | Пример |
|----------|---------|--------|
| `MATERIAL` | Металл, сплав, керамика, полимер | `Ti6Al4V`, `Al6061`, `Al2O3` |
| `PROPERTY` | Механическое, тепловое, электрическое свойство | `tensile_strength`, `hardness` |
| `EXPERIMENT` | Название или описание испытания | `tensile_test`, `fatigue_test` |
| `MODE` | Режим обработки или условия испытания | `annealing`, `heat_treatment` |
| `EQUIPMENT` | Прибор, установка, инструмент | `SEM`, `XRD`, `tensile_machine` |
| `TEAM` | Исследовательская группа, лаборатория | `MIT_Materials_Lab` |
| `ARTICLE` | Публикация, отчёт, документ | `doi:10.1000/xyz` |
| `CONCLUSION` | Вывод, результат, наблюдение | `Strength increased by 15%` |

И 12 типов отношений, которые их связывают:

```
MATERIAL ──has_property──→ PROPERTY       (сплав имеет свойство)
MATERIAL ──used_in──────→ EXPERIMENT       (сплав использован в эксперименте)
EXPERIMENT ──measures────→ PROPERTY        (эксперимент измеряет свойство)
EXPERIMENT ──uses_equipment→ EQUIPMENT      (эксперимент использует прибор)
MATERIAL ──has_mode──────→ MODE            (сплав обработан в режиме)
EXPERIMENT ──conducted_by→ TEAM            (эксперимент проведён командой)
EXPERIMENT ──described_in→ ARTICLE         (эксперимент описан в статье)
EXPERIMENT ──has_conclusion→ CONCLUSION     (эксперимент дал вывод)
──depends_on──                             (общая зависимость)
MATERIAL ──composed_of──→ MATERIAL         (композит/сплав состоит из)
──compared_to──                            (сравнение между сущностями)
──optimized_for──→ PROPERTY                (оптимизирован под свойство)
```

---

## 3. Компоненты системы (модуль `kg_engine/graph/`)

Система состоит из 9 файлов, каждый отвечает за свою часть конвейера:

```
kg_engine/graph/
  schemas.py    → Pydantic-модели: типы сущностей, отношений, структуры данных
  store.py      → Хранилище графа: NetworkX + JSON (чтение/запись)
  extractor.py  → Извлечение сущностей: regex + LLM
  builder.py    → Построение графа: текст документа → граф
  query.py      → Запросы к графу: по материалу, свойству, связанным сущностям
  search.py     → Гибридный поиск: векторный + графовый
  pipeline.py   → Сквозной пайплайн: index → ask → find_gaps → save/load
  tools.py      → LangChain-инструменты: 5 функций @tool для агента
  __init__.py   → Публичные экспорты
```

### 3.1 `schemas.py` — Модели данных (Pydantic)

Определяет:
- **`EntityType`** — Enum с 8 типами сущностей (`MATERIAL`, `PROPERTY`, …)
- **`RelationType`** — Enum с 12 типами отношений (`HAS_PROPERTY`, `USED_IN`, …)
- **`GraphEntity`** — Pydantic-модель сущности: `id`, `type`, `name`, `aliases`, `properties`, `source`, `confidence`
- **`GraphRelation`** — Pydantic-модель отношения: `source_id`, `target_id`, `type`, `properties`, `source`, `confidence`

**Почему Pydantic?** Валидация на входе, сериализация в JSON, автодополнение в IDE. Все данные проходят через эти модели, поэтому JSON на диске всегда структурно корректен.

### 3.2 `store.py` — Хранилище графа (NetworkX)

Самая важная часть. Это in-memory граф, работающий на NetworkX `MultiDiGraph` (мульти-направленный граф: между двумя узлами может быть несколько рёбер разных типов).

**Что умеет:**
- **Добавлять/получать/удалять** сущности по ID
- **Добавлять связи** между сущностями
- **Искать сущности** по типу или по имени (частичное совпадение)
- **Получать соседей** узла (BFS на глубину N)
- **Находить пути** между двумя узлами
- **Сериализовать** весь граф в JSON и загружать обратно
- **Собирать статистику** (сколько сущностей каждого типа, сколько связей)
- **Находить пробелы** в данных (материалы без свойств, материалы без экспериментов)

**Thread-safe:** На запись используется `threading.Lock`, чтение без блокировки.

**Как хранит данные:** NetworkX хранит узлы и рёбра со словарями атрибутов. Мы сохраняем `entity_type`, `name`, `properties` в атрибуты узла, и `relation_type`, `properties` в атрибуты ребра.

### 3.3 `extractor.py` — Извлечение сущностей (Regex + LLM)

**Двухуровневая стратегия:**

1. **Regex (быстрый путь):** Заранее подготовленные паттерны ищут в тексте:
   - Материалы: `\b(Ti6Al4V|Al6061|Inconel 718|…)\b`
   - Свойства: `\b(tensile strength|hardness|…)\b`
   - Режимы: `\b(annealing|quenching|…)\b`

2. **LLM (точный путь):** Если regex не справился или нужны сложные связи, вызывается LLM с структурированным промптом, который просит вернуть JSON с сущностями и отношениями.

**Как работает:**
- `extract_entities(text)` → возвращает список `GraphEntity`
- `extract_relations(text)` → возвращает список `GraphRelation`
- Если LLM падает — используется только regex

### 3.4 `builder.py` — Построитель графа

Берёт текст документа (или чанка), прогоняет через экстрактор, создаёт сущности и связи, добавляет их в хранилище.

**Процесс:**
1. Получает `ExtractionResult` (сущности + связи из экстрактора)
2. Создаёт `GraphEntity` для каждой сущности
3. Создаёт `GraphRelation` для каждой связи
4. Добавляет сущность `article` для документа
5. Добавляет связь `described_in` для всех сущностей из документа
6. Вызывает `store.add_entity()` и `store.add_relation()` для каждого

### 3.5 `query.py` — Движок запросов

Read-only интерфейс (не меняет граф). Содержит три ключевых метода:

| Метод | Что делает | Пример |
|-------|------------|--------|
| `query_by_material_and_mode(name, mode)` | Ищет материал, собирает все его свойства, эксперименты, режимы, выводы | «Что знаем про Ti6Al4V после annealing?» |
| `query_by_property(name, min, max)` | Ищет свойство, возвращает все материалы, у которых оно измерено (с фильтром по значению) | «Какие сплавы имеют tensile_strength > 800?» |
| `query_related(name, depth)` | BFS-обход графа от сущности на N шагов | «Что связано с Ti6Al4V на 2 шага?» |
| `find_data_gaps()` | Какие материалы не имеют свойств или экспериментов | «Чего не хватает?» |
| `stats()` | Статистика графа | «Сколько материалов, свойств, связей?» |

### 3.6 `search.py` — Гибридный поиск

Объединяет два подхода:
1. **Векторный поиск:** Превращает запрос в embedding (через ChromDB или другую модель), находит семантически близкие документы/сущности
2. **Графовый поиск:** Те же результаты прогоняет через граф, находит связанные сущности
3. **Ранжирование:** Объединяет и сортирует по релевантности

### 3.7 `pipeline.py` — Сквозной пайплайн

Оркестратор, который связывает всё вместе:

```python
pipeline = GraphPipeline()

# 1. Индексация документа
pipeline.index_document("статья.txt")
pipeline.index_chunks(["чанк1", "чанк2"])

# 2. Запрос
result = pipeline.ask(query="Ti6Al4V", mode="annealing")
# → JSON с материалом, свойствами, экспериментами, выводами

# 3. Поиск пробелов
gaps = pipeline.find_gaps()
# → [{"type": "missing_mode", "material": "Ti6Al4V", "missing": "annealing"}, ...]

# 4. Сохранение и загрузка
pipeline.save("graph.json")
pipeline.load("graph.json")

# 5. Статистика
pipeline.stats()
# → {"entities": {"MATERIAL": 42, "PROPERTY": 156, ...}, "relations": 389}
```

### 3.8 `tools.py` — LangChain-инструменты для агента

Пять функций, обёрнутых в `@tool` декоратор с Pydantic-схемой аргументов:

| Инструмент | Назначение | Параметры |
|------------|-----------|-----------|
| `query_material` | Основной запрос по материалу и режиму | `material_name`, `mode_name?` |
| `query_property` | Поиск по свойству с фильтром значений | `property_name`, `min_value?`, `max_value?` |
| `query_related` | Связанные сущности через BFS | `entity_name`, `max_depth` |
| `graph_data_gaps` | Анализ пробелов в данных | (нет параметров) |
| `graph_stats` | Статистика графа | (нет параметров) |

---

## 4. Data Flow: от документа к ответу

```
Документ (PDF/текст)
    │
    ▼
┌─────────────────────────────────────┐
│  extractor.py                       │
│  ┌──────────┐   ┌───────────────┐   │
│  │ Regex    │ → │ LLM (fallback)│   │
│  │ (быстро) │   │ (точно)       │   │
│  └──────────┘   └───────────────┘   │
│  → EntityType, RelationType          │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  builder.py                         │
│  → GraphEntity + GraphRelation       │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  store.py (NetworkX MultiDiGraph)   │
│  → .add_entity() .add_relation()    │
│  → JSON serialization               │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  query.py                           │
│  → query_by_material_and_mode()     │
│  → query_by_property()             │
│  → query_related()                 │
│  → find_data_gaps()                │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  search.py (гибрид)                 │
│  → Vector search (ChromaDB)         │
│  → Graph traversal (NetworkX)       │
│  → Merged results                   │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  tools.py → LangChain Agent         │
│  → query_material()                 │
│  → query_property()                 │
│  → query_related()                  │
│  → graph_data_gaps()                │
│  → graph_stats()                    │
└─────────────────────────────────────┘
    │
    ▼
Пользователь ← (человекочитаемый ответ Markdown)
```

---

## 5. Примеры использования

### 5.1 Собрать граф из документов

```bash
# Из одного JSON-файла с чанками
python kg_engine/scripts/build_knowledge_graph.py \
    --source chunks.json \
    --output graph.json

# С LLM-извлечением (точнее, но дольше)
python kg_engine/scripts/build_knowledge_graph.py \
    --source chunks.json \
    --output graph.json \
    --use-llm
```

### 5.2 Запросить граф из Python

```python
from kg_engine.graph import GraphPipeline

pipeline = GraphPipeline()
pipeline.load("graph.json")

# "Что знаем про Ti6Al4V?"
result = pipeline.ask(query="Ti6Al4V")
# → { "material": "Ti6Al4V", "properties": [...], "experiments": [...], "modes": [...] }

# "А если annealing?"
result = pipeline.ask(query="Ti6Al4V", mode="annealing")

# "Какие сплавы прочнее 800 МПа?"
from kg_engine.graph.query import KnowledgeGraphQuery
query = KnowledgeGraphQuery(store)
results = query.query_by_property("tensile_strength", min_value=800)

# "Какие данные отсутствуют?"
gaps = pipeline.find_gaps()
# → missing material-mode, material-property combinations
```

### 5.3 Через LangChain-агента

```python
from kg_engine.graph.tools import (
    query_material,
    query_property,
    query_related,
    graph_data_gaps,
    graph_stats,
    set_graph_pipeline,
)

set_graph_pipeline(pipeline)

# Теперь агент может вызывать:
# - query_material(material_name="Ti6Al4V")
# - query_property(property_name="hardness", min_value=500)
# - query_related(entity_name="Ti6Al4V", max_depth=2)
# - graph_data_gaps()
# - graph_stats()
```

---

## 6. Расширение системы

### Добавить новый тип сущности
1. Добавить значение в `EntityType` в `schemas.py`
2. Добавить regex-паттерн в `extractor.py`
3. Добавить примеры в промпт LLM

### Добавить новый тип отношения
1. Добавить значение в `RelationType` в `schemas.py`
2. Описать направление и семантику
3. Использовать в `query.py` при фильтрации

### Заменить NetworkX на Neo4j
- Заменить `store.py`: имплементировать тот же интерфейс через `neo4j` driver
- `query.py` не меняется — он работает через интерфейс `GraphStore`
- `search.py` может получить Cypher-запросы

---

## 7. Тестирование

```bash
# Все тесты графового модуля
python -m pytest kg_engine/tests/test_graph.py -v

# Все тесты проекта
python -m pytest kg_engine/tests/ -v
```

Тесты покрывают:
- 8 типов сущностей и их значения
- Создание и валидацию Pydantic-моделей
- Все CRUD-операции хранилища (добавить, получить, удалить, найти)
- Сериализацию/десериализацию (JSON roundtrip)
- Пути между узлами (BFS)
- Три метода запросов (by material+mode, by property, related)
- Regex-извлечение на русском и английском

---

## 8. Глоссарий

| Термин | Значение |
|--------|---------|
| **Knowledge Graph** | Графовая база, где узлы — сущности, рёбра — отношения между ними |
| **Entity** | Сущность (материал, свойство, эксперимент, …) |
| **Relation** | Отношение между двумя сущностями (has_property, used_in, …) |
| **NetworkX** | Python-библиотека для работы с графами (in-memory) |
| **ChromaDB** | Векторная БД для семантического поиска |
| **Embedding** | Числовое представление текста (вектор), где близкие по смыслу тексты имеют близкие вектора |
| **Hybrid Search** | Комбинация векторного (семантического) и графового (структурного) поиска |
| **Pydantic** | Python-библиотека для валидации данных через аннотации типов |
| **BFS** | Breadth-First Search (поиск в ширину) — обход графа от узла по уровням |
| **Regex** | Regular Expression — шаблон для поиска текста по паттерну |
| **LLM Fallback** | Стратегия: сначала быстрый regex, если не хватило — LLM |
| **Gap Analysis** | Поиск отсутствующих данных (материал без свойства, без эксперимента) |

---

## 9. Связанные файлы

| Файл | Описание |
|------|---------|
| `AGENTS.md` | Полный гайд для агентов (команды, конвенции, правила) |
| `.agents/skills/materials-knowledge-graph/SKILL.md` | Детали домена: все типы, примеры, архитектура |
| `.cursor/rules/materials-kg-agent.mdc` | Правила кодинга для Cursor-агента |
| `kg_engine/scripts/build_knowledge_graph.py` | CLI для сборки графа из JSON-чанков |
| `docs/ARCHITECTURE.md` | Этот файл |
