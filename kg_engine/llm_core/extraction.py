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
    context_parts: list[str] = []

    if graph_context.get("matched_entities"):
        names = [
            e.get("canonical_name", "") for e in graph_context["matched_entities"][:10]
        ]
        context_parts.append(f"Matched entities: {', '.join(names)}")

    if graph_context.get("experiments"):
        exps = graph_context["experiments"][:5]
        for exp in exps:
            context_parts.append(
                f"Experiment: {exp.get('canonical_name', exp.get('id', ''))}"
            )

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

    if graph_context.get("evidence"):
        evidence_items = graph_context["evidence"][:8]
        for ev in evidence_items:
            source_id = ev.get("source_id", "")
            source_kind = ev.get("source_kind", "")
            fragment = (
                ev.get("span", {}).get("fragment", "")
                if isinstance(ev.get("span"), dict)
                else ""
            )
            confidence = ev.get("confidence", "")
            context_parts.append(
                f"Evidence [{source_kind}] from '{source_id}' "
                f"(confidence={confidence}): {fragment[:300]}"
            )

    if graph_context.get("search_hits"):
        hits = graph_context["search_hits"][:5]
        for h in hits:
            source_entity_id = h.get("source_entity_id", "")
            content = h.get("content", "")
            context_parts.append(
                f"Source text from '{source_entity_id}': {content[:400]}"
            )

    if graph_context.get("relations"):
        rels = graph_context["relations"][:8]
        for rel in rels:
            rel_type = rel.get("relation_type", "")
            src = rel.get("source_entity_id", "")
            tgt = rel.get("target_entity_id", "")
            context_parts.append(f"Relation: {src} --[{rel_type}]--> {tgt}")

    context_str = (
        "\n".join(context_parts)
        if context_parts
        else "No data found in knowledge graph."
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

    user_content = f"Knowledge graph data:\n{context_str}\n\nQuestion: {question}"

    messages: list[dict[str, str]] = []
    if conversation_history:
        for hist_msg in conversation_history[-10:]:
            messages.append({"role": hist_msg["role"], "content": hist_msg["content"]})

    messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    try:
        from kg_engine.llm_core.token_budget import (
            count_messages_tokens,
            fit_context_to_budget,
        )
        from kg_engine.config.settings import settings

        total_tokens = count_messages_tokens(messages)
        context_window = settings.llm_context_window
        safety_margin = settings.llm_safety_margin_tokens

        if total_tokens > context_window - safety_margin:
            truncated_parts = fit_context_to_budget(
                graph_context,
                budget=context_window,
                system_prompt_tokens=count_messages_tokens([messages[0]]),
                safety_margin=safety_margin + count_messages_tokens([messages[-1]]),
            )
            import json

            new_context_parts = []
            for key in [
                "matched_entities",
                "experiments",
                "observations",
                "decision_history",
                "data_gaps",
                "evidence",
                "search_hits",
                "relations",
            ]:
                val = truncated_parts.get(key)
                if val:
                    new_context_parts.append(
                        f"{key}: {json.dumps(val, ensure_ascii=False, default=str)[:500]}"
                    )
            user_content = f"Knowledge graph data:\n{'  '.join(new_context_parts)}\n\nQuestion: {question}"
            messages[-1] = {"role": "user", "content": user_content}
    except Exception:
        logger.debug("Token budget management failed, using default truncation")

    answer = provider.chat(messages, temperature=0.3, max_tokens=1024)
    return answer or ""
