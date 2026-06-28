"""Postgres + pgvector repository for the graph-first materials KG core."""

from __future__ import annotations

import json
import logging
from datetime import UTC
from datetime import datetime
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
from kg_engine.domain.models import SourceKind
from kg_engine.domain.models import SourceSpan
from kg_engine.domain.resolution import normalize_name

logger = logging.getLogger(__name__)


def _ensure_datetime(value: Any) -> datetime | None:
    """Coerce a database value to an aware UTC datetime, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    return value

POSTGRES_SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kg_entities (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS kg_entity_aliases (
    entity_id TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    PRIMARY KEY (kind, normalized_alias)
);

CREATE TABLE IF NOT EXISTS kg_evidence (
    id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    span JSONB NOT NULL DEFAULT '{}'::jsonb,
    extraction_method TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    version TEXT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS kg_relations (
    id TEXT PRIMARY KEY,
    relation_type TEXT NOT NULL,
    source_entity_id TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    target_entity_id TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS kg_observations (
    id TEXT PRIMARY KEY,
    material_id TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    property_id TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    experiment_id TEXT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    mode_id TEXT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    value DOUBLE PRECISION NULL,
    unit TEXT NULL,
    comparator TEXT NULL,
    evidence_id TEXT NOT NULL REFERENCES kg_evidence(id) ON DELETE CASCADE,
    confidence DOUBLE PRECISION NOT NULL,
    observed_at TIMESTAMPTZ NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS kg_decision_traces (
    id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    decision TEXT NULL,
    entity_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    experiment_id TEXT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    observation_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    changed_from_trace_id TEXT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS kg_coverage_rules (
    rule_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    material_names JSONB NOT NULL DEFAULT '[]'::jsonb,
    mode_names JSONB NOT NULL DEFAULT '[]'::jsonb,
    property_names JSONB NOT NULL DEFAULT '[]'::jsonb,
    scope TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS kg_text_units (
    id TEXT PRIMARY KEY,
    source_entity_id TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    source_kind TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1536),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);
"""


