"""Typed domain models for the graph-first materials knowledge graph core."""

from __future__ import annotations

import enum
from datetime import UTC
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from pydantic import Field


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class EntityKind(str, enum.Enum):
    """Supported first-class entities in the materials KG."""

    MATERIAL = "material"
    EXPERIMENT = "experiment"
    PROPERTY = "property"
    MODE = "mode"
    EQUIPMENT = "equipment"
    TEAM = "team"
    DOCUMENT = "document"
    TAG = "tag"


class SourceKind(str, enum.Enum):
    """Source families used by ingestion and provenance records."""

    DOCUMENT = "document"
    EXPERIMENT = "experiment"
    REFERENCE = "reference"
    DIRECTORY = "directory"
    TAG = "tag"


class RelationType(str, enum.Enum):
    """Graph relations used by traversal and explainability."""

    EVALUATES_MATERIAL = "evaluates_material"
    USES_MODE = "uses_mode"
    MEASURES_PROPERTY = "measures_property"
    USES_EQUIPMENT = "uses_equipment"
    PERFORMED_BY = "performed_by"
    DOCUMENTED_IN = "documented_in"
    TAGGED_WITH = "tagged_with"
    REFERENCES = "references"
    RELATED_TO = "related_to"


class SourceSpan(BaseModel):
    """Precise provenance pointer within a source document or row-set."""

    fragment: str | None = Field(default=None)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    row_reference: str | None = Field(default=None)
    section: str | None = Field(default=None)


class Entity(BaseModel):
    """Canonical entity stored in the graph core."""

    id: str
    kind: EntityKind
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Evidence(BaseModel):
    """Evidence record attached to relations, observations, and traces."""

    id: str
    source_kind: SourceKind
    source_id: str
    span: SourceSpan = Field(default_factory=SourceSpan)
    extraction_method: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    version: str | None = Field(default=None)
    recorded_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Relation(BaseModel):
    """Typed relation between canonical entities."""

    id: str
    relation_type: RelationType
    source_entity_id: str
    target_entity_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Observation(BaseModel):
    """Measured observation tied to an experiment and provenance trail."""

    id: str
    material_id: str
    property_id: str
    experiment_id: str | None = Field(default=None)
    mode_id: str | None = Field(default=None)
    value: float | None = Field(default=None)
    unit: str | None = Field(default=None)
    comparator: str | None = Field(default=None)
    evidence_id: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    observed_at: datetime | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionTrace(BaseModel):
    """History layer that explains why a conclusion exists and how it changed."""

    id: str
    summary: str
    decision: str | None = Field(default=None)
    entity_ids: list[str] = Field(default_factory=list)
    experiment_id: str | None = Field(default=None)
    observation_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    changed_from_trace_id: str | None = Field(default=None)
    timestamp: datetime = Field(default_factory=utc_now)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchTextUnit(BaseModel):
    """Searchable chunk stored for hybrid evidence lookup."""

    id: str
    source_entity_id: str
    source_kind: SourceKind
    content: str
    embedding: list[float] | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class DataGap(BaseModel):
    """Expected-but-missing coverage discovered from coverage rules."""

    id: str
    scope: str
    rule_id: str | None = Field(default=None)
    material_id: str | None = Field(default=None)
    mode_id: str | None = Field(default=None)
    property_id: str | None = Field(default=None)
    reason: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CanonicalEntityInput(BaseModel):
    """Reference record used to seed canonical dictionaries."""

    kind: EntityKind
    name: str
    canonical_id: str | None = Field(default=None)
    aliases: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    source_ref: str | None = Field(default=None)


class CoverageRuleInput(BaseModel):
    """Expected experimental coverage for gap analysis."""

    rule_id: str
    name: str
    material_names: list[str] = Field(default_factory=list)
    mode_names: list[str] = Field(default_factory=list)
    property_names: list[str] = Field(default_factory=list)
    scope: str = Field(default="material-mode-property")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReferenceDataBatch(BaseModel):
    """Reference data inputs grouped by source family."""

    entities: list[CanonicalEntityInput] = Field(default_factory=list)
    coverage_rules: list[CoverageRuleInput] = Field(default_factory=list)


