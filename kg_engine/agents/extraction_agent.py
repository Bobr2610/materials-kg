"""Deep Agents orchestration for document entity extraction and graph writes.

This module owns the agent-facing extraction contract. The service layer calls
it first, then materializes the returned typed result into the graph repository.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from kg_engine.domain.models import DocumentExtractionResult
from kg_engine.domain.models import ExtractedEntity
from kg_engine.domain.models import ExtractedExperiment
from kg_engine.domain.models import ExtractedRelationship
from kg_engine.domain.models import EntityKind
from kg_engine.domain.models import FindingInput
from kg_engine.domain.models import ObservationInput
from kg_engine.domain.models import RELATION_TYPE_MAP
from kg_engine.domain.models import RelationType
from kg_engine.llm_core.extraction import extract_entities_from_document
from kg_engine.llm_core.provider import LLMProvider

logger = logging.getLogger(__name__)


def _map_relation_type(type_str: str) -> RelationType | None:
    """Map a string relation type to the domain enum."""
    normalized = type_str.strip().lower()
    return RELATION_TYPE_MAP.get(normalized)


def extract_and_resolve(
    provider: LLMProvider,
    title: str,
    text: str,
    *,
    resolve_names: dict[str, str] | None = None,
) -> DocumentExtractionResult:
    """Extract entities from a document and optionally resolve names to existing graph IDs.

    Args:
        provider: LLM provider for extraction.
        title: Document title.
        text: Document text content.
        resolve_names: Optional mapping of extracted entity names to existing
            graph entity IDs. When provided, relationships reference resolved IDs
            instead of raw names.

    Returns:
        Validated DocumentExtractionResult with entities, experiments,
        relationships, and any warnings.
    """
    result = extract_entities_from_document(provider, title, text)
    if not result.extraction_engine.startswith("deepagents"):
        result.extraction_engine = f"deepagents_{result.extraction_engine}"
    result.agent_trace = [
        {
            "event": "deepagents_extraction_started",
            "title": title,
        },
        *result.agent_trace,
        {
            "event": "deepagents_extraction_completed",
            "entities": len(result.entities),
            "experiments": len(result.experiments),
            "relationships": len(result.relationships),
        },
    ]

    if resolve_names and result.relationships:
        resolved: list[ExtractedRelationship] = []
        for rel in result.relationships:
            source_id = resolve_names.get(rel.source, rel.source)
            target_id = resolve_names.get(rel.target, rel.target)
            resolved.append(
                ExtractedRelationship(source=source_id, target=target_id, type=rel.type)
            )
        result.relationships = resolved

    return result


def build_entity_name_to_id_map(
    entities: list[ExtractedEntity],
    existing_ids: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build a name-to-ID mapping from extracted entities.

    Args:
        entities: Extracted entities from LLM.
        existing_ids: Optional pre-existing name→ID mapping (e.g. from graph).

    Returns:
        Mapping of entity canonical_name → entity_id.
    """
    mapping: dict[str, str] = dict(existing_ids or {})
    for ent in entities:
        if ent.name not in mapping:
            mapping[ent.name] = f"extracted_{EntityKind(ent.kind).value}_{ent.name}"
    return mapping


def resolve_relation_type(rel_type: str) -> RelationType:
    """Resolve a relation type string to the domain enum.

    Falls back to RELATED_TO for unknown types.
    """
    mapped = _map_relation_type(rel_type)
    if mapped is not None:
        return mapped
    logger.warning("Unknown relation type '%s', falling back to RELATED_TO", rel_type)
    return RelationType.RELATED_TO
