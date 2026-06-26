"""User request analysis tool (schema-guided request analysis).

This is a lightweight LangChain tool whose *arguments* are the plan itself.
We force the model to call this tool first, so the plan is emitted as a tool call
(structured args), and then stored into `AgentContext` for UI/batch use.

The tool returns a formatted markdown directive for the LLM context, not raw JSON.
"""

from __future__ import annotations

import logging

from langchain.tools import ToolRuntime, tool

from kg_engine.llm.schemas import SGRAction, SGRCategory, SGRPlanResult
from kg_engine.utils.context_tracker import AgentContext

logger = logging.getLogger(__name__)


def _get_answer_language(plan: dict) -> str:
    """Normalize answer language code from plan.

    Returns:
        "en" or "ru" when the model explicitly sets a supported language.
        "" (empty string) when language is missing or unrecognized, so that
        the top-level system prompt controls answer language.
    """
    raw = (plan.get("answer_language") or "").strip().lower()
    if not raw:
        return ""

    # Accept both codes and full names, be forgiving about minor variants
    if raw in {"en", "eng", "english"}:
        return "en"
    if raw in {"ru", "rus", "russian", "русский", "русском"}:
        return "ru"

    # Unknown value: let the main system prompt decide language
    return ""


def _render_proceed_template(plan: dict, guardian_result: dict | None = None) -> str:
    """Render proceed template with optional content advisory."""
    lang = _get_answer_language(plan)
    queries = "\n   - ".join(plan.get("knowledge_base_search_queries", []))

    if lang == "en":
        advisory = ""
        if guardian_result and guardian_result.get("safety_level") == "Controversial":
            categories = ", ".join(guardian_result.get("categories", []))
            advisory = f"""
⚠️ **Content Advisory**: This request was flagged as potentially controversial ({categories}).
Respond with factual, neutral tone. Avoid speculation or subjective opinions."""

        return f"""**Request Analysis**
Answer language: English. Answer to the user in English.
Intent: {plan["user_intent"]}
Category: {plan["category"]}
Confidence: {plan["intent_confidence"] * 100:.0f}%
{advisory}

**Required next steps**
1. Call retrieve_context tool with these queries:
   - {queries}
2. Review results and provide answer based on retrieved documentation."""

    advisory = ""
    if guardian_result and guardian_result.get("safety_level") == "Controversial":
        categories = ", ".join(guardian_result.get("categories", []))
        advisory = (
            f"\n⚠️ **Предупреждение по содержанию**: запрос помечен как потенциально спорный "
            f"({categories}). Отвечай нейтрально, опираясь только на факты из документации."
        )

    # For non-English / non-Russian or empty language, we still use the Russian
    # planning template (internal to the model) but do NOT restate an explicit
    # "answer language" line. This lets the global system prompt control user-facing
    # language when the model didn't confidently choose one here.
    heading = "**Анализ запроса**"
    lang_line = ""
    if lang == "ru":
        lang_line = "Язык ответа: русский. Отвечай пользователю на русском языке.\n"

    return (
        f"""{heading}
{lang_line}Намерение: {plan["user_intent"]}
Категория: {plan["category"]}
Уверенность: {plan["intent_confidence"] * 100:.0f}%"""
        f"{advisory}\n\n"
        "**Следующие шаги**\n"
        "1. Вызови инструмент retrieve_context с такими запросами:\n"
        f"   - {queries}\n"
        "2. Изучи результаты и ответь на вопрос на основе найденной документации."
    )


def _render_clarify_template(plan: dict) -> str:
    """Render clarification needed template."""
    lang = _get_answer_language(plan)
    questions = "\n   - ".join(plan.get("clarification_questions_to_ask", []))

    if lang == "en":
        return f"""**Request Analysis**
Answer language: English. Answer to the user in English.
Intent: {plan["user_intent"]}
Category: {plan["category"]}
Confidence: {plan["intent_confidence"] * 100:.0f}% (low)

**Required next steps**
1. Ask the user these clarification questions:
   - {questions}
   - [+ add any additional questions if needed]
2. Wait for user response before proceeding."""

    # For empty/unknown language, use Russian planning template but skip explicit lang line.
    heading = "**Анализ запроса**"
    lang_line = ""
    if lang == "ru":
        lang_line = "Язык ответа: русский. Отвечай пользователю на русском языке.\n"

    return (
        f"""{heading}
{lang_line}Намерение: {plan["user_intent"]}
Категория: {plan["category"]}
Уверенность: {plan["intent_confidence"] * 100:.0f}% (низкая)

**Следующие шаги**
1. Задай пользователю следующие уточняющие вопросы:
   - {questions}
   - [+ добавь дополнительные вопросы при необходимости]
2. Дождись ответа пользователя перед тем, как продолжить."""
    )


