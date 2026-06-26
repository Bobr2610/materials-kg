"""Support Resolution Plan tool (SRP).

Generates a step-by-step resolution plan for human support engineers
based on the conversation context and final answer.
"""

from __future__ import annotations

import logging

from langchain.tools import ToolRuntime, tool

from kg_engine.llm.schemas import ResolutionOutcome, ResolutionPlanResult
from kg_engine.utils.context_tracker import AgentContext

logger = logging.getLogger(__name__)


def _render_plan_markdown(plan: dict) -> str:
    """Render resolution plan as markdown string. Skips headings for empty fields."""
    from kg_engine.api.i18n import get_text

    parts = [f"# {get_text('srp_section_title')}"]

    issue_summary = (plan.get("issue_summary") or "").strip()
    if issue_summary:
        parts.append(f"## {get_text('srp_issue_summary')}\n{issue_summary}")

    steps = plan.get("steps_completed") or []
    if steps:
        steps_text = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(steps))
        parts.append(f"## {get_text('srp_steps_completed')}\n{steps_text}")

    next_steps = plan.get("next_steps") or []
    if next_steps:
        next_steps_text = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(next_steps))
        parts.append(f"## {get_text('srp_next_steps')}\n{next_steps_text}")

    outcome = plan.get("outcome")
    if outcome is not None:
        outcome_str = str(outcome)
        if "." in outcome_str:
            outcome_str = outcome_str.split(".")[-1].lower()
        outcome_key = f"srp_outcome_{outcome_str}"
        outcome_text = get_text(outcome_key)
        parts.append(f"## {get_text('srp_result')}\n{outcome_text}")

    return "\n\n".join(parts)


@tool(
    "generate_resolution_plan",
    args_schema=ResolutionPlanResult,
    description=ResolutionPlanResult.__doc__,
)
async def generate_resolution_plan(
    engineer_intervention_needed: bool = False,
    issue_summary: str = "",
    steps_completed: list[str] = None,
    next_steps: list[str] = None,
    outcome: ResolutionOutcome | None = None,
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> dict:
    plan = {
        "engineer_intervention_needed": engineer_intervention_needed,
        "issue_summary": issue_summary,
        "steps_completed": steps_completed or [],
        "next_steps": next_steps or [],
        "outcome": outcome,
    }

    if runtime and hasattr(runtime, "context") and runtime.context is not None:
        try:
            runtime.context.resolution_plan = plan
        except Exception as exc:
            logger.warning("Failed to store resolution_plan into AgentContext: %s", exc)

    return {
        "json": plan,
        "markdown": _render_plan_markdown(plan),
    }
