"""Pydantic schemas for structured agent outputs.

We keep these schemas lean and avoid duplicating existing runtime structures:
- Articles are represented as dicts serialized from existing `Article` objects.
- Query trace is represented as dicts captured during actual tool execution.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

try:
    from kg_engine.cmw_platform.category_enum import (
        get_category_choices_with_descriptions,
        load_category_enum,
    )
except ImportError:
    def get_category_choices_with_descriptions() -> list[tuple[str, str]]:  # type: ignore[unused-ignore]
        return []
    def load_category_enum() -> type:  # type: ignore[unused-ignore]
        from enum import Enum
        class _EmptyCategory(str, Enum):
            uncategorized = "uncategorized"
        return _EmptyCategory


class SGRAction(str, Enum):
    """Routing actions for request handling."""

    PROCEED = "proceed"
    ASK_CLARIFICATION = "ask_clarification"
    DECLINE = "decline"


def _get_category_enum() -> type[Enum]:
    """Get the dynamic category enum from YAML config."""
    return load_category_enum()


# Dynamic Enum for the schema
SGRCategory = _get_category_enum()
_category_choices_with_desc = get_category_choices_with_descriptions()


class SGRPlanResult(BaseModel):
    """Analyze the user request and produce the resolution plan for Comindware Platform support.

    Returns guidance for your further steps.

    Reason step by step, like a human would think, and fill the arguments with meaningful data:

    1. Understand what user wants
    2. Identify topic and category
    3. Assess confidence in understanding
    4. Check if request is relevant/safe
    5. Plan search strategy
    6. Decide action
    7. Prepare clarification if needed

    Edge cases:
    - Simple greetings (привет, спасибо): Set queries=[], action=proceed, spam_score=0
    - Time/date questions (сколько времени?): Set queries=[], action=proceed
    - General knowledge (2+2=?): Set queries=[], action=proceed
    """

    user_intent: str = Field(
        default="",
        description=(
            "Determine: What does the user actually want to achieve? "
            "Think beyond keywords: What is their underlying goal? "
            "What business problem are they trying to solve? "
            "Write in the user's question original language, 10-100 words."
        ),
    )

    topic: str = Field(
        default="",
        description=(
            "What is this request about? "
            "Example: 'Настройка SSO', 'Создание процесса', 'Интеграция с API'. "
            "Write in Russian, 2-5 words."
        ),
    )

    category: SGRCategory = Field(
        default=SGRCategory.OTHER if hasattr(SGRCategory, "OTHER") else list(SGRCategory)[0],
        description=(
            f"Type of request. Choose from available categories:\n{_category_choices_with_desc}"
        ),
    )

    @field_validator("category", mode="before")
    @classmethod
    def _convert_category(cls, v: Any) -> SGRCategory:
        """Accept any string value - will be matched against valid codes."""
        if isinstance(v, str):
            # Try to match by value (code)
            v_clean = v.lower().strip()
            for member in SGRCategory:
                if member.value.lower() == v_clean:
                    return member
        # Fallback to OTHER
        return SGRCategory.OTHER if hasattr(SGRCategory, "OTHER") else list(SGRCategory)[0]


    intent_confidence: float | None = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Decide: How confident are you in understanding what the user wants? "
            "Think: Is the request clear? Do you understand the context? "
            "0.0-0.4: Very unclear, major uncertainties; "
            "0.5-0.7: Somewhat clear but some gaps; "
            "0.8-1.0: Clear and well-understood."
        ),
    )

    clarification_questions_to_ask: list[str] = Field(
        default_factory=list,
        max_length=5,
        description=(
            "If intent_confidence < 0.7, "
            "determine specific questions that would help you understand user request better. "
            "Write in the user's language, be polite and specific. "
            "These questions will be shown to the user to get clarification. "
            "Example: ['вас интересует инструкция для Linux или Windows?', 'какой именно интерфейс вас интересует?', 'какая версия платформы у вас установлена?']"
            "Empty list if intent_confidence >= 0.7."
        ),
    )

    @field_validator("clarification_questions_to_ask", mode="before")
    @classmethod
    def _convert_clarification_questions(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v else []
        if isinstance(v, list):
            return [str(item) for item in v]
        return []

    spam_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Determine: Is this request appropriate for Comindware Platform support? "
            "0.0-0.2: Clearly relevant; "
            "0.3-0.5: Ambiguous or partially related; "
            "0.6-0.8: Likely irrelevant; "
            "0.9-1.0: Obviously spam or malicious."
        ),
    )

    spam_reason: str = Field(
        default="",
        description=(
            "Provide brief explanation of spam_score in 10-20 words. "
            "Write in Russian. "
            "Set 'Not spam' if spam_score < 0.3."
        ),
    )

    answer_language: str = Field(
        default="",
        description=(
            "Determine the language of the original user's request. "
            "Use plain names: 'Russian' or 'English'. Short codes 'ru'/'en' are also accepted. "
        ),
    )

    knowledge_base_search_queries: list[str] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "Devise specific terms to search in the articles the knowledge. "
            "Include: feature names, technical terms, error messages, relevant keywords. "
            "Example: ['сведения о выпуске', 'развёртывание ПО', 'справочник по API']"
            "Write in Russian, avoid duplicates. "
            "Leave EMPTY if no search needed (e.g., simple greetings, time/date questions, "
            "or direct answers not requiring documentation lookup)."
        ),
    )

    @field_validator("knowledge_base_search_queries", mode="before")
    @classmethod
    def _convert_queries(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v else []
        if isinstance(v, list):
            return [str(item) for item in v]
        return []

    action_plan: list[str] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "Plan. How will you answer this request? "
            "Example steps: ['понять запрос пользователя', 'найти статьи', 'оценить релевантность статей', 'составить ответ', 'запросить уточнение', 'составить план для инженера поддержки']. "
            "Write as actionable instructions to yourself."
        ),
    )

    @field_validator("action_plan", mode="before")
    @classmethod
    def _convert_action_plan(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v else []
        if isinstance(v, list):
            return [str(item) for item in v]
        return []

    action: SGRAction = Field(
        default=SGRAction.PROCEED,
        description=(
            "Based on all previous reasoning, determine what action to take? "
            "'proceed': request is relevant and clear - assist normally; "
            "'ask_clarification': request needs clarification from user; "
            "'decline': request is off-topic or inappropriate - do not assist; "
            "Guideline: spam_score >= 0.7 suggests decline; "
            "intent_confidence < 0.6 suggests ask_clarification. "
        ),
    )


class ResolutionOutcome(str, Enum):
    """Resolution status for support engineer plan."""

    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    ESCALATION_REQUIRED = "escalation_required"
    USER_FOLLOWUP_NEEDED = "user_followup_needed"
    NOT_APPLICABLE = "not_applicable"


class ResolutionPlanResult(BaseModel):
    """Generate a support engineer resolution plan for Comindware Platform.

    Analyze the original user's request/question, the whole conversation,
    and YOUR final answer.

    Reason step by step and fill the arguments with meaningful data:

    1. Critique your answer: Did you solve the user's original specific problem?
    2. Describe the user's original issue clearly
    3. List the steps you took to resolve it
    4. Define next steps for the support engineer (if any)
    5. Determine the resolution outcome

    Always fill these fields (for structured trace):
    - issue_summary: original user's request analysis, 2-3 sentences (20-150 words) in Russian
    - steps_completed: what you did to resolve the user's issue, 2-5 items in Russian
    - next_steps: what the engineer should do, 1-3 items in Russian
    - outcome: resolved / partially_resolved / escalation_required / user_followup_needed / not_applicable
    - engineer_intervention_needed: set TRUE if human help needed.
        Set FALSE if answer fully resolves request (version queries, simple how-tos with complete KB answers, factual lookups).
    """

    engineer_intervention_needed: bool = Field(
        default=False,
        description=(
            "CRITIQUE your answer first: Did you solve the user's specific problem? "
            "Set to TRUE for: "
            "- support engineer intervention or escalation needed for this issue, "
            "- errors, bugs, configuration issues, incomplete solutions, "
            "- troubleshooting required, software fails, "
            "- any issue requiring human investigation/action. "
            "Set to FALSE for: "
            "- version queries that you resolved, "
            "- simple how-tos with complete KB answers, "
            "- factual lookups that are fully resolved, "
            "- self-service queries. "
        ),
    )

    issue_summary: str = Field(
        default="",
        description=(
            "Describe the user's original issue/request/problem/task in 2-3 sentences (20-150 words). "
            "Russian. "
            "Always fill for structured trace."
        ),
    )

    steps_completed: list[str] = Field(
        default_factory=list,
        description=(
            "List the steps you took to resolve the issue (2-5 items). "
            "Russian. "
            "Always fill for structured trace."
        ),
    )

    @field_validator("steps_completed", mode="before")
    @classmethod
    def _convert_steps_completed(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v else []
        if isinstance(v, list):
            return [str(item) for item in v]
        return []

    next_steps: list[str] = Field(
        default_factory=list,
        description=(
            "List recommended actions for support engineer (1-3 items). "
            "Russian. "
            "Always fill for structured trace."
        ),
    )

    @field_validator("next_steps", mode="before")
    @classmethod
    def _convert_next_steps(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v else []
        if isinstance(v, list):
            return [str(item) for item in v]
        return []

    outcome: ResolutionOutcome | None = Field(
        default=None,
        description=(
            "Give resolution status based on the answer provided. "
            "Use English enum value: "
            "'resolved': Fully resolved; "
            "'partially_resolved': Additional actions needed; "
            "'escalation_required': Requires escalation; "
            "'user_followup_needed': User follow-up required; "
            "'not_applicable': Engineer plan not needed (engineer_intervention_needed=False)."
        ),
    )


class UsageTotals(BaseModel):
    """Aggregated usage metrics (tokens and cost) for a scope (turn or conversation)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    cost: float = 0.0
    upstream_cost: float = 0.0


