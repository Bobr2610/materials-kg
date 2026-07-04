"""LLM-powered entity and relationship extraction from documents."""

from __future__ import annotations

import json
import logging
import re
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
You answer strictly from the provided graph retrieval packet, citing sources.
</role>

<answer_language>
- Answer in the same language as the user's question.
- If source fragments are in another language, translate only what is needed for clarity.
- Do not mix languages unless a material name, method, unit, code, or source term requires it.
</answer_language>

<grounding_rules>
- Use ONLY facts present in the graph retrieval packet.
- Do not invent materials, modes, properties, experiments, values, units, teams, equipment, mechanisms, or relationships.
- Every factual claim MUST be tied to a source. Use this citation format:
  * For text fragments: [источник: file_name, стр. N] or [source: file_name, page N]
  * For measurements: [измерение: property value unit, источник: file_name, стр. N]
  * For experiments: [эксперимент: experiment_id, источник: file_name]
- Search for source_file and page in search_hits.metadata and evidence metadata to build citations.
- If the packet is insufficient, say: "Недостаточно данных в загруженных источниках для полного ответа."
- Explicitly call out data gaps when they are present.
</grounding_rules>

<graph_packet_contract>
- resolved_query: entities selected for this question.
- entity_lookup: names and kinds for IDs referenced by observations, relations, evidence, and gaps.
- observations: measured facts with source_file/page in metadata; prefer these for numerical answers.
- evidence and search_hits: source fragments with source_file/page metadata; use these for citations and wording.
- relations and decision_history: graph context, dependencies, conclusions, and related experiments/entities.
- data_gaps: known missing coverage; mention only when relevant.
</graph_packet_contract>

<citation_examples>
- "Прочность на разрыв CuCrZr составляет 450 МПа [измерение: tensile_strength 450 MPa, источник: report.pdf, стр. 12]"
- "Флотация угля описана в [источник: geokniga.pdf, стр. 27-29]"
- "Эксперимент exp_001 проводился с образцами CuCrZr при режиме отжига [эксперимент: exp_001, источник: lab_notes.xlsx]"
</citation_examples>

<answer_style>
- Be concise but complete.
- Prefer bullets or short sections when several measurements or gaps are present.
- Always include source citations for factual claims.
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


_ENTITY_PROMPT = """You are a materials science knowledge graph entity extractor.
Extract only canonical entities from the document. Do not extract relationships
or measurements in this step.

Document title: {title}
Document text:
{content}

Return a JSON object with:
{{
  "entities": [
    {{"kind": "material|property|mode|equipment|team|document|tag", "name": "...", "aliases": [...], "properties": {{}}}}
  ]
}}

Rules:
- Extract at most {max_entities} entities.
- Every entity MUST have a non-empty "name" field.
- Prefer canonical material names, alloy names, process/mode names, measured properties, equipment, teams, documents, and tags.
- Preserve aliases exactly when the document gives abbreviations or alternate spellings.
- If no entities are found, return {{"entities": []}}.
- Return ONLY valid JSON, no markdown."""


_RELATIONSHIP_PROMPT = """You are a materials science knowledge graph relationship extractor.
Use the provided entity list as the only allowed node set. Extract only explicit
or strongly implied relationships between those entities.

Document title: {title}
Known entities:
{entities_json}

Document text:
{content}

Return a JSON object with:
{{
  "relationships": [
    {{"source": "entity_name", "target": "entity_name", "type": "evaluates_material|uses_mode|measures_property|uses_equipment|performed_by|documented_in|tagged_with|references|related_to"}}
  ]
}}

Rules:
- Extract at most {max_relationships} relationships.
- Every relationship source and target MUST match an entity name from Known entities.
- Do not create new entities in this step.
- Use "related_to" when the relation is useful but does not fit a stricter type.
- If no relationships are found, return {{"relationships": []}}.
- Return ONLY valid JSON, no markdown."""


_MEASUREMENT_PROMPT = """You are a materials science measurement and experiment extractor.
Use the provided entity list as the vocabulary. Extract experiments, numerical
observations, units, and concise findings. Do not invent values.

Document title: {title}
Known entities:
{entities_json}

Document text:
{content}

Return a JSON object with:
{{
  "experiments": [
    {{
      "experiment_id": "...",
      "title": "...",
      "material_name": "...",
      "mode_name": "...",
      "observations": [
        {{"property_name": "...", "value": number, "unit": "...", "comparator": null, "fragment": "...", "row_reference": null, "confidence": 0.95}}
      ],
      "findings": [{{"summary": "...", "fragment": "...", "confidence": 0.9}}]
    }}
  ]
}}

Rules:
- Extract at most {max_experiments} experiments.
- Every experiment MUST have a non-empty material_name.
- Prefer material_name, mode_name, and property_name values from Known entities.
- Extract materials (alloys, steels, titanium, composites, etc.)
- Extract properties (tensile strength, hardness, fatigue, conductivity, etc.)
- Extract processing modes (annealing, aging, welding, sintering, etc.)
- Extract actual numerical measurements with units, including MPa, HRC, HV, %IACS, %, degC/C, min, h, and mm/s.
- Preserve comparator signs such as >, <, >=, <= when present.
- If no structured measurements are found, return {{"experiments": []}}.
- Return ONLY valid JSON, no markdown."""


