"""Graph-first service layer for materials knowledge graph ingestion and query."""

from __future__ import annotations

import hashlib
import logging
from collections import deque
from statistics import fmean
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from kg_engine.domain.models import CanonicalEntityInput
from kg_engine.domain.models import CoverageRuleInput
from kg_engine.domain.models import DataGap
from kg_engine.domain.models import DecisionHistoryQueryResult
from kg_engine.domain.models import DecisionTrace
from kg_engine.domain.models import DocumentInput
from kg_engine.domain.models import Entity
from kg_engine.domain.models import EntityKind
from kg_engine.domain.models import Evidence
from kg_engine.domain.models import EvidencePath
from kg_engine.domain.models import ExperimentInput
from kg_engine.domain.models import FindingInput
from kg_engine.domain.models import HypothesisGenerationResult
from kg_engine.domain.models import HypothesisInput
from kg_engine.domain.models import HypothesisScore
from kg_engine.domain.models import MaterialModeQueryResult
from kg_engine.domain.models import Observation
from kg_engine.domain.models import ObservationInput
from kg_engine.domain.models import PropertyFilters
from kg_engine.domain.models import PropertyQueryResult
from kg_engine.domain.models import QueryFilters
from kg_engine.domain.models import ReferenceDataBatch
from kg_engine.domain.models import RelatedEntitiesQueryResult
from kg_engine.domain.models import Relation
from kg_engine.domain.models import RelationType
from kg_engine.domain.models import ResearchHypothesis
from kg_engine.domain.models import SearchTextUnit
from kg_engine.domain.models import SourceKind
from kg_engine.domain.models import SourceSpan
from kg_engine.domain.models import TextUnitInput
from kg_engine.domain.resolution import normalize_name
from kg_engine.repositories.protocols import MaterialsKGRepository

logger = logging.getLogger(__name__)


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "::".join(str(part) for part in parts if part is not None)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _entity_matches_sources(entity: Entity, source_set: set[str]) -> bool:
    """Check if an entity originated from any of the given sources."""
    if any(ref in source_set for ref in entity.source_refs):
        return True
    props = entity.properties
    for key in ("source_file", "source_ref", "_uploaded_from"):
        val = props.get(key)
        if val and val in source_set:
            return True
    return False


def _evidence_matches_sources(evidence: Evidence, source_set: set[str]) -> bool:
    """Check if evidence originated from any of the given sources."""
    if evidence.source_id in source_set:
        return True
    meta = evidence.metadata
    for key in ("source_file", "source_ref"):
        val = meta.get(key)
        if val and val in source_set:
            return True
    return False


def _observation_matches_sources(
    observation: Observation,
    evidence_by_id: dict[str, Evidence],
    source_set: set[str],
) -> bool:
    """Check if an observation's evidence came from the given sources."""
    ev = evidence_by_id.get(observation.evidence_id)
    if ev is not None and _evidence_matches_sources(ev, source_set):
        return True
    for key in ("source_file", "source_ref"):
        val = observation.metadata.get(key)
        if val and val in source_set:
            return True
    return False


def _relation_matches_sources(
    relation: Relation,
    evidence_by_id: dict[str, Evidence],
    source_set: set[str],
) -> bool:
    """Check if a relation's evidence came from the given sources."""
    for eid in relation.evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev is not None and _evidence_matches_sources(ev, source_set):
            return True
    return False


def _trace_matches_sources(
    trace: DecisionTrace,
    evidence_by_id: dict[str, Evidence],
    source_set: set[str],
) -> bool:
    """Check if a decision trace's evidence came from the given sources."""
    for eid in trace.evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev is not None and _evidence_matches_sources(ev, source_set):
            return True
    meta = trace.metadata
    for key in ("source_file", "source_ref"):
        val = meta.get(key)
        if val and val in source_set:
            return True
    return False