class PostgresMaterialsKGRepository:
    """Repository implementation backed by Postgres and pgvector."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def ensure_schema(self) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(POSTGRES_SCHEMA_SQL)
        self._connection.commit()

    def upsert_entity(self, entity: Entity) -> Entity:
        query = """
        INSERT INTO kg_entities (
            id, kind, canonical_name, normalized_name, aliases, properties,
            source_refs, confidence, created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            canonical_name = EXCLUDED.canonical_name,
            normalized_name = EXCLUDED.normalized_name,
            aliases = COALESCE((
                SELECT jsonb_agg(DISTINCT elem)
                FROM jsonb_array_elements(
                    COALESCE(kg_entities.aliases, '[]'::jsonb)
                    || COALESCE(EXCLUDED.aliases, '[]'::jsonb)
                ) AS elem
            ), '[]'::jsonb),
            properties = kg_entities.properties || EXCLUDED.properties,
            source_refs = COALESCE((
                SELECT jsonb_agg(DISTINCT elem)
                FROM jsonb_array_elements(
                    COALESCE(kg_entities.source_refs, '[]'::jsonb)
                    || COALESCE(EXCLUDED.source_refs, '[]'::jsonb)
                ) AS elem
            ), '[]'::jsonb),
            confidence = GREATEST(kg_entities.confidence, EXCLUDED.confidence),
            updated_at = EXCLUDED.updated_at
        """
        payload = (
            entity.id,
            entity.kind.value,
            entity.canonical_name,
            normalize_name(entity.canonical_name),
            json.dumps(entity.aliases),
            json.dumps(entity.properties),
            json.dumps(entity.source_refs),
            entity.confidence,
            entity.created_at,
            entity.updated_at,
        )
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(query, payload)
                cursor.execute(
                    "DELETE FROM kg_entity_aliases WHERE entity_id = %s",
                    (entity.id,),
                )
                aliases = [entity.canonical_name, *entity.aliases]
                for alias in aliases:
                    cursor.execute(
                        """
                        INSERT INTO kg_entity_aliases(entity_id, kind, alias, normalized_alias)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (kind, normalized_alias) DO UPDATE
                        SET entity_id = EXCLUDED.entity_id, alias = EXCLUDED.alias
                        """,
                        (
                            entity.id,
                            entity.kind.value,
                            alias,
                            normalize_name(alias),
                        ),
                    )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return entity

    def get_entity(self, entity_id: str) -> Entity | None:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT * FROM kg_entities WHERE id = %s", (entity_id,))
            row = cursor.fetchone()
        return None if row is None else self._row_to_entity(row)

    def find_entities(
        self,
        *,
        kind: EntityKind | None = None,
        name: str | None = None,
        ids: list[str] | None = None,
    ) -> list[Entity]:
        clauses = ["TRUE"]
        params: list[Any] = []
        if kind is not None:
            clauses.append("kind = %s")
            params.append(kind.value)
        if name is not None:
            clauses.append(
                "(normalized_name = %s OR id IN ("
                "SELECT entity_id FROM kg_entity_aliases WHERE normalized_alias = %s"
                "))"
            )
            normalized = normalize_name(name)
            params.extend([normalized, normalized])
        if ids is not None:
            clauses.append("id = ANY(%s)")
            params.append(ids)
        query = f"SELECT * FROM kg_entities WHERE {' AND '.join(clauses)}"
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return [self._row_to_entity(row) for row in rows]

    def resolve_entity(self, kind: EntityKind, raw_name: str) -> Entity | None:
        entities = self.find_entities(kind=kind, name=raw_name)
        return entities[0] if entities else None

    def upsert_evidence(self, evidence: Evidence) -> Evidence:
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO kg_evidence (
                        id, source_kind, source_id, span, extraction_method,
                        confidence, version, recorded_at, metadata
                    )
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        span = EXCLUDED.span,
                        extraction_method = EXCLUDED.extraction_method,
                        confidence = GREATEST(kg_evidence.confidence, EXCLUDED.confidence),
                        version = EXCLUDED.version,
                        metadata = kg_evidence.metadata || EXCLUDED.metadata
                    """,
                    (
                        evidence.id,
                        evidence.source_kind.value,
                        evidence.source_id,
                        json.dumps(evidence.span.model_dump()),
                        evidence.extraction_method,
                        evidence.confidence,
                        evidence.version,
                        evidence.recorded_at,
                        json.dumps(evidence.metadata),
                    ),
                )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return evidence

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT * FROM kg_evidence WHERE id = %s", (evidence_id,))
            row = cursor.fetchone()
        return None if row is None else self._row_to_evidence(row)

    def list_evidence(self, evidence_ids: list[str]) -> list[Evidence]:
        if not evidence_ids:
            return []
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM kg_evidence WHERE id = ANY(%s)",
                (evidence_ids,),
            )
            rows = cursor.fetchall()
        return [self._row_to_evidence(row) for row in rows]

    def upsert_relation(self, relation: Relation) -> Relation:
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO kg_relations (
                        id, relation_type, source_entity_id, target_entity_id,
                        evidence_ids, properties, confidence, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        evidence_ids = COALESCE((
                            SELECT jsonb_agg(DISTINCT elem)
                            FROM jsonb_array_elements(
                                COALESCE(kg_relations.evidence_ids, '[]'::jsonb)
                                || COALESCE(EXCLUDED.evidence_ids, '[]'::jsonb)
                            ) AS elem
                        ), '[]'::jsonb),
                        properties = kg_relations.properties || EXCLUDED.properties,
                        confidence = GREATEST(kg_relations.confidence, EXCLUDED.confidence),
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        relation.id,
                        relation.relation_type.value,
                        relation.source_entity_id,
                        relation.target_entity_id,
                        json.dumps(relation.evidence_ids),
                        json.dumps(relation.properties),
                        relation.confidence,
                        relation.created_at,
                        relation.updated_at,
                    ),
                )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return relation

    def list_relations(
        self,
        *,
        entity_id: str | None = None,
        relation_types: list[RelationType] | None = None,
    ) -> list[Relation]:
        clauses = ["TRUE"]
        params: list[Any] = []
        if entity_id is not None:
            clauses.append("(source_entity_id = %s OR target_entity_id = %s)")
            params.extend([entity_id, entity_id])
        if relation_types is not None:
            clauses.append("relation_type = ANY(%s)")
            params.append([item.value for item in relation_types])
        query = f"SELECT * FROM kg_relations WHERE {' AND '.join(clauses)}"
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return [self._row_to_relation(row) for row in rows]

    def upsert_observation(self, observation: Observation) -> Observation:
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO kg_observations (
                        id, material_id, property_id, experiment_id, mode_id,
                        value, unit, comparator, evidence_id, confidence,
                        observed_at, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        value = EXCLUDED.value,
                        unit = EXCLUDED.unit,
                        comparator = EXCLUDED.comparator,
                        confidence = GREATEST(
                            kg_observations.confidence, EXCLUDED.confidence
                        ),
                        observed_at = EXCLUDED.observed_at,
                        metadata = kg_observations.metadata || EXCLUDED.metadata
                    """,
                    (
                        observation.id,
                        observation.material_id,
                        observation.property_id,
                        observation.experiment_id,
                        observation.mode_id,
                        observation.value,
                        observation.unit,
                        observation.comparator,
                        observation.evidence_id,
                        observation.confidence,
                        observation.observed_at,
                        json.dumps(observation.metadata),
                    ),
                )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return observation

    def list_observations(
        self,
        *,
        material_id: str | None = None,
        property_id: str | None = None,
        experiment_id: str | None = None,
        mode_id: str | None = None,
    ) -> list[Observation]:
        clauses = ["TRUE"]
        params: list[Any] = []
        if material_id is not None:
            clauses.append("material_id = %s")
            params.append(material_id)
        if property_id is not None:
            clauses.append("property_id = %s")
            params.append(property_id)
        if experiment_id is not None:
            clauses.append("experiment_id = %s")
            params.append(experiment_id)
        if mode_id is not None:
            clauses.append("mode_id = %s")
            params.append(mode_id)
        query = f"SELECT * FROM kg_observations WHERE {' AND '.join(clauses)}"
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return [self._row_to_observation(row) for row in rows]

    def upsert_decision_trace(self, trace: DecisionTrace) -> DecisionTrace:
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO kg_decision_traces (
                        id, summary, decision, entity_ids, experiment_id,
                        observation_ids, evidence_ids, changed_from_trace_id,
                        timestamp, confidence, metadata
                    )
                    VALUES (
                        %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s::jsonb,
                        %s, %s, %s, %s::jsonb
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        summary = EXCLUDED.summary,
                        decision = EXCLUDED.decision,
                        entity_ids = EXCLUDED.entity_ids,
                        observation_ids = EXCLUDED.observation_ids,
                        evidence_ids = EXCLUDED.evidence_ids,
                        changed_from_trace_id = EXCLUDED.changed_from_trace_id,
                        timestamp = EXCLUDED.timestamp,
                        confidence = GREATEST(
                            kg_decision_traces.confidence, EXCLUDED.confidence
                        ),
                        metadata = kg_decision_traces.metadata || EXCLUDED.metadata
                    """,
                    (
                        trace.id,
                        trace.summary,
                        trace.decision,
                        json.dumps(trace.entity_ids),
                        trace.experiment_id,
                        json.dumps(trace.observation_ids),
                        json.dumps(trace.evidence_ids),
                        trace.changed_from_trace_id,
                        trace.timestamp,
                        trace.confidence,
                        json.dumps(trace.metadata),
                    ),
                )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return trace

    def list_decision_traces(
        self,
        *,
        entity_id: str | None = None,
        experiment_id: str | None = None,
    ) -> list[DecisionTrace]:
        clauses = ["TRUE"]
        params: list[Any] = []
        if entity_id is not None:
            clauses.append("entity_ids @> %s::jsonb")
            params.append(json.dumps([entity_id]))
        if experiment_id is not None:
            clauses.append("experiment_id = %s")
            params.append(experiment_id)
        query = (
            f"SELECT * FROM kg_decision_traces WHERE {' AND '.join(clauses)} "
            "ORDER BY timestamp"
        )
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return [self._row_to_trace(row) for row in rows]

    def upsert_coverage_rule(self, rule: CoverageRuleInput) -> CoverageRuleInput:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO kg_coverage_rules(
                    rule_id, name, material_names, mode_names, property_names,
                    scope, metadata
                )
                VALUES (%s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s::jsonb)
                ON CONFLICT (rule_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    material_names = EXCLUDED.material_names,
                    mode_names = EXCLUDED.mode_names,
                    property_names = EXCLUDED.property_names,
                    scope = EXCLUDED.scope,
                    metadata = EXCLUDED.metadata
                """,
                (
                    rule.rule_id,
                    rule.name,
                    json.dumps(rule.material_names),
                    json.dumps(rule.mode_names),
                    json.dumps(rule.property_names),
                    rule.scope,
                    json.dumps(rule.metadata),
                ),
            )
        self._connection.commit()
        return rule

    def list_coverage_rules(self) -> list[CoverageRuleInput]:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT * FROM kg_coverage_rules ORDER BY rule_id")
            rows = cursor.fetchall()
        return [self._row_to_rule(row) for row in rows]

    def upsert_text_unit(self, text_unit: SearchTextUnit) -> SearchTextUnit:
        with self._connection.cursor() as cursor:
            if text_unit.embedding is None:
                cursor.execute(
                    """
                    INSERT INTO kg_text_units (
                        id, source_entity_id, source_kind, content, embedding,
                        metadata, created_at
                    )
                    VALUES (%s, %s, %s, %s, NULL, %s::jsonb, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        metadata = kg_text_units.metadata || EXCLUDED.metadata
                    """,
                    (
                        text_unit.id,
                        text_unit.source_entity_id,
                        text_unit.source_kind.value,
                        text_unit.content,
                        json.dumps(text_unit.metadata),
                        text_unit.created_at,
                    ),
                )
            else:
                embedding_expr = "[" + ",".join(str(value) for value in text_unit.embedding) + "]"
                cursor.execute(
                    """
                    INSERT INTO kg_text_units (
                        id, source_entity_id, source_kind, content, embedding,
                        metadata, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s::vector, %s::jsonb, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        metadata = kg_text_units.metadata || EXCLUDED.metadata
                    """,
                    (
                        text_unit.id,
                        text_unit.source_entity_id,
                        text_unit.source_kind.value,
                        text_unit.content,
                        embedding_expr,
                        json.dumps(text_unit.metadata),
                        text_unit.created_at,
                    ),
                )
        self._connection.commit()
        return text_unit

    def search_text_units(self, query: str, *, limit: int = 5) -> list[SearchTextUnit]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM kg_text_units
                WHERE content ILIKE %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (f"%{query}%", limit),
            )
            rows = cursor.fetchall()
        return [self._row_to_text_unit(row) for row in rows]

    def _row_to_entity(self, row: Any) -> Entity:
        return Entity(
            id=row[0],
            kind=EntityKind(row[1]),
            canonical_name=row[2],
            aliases=row[4] or [],
            properties=row[5] or {},
            source_refs=row[6] or [],
            confidence=row[7],
            created_at=_ensure_datetime(row[8]) or datetime.now(UTC),
            updated_at=_ensure_datetime(row[9]) or datetime.now(UTC),
        )

    def _row_to_evidence(self, row: Any) -> Evidence:
        raw_kind = row[1]
        if isinstance(raw_kind, SourceKind):
            source_kind = raw_kind
        elif isinstance(raw_kind, str):
            source_kind = SourceKind(raw_kind)
        else:
            source_kind = SourceKind(str(raw_kind))
        return Evidence(
            id=row[0],
            source_kind=source_kind,
            source_id=row[2],
            span=SourceSpan(**(row[3] or {})),
            extraction_method=row[4],
            confidence=row[5],
            version=row[6],
            recorded_at=_ensure_datetime(row[7]) or datetime.now(UTC),
            metadata=row[8] or {},
        )

    def _row_to_relation(self, row: Any) -> Relation:
        return Relation(
            id=row[0],
            relation_type=RelationType(row[1]),
            source_entity_id=row[2],
            target_entity_id=row[3],
            evidence_ids=row[4] or [],
            properties=row[5] or {},
            confidence=row[6],
            created_at=row[7],
            updated_at=row[8],
        )

    def _row_to_observation(self, row: Any) -> Observation:
        return Observation(
            id=row[0],
            material_id=row[1],
            property_id=row[2],
            experiment_id=row[3],
            mode_id=row[4],
            value=row[5],
            unit=row[6],
            comparator=row[7],
            evidence_id=row[8],
            confidence=row[9],
            observed_at=row[10],
            metadata=row[11] or {},
        )

    def _row_to_trace(self, row: Any) -> DecisionTrace:
        return DecisionTrace(
            id=row[0],
            summary=row[1],
            decision=row[2],
            entity_ids=row[3] or [],
            experiment_id=row[4],
            observation_ids=row[5] or [],
            evidence_ids=row[6] or [],
            changed_from_trace_id=row[7],
            timestamp=row[8],
            confidence=row[9],
            metadata=row[10] or {},
        )

    def _row_to_rule(self, row: Any) -> CoverageRuleInput:
        return CoverageRuleInput(
            rule_id=row[0],
            name=row[1],
            material_names=row[2] or [],
            mode_names=row[3] or [],
            property_names=row[4] or [],
            scope=row[5],
            metadata=row[6] or {},
        )

    def _row_to_text_unit(self, row: Any) -> SearchTextUnit:
        return SearchTextUnit(
            id=row[0],
            source_entity_id=row[1],
            source_kind=row[2] if hasattr(row[2], "value") else row[2],
            content=row[3],
            embedding=row[4],
            metadata=row[5] or {},
            created_at=row[6],
        )
