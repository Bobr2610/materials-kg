"""Neo4j repository for the graph-first Materials Hypothesis Factory core."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any

from kg_engine.domain.models import CoverageRuleInput
from kg_engine.domain.models import DecisionTrace
from kg_engine.domain.models import Entity
from kg_engine.domain.models import EntityKind
from kg_engine.domain.models import Evidence
from kg_engine.domain.models import Observation
from kg_engine.domain.models import Relation
from kg_engine.domain.models import RelationType
from kg_engine.domain.models import SearchTextUnit
from kg_engine.domain.models import SourceSpan
from kg_engine.domain.resolution import normalize_name

if TYPE_CHECKING:
    from collections.abc import Callable


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _neo4j_properties(data: dict[str, Any]) -> dict[str, Any]:
    """Convert domain JSON data into legal Neo4j property values."""
    properties: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict) or (
            isinstance(value, list)
            and any(isinstance(item, dict | list) for item in value)
        ):
            properties[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            properties[key] = value
    return properties


def _decode_json_fields(data: dict[str, Any], *field_names: str) -> dict[str, Any]:
    for field_name in field_names:
        value = data.get(field_name)
        if isinstance(value, str) and value[:1] in {"{", "["}:
            data[field_name] = json.loads(value)
    return data


def _record_value(record: Any, key: str) -> Any:
    if isinstance(record, dict):
        return record[key]
    return record[key]


class Neo4jMaterialsKGRepository:
    """Repository implementation backed by native Neo4j nodes and relationships."""

    def __init__(self, driver: Any, *, database: str | None = None) -> None:
        self._driver = driver
        self._database = database

    def close(self) -> None:
        self._driver.close()

    def ensure_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT evidence_id IF NOT EXISTS FOR (n:Evidence) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT observation_id IF NOT EXISTS FOR (n:Observation) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT trace_id IF NOT EXISTS FOR (n:DecisionTrace) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT text_unit_id IF NOT EXISTS FOR (n:TextUnit) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT coverage_rule_id IF NOT EXISTS FOR (n:CoverageRule) REQUIRE n.rule_id IS UNIQUE",
            "CREATE CONSTRAINT kg_relation_id IF NOT EXISTS FOR ()-[r:KG_RELATION]-() REQUIRE r.id IS UNIQUE",
        ]
        with self._session() as session:
            for statement in statements:
                session.run(statement)

    def upsert_entity(self, entity: Entity) -> Entity:
        payload = self._entity_to_properties(entity)
        self._write(
            """
            MERGE (n:Entity {id: $id})
            SET n += $payload
            RETURN n
            """,
            {"id": entity.id, "payload": payload},
        )
        return self.get_entity(entity.id) or entity

    def get_entity(self, entity_id: str) -> Entity | None:
        rows = self._read(
            "MATCH (n:Entity {id: $id}) RETURN n LIMIT 1",
            {"id": entity_id},
        )
        return self._node_to_entity(_record_value(rows[0], "n")) if rows else None

    def find_entities(
        self,
        *,
        kind: EntityKind | None = None,
        name: str | None = None,
        ids: list[str] | None = None,
    ) -> list[Entity]:
        rows = self._read("MATCH (n:Entity) RETURN n", {})
        entities = [self._node_to_entity(_record_value(row, "n")) for row in rows]
        if kind is not None:
            entities = [entity for entity in entities if entity.kind == kind]
        if ids is not None:
            id_set = set(ids)
            entities = [entity for entity in entities if entity.id in id_set]
        if name is not None:
            normalized = normalize_name(name)
            entities = [
                entity
                for entity in entities
                if normalize_name(entity.canonical_name) == normalized
                or normalized in normalize_name(entity.canonical_name)
                or any(normalized in normalize_name(alias) for alias in entity.aliases)
            ]
        return entities

    def resolve_entity(self, kind: EntityKind, raw_name: str) -> Entity | None:
        normalized = normalize_name(raw_name)
        rows = self._read(
            """
            MATCH (n:Entity {kind: $kind})
            WHERE n.normalized_name = $normalized
               OR $normalized IN coalesce(n.normalized_aliases, [])
            RETURN n
            LIMIT 1
            """,
            {"kind": kind.value, "normalized": normalized},
        )
        if rows:
            return self._node_to_entity(_record_value(rows[0], "n"))
        matches = self.find_entities(kind=kind, name=raw_name)
        return matches[0] if matches else None

    def upsert_evidence(self, evidence: Evidence) -> Evidence:
        self._write(
            """
            MERGE (n:Evidence {id: $id})
            SET n += $payload
            RETURN n
            """,
            {"id": evidence.id, "payload": self._evidence_to_properties(evidence)},
        )
        return self.get_evidence(evidence.id) or evidence

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        rows = self._read(
            "MATCH (n:Evidence {id: $id}) RETURN n LIMIT 1",
            {"id": evidence_id},
        )
        return self._node_to_evidence(_record_value(rows[0], "n")) if rows else None

    def list_evidence(self, evidence_ids: list[str]) -> list[Evidence]:
        if not evidence_ids:
            return []
        rows = self._read(
            "MATCH (n:Evidence) WHERE n.id IN $ids RETURN n",
            {"ids": evidence_ids},
        )
        by_id = {
            evidence.id: evidence
            for evidence in (
                self._node_to_evidence(_record_value(row, "n")) for row in rows
            )
        }
        return [by_id[item] for item in evidence_ids if item in by_id]

    def upsert_relation(self, relation: Relation) -> Relation:
        self._write(
            """
            MATCH (source:Entity {id: $source_id})
            MATCH (target:Entity {id: $target_id})
            MERGE (source)-[r:KG_RELATION {id: $id}]->(target)
            SET r += $payload
            RETURN r
            """,
            {
                "id": relation.id,
                "source_id": relation.source_entity_id,
                "target_id": relation.target_entity_id,
                "payload": self._relation_to_properties(relation),
            },
        )
        matches = self.list_relations(entity_id=relation.source_entity_id)
        return next((item for item in matches if item.id == relation.id), relation)

    def list_relations(
        self,
        *,
        entity_id: str | None = None,
        relation_types: list[RelationType] | None = None,
    ) -> list[Relation]:
        if entity_id is None:
            query = "MATCH (s:Entity)-[r:KG_RELATION]->(t:Entity) RETURN r, s.id AS source_id, t.id AS target_id"
            params: dict[str, Any] = {}
        else:
            query = """
            MATCH (s:Entity)-[r:KG_RELATION]->(t:Entity)
            WHERE s.id = $entity_id OR t.id = $entity_id
            RETURN r, s.id AS source_id, t.id AS target_id
            """
            params = {"entity_id": entity_id}
        rows = self._read(query, params)
        relations = [self._record_to_relation(row) for row in rows]
        if relation_types is not None:
            allowed = set(relation_types)
            relations = [item for item in relations if item.relation_type in allowed]
        return relations

    def upsert_observation(self, observation: Observation) -> Observation:
        self._write(
            """
            MERGE (n:Observation {id: $id})
            SET n += $payload
            WITH n
            OPTIONAL MATCH (m:Entity {id: $material_id})
            OPTIONAL MATCH (p:Entity {id: $property_id})
            OPTIONAL MATCH (e:Entity {id: $experiment_id})
            OPTIONAL MATCH (mode:Entity {id: $mode_id})
            OPTIONAL MATCH (ev:Evidence {id: $evidence_id})
            FOREACH (_ IN CASE WHEN m IS NULL THEN [] ELSE [1] END | MERGE (n)-[:OBSERVED_MATERIAL]->(m))
            FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | MERGE (n)-[:OBSERVED_PROPERTY]->(p))
            FOREACH (_ IN CASE WHEN e IS NULL THEN [] ELSE [1] END | MERGE (n)-[:OBSERVED_IN]->(e))
            FOREACH (_ IN CASE WHEN mode IS NULL THEN [] ELSE [1] END | MERGE (n)-[:OBSERVED_MODE]->(mode))
            FOREACH (_ IN CASE WHEN ev IS NULL THEN [] ELSE [1] END | MERGE (n)-[:SUPPORTED_BY]->(ev))
            RETURN n
            """,
            {
                "id": observation.id,
                "payload": self._observation_to_properties(observation),
                "material_id": observation.material_id,
                "property_id": observation.property_id,
                "experiment_id": observation.experiment_id,
                "mode_id": observation.mode_id,
                "evidence_id": observation.evidence_id,
            },
        )
        return observation

    def list_observations(
        self,
        *,
        material_id: str | None = None,
        property_id: str | None = None,
        experiment_id: str | None = None,
        mode_id: str | None = None,
    ) -> list[Observation]:
        rows = self._read("MATCH (n:Observation) RETURN n", {})
        observations = [self._node_to_observation(_record_value(row, "n")) for row in rows]
        if material_id is not None:
            observations = [item for item in observations if item.material_id == material_id]
        if property_id is not None:
            observations = [item for item in observations if item.property_id == property_id]
        if experiment_id is not None:
            observations = [item for item in observations if item.experiment_id == experiment_id]
        if mode_id is not None:
            observations = [item for item in observations if item.mode_id == mode_id]
        return observations

    def upsert_decision_trace(self, trace: DecisionTrace) -> DecisionTrace:
        self._write(
            """
            MERGE (n:DecisionTrace {id: $id})
            SET n += $payload
            RETURN n
            """,
            {"id": trace.id, "payload": self._trace_to_properties(trace)},
        )
        return trace

    def list_decision_traces(
        self,
        *,
        entity_id: str | None = None,
        experiment_id: str | None = None,
    ) -> list[DecisionTrace]:
        rows = self._read("MATCH (n:DecisionTrace) RETURN n", {})
        traces = [self._node_to_trace(_record_value(row, "n")) for row in rows]
        if entity_id is not None:
            traces = [item for item in traces if entity_id in item.entity_ids]
        if experiment_id is not None:
            traces = [item for item in traces if item.experiment_id == experiment_id]
        traces.sort(key=lambda item: item.timestamp)
        return traces

    def upsert_coverage_rule(self, rule: CoverageRuleInput) -> CoverageRuleInput:
        self._write(
            """
            MERGE (n:CoverageRule {rule_id: $rule_id})
            SET n += $payload
            RETURN n
            """,
            {
                "rule_id": rule.rule_id,
                "payload": _neo4j_properties(
                    _jsonable(rule.model_dump(mode="json"))
                ),
            },
        )
        return rule

    def list_coverage_rules(self) -> list[CoverageRuleInput]:
        rows = self._read("MATCH (n:CoverageRule) RETURN n", {})
        rules = []
        for row in rows:
            data = dict(_record_value(row, "n"))
            _decode_json_fields(data, "metadata")
            rules.append(CoverageRuleInput.model_validate(data))
        return rules

    def upsert_text_unit(self, text_unit: SearchTextUnit) -> SearchTextUnit:
        self._write(
            """
            MERGE (n:TextUnit {id: $id})
            SET n += $payload
            RETURN n
            """,
            {"id": text_unit.id, "payload": self._text_unit_to_properties(text_unit)},
        )
        return text_unit

    def search_text_units(self, query: str, *, limit: int = 5) -> list[SearchTextUnit]:
        rows = self._read(
            """
            MATCH (n:TextUnit)
            WHERE toLower(n.content) CONTAINS toLower($text_query)
               OR any(term IN $terms WHERE toLower(n.content) CONTAINS term)
            RETURN n
            LIMIT $limit
            """,
            {
                "text_query": query,
                "terms": [term.lower() for term in query.split() if len(term) > 2],
                "limit": limit,
            },
        )
        return [self._node_to_text_unit(_record_value(row, "n")) for row in rows]

    def _session(self) -> Any:
        if self._database:
            return self._driver.session(database=self._database)
        return self._driver.session()

    def _read(self, query: str, params: dict[str, Any]) -> list[Any]:
        return self._run(query, params)

    def _write(self, query: str, params: dict[str, Any]) -> list[Any]:
        return self._run(query, params)

    def _run(self, query: str, params: dict[str, Any]) -> list[Any]:
        with self._session() as session:
            result = session.run(query, **params)
            return list(result)

    def _entity_to_properties(self, entity: Entity) -> dict[str, Any]:
        return _neo4j_properties({
            **_jsonable(entity.model_dump(mode="json")),
            "kind": entity.kind.value,
            "normalized_name": normalize_name(entity.canonical_name),
            "normalized_aliases": [normalize_name(alias) for alias in entity.aliases],
        })

    def _node_to_entity(self, node: Any) -> Entity:
        data = dict(node)
        data.pop("normalized_name", None)
        data.pop("normalized_aliases", None)
        _decode_json_fields(data, "properties")
        return Entity.model_validate(data)

    def _evidence_to_properties(self, evidence: Evidence) -> dict[str, Any]:
        data = evidence.model_dump(mode="json")
        span = data.pop("span")
        return _neo4j_properties({
            **_jsonable(data),
            "span_fragment": span.get("fragment"),
            "span_start_offset": span.get("start_offset"),
            "span_end_offset": span.get("end_offset"),
            "span_row_reference": span.get("row_reference"),
            "span_section": span.get("section"),
        })

    def _node_to_evidence(self, node: Any) -> Evidence:
        data = dict(node)
        span = SourceSpan(
            fragment=data.pop("span_fragment", None),
            start_offset=data.pop("span_start_offset", None),
            end_offset=data.pop("span_end_offset", None),
            row_reference=data.pop("span_row_reference", None),
            section=data.pop("span_section", None),
        )
        data["span"] = span
        _decode_json_fields(data, "metadata")
        return Evidence.model_validate(data)

    def _relation_to_properties(self, relation: Relation) -> dict[str, Any]:
        return _neo4j_properties(_jsonable(relation.model_dump(mode="json")))

    def _record_to_relation(self, record: Any) -> Relation:
        data = dict(_record_value(record, "r"))
        data["source_entity_id"] = _record_value(record, "source_id")
        data["target_entity_id"] = _record_value(record, "target_id")
        _decode_json_fields(data, "properties")
        return Relation.model_validate(data)

    def _observation_to_properties(self, observation: Observation) -> dict[str, Any]:
        return _neo4j_properties(_jsonable(observation.model_dump(mode="json")))

    def _node_to_observation(self, node: Any) -> Observation:
        data = dict(node)
        _decode_json_fields(data, "metadata")
        return Observation.model_validate(data)

    def _trace_to_properties(self, trace: DecisionTrace) -> dict[str, Any]:
        return _neo4j_properties(_jsonable(trace.model_dump(mode="json")))

    def _node_to_trace(self, node: Any) -> DecisionTrace:
        data = dict(node)
        _decode_json_fields(data, "metadata")
        return DecisionTrace.model_validate(data)

    def _text_unit_to_properties(self, text_unit: SearchTextUnit) -> dict[str, Any]:
        return _neo4j_properties(_jsonable(text_unit.model_dump(mode="json")))

    def _node_to_text_unit(self, node: Any) -> SearchTextUnit:
        data = dict(node)
        _decode_json_fields(data, "metadata")
        return SearchTextUnit.model_validate(data)

    def clear_all(self) -> None:
        self._write("MATCH (n) DETACH DELETE n", {})

    def delete_source(self, source_id: str) -> int:
        rows = self._read(
            "MATCH (n:Entity) WHERE $sid IN n.source_refs OR n.properties CONTAINS $sid RETURN n.id AS id",
            {"sid": source_id},
        )
        entity_ids = [row["id"] for row in rows]
        removed = len(entity_ids)
        if entity_ids:
            self._write(
                "MATCH (n:Entity) WHERE n.id IN $ids DETACH DELETE n",
                {"ids": entity_ids},
            )
        self._write(
            "MATCH (n:Evidence) WHERE n.source_id = $sid DETACH DELETE n",
            {"sid": source_id},
        )
        self._write(
            "MATCH (n:TextUnit) WHERE n.source_entity_id IN $ids DETACH DELETE n",
            {"ids": entity_ids},
        )
        self._write(
            "MATCH (n:Observation) WHERE n.experiment_id IN $ids OR n.material_id IN $ids DETACH DELETE n",
            {"ids": entity_ids},
        )
        self._write(
            "MATCH (n:DecisionTrace) WHERE n.experiment_id IN $ids DETACH DELETE n",
            {"ids": entity_ids},
        )
        return removed


def create_neo4j_repository(
    *,
    uri: str,
    user: str,
    password: str,
    database: str | None = None,
    driver_factory: Callable[..., Any] | None = None,
) -> Neo4jMaterialsKGRepository:
    """Create a Neo4j repository without importing the driver unless requested."""
    if driver_factory is None:
        from neo4j import GraphDatabase

        driver_factory = GraphDatabase.driver
    driver = driver_factory(uri, auth=(user, password))
    return Neo4jMaterialsKGRepository(driver, database=database)
