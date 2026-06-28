"""Repository protocol for graph-first materials KG persistence."""

from __future__ import annotations

from typing import Protocol

from kg_engine.domain.models import CoverageRuleInput
from kg_engine.domain.models import DataGap
from kg_engine.domain.models import DecisionTrace
from kg_engine.domain.models import Entity
from kg_engine.domain.models import EntityKind
from kg_engine.domain.models import Evidence
from kg_engine.domain.models import Observation
from kg_engine.domain.models import Relation
from kg_engine.domain.models import RelationType
from kg_engine.domain.models import SearchTextUnit


class MaterialsKGRepository(Protocol):
    """Persistence operations needed by the graph-first service layer."""

    def upsert_entity(self, entity: Entity) -> Entity:
        ...

    def get_entity(self, entity_id: str) -> Entity | None:
        ...

    def find_entities(
        self,
        *,
        kind: EntityKind | None = None,
        name: str | None = None,
        ids: list[str] | None = None,
    ) -> list[Entity]:
        ...

    def resolve_entity(self, kind: EntityKind, raw_name: str) -> Entity | None:
        ...

    def upsert_evidence(self, evidence: Evidence) -> Evidence:
        ...

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        ...

    def list_evidence(self, evidence_ids: list[str]) -> list[Evidence]:
        ...

    def upsert_relation(self, relation: Relation) -> Relation:
        ...

    def list_relations(
        self,
        *,
        entity_id: str | None = None,
        relation_types: list[RelationType] | None = None,
    ) -> list[Relation]:
        ...

    def upsert_observation(self, observation: Observation) -> Observation:
        ...

    def list_observations(
        self,
        *,
        material_id: str | None = None,
        property_id: str | None = None,
        experiment_id: str | None = None,
        mode_id: str | None = None,
    ) -> list[Observation]:
        ...

    def upsert_decision_trace(self, trace: DecisionTrace) -> DecisionTrace:
        ...

    def list_decision_traces(
        self,
        *,
        entity_id: str | None = None,
        experiment_id: str | None = None,
    ) -> list[DecisionTrace]:
        ...

    def upsert_coverage_rule(self, rule: CoverageRuleInput) -> CoverageRuleInput:
        ...

    def list_coverage_rules(self) -> list[CoverageRuleInput]:
        ...

    def upsert_text_unit(self, text_unit: SearchTextUnit) -> SearchTextUnit:
        ...

    def search_text_units(self, query: str, *, limit: int = 5) -> list[SearchTextUnit]:
        ...
