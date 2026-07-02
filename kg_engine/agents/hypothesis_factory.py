"""Deep Agents orchestration for the Materials Hypothesis Factory."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from kg_engine.agents.hypothesis_tools import create_hypothesis_tools
from kg_engine.config.settings import Settings
from kg_engine.config.settings import settings as default_settings
from kg_engine.domain.models import HypothesisGenerationResult
from kg_engine.domain.models import HypothesisInput
from kg_engine.llm_core.provider import create_langchain_chat_model_from_settings
from kg_engine.services.hypothesis_adjustments import EXPERT_ADJUSTMENT_SCHEMA
from kg_engine.services.hypothesis_adjustments import apply_expert_adjustments
from kg_engine.services.materials_kg import MaterialsKGService

logger = logging.getLogger(__name__)


class DeepAgentsConfigurationError(RuntimeError):
    """Deep Agents cannot run because settings or dependencies are incomplete."""


class DeepAgentsResultError(RuntimeError):
    """Deep Agents returned a payload that does not match the public contract."""


AgentFactory = Callable[..., Any]
ModelFactory = Callable[[Settings], tuple[Any, str]]


def create_langchain_chat_model(
    runtime_settings: Settings,
) -> tuple[Any, str]:
    """Create a LangChain-compatible chat model from shared LLM settings."""
    try:
        return create_langchain_chat_model_from_settings(runtime_settings)
    except RuntimeError as exc:
        raise DeepAgentsConfigurationError(str(exc)) from exc


def _load_create_deep_agent() -> AgentFactory:
    try:
        from deepagents import create_deep_agent
    except ImportError as exc:
        msg = (
            "deepagents is required for MATERIALS_HYPOTHESIS_ENGINE=deepagents. "
            "Install kg_engine/requirements.txt before running the factory."
        )
        raise DeepAgentsConfigurationError(msg) from exc
    return create_deep_agent


def _subagents() -> list[dict[str, Any]]:
    return [
        {
            "name": "evidence_analyst",
            "description": "Finds supporting observations, text evidence, and contradictions.",
            "system_prompt": (
                "You are a materials evidence analyst. Use only provided KG tools. "
                "Return concise findings with evidence ids and uncertainty."
            ),
        },
        {
            "name": "novelty_reviewer",
            "description": "Assesses whether a hypothesis is underexplored in the KG.",
            "system_prompt": (
                "You judge novelty from graph coverage, data gaps, and text hits. "
                "Return a 0..1 novelty recommendation and rationale."
            ),
        },
        {
            "name": "risk_reviewer",
            "description": "Identifies technical risks and falsification criteria.",
            "system_prompt": (
                "You review experiment risk. Return concrete risks, validation checks, "
                "required evidence, and falsification criteria."
            ),
        },
        {
            "name": "ranker",
            "description": "Normalizes score components and checks ranking consistency.",
            "system_prompt": (
                "You validate HypothesisScore values. Preserve the public formula: "
                "0.35*value + 0.25*evidence_strength + 0.20*novelty + 0.20*(1-risk)."
            ),
        },
    ]


def _system_prompt(request: HypothesisInput, source_overview: dict[str, Any]) -> str:
    source_count = len(source_overview.get("source_files") or [])
    by_kind = source_overview.get("by_kind") or {}
    request_focus = {
        "target_kpi": request.target_kpi,
        "question": request.question,
        "material": request.material,
        "mode": request.mode,
        "property_name": request.property_name,
        "source_ids": request.source_ids,
        "max_hypotheses": request.max_hypotheses,
    }
    return f"""
You are the Materials Hypothesis Factory coordinator.

Goal:
Generate interpretable, testable R&D hypotheses for materials science and
technology projects from the graph knowledge base.

Current request focus:
{json.dumps(request_focus, ensure_ascii=False)}

Loaded graph profile:
- source_count: {source_count}
- entity_counts_by_kind: {json.dumps(by_kind, ensure_ascii=False)}
- observations: {source_overview.get("total_observations", 0)}
- relations: {source_overview.get("total_relations", 0)}
- evidence: {source_overview.get("total_evidence", 0)}