class MaterialsKGService:
    """Public ingestion and query API for the compact domain core."""

    def __init__(
        self,
        repository: MaterialsKGRepository,
        llm_provider: Any | None = None,
        session_store: Any | None = None,
    ) -> None:
        self._repository = repository
        self._llm = llm_provider
        self._session_store = session_store

    def ingest_reference_data(self, batch: ReferenceDataBatch) -> dict[str, int]:
        entity_count = 0
        for record in batch.entities:
            self._upsert_reference_entity(record)
            entity_count += 1
        for rule in batch.coverage_rules:
            self._repository.upsert_coverage_rule(rule)
        return {
            "entities": entity_count,
            "coverage_rules": len(batch.coverage_rules),
        }

    def ingest_experiments(self, batch: list[ExperimentInput]) -> dict[str, int]:
        observation_count = 0
        trace_count = 0
        for experiment in batch:
            provenance_ref = experiment.source_ref or experiment.experiment_id
            experiment_entity = self._ensure_entity(
                EntityKind.EXPERIMENT,
                experiment.title,
                entity_id=experiment.experiment_id,
                aliases=[experiment.experiment_id],
                source_ref=provenance_ref,
                properties=experiment.metadata,
            )
            material = self._ensure_entity(
                EntityKind.MATERIAL,
                experiment.material_name,
                source_ref=provenance_ref,
            )
            self._link_entities(
                experiment_entity.id,
                material.id,
                RelationType.EVALUATES_MATERIAL,
                evidence_ids=[],
                properties={"source": provenance_ref},
            )
            mode_entity = None
            if experiment.mode_name:
                mode_entity = self._ensure_entity(
                    EntityKind.MODE,
                    experiment.mode_name,
                    source_ref=provenance_ref,
                )
                self._link_entities(
                    experiment_entity.id,
                    mode_entity.id,
                    RelationType.USES_MODE,
                    evidence_ids=[],
                )
            if experiment.team_name:
                team = self._ensure_entity(
                    EntityKind.TEAM,
                    experiment.team_name,
                    source_ref=provenance_ref,
                )
                self._link_entities(
                    experiment_entity.id,
                    team.id,
                    RelationType.PERFORMED_BY,
                    evidence_ids=[],
                )
            for equipment_name in experiment.equipment_names:
                equipment = self._ensure_entity(
                    EntityKind.EQUIPMENT,
                    equipment_name,
                    source_ref=provenance_ref,
                )
                self._link_entities(
                    experiment_entity.id,
                    equipment.id,
                    RelationType.USES_EQUIPMENT,
                    evidence_ids=[],
                )
            if experiment.document_id:
                document = self._ensure_entity(
                    EntityKind.DOCUMENT,
                    experiment.document_id,
                    entity_id=experiment.document_id,
                    aliases=[experiment.document_id],
                    source_ref=provenance_ref,
                )
                self._link_entities(
                    experiment_entity.id,
                    document.id,
                    RelationType.DOCUMENTED_IN,
                    evidence_ids=[],
                )

            observation_ids: list[str] = []
            for observation_input in experiment.observations:
                observation = self._create_observation(
                    experiment=experiment,
                    experiment_entity=experiment_entity,
                    material=material,
                    mode_entity=mode_entity,
                    observation_input=observation_input,
                    provenance_ref=provenance_ref,
                )
                observation_ids.append(observation.id)
                observation_count += 1

            for index, finding in enumerate(experiment.findings):
                self._create_trace(
                    finding=finding,
                    source_kind=SourceKind.EXPERIMENT,
                    source_id=provenance_ref,
                    entity_ids=[
                        material.id,
                        experiment_entity.id,
                        *([mode_entity.id] if mode_entity else []),
                    ],
                    experiment_id=experiment_entity.id,
                    observation_ids=[
                        observation_ids[item]
                        for item in finding.observation_indices
                        if item < len(observation_ids)
                    ],
                    trace_id=_stable_id(
                        "trace",
                        experiment.experiment_id,
                        index,
                        finding.summary,
                    ),
                    version=experiment.source_version,
                )
                trace_count += 1

            for index, text_unit in enumerate(experiment.text_units):
                unit_metadata = {
                    **text_unit.metadata,
                    "source_id": provenance_ref,
                    "source_file": provenance_ref,
                }
                self._repository.upsert_text_unit(
                    SearchTextUnit(
                        id=_stable_id(
                            "text",
                            experiment.experiment_id,
                            index,
                            text_unit.content,
                        ),
                        source_entity_id=experiment_entity.id,
                        source_kind=SourceKind.EXPERIMENT,
                        content=text_unit.content,
                        metadata=unit_metadata,
                    )
                )
        return {
            "experiments": len(batch),
            "observations": observation_count,
            "decision_traces": trace_count,
        }

    def ingest_documents(self, batch: list[DocumentInput]) -> dict[str, int]:
        trace_count = 0
        llm_extracted_count = 0
        for document in batch:
            doc_src = document.source_ref or document.document_id
            document_entity = self._ensure_entity(
                EntityKind.DOCUMENT,
                document.title,
                entity_id=document.document_id,
                aliases=[document.document_id],
                source_ref=doc_src,
                properties=document.metadata,
            )
            linked_entity_ids: list[str] = [document_entity.id]

            has_explicit_entities = any(
                [
                    document.material_names,
                    document.mode_names,
                    document.property_names,
                    document.equipment_names,
                    document.team_names,
                    document.experiment_ids,
                ]
            )

            if self._llm and not has_explicit_entities and document.text:
                try:
                    from kg_engine.llm_core.extraction import (
                        extract_entities_from_document,
                    )

                    extracted = extract_entities_from_document(
                        self._llm, document.title, document.text
                    )
                    for ent in extracted.get("entities", []):
                        kind_str = ent.get("kind", "document")
                        try:
                            kind = EntityKind(kind_str)
                        except ValueError:
                            kind = EntityKind.DOCUMENT
                        entity = self._ensure_entity(
                            kind,
                            ent.get("name", ""),
                            source_ref=doc_src,
                            aliases=ent.get("aliases", []),
                            properties=ent.get("properties", {}),
                        )
                        linked_entity_ids.append(entity.id)
                        evidence = self._create_evidence(
                            source_kind=SourceKind.DOCUMENT,
                            source_id=doc_src,
                            fragment=ent.get("name", ""),
                            extraction_method="llm_extraction",
                            confidence=0.85,
                        )
                        self._link_entities(
                            document_entity.id,
                            entity.id,
                            RelationType.REFERENCES,
                            evidence_ids=[evidence.id],
                        )
                    for exp in extracted.get("experiments", []):
                        material_name = exp.get("material_name", "")
                        mode_name = exp.get("mode_name", "")
                        observations = []
                        for obs in exp.get("observations", []):
                            observations.append(
                                ObservationInput(
                                    property_name=obs.get("property_name", ""),
                                    value=obs.get("value"),
                                    unit=obs.get("unit", ""),
                                    confidence=obs.get("confidence", 0.85),
                                    extraction_method="llm_extraction",
                                )
                            )
                        findings = []
                        for f in exp.get("findings", []):
                            from kg_engine.domain.models import FindingInput

                            findings.append(
                                FindingInput(
                                    summary=f.get("summary", ""),
                                    confidence=f.get("confidence", 0.85),
                                    extraction_method="llm_extraction",
                                )
                            )
                        exp_input = ExperimentInput(
                            experiment_id=exp.get(
                                "experiment_id",
                                f"{document.document_id}_exp_{llm_extracted_count}",
                            ),
                            title=exp.get("title", f"Extracted from {document.title}"),
                            material_name=material_name,
                            mode_name=mode_name,
                            observations=observations,
                            findings=findings,
                            source_ref=doc_src,
                            metadata={
                                "source_document": document.document_id,
                                "extraction_method": "llm",
                            },
                        )
                        self.ingest_experiments([exp_input])
                        llm_extracted_count += 1
                except Exception:
                    logger.exception(
                        "LLM extraction failed for document %s", document.document_id
                    )

            for kind, values in (
                (EntityKind.MATERIAL, document.material_names),
                (EntityKind.MODE, document.mode_names),
                (EntityKind.PROPERTY, document.property_names),
                (EntityKind.EQUIPMENT, document.equipment_names),
                (EntityKind.TEAM, document.team_names),
            ):
                for value in values:
                    entity = self._ensure_entity(kind, value, source_ref=doc_src)
                    linked_entity_ids.append(entity.id)
                    evidence = self._create_evidence(
                        source_kind=SourceKind.DOCUMENT,
                        source_id=doc_src,
                        fragment=value,
                        extraction_method="document_reference",
                        metadata={"source_file": doc_src},
                    )
                    self._link_entities(
                        document_entity.id,
                        entity.id,
                        RelationType.REFERENCES,
                        evidence_ids=[evidence.id],
                    )
            for tag_name in document.tag_names:
                tag = self._ensure_entity(EntityKind.TAG, tag_name, source_ref=doc_src)
                linked_entity_ids.append(tag.id)
                self._link_entities(
                    document_entity.id,
                    tag.id,
                    RelationType.TAGGED_WITH,
                    evidence_ids=[],
                )
            for experiment_id in document.experiment_ids:
                experiment_entity = self._ensure_entity(
                    EntityKind.EXPERIMENT,
                    experiment_id,
                    entity_id=experiment_id,
                    aliases=[experiment_id],
                    source_ref=doc_src,
                )
                linked_entity_ids.append(experiment_entity.id)
                self._link_entities(
                    experiment_entity.id,
                    document_entity.id,
                    RelationType.DOCUMENTED_IN,
                    evidence_ids=[],
                )
            doc_metadata = {
                **document.metadata,
                "source_id": doc_src,
                "source_file": doc_src,
            }
            self._upsert_text_unit_with_embedding(
                unit_id=_stable_id("doc_text", document.document_id, document.text),
                source_entity_id=document_entity.id,
                source_kind=SourceKind.DOCUMENT,
                content=document.text,
                metadata=doc_metadata,
            )
            for index, text_unit in enumerate(document.text_units):
                unit_metadata = {
                    **text_unit.metadata,
                    "source_id": doc_src,
                    "source_file": doc_src,
                }
                self._upsert_text_unit_with_embedding(
                    unit_id=_stable_id("doc_chunk", document.document_id, index),
                    source_entity_id=document_entity.id,
                    source_kind=SourceKind.DOCUMENT,
                    content=text_unit.content,
                    metadata=unit_metadata,
                )
            for index, finding in enumerate(document.findings):
                self._create_trace(
                    finding=finding,
                    source_kind=SourceKind.DOCUMENT,
                    source_id=doc_src,
                    entity_ids=linked_entity_ids,
                    experiment_id=None,
                    observation_ids=[],
                    trace_id=_stable_id(
                        "doc_trace",
                        document.document_id,
                        index,
                        finding.summary,
                    ),
                )
                trace_count += 1
        return {"documents": len(batch), "decision_traces": trace_count}

    def _upsert_text_unit_with_embedding(
        self,
        unit_id: str,
        source_entity_id: str,
        source_kind: SourceKind,
        content: str,
        metadata: dict | None = None,
    ) -> SearchTextUnit:
        embedding = None
        if self._llm and content:
            try:
                embeddings = self._llm.embed([content[:2000]])
                if embeddings and embeddings[0]:
                    embedding = embeddings[0]
            except Exception:
                logger.debug("Embedding generation failed for text unit %s", unit_id)
        unit = SearchTextUnit(
            id=unit_id,
            source_entity_id=source_entity_id,
            source_kind=source_kind,
            content=content,
            embedding=embedding,
            metadata=metadata or {},
        )
        return self._repository.upsert_text_unit(unit)

    def query_material_mode(
        self,
        material: str,
        mode: str | None = None,
        property_name: str | None = None,
    ) -> MaterialModeQueryResult:
        material_entity = self._require_entity(EntityKind.MATERIAL, material)
        mode_entity = (
            None if mode is None else self._require_entity(EntityKind.MODE, mode)
        )
        property_entity = None
        if property_name is not None:
            property_entity = self._require_entity(EntityKind.PROPERTY, property_name)
        observations = self._repository.list_observations(
            material_id=material_entity.id
        )
        if mode_entity is not None:
            observations = [
                observation
                for observation in observations
                if observation.mode_id == mode_entity.id
            ]
        if property_entity is not None:
            observations = [
                observation
                for observation in observations
                if observation.property_id == property_entity.id
            ]
        experiment_ids = [
            observation.experiment_id
            for observation in observations
            if observation.experiment_id is not None
        ]
        experiments = self._repository.find_entities(
            ids=list(dict.fromkeys(experiment_ids))
        )
        findings: list[DecisionTrace] = []
        for experiment in experiments:
            findings.extend(
                self._repository.list_decision_traces(experiment_id=experiment.id)
            )
        evidence_ids = [observation.evidence_id for observation in observations]
        for trace in findings:
            evidence_ids.extend(trace.evidence_ids)
        search_query = " ".join(
            item for item in [material, mode, property_name] if item is not None
        )
        search_hits = self._repository.search_text_units(search_query, limit=5)
        evidence = self._repository.list_evidence(list(dict.fromkeys(evidence_ids)))
        confidence_values = [
            observation.confidence for observation in observations
        ] or [material_entity.confidence]
        return MaterialModeQueryResult(
            material=material_entity,
            mode=mode_entity,
            experiments=experiments,
            observations=observations,
            findings=findings,
            evidence=evidence,
            search_hits=search_hits,
            confidence=fmean(confidence_values),
        )

    def query_property(
        self,
        property_name: str,
        filters: PropertyFilters | None = None,
    ) -> PropertyQueryResult:
        filters = filters or PropertyFilters()
        property_entity = self._require_entity(EntityKind.PROPERTY, property_name)
        observations = self._repository.list_observations(
            property_id=property_entity.id
        )
        if filters.material_name:
            material_entity = self._require_entity(
                EntityKind.MATERIAL,
                filters.material_name,
            )
            observations = [
                observation
                for observation in observations
                if observation.material_id == material_entity.id
            ]
        if filters.mode_name:
            mode_entity = self._require_entity(EntityKind.MODE, filters.mode_name)
            observations = [
                observation
                for observation in observations
                if observation.mode_id == mode_entity.id
            ]
        filtered_observations: list[Observation] = []
        for observation in observations:
            if filters.min_value is not None and (
                observation.value is None or observation.value < filters.min_value
            ):
                continue
            if filters.max_value is not None and (
                observation.value is None or observation.value > filters.max_value
            ):
                continue
            filtered_observations.append(observation)
        material_ids = list(
            dict.fromkeys(
                observation.material_id for observation in filtered_observations
            )
        )
        experiment_ids = list(
            dict.fromkeys(
                observation.experiment_id
                for observation in filtered_observations
                if observation.experiment_id is not None
            )
        )
        evidence_ids = list(
            dict.fromkeys(
                observation.evidence_id for observation in filtered_observations
            )
        )
        return PropertyQueryResult(
            property_entity=property_entity,
            observations=filtered_observations,
            materials=self._repository.find_entities(ids=material_ids),
            experiments=self._repository.find_entities(ids=experiment_ids),
            evidence=self._repository.list_evidence(evidence_ids),
        )

    def query_related(
        self,
        entity: str,
        depth: int = 2,
        relation_filters: list[RelationType] | None = None,
    ) -> RelatedEntitiesQueryResult:
        root = self._resolve_any_entity(entity)
        visited = {root.id}
        related_entities: dict[str, Entity] = {}
        relations: dict[str, Relation] = {}
        evidence_paths: list[EvidencePath] = []
        queue: deque[tuple[str, list[str], list[str], int]] = deque(
            [(root.id, [root.id], [], 0)]
        )
        while queue:
            current_id, path_entities, path_relations, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for relation in self._repository.list_relations(
                entity_id=current_id,
                relation_types=relation_filters,
            ):
                neighbor_id = (
                    relation.target_entity_id
                    if relation.source_entity_id == current_id
                    else relation.source_entity_id
                )
                relations[relation.id] = relation
                new_path_entities = [*path_entities, neighbor_id]
                new_path_relations = [*path_relations, relation.id]
                evidence_paths.append(
                    EvidencePath(
                        entity_ids=new_path_entities,
                        relation_ids=new_path_relations,
                        evidence_ids=relation.evidence_ids,
                    )
                )
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)
                neighbor = self._repository.get_entity(neighbor_id)
                if neighbor is not None:
                    related_entities[neighbor.id] = neighbor
                    queue.append(
                        (
                            neighbor_id,
                            new_path_entities,
                            new_path_relations,
                            current_depth + 1,
                        )
                    )
        evidence_ids: list[str] = []
        for relation in relations.values():
            evidence_ids.extend(relation.evidence_ids)
        return RelatedEntitiesQueryResult(
            root_entity=root,
            related_entities=list(related_entities.values()),
            relations=list(relations.values()),
            evidence_paths=evidence_paths,
            evidence=self._repository.list_evidence(list(dict.fromkeys(evidence_ids))),
        )

    def query_decision_history(
        self, entity_or_experiment: str
    ) -> DecisionHistoryQueryResult:
        root = self._resolve_any_entity(entity_or_experiment)
        traces = self._repository.list_decision_traces(entity_id=root.id)
        if root.kind == EntityKind.EXPERIMENT:
            traces.extend(self._repository.list_decision_traces(experiment_id=root.id))
        deduped: dict[str, DecisionTrace] = {trace.id: trace for trace in traces}
        evidence_ids: list[str] = []
        for trace in deduped.values():
            evidence_ids.extend(trace.evidence_ids)
        return DecisionHistoryQueryResult(
            requested_entity=root,
            traces=sorted(deduped.values(), key=lambda item: item.timestamp),
            evidence=self._repository.list_evidence(list(dict.fromkeys(evidence_ids))),
        )

    def query_data_gaps(
        self,
        scope: str | None = None,
        filters: QueryFilters | None = None,
    ) -> list[DataGap]:
        filters = filters or QueryFilters()
        observations = self._repository.list_observations()
        observed_keys = {
            (item.material_id, item.mode_id, item.property_id) for item in observations
        }
        gaps: list[DataGap] = []
        for rule in self._repository.list_coverage_rules():
            if scope is not None and rule.scope != scope:
                continue
            materials = self._resolve_rule_entities(
                EntityKind.MATERIAL, rule.material_names
            )
            modes = self._resolve_rule_entities(EntityKind.MODE, rule.mode_names)
            properties = self._resolve_rule_entities(
                EntityKind.PROPERTY,
                rule.property_names,
            )
            for material_entity in materials:
                if filters.material_name and normalize_name(
                    material_entity.canonical_name
                ) != normalize_name(filters.material_name):
                    continue
                for mode_entity in modes:
                    if filters.mode_name and normalize_name(
                        mode_entity.canonical_name
                    ) != normalize_name(filters.mode_name):
                        continue
                    for property_entity in properties:
                        if filters.property_name and normalize_name(
                            property_entity.canonical_name
                        ) != normalize_name(filters.property_name):
                            continue
                        key = (
                            material_entity.id,
                            mode_entity.id,
                            property_entity.id,
                        )
                        if key in observed_keys:
                            continue
                        gaps.append(
                            DataGap(
                                id=_stable_id("gap", rule.rule_id, *key),
                                scope=rule.scope,
                                rule_id=rule.rule_id,
                                material_id=material_entity.id,
                                mode_id=mode_entity.id,
                                property_id=property_entity.id,
                                reason=(
                                    f"Missing observation for "
                                    f"{material_entity.canonical_name} / "
                                    f"{mode_entity.canonical_name} / "
                                    f"{property_entity.canonical_name}"
                                ),
                                metadata={"rule_name": rule.name},
                            )
                        )
        return gaps

    def answer_question(
        self,
        *,
        question: str,
        material: str | None = None,
        mode: str | None = None,
        property_name: str | None = None,
        source_ids: list[str] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Resolve a free-form research question into graph-backed answer parts."""
        warnings: list[str] = []
        matched_entities = self._match_entities_from_question(question)

        material_entity = self._resolve_filter_entity(
            EntityKind.MATERIAL,
            material,
            matched_entities,
            warnings,
        )
        mode_entity = self._resolve_filter_entity(
            EntityKind.MODE,
            mode,
            matched_entities,
            warnings,
        )
        property_entity = self._resolve_filter_entity(
            EntityKind.PROPERTY,
            property_name,
            matched_entities,
            warnings,
        )

        root_entity = (
            material_entity
            or property_entity
            or mode_entity
            or (matched_entities[0] if matched_entities else None)
        )
        experiments: list[Entity] = []
        observations: list[Observation] = []
        evidence: list[Evidence] = []
        findings: list[DecisionTrace] = []
        related_entities: list[Entity] = []
        relations: list[Relation] = []
        search_hits = (
            self._repository.search_text_units(question, limit=8) if question else []
        )

        if material_entity is not None:
            material_result = self.query_material_mode(
                material_entity.canonical_name,
                mode_entity.canonical_name if mode_entity else None,
                property_entity.canonical_name if property_entity else None,
            )
            experiments.extend(material_result.experiments)
            observations.extend(material_result.observations)
            evidence.extend(material_result.evidence)
            findings.extend(material_result.findings)
            search_hits = material_result.search_hits or search_hits
        elif property_entity is not None:
            property_result = self.query_property(property_entity.canonical_name)
            experiments.extend(property_result.experiments)
            observations.extend(property_result.observations)
            evidence.extend(property_result.evidence)

        if root_entity is not None:
            related = self.query_related(root_entity.canonical_name, depth=2)
            related_entities.extend(related.related_entities)
            relations.extend(related.relations)
            evidence.extend(related.evidence)
            history = self.query_decision_history(root_entity.canonical_name)
            findings.extend(history.traces)
            evidence.extend(history.evidence)
        elif not search_hits:
            warnings.append(
                "Не удалось сопоставить вопрос с загруженными сущностями графа."
            )

        filters = QueryFilters(
            material_name=material_entity.canonical_name if material_entity else None,
            mode_name=mode_entity.canonical_name if mode_entity else None,
            property_name=property_entity.canonical_name if property_entity else None,
        )
        data_gaps = self.query_data_gaps(filters=filters)
        if not observations and not data_gaps and root_entity is not None:
            warnings.append("Прямых измерений по распознанным сущностям не найдено.")

        evidence_deduped = self._dedupe_by_id(evidence)
        search_deduped = self._dedupe_by_id(search_hits)
        if source_ids is not None:
            source_set = set(source_ids)
            evidence_by_id = {e.id: e for e in evidence_deduped}
            matched_entities = [
                e for e in matched_entities if _entity_matches_sources(e, source_set)
            ]
            if material_entity is not None and not _entity_matches_sources(
                material_entity, source_set
            ):
                material_entity = None
            if mode_entity is not None and not _entity_matches_sources(
                mode_entity, source_set
            ):
                mode_entity = None
            if property_entity is not None and not _entity_matches_sources(
                property_entity, source_set
            ):
                property_entity = None
            experiments = [
                e
                for e in self._dedupe_entities(experiments)
                if _entity_matches_sources(e, source_set)
            ]
            observations = [
                o
                for o in self._dedupe_by_id(observations)
                if _observation_matches_sources(o, evidence_by_id, source_set)
            ]
            evidence_deduped = [
                e for e in evidence_deduped if _evidence_matches_sources(e, source_set)
            ]
            search_deduped = [
                h
                for h in search_deduped
                if h.source_entity_id in source_set
                or h.metadata.get("source_id") in source_set
                or h.metadata.get("source_file") in source_set
            ]
            findings = [
                t
                for t in self._dedupe_by_id(findings)
                if _trace_matches_sources(t, evidence_by_id, source_set)
            ]
            relations = [
                r
                for r in self._dedupe_by_id(relations)
                if _relation_matches_sources(r, evidence_by_id, source_set)
            ]
            related_entities = [
                e
                for e in self._dedupe_entities(related_entities)
                if _entity_matches_sources(e, source_set)
            ]
            data_gaps = [
                g
                for g in data_gaps
                if (g.material_id and g.material_id in source_set)
                or (g.mode_id and g.mode_id in source_set)
                or (g.property_id and g.property_id in source_set)
                or any(
                    _entity_matches_sources(e, source_set)
                    for e in self._repository.find_entities(
                        ids=[x for x in (g.material_id, g.mode_id, g.property_id) if x]
                    )
                )
            ]

        citations = self._build_citations(evidence_deduped, search_deduped)
        answer = self._build_answer_text(
            material_entity=material_entity,
            mode_entity=mode_entity,
            property_entity=property_entity,
            experiments=experiments,
            observations=observations,
            findings=findings,
            data_gaps=data_gaps,
            search_hits=search_deduped,
        )

        if self._llm:
            try:
                from kg_engine.llm_core.extraction import llm_generate_answer

                graph_context = {
                    "matched_entities": [
                        e.model_dump(mode="json") for e in matched_entities
                    ],
                    "experiments": [
                        e.model_dump(mode="json")
                        for e in self._dedupe_entities(experiments)
                    ],
                    "observations": [
                        o.model_dump(mode="json")
                        for o in self._dedupe_by_id(observations)
                    ],
                    "decision_history": [
                        t.model_dump(mode="json") for t in self._dedupe_by_id(findings)
                    ],
                    "data_gaps": [g.model_dump(mode="json") for g in data_gaps],
                    "search_hits": [h.model_dump(mode="json") for h in search_deduped],
                    "evidence": [e.model_dump(mode="json") for e in evidence_deduped],
                    "relations": [
                        r.model_dump(mode="json") for r in self._dedupe_by_id(relations)
                    ],
                }

                conversation_history: list[dict[str, str]] = []
                if self._session_store and session_id:
                    from kg_engine.config.settings import settings

                    conversation_history = self._session_store.get_context_messages(
                        session_id,
                        last_n=settings.session_history_turns,
                    )

                llm_answer = llm_generate_answer(
                    self._llm,
                    question,
                    graph_context,
                    conversation_history=conversation_history,
                )
                if llm_answer:
                    answer = llm_answer

                if self._session_store and session_id:
                    self._session_store.add_message(session_id, "user", question)
                    self._session_store.add_message(session_id, "assistant", answer)

            except Exception:
                logger.exception("LLM answer generation failed, using template answer")
        return {
            "question": question,
            "answer": answer,
            "resolved_query": {
                "material": material_entity.canonical_name if material_entity else None,
                "mode": mode_entity.canonical_name if mode_entity else None,
                "property_name": (
                    property_entity.canonical_name if property_entity else None
                ),
            },
            "matched_entities": [
                entity.model_dump(mode="json") for entity in matched_entities
            ],
            "experiments": [
                entity.model_dump(mode="json")
                for entity in self._dedupe_entities(experiments)
            ],
            "observations": [
                observation.model_dump(mode="json")
                for observation in self._dedupe_by_id(observations)
            ],
            "evidence": [item.model_dump(mode="json") for item in evidence_deduped],
            "citations": citations,
            "related_entities": [
                entity.model_dump(mode="json")
                for entity in self._dedupe_entities(related_entities)
            ],
            "relations": [
                relation.model_dump(mode="json")
                for relation in self._dedupe_by_id(relations)
            ],
            "decision_history": [
                trace.model_dump(mode="json") for trace in self._dedupe_by_id(findings)
            ],
            "data_gaps": [gap.model_dump(mode="json") for gap in data_gaps],
            "search_hits": [hit.model_dump(mode="json") for hit in search_deduped],
            "warnings": warnings,
        }

    async def answer_question_stream(
        self,
        *,
        question: str,
        material: str | None = None,
        mode: str | None = None,
        property_name: str | None = None,
        source_ids: list[str] | None = None,
        session_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream answer tokens for a research question.

        Yields string chunks as the LLM generates them.
        Falls back to sync answer if streaming is unavailable.
        """
        if not self._llm:
            result = self.answer_question(
                question=question,
                material=material,
                mode=mode,
                property_name=property_name,
                source_ids=source_ids,
                session_id=session_id,
            )
            yield result["answer"]
            return

        warnings: list[str] = []
        matched_entities = self._match_entities_from_question(question)
        material_entity = self._resolve_filter_entity(
            EntityKind.MATERIAL,
            material,
            matched_entities,
            warnings,
        )
        mode_entity = self._resolve_filter_entity(
            EntityKind.MODE,
            mode,
            matched_entities,
            warnings,
        )
        property_entity = self._resolve_filter_entity(
            EntityKind.PROPERTY,
            property_name,
            matched_entities,
            warnings,
        )

        graph_context: dict[str, Any] = {}
        if source_ids is not None:
            source_set = set(source_ids)
            matched_entities = [
                e for e in matched_entities if _entity_matches_sources(e, source_set)
            ]
            if material_entity is not None and not _entity_matches_sources(
                material_entity, source_set
            ):
                material_entity = None
            if mode_entity is not None and not _entity_matches_sources(
                mode_entity, source_set
            ):
                mode_entity = None
            if property_entity is not None and not _entity_matches_sources(
                property_entity, source_set
            ):
                property_entity = None
        if material_entity is not None:
            material_result = self.query_material_mode(
                material_entity.canonical_name,
                mode_entity.canonical_name if mode_entity else None,
                property_entity.canonical_name if property_entity else None,
            )
            experiments = self._dedupe_entities(material_result.experiments)
            observations = self._dedupe_by_id(material_result.observations)
            evidence = self._dedupe_by_id(material_result.evidence)
            if source_ids is not None:
                source_set = set(source_ids)
                evidence_by_id = {e.id: e for e in evidence}
                experiments = [
                    e for e in experiments if _entity_matches_sources(e, source_set)
                ]
                observations = [
                    o
                    for o in observations
                    if _observation_matches_sources(o, evidence_by_id, source_set)
                ]
                evidence = [
                    e for e in evidence if _evidence_matches_sources(e, source_set)
                ]
            graph_context = {
                "matched_entities": [
                    e.model_dump(mode="json") for e in matched_entities
                ],
                "experiments": [e.model_dump(mode="json") for e in experiments],
                "observations": [o.model_dump(mode="json") for o in observations],
                "evidence": [e.model_dump(mode="json") for e in evidence],
            }

        conversation_history: list[dict[str, str]] = []
        if self._session_store and session_id:
            from kg_engine.config.settings import settings

            conversation_history = self._session_store.get_context_messages(
                session_id,
                last_n=settings.session_history_turns,
            )

        full_answer_parts: list[str] = []
        try:
            from kg_engine.llm_core.extraction import _build_graph_context_str

            context_str = (
                _build_graph_context_str(graph_context)
                if graph_context
                else "No data found."
            )

            system_prompt = (
                "You are a materials science research assistant.\n\n"
                "RULES (mandatory):\n"
                "1. Answer questions based ONLY on the knowledge graph data provided below. "
                "Do NOT invent, assume, or fabricate any facts, measurements, or entity relationships "
                "that are not explicitly present in the provided data.\n"
                "2. For each claim in your answer, reference the source: mention the source_id "
                "and the specific fragment or measurement value you are citing.\n"
                "3. If the provided data does not contain enough information to answer the question, "
                "state explicitly: 'Недостаточно данных в загруженных источниках для полного ответа.' "
                "Do NOT guess or fill gaps with general knowledge.\n"
                "4. Be specific: cite measurements with values and units.\n"
                "5. Answer in the same language as the question.\n"
                "6. If you identify data gaps (missing experiments, unmeasured properties), mention them."
            )

            user_content = (
                f"Knowledge graph data:\n{context_str}\n\nQuestion: {question}"
            )

            messages: list[dict[str, str]] = []
            if conversation_history:
                for hist_msg in conversation_history[-10:]:
                    messages.append(
                        {"role": hist_msg["role"], "content": hist_msg["content"]}
                    )
            messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_content})

            async for chunk in self._llm.chat_stream(
                messages, temperature=0.3, max_tokens=1024
            ):
                full_answer_parts.append(chunk)
                yield chunk

        except Exception:
            logger.exception("LLM streaming failed, falling back to sync answer")
            result = self.answer_question(
                question=question,
                material=material,
                mode=mode,
                property_name=property_name,
                source_ids=source_ids,
                session_id=session_id,
            )
            yield result["answer"]
            return

        if self._session_store and session_id:
            full_answer = "".join(full_answer_parts)
            self._session_store.add_message(session_id, "user", question)
            self._session_store.add_message(session_id, "assistant", full_answer)

    def generate_hypotheses(
        self,
        request: HypothesisInput,
    ) -> HypothesisGenerationResult:
        """Generate transparent, graph-grounded research hypotheses for a KPI."""
        warnings: list[str] = []
        lookup_text = " ".join(
            item for item in (request.target_kpi, request.question) if item
        )
        matched_entities = self._match_entities_from_question(lookup_text)
        material_entity = self._resolve_filter_entity(
            EntityKind.MATERIAL,
            request.material,
            matched_entities,
            warnings,
        )
        mode_entity = self._resolve_filter_entity(
            EntityKind.MODE,
            request.mode,
            matched_entities,
            warnings,
        )
        property_entity = self._resolve_filter_entity(
            EntityKind.PROPERTY,
            request.property_name,
            matched_entities,
            warnings,
        )
        if property_entity is None:
            property_entity = self._resolve_filter_entity(
                EntityKind.PROPERTY,
                request.target_kpi,
                matched_entities,
                warnings=[],
            )

        filters = QueryFilters(
            material_name=material_entity.canonical_name if material_entity else None,
            mode_name=mode_entity.canonical_name if mode_entity else None,
            property_name=property_entity.canonical_name if property_entity else None,
        )
        observations = self._collect_hypothesis_observations(
            material_entity,
            mode_entity,
            property_entity,
        )
        evidence = self._repository.list_evidence(
            list(
                dict.fromkeys(
                    observation.evidence_id
                    for observation in observations
                    if observation.evidence_id
                )
            )
        )
        data_gaps = self.query_data_gaps(filters=filters)

        if request.source_ids is not None:
            source_set = set(request.source_ids)
            evidence_by_id = {e.id: e for e in evidence}
            observations = [
                o
                for o in observations
                if _observation_matches_sources(o, evidence_by_id, source_set)
            ]
            evidence = [e for e in evidence if _evidence_matches_sources(e, source_set)]
            data_gaps = [
                g
                for g in data_gaps
                if all(
                    _entity_matches_sources(e, source_set)
                    for e in self._repository.find_entities(
                        ids=[x for x in (g.material_id, g.mode_id, g.property_id) if x]
                    )
                )
            ]

        total_observations = len(observations)
        total_evidence = len(evidence)
        avg_evidence_confidence = (
            fmean([ev.confidence for ev in evidence]) if evidence else 0.0
        )
        avg_observation_confidence = (
            fmean([obs.confidence for obs in observations]) if observations else 0.0
        )

        hypotheses: list[ResearchHypothesis] = []

        for gap in data_gaps:
            mat_name = self._entity_name(gap.material_id, "material")
            mode_name = self._entity_name(gap.mode_id, "mode")
            prop_name = self._entity_name(
                gap.property_id,
                property_entity.canonical_name
                if property_entity
                else request.target_kpi,
            )

            novelty = min(1.0, 0.7 + 0.3 * (1.0 - min(total_observations / 20.0, 1.0)))
            risk = 0.45 + 0.2 * (1.0 - avg_evidence_confidence)
            value = 0.7 + 0.15 * (1.0 - min(total_evidence / 30.0, 1.0))
            evidence_strength = avg_observation_confidence * 0.3

            conflicting_for_prop = sum(
                1
                for obs in observations
                if obs.property_id == gap.property_id and obs.mode_id == gap.mode_id
            )

            score = self._hypothesis_score(
                novelty=novelty,
                risk=risk,
                value=value,
                evidence_strength=evidence_strength,
            )
            hypotheses.append(
                ResearchHypothesis(
                    id=_stable_id("hyp", request.target_kpi, gap.id),
                    target_kpi=request.target_kpi,
                    statement=(
                        f"Проверить, улучшает ли режим {mode_name} для {mat_name} "
                        f"целевой KPI '{prop_name}'."
                    ),
                    rationale=(
                        f"Правило покрытия '{gap.metadata.get('rule_name', gap.rule_id)}' "
                        f"требует измерения {prop_name} для {mat_name}/{mode_name}, "
                        f"но данные отсутствуют ({gap.reason}). "
                        "Пробел является проверяемой гипотезой."
                    ),
                    test_plan=(
                        f"Провести эксперимент {mat_name} / {mode_name}; измерить "
                        f"{prop_name}; сохранить row-level evidence; сравнить с "
                        "существующими режимами и другими материалами."
                    ),
                    score=score,
                    supporting_entity_ids=[
                        item
                        for item in (gap.material_id, gap.mode_id, gap.property_id)
                        if item
                    ],
                    data_gap_ids=[gap.id],
                    assumptions=[
                        "Coverage rule отражает реальную матрицу исследований.",
                        "Отсутствие observation = непроверенная область, не отрицательный результат.",
                    ],
                    novelty_rationale=(
                        f"Нет измерений {prop_name} для {mat_name}/{mode_name} — "
                        f"область полностью неизучена ({total_observations} observations в графе)."
                    ),
                    risk_items=[
                        "Эксперимент может потребовать оборудования, отсутствующего в базе.",
                        f"Есть {conflicting_for_prop} связанных observations — возможны конфликты.",
                        "Отсутствие baseline для сравнения без дополнительных замеров.",
                    ],
                    value_rationale=(
                        f"Заполнение пробела в coverage matrix для {prop_name} "
                        f"повысит полноту данных на {100 // max(total_observations + 1, 1)}%."
                    ),
                    logic_trace=[
                        f"1. Загружено {total_observations} observations, {total_evidence} evidence.",
                        f"2. Coverage rule '{gap.metadata.get('rule_name', gap.rule_id)}' требует {prop_name} для {mat_name}/{mode_name}.",
                        "3. Observation для этой связки отсутствует → data gap.",
                        f"4. novelty={novelty:.2f} (нет данных), risk={risk:.2f}, value={value:.2f}.",
                    ],
                    validation_checks=[
                        f"Проверить наличие оборудования для {mode_name}.",
                        "Убедиться, что KPI измеряется в той же единице.",
                    ],
                    falsification_criteria=[
                        f"Гипотеза falsified, если эксперимент покажет, что {prop_name} не зависит от {mode_name}.",
                        "Гипотеза falsified, если существующие данные уже покрывают эту связку.",
                    ],
                    required_evidence=[
                        f"Измерение {prop_name} для {mat_name}/{mode_name}.",
                        "Контрольный замер для baseline-сравнения.",
                    ],
                    metadata={"source": "coverage_gap"},
                )
            )

        for observation in observations:
            mat_name = self._entity_name(observation.material_id, "material")
            mode_name = self._entity_name(observation.mode_id, "mode")
            prop_name = self._entity_name(observation.property_id, request.target_kpi)
            evidence_item = self._repository.get_evidence(observation.evidence_id)
            evidence_strength = observation.confidence
            if evidence_item is not None:
                evidence_strength = fmean(
                    [observation.confidence, evidence_item.confidence]
                )

            conflicting_count = sum(
                1
                for obs in observations
                if obs.property_id == observation.property_id
                and obs.mode_id == observation.mode_id
                and obs.value is not None
                and observation.value is not None
                and abs(obs.value - observation.value)
                / max(abs(observation.value), 1e-10)
                > 0.15
            )
            same_obs_count = sum(
                1
                for obs in observations
                if obs.property_id == observation.property_id
                and obs.mode_id == observation.mode_id
            )
            novelty = max(
                0.2,
                0.6
                - 0.1 * conflicting_count
                - 0.05 * min(total_observations / 10.0, 0.3),
            )
            risk = max(0.15, 0.3 - 0.1 * evidence_strength + 0.05 * conflicting_count)
            value = min(
                1.0,
                0.65
                + 0.15 * evidence_strength
                + 0.05 * min(total_evidence / 15.0, 0.2),
            )

            value_text = (
                f"{observation.value:g} {observation.unit or ''}".strip()
                if observation.value is not None
                else "наблюдаемый эффект"
            )
            score = self._hypothesis_score(
                novelty=novelty,
                risk=risk,
                value=value,
                evidence_strength=evidence_strength,
            )
            hypotheses.append(
                ResearchHypothesis(
                    id=_stable_id("hyp", request.target_kpi, observation.id),
                    target_kpi=request.target_kpi,
                    statement=(
                        f"Использовать связку {mat_name} / {mode_name} как основу "
                        f"для повышения KPI '{prop_name}'."
                    ),
                    rationale=(
                        f"В графе есть измерение {prop_name}: {value_text} "
                        f"(confidence={evidence_strength:.2f}). "
                        "Гипотеза опирается на существующее observation и может быть "
                        "проверена вариацией режима."
                    ),
                    test_plan=(
                        f"Повторить эксперимент для {mat_name} / {mode_name}, затем "
                        f"изменить один параметр и сравнить {prop_name} с базовым "
                        f"значением {value_text}."
                    ),
                    score=score,
                    supporting_entity_ids=[
                        item
                        for item in (
                            observation.material_id,
                            observation.mode_id,
                            observation.property_id,
                            observation.experiment_id,
                        )
                        if item
                    ],
                    supporting_evidence_ids=[observation.evidence_id],
                    supporting_observation_ids=[observation.id],
                    assumptions=[
                        "Историческое измерение воспроизводимо в текущей лабораторной базе.",
                        "Изменение режима сравнивается с тем же KPI и единицами измерения.",
                    ],
                    novelty_rationale=(
                        f"Есть {same_obs_count} observations для {prop_name}/{mode_name}, "
                        f"{conflicting_count} конфликтующих — {'низкая' if conflicting_count > 2 else 'умеренная'} новизна."
                    ),
                    risk_items=[
                        f"Конфликтующие данные ({conflicting_count} observations) могут указывать на нестабильность.",
                        "Воспроизводимость зависит от точного воспроизведения условий.",
                    ],
                    value_rationale=(
                        f"Подтвержденное значение {value_text} (confidence={evidence_strength:.2f}) "
                        "даёт reproducible baseline для оптимизации."
                    ),
                    logic_trace=[
                        f"1. Observation {observation.id}: {value_text} (confidence={evidence_strength:.2f}).",
                        f"2. {same_obs_count} observations для этой связки, {conflicting_count} конфликтующих.",
                        f"3. novelty={novelty:.2f}, risk={risk:.2f}, value={value:.2f}.",
                    ],
                    validation_checks=[
                        "Проверить, что измерение проводилось в одинаковых условиях.",
                        "Убедиться в воспроизводимости equipment/mode.",
                    ],
                    falsification_criteria=[
                        f"Гипотеза falsified, если повторный замер отклоняется >20% от {value_text}.",
                        "Гипотеза falsified, если оптимизация режима не приводит к росту KPI.",
                    ],
                    required_evidence=[
                        f"Повторный замер {prop_name} для {mat_name}/{mode_name}.",
                        "Baseline comparison с контрольной группой.",
                    ],
                    metadata={"source": "observed_effect"},
                )
            )

        if request.expert_adjustments:
            for hypothesis in hypotheses:
                adj = request.expert_adjustments.get(hypothesis.id)
                if adj is None:
                    note = "Учтены общие экспертные корректировки: " + ", ".join(
                        sorted(request.expert_adjustments)
                    )
                    hypothesis.expert_notes.append(note)
                elif isinstance(adj, dict):
                    if adj.get("reject"):
                        hypothesis.score = HypothesisScore(
                            novelty=0,
                            risk=1.0,
                            value=0,
                            evidence_strength=0,
                            final_score=0,
                        )
                    else:
                        new_novelty = hypothesis.score.novelty
                        new_risk = hypothesis.score.risk
                        new_value = hypothesis.score.value
                        new_ev = hypothesis.score.evidence_strength
                        if "risk_adjustment" in adj:
                            new_risk = max(
                                0.0, min(1.0, new_risk + adj["risk_adjustment"])
                            )
                        if "value_adjustment" in adj:
                            new_value = max(
                                0.0, min(1.0, new_value + adj["value_adjustment"])
                            )
                        if "novelty_adjustment" in adj:
                            new_novelty = max(
                                0.0, min(1.0, new_novelty + adj["novelty_adjustment"])
                            )
                        if "evidence_strength_adjustment" in adj:
                            new_ev = max(
                                0.0,
                                min(1.0, new_ev + adj["evidence_strength_adjustment"]),
                            )
                        if "score_override" in adj:
                            final = max(0.0, min(1.0, adj["score_override"]))
                        else:
                            final = (
                                0.35 * new_value
                                + 0.25 * new_ev
                                + 0.20 * new_novelty
                                + 0.20 * (1.0 - new_risk)
                            )
                            final = max(0.0, min(1.0, final))
                        hypothesis.score = HypothesisScore(
                            novelty=new_novelty,
                            risk=new_risk,
                            value=new_value,
                            evidence_strength=new_ev,
                            final_score=final,
                        )
                    if "note" in adj:
                        hypothesis.expert_notes.append(adj["note"])

        hypotheses.sort(key=lambda item: item.score.final_score, reverse=True)
        hypotheses = hypotheses[: request.max_hypotheses]
        if not hypotheses:
            warnings.append(
                "Не удалось построить гипотезы: загрузите источники или уточните KPI/material/mode/property."
            )
        return HypothesisGenerationResult(
            target_kpi=request.target_kpi,
            resolved_query={
                "material": material_entity.canonical_name if material_entity else None,
                "mode": mode_entity.canonical_name if mode_entity else None,
                "property_name": (
                    property_entity.canonical_name if property_entity else None
                ),
            },
            hypotheses=hypotheses,
            evidence=evidence,
            observations=self._dedupe_by_id(observations),
            data_gaps=data_gaps,
            matched_entities=matched_entities,
            warnings=warnings,
        )

    def _collect_hypothesis_observations(
        self,
        material_entity: Entity | None,
        mode_entity: Entity | None,
        property_entity: Entity | None,
    ) -> list[Observation]:
        if material_entity is not None:
            result = self.query_material_mode(
                material_entity.canonical_name,
                mode_entity.canonical_name if mode_entity else None,
                property_entity.canonical_name if property_entity else None,
            )
            return self._dedupe_by_id(result.observations)
        if property_entity is not None:
            result = self.query_property(property_entity.canonical_name)
            return self._dedupe_by_id(result.observations)
        return self._repository.list_observations()

    def _hypothesis_score(
        self,
        *,
        novelty: float,
        risk: float,
        value: float,
        evidence_strength: float,
    ) -> HypothesisScore:
        final_score = (
            0.35 * value
            + 0.25 * evidence_strength
            + 0.20 * novelty
            + 0.20 * (1.0 - risk)
        )
        return HypothesisScore(
            novelty=max(0.0, min(1.0, novelty)),
            risk=max(0.0, min(1.0, risk)),
            value=max(0.0, min(1.0, value)),
            evidence_strength=max(0.0, min(1.0, evidence_strength)),
            final_score=max(0.0, min(1.0, final_score)),
        )

    def _entity_name(self, entity_id: str | None, fallback: str) -> str:
        if entity_id is None:
            return fallback
        entity = self._repository.get_entity(entity_id)
        return entity.canonical_name if entity is not None else fallback

    def _build_citations(
        self,
        evidence: list[Evidence],
        search_hits: list[SearchTextUnit],
    ) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in evidence[:12]:
            key = f"{item.source_id}:{item.span.fragment or item.extraction_method}"
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                {
                    "id": item.id,
                    "source_id": item.source_id,
                    "source_kind": item.source_kind.value,
                    "fragment": item.span.fragment or item.extraction_method,
                    "section": item.span.section,
                    "row_reference": item.span.row_reference,
                    "confidence": item.confidence,
                }
            )
        for hit in search_hits[:5]:
            key = f"search:{hit.id}"
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                {
                    "id": hit.id,
                    "source_id": hit.source_entity_id,
                    "source_kind": hit.source_kind.value,
                    "fragment": hit.content[:200],
                    "section": None,
                    "row_reference": None,
                    "confidence": 1.0,
                }
            )
        return citations

    def get_source_overview(self) -> dict[str, Any]:
        """Generate overview of all loaded sources."""
        entities = self._repository.find_entities()
        observations = self._repository.list_observations()
        relations = self._repository.list_relations()
        evidence_ids = [obs.evidence_id for obs in observations if obs.evidence_id]
        evidence_all = (
            self._repository.list_evidence(evidence_ids) if evidence_ids else []
        )
        by_kind: dict[str, int] = {}
        for e in entities:
            by_kind[e.kind.value] = by_kind.get(e.kind.value, 0) + 1
        source_files: set[str] = set()
        for e in entities:
            for ref in e.source_refs:
                source_files.add(ref)
            props = e.properties
            for key in ("source_file", "source_ref", "_uploaded_from"):
                val = props.get(key)
                if val:
                    source_files.add(val)
        for ev in evidence_all:
            meta = ev.metadata
            if meta.get("source_file"):
                source_files.add(meta["source_file"])
            elif meta.get("source_ref"):
                source_files.add(meta["source_ref"])
            else:
                source_files.add(ev.source_id)
        return {
            "total_entities": len(entities),
            "by_kind": by_kind,
            "total_observations": len(observations),
            "total_relations": len(relations),
            "total_evidence": len(evidence_all),
            "source_files": sorted(source_files),
            "summary": (
                f"Загружено {len(entities)} сущностей "
                f"({', '.join(f'{k}: {v}' for k, v in sorted(by_kind.items()))}), "
                f"{len(observations)} измерений, {len(relations)} связей, "
                f"{len(evidence_all)} доказательств из {len(source_files)} файлов."
            ),
        }

    def get_suggested_questions(self) -> list[str]:
        """Suggest follow-up questions based on loaded data."""
        entities = self._repository.find_entities()
        by_kind: dict[EntityKind, list[Entity]] = {}
        for e in entities:
            by_kind.setdefault(e.kind, []).append(e)
        suggestions: list[str] = []
        materials = by_kind.get(EntityKind.MATERIAL, [])
        properties = by_kind.get(EntityKind.PROPERTY, [])
        modes = by_kind.get(EntityKind.MODE, [])
        teams = by_kind.get(EntityKind.TEAM, [])
        equipment = by_kind.get(EntityKind.EQUIPMENT, [])
        if materials and modes:
            m = materials[0]
            mo = modes[0]
            suggestions.append(
                f"Что уже делали по {m.canonical_name} при режиме {mo.canonical_name}?"
            )
        if materials and properties:
            m = materials[0]
            p = properties[0]
            suggestions.append(f"Какие свойства измеряли для {m.canonical_name}?")
        if properties:
            p = properties[0]
            suggestions.append(f"Где есть пробелы по {p.canonical_name}?")
        if materials:
            for m in materials[:2]:
                suggestions.append(f"Какие документы связаны с {m.canonical_name}?")
        if teams:
            t = teams[0]
            suggestions.append(f"Какие эксперименты выполняла {t.canonical_name}?")
        if equipment:
            eq = equipment[0]
            suggestions.append(f"Где использовали {eq.canonical_name}?")
        if not suggestions:
            suggestions = [
                "Какие материалы загружены в систему?",
                "Какие эксперименты есть в базе?",
                "Какие свойства измерялись?",
                "Где есть пробелы в данных?",
            ]
        return suggestions[:6]

    def _match_entities_from_question(self, question: str) -> list[Entity]:
        normalized_question = normalize_name(question)
        if not normalized_question:
            return []
        scored: list[tuple[int, Entity]] = []
        for entity in self._repository.find_entities():
            names = [entity.canonical_name, *entity.aliases]
            score = 0
            for name in names:
                normalized_name = normalize_name(name)
                if len(normalized_name) < 3:
                    continue
                if normalized_name in normalized_question:
                    score = max(score, len(normalized_name))
            if score:
                scored.append((score, entity))
        scored.sort(key=lambda item: (item[0], item[1].kind.value), reverse=True)
        return [entity for _, entity in scored]

    def _resolve_filter_entity(
        self,
        kind: EntityKind,
        explicit_name: str | None,
        matched_entities: list[Entity],
        warnings: list[str],
    ) -> Entity | None:
        if explicit_name:
            entity = self._repository.resolve_entity(kind, explicit_name)
            if entity is None:
                warnings.append(
                    f"Фильтр '{explicit_name}' не найден среди сущностей типа {kind.value}."
                )
            return entity
        for entity in matched_entities:
            if entity.kind == kind:
                return entity
        return None

    def _build_answer_text(
        self,
        *,
        material_entity: Entity | None,
        mode_entity: Entity | None,
        property_entity: Entity | None,
        experiments: list[Entity],
        observations: list[Observation],
        findings: list[DecisionTrace],
        data_gaps: list[DataGap],
        search_hits: list[SearchTextUnit],
    ) -> str:
        parts: list[str] = []
        context = " / ".join(
            item.canonical_name
            for item in (material_entity, mode_entity, property_entity)
            if item is not None
        )
        if observations:
            values = [
                f"{item.value:g} {item.unit or ''}".strip()
                for item in observations
                if item.value is not None
            ]
            value_text = ", ".join(values[:5]) if values else "без числовых значений"
            parts.append(
                f"Найдено экспериментов: {len(self._dedupe_entities(experiments))}; "
                f"измерений: {len(self._dedupe_by_id(observations))}. "
                f"Значения: {value_text}."
            )
        elif experiments:
            parts.append(
                f"Найдены связанные эксперименты: {len(self._dedupe_entities(experiments))}, "
                "но прямые измерения для уточненного вопроса не найдены."
            )
        elif search_hits:
            parts.append(
                "Прямых структурированных измерений не найдено, но есть текстовые "
                "фрагменты в документах и описаниях экспериментов."
            )
        else:
            parts.append("По загруженным данным прямых совпадений не найдено.")
        if findings:
            summaries = [trace.summary for trace in self._dedupe_by_id(findings)[:3]]
            parts.append("Выводы: " + " ".join(summaries))
        if data_gaps:
            parts.append(
                f"Пробелы данных: {len(data_gaps)} ожидаемых связок без измерений."
            )
        if context:
            parts.insert(0, f"Контекст запроса: {context}.")
        return " ".join(parts)

    def _dedupe_entities(self, entities: list[Entity]) -> list[Entity]:
        return list({entity.id: entity for entity in entities}.values())

    def _dedupe_by_id(self, items: list[Any]) -> list[Any]:
        return list({item.id: item for item in items}.values())

    def _create_observation(
        self,
        *,
        experiment: ExperimentInput,
        experiment_entity: Entity,
        material: Entity,
        mode_entity: Entity | None,
        observation_input: ObservationInput,
        provenance_ref: str | None = None,
    ) -> Observation:
        src = provenance_ref or experiment.source_ref or experiment.experiment_id
        property_entity = self._ensure_entity(
            EntityKind.PROPERTY,
            observation_input.property_name,
            source_ref=src,
        )
        evidence = self._create_evidence(
            source_kind=SourceKind.EXPERIMENT,
            source_id=src,
            fragment=observation_input.fragment,
            row_reference=observation_input.row_reference,
            extraction_method=observation_input.extraction_method,
            confidence=observation_input.confidence,
            version=experiment.source_version,
            metadata={**observation_input.metadata, "source_file": src},
        )
        observation = Observation(
            id=_stable_id(
                "obs",
                experiment.experiment_id,
                material.id,
                property_entity.id,
                mode_entity.id if mode_entity else None,
                observation_input.value,
                observation_input.unit,
                observation_input.row_reference,
            ),
            material_id=material.id,
            property_id=property_entity.id,
            experiment_id=experiment_entity.id,
            mode_id=mode_entity.id if mode_entity else None,
            value=observation_input.value,
            unit=observation_input.unit,
            comparator=observation_input.comparator,
            evidence_id=evidence.id,
            confidence=observation_input.confidence,
            observed_at=observation_input.observed_at,
            metadata=observation_input.metadata,
        )
        self._repository.upsert_observation(observation)
        self._link_entities(
            experiment_entity.id,
            property_entity.id,
            RelationType.MEASURES_PROPERTY,
            evidence_ids=[evidence.id],
            properties={
                "value": observation.value,
                "unit": observation.unit,
                "comparator": observation.comparator,
            },
        )
        return observation

    def _create_trace(
        self,
        *,
        finding: FindingInput,
        source_kind: SourceKind,
        source_id: str,
        entity_ids: list[str],
        experiment_id: str | None,
        observation_ids: list[str],
        trace_id: str,
        version: str | None = None,
    ) -> DecisionTrace:
        evidence = self._create_evidence(
            source_kind=source_kind,
            source_id=source_id,
            fragment=finding.fragment or finding.summary,
            extraction_method=finding.extraction_method,
            confidence=finding.confidence,
            version=version,
            metadata=finding.metadata,
        )
        trace = DecisionTrace(
            id=trace_id,
            summary=finding.summary,
            decision=finding.decision,
            entity_ids=list(dict.fromkeys(entity_ids)),
            experiment_id=experiment_id,
            observation_ids=observation_ids,
            evidence_ids=[evidence.id],
            changed_from_trace_id=finding.changed_from_trace_id,
            confidence=finding.confidence,
            metadata=finding.metadata,
        )
        self._repository.upsert_decision_trace(trace)
        return trace

    def _upsert_reference_entity(self, record: CanonicalEntityInput) -> Entity:
        entity_id = record.canonical_id or _stable_id(record.kind.value, record.name)
        entity = Entity(
            id=entity_id,
            kind=record.kind,
            canonical_name=record.name,
            aliases=record.aliases,
            properties=record.properties,
            source_refs=[record.source_ref] if record.source_ref else [],
        )
        return self._repository.upsert_entity(entity)

    def _ensure_entity(
        self,
        kind: EntityKind,
        name: str,
        *,
        entity_id: str | None = None,
        aliases: list[str] | None = None,
        source_ref: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> Entity:
        existing = self._repository.resolve_entity(kind, name)
        if existing is not None:
            updates: dict[str, Any] = {
                "aliases": list({*existing.aliases, *(aliases or [])}),
                "properties": {**existing.properties, **(properties or {})},
                "source_refs": list(
                    {
                        *existing.source_refs,
                        *([source_ref] if source_ref else []),
                    }
                ),
            }
            return self._repository.upsert_entity(existing.model_copy(update=updates))
        entity = Entity(
            id=entity_id or _stable_id(kind.value, name),
            kind=kind,
            canonical_name=name,
            aliases=aliases or [],
            properties=properties or {},
            source_refs=[source_ref] if source_ref else [],
        )
        return self._repository.upsert_entity(entity)

    def _create_evidence(
        self,
        *,
        source_kind: SourceKind,
        source_id: str,
        fragment: str | None,
        extraction_method: str,
        confidence: float = 1.0,
        row_reference: str | None = None,
        version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Evidence:
        evidence = Evidence(
            id=_stable_id(
                "evidence",
                source_kind.value,
                source_id,
                fragment,
                extraction_method,
                row_reference,
            ),
            source_kind=source_kind,
            source_id=source_id,
            span=SourceSpan(fragment=fragment, row_reference=row_reference),
            extraction_method=extraction_method,
            confidence=confidence,
            version=version,
            metadata=metadata or {},
        )
        return self._repository.upsert_evidence(evidence)

    def _link_entities(
        self,
        source_entity_id: str,
        target_entity_id: str,
        relation_type: RelationType,
        *,
        evidence_ids: list[str],
        properties: dict[str, Any] | None = None,
    ) -> Relation:
        relation = Relation(
            id=_stable_id(
                "rel",
                relation_type.value,
                source_entity_id,
                target_entity_id,
            ),
            relation_type=relation_type,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            evidence_ids=evidence_ids,
            properties=properties or {},
        )
        return self._repository.upsert_relation(relation)

    def _resolve_rule_entities(
        self,
        kind: EntityKind,
        names: list[str],
    ) -> list[Entity]:
        entities: list[Entity] = []
        for name in names:
            entity = self._repository.resolve_entity(kind, name)
            if entity is not None:
                entities.append(entity)
        return entities

    def _require_entity(self, kind: EntityKind, raw_name: str) -> Entity:
        entity = self._repository.resolve_entity(kind, raw_name)
        if entity is None:
            raise ValueError(f"{kind.value.title()} '{raw_name}' not found")
        return entity

    def _resolve_any_entity(self, raw_name: str) -> Entity:
        for kind in EntityKind:
            entity = self._repository.resolve_entity(kind, raw_name)
            if entity is not None:
                return entity
        raise ValueError(f"Entity '{raw_name}' not found")