_MONOLITHIC_FALLBACK_PROMPT = """You are a materials science knowledge graph extractor.
Analyze the document and return entities, relationships, and experiments in one
JSON object matching the same schemas used by the phased extraction pipeline.

Document title: {title}
Document text:
{content}

Return ONLY valid JSON with keys: entities, relationships, experiments, warnings."""


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
        raw_value = obs.get("value")
        if isinstance(raw_value, str) and raw_value.strip():
            try:
                numeric_value = float(raw_value.strip().replace(",", "."))
                if numeric_value == int(numeric_value):
                    numeric_value = int(numeric_value)
            except ValueError:
                numeric_value = None
        elif isinstance(raw_value, (int, float)):
            numeric_value = raw_value
        else:
            numeric_value = None
        observations.append(
            ObservationInput(
                property_name=prop_name,
                value=numeric_value,
                unit=(obs.get("unit") or "").strip() or None,
                comparator=(obs.get("comparator") or "").strip() or None,
                fragment=(obs.get("fragment") or "").strip() or None,
                row_reference=(obs.get("row_reference") or "").strip() or None,
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
                fragment=(f.get("fragment") or "").strip() or None,
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


def select_extraction_strategy(title: str, text: str) -> str:
    """Choose a document processing strategy from cheap document signals."""
    _ = title
    stripped = text.strip()
    if not stripped:
        return "empty"
    try:
        from kg_engine.config.settings import settings
        budget = int(getattr(settings, "llm_embedding_truncation_chars", 25000))
    except Exception:
        budget = 25000
    if len(stripped) > budget:
        return "chunked_phased"
    return "phased"


def _json_messages(role: str, prompt: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                f"You are {role}. Return one valid JSON object only. "
                "Do not include markdown or prose outside JSON."
            ),
        },
        {"role": "user", "content": prompt},
    ]


def _call_json_phase(
    provider: LLMProvider,
    *,
    role: str,
    prompt: str,
    max_tokens: int,
) -> dict[str, Any]:
    raw = provider.chat_json(
        _json_messages(role, prompt),
        temperature=0.1,
        max_tokens=max_tokens,
    )
    return raw if isinstance(raw, dict) else {}


def _entities_json(entities: list[ExtractedEntity]) -> str:
    return json.dumps(
        [
            {
                "kind": entity.kind.value,
                "name": entity.name,
                "aliases": entity.aliases,
            }
            for entity in entities
        ],
        ensure_ascii=False,
        indent=2,
    )


_CHUNK_SIZE = 3000
_CHUNK_OVERLAP = 500


def _get_chunk_config() -> tuple[int, int]:
    try:
        from kg_engine.config.settings import settings
        return (
            getattr(settings, "materials_llm_extraction_chunk_size", _CHUNK_SIZE),
            getattr(settings, "materials_llm_extraction_chunk_overlap", _CHUNK_OVERLAP),
        )
    except Exception:
        return (_CHUNK_SIZE, _CHUNK_OVERLAP)