class ObservationInput(BaseModel):
    """Structured measurement used by experiment ingestion."""

    property_name: str
    value: float | None = Field(default=None)
    unit: str | None = Field(default=None)
    comparator: str | None = Field(default=None)
    fragment: str | None = Field(default=None)
    row_reference: str | None = Field(default=None)
    extraction_method: str = Field(default="structured_experiment")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    observed_at: datetime | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FindingInput(BaseModel):
    """Conclusion or decision item emitted by experiments or documents."""

    summary: str
    decision: str | None = Field(default=None)
    fragment: str | None = Field(default=None)
    extraction_method: str = Field(default="structured_finding")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    observation_indices: list[int] = Field(default_factory=list)
    changed_from_trace_id: str | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TextUnitInput(BaseModel):
    """Searchable text unit provided directly by callers."""

    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExperimentInput(BaseModel):
    """Experiment catalog record."""

    experiment_id: str
    title: str
    material_name: str
    mode_name: str | None = Field(default=None)
    equipment_names: list[str] = Field(default_factory=list)
    team_name: str | None = Field(default=None)
    document_id: str | None = Field(default=None)
    source_version: str | None = Field(default=None)
    observations: list[ObservationInput] = Field(default_factory=list)
    findings: list[FindingInput] = Field(default_factory=list)
    text_units: list[TextUnitInput] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentInput(BaseModel):
    """Internal document corpus record."""

    document_id: str
    title: str
    text: str
    material_names: list[str] = Field(default_factory=list)
    mode_names: list[str] = Field(default_factory=list)
    property_names: list[str] = Field(default_factory=list)
    equipment_names: list[str] = Field(default_factory=list)
    team_names: list[str] = Field(default_factory=list)
    tag_names: list[str] = Field(default_factory=list)
    experiment_ids: list[str] = Field(default_factory=list)
    findings: list[FindingInput] = Field(default_factory=list)
    text_units: list[TextUnitInput] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class QueryFilters(BaseModel):
    """Common filters for graph query APIs."""

    material_name: str | None = Field(default=None)
    mode_name: str | None = Field(default=None)
    property_name: str | None = Field(default=None)
    team_name: str | None = Field(default=None)
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class PropertyFilters(QueryFilters):
    """Range filters for property-oriented queries."""

    min_value: float | None = Field(default=None)
    max_value: float | None = Field(default=None)


class EvidencePath(BaseModel):
    """Path item returned by related-entity traversal."""

    entity_ids: list[str] = Field(default_factory=list)
    relation_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class MaterialModeQueryResult(BaseModel):
    """Result envelope for material+mode question answering."""

    material: Entity
    mode: Entity | None = Field(default=None)
    experiments: list[Entity] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    findings: list[DecisionTrace] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    search_hits: list[SearchTextUnit] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class PropertyQueryResult(BaseModel):
    """Results for property threshold/range queries."""

    property_entity: Entity
    observations: list[Observation] = Field(default_factory=list)
    materials: list[Entity] = Field(default_factory=list)
    experiments: list[Entity] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class RelatedEntitiesQueryResult(BaseModel):
    """Results for BFS-style traversal with explainable evidence paths."""

    root_entity: Entity
    related_entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    evidence_paths: list[EvidencePath] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class DecisionHistoryQueryResult(BaseModel):
    """Results for decision history lookups."""

    requested_entity: Entity
    traces: list[DecisionTrace] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class HypothesisInput(BaseModel):
    """Request for explainable research hypothesis generation."""

    target_kpi: str
    question: str = Field(default="")
    material: str | None = Field(default=None)
    mode: str | None = Field(default=None)
    property_name: str | None = Field(default=None)
    max_hypotheses: int = Field(default=5, ge=1, le=20)
    expert_adjustments: dict[str, Any] = Field(default_factory=dict)


class HypothesisScore(BaseModel):
    """Transparent score components for a generated hypothesis."""

    novelty: float = Field(ge=0.0, le=1.0)
    risk: float = Field(ge=0.0, le=1.0)
    value: float = Field(ge=0.0, le=1.0)
    evidence_strength: float = Field(ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)


class ResearchHypothesis(BaseModel):
    """Interpretable, testable hypothesis grounded in graph evidence."""

    id: str
    target_kpi: str
    statement: str
    rationale: str
    test_plan: str
    score: HypothesisScore
    supporting_entity_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    supporting_observation_ids: list[str] = Field(default_factory=list)
    data_gap_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    expert_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HypothesisGenerationResult(BaseModel):
    """Hypothesis Factory response with evidence and ranking details."""

    target_kpi: str
    resolved_query: dict[str, str | None] = Field(default_factory=dict)
    hypotheses: list[ResearchHypothesis] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    data_gaps: list[DataGap] = Field(default_factory=list)
    matched_entities: list[Entity] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    """A single message in a conversation session."""

    role: str = Field(description="'user' or 'assistant'")
    content: str
    timestamp: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationSession(BaseModel):
    """A conversation session with message history and TTL."""

    session_id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    last_active: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)