class UsageBlock(BaseModel):
    """Usage for the current turn and conversation."""

    turn: UsageTotals | None = None
    conversation: UsageTotals | None = None


class StructuredAgentResult(BaseModel):
    """Structured output from `ask_comindware_structured()`.

    Notes:
    - `per_query_results` is a list of dicts captured from actual tool calls:
      {query, confidence: {...}, articles: [...]}
    - `final_articles` is a list of dicts serialized from existing Article objects
      (same shape as retrieve_context tool output's article items).
    - `resolution_plan` contains SRP (Support Resolution Plan) fields:
      engineer_intervention_needed, issue_summary, steps_completed, next_steps, outcome
    - `executed_queries` contains the actual queries sent to the knowledge base
    - `answer_confidence` is calculated from average rerank scores of retrieved articles
    """

    plan: SGRPlanResult
    resolution_plan: dict[str, Any] | None = Field(default=None)
    executed_queries: list[str] = Field(default_factory=list)
    answer_confidence: float | None = Field(default=None)
    per_query_results: list[dict[str, Any]] = Field(default_factory=list)
    final_articles: list[dict[str, Any]] = Field(default_factory=list)
    answer_text: str = ""
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    usage: UsageBlock | None = Field(
        default=None,
        description="Usage accounting (tokens, cost) for this turn and conversation.",
    )