def _chunk_text(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
    _size, _overlap = _get_chunk_config()
    chunk_size = chunk_size or _size
    overlap = overlap or _overlap
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += chunk_size - overlap
    return chunks


def _deduplicate_entities(entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
    """Deduplicate entities by normalized (lowered) name, keeping first occurrence."""
    seen: set[str] = set()
    result: list[ExtractedEntity] = []
    for e in entities:
        key = e.name.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(e)
    return result


def _deduplicate_relationships(relationships: list[ExtractedRelationship]) -> list[ExtractedRelationship]:
    """Deduplicate relationships by (source, target, type) tuple."""
    seen: set[tuple[str, str, str]] = set()
    result: list[ExtractedRelationship] = []
    for r in relationships:
        key = (r.source.strip().lower(), r.target.strip().lower(), r.type.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(r)
    return result


def _merge_chunk_results(
    chunk_results: list[DocumentExtractionResult],
) -> DocumentExtractionResult:
    """Merge extraction results from multiple chunks into one."""
    all_entities: list[ExtractedEntity] = []
    all_experiments: list[ExtractedExperiment] = []
    all_relationships: list[ExtractedRelationship] = []
    all_warnings: list[str] = []
    all_trace: list[dict[str, Any]] = []
    seen_exp_ids: set[str] = set()
    exp_counter = 0

    for result in chunk_results:
        all_entities.extend(result.entities)
        all_relationships.extend(result.relationships)
        all_warnings.extend(result.warnings or [])
        all_trace.extend(result.agent_trace or [])

        for exp in result.experiments:
            exp_id = exp.experiment_id
            merged_exp = exp
            if exp_id in seen_exp_ids:
                exp_counter += 1
                exp_id = f"{exp_id}_chunk{exp_counter}"
                merged_exp = ExtractedExperiment(
                    experiment_id=exp_id,
                    title=exp.title,
                    material_name=exp.material_name,
                    mode_name=exp.mode_name,
                    observations=exp.observations,
                    findings=exp.findings,
                )
            seen_exp_ids.add(exp_id)
            all_experiments.append(merged_exp)

    entities = _deduplicate_entities(all_entities)
    relationships = _deduplicate_relationships(all_relationships)

    return DocumentExtractionResult(
        entities=entities,
        experiments=all_experiments[:_MAX_EXTRACTED_EXPERIMENTS],
        relationships=relationships[:_MAX_EXTRACTED_RELATIONSHIPS],
        warnings=all_warnings,
        extraction_engine="llm_chunked_phased",
        agent_trace=all_trace,
    )


def _merge_phase_results(
    *,
    entities_raw: dict[str, Any],
    relationships_raw: dict[str, Any],
    measurements_raw: dict[str, Any],
    strategy: str,
    trace: list[dict[str, Any]],
) -> DocumentExtractionResult:
    entity_result = _validate_extraction({"entities": entities_raw.get("entities") or []})
    known_names = {entity.name for entity in entity_result.entities}
    name_index: dict[str, str] = {}
    for entity in entity_result.entities:
        name_index[entity.name] = entity.name
        name_index[entity.name.lower()] = entity.name
        for alias in entity.aliases:
            name_index[alias] = entity.name
            name_index[alias.lower()] = entity.name

    relationships: list[ExtractedRelationship] = []
    raw_relationships = relationships_raw.get("relationships") or []
    if isinstance(raw_relationships, list):
        for item in raw_relationships:
            if not isinstance(item, dict):
                continue
            rel = _validate_relationship(item, known_names, name_index)
            if rel is not None:
                relationships.append(rel)
    relationships = relationships[:_MAX_EXTRACTED_RELATIONSHIPS]

    experiments_result = _validate_extraction(
        {"experiments": measurements_raw.get("experiments") or []}
    )
    warnings = [
        *entity_result.warnings,
        *experiments_result.warnings,
    ]
    result = DocumentExtractionResult(
        entities=entity_result.entities,
        experiments=experiments_result.experiments[:_MAX_EXTRACTED_EXPERIMENTS],
        relationships=relationships,
        warnings=warnings,
        extraction_engine=f"llm_{strategy}",
        agent_trace=trace,
    )
    if not result.entities and not result.experiments and not result.relationships:
        result.warnings.append("No structured graph data extracted")
    return result


def _extract_chunked_phased(
    provider: LLMProvider,
    title: str,
    full_text: str,
    budget: int,
    parent_trace: list[dict[str, Any]],
) -> DocumentExtractionResult:
    """Chunk a long document and run phased extraction on each chunk."""
    chunk_size, overlap = _get_chunk_config()
    chunks = _chunk_text(full_text, chunk_size=chunk_size, overlap=overlap)
    logger.info(
        "Document '%s' chunked into %d segments (size=%d, overlap=%d) for extraction",
        title, len(chunks), chunk_size, overlap,
    )
    chunk_results: list[DocumentExtractionResult] = []
    for idx, chunk in enumerate(chunks):
        chunk_budget = min(budget, len(chunk))
        truncated_chunk = chunk[:chunk_budget] if len(chunk) > chunk_budget else chunk
        chunk_trace: list[dict[str, Any]] = [
            *parent_trace,
            {"event": "chunk_start", "chunk_index": idx, "chunk_chars": len(chunk)},
        ]

        entities_raw = _call_json_phase(
            provider,
            role="a materials science entity extractor",
            prompt=_ENTITY_PROMPT.format(
                title=f"{title} (chunk {idx + 1}/{len(chunks)})",
                content=truncated_chunk,
                max_entities=_MAX_EXTRACTED_ENTITIES,
            ),
            max_tokens=2048,
        )
        chunk_trace.append(
            {"event": "entities_extracted", "count": len(entities_raw.get("entities") or [])}
        )
        entity_result = _validate_extraction({"entities": entities_raw.get("entities") or []})
        entities_payload = _entities_json(entity_result.entities)

        relationships_raw: dict[str, Any] = {"relationships": []}
        if entity_result.entities:
            relationships_raw = _call_json_phase(
                provider,
                role="a materials science relationship extractor",
                prompt=_RELATIONSHIP_PROMPT.format(
                    title=f"{title} (chunk {idx + 1}/{len(chunks)})",
                    entities_json=entities_payload,
                    content=truncated_chunk,
                    max_relationships=_MAX_EXTRACTED_RELATIONSHIPS,
                ),
                max_tokens=2048,
            )
        chunk_trace.append(
            {"event": "relationships_extracted", "count": len(relationships_raw.get("relationships") or [])}
        )

        measurements_raw: dict[str, Any] = {"experiments": []}
        if re.search(r"\d", truncated_chunk):
            measurements_raw = _call_json_phase(
                provider,
                role="a materials science measurement extractor",
                prompt=_MEASUREMENT_PROMPT.format(
                    title=f"{title} (chunk {idx + 1}/{len(chunks)})",
                    entities_json=entities_payload,
                    content=truncated_chunk,
                    max_experiments=_MAX_EXTRACTED_EXPERIMENTS,
                ),
                max_tokens=4096,
            )
        chunk_trace.append(
            {"event": "measurements_extracted", "count": len(measurements_raw.get("experiments") or [])}
        )

        chunk_result = _merge_phase_results(
            entities_raw=entities_raw,
            relationships_raw=relationships_raw,
            measurements_raw=measurements_raw,
            strategy="chunked_phased",
            trace=chunk_trace,
        )
        chunk_results.append(chunk_result)

    return _merge_chunk_results(chunk_results)


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

    strategy = select_extraction_strategy(title, text)
    trace: list[dict[str, Any]] = [
        {
            "event": "strategy_selected",
            "strategy": strategy,
            "title": title,
            "chars": len(text),
        }
    ]
    if strategy == "empty":
        return DocumentExtractionResult(
            warnings=["Document text is empty"],
            extraction_engine="llm_empty",
            agent_trace=trace,
        )

    if strategy == "chunked_phased":
        return _extract_chunked_phased(provider, title, text, budget, trace)

    entities_raw = _call_json_phase(
        provider,
        role="a materials science entity extractor",
        prompt=_ENTITY_PROMPT.format(
            title=title,
            content=truncated,
            max_entities=_MAX_EXTRACTED_ENTITIES,
        ),
        max_tokens=2048,
    )
    trace.append(
        {
            "event": "entities_extracted",
            "count": len(entities_raw.get("entities") or []),
        }
    )
    entity_result = _validate_extraction({"entities": entities_raw.get("entities") or []})

    entities_payload = _entities_json(entity_result.entities)
    relationships_raw: dict[str, Any] = {"relationships": []}
    if entity_result.entities:
        relationships_raw = _call_json_phase(
            provider,
            role="a materials science relationship extractor",
            prompt=_RELATIONSHIP_PROMPT.format(
                title=title,
                entities_json=entities_payload,
                content=truncated,
                max_relationships=_MAX_EXTRACTED_RELATIONSHIPS,
            ),
            max_tokens=2048,
        )
    trace.append(
        {
            "event": "relationships_extracted",
            "count": len(relationships_raw.get("relationships") or []),
        }
    )

    measurements_raw: dict[str, Any] = {"experiments": []}
    measurements_raw = _call_json_phase(
            provider,
            role="a materials science measurement extractor",
            prompt=_MEASUREMENT_PROMPT.format(
                title=title,
                entities_json=entities_payload,
                content=truncated,
                max_experiments=_MAX_EXTRACTED_EXPERIMENTS,
            ),
            max_tokens=4096,
        )
    trace.append(
        {
            "event": "measurements_extracted",
            "count": len(measurements_raw.get("experiments") or []),
        }
    )

    result = _merge_phase_results(
        entities_raw=entities_raw,
        relationships_raw=relationships_raw,
        measurements_raw=measurements_raw,
        strategy=strategy,
        trace=trace,
    )
    if not result.entities and not result.experiments and not result.relationships:
        raw = _call_json_phase(
            provider,
            role="a materials science knowledge graph extractor",
            prompt=_MONOLITHIC_FALLBACK_PROMPT.format(title=title, content=truncated),
            max_tokens=4096,
        )
        if raw:
            result = _validate_extraction(raw)
            result.extraction_engine = "llm_monolithic_fallback"
            result.agent_trace = [*trace, {"event": "monolithic_fallback_used"}]
    return result


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
