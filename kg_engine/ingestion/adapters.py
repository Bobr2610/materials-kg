"""Adapters that normalize raw source-family payloads into domain inputs."""

from __future__ import annotations

import json
from typing import Any

from kg_engine.domain.models import CanonicalEntityInput
from kg_engine.domain.models import CoverageRuleInput
from kg_engine.domain.models import DocumentInput
from kg_engine.domain.models import EntityKind
from kg_engine.domain.models import ExperimentInput
from kg_engine.domain.models import FindingInput
from kg_engine.domain.models import ObservationInput
from kg_engine.domain.models import ReferenceDataBatch
from kg_engine.domain.models import TextUnitInput


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return parsed
        for separator in (";", "|"):
            if separator in stripped:
                return [part.strip() for part in stripped.split(separator) if part.strip()]
        return [stripped]
    return [value]


def _first(item: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in item and item[name] not in (None, ""):
            return item[name]
    return default


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        normalized = value.strip().replace(",", ".")
        if not normalized:
            return None
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _record_list(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if any(key in payload for key in ("name", "title", "id", "document_id")):
            return [payload]
    return []


def _entity_kind(value: Any) -> EntityKind | None:
    if isinstance(value, EntityKind):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    try:
        return EntityKind(normalized)
    except ValueError:
        return None


def _entity_from_item(
    item: dict[str, Any],
    *,
    default_kind: EntityKind | None = None,
) -> CanonicalEntityInput | None:
    kind = _entity_kind(_first(item, "kind", "entity_kind", "type")) or default_kind
    name = _first(item, "name", "title", "label", "canonical_name")
    if kind is None or not name:
        return None
    reserved = {
        "kind",
        "entity_kind",
        "type",
        "name",
        "title",
        "label",
        "canonical_name",
        "canonical_id",
        "id",
        "code",
        "aliases",
        "properties",
        "source_ref",
        "source",
        "file",
    }
    properties = {
        key: value
        for key, value in item.items()
        if key not in reserved and value not in (None, "")
    }
    properties.update(_as_dict(item.get("properties")))
    return CanonicalEntityInput(
        kind=kind,
        name=name,
        canonical_id=_first(item, "canonical_id", "id", "code"),
        aliases=_as_list(item.get("aliases")),
        properties=properties,
        source_ref=_first(item, "source_ref", "source", "file"),
    )


def _extra_fields(item: dict[str, Any], reserved: set[str]) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if key not in reserved and value not in (None, "")
    }


class ReferenceDataAdapter:
    """Normalize materials, equipment, and coverage dictionaries."""

    def from_payload(self, payload: dict[str, Any]) -> ReferenceDataBatch:
        entities: list[CanonicalEntityInput] = []
        for item in _record_list(payload.get("entities"), "entities", "rows"):
            entity = _entity_from_item(item)
            if entity is not None:
                entities.append(entity)
        for section, entity_kind in (
            ("materials", EntityKind.MATERIAL),
            ("equipment", EntityKind.EQUIPMENT),
            ("properties", EntityKind.PROPERTY),
            ("modes", EntityKind.MODE),
            ("teams", EntityKind.TEAM),
            ("documents", EntityKind.DOCUMENT),
            ("tags", EntityKind.TAG),
        ):
            for item in _record_list(payload.get(section), section):
                entity = _entity_from_item(item, default_kind=entity_kind)
                if entity is not None:
                    entities.append(entity)
        coverage_rules = [
            CoverageRuleInput.model_validate(item)
            for item in payload.get("coverage_rules", [])
        ]
        return ReferenceDataBatch(entities=entities, coverage_rules=coverage_rules)


class ExperimentCatalogAdapter:
    """Normalize experiment-catalog rows into structured experiment inputs."""

    def from_payload(self, payload: Any) -> list[ExperimentInput]:
        experiments: list[ExperimentInput] = []
        experiment_reserved = {
            "experiment_id",
            "id",
            "code",
            "title",
            "name",
            "material_name",
            "material",
            "alloy",
            "mode_name",
            "mode",
            "regime",
            "equipment_names",
            "equipment",
            "team_name",
            "team",
            "lab",
            "laboratory",
            "document_id",
            "source_version",
            "observations",
            "findings",
            "text_units",
            "metadata",
        }
        observation_reserved = {
            "property_name",
            "property",
            "property_id",
            "value",
            "measurement",
            "result",
            "unit",
            "units",
            "comparator",
            "fragment",
            "quote",
            "source_fragment",
            "row_reference",
            "row",
            "cell",
            "extraction_method",
            "confidence",
            "metadata",
        }
        finding_reserved = {
            "summary",
            "finding",
            "conclusion",
            "decision",
            "fragment",
            "extraction_method",
            "confidence",
            "observation_indices",
            "changed_from_trace_id",
            "metadata",
        }
        for item in _record_list(payload, "experiments", "rows"):
            observations_payload = _record_list(item.get("observations"))
            if not observations_payload and _first(item, "property_name", "property"):
                observations_payload = [item]
            observations = [
                ObservationInput(
                    property_name=_first(entry, "property_name", "property", "property_id"),
                    value=_as_float(_first(entry, "value", "measurement", "result")),
                    unit=_first(entry, "unit", "units"),
                    comparator=entry.get("comparator"),
                    fragment=_first(entry, "fragment", "quote", "source_fragment"),
                    row_reference=_first(entry, "row_reference", "row", "cell"),
                    extraction_method=entry.get(
                        "extraction_method",
                        "structured_experiment",
                    ),
                    confidence=entry.get("confidence", 1.0),
                    metadata={
                        **_extra_fields(entry, observation_reserved),
                        **_as_dict(entry.get("metadata")),
                    },
                )
                for entry in observations_payload
                if _first(entry, "property_name", "property", "property_id")
            ]
            findings_payload = _record_list(item.get("findings"))
            if not findings_payload and _first(item, "finding", "summary", "conclusion"):
                findings_payload = [item]
            findings = [
                FindingInput(
                    summary=_first(entry, "summary", "finding", "conclusion"),
                    decision=entry.get("decision"),
                    fragment=entry.get("fragment"),
                    extraction_method=entry.get(
                        "extraction_method",
                        "structured_finding",
                    ),
                    confidence=entry.get("confidence", 1.0),
                    observation_indices=_as_list(entry.get("observation_indices")),
                    changed_from_trace_id=entry.get("changed_from_trace_id"),
                    metadata={
                        **_extra_fields(entry, finding_reserved),
                        **_as_dict(entry.get("metadata")),
                    },
                )
                for entry in findings_payload
                if _first(entry, "summary", "finding", "conclusion")
            ]
            text_units = [
                TextUnitInput(
                    content=_first(entry, "content", "text", "body"),
                    metadata=_as_dict(entry.get("metadata")),
                )
                for entry in _record_list(item.get("text_units"))
                if _first(entry, "content", "text", "body")
            ]
            experiment_id = _first(item, "experiment_id", "id", "code")
            material_name = _first(item, "material_name", "material", "alloy")
            if not experiment_id or not material_name:
                continue
            experiments.append(
                ExperimentInput(
                    experiment_id=experiment_id,
                    title=_first(item, "title", "name", default=experiment_id),
                    material_name=material_name,
                    mode_name=_first(item, "mode_name", "mode", "regime"),
                    equipment_names=_as_list(_first(item, "equipment_names", "equipment")),
                    team_name=_first(item, "team_name", "team", "lab", "laboratory"),
                    document_id=item.get("document_id"),
                    source_version=item.get("source_version"),
                    observations=observations,
                    findings=findings,
                    text_units=text_units,
                    metadata={
                        **_extra_fields(item, experiment_reserved),
                        **_as_dict(item.get("metadata")),
                    },
                )
            )
        return experiments


class DocumentCorpusAdapter:
    """Normalize internal document-corpus records into document inputs."""

    def from_payload(self, payload: Any) -> list[DocumentInput]:
        documents: list[DocumentInput] = []
        document_reserved = {
            "document_id",
            "id",
            "path",
            "file",
            "title",
            "name",
            "text",
            "content",
            "body",
            "material_names",
            "materials",
            "mode_names",
            "modes",
            "property_names",
            "properties",
            "equipment_names",
            "equipment",
            "team_names",
            "teams",
            "labs",
            "tag_names",
            "tags",
            "experiment_ids",
            "findings",
            "text_units",
            "metadata",
        }
        for item in _record_list(payload, "documents", "rows"):
            findings = [
                FindingInput(
                    summary=_first(entry, "summary", "finding", "conclusion"),
                    decision=entry.get("decision"),
                    fragment=entry.get("fragment"),
                    extraction_method=entry.get(
                        "extraction_method",
                        "document_finding",
                    ),
                    confidence=entry.get("confidence", 1.0),
                    observation_indices=_as_list(entry.get("observation_indices")),
                    changed_from_trace_id=entry.get("changed_from_trace_id"),
                    metadata={
                        **_extra_fields(entry, {"metadata"}),
                        **_as_dict(entry.get("metadata")),
                    },
                )
                for entry in _record_list(item.get("findings"))
                if _first(entry, "summary", "finding", "conclusion")
            ]
            text_units = [
                TextUnitInput(
                    content=_first(entry, "content", "text", "body"),
                    metadata=_as_dict(entry.get("metadata")),
                )
                for entry in _record_list(item.get("text_units"))
                if _first(entry, "content", "text", "body")
            ]
            document_id = _first(item, "document_id", "id", "path", "file")
            text = _first(item, "text", "content", "body", default="")
            if not document_id or not text:
                continue
            documents.append(
                DocumentInput(
                    document_id=document_id,
                    title=_first(item, "title", "name", default=document_id),
                    text=text,
                    material_names=_as_list(_first(item, "material_names", "materials")),
                    mode_names=_as_list(_first(item, "mode_names", "modes")),
                    property_names=_as_list(_first(item, "property_names", "properties")),
                    equipment_names=_as_list(_first(item, "equipment_names", "equipment")),
                    team_names=_as_list(_first(item, "team_names", "teams", "labs")),
                    tag_names=_as_list(_first(item, "tag_names", "tags")),
                    experiment_ids=_as_list(item.get("experiment_ids")),
                    findings=findings,
                    text_units=text_units,
                    metadata={
                        **_extra_fields(item, document_reserved),
                        **_as_dict(item.get("metadata")),
                    },
                )
            )
        return documents


class StaffDirectoryAdapter:
    """Normalize employee/lab directory data into canonical team records."""

    def from_payload(self, payload: Any) -> ReferenceDataBatch:
        entities = [
            CanonicalEntityInput(
                kind=EntityKind.TEAM,
                name=_first(item, "name", "team", "lab", "laboratory"),
                canonical_id=_first(item, "canonical_id", "id", "code"),
                aliases=_as_list(item.get("aliases")),
                properties={
                    "members": _as_list(item.get("members")),
                    **_as_dict(item.get("properties")),
                },
                source_ref=item.get("source_ref"),
            )
            for item in _record_list(payload, "teams", "staff", "labs", "rows")
            if _first(item, "name", "team", "lab", "laboratory")
        ]
        return ReferenceDataBatch(entities=entities, coverage_rules=[])


class TagCatalogAdapter:
    """Normalize topic-tag catalogs into canonical tag records."""

    def from_payload(self, payload: Any) -> ReferenceDataBatch:
        entities = [
            CanonicalEntityInput(
                kind=EntityKind.TAG,
                name=_first(item, "name", "tag", "label"),
                canonical_id=_first(item, "canonical_id", "id", "code"),
                aliases=_as_list(item.get("aliases")),
                properties=_as_dict(item.get("properties")),
                source_ref=item.get("source_ref"),
            )
            for item in _record_list(payload, "tags", "topics", "rows")
            if _first(item, "name", "tag", "label")
        ]
        return ReferenceDataBatch(entities=entities, coverage_rules=[])
