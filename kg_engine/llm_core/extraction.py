"""LLM-powered entity and relationship extraction from documents."""

from __future__ import annotations

import logging
from typing import Any
import json

from kg_engine.domain.models import CanonicalEntityInput
from kg_engine.domain.models import DocumentInput
from kg_engine.domain.models import EntityKind
from kg_engine.domain.models import ExperimentInput
from kg_engine.domain.models import ObservationInput
from kg_engine.llm_core.provider import LLMProvider

logger = logging.getLogger(__name__)

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


def _build_graph_context_str(graph_context: dict[str, Any]) -> str:
    """Build a text representation of graph context for LLM consumption."""
    parts: list[str] = []

    if graph_context.get("matched_entities"):
        names = [
            e.get("canonical_name", "") for e in graph_context["matched_entities"][:10]
        ]
        parts.append(f"Matched entities: {', '.join(names)}")

    if graph_context.get("experiments"):
        for exp in graph_context["experiments"][:5]:
            parts.append(f"Experiment: {exp.get('canonical_name', exp.get('id', ''))}")

    if graph_context.get("observations"):
        obs_text = "; ".join(
            f"{o.get('property_id', '')}: {o.get('value', 'n/a')} {o.get('unit', '')}"
            for o in graph_context["observations"][:10]
        )
        parts.append(f"Measurements: {obs_text}")

    if graph_context.get("evidence"):
        for ev in graph_context["evidence"][:8]:
            source_id = ev.get("source_id", "")
            source_kind = ev.get("source_kind", "")
            fragment = (
                ev.get("span", {}).get("fragment", "")
                if isinstance(ev.get("span"), dict)
                else ""
            )
            parts.append(
                f"Evidence [{source_kind}] from '{source_id}': {fragment[:300]}"
            )

    if graph_context.get("search_hits"):
        for h in graph_context["search_hits"][:5]:
            parts.append(
                f"Source text from '{h.get('source_entity_id', '')}': {h.get('content', '')[:400]}"
            )

    return "\n".join(parts) if parts else "No data found in knowledge graph."


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


_EXTRACT_PROMPT = """You are a materials science knowledge graph extractor.
Analyze the following document and extract ALL entities and relationships.

Document title: {title}
Document text:
{content}

Return a JSON object with:
{{
  "entities": [
    {{"kind": "material|property|mode|equipment|team|tag|document", "name": "...", "aliases": [...], "properties": {{}}}},
    ...
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
    {{"source": "entity_name", "target": "entity_name", "type": "uses_mode|measures_property|uses_equipment|performed_by|documented_in"}}
  ]
}}

Rules:
- Extract EVERY material mentioned (alloys, steels, titanium, etc.)
- Extract EVERY property measured (tensile strength, hardness, fatigue, etc.)
- Extract EVERY processing mode (annealing, aging, welding, etc.)
- Extract equipment and team names if mentioned
- For experiments, extract actual numerical measurements with units
- Be precise with values and units
- If no structured data found, return empty arrays
- Return ONLY valid JSON, no markdown"""


_UPLOAD_STRUCTURE_PROMPT = """You are a materials science ingestion agent.
Your job is to profile an arbitrary uploaded file and invent the mapping from
its own columns/fields into the canonical payloads used by a graph-backed
materials knowledge base.

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
- First infer what each column/field means from headers, values, units,
  neighboring fields, row patterns, and materials-science context.
- The source may use arbitrary names, abbreviations, another language, internal
  codes, or no obvious names at all. Do not require exact column names.
- Create the column/field mapping yourself and store it in metadata under
  "llm_column_mapping" for emitted records when useful.
- Convert rows into experiments only when the row contains enough evidence for
  a material/sample, a measured or target property, and an observed value/result.
- Use any column that behaves like a processing route, treatment, condition,
  state, protocol, or environment as mode_name, but only if the data supports it.
- Preserve row-level provenance in fragment and row_reference.
- Do not invent values, units, materials, modes, or experiments.
- If a row is too ambiguous, put it into documents as searchable text.
- Add source_ref="{filename}" or metadata.source_file="{filename}" to every emitted record.
"""


def extract_entities_from_document(
    provider: LLMProvider,
    title: str,
    text: str,
) -> dict[str, Any]:
    """Use LLM to extract entities, experiments, and relationships from a document."""
    from kg_engine.config.settings import settings

    truncated = text[: settings.llm_embedding_truncation_chars]
    messages = [
        {
            "role": "system",
            "content": "You are a materials science knowledge graph extractor. Return only valid JSON.",
        },
        {
            "role": "user",
            "content": _EXTRACT_PROMPT.format(title=title, content=truncated),
        },
    ]
    result = provider.chat_json(messages, temperature=0.1, max_tokens=4096)
    if not result:
        return {"entities": [], "experiments": [], "relationships": []}
    return {
        "entities": result.get("entities", []),
        "experiments": result.get("experiments", []),
        "relationships": result.get("relationships", []),
    }


def structure_upload_with_llm(
    provider: LLMProvider,
    filename: str,
    file_type: str,
    parsed_content: Any,
) -> dict[str, Any]:
    """Use the LLM to route arbitrary uploaded data into graph ingestion payloads."""
    from kg_engine.config.settings import settings

    content = json.dumps(parsed_content, ensure_ascii=False, indent=2, default=str)
    truncated = content[: settings.llm_embedding_truncation_chars]
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


def llm_enhance_reference_entities(
    provider: LLMProvider,
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Use LLM to enrich reference entities with better aliases and properties."""
    if not entities:
        return entities
    names = [e.get("name", "") for e in entities[:50]]
    messages = [
        {
            "role": "system",
            "content": "You are a materials science ontology enricher. Return only valid JSON.",
        },
        {
            "role": "user",
            "content": (
                "For each entity below, suggest additional aliases (alternative names, abbreviations, "
                "common references) and any known properties. Return JSON: "
                '{"enriched": [{"name": "...", "aliases": [...], "properties": {...}}]}'
                f"\n\nEntities: {names}"
            ),
        },
    ]
    result = provider.chat_json(messages, temperature=0.2, max_tokens=2048)
    enriched_list = result.get("enriched", [])
    alias_map = {item.get("name", ""): item for item in enriched_list}
    for entity in entities:
        name = entity.get("name", "")
        if name in alias_map:
            extra = alias_map[name]
            existing_aliases = set(entity.get("aliases", []))
            existing_aliases.update(extra.get("aliases", []))
            entity["aliases"] = list(existing_aliases)
            extra_props = extra.get("properties", {})
            if extra_props:
                entity.setdefault("properties", {}).update(extra_props)
    return entities


def llm_generate_answer(
    provider: LLMProvider,
    question: str,
    graph_context: dict[str, Any],
    conversation_history: list[dict[str, str]] | None = None,
) -> str:
    """Use LLM to generate a natural language answer from graph query results.

    The answer must be grounded exclusively in the provided graph_context.
    Raw source text fragments are included so the LLM can cite specific evidence.
    Supports multi-turn conversation via conversation_history.
    """
    messages = build_answer_messages(question, graph_context, conversation_history)
    answer = provider.chat(messages, temperature=0.3, max_tokens=1024)
    return answer or ""
