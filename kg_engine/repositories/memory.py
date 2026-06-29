"""In-memory repository used for tests and local validation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from kg_engine.domain.models import CoverageRuleInput
from kg_engine.domain.models import DecisionTrace
from kg_engine.domain.models import Entity
from kg_engine.domain.models import EntityKind
from kg_engine.domain.models import Evidence
from kg_engine.domain.models import Observation
from kg_engine.domain.models import Relation
from kg_engine.domain.models import RelationType
from kg_engine.domain.models import SearchTextUnit
from kg_engine.domain.resolution import normalize_name


@dataclass
class _ScoredTextUnit:
    score: int
    text_unit: SearchTextUnit


_TERM_PATTERN = re.compile(r"[a-z0-9]+")


class InMemoryMaterialsKGRepository:
    """Simple repository implementation for service logic and tests."""

    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}
        self._alias_index: dict[tuple[EntityKind, str], str] = {}
        self._evidence: dict[str, Evidence] = {}
        self._relations: dict[str, Relation] = {}
        self._observations: dict[str, Observation] = {}
        self._traces: dict[str, DecisionTrace] = {}
        self._coverage_rules: dict[str, CoverageRuleInput] = {}
        self._text_units: dict[str, SearchTextUnit] = {}

    def upsert_entity(self, entity: Entity) -> Entity:
        current = self._entities.get(entity.id)
        if current is None:
            stored = entity
        else:
            aliases = list({*current.aliases, *entity.aliases})
            source_refs = list({*current.source_refs, *entity.source_refs})
            properties = {**current.properties, **entity.properties}
            stored = current.model_copy(
                update={
                    "canonical_name": entity.canonical_name,
                    "aliases": aliases,
                    "properties": properties,
                    "source_refs": source_refs,
                    "confidence": max(current.confidence, entity.confidence),
                    "updated_at": entity.updated_at,
                }
            )
        self._entities[entity.id] = stored
        names = [stored.canonical_name, *stored.aliases]
        for name in names:
            self._alias_index[(stored.kind, normalize_name(name))] = stored.id
        return stored

    def get_entity(self, entity_id: str) -> Entity | None:
        return self._entities.get(entity_id)

    def find_entities(
        self,
        *,
        kind: EntityKind | None = None,
        name: str | None = None,
        ids: list[str] | None = None,
    ) -> list[Entity]:
        entities = list(self._entities.values())
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
        entity_id = self._alias_index.get((kind, normalize_name(raw_name)))
        if entity_id is None:
            matches = self.find_entities(kind=kind, name=raw_name)
            return matches[0] if matches else None
        return self._entities.get(entity_id)

    def upsert_evidence(self, evidence: Evidence) -> Evidence:
        self._evidence[evidence.id] = evidence
        return evidence

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        return self._evidence.get(evidence_id)

    def list_evidence(self, evidence_ids: list[str]) -> list[Evidence]:
        return [
            self._evidence[evidence_id]
            for evidence_id in evidence_ids
            if evidence_id in self._evidence
        ]

    def upsert_relation(self, relation: Relation) -> Relation:
        current = self._relations.get(relation.id)
        if current is None:
            self._relations[relation.id] = relation
        else:
            merged_evidence = list({*current.evidence_ids, *relation.evidence_ids})
            properties = {**current.properties, **relation.properties}
            self._relations[relation.id] = current.model_copy(
                update={
                    "evidence_ids": merged_evidence,
                    "properties": properties,
                    "confidence": max(current.confidence, relation.confidence),
                    "updated_at": relation.updated_at,
                }
            )
        return self._relations[relation.id]

    def list_relations(
        self,
        *,
        entity_id: str | None = None,
        relation_types: list[RelationType] | None = None,
    ) -> list[Relation]:
        relations = list(self._relations.values())
        if entity_id is not None:
            relations = [
                relation
                for relation in relations
                if relation.source_entity_id == entity_id
                or relation.target_entity_id == entity_id
            ]
        if relation_types is not None:
            allowed = set(relation_types)
            relations = [
                relation for relation in relations if relation.relation_type in allowed
            ]
        return relations

    def upsert_observation(self, observation: Observation) -> Observation:
        self._observations[observation.id] = observation
        return observation

    def list_observations(
        self,
        *,
        material_id: str | None = None,
        property_id: str | None = None,
        experiment_id: str | None = None,
        mode_id: str | None = None,
    ) -> list[Observation]:
        observations = list(self._observations.values())
        if material_id is not None:
            observations = [
                item for item in observations if item.material_id == material_id
            ]
        if property_id is not None:
            observations = [
                item for item in observations if item.property_id == property_id
            ]
        if experiment_id is not None:
            observations = [
                item for item in observations if item.experiment_id == experiment_id
            ]
        if mode_id is not None:
            observations = [item for item in observations if item.mode_id == mode_id]
        return observations

    def upsert_decision_trace(self, trace: DecisionTrace) -> DecisionTrace:
        self._traces[trace.id] = trace
        return trace

    def list_decision_traces(
        self,
        *,
        entity_id: str | None = None,
        experiment_id: str | None = None,
    ) -> list[DecisionTrace]:
        traces = list(self._traces.values())
        if entity_id is not None:
            traces = [trace for trace in traces if entity_id in trace.entity_ids]
        if experiment_id is not None:
            traces = [trace for trace in traces if trace.experiment_id == experiment_id]
        traces.sort(key=lambda item: item.timestamp)
        return traces

    def upsert_coverage_rule(self, rule: CoverageRuleInput) -> CoverageRuleInput:
        self._coverage_rules[rule.rule_id] = rule
        return rule

    def list_coverage_rules(self) -> list[CoverageRuleInput]:
        return list(self._coverage_rules.values())

    def upsert_text_unit(self, text_unit: SearchTextUnit) -> SearchTextUnit:
        self._text_units[text_unit.id] = text_unit
        return text_unit

    def search_text_units(self, query: str, *, limit: int = 5) -> list[SearchTextUnit]:
        normalized_terms = _TERM_PATTERN.findall(query.lower())
        scored: list[_ScoredTextUnit] = []
        for text_unit in self._text_units.values():
            lowered_content = text_unit.content.lower()
            normalized_content = normalize_name(text_unit.content)
            score = 0
            for term in normalized_terms:
                if term and (
                    term in lowered_content
                    or normalize_name(term) in normalized_content
                ):
                    score += len(term)
            if score == 0:
                raw_lower = query.lower()
                if raw_lower in text_unit.content.lower():
                    score = len(raw_lower)
            if score > 0:
                scored.append(_ScoredTextUnit(score=score, text_unit=text_unit))
        scored.sort(key=lambda item: item.score, reverse=True)
        return [item.text_unit for item in scored[:limit]]

    def clear_all(self) -> None:
        self._entities.clear()
        self._alias_index.clear()
        self._evidence.clear()
        self._relations.clear()
        self._observations.clear()
        self._traces.clear()
        self._coverage_rules.clear()
        self._text_units.clear()

    def delete_source(self, source_id: str) -> int:
        removed = 0
        entity_ids_to_remove: list[str] = []
        for eid, entity in list(self._entities.items()):
            if source_id not in entity.source_refs:
                continue
            if len(entity.source_refs) <= 1:
                entity_ids_to_remove.append(eid)
                continue
            new_refs = [ref for ref in entity.source_refs if ref != source_id]
            self._entities[eid] = entity.model_copy(update={"source_refs": new_refs})
            removed += 1
        for eid in entity_ids_to_remove:
            del self._entities[eid]
            removed += 1
        self._alias_index = {
            k: v for k, v in self._alias_index.items() if v not in entity_ids_to_remove
        }
        evidence_to_remove = [
            eid for eid, ev in self._evidence.items() if ev.source_id == source_id
        ]
        for eid in evidence_to_remove:
            del self._evidence[eid]
            removed += 1
        self._relations = {
            rid: r
            for rid, r in self._relations.items()
            if r.source_entity_id not in entity_ids_to_remove
            and r.target_entity_id not in entity_ids_to_remove
        }
        obs_to_remove = [
            oid
            for oid, o in self._observations.items()
            if o.experiment_id in entity_ids_to_remove
            or o.material_id in entity_ids_to_remove
        ]
        for oid in obs_to_remove:
            del self._observations[oid]
            removed += 1
        traces_to_remove = [
            tid
            for tid, t in self._traces.items()
            if t.experiment_id in entity_ids_to_remove
            or any(eid in entity_ids_to_remove for eid in t.entity_ids)
        ]
        for tid in traces_to_remove:
            del self._traces[tid]
            removed += 1
        text_to_remove = [
            tid
            for tid, tu in self._text_units.items()
            if tu.source_entity_id in entity_ids_to_remove
        ]
        for tid in text_to_remove:
            del self._text_units[tid]
            removed += 1
        return removed
