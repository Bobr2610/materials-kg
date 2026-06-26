"""Internationalization resources for Gradio UI using gr.I18n.

We define both Russian and English strings for tool-progress bubbles.
Locale is determined from GRADIO_LOCALE environment variable (defaults to "ru").
For details, see the Gradio i18n guide:
https://www.gradio.app/guides/internationalization
"""

from __future__ import annotations

import os

import gradio as gr

i18n = gr.I18n(
    en={
        # Tool progress / thinking bubbles
        "language": "en",
        "search_started_title": "🧠 Searching the knowledge base",
        "search_started_content": "Searching for: {query}",
        "search_completed_title": "✅ Search completed",
        "search_completed_title_with_count": "✅ Search completed",
        "search_completed_content_with_count": "Found articles: {count}.",
        "search_completed_query_prefix": "Query: {query}",
        "sources_header": "**Sources:**",
        "thinking_title": "🧠 Thinking",
        "thinking_content": "Using tool: {tool_name}",
        "generating_answer_title": "✍️ Generating answer",
        "generating_answer_content": "Composing response based on retrieved information...",
        "reasoning_title": "💭 Reasoning",
        "sgr_planning_title": "🧭 Analyzing request",
        "sgr_planning_content": "Building spam score and subqueries...",
        "model_switch_title": "⚡ Switched to {model} (requires more context)",
        "cancelled_title": "⏹️ Cancelled",
        "cancelled_message": "⚠️ Response cancelled by user.",
        "user_intent_prefix": "How I understood your request:",
        # SGR response templates
        "sgr_proceed_response": "Proceeding to search the knowledge base.",
        "sgr_clarify_response": "{clarification_question}",
        "sgr_spam_response": "Sorry, I cannot help with this request.",
        "sgr_spam_refusal": "Sorry, I cannot help with this request. It is not related to the Comindware platform.",
        "sgr_guardian_refusal": "Sorry, I cannot process this request for security reasons.",
        "guard_blocked": "Message blocked for security reasons.",
        # Debug metadata UI
        "spam_badge_label": "Spam",
        "spam_level_na": "N/A",
        "spam_level_low": "Low",
        "spam_level_medium": "Medium",
        "spam_level_high": "High",
        "confidence_badge_label": "Retrieval Confidence",
        "confidence_level_na": "N/A",
        "confidence_level_low": "Low",
        "confidence_level_medium": "Medium",
        "confidence_level_high": "High",
        "queries_badge_label": "Queries",
        "analysis_summary_title": "Analysis Summary",
        "retrieved_articles_title": "Retrieved Articles",
        "guardian_badge_label": "Guardian",
        "sgr_plan_label": "SGR Plan",
        "srp_plan_label": "SRP Plan",
        # SRP badges
        "srp_badge_label": "SRP",
        "srp_intervention_needed_label": "Intervention",
        "srp_outcome_label": "Outcome",
        "srp_priority_label": "Priority",
        "srp_enabled_label": "Enabled",
        "srp_disabled_label": "Disabled",
        "srp_error_label": "Error",
        "user_intent_label": "User Intent",
        "topic_label": "Topic",
        "category_label": "Category",
        "intent_confidence_label": "Intent Confidence",
        "subqueries_label": "Subqueries",
        "action_plan_label": "Action Plan",
        "articles_rank_header": "Rank",
        "articles_title_header": "Title",
        "articles_confidence_header": "Confidence",
        "articles_normalized_header": "Normalized",
        "articles_url_header": "URL",
        # Guard/Safety badge
        "guard_badge_label": "Safety",
        "guard_level_safe": "Safe",
        "guard_level_controversial": "Controversial",
        "guard_level_unsafe": "Unsafe",
        "guard_categories_label": "Categories",
        # Guard/Safety categories (localized)
        "cat_violence": "Violence",
        "cat_sexual": "Sexual Content",
        "cat_pii": "PII",
        "cat_self_harm": "Self-Harm",
        "cat_harassment": "Harassment",
        "cat_hate": "Hate Speech",
        "cat_illegal": "Illegal Acts",
        "cat_unethical": "Unethical Acts",
        "cat_politically": "Politically Sensitive",
        "cat_copyright": "Copyright",
        "cat_jailbreak": "Jailbreak",
        "cat_spam": "Spam",
        "cat_other": "Other",
        # SRP (Support Resolution Plan)
        "srp_planning_title": "📝 Generating support engineer plan",
        "srp_planning_content": "Analyzing conversation and building resolution steps...",
        "srp_section_title": "Support Engineer Resolution Plan",
        "srp_toc_title": "Table of Contents",
        "srp_issue_summary": "Issue Summary",
        "srp_steps_completed": "Steps Completed",
        "srp_next_steps": "Recommended Next Steps",
        "srp_result": "Result",
        "srp_additional_notes": "Additional Notes",
        "srp_outcome_resolved": "Resolved",
        "srp_outcome_partially_resolved": "Partially Resolved",
        "srp_outcome_escalation_required": "Escalation Required",
        "srp_outcome_user_followup_needed": "User Follow-up Needed",
        "srp_outcome_not_applicable": "Not Applicable",
        "srp_outcome_unknown": "Unknown",
        "srp_no_steps": "No steps recorded.",
        "srp_no_next_steps": "No next steps required.",
        "srp_no_additional_notes": "No additional notes.",
        "product_version_label": "Product Version",
    },
    ru={
        "language": "ru",
        "search_started_title": "🧠 Поиск информации в базе знаний",
        "search_started_content": "Ищу: {query}",
        "search_completed_title": "✅ Поиск завершен",
        "search_completed_title_with_count": "✅ Поиск завершен",
        "search_completed_content_with_count": "Найдено статей: {count}.",
        "search_completed_count": "Найдено статей: {count}.",
        "search_completed_query_prefix": "Запрос: {query}",
        "sources_header": "**Источники:**",
        "thinking_title": "🧠 Размышление",
        "thinking_content": "Использую инструмент: {tool_name}",
        "generating_answer_title": "✍️ Генерация ответа",
        "generating_answer_content": "Формирую ответ на основе найденной информации...",
        "reasoning_title": "💭 Размышление",
        "sgr_planning_title": "🧭 Анализ запроса",
        "sgr_planning_content": "Определяю спам-рейтинг и подзапросы...",
        "model_switch_title": "⚡ Переключение на {model} (требуется больше контекста)",
        "cancelled_title": "⏹️ Отменено",
        "cancelled_message": "⚠️ Ответ отменён пользователем.",
        "user_intent_prefix": "Как я понял ваш запрос:",
        # SGR response templates
        "sgr_proceed_response": "Приступаю к поиску информации в базе знаний.",
        "sgr_clarify_response": "{clarification_question}",
        "sgr_spam_response": "Извините, я не могу помочь с этим запросом.",
        "sgr_spam_refusal": "Извините, я не могу помочь с этим запросом. Он не относится к Comindware Platform.",
        "sgr_guardian_refusal": "Извините, я не могу обработать этот запрос в целях безопасности.",
        "guard_blocked": "Сообщение заблокировано по соображениям безопасности.",
        # Debug metadata UI
        "spam_badge_label": "Спам",
        "spam_level_na": "Н/Д",
        "spam_level_low": "Низкий",
        "spam_level_medium": "Средний",
        "spam_level_high": "Высокий",
        "confidence_badge_label": "Уверенность поиска",
        "confidence_level_na": "Н/Д",
        "confidence_level_low": "Низкая",
        "confidence_level_medium": "Средняя",
        "confidence_level_high": "Высокая",
        "queries_badge_label": "Запросы",
        "analysis_summary_title": "Сводка анализа",
        "retrieved_articles_title": "Найденные статьи",
        "guardian_badge_label": "Guardian",
        "sgr_plan_label": "SGR план",
        "srp_plan_label": "SRP план",
        "user_intent_label": "Цель запроса",
        "topic_label": "Тема",
        "category_label": "Категория",
        "intent_confidence_label": "Понимание SGR",
        # SRP badges
        "srp_badge_label": "SRP",
        "srp_intervention_needed_label": "Вмешательство",
        "srp_outcome_label": "Результат",
        "srp_priority_label": "Приоритет",
        "srp_enabled_label": "Включен",
        "srp_disabled_label": "Выключен",
        "srp_error_label": "Ошибка",
        "subqueries_label": "Подзапросы",
        "action_plan_label": "План действий",
        "articles_rank_header": "Ранг",
        "articles_title_header": "Название",
        "articles_confidence_header": "Релевантность",
        "articles_normalized_header": "Нормализованная",
        "articles_url_header": "URL",
        # Guard/Safety badge
        "guard_badge_label": "Безопасность",
        "guard_level_safe": "Безопасно",
        "guard_level_controversial": "Спорно",
        "guard_level_unsafe": "Опасно",
        "guard_categories_label": "Категории",
        # Guard/Safety categories (localized)
        "cat_violence": "Насилие",
        "cat_sexual": "Сексуальный контент",
        "cat_pii": "Персональные данные",
        "cat_self_harm": "Самоповреждение",
        "cat_harassment": "Домогательство",
        "cat_hate": "Разжигание ненависти",
        "cat_illegal": "Незаконные действия",
        "cat_unethical": "Неэтичные действия",
        "cat_politically": "Политически чувствительно",
        "cat_copyright": "Нарушение авторских прав",
        "cat_jailbreak": "Обход безопасности",
        "cat_spam": "Спам",
        "cat_other": "Другое",
        # SRP (Support Resolution Plan)
        "srp_planning_title": "📝 Формирую план для инженера поддержки",
        "srp_planning_content": "Анализирую диалог и создаю план решения...",
        "srp_section_title": "План решения для инженера поддержки",
        "srp_toc_title": "Оглавление",
        "srp_issue_summary": "Краткое описание проблемы",
        "srp_steps_completed": "Выполненные шаги",
        "srp_next_steps": "Рекомендуемые следующие шаги",
        "srp_result": "Результат",
        "srp_additional_notes": "Примечания",
        "srp_outcome_resolved": "Решено",
        "srp_outcome_partially_resolved": "Частично решено",
        "srp_outcome_escalation_required": "Требуется эскалация",
        "srp_outcome_user_followup_needed": "Требуется уточнение у пользователя",
        "srp_outcome_not_applicable": "Не применимо",
        "srp_outcome_unknown": "Неизвестно",
        "srp_no_steps": "Шаги не записаны.",
        "srp_no_next_steps": "Следующие шаги не требуются.",
        "srp_no_additional_notes": "Дополнительных примечаний нет.",
        "product_version_label": "Версия ПО",
    },
)


