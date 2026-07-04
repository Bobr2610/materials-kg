"""Graph-first service layer for materials knowledge graph ingestion and query."""

from __future__ import annotations

import hashlib
import asyncio
import inspect
import json
import logging
from collections import deque
from pathlib import Path
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
from kg_engine.domain.models import ResearchHypothesis
from kg_engine.domain.models import SearchTextUnit
from kg_engine.domain.models import SourceKind
from kg_engine.domain.models import SourceSpan
from kg_engine.domain.models import TextUnitInput
from kg_engine.domain.product import DecisionGate
from kg_engine.domain.product import ExpectedEffect
from kg_engine.domain.product import ExperimentStep
from kg_engine.domain.product import RequiredResource
from kg_engine.domain.product import VerificationRoadmap
from kg_engine.domain.resolution import normalize_name
from kg_engine.repositories.protocols import MaterialsKGRepository
from kg_engine.services.hypothesis_adjustments import EXPERT_ADJUSTMENT_SCHEMA
from kg_engine.services.hypothesis_adjustments import apply_expert_adjustments
from kg_engine.services.hypothesis_adjustments import calculate_final_score
from kg_engine.services.hypothesis_adjustments import clamp_score

logger = logging.getLogger(__name__)

_FALLBACK_SEMANTIC_TEXT_MAX_CHARS = 1400
_FALLBACK_IMPORTANT_TERMS = (
    "material",
    "alloy",
    "sample",
    "property",
    "temperature",
    "strength",
    "hardness",
    "conductivity",
    "mpa",
    "gpa",
    "hv",
    "hrc",
    "iacs",
    "CuCrZr",
    "Ti-6Al",
    "316L",
    "материал",
    "образец",
    "свойство",
    "температура",
    "прочность",
    "твердость",
    "твёрдость",
)
_SOURCE_DOCUMENT_TAG = "source_document"


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "::".join(str(part) for part in parts if part is not None)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _merge_source_refs(
    existing_refs: list[str] | None,
    *,
    source_ref: str | None,
    upload_file: str | None,
) -> list[str]:
    refs = set(existing_refs or [])
    if source_ref:
        refs.add(source_ref)
    if upload_file:
        refs.add(upload_file)
    return list(refs)


def _source_key_variants(value: Any) -> set[str]:
    if value is None:
        return set()
    normalized = str(value).strip().replace("\\", "/")
    if not normalized:
        return set()
    parts = [part for part in normalized.split("/") if part]
    variants = {normalized.casefold()}
    for idx in range(len(parts)):
        variants.add("/".join(parts[idx:]).casefold())
    return variants


def _expand_source_set(source_set: set[str]) -> set[str]:
    expanded: set[str] = set()
    for item in source_set:
        expanded.update(_source_key_variants(item))
    return expanded


def _source_matches(value: Any, source_set: set[str]) -> bool:
    return bool(_source_key_variants(value) & source_set)


def _hypothesis_mentions_any(
    hypothesis: ResearchHypothesis,
    excluded_terms: list[str],
) -> bool:
    if not excluded_terms:
        return False
    searchable = " ".join(
        [
            hypothesis.statement,
            hypothesis.rationale,
            hypothesis.test_plan,
            hypothesis.mechanism,
        ]
    ).casefold()
    return any(term in searchable for term in excluded_terms)


