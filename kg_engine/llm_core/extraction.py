"""LLM-powered entity and relationship extraction from documents."""

from __future__ import annotations

import json
import logging
from typing import Any

from kg_engine.domain.models import DocumentExtractionResult
from kg_engine.domain.models import ExtractedEntity
from kg_engine.domain.models import ExtractedExperiment
from kg_engine.domain.models import ExtractedRelationship
from kg_engine.domain.models import EntityKind
from kg_engine.domain.models import ObservationInput
from kg_engine.domain.models import FindingInput
from kg_engine.llm_core.provider import LLMProvider

logger = logging.getLogger(__name__)

_MAX_EXTRACTED_ENTITIES = 50
_MAX_EXTRACTED_EXPERIMENTS = 20
_MAX_EXTRACTED_RELATIONSHIPS = 30

_ANSWER_CONTEXT_KEYS = [
    "resolved_query",
    "matched_entities",
    "entity_lookup",
    "experiments",
    "observations",
    "decision_history",
    "data_gaps",
    "evidence",
    "search_hits",
    "relations",
    "warnings",
]

MATERIALS_ANSWER_SYSTEM_PROMPT = """<role>
You are a materials science research assistant working over a graph-backed evidence base.
You answer strictly from the provided graph retrieval packet.
</role>

<answer_language>
- Answer in the same language as the user's question.
- If source fragments are in another language, translate only what is needed for clarity.
- Do not mix languages unless a material name, method, unit, code, or source term requires it.
</answer_language>

<grounding_rules>
- Use ONLY facts present in the graph retrieval packet.
- Do not invent materials, modes, properties, experiments, values, units, teams, equipment, mechanisms, or relationships.
- Tie important claims to evidence: mention source_id and, when useful, the fragment, row_reference, value, unit, or confidence.
- If the packet is insufficient, say: "Недостаточно данных в загруженных источниках для полного ответа."
- Explicitly call out data gaps when they are present.
</grounding_rules>

<graph_packet_contract>
- resolved_query: entities selected for this question.
- entity_lookup: names and kinds for IDs referenced by observations, relations, evidence, and gaps.
- observations: measured facts; prefer these for numerical answers.
- evidence and search_hits: source fragments; use these for citations and wording.
- relations and decision_history: graph context, dependencies, conclusions, and related experiments/entities.
- data_gaps: known missing coverage; mention only when relevant.
</graph_packet_contract>

<answer_style>
- Be concise but complete.
- Prefer bullets or short sections when several measurements or gaps are present.
- Do not expose hidden reasoning or query-planning text.
- Never duplicate sections.
</answer_style>"""


def _compact_graph_context(graph_context: dict[str, Any]) -> dict[str, Any]:
    """Keep the graph packet structured while bounding noisy arrays."""
    limits = {
        "matched_entities": 16,
        "experiments": 12,
        "observations": 24,
        "decision_history": 12,
        "data_gaps": 12,
        "evidence": 16,
        "search_hits": 10,
        "relations": 20,
    }
    compact: dict[str, Any] = {}
    for key in _ANSWER_CONTEXT_KEYS:
        value = graph_context.get(key)
        if not value:
            continue
        if isinstance(value, list):
            compact[key] = value[: limits.get(key, 20)]
        else:
            compact[key] = value
    return compact