def _get_current_locale() -> str:
    """Get current locale from environment variable.

    Returns:
        Locale code (e.g., "en", "ru"). Defaults to "ru" if not set or invalid.
    """
    locale = os.getenv("GRADIO_LOCALE", "ru").lower()
    # Validate locale is in available translations
    if locale in i18n.translations:
        return locale
    return "ru"


def i18n_resolve(key: str, locale: str | None = None) -> str:
    """Workaround helper to manually resolve i18n translations.

    This function extracts translations directly from i18n.translations
    dictionary, bypassing the frontend resolution that may not work.
    Use this instead of i18n() for Gradio component properties.

    Args:
        key: Translation key to resolve
        locale: Optional locale override. If None, reads from GRADIO_LOCALE env variable

    Returns:
        Resolved translation string, or the key itself if not found

    Example:
        >>> gr.Textbox(label=i18n_resolve("input_label"))
        >>> gr.Button(i18n_resolve("button_label"))
    """
    target_locale = locale or _get_current_locale()
    translations = i18n.translations.get(target_locale, {})
    return translations.get(key, i18n.translations.get("en", {}).get(key, key))


def get_text(key: str, **kwargs: str | int) -> str:
    """Get i18n translated text as a plain string with format arguments.

    Args:
        key: i18n translation key (e.g., "search_started_title")
        **kwargs: Format arguments for the translation string (e.g., query="test", count=5)

    Returns:
        Resolved translation string (never returns i18n metadata objects).

    Notes:
        Locale is read from GRADIO_LOCALE environment variable (defaults to "ru").
        Accesses translations directly from i18n.translations dictionary to avoid i18n metadata objects.
        For simple translations without format arguments, use i18n_resolve() instead.

    Example:
        >>> get_text("search_started_content", query="test")
        "Searching for: test"
    """
    locale = _get_current_locale()
    text = i18n.translations.get(locale, {}).get(key, key)
    return text.format(**kwargs)