def _render_decline_template(plan: dict) -> str:
    """Render decline template (spam/off-topic)."""
    lang = _get_answer_language(plan)

    if lang == "en":
        refusal = (
            "Sorry, I cannot help with this request. It is not related to the Comindware Platform."
        )
        return f"""**Request Analysis**
Answer language: English. Answer to the user in English.
Assessment: Request is not related to the Comindware Platform.
Reason: {plan["spam_reason"]}
Spam Score: {plan["spam_score"]}

**Required next steps**
Do not process this request. Use this refusal message:

"{refusal}"."""

    refusal = "Извините, я не могу помочь с этим запросом. Он не относится к Comindware Platform."

    # For empty/unknown language, use Russian planning template but skip explicit lang line.
    heading = "**Анализ запроса**"
    lang_line = ""
    if lang == "ru":
        lang_line = "Язык ответа: русский. Отвечай пользователю на русском языке.\n"

    return (
        f"""{heading}
{lang_line}Оценка: запрос не относится к Comindware Platform.
Причина: {plan["spam_reason"]}
Оценка спама: {plan["spam_score"]}

**Следующие шаги**
Не обрабатывай этот запрос. Используй такое сообщение отказа:

"{refusal}"."""
    )


def render_sgr_template(
    action: str,
    plan: dict,
    guardian_result: dict | None = None,
) -> str:
    """Render SGR plan as directive tool result.

    Args:
        action: Action from SGR analysis (proceed, ask_clarification, decline)
        plan: SGR analysis plan dict
        guardian_result: Optional guardian classification for advisory note

    Returns:
        Formatted markdown string for LLM context
    """
    if action == SGRAction.PROCEED.value or action == SGRAction.PROCEED:
        return _render_proceed_template(plan, guardian_result)
    elif action == SGRAction.ASK_CLARIFICATION.value or action == SGRAction.ASK_CLARIFICATION:
        return _render_clarify_template(plan)
    elif action == SGRAction.DECLINE.value or action == SGRAction.DECLINE:
        return _render_decline_template(plan)
    return ""


@tool("analyse_user_request", args_schema=SGRPlanResult, description=SGRPlanResult.__doc__)
async def analyse_user_request(
    user_intent: str = "",
    topic: str = "",
    category: SGRCategory = SGRCategory.OTHER if hasattr(SGRCategory, "OTHER") else list(SGRCategory)[0],
    intent_confidence: float = 0.0,
    clarification_questions_to_ask: list[str] = None,
    spam_score: float = 0.0,
    spam_reason: str = "",
    answer_language: str = "",
    knowledge_base_search_queries: list[str] = None,
    action_plan: list[str] = None,
    action: SGRAction = SGRAction.PROCEED,
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> dict:
    # LangChain passes original args, not Pydantic-validated ones; ensure lists are never None
    plan = {
        "user_intent": user_intent,
        "topic": topic,
        "category": category.value if hasattr(category, "value") else str(category),
        "intent_confidence": intent_confidence,
        "clarification_questions_to_ask": clarification_questions_to_ask or [],
        "spam_score": spam_score,
        "spam_reason": spam_reason,
        "answer_language": answer_language,
        "knowledge_base_search_queries": knowledge_base_search_queries or [],
        "action_plan": action_plan or [],
        "action": action.value if hasattr(action, "value") else str(action),
    }

    if runtime and hasattr(runtime, "context") and runtime.context is not None:
        try:
            runtime.context.sgr_plan = plan
        except Exception as exc:
            logger.warning("Failed to store sgr_plan into AgentContext: %s", exc)

    return {
        "json": plan,
        "markdown": render_sgr_template(action.value, plan),
    }
