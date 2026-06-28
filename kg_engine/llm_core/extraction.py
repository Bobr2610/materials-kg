"""LLM-powered entity and relationship extraction from documents."""

from __future__ import annotations

import logging
from typing import Any

from kg_engine.domain.models import CanonicalEntityInput
from kg_engine.domain.models import DocumentInput
from kg_engine.domain.models import EntityKind
from kg_engine.domain.models import ExperimentInput
from kg_engine.domain.models import ObservationInput
from kg_engine.llm_core.provider import LLMProvider

logger = logging.getLogger(__name__)

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


def extract_entities_from_document(
    provider: LLMProvider,
    title: str,
    text: str,
) -> dict[str, Any]:
    """Use LLM to extract entities, experiments, and relationships from a document."""
    truncated = text[:8000]
    messages = [
        {"role": "system", "content": "You are a materials science knowledge graph extractor. Return only valid JSON."},
        {"role": "user", "content": _EXTRACT_PROMPT.format(title=title, content=truncated)},
    ]
    result = provider.chat_json(messages, temperature=0.1, max_tokens=4096)
    if not result:
        return {"entities": [], "experiments": [], "relationships": []}
    return {
        "entities": result.get("entities", []),
        "experiments": result.get("experiments", []),
        "relationships": result.get("relationships", []),
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
        {"role": "system", "content": "You are a materials science ontology enricher. Return only valid JSON."},
        {"role": "user", "content": (
            "For each entity below, suggest additional aliases (alternative names, abbreviations, "
            "common references) and any known properties. Return JSON: "
            '{"enriched": [{"name": "...", "aliases": [...], "properties": {...}}]}'
            f"\n\nEntities: {names}"
        )},
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
) -> str:
    """Use LLM to generate a natural language answer from graph query results."""
    context_parts = []
    if graph_context.get("matched_entities"):
        names = [e.get("canonical_name", "") for e in graph_context["matched_entities"][:10]]
        context_parts.append(f"Matched entities: {', '.join(names)}")
    if graph_context.get("experiments"):
        exps = graph_context["experiments"][:5]
        for exp in exps:
            context_parts.append(f"Experiment: {exp.get('canonical_name', exp.get('id', ''))}")
    if graph_context.get("observations"):
        obs = graph_context["observations"][:10]
        obs_text = "; ".join(
            f"{o.get('property_id', '')}: {o.get('value', 'n/a')} {o.get('unit', '')}"
            for o in obs
        )
        context_parts.append(f"Measurements: {obs_text}")
    if graph_context.get("decision_history"):
        traces = graph_context["decision_history"][:5]
        for t in traces:
            context_parts.append(f"Finding: {t.get('summary', '')}")
    if graph_context.get("data_gaps"):
        gaps = graph_context["data_gaps"][:5]
        gap_text = "; ".join(g.get("reason", "") for g in gaps)
        context_parts.append(f"Data gaps: {gap_text}")
    if graph_context.get("search_hits"):
        hits = graph_context["search_hits"][:3]
        for h in hits:
            context_parts.append(f"Document excerpt: {(h.get('content', ''))[:200]}")

    context_str = "\n".join(context_parts) if context_parts else "No data found in knowledge graph."

    messages = [
        {"role": "system", "content": (
            "You are a materials science research assistant. Answer questions based ONLY on "
            "the knowledge graph data provided. Be specific, cite measurements with values and units, "
            "and note when data is missing. Answer in the same language as the question."
        )},
        {"role": "user", "content": f"Knowledge graph data:\n{context_str}\n\nQuestion: {question}"},
    ]
    answer = provider.chat(messages, temperature=0.3, max_tokens=1024)
    return answer or ""
