"""Neo4j repository for the graph-first Materials Hypothesis Factory core."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any

from kg_engine.domain.models import CoverageRuleInput
from kg_engine.domain.models import DecisionTrace
from kg_engine.domain.models import Entity
from kg_engine.domain.models import Evidence
from kg_engine.domain.models import Observation
from kg_engine.domain.models import Relation
from kg_engine.domain.models import SearchTextUnit
from kg_engine.domain.models import SourceSpan
from kg_engine.domain.resolution import normalize_name

if TYPE_CHECKING:
    from collections.abc import Callable


logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (set, tuple, frozenset)):
        return [_jsonable(item) for item in value]
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
            "CREATE FULLTEXT INDEX text_unit_fulltext IF NOT EXISTS FOR (n:TextUnit) ON EACH [n.content]",
        ]
        with self._session() as session:
            for statement in statements:
                session.run(statement)

    def upsert_entity(self, entity: Entity) -> Entity:
        payload = self._entity_to_properties(entity)
        self._run(
            """
            MERGE (n:Entity {id: $id})
            SET n += $payload
            RETURN n
            """,
            {"id": entity.id, "payload": payload},
        )
        return self.get_entity(entity.id) or entity

    def get_entity(self, entity_id: str) -> Entity | None:
        rows = self._run(
            "MATCH (n:Entity {id: $id}) RETURN n LIMIT 1",
            {"id": entity_id},
        )
        return self._node_to_entity(rows[0]["n"]) if rows else None

    def find_entities(
        self,
        *,
        kind: str | None = None,
        name: str | None = None,
        ids: list[str] | None = None,
    ) -> list[Entity]:
        where_clauses: list[str] = []
        params: dict[str, Any] = {}
        if kind is not None:
            where_clauses.append("n.kind = $kind")
            params["kind"] = kind
        if ids is not None:
            where_clauses.append("n.id IN $ids")
            params["ids"] = ids
        where = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        query = f"MATCH (n:Entity){where} RETURN n"
        rows = self._run(query, params)
        entities = [self._node_to_entity(row["n"]) for row in rows]
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

    def resolve_entity(self, kind: str, raw_name: str) -> Entity | None:
        normalized = normalize_name(raw_name)
        rows = self._run(
            """
            MATCH (n:Entity {kind: $kind})
            WHERE n.normalized_name = $normalized
               OR $normalized IN coalesce(n.normalized_aliases, [])
            RETURN n
            LIMIT 1
            """,
            {"kind": kind, "normalized": normalized},
        )
        if rows:
            return self._node_to_entity(rows[0]["n"])
        matches = self.find_entities(kind=kind, name=raw_name)
        return matches[0] if matches else None

    def upsert_evidence(self, evidence: Evidence) -> Evidence:
        self._run(
            """
            MERGE (n:Evidence {id: $id})
            SET n += $payload
            RETURN n
            """,
            {"id": evidence.id, "payload": self._evidence_to_properties(evidence)},
        )
        return self.get_evidence(evidence.id) or evidence

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        rows = self._run(
            "MATCH (n:Evidence {id: $id}) RETURN n LIMIT 1",
            {"id": evidence_id},
        )
        return self._node_to_evidence(rows[0]["n"]) if rows else None

    def list_evidence(self, evidence_ids: list[str]) -> list[Evidence]:
        if not evidence_ids:
            return []
        rows = self._run(
            "MATCH (n:Evidence) WHERE n.id IN $ids RETURN n",
            {"ids": evidence_ids},
        )
        by_id = {
            evidence.id: evidence
            for evidence in (
                self._node_to_evidence(row["n"]) for row in rows
            )
        }
        return [by_id[item] for item in evidence_ids if item in by_id]

    def list_all_evidence(self) -> list[Evidence]:
        rows = self._run("MATCH (n:Evidence) RETURN n", {})
        return [self._node_to_evidence(row["n"]) for row in rows]

    def upsert_relation(self, relation: Relation) -> Relation:
        rows = self._run(
            """
            MATCH (source:Entity {id: $source_id})
            MATCH (target:Entity {id: $target_id})
            MERGE (source)-[r:KG_RELATION {id: $id}]->(target)
            WITH r, source, target, coalesce(r.evidence_ids, []) AS existing_evidence_ids
            SET r += $payload
            WITH r, source, target, existing_evidence_ids + $new_evidence_ids AS evidence_ids
            SET r.evidence_ids = reduce(
                acc = [],
                evidence_id IN evidence_ids |
                CASE WHEN evidence_id IN acc THEN acc ELSE acc + evidence_id END
            )
            RETURN r, source.id AS source_id, target.id AS target_id
            """,
            {
                "id": relation.id,
                "source_id": relation.source_entity_id,
                "target_id": relation.target_entity_id,
                "payload": self._relation_to_properties(relation),
                "new_evidence_ids": relation.evidence_ids,
            },
        )
        if rows:
            return self._record_to_relation(rows[0])
        return relation

    def list_relations(
        self,
        *,
        entity_id: str | None = None,
        relation_types: list[str] | None = None,
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
        rows = self._run(query, params)
        relations = [self._record_to_relation(row) for row in rows]
        if relation_types is not None:
            allowed = set(relation_types)
            relations = [item for item in relations if item.relation_type in allowed]
        return relations

    def upsert_observation(self, observation: Observation) -> Observation:
        self._run(
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
        where_clauses: list[str] = []
        params: dict[str, Any] = {}
        if material_id is not None:
            where_clauses.append("n.material_id = $material_id")
            params["material_id"] = material_id
        if property_id is not None:
            where_clauses.append("n.property_id = $property_id")
            params["property_id"] = property_id
        if experiment_id is not None:
            where_clauses.append("n.experiment_id = $experiment_id")
            params["experiment_id"] = experiment_id
        if mode_id is not None:
            where_clauses.append("n.mode_id = $mode_id")
            params["mode_id"] = mode_id
        where = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        query = f"MATCH (n:Observation){where} RETURN n"
        rows = self._run(query, params)
        return [self._node_to_observation(row["n"]) for row in rows]

    def upsert_decision_trace(self, trace: DecisionTrace) -> DecisionTrace:
        self._run(
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
        where_clauses: list[str] = []
        params: dict[str, Any] = {}
        if entity_id is not None:
            where_clauses.append("any(eid IN n.entity_ids WHERE eid = $entity_id)")
            params["entity_id"] = entity_id
        if experiment_id is not None:
            where_clauses.append("n.experiment_id = $experiment_id")
            params["experiment_id"] = experiment_id
        where = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        query = f"MATCH (n:DecisionTrace){where} RETURN n"
        rows = self._run(query, params)
        traces = [self._node_to_trace(row["n"]) for row in rows]
        traces.sort(key=lambda item: item.timestamp)
        return traces

    def upsert_coverage_rule(self, rule: CoverageRuleInput) -> CoverageRuleInput:
        self._run(
            """
            MERGE (n:CoverageRule {rule_id: $rule_id})
            SET n += $payload
            RETURN n
            """,
            {
                "rule_id": rule.rule_id,
                "payload": _neo4j_properties(_jsonable(rule.model_dump(mode="json"))),
            },
        )
        return rule

    def list_coverage_rules(self) -> list[CoverageRuleInput]:
        rows = self._run("MATCH (n:CoverageRule) RETURN n", {})
        rules = []
        for row in rows:
            data = dict(row["n"])
            _decode_json_fields(data, "metadata")
            rules.append(CoverageRuleInput.model_validate(data))
        return rules

    def upsert_text_unit(self, text_unit: SearchTextUnit) -> SearchTextUnit:
        self._run(
            """
            MERGE (n:TextUnit {id: $id})
            SET n += $payload
            RETURN n
            """,
            {"id": text_unit.id, "payload": self._text_unit_to_properties(text_unit)},
        )
        return text_unit

    def batch_upsert_entities(self, entities: list[Entity]) -> list[Entity]:
        if not entities:
            return []
        batch = [
            {"id": e.id, "payload": self._entity_to_properties(e)}
            for e in entities
        ]
        self._run(
            """
            UNWIND $batch AS row
            MERGE (n:Entity {id: row.id})
            SET n += row.payload
            """,
            {"batch": batch},
        )
        return entities

    def batch_upsert_observations(self, observations: list[Observation]) -> list[Observation]:
        if not observations:
            return []
        batch = [
            {
                "id": obs.id,
                "payload": self._observation_to_properties(obs),
                "material_id": obs.material_id,
                "property_id": obs.property_id,
                "experiment_id": obs.experiment_id,
                "mode_id": obs.mode_id,
                "evidence_id": obs.evidence_id,
            }
            for obs in observations
        ]
        self._run(
            """
            UNWIND $batch AS row
            MERGE (n:Observation {id: row.id})
            SET n += row.payload
            WITH n, row
            OPTIONAL MATCH (m:Entity {id: row.material_id})
            OPTIONAL MATCH (p:Entity {id: row.property_id})
            OPTIONAL MATCH (e:Entity {id: row.experiment_id})
            OPTIONAL MATCH (mode:Entity {id: row.mode_id})
            OPTIONAL MATCH (ev:Evidence {id: row.evidence_id})
            FOREACH (_ IN CASE WHEN m IS NULL THEN [] ELSE [1] END | MERGE (n)-[:OBSERVED_MATERIAL]->(m))
            FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | MERGE (n)-[:OBSERVED_PROPERTY]->(p))
            FOREACH (_ IN CASE WHEN e IS NULL THEN [] ELSE [1] END | MERGE (n)-[:OBSERVED_IN]->(e))
            FOREACH (_ IN CASE WHEN mode IS NULL THEN [] ELSE [1] END | MERGE (n)-[:OBSERVED_MODE]->(mode))
            FOREACH (_ IN CASE WHEN ev IS NULL THEN [] ELSE [1] END | MERGE (n)-[:SUPPORTED_BY]->(ev))
            """,
            {"batch": batch},
        )
        return observations

    def batch_upsert_traces(self, traces: list[DecisionTrace]) -> list[DecisionTrace]:
        if not traces:
            return []
        batch = [
            {"id": t.id, "payload": self._trace_to_properties(t)}
            for t in traces
        ]
        self._run(
            """
            UNWIND $batch AS row
            MERGE (n:DecisionTrace {id: row.id})
            SET n += row.payload
            """,
            {"batch": batch},
        )
        return traces

    def batch_upsert_evidence(self, evidence_list: list[Evidence]) -> list[Evidence]:
        if not evidence_list:
            return []
        batch = [
            {"id": ev.id, "payload": self._evidence_to_properties(ev)}
            for ev in evidence_list
        ]
        self._run(
            """
            UNWIND $batch AS row
            MERGE (n:Evidence {id: row.id})
            SET n += row.payload
            """,
            {"batch": batch},
        )
        return evidence_list

    def batch_upsert_relations(self, relations: list[Relation]) -> list[Relation]:
        if not relations:
            return []
        batch = [
            {
                "id": r.id,
                "source_id": r.source_entity_id,
                "target_id": r.target_entity_id,
                "payload": self._relation_to_properties(r),
                "new_evidence_ids": r.evidence_ids,
            }
            for r in relations
        ]
        self._run(
            """
            UNWIND $batch AS row
            MATCH (source:Entity {id: row.source_id})
            MATCH (target:Entity {id: row.target_id})
            MERGE (source)-[r:KG_RELATION {id: row.id}]->(target)
            WITH r, row, coalesce(r.evidence_ids, []) AS existing_evidence_ids
            SET r += row.payload
            WITH r, existing_evidence_ids + row.new_evidence_ids AS evidence_ids
            SET r.evidence_ids = reduce(
                acc = [],
                evidence_id IN evidence_ids |
                CASE WHEN evidence_id IN acc THEN acc ELSE acc + evidence_id END
            )
            """,
            {"batch": batch},
        )
        return relations

    def batch_upsert_text_units(self, text_units: list[SearchTextUnit]) -> list[SearchTextUnit]:
        if not text_units:
            return []
        batch = [
            {"id": tu.id, "payload": self._text_unit_to_properties(tu)}
            for tu in text_units
        ]
        self._run(
            """
            UNWIND $batch AS row
            MERGE (n:TextUnit {id: row.id})
            SET n += row.payload
            """,
            {"batch": batch},
        )
        return text_units

    def search_text_units(self, query: str, *, limit: int = 5) -> list[SearchTextUnit]:
        terms = [term.lower() for term in query.split() if len(term) > 2]
        if not terms:
            terms = [query.lower()]
        fulltext_query = " OR ".join(terms)
        try:
            rows = self._run(
                """
                CALL db.index.fulltext.queryNodes('text_unit_fulltext', $fulltext_query)
                YIELD node AS n, score
                RETURN n
                LIMIT $limit
                """,
                {"fulltext_query": fulltext_query, "limit": limit},
            )
            if rows:
                return [self._node_to_text_unit(row["n"]) for row in rows]
        except Exception:
            logger.debug("Neo4j fulltext text-unit search failed", exc_info=True)
        rows = self._run(
            """
            MATCH (n:TextUnit)
            WHERE toLower(n.content) CONTAINS toLower($text_query)
               OR any(term IN $terms WHERE toLower(n.content) CONTAINS term)
            RETURN n
            LIMIT $limit
            """,
            {
                "text_query": query,
                "terms": terms,
                "limit": limit,
            },
        )
        text_results = [self._node_to_text_unit(row["n"]) for row in rows]
        try:
            all_rows = self._run(
                "MATCH (n:TextUnit) WHERE n.embedding IS NOT NULL RETURN n",
                {},
            )
        except Exception:
            return text_results
        if not all_rows:
            return text_results
        query_embedding = self._compute_query_embedding(query)
        if query_embedding is None:
            return text_results
        cosine_results: list[tuple[float, SearchTextUnit]] = []
        for row in all_rows:
            unit = self._node_to_text_unit(row["n"])
            if unit.embedding is None:
                continue
            similarity = _cosine_similarity(query_embedding, unit.embedding)
            if similarity > 0.1:
                cosine_results.append((similarity, unit))
        cosine_results.sort(key=lambda item: item[0], reverse=True)
        seen_ids = {unit.id for unit in text_results}
        for _sim, unit in cosine_results:
            if unit.id not in seen_ids:
                text_results.append(unit)
                seen_ids.add(unit.id)
        return text_results[:limit]

    def list_text_units(self) -> list[SearchTextUnit]:
        rows = self._run("MATCH (n:TextUnit) RETURN n", {})
        return [self._node_to_text_unit(row["n"]) for row in rows]

    def _compute_query_embedding(self, query: str) -> list[float] | None:
        try:
            from kg_engine.config.settings import settings
            from kg_engine.llm_core.provider import create_provider_from_settings

            provider = create_provider_from_settings(settings)
            if provider is None:
                return None
            embeddings = provider.embed([query])
            if embeddings and embeddings[0]:
                return embeddings[0]
        except Exception:
            pass
        return None

    def _session(self) -> Any:
        if self._database:
            return self._driver.session(database=self._database)
        return self._driver.session()

    def _run(self, query: str, params: dict[str, Any]) -> list[Any]:
        with self._session() as session:
            result = session.run(query, **params)
            return list(result)

    def batch_run(self, operations: list[tuple[str, dict[str, Any]]]) -> list[list[Any]]:
        """Execute multiple Cypher operations in a single transaction."""
        if not operations:
            return []
        with self._session() as session, session.begin_transaction() as tx:
            results: list[list[Any]] = []
            for query, params in operations:
                result = tx.run(query, **params)
                results.append(list(result))
            tx.commit()
            return results

    def _entity_to_properties(self, entity: Entity) -> dict[str, Any]:
        return _neo4j_properties(
            {
                **_jsonable(entity.model_dump(mode="json")),
                "kind": entity.kind,
                "normalized_name": normalize_name(entity.canonical_name),
                "normalized_aliases": [
                    normalize_name(alias) for alias in entity.aliases
                ],
            }
        )

    def _node_to_entity(self, node: Any) -> Entity:
        data = dict(node)
        data.pop("normalized_name", None)
        data.pop("normalized_aliases", None)
        _decode_json_fields(data, "properties")
        return Entity.model_validate(data)

    def _evidence_to_properties(self, evidence: Evidence) -> dict[str, Any]:
        data = evidence.model_dump(mode="json")
        span = data.pop("span")
        return _neo4j_properties(
            {
                **_jsonable(data),
                "span_fragment": span.get("fragment"),
                "span_start_offset": span.get("start_offset"),
                "span_end_offset": span.get("end_offset"),
                "span_row_reference": span.get("row_reference"),
                "span_section": span.get("section"),
            }
        )

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
        data = dict(record["r"])
        data["source_entity_id"] = record["source_id"]
        data["target_entity_id"] = record["target_id"]
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
        self._run("MATCH (n) DETACH DELETE n", {})

    def delete_source(self, source_id: str) -> int:
        rows = self._run(
            """
            MATCH (n:Entity)
            WHERE $sid IN n.source_refs
            RETURN n.id AS id, n.source_refs AS source_refs
            """,
            {"sid": source_id},
        )
        removed = 0
        entity_ids: list[str] = []
        for row in rows:
            refs = list(row.get("source_refs") or [])
            if len(refs) <= 1:
                entity_ids.append(row["id"])
                continue
            new_refs = [ref for ref in refs if ref != source_id]
            self._run(
                "MATCH (n:Entity {id: $id}) SET n.source_refs = $refs",
                {"id": row["id"], "refs": new_refs},
            )
            removed += 1
        removed += len(entity_ids)
        if entity_ids:
            self._run(
                "MATCH (n:TextUnit) WHERE n.source_entity_id IN $ids DETACH DELETE n",
                {"ids": entity_ids},
            )
            self._run(
                "MATCH (n:Observation) WHERE n.experiment_id IN $ids OR n.material_id IN $ids OR n.property_id IN $ids OR n.mode_id IN $ids DETACH DELETE n",
                {"ids": entity_ids},
            )
            self._run(
                "MATCH (n:DecisionTrace) WHERE n.experiment_id IN $ids OR any(eid IN n.entity_ids WHERE eid IN $ids) DETACH DELETE n",
                {"ids": entity_ids},
            )
            self._run(
                "MATCH ()-[r:KG_RELATION]->() WHERE r.source_entity_id IN $ids OR r.target_entity_id IN $ids DELETE r",
                {"ids": entity_ids},
            )
            self._run(
                "MATCH (n:Entity) WHERE n.id IN $ids DETACH DELETE n",
                {"ids": entity_ids},
            )
        self._run(
            "MATCH (n:Evidence) WHERE n.source_id = $sid DETACH DELETE n",
            {"sid": source_id},
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