def _compact_document_text_for_storage(text: str, *, document_id: str) -> tuple[str, dict[str, Any]]:
    """Keep fallback document text units compact when parser text_units are absent."""
    lines = [" ".join(line.strip().split()) for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return "", {
            "semantic_unit": True,
            "semantic_method": "fallback_document_compaction_v1",
            "source_text_chars": len(text),
            "stored_text_chars": 0,
            "storage_policy": "meaning_with_document_provenance",
        }

    selected: list[str] = []
    selected_indices = set(range(min(2, len(lines))))
    scored = sorted(
        (
            (
                _fallback_semantic_line_score(line, idx),
                idx,
            )
            for idx, line in enumerate(lines)
        ),
        key=lambda item: (-item[0], item[1]),
    )
    for score, idx in scored:
        if len(selected_indices) >= 14:
            break
        if score <= 0:
            continue
        selected_indices.add(idx)
    if len(selected) < min(4, len(lines)):
        for idx in range(len(lines)):
            selected_indices.add(idx)
            if len(selected_indices) >= min(4, len(lines)):
                break
    selected = [lines[idx] for idx in sorted(selected_indices)]

    content = (
        f"Meaning from {document_id}; page unknown; storage=fallback semantic. "
        f"Semantic summary: {' / '.join(selected)}"
    )
    if len(content) > _FALLBACK_SEMANTIC_TEXT_MAX_CHARS:
        content = content[: _FALLBACK_SEMANTIC_TEXT_MAX_CHARS - 3].rstrip() + "..."
    metadata = {
        "semantic_unit": True,
        "semantic_method": "fallback_document_compaction_v1",
        "source_text_chars": len(text),
        "stored_text_chars": len(content),
        "storage_policy": "meaning_with_document_provenance",
    }
    return content, metadata


def _fallback_semantic_line_score(line: str, index: int) -> int:
    lower = line.casefold()
    score = 0
    if index < 2:
        score += 2
    if any(char.isdigit() for char in line):
        score += 2
    if any(term.casefold() in lower for term in _FALLBACK_IMPORTANT_TERMS):
        score += 4
    if "%" in line or "°" in line:
        score += 2
    if len(line) <= 180:
        score += 1
    return score


def _document_extraction_batches(
    document: DocumentInput,
    max_chars: int,
) -> list[tuple[str, str, dict[str, Any]]]:
    """Split documents into extraction prompts without silently dropping context."""
    try:
        from kg_engine.config.settings import settings

        batch_chars = int(
            getattr(settings, "materials_llm_extraction_batch_chars", 25_000)
        )
        max_batches = int(
            getattr(settings, "materials_llm_extraction_max_batches_per_document", 0)
        )
        overlap = int(
            getattr(settings, "materials_llm_extraction_chunk_overlap", 2_000)
        )
    except Exception:
        batch_chars = 25_000
        max_batches = 0
        overlap = 2_000
    batch_chars = max(1_000, min(max_chars, batch_chars))
    max_batches = max(0, max_batches)
    overlap = max(0, min(batch_chars - 1, overlap))

    if not document.text:
        return []
    if not document.text_units and len(document.text) <= batch_chars:
        return [
            (
                document.title,
                document.text,
                {
                    "batch_index": 1,
                    "batch_count": 1,
                    "batch_source": "document_text",
                    "coverage_scope": "full_document",
                    "source_char_start": 0,
                    "source_char_end": len(document.text),
                },
            )
        ]
    if not document.text_units:
        batches: list[tuple[str, str, dict[str, Any]]] = []
        start = 0
        while start < len(document.text):
            if max_batches and len(batches) >= max_batches:
                break
            end = min(start + batch_chars, len(document.text))
            batch_number = len(batches) + 1
            batches.append(
                (
                    f"{document.title} text batch {batch_number}",
                    document.text[start:end],
                    {
                        "batch_index": batch_number,
                        "batch_source": "document_text",
                        "coverage_scope": "full_document",
                        "source_char_start": start,
                        "source_char_end": end,
                    },
                )
            )
            if end == len(document.text):
                break
            start = end - overlap if overlap else end
        batch_count = len(batches)
        omitted_chars = max(len(document.text) - (batches[-1][2]["source_char_end"] if batches else 0), 0)
        return [
            (
                title,
                text,
                {
                    **metadata,
                    "batch_count": batch_count,
                    "total_source_chars": len(document.text),
                    "omitted_chars": omitted_chars,
                    "llm_extraction_truncated": omitted_chars > 0,
                },
            )
            for title, text, metadata in batches
        ]

    batches: list[tuple[str, str, dict[str, Any]]] = []
    current_parts: list[str] = []
    current_pages: list[int] = []
    current_chars = 0
    processed_units = 0
    total_units = len(document.text_units)
    # Keep each LLM request small enough to avoid provider read timeouts on books.
    target_chars = batch_chars

    def flush() -> None:
        nonlocal current_parts, current_pages, current_chars
        if not current_parts:
            return
        pages = sorted(set(current_pages))
        batch_number = len(batches) + 1
        title = f"{document.title} semantic batch {batch_number}"
        metadata: dict[str, Any] = {
            "batch_index": batch_number,
            "batch_source": "semantic_text_units",
            "text_units": len(current_parts),
            "coverage_scope": "full_document",
        }
        if pages:
            metadata["pages"] = pages
            metadata["page_start"] = pages[0]
            metadata["page_end"] = pages[-1]
        batches.append((title, "\n\n".join(current_parts), metadata))
        current_parts = []
        current_pages = []
        current_chars = 0

    for index, text_unit in enumerate(document.text_units, start=1):
        if max_batches and len(batches) >= max_batches:
            break
        metadata = text_unit.metadata
        page = metadata.get("page")
        source_file = metadata.get("source_file") or metadata.get("source_id") or document.document_id
        block_id = metadata.get("block_id") or f"text-unit-{index}"
        prefix = (
            f"[text_unit={index} source={source_file} page={page} "
            f"block_id={block_id} semantic_unit={metadata.get('semantic_unit', False)}]"
        )
        part = f"{prefix}\n{text_unit.content}"
        if current_parts and current_chars + len(part) > target_chars:
            flush()
            if max_batches and len(batches) >= max_batches:
                break
        if len(part) > target_chars:
            part = part[: target_chars - 3].rstrip() + "..."
        current_parts.append(part)
        current_chars += len(part)
        processed_units = index
        if isinstance(page, int):
            current_pages.append(page)

    flush()
    batch_count = len(batches)
    return [
        (
            title,
            text,
            {
                **metadata,
                "batch_count": batch_count,
                "total_text_units": total_units,
                "processed_text_units": min(processed_units, total_units),
                "omitted_text_units": max(total_units - processed_units, 0),
                "llm_extraction_truncated": processed_units < total_units,
            },
        )
        for title, text, metadata in batches
    ]


def _document_extraction_coverage_warnings(
    document_id: str,
    batches: list[tuple[str, str, dict[str, Any]]],
) -> list[str]:
    if not batches:
        return []
    metadata = batches[-1][2]
    if not metadata.get("llm_extraction_truncated"):
        return []
    omitted_units = int(metadata.get("omitted_text_units") or 0)
    omitted_chars = int(metadata.get("omitted_chars") or 0)
    if omitted_units:
        return [
            f"{document_id}: LLM extraction capped; omitted {omitted_units} text units"
        ]
    if omitted_chars:
        return [
            f"{document_id}: LLM extraction capped; omitted {omitted_chars} source chars"
        ]
    return [f"{document_id}: LLM extraction capped"]


def _build_extraction_context(
    *,
    source_file: str,
    agent_trace: list[dict[str, Any]],
    batch_metadata: dict[str, Any],
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "source_file": source_file,
        "agent_trace": agent_trace,
        "extraction_batch": batch_metadata,
    }
    if "pages" in batch_metadata:
        context["source_pages"] = batch_metadata["pages"]
    if "page_start" in batch_metadata:
        context["page_start"] = batch_metadata["page_start"]
    if "page_end" in batch_metadata:
        context["page_end"] = batch_metadata["page_end"]
    if "source_char_start" in batch_metadata:
        context["source_char_start"] = batch_metadata["source_char_start"]
    if "source_char_end" in batch_metadata:
        context["source_char_end"] = batch_metadata["source_char_end"]
    return context


def _entity_matches_sources(entity: Entity, source_set: set[str]) -> bool:
    """Check if an entity originated from any of the given sources."""
    if any(_source_matches(ref, source_set) for ref in entity.source_refs):
        return True
    props = entity.properties
    for key in ("source_file", "source_ref", "_uploaded_from"):
        val = props.get(key)
        if _source_matches(val, source_set):
            return True
    return False


def _evidence_matches_sources(evidence: Evidence, source_set: set[str]) -> bool:
    """Check if evidence originated from any of the given sources."""
    if _source_matches(evidence.source_id, source_set):
        return True
    meta = evidence.metadata
    for key in ("source_file", "source_ref"):
        val = meta.get(key)
        if _source_matches(val, source_set):
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
        if _source_matches(val, source_set):
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


def _add_document_provenance_relation(
    *,
    document_entity: Entity,
    tag_entity: Entity,
    doc_src: str,
    pending_evidence: list[Evidence],
    pending_relations: list[Relation],
    create_evidence,
) -> None:
    evidence = create_evidence(
        source_kind=SourceKind.DOCUMENT,
        source_id=doc_src,
        fragment=document_entity.canonical_name,
        extraction_method="document_provenance",
        confidence=1.0,
        metadata={"source_file": doc_src, "system_relation": True},
    )
    pending_evidence.append(evidence)
    pending_relations.append(
        Relation(
            id=_stable_id(
                "rel",
                "tagged_with",
                document_entity.id,
                tag_entity.id,
            ),
            relation_type="tagged_with",
            source_entity_id=document_entity.id,
            target_entity_id=tag_entity.id,
            evidence_ids=[evidence.id],
            properties={
                "extraction_method": "document_provenance",
                "system_relation": True,
            },
        )
    )


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
        if _source_matches(val, source_set):
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

    @property
    def llm_provider(self) -> Any | None:
        return self._llm

    @property
    def repository(self) -> MaterialsKGRepository:
        """Repository used by read-only service integrations such as metrics."""
        return self._repository

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

    def ingest_experiments(
        self,
        batch: list[ExperimentInput],
        *,
        enable_embeddings: bool = True,
    ) -> dict[str, int]:
        observation_count = 0
        trace_count = 0
        pending_observations: list[Observation] = []
        pending_evidence: list[Evidence] = []
        pending_relations: list[Relation] = []
        pending_traces: list[DecisionTrace] = []
        pending_text_units: list[SearchTextUnit] = []

        for experiment in batch:
            provenance_ref = experiment.source_ref or experiment.experiment_id
            upload_file = experiment.metadata.get("source_file") or experiment.metadata.get(
                "_uploaded_from"
            )
            experiment_entity = self._ensure_entity(
                "experiment",
                experiment.title,
                entity_id=experiment.experiment_id,
                aliases=[experiment.experiment_id],
                source_ref=provenance_ref,
                upload_file=upload_file,
                properties=experiment.metadata,
            )
            material = self._ensure_entity(
                "material",
                experiment.material_name,
                source_ref=provenance_ref,
                upload_file=upload_file,
            )
            self._link_entities(
                experiment_entity.id,
                material.id,
                "evaluates_material",
                evidence_ids=[],
                properties={"source": provenance_ref},
            )
            mode_entity = None
            if experiment.mode_name:
                mode_entity = self._ensure_entity(
                    "mode",
                    experiment.mode_name,
                    source_ref=provenance_ref,
                    upload_file=upload_file,
                )
                self._link_entities(
                    experiment_entity.id,
                    mode_entity.id,
                    "uses_mode",
                    evidence_ids=[],
                )
            if experiment.team_name:
                team = self._ensure_entity(
                    "team",
                    experiment.team_name,
                    source_ref=provenance_ref,
                    upload_file=upload_file,
                )
                self._link_entities(
                    experiment_entity.id,
                    team.id,
                    "performed_by",
                    evidence_ids=[],
                )
            for equipment_name in experiment.equipment_names:
                equipment = self._ensure_entity(
                    "equipment",
                    equipment_name,
                    source_ref=provenance_ref,
                    upload_file=upload_file,
                )
                self._link_entities(
                    experiment_entity.id,
                    equipment.id,
                    "uses_equipment",
                    evidence_ids=[],
                )
            if experiment.document_id:
                document = self._ensure_entity(
                    "document",
                    experiment.document_id,
                    entity_id=experiment.document_id,
                    aliases=[experiment.document_id],
                    source_ref=provenance_ref,
                    upload_file=upload_file,
                )
                self._link_entities(
                    experiment_entity.id,
                    document.id,
                    "documented_in",
                    evidence_ids=[],
                )

            observation_ids: list[str] = []
            for observation_input in experiment.observations:
                obs, obs_evidence, obs_relations = self._build_observation(
                    experiment=experiment,
                    experiment_entity=experiment_entity,
                    material=material,
                    mode_entity=mode_entity,
                    observation_input=observation_input,
                    provenance_ref=provenance_ref,
                    upload_file=upload_file,
                )
                observation_ids.append(obs.id)
                pending_observations.append(obs)
                pending_evidence.append(obs_evidence)
                pending_relations.extend(obs_relations)
                observation_count += 1

            for index, finding in enumerate(experiment.findings):
                trace, trace_evidence = self._build_trace(
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
                pending_traces.append(trace)
                pending_evidence.append(trace_evidence)
                trace_count += 1

            for index, text_unit in enumerate(experiment.text_units):
                unit_metadata = {
                    **text_unit.metadata,
                    "source_id": provenance_ref,
                    "source_file": provenance_ref,
                }
                pending_text_units.append(
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

        self._repository.batch_upsert_observations(pending_observations)
        self._repository.batch_upsert_evidence(pending_evidence)
        self._repository.batch_upsert_relations(pending_relations)
        self._repository.batch_upsert_traces(pending_traces)
        if enable_embeddings:
            pending_text_units = self._batch_compute_embeddings(pending_text_units)
        self._repository.batch_upsert_text_units(pending_text_units)

        return {
            "experiments": len(batch),
            "observations": observation_count,
            "decision_traces": trace_count,
        }

    def ingest_documents(
        self,
        batch: list[DocumentInput],
        *,
        enable_llm_extraction: bool = True,
        enable_embeddings: bool = True,
    ) -> dict[str, int]:
        trace_count = 0
        llm_extracted_count = 0
        llm_extraction_errors: list[str] = []
        pending_evidence: list[Evidence] = []
        pending_relations: list[Relation] = []
        pending_traces: list[DecisionTrace] = []
        pending_text_units: list[SearchTextUnit] = []

        for document in batch:
            doc_src = document.source_ref or document.document_id
            document_entity = self._ensure_entity(
                "document",
                document.title,
                entity_id=document.document_id,
                aliases=[document.document_id],
                source_ref=doc_src,
                properties=document.metadata,
            )
            source_tag = self._ensure_entity(
                "tag",
                _SOURCE_DOCUMENT_TAG,
                source_ref=doc_src,
            )
            _add_document_provenance_relation(
                document_entity=document_entity,
                tag_entity=source_tag,
                doc_src=doc_src,
                pending_evidence=pending_evidence,
                pending_relations=pending_relations,
                create_evidence=self._create_evidence,
            )
            linked_entity_ids: list[str] = [document_entity.id]

            llm_extracted_entity_names: set[tuple[str, str]] = set()

            from kg_engine.config.settings import settings as _kg_settings
            _llm_max_chars = getattr(_kg_settings, "materials_llm_extraction_max_chars", 80_000)
            extraction_batches = (
                _document_extraction_batches(document, _llm_max_chars)
                if self._llm and enable_llm_extraction
                else []
            )
            llm_extraction_errors.extend(
                _document_extraction_coverage_warnings(
                    document.document_id,
                    extraction_batches,
                )
            )

            if extraction_batches:
                try:
                    from kg_engine.agents.extraction_agent import (
                        extract_and_resolve,
                    )
                    from kg_engine.agents.extraction_agent import (
                        resolve_relation_type,
                    )

                    for batch_title, batch_text, batch_metadata in extraction_batches:
                        extraction = extract_and_resolve(
                            self._llm, batch_title, batch_text
                        )
                        extraction_method = extraction.extraction_engine
                        extraction_context = _build_extraction_context(
                            source_file=doc_src,
                            agent_trace=extraction.agent_trace,
                            batch_metadata=batch_metadata,
                        )

                        name_to_id: dict[str, str] = {}
                        for ent in extraction.entities:
                            entity = self._ensure_entity(
                                ent.kind,
                                ent.name,
                                source_ref=doc_src,
                                aliases=ent.aliases,
                                properties={
                                    **ent.properties,
                                    "extraction_batch": batch_metadata,
                                },
                            )
                            name_to_id[ent.name] = entity.id
                            linked_entity_ids.append(entity.id)
                            llm_extracted_entity_names.add(
                                (ent.kind, ent.name.lower().strip())
                            )
                            evidence = self._create_evidence(
                                source_kind=SourceKind.DOCUMENT,
                                source_id=doc_src,
                                fragment=ent.name,
                                extraction_method=extraction_method,
                                confidence=0.85,
                                metadata=extraction_context,
                            )
                            pending_evidence.append(evidence)
                            pending_relations.append(Relation(
                                id=_stable_id(
                                    "rel",
                                    "references",
                                    document_entity.id,
                                    entity.id,
                                ),
                                relation_type="references",
                                source_entity_id=document_entity.id,
                                target_entity_id=entity.id,
                                evidence_ids=[evidence.id],
                            ))

                        for exp in extraction.experiments:
                            observations = [
                                item.model_copy(
                                    update={
                                        "extraction_method": extraction_method,
                                        "metadata": {
                                            **item.metadata,
                                            "agent_trace": extraction.agent_trace,
                                            "extraction_batch": batch_metadata,
                                        },
                                    }
                                )
                                for item in exp.observations
                            ]
                            findings = [
                                item.model_copy(
                                    update={
                                        "extraction_method": extraction_method,
                                        "metadata": {
                                            **item.metadata,
                                            "agent_trace": extraction.agent_trace,
                                            "extraction_batch": batch_metadata,
                                        },
                                    }
                                )
                                for item in exp.findings
                            ]
                            exp_input = ExperimentInput(
                                experiment_id=exp.experiment_id,
                                title=exp.title or f"Extracted from {document.title}",
                                material_name=exp.material_name,
                                mode_name=exp.mode_name,
                                observations=observations,
                                findings=findings,
                                source_ref=doc_src,
                                metadata={
                                    "source_document": document.document_id,
                                    "extraction_method": extraction_method,
                                    "agent_trace": extraction.agent_trace,
                                    "extraction_batch": batch_metadata,
                                },
                            )
                            self.ingest_experiments(
                                [exp_input],
                                enable_embeddings=enable_embeddings,
                            )
                            llm_extracted_count += 1

                        for rel in extraction.relationships:
                            source_id = name_to_id.get(rel.source)
                            target_id = name_to_id.get(rel.target)
                            if not source_id or not target_id:
                                continue

                            relation_type = resolve_relation_type(rel.type)
                            evidence = self._create_evidence(
                                source_kind=SourceKind.DOCUMENT,
                                source_id=doc_src,
                                fragment=f"{rel.source} {relation_type} {rel.target}",
                                extraction_method=f"{extraction_method}_relationship",
                                confidence=0.8,
                                metadata=extraction_context,
                            )
                            pending_evidence.append(evidence)
                            pending_relations.append(Relation(
                                id=_stable_id(
                                    "rel",
                                    relation_type,
                                    source_id,
                                    target_id,
                                ),
                                relation_type=relation_type,
                                source_entity_id=source_id,
                                target_entity_id=target_id,
                                evidence_ids=[evidence.id],
                                properties={
                                    "extraction_method": extraction_method,
                                    "extraction_batch": batch_metadata,
                                },
                            ))

                        for warning in extraction.warnings:
                            llm_extraction_errors.append(
                                f"{document.document_id}: {batch_title}: {warning}"
                            )

                except Exception:
                    logger.exception(
                        "LLM extraction failed for document %s",
                        document.document_id,
                    )
                    llm_extraction_errors.append(
                        f"{document.document_id}: extraction failed"
                    )

            for kind, values in (
                ("material", document.material_names),
                ("mode", document.mode_names),
                ("property", document.property_names),
                ("equipment", document.equipment_names),
                ("team", document.team_names),
            ):
                for value in values:
                    entity = self._ensure_entity(kind, value, source_ref=doc_src)
                    linked_entity_ids.append(entity.id)
                    already_linked = (
                        kind,
                        value.lower().strip(),
                    ) in llm_extracted_entity_names
                    if not already_linked:
                        evidence = self._create_evidence(
                            source_kind=SourceKind.DOCUMENT,
                            source_id=doc_src,
                            fragment=value,
                            extraction_method="document_reference",
                            metadata={"source_file": doc_src},
                        )
                        pending_evidence.append(evidence)
                        pending_relations.append(Relation(
                            id=_stable_id(
                                "rel",
                                "references",
                                document_entity.id,
                                entity.id,
                            ),
                            relation_type="references",
                            source_entity_id=document_entity.id,
                            target_entity_id=entity.id,
                            evidence_ids=[evidence.id],
                        ))
            for tag_name in document.tag_names:
                tag = self._ensure_entity("tag", tag_name, source_ref=doc_src)
                linked_entity_ids.append(tag.id)
                pending_relations.append(Relation(
                    id=_stable_id(
                        "rel",
                        "tagged_with",
                        document_entity.id,
                        tag.id,
                    ),
                    relation_type="tagged_with",
                    source_entity_id=document_entity.id,
                    target_entity_id=tag.id,
                    evidence_ids=[],
                ))
            for experiment_id in document.experiment_ids:
                experiment_entity = self._ensure_entity(
                    "experiment",
                    experiment_id,
                    entity_id=experiment_id,
                    aliases=[experiment_id],
                    source_ref=doc_src,
                )
                linked_entity_ids.append(experiment_entity.id)
                pending_relations.append(Relation(
                    id=_stable_id(
                        "rel",
                        "documented_in",
                        experiment_entity.id,
                        document_entity.id,
                    ),
                    relation_type="documented_in",
                    source_entity_id=experiment_entity.id,
                    target_entity_id=document_entity.id,
                    evidence_ids=[],
                ))
            doc_metadata = {
                **document.metadata,
                "source_id": doc_src,
                "source_file": doc_src,
            }
            if not document.text_units:
                compact_content, compact_metadata = _compact_document_text_for_storage(
                    document.text,
                    document_id=document.document_id,
                )
                doc_text_unit = self._build_text_unit(
                    unit_id=_stable_id("doc_text", document.document_id, compact_content),
                    source_entity_id=document_entity.id,
                    source_kind=SourceKind.DOCUMENT,
                    content=compact_content,
                    metadata={**doc_metadata, **compact_metadata},
                )
                if doc_text_unit is not None:
                    pending_text_units.append(doc_text_unit)
            for index, text_unit in enumerate(document.text_units):
                unit_metadata = {
                    **text_unit.metadata,
                    "source_id": doc_src,
                    "source_file": doc_src,
                }
                chunk_unit = self._build_text_unit(
                    unit_id=_stable_id("doc_chunk", document.document_id, index),
                    source_entity_id=document_entity.id,
                    source_kind=SourceKind.DOCUMENT,
                    content=text_unit.content,
                    metadata=unit_metadata,
                )
                if chunk_unit is not None:
                    pending_text_units.append(chunk_unit)
            for index, finding in enumerate(document.findings):
                trace, trace_evidence = self._build_trace(
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
                pending_traces.append(trace)
                pending_evidence.append(trace_evidence)
                trace_count += 1

        self._repository.batch_upsert_evidence(pending_evidence)
        self._repository.batch_upsert_relations(pending_relations)
        self._repository.batch_upsert_traces(pending_traces)
        if enable_embeddings:
            pending_text_units = self._batch_compute_embeddings(pending_text_units)
        self._repository.batch_upsert_text_units(pending_text_units)

        return {
            "documents": len(batch),
            "decision_traces": trace_count,
            "llm_extracted_experiments": llm_extracted_count,
            "deepagents_extracted_experiments": llm_extracted_count,
            "llm_extraction_errors": llm_extraction_errors,
        }

    async def ingest_documents_async(
        self,
        batch: list[DocumentInput],
        *,
        enable_llm_extraction: bool = True,
        enable_embeddings: bool = True,
        parallel_workers: int = 4,
    ) -> dict[str, int]:
        """Ingest documents concurrently without blocking the FastAPI event loop."""
        if not batch or parallel_workers <= 1:
            return await asyncio.to_thread(
                self.ingest_documents,
                batch,
                enable_llm_extraction=enable_llm_extraction,
                enable_embeddings=enable_embeddings,
            )

        from kg_engine.agents.extraction_agent import extract_and_resolve
        from kg_engine.agents.extraction_agent import resolve_relation_type
        from kg_engine.config.settings import settings as _kg_settings

        _llm_max_chars = getattr(_kg_settings, "materials_llm_extraction_max_chars", 80_000)

        all_evidence: list[Evidence] = []
        all_relations: list[Relation] = []
        all_traces: list[DecisionTrace] = []
        all_text_units: list[SearchTextUnit] = []
        all_errors: list[str] = []
        trace_count = 0
        llm_extracted_count = 0

        def _process_one_document(document: DocumentInput) -> dict:
            """Process a single document; called through asyncio.to_thread."""
            local_evidence: list[Evidence] = []
            local_relations: list[Relation] = []
            local_traces: list[DecisionTrace] = []
            local_text_units: list[SearchTextUnit] = []
            local_errors: list[str] = []
            local_trace_count = 0
            local_llm_count = 0

            doc_src = document.source_ref or document.document_id
            try:
                document_entity = self._ensure_entity(
                    "document",
                    document.title,
                    entity_id=document.document_id,
                    aliases=[document.document_id],
                    source_ref=doc_src,
                    properties=document.metadata,
                )
            except Exception:
                logger.exception("FAILED _ensure_entity for doc_src=%s document_id=%s", doc_src, document.document_id)
                raise
            source_tag = self._ensure_entity(
                "tag",
                _SOURCE_DOCUMENT_TAG,
                source_ref=doc_src,
            )
            _add_document_provenance_relation(
                document_entity=document_entity,
                tag_entity=source_tag,
                doc_src=doc_src,
                pending_evidence=local_evidence,
                pending_relations=local_relations,
                create_evidence=self._create_evidence,
            )
            linked_entity_ids: list[str] = [document_entity.id]
            llm_extracted_entity_names: set[tuple[str, str]] = set()

            extraction_batches = (
                _document_extraction_batches(document, _llm_max_chars)
                if self._llm and enable_llm_extraction
                else []
            )
            local_errors.extend(
                _document_extraction_coverage_warnings(
                    document.document_id,
                    extraction_batches,
                )
            )

            if extraction_batches:
                try:
                    for batch_title, batch_text, batch_metadata in extraction_batches:
                        extraction = extract_and_resolve(
                            self._llm, batch_title, batch_text
                        )
                        extraction_method = extraction.extraction_engine
                        extraction_context = _build_extraction_context(
                            source_file=doc_src,
                            agent_trace=extraction.agent_trace,
                            batch_metadata=batch_metadata,
                        )

                        name_to_id: dict[str, str] = {}
                        for ent in extraction.entities:
                            entity = self._ensure_entity(
                                ent.kind,
                                ent.name,
                                source_ref=doc_src,
                                aliases=ent.aliases,
                                properties={
                                    **ent.properties,
                                    "extraction_batch": batch_metadata,
                                },
                            )
                            name_to_id[ent.name] = entity.id
                            linked_entity_ids.append(entity.id)
                            llm_extracted_entity_names.add(
                                (ent.kind, ent.name.lower().strip())
                            )
                            evidence = self._create_evidence(
                                source_kind=SourceKind.DOCUMENT,
                                source_id=doc_src,
                                fragment=ent.name,
                                extraction_method=extraction_method,
                                confidence=0.85,
                                metadata=extraction_context,
                            )
                            local_evidence.append(evidence)
                            local_relations.append(Relation(
                                id=_stable_id(
                                    "rel",
                                    "references",
                                    document_entity.id,
                                    entity.id,
                                ),
                                relation_type="references",
                                source_entity_id=document_entity.id,
                                target_entity_id=entity.id,
                                evidence_ids=[evidence.id],
                            ))

                        for exp in extraction.experiments:
                            observations = [
                                item.model_copy(
                                    update={
                                        "extraction_method": extraction_method,
                                        "metadata": {
                                            **item.metadata,
                                            "agent_trace": extraction.agent_trace,
                                            "extraction_batch": batch_metadata,
                                        },
                                    }
                                )
                                for item in exp.observations
                            ]
                            findings = [
                                item.model_copy(
                                    update={
                                        "extraction_method": extraction_method,
                                        "metadata": {
                                            **item.metadata,
                                            "agent_trace": extraction.agent_trace,
                                            "extraction_batch": batch_metadata,
                                        },
                                    }
                                )
                                for item in exp.findings
                            ]
                            exp_input = ExperimentInput(
                                experiment_id=exp.experiment_id,
                                title=exp.title or f"Extracted from {document.title}",
                                material_name=exp.material_name,
                                mode_name=exp.mode_name,
                                observations=observations,
                                findings=findings,
                                source_ref=doc_src,
                                metadata={
                                    "source_document": document.document_id,
                                    "extraction_method": extraction_method,
                                    "agent_trace": extraction.agent_trace,
                                    "extraction_batch": batch_metadata,
                                },
                            )
                            self.ingest_experiments(
                                [exp_input],
                                enable_embeddings=enable_embeddings,
                            )
                            local_llm_count += 1

                        for rel in extraction.relationships:
                            source_id = name_to_id.get(rel.source)
                            target_id = name_to_id.get(rel.target)
                            if not source_id or not target_id:
                                continue
                            relation_type = resolve_relation_type(rel.type)
                            evidence = self._create_evidence(
                                source_kind=SourceKind.DOCUMENT,
                                source_id=doc_src,
                                fragment=f"{rel.source} {relation_type} {rel.target}",
                                extraction_method=f"{extraction_method}_relationship",
                                confidence=0.8,
                                metadata=extraction_context,
                            )
                            local_evidence.append(evidence)
                            local_relations.append(Relation(
                                id=_stable_id(
                                    "rel",
                                    relation_type,
                                    source_id,
                                    target_id,
                                ),
                                relation_type=relation_type,
                                source_entity_id=source_id,
                                target_entity_id=target_id,
                                evidence_ids=[evidence.id],
                                properties={
                                    "extraction_method": extraction_method,
                                    "extraction_batch": batch_metadata,
                                },
                            ))

                        for warning in extraction.warnings:
                            local_errors.append(
                                f"{document.document_id}: {batch_title}: {warning}"
                            )

                except Exception:
                    logger.exception(
                        "LLM extraction failed for document %s",
                        document.document_id,
                    )
                    local_errors.append(
                        f"{document.document_id}: extraction failed"
                    )

            for kind, values in (
                ("material", document.material_names),
                ("mode", document.mode_names),
                ("property", document.property_names),
                ("equipment", document.equipment_names),
                ("team", document.team_names),
            ):
                for value in values:
                    entity = self._ensure_entity(kind, value, source_ref=doc_src)
                    linked_entity_ids.append(entity.id)
                    already_linked = (
                        kind,
                        value.lower().strip(),
                    ) in llm_extracted_entity_names
                    if not already_linked:
                        evidence = self._create_evidence(
                            source_kind=SourceKind.DOCUMENT,
                            source_id=doc_src,
                            fragment=value,
                            extraction_method="document_reference",
                            metadata={"source_file": doc_src},
                        )
                        local_evidence.append(evidence)
                        local_relations.append(Relation(
                            id=_stable_id(
                                "rel",
                                "references",
                                document_entity.id,
                                entity.id,
                            ),
                            relation_type="references",
                            source_entity_id=document_entity.id,
                            target_entity_id=entity.id,
                            evidence_ids=[evidence.id],
                        ))
            for tag_name in document.tag_names:
                tag = self._ensure_entity("tag", tag_name, source_ref=doc_src)
                linked_entity_ids.append(tag.id)
                local_relations.append(Relation(
                    id=_stable_id(
                        "rel",
                        "tagged_with",
                        document_entity.id,
                        tag.id,
                    ),
                    relation_type="tagged_with",
                    source_entity_id=document_entity.id,
                    target_entity_id=tag.id,
                    evidence_ids=[],
                ))
            for experiment_id in document.experiment_ids:
                experiment_entity = self._ensure_entity(
                    "experiment",
                    experiment_id,
                    entity_id=experiment_id,
                    aliases=[experiment_id],
                    source_ref=doc_src,
                )
                linked_entity_ids.append(experiment_entity.id)
                local_relations.append(Relation(
                    id=_stable_id(
                        "rel",
                        "documented_in",
                        experiment_entity.id,
                        document_entity.id,
                    ),
                    relation_type="documented_in",
                    source_entity_id=experiment_entity.id,
                    target_entity_id=document_entity.id,
                    evidence_ids=[],
                ))

            doc_metadata = {
                **document.metadata,
                "source_id": doc_src,
                "source_file": doc_src,
            }
            if not document.text_units:
                compact_content, compact_metadata = _compact_document_text_for_storage(
                    document.text,
                    document_id=document.document_id,
                )
                doc_text_unit = self._build_text_unit(
                    unit_id=_stable_id("doc_text", document.document_id, compact_content),
                    source_entity_id=document_entity.id,
                    source_kind=SourceKind.DOCUMENT,
                    content=compact_content,
                    metadata={**doc_metadata, **compact_metadata},
                )
                if doc_text_unit is not None:
                    local_text_units.append(doc_text_unit)
            for index, text_unit in enumerate(document.text_units):
                unit_metadata = {
                    **text_unit.metadata,
                    "source_id": doc_src,
                    "source_file": doc_src,
                }
                chunk_unit = self._build_text_unit(
                    unit_id=_stable_id("doc_chunk", document.document_id, index),
                    source_entity_id=document_entity.id,
                    source_kind=SourceKind.DOCUMENT,
                    content=text_unit.content,
                    metadata=unit_metadata,
                )
                if chunk_unit is not None:
                    local_text_units.append(chunk_unit)

            for index, finding in enumerate(document.findings):
                trace, trace_evidence = self._build_trace(
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
                local_traces.append(trace)
                local_evidence.append(trace_evidence)
                local_trace_count += 1

            return {
                "evidence": local_evidence,
                "relations": local_relations,
                "traces": local_traces,
                "text_units": local_text_units,
                "errors": local_errors,
                "trace_count": local_trace_count,
                "llm_count": local_llm_count,
            }

        max_workers = min(parallel_workers, len(batch))
        logger.info(
            "Async ingestion: %d documents across %d workers",
            len(batch),
            max_workers,
        )

        semaphore = asyncio.Semaphore(max_workers)

        async def _process_with_limit(document: DocumentInput) -> dict:
            async with semaphore:
                return await asyncio.to_thread(_process_one_document, document)

        tasks = [asyncio.create_task(_process_with_limit(doc)) for doc in batch]
        for task, doc in zip(tasks, batch, strict=False):
            try:
                result = await task
                all_evidence.extend(result["evidence"])
                all_relations.extend(result["relations"])
                all_traces.extend(result["traces"])
                all_text_units.extend(result["text_units"])
                all_errors.extend(result["errors"])
                trace_count += result["trace_count"]
                llm_extracted_count += result["llm_count"]
            except Exception:
                logger.exception("Worker failed for document %s", doc.document_id)
                all_errors.append(f"{doc.document_id}: worker_failed")

        await asyncio.to_thread(self._repository.batch_upsert_evidence, all_evidence)
        await asyncio.to_thread(self._repository.batch_upsert_relations, all_relations)
        await asyncio.to_thread(self._repository.batch_upsert_traces, all_traces)
        if enable_embeddings:
            all_text_units = await self._batch_compute_embeddings_async(all_text_units)
        await asyncio.to_thread(self._repository.batch_upsert_text_units, all_text_units)

        return {
            "documents": len(batch),
            "decision_traces": trace_count,
            "llm_extracted_experiments": llm_extracted_count,
            "deepagents_extracted_experiments": llm_extracted_count,
            "llm_extraction_errors": all_errors,
        }

    def ingest_documents_parallel(
        self,
        batch: list[DocumentInput],
        *,
        enable_llm_extraction: bool = True,
        enable_embeddings: bool = True,
        parallel_workers: int = 4,
    ) -> dict[str, int]:
        """Compatibility wrapper; API code uses ``ingest_documents_async``."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.ingest_documents_async(
                    batch,
                    enable_llm_extraction=enable_llm_extraction,
                    enable_embeddings=enable_embeddings,
                    parallel_workers=parallel_workers,
                )
            )
        msg = "ingest_documents_parallel cannot be called from an async event loop"
        raise RuntimeError(msg)

    def _build_text_unit(
        self,
        unit_id: str,
        source_entity_id: str,
        source_kind: SourceKind,
        content: str,
        metadata: dict | None = None,
    ) -> SearchTextUnit | None:
        if not content:
            return None
        return SearchTextUnit(
            id=unit_id,
            source_entity_id=source_entity_id,
            source_kind=source_kind,
            content=content,
            embedding=None,
            metadata=metadata or {},
        )

    def _batch_compute_embeddings(
        self, text_units: list[SearchTextUnit]
    ) -> list[SearchTextUnit]:
        if not text_units or not self._llm:
            return text_units
        texts: list[str] = []
        indices: list[int] = []
        from kg_engine.config.settings import settings
        embed_budget = settings.llm_embedding_truncation_chars
        for idx, unit in enumerate(text_units):
            content = (unit.content or "").strip()
            if not content:
                continue
            texts.append(content[:embed_budget])
            indices.append(idx)
        if not texts:
            return text_units
        try:
            results = self._llm.embed(texts)
            for idx, emb in zip(indices, results, strict=False):
                if emb:
                    text_units[idx].embedding = emb
        except Exception:
            logger.debug("Batch embedding failed for %d text units", len(texts))
        return text_units

    async def _batch_compute_embeddings_async(
        self, text_units: list[SearchTextUnit]
    ) -> list[SearchTextUnit]:
        if not text_units or not self._llm:
            return text_units
        texts: list[str] = []
        indices: list[int] = []
        from kg_engine.config.settings import settings
        embed_budget = settings.llm_embedding_truncation_chars
        for idx, unit in enumerate(text_units):
            content = (unit.content or "").strip()
            if not content:
                continue
            texts.append(content[:embed_budget])
            indices.append(idx)
        if not texts:
            return text_units
        try:
            embed_async = getattr(self._llm, "embed_async", None)
            if embed_async is not None and inspect.iscoroutinefunction(embed_async):
                results = await embed_async(texts)
            else:
                results = await asyncio.to_thread(self._llm.embed, texts)
            for idx, emb in zip(indices, results, strict=False):
                if emb:
                    text_units[idx].embedding = emb
        except Exception:
            logger.debug("Async batch embedding failed for %d text units", len(texts))
        return text_units

    def _upsert_text_unit_with_embedding(
        self,
        unit_id: str,
        source_entity_id: str,
        source_kind: SourceKind,
        content: str,
        metadata: dict | None = None,
    ) -> SearchTextUnit | None:
        unit = self._build_text_unit(
            unit_id=unit_id,
            source_entity_id=source_entity_id,
            source_kind=source_kind,
            content=content,
            metadata=metadata,
        )
        if unit is None:
            return None
        units = self._batch_compute_embeddings([unit])
        return self._repository.upsert_text_unit(units[0])

    def query_material_mode(
        self,
        material: str,
        mode: str | None = None,
        property_name: str | None = None,
    ) -> MaterialModeQueryResult:
        material_entity = self._require_entity("material", material)
        mode_entity = (
            None if mode is None else self._require_entity("mode", mode)
        )
        property_entity = None
        if property_name is not None:
            property_entity = self._require_entity("property", property_name)
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
        property_entity = self._require_entity("property", property_name)
        observations = self._repository.list_observations(
            property_id=property_entity.id
        )
        if filters.material_name:
            material_entity = self._require_entity(
                "material",
                filters.material_name,
            )
            observations = [
                observation
                for observation in observations
                if observation.material_id == material_entity.id
            ]
        if filters.mode_name:
            mode_entity = self._require_entity("mode", filters.mode_name)
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
        relation_filters: list[str] | None = None,
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
        if root.kind == "experiment":
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
        source_ids: list[str] | None = None,
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
                "material", rule.material_names
            )
            modes = self._resolve_rule_entities("mode", rule.mode_names)
            properties = self._resolve_rule_entities(
                "property",
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
        if source_ids is None:
            return gaps

        source_set = set(source_ids)
        all_entity_ids: set[str] = set()
        for gap in gaps:
            for entity_id in (gap.material_id, gap.mode_id, gap.property_id):
                if entity_id:
                    all_entity_ids.add(entity_id)
        all_entities = self._repository.find_entities(ids=list(all_entity_ids))
        entity_lookup: dict[str, Entity] = {e.id: e for e in all_entities}

        return [
            gap
            for gap in gaps
            if all(
                _entity_matches_sources(entity, source_set)
                for entity in (
                    entity_lookup[eid]
                    for eid in (gap.material_id, gap.mode_id, gap.property_id)
                    if eid and eid in entity_lookup
                )
            )
        ]

    def search_evidence_units(
        self,
        query: str,
        *,
        limit: int = 8,
        source_ids: list[str] | None = None,
    ) -> list[SearchTextUnit]:
        """Search read-only text evidence units for agent orchestration."""
        if not query.strip():
            return []
        hits = self._repository.search_text_units(query, limit=limit)
        if source_ids is None:
            return hits
        source_set = _expand_source_set(
            {item.strip() for item in source_ids if item and item.strip()}
        )
        return [
            hit
            for hit in hits
            if _source_matches(hit.source_entity_id, source_set)
            or _source_matches(hit.metadata.get("source_id"), source_set)
            or _source_matches(hit.metadata.get("source_file"), source_set)
            or _source_matches(hit.metadata.get("source_ref"), source_set)
            or _source_matches(hit.metadata.get("source_path"), source_set)
        ]

    def _build_answer_context(
        self,
        *,
        question: str,
        material: str | None = None,
        mode: str | None = None,
        property_name: str | None = None,
        source_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build one authoritative graph retrieval packet for sync and stream answers."""
        warnings: list[str] = []
        matched_entities = self._match_entities_from_question(question)

        material_entity = self._resolve_filter_entity(
            "material",
            material,
            matched_entities,
            warnings,
        )
        mode_entity = self._resolve_filter_entity(
            "mode",
            mode,
            matched_entities,
            warnings,
        )
        property_entity = self._resolve_filter_entity(
            "property",
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
            self._repository.search_text_units(question, limit=15) if question else []
        )
        # Boost VL interpretations to the top — they contain richer content
        search_hits.sort(
            key=lambda h: (
                0 if "vl_conductor" in str(h.metadata.get("parser", "")) else 1,
                -(h.metadata.get("confidence", 0) or 0),
            )
        )
        search_hits = search_hits[:8]

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
                for e in self._dedupe_by_id(experiments)
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
                for e in self._dedupe_by_id(related_entities)
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

        experiments_deduped = self._dedupe_by_id(experiments)
        observations_deduped = self._dedupe_by_id(observations)
        findings_deduped = self._dedupe_by_id(findings)
        relations_deduped = self._dedupe_by_id(relations)
        related_entities_deduped = self._dedupe_by_id(related_entities)

        entity_ids: set[str] = set()
        for entity in [
            material_entity,
            mode_entity,
            property_entity,
            root_entity,
            *matched_entities,
            *experiments_deduped,
            *related_entities_deduped,
        ]:
            if entity is not None:
                entity_ids.add(entity.id)
        for observation in observations_deduped:
            entity_ids.update(
                item
                for item in (
                    observation.material_id,
                    observation.mode_id,
                    observation.property_id,
                    observation.experiment_id,
                )
                if item
            )
        for relation in relations_deduped:
            entity_ids.add(relation.source_entity_id)
            entity_ids.add(relation.target_entity_id)
        for gap in data_gaps:
            entity_ids.update(
                item for item in (gap.material_id, gap.mode_id, gap.property_id) if item
            )

        entity_lookup = {
            entity.id: {
                "kind": entity.kind,
                "canonical_name": entity.canonical_name,
                "aliases": entity.aliases,
            }
            for entity in self._repository.find_entities(ids=sorted(entity_ids))
        }
        graph_context = {
            "resolved_query": {
                "material": (
                    material_entity.canonical_name if material_entity else None
                ),
                "mode": mode_entity.canonical_name if mode_entity else None,
                "property_name": (
                    property_entity.canonical_name if property_entity else None
                ),
            },
            "matched_entities": [
                e.model_dump(mode="json") for e in matched_entities
            ],
            "entity_lookup": entity_lookup,
            "experiments": [
                e.model_dump(mode="json") for e in experiments_deduped
            ],
            "observations": [
                o.model_dump(mode="json") for o in observations_deduped
            ],
            "decision_history": [
                t.model_dump(mode="json") for t in findings_deduped
            ],
            "data_gaps": [g.model_dump(mode="json") for g in data_gaps],
            "search_hits": [h.model_dump(mode="json") for h in search_deduped],
            "evidence": [e.model_dump(mode="json") for e in evidence_deduped],
            "relations": [
                r.model_dump(mode="json") for r in relations_deduped
            ],
            "warnings": warnings,
        }
        answer = self._build_answer_text(
            material_entity=material_entity,
            mode_entity=mode_entity,
            property_entity=property_entity,
            experiments=experiments_deduped,
            observations=observations_deduped,
            findings=findings_deduped,
            data_gaps=data_gaps,
            search_hits=search_deduped,
        )
        return {
            "warnings": warnings,
            "material_entity": material_entity,
            "mode_entity": mode_entity,
            "property_entity": property_entity,
            "matched_entities": matched_entities,
            "experiments": experiments_deduped,
            "observations": observations_deduped,
            "evidence": evidence_deduped,
            "search_hits": search_deduped,
            "findings": findings_deduped,
            "related_entities": related_entities_deduped,
            "relations": relations_deduped,
            "data_gaps": data_gaps,
            "citations": self._build_citations(evidence_deduped, search_deduped),
            "graph_context": graph_context,
            "answer": answer,
        }

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
        context = self._build_answer_context(
            question=question,
            material=material,
            mode=mode,
            property_name=property_name,
            source_ids=source_ids,
        )
        answer = context["answer"]

        if self._llm:
            try:
                from kg_engine.llm_core.extraction import llm_generate_answer

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
                    context["graph_context"],
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
            "resolved_query": context["graph_context"]["resolved_query"],
            "matched_entities": [
                entity.model_dump(mode="json") for entity in context["matched_entities"]
            ],
            "experiments": [
                entity.model_dump(mode="json") for entity in context["experiments"]
            ],
            "observations": [
                observation.model_dump(mode="json")
                for observation in context["observations"]
            ],
            "evidence": [item.model_dump(mode="json") for item in context["evidence"]],
            "citations": context["citations"],
            "related_entities": [
                entity.model_dump(mode="json")
                for entity in context["related_entities"]
            ],
            "relations": [
                relation.model_dump(mode="json") for relation in context["relations"]
            ],
            "decision_history": [
                trace.model_dump(mode="json") for trace in context["findings"]
            ],
            "data_gaps": [gap.model_dump(mode="json") for gap in context["data_gaps"]],
            "search_hits": [
                hit.model_dump(mode="json") for hit in context["search_hits"]
            ],
            "warnings": context["warnings"],
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

        context = self._build_answer_context(
            question=question,
            material=material,
            mode=mode,
            property_name=property_name,
            source_ids=source_ids,
        )
        conversation_history: list[dict[str, str]] = []
        if self._session_store and session_id:
            from kg_engine.config.settings import settings

            conversation_history = self._session_store.get_context_messages(
                session_id,
                last_n=settings.session_history_turns,
            )

        full_answer_parts: list[str] = []
        try:
            from kg_engine.llm_core.extraction import build_answer_messages

            messages = build_answer_messages(
                question,
                context["graph_context"],
                conversation_history=conversation_history,
            )

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
            "material",
            request.material,
            matched_entities,
            warnings,
        )
        mode_entity = self._resolve_filter_entity(
            "mode",
            request.mode,
            matched_entities,
            warnings,
        )
        property_entity = self._resolve_filter_entity(
            "property",
            request.property_name,
            matched_entities,
            warnings,
        )
        if property_entity is None:
            property_entity = self._resolve_filter_entity(
                "property",
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
        search_query = " ".join(
            item
            for item in (
                request.target_kpi,
                request.question,
                material_entity.canonical_name if material_entity else request.material,
                mode_entity.canonical_name if mode_entity else request.mode,
                property_entity.canonical_name
                if property_entity
                else request.property_name,
            )
            if item
        )
        search_hits = (
            self._repository.search_text_units(search_query, limit=12)
            if search_query
            else []
        )

        if request.source_ids is not None:
            source_set = set(request.source_ids)
            evidence_by_id = {e.id: e for e in evidence}
            observations = [
                o
                for o in observations
                if _observation_matches_sources(o, evidence_by_id, source_set)
            ]
            evidence = [e for e in evidence if _evidence_matches_sources(e, source_set)]
            search_hits = [
                h
                for h in search_hits
                if h.source_entity_id in source_set
                or h.metadata.get("source_id") in source_set
                or h.metadata.get("source_file") in source_set
            ]
            data_gaps = self.query_data_gaps(
                filters=filters,
                source_ids=request.source_ids,
            )

        total_observations = len(observations)
        total_evidence = len(evidence)
        total_search_hits = len(search_hits)
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
                    hypothesis_type="coverage_gap",
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
                    hypothesis_type="observed_effect",
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

        for index, hit in enumerate(search_hits):
            source_label = hit.metadata.get("source_file") or hit.metadata.get(
                "source_id", hit.source_entity_id
            )
            fragment = hit.content.strip().replace("\n", " ")
            if not fragment:
                continue
            fragment_preview = fragment[:220]
            novelty = 0.65 if not observations else 0.45
            risk = 0.55 if not observations else 0.40
            value = 0.60 + min(0.20, total_search_hits * 0.02)
            evidence_strength = 0.35 if not evidence else min(
                0.70,
                avg_evidence_confidence * 0.5 + 0.25,
            )
            score = self._hypothesis_score(
                novelty=novelty,
                risk=risk,
                value=value,
                evidence_strength=evidence_strength,
            )
            hypotheses.append(
                ResearchHypothesis(
                    id=_stable_id("hyp", request.target_kpi, hit.id, index),
                    target_kpi=request.target_kpi,
                    hypothesis_type="literature_signal",
                    statement=(
                        f"Проверить исследовательскую идею из источника {source_label} "
                        f"на влияние на KPI '{request.target_kpi}'."
                    ),
                    rationale=(
                        "В базе знаний найден релевантный фрагмент, который может "
                        f"указывать на фактор для проверки: {fragment_preview}"
                    ),
                    test_plan=(
                        f"Сформулировать фактор из источника {source_label}, задать "
                        f"контрольный эксперимент по KPI '{request.target_kpi}', "
                        "зафиксировать материал, режим, единицы измерения и сравнить "
                        "с baseline из графа или новой контрольной серией."
                    ),
                    score=score,
                    supporting_entity_ids=[hit.source_entity_id],
                    supporting_text_unit_ids=[hit.id],
                    assumptions=[
                        "Текстовый фрагмент является исследовательским сигналом, а не доказанным эффектом.",
                        "Перед запуском эксперимента эксперт должен уточнить фактор и условия проверки.",
                    ],
                    novelty_rationale=(
                        "Идея извлечена из литературы/отчёта и не обязана иметь "
                        "готовое observation в графе."
                    ),
                    risk_items=[
                        "Сигнал из текста может быть неполным или относиться к другим условиям.",
                        "Без численного observation выше риск неверной интерпретации.",
                    ],
                    value_rationale=(
                        "Позволяет использовать неструктурированную базу знаний для "
                        "быстрого старта НИОКР даже до очистки всех таблиц."
                    ),
                    logic_trace=[
                        f"1. Найден text unit {hit.id} из источника {source_label}.",
                        f"2. Фрагмент релевантен KPI '{request.target_kpi}'.",
                        f"3. observations={total_observations}, text_hits={total_search_hits}.",
                        f"4. novelty={novelty:.2f}, risk={risk:.2f}, value={value:.2f}.",
                    ],
                    validation_checks=[
                        "Экспертно подтвердить, какой фактор из фрагмента проверяется.",
                        "Проверить, есть ли в графе сопоставимые материалы, режимы и единицы KPI.",
                    ],
                    falsification_criteria=[
                        f"Гипотеза falsified, если эксперимент не меняет KPI '{request.target_kpi}' относительно baseline.",
                        "Гипотеза falsified, если источник относится к несопоставимому материалу или режиму.",
                    ],
                    required_evidence=[
                        f"Экспериментальное измерение KPI '{request.target_kpi}'.",
                        "Источник с условиями, материалом, режимом и единицами измерения.",
                    ],
                    metadata={
                        "source": "literature_signal",
                        "source_file": source_label,
                    },
                )
            )

        if request.excluded_directions:
            excluded_terms = [
                item.strip().casefold()
                for item in request.excluded_directions
                if item.strip()
            ]
            before_filter = len(hypotheses)
            hypotheses = [
                hypothesis
                for hypothesis in hypotheses
                if not _hypothesis_mentions_any(hypothesis, excluded_terms)
            ]
            removed = before_filter - len(hypotheses)
            if removed:
                warnings.append(
                    f"Excluded {removed} hypotheses by project/domain exclusions."
                )

        expert_adjustments = dict(request.expert_adjustments)
        if request.ranking_weights:
            expert_adjustments["ranking_weights"] = request.ranking_weights
        apply_expert_adjustments(hypotheses, expert_adjustments)
        for hypothesis in hypotheses:
            self._populate_verification_plan(hypothesis, request)

        hypotheses.sort(key=lambda item: item.score.final_score, reverse=True)
        hypotheses = hypotheses[: request.max_hypotheses]
        for rank, hypothesis in enumerate(hypotheses, start=1):
            hypothesis.rank = rank
        if not hypotheses:
            warnings.append(
                "Не удалось построить гипотезы: загрузите источники или уточните KPI/material/mode/property."
            )
        knowledge_base_summary = {
            "target_kpi": request.target_kpi,
            "matched_entities": len(matched_entities),
            "observations": total_observations,
            "evidence": total_evidence,
            "data_gaps": len(data_gaps),
            "text_hits": total_search_hits,
            "hypothesis_types": {
                "coverage_gap": sum(
                    1 for item in hypotheses if item.hypothesis_type == "coverage_gap"
                ),
                "observed_effect": sum(
                    1
                    for item in hypotheses
                    if item.hypothesis_type == "observed_effect"
                ),
                "literature_signal": sum(
                    1
                    for item in hypotheses
                    if item.hypothesis_type == "literature_signal"
                ),
            },
            "source_ids_filter": request.source_ids,
            "excluded_directions": request.excluded_directions,
            "domain_constraints": request.domain_constraints,
        }
        ranking_weights = expert_adjustments.get("ranking_weights")
        ranking_rubric = {
            "final_score_formula": (
                "value*w_value + evidence_strength*w_evidence_strength + "
                "novelty*w_novelty + (1-risk)*w_inverse_risk"
            ),
            "weights": ranking_weights or {
                "value": 0.35,
                "evidence_strength": 0.25,
                "novelty": 0.20,
                "inverse_risk": 0.20,
            },
            "score_range": "0..1",
            "interpretation": {
                "novelty": "насколько идея непокрыта или недоисследована в базе знаний",
                "risk": "неопределённость, конфликты и нехватка проверочных данных",
                "value": "потенциальная польза для целевого KPI",
                "evidence_strength": "сила observation/evidence/text-grounding",
            },
        }
        result = HypothesisGenerationResult(
            target_kpi=request.target_kpi,
            generation_engine="deterministic",
            expert_adjustment_schema=EXPERT_ADJUSTMENT_SCHEMA,
            resolved_query={
                "material": material_entity.canonical_name if material_entity else None,
                "mode": mode_entity.canonical_name if mode_entity else None,
                "property_name": (
                    property_entity.canonical_name if property_entity else None
                ),
            },
            knowledge_base_summary=knowledge_base_summary,
            ranking_rubric=ranking_rubric,
            hypotheses=hypotheses,
            evidence=evidence,
            observations=self._dedupe_by_id(observations),
            data_gaps=data_gaps,
            search_hits=self._dedupe_by_id(search_hits),
            matched_entities=matched_entities,
            warnings=warnings,
        )
        return self.attach_hypothesis_metrics(result)

    def attach_hypothesis_metrics(
        self,
        result: HypothesisGenerationResult,
    ) -> HypothesisGenerationResult:
        """Attach repository-grounded quality metrics to an agent result."""
        from kg_engine.services.metrics import MetricContext
        from kg_engine.services.metrics import build_repository_coverage_heatmap
        from kg_engine.services.metrics import evaluate_hypothesis_metrics

        context = MetricContext(
            evidence_ids=[item.id for item in result.evidence],
            observation_ids=[item.id for item in result.observations],
            text_unit_ids=[item.id for item in result.search_hits],
            entity_ids=[item.id for item in result.matched_entities],
        )
        coverage = build_repository_coverage_heatmap(self._repository)
        metrics = evaluate_hypothesis_metrics(
            hypotheses=result.hypotheses,
            context=context,
            coverage=coverage,
        )
        metrics_payload = metrics.model_dump(mode="json")
        quality_context = {
            "evidence_ids": len(context.evidence_ids),
            "observation_ids": len(context.observation_ids),
            "text_unit_ids": len(context.text_unit_ids),
            "entity_ids": len(context.entity_ids),
            "coverage_cells": len(coverage.cells),
            "coverage_ratio": coverage.coverage_ratio,
        }
        result.ranking_rubric = {
            **result.ranking_rubric,
            "quality_metrics": metrics_payload,
            "quality_metrics_context": quality_context,
        }
        result.knowledge_base_summary = {
            **result.knowledge_base_summary,
            "quality_metrics": {
                "average_faithfulness": metrics.average_faithfulness,
                "average_groundedness": metrics.average_groundedness,
                "average_novelty": metrics.average_novelty,
                "coverage_ratio": metrics.coverage_ratio,
            },
        }
        result.agent_trace.append(
            {
                "event": "hypothesis_metrics_evaluated",
                "average_faithfulness": metrics.average_faithfulness,
                "average_groundedness": metrics.average_groundedness,
                "average_novelty": metrics.average_novelty,
                "coverage_ratio": metrics.coverage_ratio,
            }
        )
        return result

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
        return HypothesisScore(
            novelty=clamp_score(novelty),
            risk=clamp_score(risk),
            value=clamp_score(value),
            evidence_strength=clamp_score(evidence_strength),
            final_score=calculate_final_score(
                novelty=novelty,
                risk=risk,
                value=value,
                evidence_strength=evidence_strength,
            ),
        )

    def _populate_verification_plan(
        self,
        hypothesis: ResearchHypothesis,
        request: HypothesisInput,
    ) -> None:
        uncertainty = clamp_score(1.0 - hypothesis.score.evidence_strength)
        technical_risk = clamp_score(hypothesis.score.risk)
        economic_risk = clamp_score(0.25 + 0.35 * uncertainty)
        regulatory_risk = clamp_score(0.10 + 0.20 * uncertainty)
        resource_cost = clamp_score(0.30 + 0.25 * hypothesis.score.risk)
        time_to_test = clamp_score(0.25 + 0.35 * uncertainty)
        feasibility = clamp_score(1.0 - (technical_risk + resource_cost) / 2.0)
        hypothesis.score = hypothesis.score.model_copy(
            update={
                "feasibility": feasibility,
                "technical_risk": technical_risk,
                "economic_risk": economic_risk,
                "regulatory_risk": regulatory_risk,
                "resource_cost": resource_cost,
                "time_to_test": time_to_test,
                "uncertainty": uncertainty,
            }
        )
        hypothesis.confidence = clamp_score(
            (hypothesis.score.evidence_strength + feasibility) / 2.0
        )
        if not hypothesis.uncertainty_factors:
            hypothesis.uncertainty_factors = [
                "Недостаточно прямых повторных измерений.",
                "Нужна проверка сопоставимости условий и единиц KPI.",
            ]
        property_name = request.property_name or request.target_kpi
        hypothesis.expected_effect = hypothesis.expected_effect or ExpectedEffect(
            property_name=property_name,
            direction="increase",
            minimum=request.target_kpi and None,
            unit=None,
        )
        resource = RequiredResource(
            kind="laboratory",
            name="Экспертная проверка и экспериментальная серия",
            quantity=1,
            unit="study",
            assumption="Оценка построена deterministic без внешней модели.",
        )
        gate = DecisionGate(
            metric=property_name,
            operator="improves",
            threshold="baseline",
            success_action="promote hypothesis and expand design-of-experiments",
            failure_action="reject or revise mechanism",
        )
        steps = [
            ExperimentStep(
                order=1,
                objective="Validate source evidence and baseline comparability",
                method="Graph evidence review",
                resources=[resource],
                estimated_duration_days=1,
            ),
            ExperimentStep(
                order=2,
                objective=f"Measure KPI '{property_name}' under controlled conditions",
                method=hypothesis.test_plan[:180] or "Controlled experiment",
                dependency_ids=[],
                resources=[resource],
                decision_gate=gate,
                estimated_duration_days=5,
            ),
        ]
        hypothesis.verification_roadmap = hypothesis.verification_roadmap or VerificationRoadmap(
            steps=steps,
            assumptions=[
                "Baseline is measured with the same material, mode, and unit.",
                "All raw observations are stored with evidence ids.",
            ],
        )
        hypothesis.resource_estimate = hypothesis.resource_estimate or [resource]
        hypothesis.success_criteria = hypothesis.success_criteria or [
            f"KPI '{property_name}' improves against baseline.",
            "Result is supported by traceable observation/evidence records.",
        ]
        hypothesis.failure_criteria = hypothesis.failure_criteria or [
            f"KPI '{property_name}' does not improve against baseline.",
            "Evidence review finds the source conditions are not comparable.",
        ]

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
                    "source_kind": item.source_kind,
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
                    "source_kind": hit.source_kind,
                    "fragment": hit.content[:200],
                    "section": None,
                    "row_reference": None,
                    "confidence": 1.0,
                }
            )
        return citations

    def get_graph_data(self, source_ids: list[str]) -> dict[str, Any]:
        """Return nodes/edges for visualization, filtered by uploaded source file names."""
        source_set = _expand_source_set(
            {item.strip() for item in source_ids if item and item.strip()}
        )
        all_entities = self._repository.find_entities()
        all_relations = self._repository.list_relations()
        if not source_set:
            kept_ids = {entity.id for entity in all_entities}
        else:
            seed_ids = {
                entity.id
                for entity in all_entities
                if _entity_matches_sources(entity, source_set)
            }
            kept_ids = set(seed_ids)
            for relation in all_relations:
                if (
                    relation.source_entity_id in seed_ids
                    or relation.target_entity_id in seed_ids
                ):
                    kept_ids.add(relation.source_entity_id)
                    kept_ids.add(relation.target_entity_id)

        entities = [entity for entity in all_entities if entity.id in kept_ids]
        entity_ids = {entity.id for entity in entities}
        relations = [
            relation
            for relation in all_relations
            if relation.source_entity_id in entity_ids
            and relation.target_entity_id in entity_ids
        ]
        return {
            "nodes": [
                {
                    "id": entity.id,
                    "kind": entity.kind,
                    "name": entity.canonical_name,
                }
                for entity in entities
            ],
            "edges": [
                {
                    "id": relation.id,
                    "type": relation.relation_type,
                    "source": relation.source_entity_id,
                    "target": relation.target_entity_id,
                }
                for relation in relations
            ],
        }

    def get_source_overview(self) -> dict[str, Any]:
        """Generate overview of all loaded sources."""
        entities = self._repository.find_entities()
        observations = self._repository.list_observations()
        relations = self._repository.list_relations()
        evidence_all = self._repository.list_all_evidence()
        by_kind: dict[str, int] = {}
        for e in entities:
            by_kind[e.kind] = by_kind.get(e.kind, 0) + 1
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
        by_kind: dict[str, list[Entity]] = {}
        for e in entities:
            by_kind.setdefault(e.kind, []).append(e)
        suggestions: list[str] = []
        materials = by_kind.get("material", [])
        properties = by_kind.get("property", [])
        modes = by_kind.get("mode", [])
        teams = by_kind.get("team", [])
        equipment = by_kind.get("equipment", [])
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
        scored.sort(key=lambda item: (item[0], item[1].kind), reverse=True)
        return [entity for _, entity in scored]

    def _resolve_filter_entity(
        self,
        kind: str,
        explicit_name: str | None,
        matched_entities: list[Entity],
        warnings: list[str],
    ) -> Entity | None:
        if explicit_name:
            entity = self._repository.resolve_entity(kind, explicit_name)
            if entity is None:
                warnings.append(
                    f"Фильтр '{explicit_name}' не найден среди сущностей типа {kind}."
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
                f"Найдено экспериментов: {len(self._dedupe_by_id(experiments))}; "
                f"измерений: {len(self._dedupe_by_id(observations))}. "
                f"Значения: {value_text}."
            )
        elif experiments:
            parts.append(
                f"Найдены связанные эксперименты: {len(self._dedupe_by_id(experiments))}, "
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

    def _dedupe_by_id(self, items: list[Any]) -> list[Any]:
        return list({item.id: item for item in items}.values())

    def export_graph_snapshot(self) -> dict[str, Any]:
        """Return a portable JSON-ready snapshot of the current graph core."""
        repository = self._repository
        return {
            "schema_version": 1,
            "entities": [
                item.model_dump(mode="json")
                for item in repository.find_entities()
            ],
            "relations": [
                item.model_dump(mode="json")
                for item in repository.list_relations()
            ],
            "evidence": [
                item.model_dump(mode="json")
                for item in repository.list_all_evidence()
            ],
            "observations": [
                item.model_dump(mode="json")
                for item in repository.list_observations()
            ],
            "decision_traces": [
                item.model_dump(mode="json")
                for item in repository.list_decision_traces()
            ],
            "coverage_rules": [
                item.model_dump(mode="json")
                for item in repository.list_coverage_rules()
            ],
            "text_units": [
                item.model_dump(mode="json")
                for item in repository.list_text_units()
            ],
        }

    def save_graph_snapshot(self, path: str | Path) -> dict[str, Any]:
        """Persist a graph snapshot and return compact counts for callers."""
        snapshot_path = Path(path)
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = self.export_graph_snapshot()
        snapshot_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "path": str(snapshot_path),
            "entities": len(snapshot["entities"]),
            "relations": len(snapshot["relations"]),
            "evidence": len(snapshot["evidence"]),
            "observations": len(snapshot["observations"]),
            "decision_traces": len(snapshot["decision_traces"]),
            "coverage_rules": len(snapshot["coverage_rules"]),
            "text_units": len(snapshot["text_units"]),
        }

    def load_graph_snapshot(self, path: str | Path, *, clear_existing: bool = False) -> dict[str, int]:
        """Load a snapshot created by save_graph_snapshot into the repository."""
        snapshot_path = Path(path)
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            raise ValueError(f"Unsupported graph snapshot schema: {payload.get('schema_version')}")
        if clear_existing:
            self._repository.clear_all()
        for item in payload.get("entities", []):
            self._repository.upsert_entity(Entity.model_validate(item))
        for item in payload.get("evidence", []):
            self._repository.upsert_evidence(Evidence.model_validate(item))
        for item in payload.get("relations", []):
            self._repository.upsert_relation(Relation.model_validate(item))
        for item in payload.get("observations", []):
            self._repository.upsert_observation(Observation.model_validate(item))
        for item in payload.get("decision_traces", []):
            self._repository.upsert_decision_trace(DecisionTrace.model_validate(item))
        for item in payload.get("coverage_rules", []):
            self._repository.upsert_coverage_rule(CoverageRuleInput.model_validate(item))
        for item in payload.get("text_units", []):
            self._repository.upsert_text_unit(SearchTextUnit.model_validate(item))
        return {
            "entities": len(payload.get("entities", [])),
            "relations": len(payload.get("relations", [])),
            "evidence": len(payload.get("evidence", [])),
            "observations": len(payload.get("observations", [])),
            "decision_traces": len(payload.get("decision_traces", [])),
            "coverage_rules": len(payload.get("coverage_rules", [])),
            "text_units": len(payload.get("text_units", [])),
        }

    def _build_observation(
        self,
        *,
        experiment: ExperimentInput,
        experiment_entity: Entity,
        material: Entity,
        mode_entity: Entity | None,
        observation_input: ObservationInput,
        provenance_ref: str | None = None,
        upload_file: str | None = None,
    ) -> tuple[Observation, Evidence, list[Relation]]:
        """Construct an observation, its evidence, and relations without writing."""
        src = provenance_ref or experiment.source_ref or experiment.experiment_id
        property_entity = self._ensure_entity(
            "property",
            observation_input.property_name,
            source_ref=src,
            upload_file=upload_file,
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
        prop_relation = Relation(
            id=_stable_id(
                "rel",
                "measures_property",
                experiment_entity.id,
                property_entity.id,
            ),
            relation_type="measures_property",
            source_entity_id=experiment_entity.id,
            target_entity_id=property_entity.id,
            evidence_ids=[evidence.id],
            properties={
                "value": observation.value,
                "unit": observation.unit,
                "comparator": observation.comparator,
            },
        )
        return observation, evidence, [prop_relation]

    def _create_observation(
        self,
        *,
        experiment: ExperimentInput,
        experiment_entity: Entity,
        material: Entity,
        mode_entity: Entity | None,
        observation_input: ObservationInput,
        provenance_ref: str | None = None,
        upload_file: str | None = None,
    ) -> Observation:
        observation, evidence, relations = self._build_observation(
            experiment=experiment,
            experiment_entity=experiment_entity,
            material=material,
            mode_entity=mode_entity,
            observation_input=observation_input,
            provenance_ref=provenance_ref,
            upload_file=upload_file,
        )
        self._repository.upsert_observation(observation)
        self._repository.upsert_evidence(evidence)
        for rel in relations:
            self._repository.upsert_relation(rel)
        return observation

    def _build_trace(
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
    ) -> tuple[DecisionTrace, Evidence]:
        """Construct a decision trace and its evidence without writing."""
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
        return trace, evidence

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
        trace, evidence = self._build_trace(
            finding=finding,
            source_kind=source_kind,
            source_id=source_id,
            entity_ids=entity_ids,
            experiment_id=experiment_id,
            observation_ids=observation_ids,
            trace_id=trace_id,
            version=version,
        )
        self._repository.upsert_evidence(evidence)
        self._repository.upsert_decision_trace(trace)
        return trace

    def _upsert_reference_entity(self, record: CanonicalEntityInput) -> Entity:
        entity_id = record.canonical_id or _stable_id(record.kind, record.name)
        source_refs: list[str] = []
        if record.source_ref:
            source_refs.append(record.source_ref)
        for key in ("source_file", "_uploaded_from"):
            value = record.properties.get(key)
            if value and value not in source_refs:
                source_refs.append(value)
        entity = Entity(
            id=entity_id,
            kind=record.kind,
            canonical_name=record.name,
            aliases=record.aliases,
            properties=record.properties,
            source_refs=source_refs,
        )
        return self._repository.upsert_entity(entity)

    def _ensure_entity(
        self,
        kind: str,
        name: str,
        *,
        entity_id: str | None = None,
        aliases: list[str] | None = None,
        source_ref: str | None = None,
        upload_file: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> Entity:
        existing = self._repository.get_entity(entity_id) if entity_id else None
        if existing is not None and existing.kind != kind:
            existing = None
        # When entity_id is explicit and not found, always create new.
        # Only fall back to name resolution when no entity_id is given
        # (i.e. the caller relies on name-based deduplication).
        if existing is None and entity_id is None:
            existing = self._repository.resolve_entity(kind, name)
        if existing is not None:
            updates: dict[str, Any] = {
                "aliases": list({*existing.aliases, *(aliases or [])}),
                "properties": {**existing.properties, **(properties or {})},
                "source_refs": _merge_source_refs(
                    existing.source_refs,
                    source_ref=source_ref,
                    upload_file=upload_file,
                ),
            }
            return self._repository.upsert_entity(existing.model_copy(update=updates))
        entity = Entity(
            id=entity_id or _stable_id(kind, name),
            kind=kind,
            canonical_name=name,
            aliases=aliases or [],
            properties=properties or {},
            source_refs=_merge_source_refs(
                None,
                source_ref=source_ref,
                upload_file=upload_file,
            ),
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
                source_kind,
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
        relation_type: str,
        *,
        evidence_ids: list[str],
        properties: dict[str, Any] | None = None,
    ) -> Relation:
        relation = Relation(
            id=_stable_id(
                "rel",
                relation_type,
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
        kind: str,
        names: list[str],
    ) -> list[Entity]:
        entities: list[Entity] = []
        for name in names:
            entity = self._repository.resolve_entity(kind, name)
            if entity is not None:
                entities.append(entity)
        return entities

    def _require_entity(self, kind: str, raw_name: str) -> Entity:
        entity = self._repository.resolve_entity(kind, raw_name)
        if entity is None:
            raise ValueError(f"{kind.title()} '{raw_name}' not found")
        return entity

    def _resolve_any_entity(self, raw_name: str) -> Entity:
        entity = self._repository.get_entity(raw_name)
        if entity is not None:
            return entity
        for kind in ("material", "experiment", "property", "mode", "equipment", "team", "document", "tag"):
            entity = self._repository.resolve_entity(kind, raw_name)
            if entity is not None:
                return entity
        raise ValueError(f"Entity '{raw_name}' not found")

    def delete_source(self, source_id: str) -> int:
        return self._repository.delete_source(source_id)

    def clear_all(self) -> None:
        self._repository.clear_all()