Rules:
- Use the KG tools before producing the final answer.
- Treat kg_generate_baseline_hypotheses as the deterministic baseline, not as a
  final answer to copy blindly.
- Choose tools based on the request: material/mode/property slices, property
  ranges, graph traversal, decision history, text evidence, and gaps are all
  available.
- Use subagents for evidence, novelty, risk, and ranking review on non-trivial
  tasks.
- Do not invent entities, observations, evidence ids, source ids, or scores.
- Keep all hypotheses grounded in returned observations, evidence, text units,
  or data gaps.
- Every hypothesis must include at least one concrete graph support id in
  supporting_evidence_ids, supporting_observation_ids, supporting_text_unit_ids,
  or data_gap_ids. Unsupported hypotheses will be discarded.
- Return only strict JSON matching HypothesisGenerationResult. No markdown,
  no prose wrapper, no fenced code block.
- Set generation_engine to "deepagents".
- Include agent_trace entries that explain planning, tool use, subagent reviews,
  and final validation.
""".strip()


def _user_prompt(request: HypothesisInput) -> str:
    return json.dumps(
        {
            "task": "generate_materials_research_hypotheses",
            "request": request.model_dump(mode="json"),
            "required_output_schema": "HypothesisGenerationResult",
            "expert_adjustment_schema": EXPERT_ADJUSTMENT_SCHEMA,
        },
        ensure_ascii=False,
    )


def _message_content(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return str(content)


def _final_content(agent_result: Any) -> str:
    if isinstance(agent_result, HypothesisGenerationResult):
        return agent_result.model_dump_json()
    if isinstance(agent_result, dict):
        if isinstance(agent_result.get("output"), str):
            return agent_result["output"]
        if isinstance(agent_result.get("structured_response"), dict):
            return json.dumps(agent_result["structured_response"], ensure_ascii=False)
        messages = agent_result.get("messages")
        if isinstance(messages, list) and messages:
            return _message_content(messages[-1])
    return _message_content(agent_result)


def _parse_agent_result(agent_result: Any) -> HypothesisGenerationResult:
    raw = _final_content(agent_result).strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        msg = "Deep Agents returned non-JSON output; refusing silent fallback."
        raise DeepAgentsResultError(msg) from exc
    try:
        return HypothesisGenerationResult.model_validate(payload)
    except Exception as exc:
        msg = "Deep Agents output does not match HypothesisGenerationResult."
        raise DeepAgentsResultError(msg) from exc


def _filter_ungrounded_hypotheses(
    result: HypothesisGenerationResult,
) -> HypothesisGenerationResult:
    evidence_ids = {item.id for item in result.evidence}
    observation_ids = {item.id for item in result.observations}
    text_unit_ids = {item.id for item in result.search_hits}
    data_gap_ids = {item.id for item in result.data_gaps}
    entity_ids = {item.id for item in result.matched_entities}

    # Collect IDs from agent_trace tool_call results
    trace_ids: set[str] = set()
    for entry in result.agent_trace:
        if not isinstance(entry, dict):
            continue
        for key in (
            "entity_ids",
            "observation_ids",
            "evidence_ids",
            "matched_ids",
            "text_unit_ids",
        ):
            val = entry.get(key)
            if isinstance(val, list):
                trace_ids.update(str(v) for v in val if v)

    all_known_ids = (
        evidence_ids | observation_ids | text_unit_ids | data_gap_ids
        | entity_ids | trace_ids
    )

    kept = []
    rejected: list[str] = []
    for hypothesis in result.hypotheses:
        has_graph_support = any(
            [
                set(hypothesis.supporting_evidence_ids) & evidence_ids,
                set(hypothesis.supporting_observation_ids) & observation_ids,
                set(hypothesis.supporting_text_unit_ids) & text_unit_ids,
                set(hypothesis.data_gap_ids) & data_gap_ids,
                set(hypothesis.supporting_entity_ids) & entity_ids,
            ]
        )
        if not has_graph_support:
            all_hypothesis_refs = (
                set(hypothesis.supporting_evidence_ids)
                | set(hypothesis.supporting_observation_ids)
                | set(hypothesis.supporting_text_unit_ids)
                | set(hypothesis.data_gap_ids)
                | set(hypothesis.supporting_entity_ids)
            )
            has_graph_support = bool(all_hypothesis_refs & all_known_ids)
        if has_graph_support:
            kept.append(hypothesis)
            continue
        rejected.append(hypothesis.id)
    if rejected:
        result.warnings.append(
            "Discarded ungrounded hypotheses without concrete graph support: "
            + ", ".join(rejected)
        )
        result.agent_trace.append(
            {
                "event": "ungrounded_hypotheses_discarded",
                "hypothesis_ids": rejected,
            }
        )
    result.hypotheses = kept
    return result


def generate_hypotheses_with_deep_agent(
    service: MaterialsKGService,
    request: HypothesisInput,
    *,
    runtime_settings: Settings | None = None,
    agent_factory: AgentFactory | None = None,
    model_factory: ModelFactory | None = None,
) -> HypothesisGenerationResult:
    """Run the Deep Agents Hypothesis Factory and validate the public result."""
    settings_obj = runtime_settings or default_settings
    if not settings_obj.materials_deepagents_enabled:
        msg = "Deep Agents are disabled by MATERIALS_DEEPAGENTS_ENABLED=false."
        raise DeepAgentsConfigurationError(msg)

    max_tool_steps = max(1, settings_obj.materials_deepagents_max_tool_steps)
    recursion_limit = max(30, max_tool_steps * 6)
    trace: list[dict[str, Any]] = [
        {
            "event": "agent_prepare",
            "engine": "deepagents",
            "target_kpi": request.target_kpi,
            "max_tool_steps": max_tool_steps,
            "recursion_limit": recursion_limit,
        }
    ]
    create_agent = agent_factory or _load_create_deep_agent()
    create_model = model_factory or create_langchain_chat_model
    model, llm_used = create_model(settings_obj)
    source_overview = service.get_source_overview()
    trace.append(
        {
            "event": "graph_profile_loaded",
            "total_entities": source_overview.get("total_entities", 0),
            "total_observations": source_overview.get("total_observations", 0),
            "total_relations": source_overview.get("total_relations", 0),
        }
    )
    subagents = _subagents()
    trace.append(
        {
            "event": "subagents_configured",
            "subagents": [item["name"] for item in subagents],
        }
    )

    agent = create_agent(
        model=model,
        tools=create_hypothesis_tools(
            service,
            trace,
            max_tool_steps=max_tool_steps,
        ),
        subagents=subagents,
        system_prompt=_system_prompt(request, source_overview),
        name="materials-hypothesis-factory",
    )
    trace.append({"event": "agent_invoke", "llm_used": llm_used})
    try:
        agent_result = agent.invoke(
            {"messages": [{"role": "user", "content": _user_prompt(request)}]},
            config={"recursion_limit": recursion_limit},
        )
    except Exception as exc:
        logger.exception("Deep Agents invocation failed")
        msg = (
            "Deep Agents invocation failed "
            f"({exc.__class__.__name__}). Check LLM provider configuration, "
            "quota, and connectivity."
        )
        raise DeepAgentsConfigurationError(msg) from exc
    result = _parse_agent_result(agent_result)
    result.generation_engine = "deepagents"
    result.llm_used = llm_used
    result.expert_adjustment_schema = EXPERT_ADJUSTMENT_SCHEMA
    result.agent_trace = [*trace, *result.agent_trace, {"event": "result_validated"}]
    result = _filter_ungrounded_hypotheses(result)
    apply_expert_adjustments(result.hypotheses, request.expert_adjustments)
    result.hypotheses.sort(key=lambda item: item.score.final_score, reverse=True)
    result.hypotheses = result.hypotheses[: request.max_hypotheses]
    for rank, hypothesis in enumerate(result.hypotheses, start=1):
        hypothesis.rank = rank
    return result