def build_answer_messages(
    question: str,
    graph_context: dict[str, Any],
    conversation_history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Build grounded answer messages from a graph retrieval packet."""
    compact_context = _compact_graph_context(graph_context)
    context_json = json.dumps(
        compact_context,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    user_content = (
        "Graph retrieval packet (JSON, authoritative):\n"
        f"{context_json}\n\n"
        f"Question: {question}"
    )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": MATERIALS_ANSWER_SYSTEM_PROMPT}
    ]
    if conversation_history:
        for hist_msg in conversation_history[-10:]:
            role = hist_msg.get("role", "")
            content = hist_msg.get("content", "")
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_content})

    try:
        from kg_engine.config.settings import settings
        from kg_engine.llm_core.token_budget import (
            count_messages_tokens,
            fit_context_to_budget,
        )

        total_tokens = count_messages_tokens(messages)
        context_window = settings.llm_context_window
        safety_margin = settings.llm_safety_margin_tokens

        if total_tokens > context_window - safety_margin:
            overhead = count_messages_tokens(messages[:-1])
            truncated_context = fit_context_to_budget(
                compact_context,
                budget=context_window,
                system_prompt_tokens=overhead,
                safety_margin=safety_margin + count_messages_tokens([messages[-1]]),
            )
            user_content = (
                "Graph retrieval packet (JSON, authoritative, truncated to fit context):\n"
                f"{json.dumps(truncated_context, ensure_ascii=False, indent=2, default=str)}\n\n"
                f"Question: {question}"
            )
            messages[-1] = {"role": "user", "content": user_content}
    except Exception:
        logger.debug("Token budget management failed, using default graph packet")

    return messages


# ── Extraction prompts ──────────────────────────────────────────────


_EXTRACT_PROMPT = """You are a materials science knowledge graph extractor.
Analyze the following document and extract entities, experiments, and relationships.

Document title: {title}
Document text:
{content}

Return a JSON object with:
{{
  "entities": [
    {{"kind": "material|property|mode|equipment|team|tag", "name": "...", "aliases": [...], "properties": {{}}}}
  ],
  "experiments": [
    {{
      "experiment_id": "...",
      "title": "...",
      "material_name": "...",
      "mode_name": "...",
      "observations": [
        {{"property_name": "...", "value": number, "unit": "...", "confidence": 0.95}}
      ],
      "findings": [{{"summary": "...", "confidence": 0.9}}]
    }}
  ],
  "relationships": [
    {{"source": "entity_name", "target": "entity_name", "type": "evaluates_material|uses_mode|measures_property|uses_equipment|performed_by|documented_in|references|related_to"}}
  ]
}}

Rules:
- Extract at most {max_entities} entities, {max_experiments} experiments, {max_relationships} relationships.
- Every entity MUST have a non-empty "name" field.
- Every experiment MUST have a non-empty "material_name" field.
- Every relationship MUST reference entity names that appear in the "entities" array.
- Extract materials (alloys, steels, titanium, composites, etc.)
- Extract properties (tensile strength, hardness, fatigue, conductivity, etc.)
- Extract processing modes (annealing, aging, welding, sintering, etc.)
- Extract equipment and team names if mentioned
- For experiments, extract actual numerical measurements with units
- Be precise with values and units
- If no structured data found, return empty arrays
- Return ONLY valid JSON, no markdown"""


_UPLOAD_STRUCTURE_PROMPT = """You are a materials science ingestion agent.
Your job is to profile an arbitrary uploaded file and map its columns/fields
into the canonical payloads used by a graph-backed materials knowledge base.

Filename: {filename}
File type: {file_type}
Parsed content sample:
{content}

Return ONLY a JSON object with this schema:
{{
  "reference": {{
    "entities": [
      {{"kind": "material|property|mode|equipment|team|document|tag", "name": "...", "aliases": [], "properties": {{}}}}
    ],
    "coverage_rules": [
      {{"rule_id": "...", "name": "...", "material_names": [], "mode_names": [], "property_names": [], "scope": "material-mode-property", "metadata": {{}}}}
    ]
  }},
  "experiments": [
    {{
      "experiment_id": "...",
      "title": "...",
      "material_name": "...",
      "mode_name": "...",
      "equipment_names": [],
      "team_name": null,
      "source_ref": "{filename}",
      "observations": [
        {{"property_name": "...", "value": 0, "unit": "...", "fragment": "...", "row_reference": "...", "confidence": 0.8}}
      ],
      "findings": [
        {{"summary": "...", "fragment": "...", "confidence": 0.8}}
      ],
      "text_units": [],
      "metadata": {{}}
    }}
  ],
  "documents": [
    {{"document_id": "...", "title": "...", "text": "...", "source_ref": "{filename}", "metadata": {{}}}}
  ]
}}

Rules:
- Infer what each column/field means from headers, values, units, and materials-science context.
- Do not require exact column names — the source may use arbitrary names, abbreviations, or another language.
- Store column mapping in metadata under "llm_column_mapping" when useful.
- Convert rows into experiments only when there is enough evidence for a material, a property, and a value.
- Use any column that behaves like a processing route, treatment, or condition as mode_name.
- Preserve row-level provenance in fragment and row_reference.
- Do not invent values, units, materials, modes, or experiments.
- If a row is too ambiguous, put it into documents as searchable text.
- Add source_ref="{filename}" or metadata.source_file="{filename}" to every record.
"""


# ── Validation helpers ──────────────────────────────────────────────


def _validate_entity(raw: dict[str, Any]) -> ExtractedEntity | None:
    """Validate a single raw entity dict. Returns None if invalid."""
    name = (raw.get("name") or "").strip()
    if not name:
        return None
    kind_str = (raw.get("kind") or "document").strip().lower()
    try:
        kind = EntityKind(kind_str)
    except ValueError:
        kind = EntityKind.DOCUMENT
    aliases = [
        str(a).strip()
        for a in (raw.get("aliases") or [])
        if isinstance(a, str) and a.strip()
    ]
    properties = raw.get("properties") or {}
    if not isinstance(properties, dict):
        properties = {}
    return ExtractedEntity(
        kind=kind,
        name=name,
        aliases=aliases,
        properties=properties,
    )


def _validate_experiment(raw: dict[str, Any], index: int) -> ExtractedExperiment | None:
    """Validate a single raw experiment dict. Returns None if invalid."""
    material_name = (raw.get("material_name") or "").strip()
    if not material_name:
        return None
    experiment_id = (raw.get("experiment_id") or "").strip()
    if not experiment_id:
        experiment_id = f"llm_exp_{index}"
    title = (raw.get("title") or "").strip()
    mode_name = (raw.get("mode_name") or "").strip()

    observations: list[ObservationInput] = []
    for obs in raw.get("observations") or []:
        prop_name = (obs.get("property_name") or "").strip()
        if not prop_name:
            continue
        observations.append(
            ObservationInput(
                property_name=prop_name,
                value=obs.get("value") if isinstance(obs.get("value"), int | float) else None,
                unit=(obs.get("unit") or "").strip() or None,
                confidence=_safe_float(obs.get("confidence"), 0.85),
                extraction_method="llm_extraction",
            )
        )

    findings: list[FindingInput] = []
    for f in raw.get("findings") or []:
        summary = (f.get("summary") or "").strip()
        if not summary:
            continue
        findings.append(
            FindingInput(
                summary=summary,
                confidence=_safe_float(f.get("confidence"), 0.85),
                extraction_method="llm_extraction",
            )
        )

    return ExtractedExperiment(
        experiment_id=experiment_id,
        title=title or f"Extracted experiment #{index}",
        material_name=material_name,
        mode_name=mode_name,
        observations=observations,
        findings=findings,
    )


def _safe_float(value: Any, default: float = 0.85) -> float:
    """Convert a value to float safely, returning default on failure."""
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            pass
    return default


def _validate_relationship(
    raw: dict[str, Any],
    known_names: set[str],
    name_index: dict[str, str] | None = None,
) -> ExtractedRelationship | None:
    """Validate a single raw relationship dict. Returns None if invalid."""
    source = (raw.get("source") or "").strip()
    target = (raw.get("target") or "").strip()
    rel_type = (raw.get("type") or "").strip()
    if not source or not target or not rel_type:
        return None
    idx = name_index or {n: n for n in known_names}
    resolved_source = idx.get(source) or idx.get(source.lower())
    resolved_target = idx.get(target) or idx.get(target.lower())
    if not resolved_source or not resolved_target:
        return None
    return ExtractedRelationship(
        source=resolved_source, target=resolved_target, type=rel_type,
    )


def _validate_extraction(raw: dict[str, Any]) -> DocumentExtractionResult:
    """Validate and normalize raw LLM extraction output into typed DTOs."""
    warnings: list[str] = []

    raw_entities = raw.get("entities") or []
    if not isinstance(raw_entities, list):
        raw_entities = []

    entities: list[ExtractedEntity] = []
    seen_names: set[str] = set()
    for item in raw_entities:
        if not isinstance(item, dict):
            continue
        entity = _validate_entity(item)
        if entity is None:
            name = (item.get("name") or "").strip()
            if name:
                warnings.append("Entity with empty name skipped")
            continue
        if entity.name in seen_names:
            continue
        seen_names.add(entity.name)
        entities.append(entity)
    if len(raw_entities) > _MAX_EXTRACTED_ENTITIES:
        warnings.append(
            f"LLM returned {len(raw_entities)} entities, capped at {_MAX_EXTRACTED_ENTITIES}"
        )
        entities = entities[:_MAX_EXTRACTED_ENTITIES]

    raw_experiments = raw.get("experiments") or []
    if not isinstance(raw_experiments, list):
        raw_experiments = []

    experiments: list[ExtractedExperiment] = []
    for idx, item in enumerate(raw_experiments):
        if not isinstance(item, dict):
            continue
        exp = _validate_experiment(item, idx)
        if exp is None:
            mat = (item.get("material_name") or "").strip()
            if not mat:
                warnings.append(f"Experiment #{idx} skipped: empty material_name")
            continue
        experiments.append(exp)
    if len(raw_experiments) > _MAX_EXTRACTED_EXPERIMENTS:
        warnings.append(
            f"LLM returned {len(raw_experiments)} experiments, capped at {_MAX_EXTRACTED_EXPERIMENTS}"
        )
        experiments = experiments[:_MAX_EXTRACTED_EXPERIMENTS]

    raw_relationships = raw.get("relationships") or []
    if not isinstance(raw_relationships, list):
        raw_relationships = []

    name_index: dict[str, str] = {}
    for name in seen_names:
        name_index[name] = name
        name_index[name.lower()] = name

    relationships: list[ExtractedRelationship] = []
    for item in raw_relationships:
        if not isinstance(item, dict):
            continue
        rel = _validate_relationship(item, seen_names, name_index)
        if rel is None:
            continue
        relationships.append(rel)
    if len(raw_relationships) > _MAX_EXTRACTED_RELATIONSHIPS:
        warnings.append(
            f"LLM returned {len(raw_relationships)} relationships, capped at {_MAX_EXTRACTED_RELATIONSHIPS}"
        )
        relationships = relationships[:_MAX_EXTRACTED_RELATIONSHIPS]

    return DocumentExtractionResult(
        entities=entities,
        experiments=experiments,
        relationships=relationships,
        warnings=warnings,
    )


# ── Public extraction functions ─────────────────────────────────────


def extract_entities_from_document(
    provider: LLMProvider,
    title: str,
    text: str,
) -> DocumentExtractionResult:
    """Use LLM to extract entities, experiments, and relationships from a document.

    Returns a validated DocumentExtractionResult. Entities with empty names,
    experiments without material_name, and relationships referencing unknown
    entities are silently dropped with warnings.
    """
    from kg_engine.config.settings import settings

    budget = settings.llm_embedding_truncation_chars
    truncated = text[:budget] if len(text) > budget else text
    if len(text) > budget:
        logger.info(
            "Document '%s' truncated from %d to %d chars for LLM extraction",
            title, len(text), budget,
        )

    messages = [
        {
            "role": "system",
            "content": "You are a materials science knowledge graph extractor. Return only valid JSON.",
        },
        {
            "role": "user",
            "content": _EXTRACT_PROMPT.format(
                title=title,
                content=truncated,
                max_entities=_MAX_EXTRACTED_ENTITIES,
                max_experiments=_MAX_EXTRACTED_EXPERIMENTS,
                max_relationships=_MAX_EXTRACTED_RELATIONSHIPS,
            ),
        },
    ]
    raw = provider.chat_json(messages, temperature=0.1, max_tokens=4096)
    if not raw:
        return DocumentExtractionResult(
            warnings=["LLM returned empty response"],
        )
    return _validate_extraction(raw)


def structure_upload_with_llm(
    provider: LLMProvider,
    filename: str,
    file_type: str,
    parsed_content: Any,
) -> dict[str, Any]:
    """Use the LLM to route arbitrary uploaded data into graph ingestion payloads."""
    from kg_engine.config.settings import settings

    content = json.dumps(parsed_content, ensure_ascii=False, indent=2, default=str)
    budget = settings.llm_embedding_truncation_chars
    truncated = content[:budget] if len(content) > budget else content
    messages = [
        {
            "role": "system",
            "content": (
                "You are a materials science data ingestion agent. "
                "Return only valid JSON matching the requested schema."
            ),
        },
        {
            "role": "user",
            "content": _UPLOAD_STRUCTURE_PROMPT.format(
                filename=filename,
                file_type=file_type,
                content=truncated,
            ),
        },
    ]
    result = provider.chat_json(messages, temperature=0.1, max_tokens=4096)
    if not result:
        return {"reference": {}, "experiments": [], "documents": []}
    return {
        "reference": result.get("reference") or {},
        "experiments": result.get("experiments") or [],
        "documents": result.get("documents") or [],
    }


def llm_generate_answer(
    provider: LLMProvider,
    question: str,
    graph_context: dict[str, Any],
    conversation_history: list[dict[str, str]] | None = None,
) -> str:
    """Use LLM to generate a natural language answer from graph query results."""
    messages = build_answer_messages(question, graph_context, conversation_history)
    answer = provider.chat(messages, temperature=0.3, max_tokens=1024)
    return answer or ""
