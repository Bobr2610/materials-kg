# ruff: noqa: E402
"""Gradio UI with Chatbot (reference agent pattern) and REST API endpoint."""

from __future__ import annotations

import dataclasses
import datetime
import json
import logging
import os
import sys
import tempfile
import time
import uuid
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

# Add project root to path if not already installed
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import gradio as gr
from openai import APIError as OpenAIAPIError

from kg_engine.api.i18n import i18n_resolve
from kg_engine.config.settings import get_allowed_fallback_models, settings  # noqa: F401
from kg_engine.llm.fallback import check_context_fallback
from kg_engine.llm.llm_manager import LLMManager
from kg_engine.llm.schemas import StructuredAgentResult
from kg_engine.llm.usage_accounting import accumulate_conversation_usage
from kg_engine.retrieval.embedder import create_embedder
from kg_engine.retrieval.retriever import RAGRetriever
from kg_engine.storage.vector_store import ChromaStore
from kg_engine.tools.get_datetime import _get_current_datetime_dict
from kg_engine.tools.retrieve_context import _retrieve_context_core, set_app_retriever
from kg_engine.utils.context_tracker import (
    AgentContext,
    compute_context_tokens,
    estimate_accumulated_context,
    estimate_accumulated_tokens,
    get_current_context,
)
from kg_engine.utils.conversation_store import salt_session_id
from kg_engine.utils.formatters import format_sources_list, format_with_citations
from kg_engine.utils.logging_manager import setup_logging
from kg_engine.utils.vllm_fallback import (
    check_stream_completion,
    execute_fallback_invoke,
    is_vllm_provider,
    should_use_fallback,
)

setup_logging()

from kg_engine.utils.huggingface_utils import configure_huggingface_env

configure_huggingface_env()

logger = logging.getLogger(__name__)


def _article_to_dict(article) -> dict:
    meta = getattr(article, "metadata", None) or {}
    title = meta.get("title", getattr(article, "kb_id", ""))
    url = (
        meta.get("article_url")
        or meta.get("url")
        or f"https://kb.comindware.ru/article.php?id={getattr(article, 'kb_id', '')}"
    )
    return {
        "kb_id": getattr(article, "kb_id", ""),
        "title": title,
        "url": url,
        "metadata": dict(meta),
    }


def _set_turn_timing_and_model(
    agent_context: AgentContext, turn_start: float, current_model: str
) -> None:
    """Set turn_time_ms and model_used on AgentContext before yielding."""
    agent_context.turn_time_ms = (time.perf_counter() - turn_start) * 1000
    agent_context.model_used = f"{settings.default_llm_provider}: {current_model}"


def _badge_html(*, label: str, value: str, color: str) -> str:
    return (
        f'<span style="background:{color};padding:2px 8px;border-radius:4px;">'
        f"{label}: {value}"
        "</span>"
    )


def format_confidence_badge(query_traces: list[dict]) -> str:
    """Format overall retrieval confidence as colored HTML badge (localized)."""
    from kg_engine.retrieval.confidence import compute_normalized_confidence_from_traces

    label = i18n_resolve("confidence_badge_label")
    avg = compute_normalized_confidence_from_traces(query_traces)

    if avg is None:
        return _badge_html(label=label, value=i18n_resolve("confidence_level_na"), color="gray")

    return format_confidence_badge_from_value(avg)


def format_confidence_badge_from_value(confidence: float | None) -> str:
    """Format confidence from a numeric value as colored HTML badge (localized)."""
    label = i18n_resolve("confidence_badge_label")

    if confidence is None:
        return _badge_html(label=label, value=i18n_resolve("confidence_level_na"), color="gray")

    if confidence > 0.7:
        color, level = "green", i18n_resolve("confidence_level_high")
    elif confidence > 0.4:
        color, level = "orange", i18n_resolve("confidence_level_medium")
    else:
        color, level = "red", i18n_resolve("confidence_level_low")

    return _badge_html(label=label, value=level, color=color)


def format_queries_badge(query_traces: list[dict]) -> str:
    """Format queries count as colored HTML badge (localized)."""
    count = len(query_traces) if query_traces else 0
    return format_queries_badge_from_count(count)


def format_queries_badge_from_count(count: int) -> str:
    """Format queries count as colored HTML badge (localized)."""
    label = i18n_resolve("queries_badge_label")
    # Use blue color for queries badge to distinguish from confidence/spam
    color = "#87CEEB"  # skyblue - valid CSS color
    return _badge_html(label=label, value=str(count), color=color)


def yield_hidden_updates(chunk: list[dict] | None = None) -> tuple:
    """Standard no-op update for all UI components during streaming."""
    chatbot_update = chunk if chunk is not None else []
    return (
        chatbot_update,
        gr.update(),  # No-op
        gr.update(),  # No-op
        gr.update(),  # No-op
        gr.update(),  # No-op
        gr.update(),  # No-op
    )


def yield_badge_updates(
    chatbot: list[dict],
    analysis_data: dict | None = None,
    metadata_dict: dict | None = None,
) -> tuple:
    """Yield badge updates and metadata updates.

    Args:
        chatbot: Chatbot history
        analysis_data: Dict with confidence_badge and queries_badge HTML
        metadata_dict: Metadata dictionary with UI values

    Returns:
        Tuple with 7 component outputs
    """
    # Analysis JSON - combines confidence and queries badges
    if analysis_data:
        analysis_update = gr.update(value=analysis_data)
    else:
        analysis_update = gr.update(value={})

    # Extract metadata values
    if metadata_dict:
        guard_info_val = metadata_dict.get("guardian_info", {})
        sgr_plan_val = metadata_dict.get("sgr_plan", {})
        srp_plan_val = metadata_dict.get("srp_plan", {})
        articles_val = metadata_dict.get("articles_df_data", [])
    else:
        guard_info_val = {}
        sgr_plan_val = {}
        srp_plan_val = {}
        articles_val = []

    # Metadata updates - just value, no visibility toggles
    guardian_json_update = gr.update(value=guard_info_val)
    sgr_plan_json_update = gr.update(value=sgr_plan_val)
    srp_plan_json_update = gr.update(value=srp_plan_val)
    articles_df_update = gr.update(value=articles_val)

    return (
        chatbot,
        analysis_update,
        guardian_json_update,
        sgr_plan_json_update,
        srp_plan_json_update,
        articles_df_update,
    )


def format_guard_badge(guard_info: dict | None) -> str:
    """Format guard/safety info as colored HTML badge (localized).

    Args:
        guard_info: Dict with safety_level, categories, is_safe, refusal

    Returns:
        HTML badge string showing safety level and localized categories
    """
    if not guard_info:
        return ""

    label = i18n_resolve("guard_badge_label")
    safety_level = guard_info.get("safety_level", "Unknown")
    categories = guard_info.get("categories", [])

    # Color based on safety level
    if safety_level == "Safe":
        color = "#4CAF50"  # green
        level_text = i18n_resolve("guard_level_safe")
    elif safety_level == "Controversial":
        color = "#FF9800"  # orange
        level_text = i18n_resolve("guard_level_controversial")
    else:  # Unsafe or Unknown
        color = "#F44336"  # red
        level_text = i18n_resolve("guard_level_unsafe")

    # Map English category names to i18n keys (case-insensitive, handles variations)
    category_mapping = {
        # Violence variations
        "Violence": "cat_violence",
        "Violent": "cat_violence",
        "Violent Content": "cat_violence",
        "Violent Behavior": "cat_violence",
        # Sexual variations
        "Sexual": "cat_sexual",
        "Sexual Content": "cat_sexual",
        "Sexually Explicit": "cat_sexual",
        # PII variations
        "PII": "cat_pii",
        "Personal Data": "cat_pii",
        "Personally Identifiable": "cat_pii",
        # Self-Harm variations
        "Self-Harm": "cat_self_harm",
        "Self Harm": "cat_self_harm",
        "Suicide": "cat_self_harm",
        # Harassment
        "Harassment": "cat_harassment",
        "Harassment/Threats": "cat_harassment",
        # Hate Speech
        "Hate Speech": "cat_hate",
        "Hate": "cat_hate",
        # Illegal variations
        "Illegal Acts": "cat_illegal",
        "Illegal": "cat_illegal",
        "Non-violent Illegal Acts": "cat_illegal",
        # Unethical
        "Unethical Acts": "cat_unethical",
        "Unethical": "cat_unethical",
        # Politically Sensitive
        "Politically Sensitive": "cat_politically",
        "Political": "cat_politically",
        # Copyright
        "Copyright": "cat_copyright",
        "Copyright Violation": "cat_copyright",
        # Jailbreak
        "Jailbreak": "cat_jailbreak",
        # Spam
        "Spam": "cat_spam",
    }

    # Localize categories (case-insensitive)
    localized_cats = []
    for cat in categories:
        # Try exact match first, then case-insensitive search
        i18n_key = category_mapping.get(cat)
        if not i18n_key:
            # Try case-insensitive search
            cat_lower = cat.lower()
            for key, value in category_mapping.items():
                if key.lower() == cat_lower:
                    i18n_key = value
                    break

        if not i18n_key:
            i18n_key = "cat_other"

        localized_cat = i18n_resolve(i18n_key)
        localized_cats.append(localized_cat)

    # Format categories (show first 2, truncate if too long)
    if localized_cats:
        cats_str = ", ".join(localized_cats[:2])
        if len(localized_cats) > 2:
            cats_str += f" +{len(localized_cats) - 2}"
        content = f"{level_text} | {cats_str}"
    else:
        content = level_text

    return _badge_html(label=label, value=content, color=color)


def format_articles_dataframe(articles: list[dict]) -> list[list]:
    rows: list[list] = []
    for idx, article in enumerate(articles or [], start=1):
        meta = article.get("metadata", {}) if isinstance(article, dict) else {}
        rows.append(
            [
                idx,
                meta.get(
                    "title",
                    article.get("title", "Untitled") if isinstance(article, dict) else "Untitled",
                ),
                f"{meta.get('rerank_score', 0):.2f}"
                if isinstance(meta.get("rerank_score"), (int, float))
                else "",
                f"{meta.get('normalized_rank', 0):.3f}"
                if isinstance(meta.get("normalized_rank"), (int, float))
                else "",
                meta.get("article_url") or meta.get("url") or article.get("url", "")
                if isinstance(article, dict)
                else "",
            ]
        )
    return rows


def _extract_executed_queries(tool_results: list[str]) -> list[str]:
    """Extract deduplicated queries from tool results."""
    from kg_engine.tools.utils import extract_metadata_from_tool_result

    seen_queries: set[str] = set()
    queries: list[str] = []
    for result_str in tool_results:
        meta = extract_metadata_from_tool_result(result_str)
        query = meta.get("query")
        if query and query not in seen_queries:
            seen_queries.add(query)
            queries.append(query)
    return queries


# Initialize singletons (order matters: llm_manager before retriever)
embedder = create_embedder(settings)
vector_store = ChromaStore(collection_name=settings.chromadb_collection)

# Health check: verify ChromaDB HTTP server is reachable
try:
    import chromadb

    health_client = chromadb.HttpClient(
        host=settings.chroma_client_host,
        port=settings.chromadb_port,
    )
    health_client.heartbeat()
    logger.info(
        "✅ ChromaDB HTTP server healthy at %s:%d",
        settings.chroma_client_host,
        settings.chromadb_port,
    )
except Exception as e:
    logger.error(
        "❌ ChromaDB HTTP server unreachable at %s:%d - %s",
        settings.chroma_client_host,
        settings.chromadb_port,
        str(e),
    )
    raise RuntimeError(
        f"Cannot connect to ChromaDB server at {settings.chroma_client_host}:{settings.chromadb_port}. "
        "Ensure 'chroma run' is started or Docker container is running."
    ) from e

llm_manager = LLMManager(
    provider=settings.default_llm_provider,
    model=settings.default_model,
    temperature=settings.llm_temperature,
)
retriever = RAGRetriever(
    embedder=embedder,
    vector_store=vector_store,
    llm_manager=llm_manager,  # NEW: Pass for dynamic context budgeting
    top_k_retrieve=settings.top_k_retrieve,
    top_k_rerank=settings.top_k_rerank,
    rerank_enabled=settings.rerank_enabled,
    metadata_boost_weights={
        "tag_match": settings.rerank_boost_tag,
        "code_presence": settings.rerank_boost_code,
        "section_match": settings.rerank_boost_section,
    },
)
# Use same retriever in retrieve_context tool so FRIDA/direct embedder is never
# loaded in a worker thread (avoids crash when agent first calls the tool).
set_app_retriever(retriever)


def _find_model_for_tokens(required_tokens: int) -> str | None:
    """Find a model that can handle the required token count.

    Args:
        required_tokens: Minimum token capacity needed

    Returns:
        Model name if found, None otherwise
    """
    from kg_engine.llm.fallback import find_fallback_model

    return find_fallback_model(required_tokens)


def _check_context_fallback(messages: list[dict]) -> str | None:
    """Check if context fallback is needed and return fallback model.

    Thin wrapper around ``rag_engine.llm.fallback.check_context_fallback`` so
    that all pre-agent fallback logic is centralized in the LLM fallback
    module. Kept for backward compatibility and tests.
    """
    # Early return if fallback is disabled
    if not getattr(settings, "llm_fallback_enabled", False):
        return None

    return check_context_fallback(messages)


def compress_tool_results(state: dict, runtime) -> dict | None:
    """Compress tool results before LLM call if approaching context limit.

    This middleware runs right before each LLM invocation, AFTER all tool calls complete.
    It extracts ALL articles from ALL tool messages, deduplicates, and compresses
    proportionally based on normalized_rank (0.0 = best, 1.0 = worst).

    Args:
        state: Agent state containing messages
        runtime: Runtime object with access to model config

    Returns:
        Updated state dict with compressed messages, or None if no changes needed
    """
    from kg_engine.llm.compression import compress_tool_messages

    messages = state.get("messages", [])
    if not messages:
        return None

    updated_messages = compress_tool_messages(
        messages=messages,
        runtime=runtime,
        llm_manager=llm_manager,
        threshold_pct=float(getattr(settings, "llm_compression_threshold_pct", 0.85)),
        target_pct=float(getattr(settings, "llm_compression_target_pct", 0.80)),
    )

    if updated_messages:
        return {"messages": updated_messages}

    return None


def _compute_context_tokens_from_state(messages: list[dict]) -> tuple[int, int]:
    """Compute (conversation_tokens, accumulated_tool_tokens) from agent state messages.

    This is a wrapper for the unified compute_context_tokens function.
    Uses configurable JSON overhead percentage from settings.

    - Conversation tokens: count non-tool message contents
    - Accumulated tool tokens: parse tool JSONs, dedupe by kb_id, sum content tokens,
      add configurable JSON overhead percentage (default 30%)
    """
    return compute_context_tokens(messages, tool_results=None, add_json_overhead=True)


def update_context_budget(state: dict, runtime) -> dict | None:
    """Middleware to populate runtime.context token figures before each model call.

    Ensures tools see accurate conversation and accumulated tool tokens via runtime.context.
    """
    messages = state.get("messages", [])
    if not messages:
        return None

    conv_toks, tool_toks = _compute_context_tokens_from_state(messages)

    # Mutate runtime.context (AgentContext) so tools can read accurate figures
    try:
        if hasattr(runtime, "context") and runtime.context:
            runtime.context.conversation_tokens = conv_toks
            runtime.context.accumulated_tool_tokens = tool_toks
            logger.debug(
                "Updated runtime.context: conversation_tokens=%d, accumulated_tool_tokens=%d",
                conv_toks,
                tool_toks,
            )
    except Exception:
        # Do not fail the run due to budgeting issues
        logger.debug("Unable to update runtime.context tokens")

    return None


from collections.abc import Callable  # noqa: E402

from langchain.agents.middleware import AgentMiddleware  # noqa: E402
from langchain.agents.middleware import wrap_tool_call as middleware_wrap_tool_call
from langchain.tools.tool_node import ToolCallRequest  # noqa: E402
from langchain_core.messages import ToolMessage  # noqa: E402
from langgraph.types import Command  # noqa: E402


class ToolBudgetMiddleware(AgentMiddleware):
    """Populate runtime.context tokens right before each tool execution.

    Ensures tools see up-to-date conversation and accumulated tool tokens
    even when multiple tool calls happen within a single agent step.
    """

    @middleware_wrap_tool_call()
    def tool_budget_wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        try:
            state = getattr(request, "state", {}) or {}
            runtime = getattr(request, "runtime", None)

            # Ensure tool_call has a stable id BEFORE tool execution.
            tool_call = getattr(request, "tool_call", None) or {}
            if isinstance(tool_call, dict) and not tool_call.get("id"):
                tool_call["id"] = f"call_{uuid.uuid4().hex}"

            # Ensure runtime.context exists for every tool invocation.
            # Prefer the thread-local AgentContext created by the stream loop (set_current_context()).
            if runtime is not None and (not hasattr(runtime, "context") or runtime.context is None):
                runtime.context = get_current_context() or AgentContext()
                logger.debug("[ToolBudget] Initialized runtime.context (was missing)")

            # Update runtime.context token budget when state has messages.
            if runtime is not None and getattr(runtime, "context", None) and state:
                conv_toks, tool_toks = _compute_context_tokens_from_state(state.get("messages", []))
                runtime.context.conversation_tokens = conv_toks
                runtime.context.accumulated_tool_tokens = tool_toks
                logger.debug(
                    "[ToolBudget] runtime.context updated before tool: conv=%d, tools=%d",
                    conv_toks,
                    tool_toks,
                )

            # Enqueue pending search bubble at tool invocation time (100% reliability).
            if runtime is not None and hasattr(runtime, "context") and runtime.context:
                if tool_call.get("name") == "retrieve_context":
                    args = tool_call.get("args") or {}
                    query = args.get("query", "") if isinstance(args, dict) else ""
                    tool_call_id = tool_call.get("id")
                    if tool_call_id and query:
                        from kg_engine.api.stream_helpers import yield_search_bubble

                        if tool_call_id not in runtime.context.emitted_ui_ids:
                            runtime.context.emitted_ui_ids.add(tool_call_id)
                            runtime.context.pending_ui_messages.append(
                                yield_search_bubble(query, search_id=tool_call_id)
                            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[ToolBudget] Failed to update context before tool: %s", exc, exc_info=True
            )

        return handler(request)


def _create_rag_agent(
    override_model: str | None = None,
    *,
    force_tool_choice: bool = False,
    enable_sgr_planning: bool = True,
    sgr_spam_threshold: float = 0.8,
):
    """Create LangChain agent with optional forced retrieval tool execution and memory compression.

    Uses centralized factory with app-specific middleware. The factory can enforce
    tool execution via tool_choice="retrieve_context" when needed, or allow model
    to choose tools freely by default.

    This wrapper preserves test patch points while delegating to the centralized
    agent_factory for consistent agent creation.

    Args:
        override_model: Optional model name to use instead of default
                       (for context window fallback)
        force_tool_choice: If True, forces retrieve_context tool execution.
                          If False, allows model to choose tools freely (default: False)

    Returns:
        Configured LangChain agent with retrieve_context tool and middleware
    """
    from kg_engine.llm.agent_factory import create_rag_agent

    return create_rag_agent(
        override_model=override_model,
        tool_budget_middleware=ToolBudgetMiddleware(),
        update_context_budget_middleware=update_context_budget,
        compress_tool_results_middleware=compress_tool_results,
        force_tool_choice=force_tool_choice,
        enable_sgr_planning=enable_sgr_planning,
        sgr_spam_threshold=sgr_spam_threshold,
    )


def _is_ui_only_message(msg: dict) -> bool:
    """Check if a message is UI-only (should not be sent to agent).

    UI-only messages include:
    - Disclaimer messages
    - Search started/completed metadata messages
    - Thinking blocks (tool execution metadata)
    - Model switch notices
    - Cancellation messages

    Regular assistant messages (actual answers) should NOT be filtered even if they
    have metadata, as they contain conversation content the agent needs to see.

    Args:
        msg: Message dict to check

    Returns:
        True if message is UI-only, False otherwise
    """
    if not isinstance(msg, dict):
        return False

    # Check for disclaimer content (disclaimer messages don't have metadata)
    from kg_engine.llm.prompts import AI_DISCLAIMER

    content = msg.get("content", "")
    if isinstance(content, str) and AI_DISCLAIMER.strip() in content:
        return True

    # Check for explicit UI-only metadata marker first (preferred, language-agnostic)
    metadata = msg.get("metadata", {})
    if isinstance(metadata, dict):
        ui_type = metadata.get("ui_type")
        if isinstance(ui_type, str) and ui_type in {
            "search_bubble",
            "search_started",
            "search_completed",
            "thinking",
            "generating_answer",
            "model_switch",
            "cancelled",
            "user_intent_display",
            "disclaimer_display",
            "reasoning",
        }:
            return True

    return False


def _disclaimer_injected_in_history(gradio_history: list) -> bool:
    """Return True if an AI disclaimer with disclaimer_injected flag is already in history (this QA turn)."""
    if not gradio_history:
        return False
    for msg in gradio_history:
        if not isinstance(msg, dict):
            continue
        meta = msg.get("metadata")
        if isinstance(meta, dict) and meta.get("disclaimer_injected") is True:
            return True
    return False


def _messages_are_equivalent(msg1: dict, msg2: dict) -> bool:
    """Check if two messages are equivalent (same role and content).

    Used to detect duplicate messages in history.

    Args:
        msg1: First message dict
        msg2: Second message dict

    Returns:
        True if messages are equivalent, False otherwise
    """
    if not isinstance(msg1, dict) or not isinstance(msg2, dict):
        return False

    role1 = msg1.get("role")
    role2 = msg2.get("role")
    if role1 != role2:
        return False

    content1 = msg1.get("content", "")
    content2 = msg2.get("content", "")

    # Compare string content
    if isinstance(content1, str) and isinstance(content2, str):
        return content1.strip() == content2.strip()

    # For structured content, compare as strings
    return str(content1) == str(content2)


def _message_exists_in_history(message: dict, history: list[dict]) -> bool:
    """Check if a message already exists in history.

    Args:
        message: Message dict to check
        history: List of message dicts

    Returns:
        True if message exists in history, False otherwise
    """
    for existing_msg in history:
        if _messages_are_equivalent(message, existing_msg):
            return True
    return False


def _build_agent_messages_from_gradio_history(
    gradio_history: list[dict],
    wrapped_user_content: str | None = None,
) -> list[dict]:
    """Build messages from Gradio history, filtering UI-only messages.

    Args:
        gradio_history: Full Gradio history including UI messages
        wrapped_user_content: If provided, replaces last user message content
                              (for SGR/agent calls). Pass None for SRP.

    Returns:
        List of message dicts in LangChain format.
    """
    from kg_engine.utils.message_utils import normalize_gradio_history_message

    messages = []

    for idx, msg in enumerate(gradio_history):
        msg_role = msg.get("role")
        msg_content = msg.get("content", "")

        # Skip UI-only messages
        if _is_ui_only_message(msg):
            logger.debug(
                "Filtered out UI-only message [%d]: role=%s, content_preview=%s",
                idx,
                msg_role,
                str(msg_content)[:100] if isinstance(msg_content, str) else "non-string",
            )
            continue

        # Normalize message for LangChain
        normalized = normalize_gradio_history_message(msg)

        # Replace blocked message content with placeholder
        if msg_role == "user" and (msg.get("metadata") or {}).get("log") == "blocked_by_guardian":
            locale = os.getenv("GRADIO_LOCALE", "ru")
            normalized["content"] = i18n_resolve("guard_blocked", locale)
            logger.info("Replaced blocked message [%d] with placeholder", idx)

        messages.append(normalized)
        logger.info(
            "Included message [%d]: role=%s, content_preview=%s",
            idx,
            msg_role,
            str(msg_content)[:100] if isinstance(msg_content, str) else "non-string",
        )

    # Replace last user message with wrapper if provided
    if wrapped_user_content and messages and messages[-1]["role"] == "user":
        messages[-1]["content"] = wrapped_user_content
        logger.info("Replaced last user message with wrapped content")
    elif wrapped_user_content and not messages:
        # No history - add wrapped content as user message (for batch/API calls)
        messages.append({"role": "user", "content": wrapped_user_content})
        logger.info("Added wrapped content as new user message")

    return messages


def _process_text_chunk_for_streaming(
    text_chunk: str,
    answer: str,
    disclaimer_prepended: bool,
    has_seen_tool_results: bool,
) -> tuple[str, bool]:
    """Process a text chunk for streaming and accumulate the answer.

    Disclaimer is injected as a separate message before the first chunk (UI only).
    Handles optional newline after tool results.

    Args:
        text_chunk: Raw text chunk from agent
        answer: Accumulated answer so far
        disclaimer_prepended: Whether disclaimer message has already been injected
        has_seen_tool_results: Whether tool results have been seen

    Returns:
        Tuple of (updated_answer, updated_disclaimer_prepended)
    """
    # Newline before first text chunk after tool results (disclaimer is a separate message)
    if has_seen_tool_results and not answer:
        text_chunk = "\n" + text_chunk

    answer = answer + text_chunk
    return answer, disclaimer_prepended


def _extract_stream_delta(chunk: str, accumulated: str) -> tuple[str, str]:
    """Normalize provider chunking differences (incremental vs cumulative).

    Some providers stream incremental deltas, others resend the full accumulated
    text on each token. This helper returns only the new delta and updated
    accumulated value for both modes.
    """
    if not chunk:
        return "", accumulated

    if not accumulated:
        return chunk, chunk

    # Cumulative content (common in some providers): full text re-sent each step.
    if chunk.startswith(accumulated):
        return chunk[len(accumulated) :], chunk
    if accumulated.startswith("\n") and chunk.startswith(accumulated[1:]):
        return chunk[len(accumulated) - 1 :], "\n" + chunk

    # Exact or suffix duplicates: nothing new.
    if chunk == accumulated or chunk == accumulated.lstrip("\n") or accumulated.endswith(chunk):
        return "", accumulated

    # Partial-overlap chunks: some providers resend tail + new content.
    # Trim only meaningful overlaps to avoid false positives on tiny tokens.
    max_k = min(len(accumulated), len(chunk))
    overlap = 0
    for k in range(max_k, 3, -1):
        if accumulated.endswith(chunk[:k]):
            overlap = k
            break
    if overlap:
        delta = chunk[overlap:]
        return delta, accumulated + delta

    # Incremental chunk.
    return chunk, accumulated + chunk


# ── Think-tag constants ─────────────────────────────────────────────────────────
_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


def _normalize_think_tags(text: str) -> str:
    """Normalize escaped think-tag variants to canonical ASCII form.

    Some providers emit JSON-escaped or HTML-escaped angle brackets, producing mixed
    tag pairs like ``\\u003cthink>`` … ``</think>`` or ``<think>`` … ``&lt;/think&gt;``.
    We only normalize when the chunk includes the substring "think" to avoid touching
    unrelated escaped content.
    """
    if "think" not in text.lower():
        return text
    if "\\u003c" in text or "\\u003e" in text:
        text = text.replace("\\u003c", "<").replace("\\u003e", ">")
    if "&lt;" in text or "&gt;" in text:
        text = text.replace("&lt;", "<").replace("&gt;", ">")
    return text


def _parse_think_tags(
    text: str,
    reasoning: str,
    in_block: bool,
) -> tuple[str, str, bool, bool]:
    """Parse <think>...</think> tags from a streamed text chunk.

    Content inside paired tags is accumulated in ``reasoning``.
    An orphan ``</think>`` (no matching open in current state) signals the caller
    to reclassify buffered inter-tool assistant text from chat to the reasoning bubble.
    Escaped tag variants are normalised before parsing.

    Returns:
        (clean_text, reasoning, in_block, saw_orphan_close)
    """
    text = _normalize_think_tags(text)
    if _THINK_OPEN not in text and _THINK_CLOSE not in text and not in_block:
        return text, reasoning, in_block, False

    clean: list[str] = []
    saw_orphan = False
    i = 0

    while i < len(text):
        if in_block:
            end = text.find(_THINK_CLOSE, i)
            if end == -1:
                seg = text[i:]
                if seg:
                    reasoning = (reasoning + "\n" + seg) if reasoning else seg
                break
            seg = text[i:end]
            if seg:
                reasoning = (reasoning + "\n" + seg) if reasoning else seg
            i = end + len(_THINK_CLOSE)
            in_block = False
        else:
            open_i = text.find(_THINK_OPEN, i)
            close_i = text.find(_THINK_CLOSE, i)
            if close_i != -1 and (open_i == -1 or close_i < open_i):
                # Orphan </think>: caller must reclassify buffered inter-tool text as reasoning.
                saw_orphan = True
                if close_i > i:
                    clean.append(text[i:close_i])
                i = close_i + len(_THINK_CLOSE)
                continue
            if open_i == -1:
                clean.append(text[i:])
                break
            if open_i > i:
                clean.append(text[i:open_i])
            i = open_i + len(_THINK_OPEN)
            in_block = True

    return "".join(clean), reasoning, in_block, saw_orphan


def _inject_reasoning_content(
    messages: list[dict],
    *,
    reasoning_enabled: bool = False,
) -> list[dict]:
    if not reasoning_enabled:
        return messages
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        if "reasoning_content" in msg:
            continue
        additional_kwargs = msg.get("additional_kwargs") or {}
        if "reasoning_content" in additional_kwargs:
            msg["reasoning_content"] = additional_kwargs["reasoning_content"]
            continue
        msg["reasoning_content"] = ""
    return messages


def _find_last_assistant_message(messages: list[dict]) -> dict | None:
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and "metadata" not in msg:
            return msg
    return None


def _preserve_reasoning_on_last_assistant(
    gradio_history: list[dict],
    reasoning_text: str,
) -> list[dict]:
    if not reasoning_text.strip():
        return gradio_history
    target = _find_last_assistant_message(gradio_history)
    if target is not None:
        if "additional_kwargs" not in target:
            target["additional_kwargs"] = {}
        target["additional_kwargs"]["reasoning_content"] = reasoning_text.strip()
    return gradio_history


# ── Per-turn reasoning state ────────────────────────────────────────────────────


@dataclasses.dataclass
class _ReasoningCtx:
    """Mutable per-turn state for streaming reasoning extraction and routing."""

    buffer: str = ""  # accumulated reasoning text
    in_block: bool = False  # currently inside a <think> block
    inter_tool_text: str = ""  # text added to `answer` since last tool boundary
    bubble_id: str | None = None
    bubble_text: str = ""  # last content shown in the reasoning bubble

    def close(self) -> str:
        remaining = ""
        if self.in_block and self.buffer:
            remaining = self.buffer
        self.in_block = False
        self.inter_tool_text = ""
        return remaining


def _has_generating_spinner(gradio_history: list, generating_answer_id: str) -> bool:
    """Return True if the generating-answer spinner is already present in history."""
    return any(
        isinstance(msg, dict)
        and msg.get("role") == "assistant"
        and (msg.get("metadata") or {}).get("id") == generating_answer_id
        for msg in gradio_history
    )


def _process_reasoning_chunk(
    text: str,
    ctx: _ReasoningCtx,
    answer: str,
    has_seen_tool_results: bool,
    reasoning_enabled: bool,
    harmony_parser,
    gradio_history: list,
    *,
    harmony_strip_only: bool = False,
) -> Generator[list, None, tuple[str, bool]]:
    # NOTE: agent_chat_handler is an async generator — ``yield from`` is not
    # allowed there.  Drive this generator with the helper below instead.
    """Parse think tags, handle orphan reclassification, run harmony, route pre-tool text.

    Mutates *ctx* in place. Yields ``list(gradio_history)`` on every UI change.
    Use as::

        text, should_skip = yield from _process_reasoning_chunk(...)
        if should_skip:
            continue          # text already routed to reasoning — skip chat streaming

    ``should_skip=True`` means the chunk has been fully handled (routed to the
    reasoning bubble or consumed as orphan context); the caller must ``continue``.
    """
    saw_orphan = False

    if reasoning_enabled:
        old_buffer = ctx.buffer
        text, parsed_reasoning, ctx.in_block, saw_orphan = _parse_think_tags(
            text, ctx.buffer, ctx.in_block
        )
        if harmony_strip_only:
            # Strip <think> from text but don't add Harmony reasoning. Still add think-tag
            # content: content_blocks may end with `<think>`, next chunk is continuation.
            if parsed_reasoning and parsed_reasoning != old_buffer:
                ctx.buffer = parsed_reasoning
            else:
                ctx.buffer = old_buffer
        # Orphan </think> between tool calls → reclassify inter-tool chat text as reasoning.
        if saw_orphan and not harmony_strip_only and has_seen_tool_results and ctx.inter_tool_text:
            sep = "\n" if ctx.buffer else ""
            ctx.buffer += sep + ctx.inter_tool_text
            answer = answer[: len(answer) - len(ctx.inter_tool_text)]
            ctx.inter_tool_text = ""
            ctx.bubble_id, ctx.bubble_text, _ = _upsert_reasoning_bubble(
                gradio_history, ctx.buffer, ctx.bubble_id, ctx.bubble_text
            )
            _update_or_append_assistant_message(gradio_history, answer)
            yield list(gradio_history)
        if harmony_parser:
            h_reasoning, h_final = harmony_parser.feed(text)
            if h_reasoning and not harmony_strip_only:
                ctx.buffer += h_reasoning
            text = h_final
        if ctx.buffer:
            ctx.bubble_id, ctx.bubble_text, changed = _upsert_reasoning_bubble(
                gradio_history, ctx.buffer, ctx.bubble_id, ctx.bubble_text
            )
            if changed:
                yield list(gradio_history)
        if not text or saw_orphan:
            return text, True  # orphan context / empty chunk — caller must continue

    # Remaining text is user-facing answer (from Harmony assistantfinal or outside <think>).
    # Stream it to chat; do not route to reasoning bubble (fixes no-tool turns eating the answer).
    return text, False


async def _apply_reasoning_chunk(
    text: str,
    ctx: _ReasoningCtx,
    answer: str,
    has_seen_tool_results: bool,
    reasoning_enabled: bool,
    harmony_parser,
    gradio_history: list,
    *,
    harmony_strip_only: bool = False,
) -> tuple[list, str, bool]:
    """Async-safe driver for ``_process_reasoning_chunk``.

    ``yield from`` is forbidden inside async generators; this wrapper manually
    iterates the sync helper and collects intermediate history yields.

    Returns ``(history_frames, clean_text, should_skip)`` where *history_frames*
    are the UI updates to yield in the caller, and *should_skip* signals that the
    text has already been routed (caller must ``continue``).
    """
    gen = _process_reasoning_chunk(
        text,
        ctx,
        answer,
        has_seen_tool_results,
        reasoning_enabled,
        harmony_parser,
        gradio_history,
        harmony_strip_only=harmony_strip_only,
    )
    frames: list[list] = []
    try:
        while True:
            frames.append(next(gen))
    except StopIteration as exc:
        clean_text, should_skip = exc.value
    return frames, clean_text, should_skip


def _truncate_reasoning_text(
    reasoning: str,
    max_chars: int = 4000,
    *,
    max_lines: int | None = None,
    include_note: bool = False,
) -> str:
    """Render a tail slice of reasoning for the UI bubble.

    The full reasoning trace stays in diagnostics; the bubble only shows a
    short tail (by lines and/or characters), optionally with a footer note.
    """
    text = (reasoning or "").strip()
    if not text:
        return ""

    # Prefer trimming by last *max_lines* to give a rotating multi-line window.
    if max_lines is not None and max_lines > 0:
        lines = text.splitlines()
        if len(lines) > max_lines:
            tail_lines = lines[-max_lines:]
            tail = "\n".join(tail_lines).lstrip()
            if include_note:
                return "…" + tail + "\n\n...[обрезано для краткости]"
            return "…" + tail

    # Fallback/secondary guard: trim by characters if needed.
    if len(text) <= max_chars:
        return text
    tail = text[-max_chars:].lstrip()
    if include_note:
        return "…" + tail + "\n\n...[обрезано для краткости]"
    return "…" + tail


def _find_ui_message_by_id(
    gradio_history: list[dict], ui_type: str, message_id: str | None
) -> dict | None:
    """Find UI message by type and metadata id."""
    if not message_id:
        return None
    for i in range(len(gradio_history) - 1, -1, -1):
        msg = gradio_history[i]
        if not isinstance(msg, dict):
            continue
        md = msg.get("metadata") or {}
        if md.get("ui_type") == ui_type and md.get("id") == message_id:
            return msg
    return None


def _upsert_reasoning_bubble(
    gradio_history: list[dict],
    reasoning_buffer: str,
    reasoning_bubble_id: str | None,
    last_reasoning_bubble_text: str,
) -> tuple[str | None, str, bool]:
    """Create or update the reasoning bubble, returning (id, last_text, changed)."""
    from kg_engine.api.stream_helpers import yield_reasoning_bubble
    from kg_engine.config.settings import settings

    tail_lines = max(settings.ui_reasoning_tail_lines, 1)
    truncated = _truncate_reasoning_text(reasoning_buffer, max_lines=tail_lines)
    if not truncated or truncated == last_reasoning_bubble_text:
        return reasoning_bubble_id, last_reasoning_bubble_text, False

    msg = _find_ui_message_by_id(gradio_history, "reasoning", reasoning_bubble_id)
    if msg is None:
        bubble = yield_reasoning_bubble(truncated)
        reasoning_bubble_id = (bubble.get("metadata") or {}).get("id")
        gradio_history.append(bubble)
        return reasoning_bubble_id, bubble["content"], True

    msg["content"] = truncated
    return reasoning_bubble_id, truncated, True


def _finalize_reasoning_bubble(
    gradio_history: list[dict],
    reasoning_bubble_id: str | None,
    reasoning_buffer: str = "",
) -> str | None:
    """Mark reasoning bubble as done, creating one if needed."""
    from kg_engine.api.stream_helpers import yield_reasoning_bubble
    from kg_engine.config.settings import settings

    tail_lines = max(settings.ui_reasoning_tail_lines, 1)
    msg = _find_ui_message_by_id(gradio_history, "reasoning", reasoning_bubble_id)
    if msg is None and reasoning_buffer.strip():
        bubble = yield_reasoning_bubble(
            _truncate_reasoning_text(
                reasoning_buffer,
                max_lines=tail_lines,
                include_note=True,
            )
        )
        (bubble.get("metadata") or {})["status"] = "done"
        gradio_history.append(bubble)
        return (bubble.get("metadata") or {}).get("id")

    if msg is not None:
        md = msg.get("metadata") or {}
        if reasoning_buffer.strip():
            msg["content"] = _truncate_reasoning_text(
                reasoning_buffer,
                max_lines=tail_lines,
                include_note=True,
            )
        md["status"] = "done"
    return reasoning_bubble_id


def _extract_content_string(content: str | list | None) -> str:
    """Extract plain text string from Gradio message content.

    Handles both string format and structured format (list of content blocks).
    Also handles double-encoded JSON strings that Gradio sometimes sends.

    Args:
        content: Message content (string, list of blocks, or None)

    Returns:
        Plain text string extracted from content
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Handle structured content format (Gradio 6): [{"type": "text", "text": "..."}]
        text_parts = []
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type == "text":
                    text = block.get("text", "")
                    if text:
                        # Recursively handle nested structures (double-encoded JSON)
                        # Handle case where text field contains a JSON string: "[{'text': '...', 'type': 'text'}]"
                        if (
                            isinstance(text, str)
                            and text.strip().startswith("[")
                            and text.strip().endswith("]")
                        ):
                            try:
                                parsed = json.loads(text)
                                if isinstance(parsed, list):
                                    # Recursively extract from nested structure
                                    extracted = _extract_content_string(parsed)
                                    if extracted:
                                        text_parts.append(extracted)
                                        continue
                            except (json.JSONDecodeError, ValueError):
                                # Not valid JSON, treat as plain text
                                pass
                        text_parts.append(str(text))
        return " ".join(text_parts) if text_parts else ""
    # Fallback: convert to string
    return str(content)


def _update_or_append_assistant_message(gradio_history: list[dict], content: str) -> None:
    """Update last assistant message or append new one if it has metadata.

    Only updates non-metadata assistant messages to preserve meta blocks.
    This ensures meta blocks (thinking, searching, etc.) are not overwritten.

    Args:
        gradio_history: List of Gradio message dictionaries
        content: Content to set for the assistant message
    """
    # Final safety net: never render leaked <think> tags in chat bubbles, but avoid
    # corrupting normal answers or literal <think> examples.
    text = str(content)
    # Fast path: no think-tags present.
    if _THINK_OPEN not in text and _THINK_CLOSE not in text and "\\u003cthink" not in text:
        sanitized_content = text
    else:
        # Minimal heuristic:
        # - When reasoning is enabled, strip all <think> content from UI (reasoning is
        #   already captured structurally elsewhere).
        # - When disabled, treat only a leading or whole-turn <think> block as
        #   reasoning; leave mid-sentence tag examples untouched.
        reasoning_enabled = getattr(settings, "llm_reasoning_enabled", False)
        if reasoning_enabled:
            sanitized_content, _, _, _ = _parse_think_tags(text, "", False)
        else:
            # Leading-block heuristic: preserve prefix before the first <think>;
            # if text starts directly with <think>, rely on parser to drop that
            # block and keep any following final answer.
            stripped = text.lstrip()
            if stripped.startswith(_THINK_OPEN):
                sanitized_content, _, _, _ = _parse_think_tags(text, "", False)
            else:
                sanitized_content = text
    if (
        gradio_history
        and gradio_history[-1].get("role") == "assistant"
        and not gradio_history[-1].get("metadata")
    ):
        gradio_history[-1] = {"role": "assistant", "content": sanitized_content}
    else:
        gradio_history.append({"role": "assistant", "content": sanitized_content})


async def agent_chat_handler(
    message: str,
    history: list[dict],
    cancel_state: dict | None = None,
    request: gr.Request | None = None,
    skip_srp: bool = False,
) -> AsyncGenerator[list[dict], None]:
    """Ask questions about Comindware Platform documentation and get intelligent answers with citations.

    The assistant automatically searches the knowledge base to find relevant articles
    and provides comprehensive answers based on official documentation. Use this for
    technical questions, configuration help, API usage, troubleshooting, and general
    platform guidance.

    Args:
        message: User's current message or question
        history: Chat history from Gradio
        cancel_state: Mutable dict with "cancelled" key for cooperative cancellation
        request: Gradio request object for session management

    Yields:
        Complete message history lists (for Chatbot) to preserve all messages
        including disclaimer, thinking blocks, and streaming answer.
        Uses reference agent pattern: always yields full working_history list.
    """

    # Helper to check if cancellation was requested
    def is_cancelled() -> bool:
        return cancel_state is not None and cancel_state.get("cancelled", False)

    if not message or not message.strip():
        yield history if history else []
        return

    # Build full message history starting from provided history
    # This ensures all messages (disclaimer, thinking blocks, answer) persist during streaming
    # Note: We keep original format for ChatInterface, normalize only when needed for agent

    # Initialize variables that might be needed in error handling
    current_model = settings.default_model
    messages = []
    tool_results = []

    # Build working history from provided history (like reference agent pattern)
    # Reference agent pattern: working_history = history + [new messages]
    # This ensures we start from ChatInterface's current state and build incrementally
    # Then we always yield the full working_history list
    gradio_history = list(history) if history else []
    turn_start = time.perf_counter()

    # Log history state for debugging memory issues
    logger.info(
        "agent_chat_handler called: message='%s', history_length=%d, gradio_history_length=%d",
        message[:50] if message else "",
        len(history) if history else 0,
        len(gradio_history),
    )
    if gradio_history:
        logger.debug(
            "Previous conversation messages in history: %d user, %d assistant",
            sum(1 for msg in gradio_history if isinstance(msg, dict) and msg.get("role") == "user"),
            sum(
                1
                for msg in gradio_history
                if isinstance(msg, dict) and msg.get("role") == "assistant"
            ),
        )

    # Don't add user message here - it's already in history from ChatInterface pattern
    # The submit_event chain adds the user message to chatbot before calling agent_chat_handler
    # (pattern from test script: line 128-129)

    # Determine if this is the first message (for template only; disclaimer injected before first answer chunk)
    is_first_message = not history

    # Three UI blocks pattern (from test script):
    # Thinking/search blocks are added dynamically when tools are actually called
    # (not here, to maintain correct order: SGR planning -> tool calls -> answer generation)
    # This prevents showing spinners for tools that aren't actually called

    # Session management (reuse existing pattern)
    base_session_id = getattr(request, "session_hash", None) if request is not None else None
    session_id = salt_session_id(base_session_id, history, message)

    # Wrap user message in template only for the first question in the conversation
    # Note: dynamic_context will be built after moderation check below
    from kg_engine.llm.prompts import (
        USER_QUESTION_TEMPLATE_FIRST,
        USER_QUESTION_TEMPLATE_SUBSEQUENT,
        get_dynamic_context,
    )

    # Wrap user message with template and dynamic context (built after moderation below)
    # SGR planning is enabled by default
    enable_sgr_planning_flag = True

    # Save user message to conversation store (BEFORE agent execution)
    # This ensures conversation history is tracked for memory compression
    if session_id:
        llm_manager._conversations.append(session_id, "user", message)

    # --- Guardian (Content Moderation) ---
    # Check user message with guardian BEFORE building messages
    from kg_engine.core.guard_client import guard_client

    moderation_result: dict | None = None
    moderation_context: str | None = None
    guard_debug_info: dict | None = None

    # Skip if guardian is disabled
    if not settings.guard_enabled:
        logger.info("Guardian is disabled, skipping moderation")
    else:
        try:
            moderation_result = await guard_client.classify(message)
            logger.info(
                "Guardian result: safety_level=%s, categories=%s",
                moderation_result.get("safety_level") if moderation_result else None,
                moderation_result.get("categories") if moderation_result else None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Guardian API call failed: %s", exc, exc_info=True)
            moderation_result = None

    # Handle based on guard mode
    guard_mode = getattr(settings, "guard_mode", "enforce")
    should_block = guard_client.should_block(moderation_result) if moderation_result else False

    if should_block and guard_mode == "enforce":
        # Enforce mode: Block unsafe content immediately

        # Mark user message with log field (survives Gradio round-trips)
        # log is part of MetadataDict and persists across turns
        for i in range(len(gradio_history) - 1, -1, -1):
            msg = gradio_history[i]
            if isinstance(msg, dict) and msg.get("role") == "user":
                metadata = msg.get("metadata") or {}
                metadata["log"] = "blocked_by_guardian"
                msg["metadata"] = metadata
                logger.info("Marked user message at index %d as blocked", i)
                break

        # Build guard_debug_info structure
        guard_debug_info = {
            "safety_level": moderation_result.get("safety_level", "Unknown")
            if moderation_result
            else "Unknown",
            "categories": moderation_result.get("categories", []) if moderation_result else [],
            "is_safe": moderation_result.get("is_safe", True) if moderation_result else True,
            "refusal": moderation_result.get("refusal", "No") if moderation_result else "No",
            "provider": moderation_result.get("provider", "unknown")
            if moderation_result
            else "unknown",
            "blocked": True,
        }

        # Generic error message - no hints
        locale = os.getenv("GRADIO_LOCALE", "ru")
        error_message = f"❌ {i18n_resolve('guard_blocked', locale)}"
        gradio_history.append(
            {
                "role": "assistant",
                "content": error_message,
                "metadata": {},
            }
        )
        yield list(gradio_history)

        # Yield AgentContext with guard_debug_info for debug pane and metadata updates
        agent_context = AgentContext(
            conversation_tokens=0,
            accumulated_tool_tokens=0,
            diagnostics={
                "guard": guard_debug_info,
                "guard_mode": guard_mode,
            },
        )
        yield agent_context
        return

    elif moderation_result:
        # Not blocked - still create guard_debug_info for analytics/reporting
        guard_debug_info = {
            "safety_level": moderation_result.get("safety_level", "Unknown"),
            "categories": moderation_result.get("categories", []),
            "is_safe": moderation_result.get("is_safe", True),
            "refusal": moderation_result.get("refusal", "No"),
            "provider": moderation_result.get("provider", "unknown"),
            "blocked": False,
        }

    def _expand_guardian_categories(categories: list[str]) -> list[str]:
        category_expansions = {
            "PII": "PII (Personal Identifiable Information)",
            "Jailbreak": "Jailbreak (System Prompt Override Attempt)",
        }
        return [category_expansions.get(cat, cat) for cat in categories]

    moderation_context: str | None = None
    if moderation_result:
        safety_level = moderation_result.get("safety_level", "Safe")
        categories = moderation_result.get("categories", [])
        guard_mode = getattr(settings, "guard_mode", "enforce")

        if safety_level == "Controversial":
            if categories:
                categories_str = ", ".join(_expand_guardian_categories(categories))
                moderation_context = (
                    "<safety_validation>\n"
                    f"  Safety: Controversial\n"
                    f"  Categories: {categories_str}\n"
                    "</safety_validation>"
                )
            else:
                moderation_context = (
                    "<safety_validation>\n  Safety: Controversial\n</safety_validation>"
                )
        elif safety_level == "Unsafe" and guard_mode == "report":
            if categories:
                categories_str = ", ".join(_expand_guardian_categories(categories))
                moderation_context = (
                    "<safety_validation>\n"
                    f"  Safety: Unsafe\n"
                    f"  Categories: {categories_str}\n"
                    "</safety_validation>"
                )
            else:
                moderation_context = "<safety_validation>\n  Safety: Unsafe\n</safety_validation>"

    # Build dynamic context for user wrapper (datetime + guardian + SGR)
    dynamic_context = get_dynamic_context(
        moderation_context=moderation_context,
        include_sgr=enable_sgr_planning_flag,
    )

    # Build wrapped message with dynamic context
    if is_first_message:
        wrapped_message = USER_QUESTION_TEMPLATE_FIRST.format(
            dynamic_context=dynamic_context, question=message
        )
    else:
        wrapped_message = USER_QUESTION_TEMPLATE_SUBSEQUENT.format(
            dynamic_context=dynamic_context, question=message
        )

    # Build messages from gradio_history for agent (LangChain format)
    # This filters out UI-only messages (disclaimer, search_started, etc.)
    # and ensures the agent only sees actual conversation content
    messages = _build_agent_messages_from_gradio_history(
        gradio_history, wrapped_user_content=wrapped_message
    )

    # Inject reasoning_content on all assistant messages for multi-turn round-trip.
    # Reasoning-enabled models (DeepSeek, OpenAI reasoning, etc.) require this field
    # on outgoing assistant messages to continue emitting thinking as reasoning_content.
    # Without it, the model falls back to plain content (thinking leak) or returns 400.
    messages = _inject_reasoning_content(
        messages,
        reasoning_enabled=getattr(settings, "llm_reasoning_enabled", False),
    )

    # Log messages being sent to agent for debugging memory issues
    logger.info(
        "Building agent messages: gradio_history_length=%d -> agent_messages_length=%d",
        len(gradio_history),
        len(messages),
    )
    if messages:
        logger.debug(
            "Agent messages breakdown: %d user, %d assistant",
            sum(1 for msg in messages if isinstance(msg, dict) and msg.get("role") == "user"),
            sum(1 for msg in messages if isinstance(msg, dict) and msg.get("role") == "assistant"),
        )

    # Note: pre-agent trimming removed by request; rely on existing middleware

    # Check if we need model fallback BEFORE creating agent
    # This matches old handler's upfront fallback check
    selected_model = None
    if settings.llm_fallback_enabled:
        selected_model = _check_context_fallback(messages)

    # Use static system prompt (cacheable)
    from kg_engine.llm.prompts import get_system_prompt

    system_msg = {"role": "system", "content": get_system_prompt()}
    messages = [system_msg] + messages
    logger.debug("Using static system prompt (cacheable)")

    # --- Forced user request analysis as tool call (per-turn) ---
    # We force an "analyse_user_request" tool call once per user turn, capture the plan, and
    # then inject the resulting tool-call transcript into the agent messages.
    # SGR planning is enabled by default (can be disabled via _create_rag_agent parameter)
    sgr_plan_dict: dict | None = None
    if enable_sgr_planning_flag:
        logger.info("SGR planning enabled, executing forced analyse_user_request tool call")
        try:
            from kg_engine.api.stream_helpers import yield_sgr_planning_started

            # Show dedicated SGR bubble (like other tool bubbles)
            gradio_history.append(yield_sgr_planning_started())
            yield list(gradio_history)
            logger.info("SGR planning UI bubble added to history")

            from kg_engine.llm.llm_manager import LLMManager

            # Initialize LLM
            sgr_llm = LLMManager(
                provider=settings.default_llm_provider,
                model=selected_model or settings.default_model,
                temperature=settings.llm_temperature,
            )._chat_model()

            # Use bind_tools + tool_choice for forced tool execution (validates + returns markdown)
            logger.info("Calling SGR planning LLM with %d messages", len(messages))
            yield list(gradio_history)

            from kg_engine.llm.model_configs import MODEL_CONFIGS
            from kg_engine.tools.analyse_user_request import analyse_user_request

            sgr_model = selected_model or settings.default_model
            sgr_cfg = MODEL_CONFIGS.get(sgr_model, {})
            sgr_supports_forced = sgr_cfg.get("supports_forced_tool_choice", True)
            sgr_tool_choice = "analyse_user_request" if sgr_supports_forced else "auto"
            sgr_llm_forced = sgr_llm.bind_tools([analyse_user_request], tool_choice=sgr_tool_choice)
            response = await sgr_llm_forced.ainvoke(messages)
            logger.info("SGR LLM returned: %s", type(response))

            if response.tool_calls:
                tool_call = response.tool_calls[0]
                # Execute tool - validates args via Pydantic and returns both json + markdown
                result = await analyse_user_request.ainvoke(tool_call["args"])
                sgr_plan_dict = result["json"]
                sgr_markdown = result["markdown"]
                logger.info(
                    "SGR plan extracted: spam_score=%.2f, user_intent_len=%d, queries_count=%d",
                    sgr_plan_dict.get("spam_score", 0.0),
                    len(sgr_plan_dict.get("user_intent", "")),
                    len(sgr_plan_dict.get("knowledge_base_search_queries", [])),
                )
            else:
                logger.warning("SGR LLM did not make tool call")
                sgr_plan_dict = None
                sgr_markdown = None

            if sgr_plan_dict:
                plan_json = json.dumps(sgr_plan_dict, ensure_ascii=False, separators=(",", ":"))
                call_id = "sgr_plan_call"

                messages = list(messages) + [
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": "analyse_user_request",
                                    "arguments": plan_json,
                                },
                            }
                        ],
                    },
                    {
                        "role": "tool",
                        "content": sgr_markdown,  # Use markdown from tool result
                        "tool_call_id": call_id,
                    },
                ]
                logger.info(
                    "SGR plan injected into agent messages (total messages: %d)", len(messages)
                )
            else:
                logger.warning("SGR plan dict is None or empty, not injecting into messages")

            from kg_engine.api.stream_helpers import (
                get_text,
                update_message_status_in_history,
            )

            update_message_status_in_history(gradio_history, "sgr_planning", "done")

            # Replace SGR planning bubble with user intent message (UI only, not context)
            if sgr_plan_dict and sgr_plan_dict.get("user_intent"):
                user_intent = sgr_plan_dict.get("user_intent", "").strip()
                if user_intent:
                    # Find and replace the sgr_planning bubble with normal assistant message
                    for i, msg in enumerate(gradio_history):
                        if isinstance(msg, dict) and msg.get("role") == "assistant":
                            metadata = msg.get("metadata")
                            if (
                                isinstance(metadata, dict)
                                and metadata.get("ui_type") == "sgr_planning"
                            ):
                                # Replace with normal assistant message with type metadata for context management
                                prefix = get_text("user_intent_prefix")
                                gradio_history[i] = {
                                    "role": "assistant",
                                    "content": f"**{prefix}**\n\n{user_intent}\n",
                                    "metadata": {
                                        "ui_type": "user_intent_display",  # Type for future context management
                                    },
                                }
                                logger.info(
                                    "Replaced SGR planning bubble with user intent: '%s'...",
                                    user_intent[:100],
                                )
                                break

            yield list(gradio_history)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "SGR forced tool call failed; continuing without plan: %s", exc, exc_info=True
            )
            from kg_engine.api.stream_helpers import update_message_status_in_history

            update_message_status_in_history(gradio_history, "sgr_planning", "done")
            yield list(gradio_history)
    else:
        logger.info("SGR planning disabled (enable_sgr_planning=False), skipping")

    # Add thinking spinner to show progress while LLM generates tool calls (same id used for removal in stream)
    from kg_engine.api.stream_helpers import short_uid, yield_thinking_block

    thinking_id = (
        short_uid()
    )  # single id for initial block; stream loop reuses it for remove_message_by_id
    thinking_msg = yield_thinking_block("agent", block_id=thinking_id)
    gradio_history.append(thinking_msg)
    yield list(gradio_history)

    # Create agent (with fallback model if needed) and stream execution
    # Force tool choice only on first message; allow model to choose on subsequent turns
    # TEMPORARILY DISABLED FOR TESTING: force_tool_choice=False
    agent = _create_rag_agent(
        override_model=selected_model, force_tool_choice=False
    )  # was: is_first_message
    tool_results = []
    answer = ""
    current_model = selected_model or settings.default_model
    has_seen_tool_results = False
    _needs_separator = (
        False  # pending newline before first text chunk after tool results
    )
    disclaimer_prepended = False  # Track if disclaimer has been prepended to stream

    # Track incomplete response for memory saving if cancelled (pattern from test script)
    incomplete_response = None
    final_response = None

    # Track accumulated context for progressive budgeting
    # Agent is responsible for counting context, not the tool
    conversation_tokens, _ = estimate_accumulated_tokens(messages, [])

    # Initialize tool call accumulator for streaming chunks
    from kg_engine.api.stream_helpers import (
        ToolCallAccumulator,
        drain_pending_ui_messages,
        remove_message_by_id,
        short_uid,
        update_search_bubble_by_id,
        yield_search_bubble,
        yield_thinking_block,
    )

    tool_call_accumulator = ToolCallAccumulator()
    # Unified bubble approach:
    # We use the stable ToolMessage.tool_call_id as the search bubble id (search_id).
    # Middleware ensures this id exists before the tool is executed.
    # Track which search bubbles have been marked as completed to prevent duplicates
    completed_search_ids: set[str] = set()
    # Reuse thinking_id from initial block above for removal when first search bubble or text arrives
    # Track generating answer block ID for removal when done
    generating_answer_id = short_uid()

    agent_context: AgentContext | None = None
    try:
        # Track tool execution state
        # Only stream text content when NOT executing tools
        tool_executing = False

        # Per-turn reasoning state: think-tag parser + bubble management.
        rctx = _ReasoningCtx()
        reasoning_stream_text: str = ""
        reasoning_enabled: bool = getattr(settings, "llm_reasoning_enabled", False)
        content_stream_text: str = ""
        has_seen_content_blocks_reasoning: bool = False
        # Harmony format (GPT-OSS) — stateful parser for streaming channel separation.
        from kg_engine.api.harmony_parser import HarmonyStreamParser
        from kg_engine.llm.model_configs import MODEL_CONFIGS

        harmony_enabled = bool(
            MODEL_CONFIGS.get(current_model or "", {}).get("harmony_format", False)
        )
        harmony_parser: HarmonyStreamParser | None = (
            HarmonyStreamParser() if harmony_enabled else None
        )

        # Pass accumulated context to agent via typed context parameter
        # Tools can access this via runtime.context (typed, clean!)
        agent_context = AgentContext(
            conversation_tokens=conversation_tokens,
            accumulated_tool_tokens=0,  # Updated as we go
            fetched_kb_ids=set(),  # Reset for new turn - tracks articles fetched in this turn
        )
        if sgr_plan_dict:
            agent_context.sgr_plan = sgr_plan_dict

        # Workaround for LangChain streaming bug: store context in thread-local storage
        # so tools can access it even when runtime.context is None during astream()
        from kg_engine.utils.context_tracker import set_current_context

        set_current_context(agent_context)

        # vLLM streaming limitation: tool_choice doesn't work in streaming mode
        # vLLM ignores tool_choice="retrieve_context" in streaming and returns finish_reason=stop
        # instead of finish_reason=tool_calls. This means forced tool execution requires invoke() mode.
        # The fallback ensures tool calls are executed even when streaming detection fails.
        # Can be disabled via vllm_streaming_fallback_enabled=False for testing (will fail to execute tools)
        is_vllm = is_vllm_provider()
        fallback_to_invoke = False

        # Use multiple stream modes for complete streaming experience
        # Per https://docs.langchain.com/oss/python/langchain/streaming#stream-multiple-modes
        # Always try streaming first - improved detection should catch tool calls via content_blocks/finish_reason
        logger.info("Starting agent.astream() with %d messages", len(messages))
        stream_chunk_count = 0
        tool_calls_detected_in_stream = False

        # Increase recursion limit for complex conversations to avoid GRAPH_RECURSION_LIMIT errors
        agent_config = {"recursion_limit": settings.langchain_recursion_limit}

        try:
            async for stream_mode, chunk in agent.astream(
                {"messages": messages},
                context=agent_context,
                config=agent_config,
                stream_mode=["updates", "messages"],
            ):
                # Check for cancellation at each iteration
                if is_cancelled():
                    logger.info("Cancellation detected in stream loop - stopping")
                    break

                stream_chunk_count += 1
                logger.debug("Stream chunk #%d: mode=%s", stream_chunk_count, stream_mode)

                # Flush any middleware-enqueued UI messages (e.g., pending search bubbles).
                if agent_context is not None and drain_pending_ui_messages(
                    gradio_history, agent_context
                ):
                    remove_message_by_id(gradio_history, thinking_id)
                    yield list(gradio_history)

                # Handle "messages" mode for token streaming
                if stream_mode == "messages":
                    token, metadata = chunk
                    token_type = getattr(token, "type", "unknown")
                    # Disabled verbose token logging for production
                    # logger.info("Messages token #%d: type=%s", stream_chunk_count, token_type)

                    # Debug logging for vLLM tool calling issues (only when expecting tool calls)
                    # Check for both "ai" type and AIMessageChunk class (LangChain uses different representations)
                    token_class = type(token).__name__
                    is_ai_message = (
                        token_type == "ai"
                        or "AIMessage" in token_class
                        or "AIMessage" in str(token_type)
                    )

                    # Process all AI tokens through accumulator to accumulate tool_call chunks
                    # This ensures we capture query even if chunks arrive before tool_call is detected
                    if is_ai_message:
                        # Process token through accumulator to extract query (works for both streaming chunks and complete tool_calls)
                        tool_call_accumulator.process_token(token)
                        tool_call_accumulator.get_tool_name(token)
                        # NOTE: search bubbles are created when we have a stable tool_call_id (token.tool_calls)
                        # and updated on tool results via ToolMessage.tool_call_id.

                    if is_ai_message:
                        has_tool_calls = bool(getattr(token, "tool_calls", None))
                        content = str(getattr(token, "content", ""))
                        response_metadata = getattr(token, "response_metadata", {})
                        finish_reason = (
                            response_metadata.get("finish_reason", "N/A")
                            if isinstance(response_metadata, dict)
                            else "N/A"
                        )

                        # Check content_blocks for tool_call_chunk (critical for vLLM streaming)
                        content_blocks = getattr(token, "content_blocks", None)
                        has_content_blocks = bool(content_blocks)
                        tool_call_chunks_in_blocks = 0
                        if content_blocks:
                            tool_call_chunks_in_blocks = sum(
                                1
                                for block in content_blocks
                                if block.get("type") == "tool_call_chunk"
                            )
                            # Log first few content_blocks in detail for debugging (only when tool calls detected)
                            if tool_call_chunks_in_blocks > 0 or finish_reason == "tool_calls":
                                logger.debug(
                                    "Content blocks detail: %s",
                                    content_blocks[:3]
                                    if len(content_blocks) > 3
                                    else content_blocks,
                                )

                        # Enhanced logging only when we expect tool calls but haven't detected them yet
                        expected_tool_calls = is_vllm and not has_seen_tool_results
                        if expected_tool_calls and not tool_calls_detected_in_stream:
                            # Only log when we're actively debugging missing tool calls
                            logger.debug(
                                "AI token #%d: has_tool_calls=%s, content_length=%d, finish_reason=%s, "
                                "has_content_blocks=%s, tool_call_chunks=%d",
                                stream_chunk_count,
                                has_tool_calls,
                                len(content),
                                finish_reason,
                                has_content_blocks,
                                tool_call_chunks_in_blocks,
                            )
                        # Disabled verbose AI token logging for production
                        # else:
                        #     logger.debug(
                        #         "AI token: has_tool_calls=%s, content_length=%d, finish_reason=%s",
                        #         has_tool_calls,
                        #         len(content),
                        #         finish_reason,
                        #     )

                    # Filter out tool-related messages (DO NOT display in chat)
                    # 1. Tool results (type="tool") - processed internally for citations
                    if hasattr(token, "type") and token.type == "tool":
                        tool_results.append(token.content)
                        logger.debug("Tool result received, %d total results", len(tool_results))
                        tool_executing = False
                        has_seen_tool_results = True
                        _needs_separator = True
                        rctx.inter_tool_text = (
                            ""  # new inter-tool phase; reset reclassification window
                        )

                        # Flush any middleware-enqueued UI messages BEFORE we mutate bubbles to completed.
                        # This guarantees the user sees pending -> complete as two yields,
                        # even when the tool result is the first chunk we receive.
                        if agent_context is not None and drain_pending_ui_messages(
                            gradio_history, agent_context
                        ):
                            remove_message_by_id(gradio_history, thinking_id)
                            yield list(gradio_history)

                        # Remove thinking block when tool result arrives (if still present)
                        remove_message_by_id(gradio_history, thinking_id)

                        # For unified bubble, update it with results
                        bubble_updated = False
                        try:
                            result_data = (
                                json.loads(token.content) if isinstance(token.content, str) else {}
                            )
                            query_from_result = result_data.get("metadata", {}).get("query", "")
                            articles_list = result_data.get("articles", [])
                            count = result_data.get("metadata", {}).get("articles_count", 0)

                            if query_from_result:
                                tool_call_id = getattr(token, "tool_call_id", None)
                                if not tool_call_id:
                                    # Should not happen; ToolMessage should always have tool_call_id.
                                    logger.warning(
                                        "Tool result missing tool_call_id; skipping bubble update"
                                    )
                                    raise AttributeError("Missing tool_call_id on tool result")

                                # Use tool_call_id as the stable bubble id.
                                search_id = str(tool_call_id)

                                # Ensure the bubble exists (tool result may arrive before tool_calls chunk)
                                has_bubble = any(
                                    isinstance(msg, dict)
                                    and msg.get("role") == "assistant"
                                    and (msg.get("metadata") or {}).get("ui_type")
                                    == "search_bubble"
                                    and (msg.get("metadata") or {}).get("search_id") == search_id
                                    for msg in gradio_history
                                )
                                if not has_bubble:
                                    gradio_history.append(
                                        yield_search_bubble(query_from_result, search_id=search_id)
                                    )

                                articles_for_display = (
                                    [
                                        {
                                            "title": a.get("title", "Untitled"),
                                            "url": a.get("url", ""),
                                        }
                                        for a in articles_list
                                    ]
                                    if articles_list
                                    else None
                                )

                                if search_id not in completed_search_ids:
                                    update_search_bubble_by_id(
                                        gradio_history,
                                        search_id,
                                        count=count,
                                        articles=articles_for_display,
                                    )
                                    completed_search_ids.add(search_id)
                                    bubble_updated = True
                                    yield list(gradio_history)
                        except (json.JSONDecodeError, AttributeError) as e:
                            logger.debug("Failed to parse tool result for bubble update: %s", e)

                        # Update accumulated context for next tool call
                        # Agent tracks context, not the tool!
                        _, accumulated_tool_tokens = estimate_accumulated_tokens([], tool_results)
                        agent_context.accumulated_tool_tokens = accumulated_tool_tokens

                        # Update fetched_kb_ids in context (if context exists)
                        if agent_context:
                            try:
                                from kg_engine.tools.utils import parse_tool_result_to_articles

                                articles_list = parse_tool_result_to_articles(token.content)
                                if articles_list:
                                    for article in articles_list:
                                        if article.kb_id:
                                            agent_context.fetched_kb_ids.add(article.kb_id)

                                    logger.debug(
                                        "Updated fetched_kb_ids: %d total articles fetched in this turn",
                                        len(agent_context.fetched_kb_ids),
                                    )
                            except Exception as exc:
                                logger.warning("Failed to update fetched_kb_ids: %s", exc)

                        logger.debug(
                            "Updated accumulated context: conversation=%d, tools=%d (total: %d)",
                            conversation_tokens,
                            accumulated_tool_tokens,
                            conversation_tokens + accumulated_tool_tokens,
                        )

                        # Parse result to check if it's from retrieve_context tool (has articles)
                        from kg_engine.api.stream_helpers import (
                            extract_article_count_from_tool_result,
                            update_message_status_in_history,
                            yield_search_completed,
                        )
                        from kg_engine.tools.utils import parse_tool_result_to_articles

                        # Check if this is a retrieve_context result (has "articles" key)
                        is_search_result = False
                        try:
                            result_json = (
                                json.loads(token.content) if isinstance(token.content, str) else {}
                            )
                            is_search_result = "articles" in result_json
                        except (json.JSONDecodeError, TypeError):
                            pass

                        if is_search_result and not bubble_updated:
                            # This is a retrieve_context result - show search completed with sources
                            # Only emit if bubble wasn't already updated (to avoid duplicates)
                            articles_list = parse_tool_result_to_articles(token.content)
                            articles_count = (
                                len(articles_list)
                                if articles_list
                                else extract_article_count_from_tool_result(token.content)
                            )

                            # Format articles for display (title and URL)
                            articles_for_display = []
                            if articles_list:
                                for article in articles_list:
                                    article_meta = (
                                        article.metadata if hasattr(article, "metadata") else {}
                                    )
                                    title = article_meta.get("title", "Untitled")
                                    url = article_meta.get("url", "")
                                    articles_for_display.append({"title": title, "url": url})

                            search_completed_msg = yield_search_completed(
                                count=articles_count,
                                articles=articles_for_display if articles_for_display else None,
                            )

                            # Update previous pending messages to done (stop spinners)
                            update_message_status_in_history(
                                gradio_history, "search_started", "done"
                            )

                            # Add search completed to history and yield full history
                            gradio_history.append(search_completed_msg)
                            yield list(gradio_history)
                        else:
                            # Non-search tool result (e.g., get_current_datetime): remove initial block, collapse this tool's thinking block
                            logger.debug(
                                "Non-search tool result received, removing initial thinking block and collapsing tool thinking block"
                            )
                            remove_message_by_id(gradio_history, thinking_id)
                            update_message_status_in_history(gradio_history, "thinking", "done")

                        # Stop SGR planning spinner after any tool result
                        update_message_status_in_history(gradio_history, "sgr_planning", "done")

                        # Show generating-answer spinner immediately after search results,
                        # before any expensive compression / next LLM call starts.
                        if is_search_result and not answer:
                            has_generating = any(
                                isinstance(msg, dict)
                                and msg.get("role") == "assistant"
                                and (msg.get("metadata") or {}).get("id") == generating_answer_id
                                for msg in gradio_history
                            )
                            if not has_generating:
                                from kg_engine.api.stream_helpers import yield_generating_answer

                                gradio_history.append(
                                    yield_generating_answer(block_id=generating_answer_id)
                                )
                                yield list(gradio_history)

                        # CRITICAL: Check if accumulated tool results exceed safe threshold
                        # This prevents overflow when agent makes multiple tool calls
                        if settings.llm_fallback_enabled and not selected_model:
                            from kg_engine.config.settings import get_allowed_fallback_models
                            from kg_engine.llm.fallback import select_mid_turn_fallback_model

                            fallback_model = select_mid_turn_fallback_model(
                                current_model,
                                messages,
                                tool_results,
                                get_allowed_fallback_models(),
                            )

                            if fallback_model:
                                from kg_engine.api.stream_helpers import yield_model_switch_notice

                                model_switch_msg = yield_model_switch_notice(fallback_model)
                                # Add model switch notice to history and yield full history
                                gradio_history.append(model_switch_msg)
                                yield list(gradio_history)

                                # Recreate agent with larger model
                                # Note: This is expensive but prevents catastrophic overflow
                                agent = _create_rag_agent(override_model=fallback_model)
                                current_model = fallback_model

                                # Note: Can't restart stream here - agent will continue with new model
                                # for subsequent calls

                        # Skip further processing of tool messages
                        continue

                    # 2. AI messages with tool_calls (when agent decides to call tools)
                    # Check multiple indicators: token.tool_calls, content_blocks, and finish_reason
                    # These should NEVER be displayed - only show metadata
                    has_tool_calls_attr = hasattr(token, "tool_calls") and bool(token.tool_calls)

                    # Check content_blocks for tool_call_chunk (critical for vLLM streaming)
                    token_content_blocks = getattr(token, "content_blocks", None)
                    has_tool_call_chunks = bool(token_content_blocks) and any(
                        block.get("type") == "tool_call_chunk" for block in token_content_blocks
                    )

                    # Check finish_reason (indicates tool calls completed)
                    token_response_metadata = getattr(token, "response_metadata", {})
                    token_finish_reason = (
                        token_response_metadata.get("finish_reason")
                        if isinstance(token_response_metadata, dict)
                        else None
                    )
                    finish_reason_is_tool_calls = token_finish_reason == "tool_calls"

                    # Tool call detected if any of these conditions are true
                    tool_call_detected = (
                        has_tool_calls_attr or has_tool_call_chunks or finish_reason_is_tool_calls
                    )

                    if tool_call_detected:
                        tool_calls_detected_in_stream = True

                        # Create pending search bubbles from stable tool_calls payload (best-effort, no accumulator).
                        # This must NOT depend on `tool_executing` because tool-call chunks can be detected earlier.
                        if has_tool_calls_attr and isinstance(
                            getattr(token, "tool_calls", None), list
                        ):
                            for tc in token.tool_calls:
                                if not isinstance(tc, dict) or tc.get("name") != "retrieve_context":
                                    continue
                                tool_call_id = tc.get("id")
                                if not tool_call_id:
                                    continue
                                tc_args = tc.get("args", {}) or tc.get("arguments", {})
                                if isinstance(tc_args, dict):
                                    query = tc_args.get("query", "") or ""
                                elif isinstance(tc_args, str):
                                    try:
                                        query = (json.loads(tc_args) or {}).get("query", "") or ""
                                    except (json.JSONDecodeError, ValueError):
                                        query = ""
                                else:
                                    query = ""
                                if not query:
                                    continue

                                search_id = str(tool_call_id)

                                has_bubble = any(
                                    isinstance(msg, dict)
                                    and msg.get("role") == "assistant"
                                    and (msg.get("metadata") or {}).get("ui_type")
                                    == "search_bubble"
                                    and (msg.get("metadata") or {}).get("search_id") == search_id
                                    for msg in gradio_history
                                )
                                if not has_bubble:
                                    gradio_history.append(
                                        yield_search_bubble(query, search_id=search_id)
                                    )
                                    remove_message_by_id(gradio_history, thinking_id)
                                    yield list(gradio_history)

                        if not tool_executing:
                            tool_executing = True
                            rctx.inter_tool_text = (
                                ""  # tool boundary; reset reclassification window
                            )
                            # Remove generating_answer block when a new tool call is detected
                            # So the next generating_answer block can appear after this tool completes
                            if has_seen_tool_results:
                                remove_message_by_id(gradio_history, generating_answer_id)
                            # Log which method detected the tool call
                            if has_tool_calls_attr:
                                call_count = (
                                    len(token.tool_calls)
                                    if isinstance(token.tool_calls, list)
                                    else "?"
                                )
                                logger.info(
                                    "Agent calling tool(s) via token.tool_calls: %s call(s)",
                                    call_count,
                                )
                            elif has_tool_call_chunks:
                                logger.info(
                                    "Agent calling tool(s) via content_blocks tool_call_chunk"
                                )
                            elif finish_reason_is_tool_calls:
                                logger.info(
                                    "Agent calling tool(s) detected via finish_reason=tool_calls"
                                )
                                # Check if tool_calls are now available in the token
                                final_tool_calls = getattr(token, "tool_calls", None)
                                if final_tool_calls:
                                    logger.info(
                                        "Final tool_calls after finish_reason: %s call(s)",
                                        len(final_tool_calls)
                                        if isinstance(final_tool_calls, list)
                                        else "?",
                                    )

                            # Get tool name to determine which thinking block to show
                            tool_name = tool_call_accumulator.get_tool_name(token)

                            logger.debug("Tool name detected: %s", tool_name)

                            if tool_name == "retrieve_context":
                                # Search bubbles are created above from token.tool_calls (stable).
                                pass
                            elif tool_name:
                                # Show generic thinking block for non-search tools
                                # Reference agent pattern: always append, don't check duplicates
                                from kg_engine.api.stream_helpers import yield_thinking_block

                                thinking_msg = yield_thinking_block(tool_name)
                                gradio_history.append(thinking_msg)
                                yield list(gradio_history)
                        # Skip displaying the tool call itself and any content
                        continue

                    # 3. Only stream text content from messages WITHOUT tool_calls
                    # This ensures we only show the final answer, not tool reasoning
                    if hasattr(token, "tool_calls") and token.tool_calls:
                        # Skip any message that has tool_calls (redundant check for safety)
                        continue

                    # Process content blocks for final answer text streaming
                    text_chunk_found = False

                    token_content_blocks = getattr(token, "content_blocks", None) or []
                    has_reasoning_in_blocks = any(
                        b.get("type") == "reasoning" for b in token_content_blocks
                    )
                    # Skip akw.reasoning_content when content_blocks has reasoning (avoid double-processing).
                    akw = getattr(token, "additional_kwargs", None) or {}
                    if (
                        reasoning_enabled
                        and not has_reasoning_in_blocks
                        and (reasoning_content := akw.get("reasoning_content"))
                    ):
                        reasoning_delta, reasoning_stream_text = _extract_stream_delta(
                            str(reasoning_content), reasoning_stream_text
                        )
                        if reasoning_delta:
                            rctx.buffer += reasoning_delta
                            (
                                rctx.bubble_id,
                                rctx.bubble_text,
                                reasoning_changed,
                            ) = _upsert_reasoning_bubble(
                                gradio_history,
                                rctx.buffer,
                                rctx.bubble_id,
                                rctx.bubble_text,
                            )
                            if reasoning_changed:
                                yield list(gradio_history)
                        # Do not add reasoning to answer; continue to process content_blocks or token.content

                    if token_content_blocks:
                        for block in token_content_blocks:
                            if block.get("type") == "tool_call_chunk":
                                # Tool call chunk detected - emit metadata if not already done
                                if not tool_executing:
                                    tool_executing = True
                                    # Remove generating_answer block when a new tool call is detected
                                    if has_seen_tool_results:
                                        remove_message_by_id(gradio_history, generating_answer_id)
                                    logger.debug("Agent calling tool via chunk")

                                    # Get tool name to determine which thinking block to show
                                    tool_name = tool_call_accumulator.get_tool_name(token)

                                    if tool_name == "retrieve_context":
                                        tool_query = tool_call_accumulator.process_token(token)
                                        # Create or update search bubble based on query availability
                                        if tool_query:
                                            tool_calls = getattr(token, "tool_calls", None) or []
                                            if isinstance(tool_calls, list):
                                                for tc in tool_calls:
                                                    if (
                                                        not isinstance(tc, dict)
                                                        or tc.get("name") != "retrieve_context"
                                                    ):
                                                        continue
                                                    tool_call_id = tc.get("id")
                                                    if not tool_call_id:
                                                        continue
                                                    search_id = str(tool_call_id)

                                                    has_bubble = any(
                                                        isinstance(msg, dict)
                                                        and msg.get("role") == "assistant"
                                                        and (msg.get("metadata") or {}).get(
                                                            "ui_type"
                                                        )
                                                        == "search_bubble"
                                                        and (msg.get("metadata") or {}).get(
                                                            "search_id"
                                                        )
                                                        == search_id
                                                        for msg in gradio_history
                                                    )
                                                    if not has_bubble:
                                                        gradio_history.append(
                                                            yield_search_bubble(
                                                                tool_query, search_id=search_id
                                                            )
                                                        )
                                                        yield list(gradio_history)
                                # Skip displaying the tool call itself and any content
                                continue

                            elif block.get("type") == "reasoning" and reasoning_enabled:
                                has_seen_content_blocks_reasoning = True
                                reasoning_text = str(
                                    block.get("reasoning") or block.get("text") or ""
                                )
                                # Strip Harmony channel label that may leak into reasoning blocks.
                                if not rctx.buffer and reasoning_text.lstrip().startswith(
                                    "analysis"
                                ):
                                    reasoning_text = reasoning_text.lstrip().removeprefix(
                                        "analysis"
                                    )
                                if reasoning_text:
                                    reasoning_delta, reasoning_stream_text = _extract_stream_delta(
                                        reasoning_text, reasoning_stream_text
                                    )
                                    if reasoning_delta:
                                        rctx.buffer += reasoning_delta

                                    (
                                        rctx.bubble_id,
                                        rctx.bubble_text,
                                        reasoning_changed,
                                    ) = _upsert_reasoning_bubble(
                                        gradio_history,
                                        rctx.buffer,
                                        rctx.bubble_id,
                                        rctx.bubble_text,
                                    )
                                    if reasoning_changed:
                                        yield list(gradio_history)

                                # Prevent fallback token.content path from re-processing.
                                text_chunk_found = True
                                # Do not stream reasoning as part of the main answer.
                                continue

                            elif block.get("type") == "text" and block.get("text"):
                                # Only stream text if we're not currently executing tools
                                # This prevents streaming the agent's "reasoning" about tool calls
                                if not tool_executing:
                                    # We handled text via content_blocks, skip fallback token.content.
                                    text_chunk_found = True
                                    raw_text_chunk = str(block["text"])
                                    text_chunk, content_stream_text = _extract_stream_delta(
                                        raw_text_chunk, content_stream_text
                                    )
                                    if not text_chunk:
                                        continue
                                    strip_only = (
                                        has_seen_content_blocks_reasoning or has_reasoning_in_blocks
                                    )
                                    # content_blocks reasoning may end with `<think>`; next chunk is continuation
                                    if strip_only and rctx.buffer.rstrip().endswith(_THINK_OPEN):
                                        rctx.in_block = True
                                    frames, text_chunk, should_skip = await _apply_reasoning_chunk(
                                        text_chunk,
                                        rctx,
                                        answer,
                                        has_seen_tool_results,
                                        reasoning_enabled,
                                        harmony_parser,
                                        gradio_history,
                                        harmony_strip_only=strip_only,
                                    )
                                    for _frame in frames:
                                        yield _frame
                                    if should_skip:
                                        continue

                                    # First answer chunk: finalize bubble, disclaimer, spinners.
                                    if not answer:
                                        rctx.bubble_id = _finalize_reasoning_bubble(
                                            gradio_history,
                                            rctx.bubble_id,
                                            rctx.buffer,
                                        )
                                        if (
                                            not disclaimer_prepended
                                            and not _disclaimer_injected_in_history(gradio_history)
                                        ):
                                            from kg_engine.api.stream_helpers import (
                                                yield_disclaimer_display,
                                            )

                                            gradio_history.append(yield_disclaimer_display())
                                            disclaimer_prepended = True
                                            yield list(gradio_history)
                                        remove_message_by_id(gradio_history, thinking_id)
                                        update_message_status_in_history(
                                            gradio_history, "search_started", "done"
                                        )
                                        update_message_status_in_history(
                                            gradio_history, "sgr_planning", "done"
                                        )
                                        if has_seen_tool_results and not _has_generating_spinner(
                                            gradio_history, generating_answer_id
                                        ):
                                            from kg_engine.api.stream_helpers import (
                                                yield_generating_answer,
                                            )

                                            gradio_history.append(
                                                yield_generating_answer(
                                                    block_id=generating_answer_id
                                                )
                                            )
                                            yield list(gradio_history)

                                    if _needs_separator:
                                        text_chunk = "\n" + text_chunk
                                        _needs_separator = False

                                    prev_answer_len = len(answer)
                                    answer, disclaimer_prepended = (
                                        _process_text_chunk_for_streaming(
                                            text_chunk,
                                            answer,
                                            disclaimer_prepended,
                                            has_seen_tool_results,
                                        )
                                    )
                                    rctx.inter_tool_text += answer[prev_answer_len:]
                                    _update_or_append_assistant_message(gradio_history, answer)
                                    yield list(gradio_history)

                    # Fallback: If no text found in content_blocks, check token.content directly
                    # This handles vLLM and other providers that provide text directly in token.content
                    # LangChain streaming provides incremental chunks (tested and confirmed)
                    if not text_chunk_found and is_ai_message and not tool_executing:
                        token_content = str(getattr(token, "content", ""))
                        if token_content:
                            token_content, content_stream_text = _extract_stream_delta(
                                token_content, content_stream_text
                            )
                            if not token_content:
                                continue

                            strip_only = (
                                has_seen_content_blocks_reasoning or has_reasoning_in_blocks
                            )
                            if strip_only and rctx.buffer.rstrip().endswith(_THINK_OPEN):
                                rctx.in_block = True
                            frames, token_content, should_skip = await _apply_reasoning_chunk(
                                token_content,
                                rctx,
                                answer,
                                has_seen_tool_results,
                                reasoning_enabled,
                                harmony_parser,
                                gradio_history,
                                harmony_strip_only=strip_only,
                            )
                            for _frame in frames:
                                yield _frame
                            if should_skip or not token_content:
                                continue

                            # First answer chunk: remove spinner, finalize bubble, disclaimer.
                            if not answer:
                                if has_seen_tool_results:
                                    remove_message_by_id(gradio_history, generating_answer_id)
                                rctx.bubble_id = _finalize_reasoning_bubble(
                                    gradio_history,
                                    rctx.bubble_id,
                                    rctx.buffer,
                                )
                                if not disclaimer_prepended and not _disclaimer_injected_in_history(
                                    gradio_history
                                ):
                                    from kg_engine.api.stream_helpers import (
                                        yield_disclaimer_display,
                                    )

                                    gradio_history.append(yield_disclaimer_display())
                                    disclaimer_prepended = True
                                    yield list(gradio_history)
                                if has_seen_tool_results and not _has_generating_spinner(
                                    gradio_history, generating_answer_id
                                ):
                                    from kg_engine.api.stream_helpers import (
                                        yield_generating_answer,
                                    )

                                    gradio_history.append(
                                        yield_generating_answer(block_id=generating_answer_id)
                                    )
                                    yield list(gradio_history)

                            if _needs_separator:
                                token_content = "\n" + token_content
                                _needs_separator = False

                            prev_answer_len = len(answer)
                            answer, disclaimer_prepended = _process_text_chunk_for_streaming(
                                token_content, answer, disclaimer_prepended, has_seen_tool_results
                            )
                            rctx.inter_tool_text += answer[prev_answer_len:]
                            _update_or_append_assistant_message(gradio_history, answer)
                            incomplete_response = answer
                            final_response = answer
                            yield list(gradio_history)

                # Handle "updates" mode for agent state updates
                elif stream_mode == "updates":
                    # We can log updates but don't need to yield them
                    logger.debug(
                        "Agent update: %s", list(chunk.keys()) if isinstance(chunk, dict) else chunk
                    )

            # After stream completes, check if we expected tool calls but didn't get results
            # Only check for vLLM on first message (when we expect tool calls)
            should_fallback, fallback_enabled = check_stream_completion(
                is_vllm=is_vllm,
                has_seen_tool_results=has_seen_tool_results,
                tool_calls_detected=tool_calls_detected_in_stream,
                tool_results_count=len(tool_results),
                stream_chunk_count=stream_chunk_count,
            )

        except OpenAIAPIError as api_error:
            # Handle OpenAI API errors (e.g., malformed streaming response)
            error_msg = str(api_error).lower()
            is_streaming_error = "list index out of range" in error_msg or "streaming" in error_msg

            if is_streaming_error:
                # If streaming fails, try falling back to invoke() mode
                # This can happen with any OpenAI-compatible provider, not just vLLM
                # Only fallback if we haven't seen tool results yet (first turn)
                if not has_seen_tool_results:
                    logger.warning(
                        "OpenAI API streaming error, falling back to invoke() mode: %s", api_error
                    )
                    fallback_to_invoke = True
                else:
                    # If we've already seen tool results, streaming error might be in the answer phase
                    # Re-raise to be handled by outer exception handler
                    logger.error(
                        "OpenAI API error during streaming (after tool execution): %s",
                        api_error,
                        exc_info=True,
                    )
                    raise
            else:
                # For other API errors, re-raise to be handled by outer exception handler
                logger.error("OpenAI API error: %s", api_error, exc_info=True)
                raise
        except Exception as stream_error:
            # If streaming fails and we expected tool calls, fall back to invoke()
            # Only if fallback is enabled
            if should_use_fallback(
                is_vllm=is_vllm,
                has_seen_tool_results=has_seen_tool_results,
                tool_calls_detected=False,
                tool_results_count=len(tool_results),
            ):
                logger.warning(
                    "Streaming failed for vLLM, falling back to invoke() mode: %s", stream_error
                )
                fallback_to_invoke = True
            else:
                raise

            # Fallback to invoke() only if we expected tool calls but didn't get them
            # This ensures tool execution happens even if streaming detection fails
            # Can be disabled via vllm_streaming_fallback_enabled setting for testing
            if fallback_to_invoke or should_fallback:
                # Show "Generating answer" spinner for invoke() fallback (non-streaming)
                # This is especially important since invoke() has no streaming feedback
                if has_seen_tool_results and not answer:
                    from kg_engine.api.stream_helpers import (
                        update_message_status_in_history,
                        yield_generating_answer,
                    )

                    # Stop SGR planning spinner when starting to generate answer
                    update_message_status_in_history(gradio_history, "sgr_planning", "done")
                    generating_msg = yield_generating_answer(block_id=generating_answer_id)
                    gradio_history.append(generating_msg)
                    yield list(gradio_history)

                # Execute fallback and process results
                fallback_results = {}
                for chunk in execute_fallback_invoke(
                    agent=agent,
                    messages=messages,
                    agent_context=agent_context,
                    has_seen_tool_results=has_seen_tool_results,
                    result_container=fallback_results,
                ):
                    # Handle metadata (dict) or text chunks (str) and add to history
                    if isinstance(chunk, dict):
                        # Metadata message (search_started, search_completed, etc.)
                        gradio_history.append(chunk)
                        yield list(gradio_history)
                    elif isinstance(chunk, str):
                        chunk, rctx.buffer, rctx.in_block, _ = _parse_think_tags(
                            chunk,
                            rctx.buffer,
                            rctx.in_block,
                        )
                        if reasoning_enabled and rctx.buffer:
                            (
                                rctx.bubble_id,
                                rctx.bubble_text,
                                reasoning_changed,
                            ) = _upsert_reasoning_bubble(
                                gradio_history,
                                rctx.buffer,
                                rctx.bubble_id,
                                rctx.bubble_text,
                            )
                            if reasoning_changed:
                                yield list(gradio_history)
                        if not chunk:
                            continue
                        # Text chunk - remove generating_answer block on first chunk
                        if not answer and has_seen_tool_results:
                            remove_message_by_id(gradio_history, generating_answer_id)
                        # Update last message or create new one
                        _update_or_append_assistant_message(gradio_history, chunk)
                        yield list(gradio_history)

            # Extract results from container
            if fallback_results:
                fallback_tool_results = fallback_results.get("tool_results", [])
                fallback_answer = fallback_results.get("final_answer", "")
                fallback_disclaimer = fallback_results.get("disclaimer_prepended", False)

                # Update tool results
                if fallback_tool_results:
                    tool_results.extend(fallback_tool_results)
                    has_seen_tool_results = True
                    # Update accumulated context
                    _, accumulated_tool_tokens = estimate_accumulated_tokens([], tool_results)
                    agent_context.accumulated_tool_tokens = accumulated_tool_tokens

                # Update answer if we got one from fallback
                if fallback_answer:
                    answer = fallback_answer
                    disclaimer_prepended = fallback_disclaimer or disclaimer_prepended

        # Check if we were cancelled during streaming
        if is_cancelled():
            logger.info("Stream cancelled by user - saving incomplete response and returning")
            rctx.close()
            if incomplete_response and session_id:
                llm_manager.save_assistant_turn(session_id, incomplete_response)
                logger.info(
                    f"Saved INCOMPLETE response to memory ({len(incomplete_response)} chars)"
                )
            yield list(gradio_history)
            try:
                agent_context.final_answer = incomplete_response or ""
                cancelled_diagnostics: dict[str, Any] = {
                    "model": current_model,
                    "cancelled": True,
                    "tool_results_count": len(tool_results),
                }
                if getattr(settings, "llm_reasoning_enabled", False) and rctx.buffer.strip():
                    cancelled_diagnostics["reasoning"] = rctx.buffer.strip()
                agent_context.diagnostics = cancelled_diagnostics
            except Exception:
                pass
            yield agent_context
            return

        # Accumulate articles from tool results and add citations
        logger.info(
            "Stream completed: %d chunks processed, %d tool results",
            stream_chunk_count,
            len(tool_results),
        )
        from kg_engine.tools import accumulate_articles_from_tool_results

        articles = accumulate_articles_from_tool_results(tool_results)

        # Inject disclaimer as separate message if it wasn't added during streaming
        if (
            not disclaimer_prepended
            and not _disclaimer_injected_in_history(gradio_history)
            and answer
        ):
            from kg_engine.api.stream_helpers import yield_disclaimer_display

            gradio_history.append(yield_disclaimer_display())
            disclaimer_prepended = True
            logger.info("Injected disclaimer message (was missing from stream)")

        # Set final text - sources will be added later at the end of the answer
        final_text = answer
        if not articles:
            logger.info("Agent completed with no retrieved articles")
        else:
            logger.info("Agent completed with %d articles", len(articles))

        # Only update/append if we have actual content (don't overwrite with empty)
        # If answer is empty, the agent didn't produce any text - don't create empty message
        if final_text and final_text.strip():
            # Update last message (answer) with final formatted text and yield full history
            _update_or_append_assistant_message(gradio_history, final_text)
        elif not final_text or not final_text.strip():
            # Empty answer - log warning but don't create empty message
            logger.warning("Agent completed with empty answer - no text content was produced")

        # Update final response tracking
        final_response = final_text

        # Save conversation turn (reuse existing pattern)
        # Streaming completed successfully - save complete response to memory
        if final_response and session_id:
            llm_manager.save_assistant_turn(session_id, final_response)
            logger.info(f"Saved complete response to memory ({len(final_response)} chars)")

        # Remove transient blocks and mark pending spinners done before final yield
        from kg_engine.api.stream_helpers import (
            update_message_status_in_history,
        )

        remove_message_by_id(gradio_history, thinking_id)
        remove_message_by_id(gradio_history, generating_answer_id)
        # Defensive: remove any duplicate generating_answer blocks (shouldn't happen, but avoids UI hang).
        for i in range(len(gradio_history) - 1, -1, -1):
            msg = gradio_history[i]
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            md = msg.get("metadata")
            if isinstance(md, dict) and md.get("ui_type") == "generating_answer":
                del gradio_history[i]
        update_message_status_in_history(gradio_history, "search_started", "done")
        # Note: sgr_planning is marked done by SGR section itself, don't mark here
        logger.info("Marked search spinner as done")

        # Flush any remaining Harmony buffer content held back for partial-marker safety.
        if harmony_parser:
            h_reasoning, h_final = harmony_parser.flush()
            if h_reasoning and not has_seen_content_blocks_reasoning:
                rctx.buffer += h_reasoning
            if h_final:
                answer += h_final
                _update_or_append_assistant_message(gradio_history, answer)

        # === Reasoning bubble (optional, UI-only) ===
        if getattr(settings, "llm_reasoning_enabled", False) and rctx.buffer.strip():
            try:
                rctx.bubble_id = _finalize_reasoning_bubble(
                    gradio_history,
                    rctx.bubble_id,
                    rctx.buffer,
                )
                logger.info("Finalized reasoning bubble (length=%d)", len(rctx.buffer.strip()))
            except Exception:
                logger.warning("Failed to inject reasoning bubble", exc_info=True)

        # Preserve reasoning_content on final assistant message for next-turn round-trip.
        # This ensures the model sees its own prior reasoning in subsequent LLM calls.
        if reasoning_enabled and rctx.buffer.strip():
            _preserve_reasoning_on_last_assistant(gradio_history, rctx.buffer)

        # ========== SRP (Support Resolution Plan) - if enabled ==========
        resolution_plan = None
        resolution_markdown = ""
        srp_enabled = getattr(settings, "srp_enabled", False) and not skip_srp
        logger.info("SRP check: srp_enabled=%s skip_srp=%s", bool(srp_enabled), skip_srp)
        if srp_enabled:
            from kg_engine.api.stream_helpers import (
                remove_message_by_ui_type,
                update_message_status_in_history,
                yield_srp_planning_started,
            )
            from kg_engine.llm.prompts import get_dynamic_context, get_system_prompt

            try:
                # Show SRP planning bubble
                gradio_history.append(yield_srp_planning_started())
                yield list(gradio_history)

                # Build messages from updated gradio_history (includes final answer)
                srp_messages = _build_agent_messages_from_gradio_history(gradio_history)

                # Build ephemeral SRP context (not stored in history)
                srp_context = get_dynamic_context(include_srp=True)
                if articles:
                    srp_context += format_sources_list(articles) + "\n\n"

                srp_analysis_request = {
                    "role": "user",
                    "content": srp_context,
                }
                srp_messages.append(srp_analysis_request)

                # Use static system prompt (cacheable)
                srp_messages = [{"role": "system", "content": get_system_prompt()}] + srp_messages

                # Initialize LLM
                srp_llm = LLMManager(
                    provider=settings.default_llm_provider,
                    model=current_model or settings.default_model,
                    temperature=settings.llm_temperature,
                )._chat_model()

                # Use bind_tools + tool_choice for forced tool execution
                from kg_engine.llm.model_configs import MODEL_CONFIGS
                from kg_engine.tools.generate_resolution_plan import generate_resolution_plan

                srp_model = current_model or settings.default_model
                srp_cfg = MODEL_CONFIGS.get(srp_model, {})
                srp_supports_forced = srp_cfg.get("supports_forced_tool_choice", True)
                srp_tool_choice = "generate_resolution_plan" if srp_supports_forced else "auto"
                srp_llm_forced = srp_llm.bind_tools(
                    [generate_resolution_plan], tool_choice=srp_tool_choice
                )
                logger.info("Calling SRP LLM...")
                response = await srp_llm_forced.ainvoke(srp_messages)
                logger.info("SRP LLM returned: %s", type(response))

                if response.tool_calls:
                    tool_call = response.tool_calls[0]
                    # Execute tool - validates args via Pydantic and returns both json + markdown
                    result = await generate_resolution_plan.ainvoke(tool_call["args"])
                    resolution_plan = result["json"]
                    resolution_markdown = result["markdown"]
                    agent_context.resolution_plan = resolution_plan
                    logger.info(
                        "SRP plan generated: engineer_intervention_needed=%s",
                        resolution_plan.get("engineer_intervention_needed"),
                    )
                else:
                    logger.warning("SRP LLM did not make tool call")

                # Hide and remove SRP bubble after completion
                update_message_status_in_history(gradio_history, "srp_planning", "done")
                remove_message_by_ui_type(gradio_history, "srp_planning")
                yield list(gradio_history)

            except Exception as exc:
                logger.error("SRP tool failed: %s", exc)
                agent_context.resolution_plan_error = str(exc)
                update_message_status_in_history(gradio_history, "srp_planning", "done")
                remove_message_by_ui_type(gradio_history, "srp_planning")
                yield list(gradio_history)

        # ========== Render Plan Section ==========
        plan_section = ""
        srp_always = getattr(settings, "srp_always_render_plan", False)
        if srp_always:
            show_plan = bool(resolution_markdown)
        else:
            show_plan = bool(
                resolution_plan
                and resolution_plan.get("engineer_intervention_needed", False)
                and resolution_markdown
            )
        if show_plan:
            plan_section = "\n\n---\n\n" + resolution_markdown
            logger.info("Plan section rendered")

        # ========== Assemble Final Message ==========
        # Structure: Answer + [Plan] + [Sources at end]
        # Always add sources at the end (regardless of plan presence)
        complete_content = f"\n{final_text}{plan_section}"
        if articles:
            complete_content += format_sources_list(articles)
        # Update the answer in gradio_history
        _update_or_append_assistant_message(gradio_history, complete_content)
        # Update final_response and final_text for consistency
        final_response = complete_content
        final_text = complete_content
        logger.info("Assembled final message with plan and sources")

        # Log final history state for debugging
        logger.info(
            "Final history yield: total_messages=%d (user=%d, assistant=%d, ui_metadata=%d)",
            len(gradio_history),
            sum(1 for msg in gradio_history if isinstance(msg, dict) and msg.get("role") == "user"),
            sum(
                1
                for msg in gradio_history
                if isinstance(msg, dict)
                and msg.get("role") == "assistant"
                and not msg.get("metadata")
            ),
            sum(1 for msg in gradio_history if isinstance(msg, dict) and msg.get("metadata")),
        )

        yield list(gradio_history)

        # Populate AgentContext for structured output / UI metadata, then yield it.
        # Ensure sgr_plan is set if it was created during SGR planning
        if sgr_plan_dict and not getattr(agent_context, "sgr_plan", None):
            agent_context.sgr_plan = sgr_plan_dict
            logger.info(
                "agent_chat_handler: restored sgr_plan_dict to agent_context before yielding"
            )
        try:
            agent_context.final_answer = final_text or ""
            agent_context.final_articles = (
                [_article_to_dict(a) for a in articles] if articles else []
            )
            agent_context.executed_queries = _extract_executed_queries(tool_results)
            if articles:
                scores = [(a.kb_id, (a.metadata or {}).get("rerank_score")) for a in articles[:5]]
                logger.debug(
                    f"agent_chat_handler: sample rerank_scores from final_articles: {scores}"
                )
            # Preserve diagnostics and include optional reasoning trace if present.
            diagnostics: dict[str, Any] = {
                "model": current_model,
                "stream_chunks": stream_chunk_count,
                "tool_results_count": len(tool_results),
                "conversation_tokens": agent_context.conversation_tokens,
                "accumulated_tool_tokens": agent_context.accumulated_tool_tokens,
                "guard": guard_debug_info,
                "session_id": session_id,
            }
            if getattr(settings, "llm_reasoning_enabled", False) and rctx.buffer.strip():
                diagnostics["reasoning"] = rctx.buffer.strip()
            agent_context.diagnostics = diagnostics
            _set_turn_timing_and_model(agent_context, turn_start, current_model)
            logger.info(
                f"agent_chat_handler: yielding AgentContext - "
                f"sgr_plan_present={agent_context.sgr_plan is not None}, "
                f"sgr_plan_dict_present={sgr_plan_dict is not None}, "
                f"query_traces_count={len(agent_context.query_traces)}, "
                f"final_articles_count={len(agent_context.final_articles)}"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to populate AgentContext final fields: %s", exc)

        rctx.close()
        yield agent_context
        return

    except GeneratorExit:
        rctx.close()
        # Stream was cancelled - save incomplete response to memory if available (pattern from test script)
        logger.info("Stream cancelled (GeneratorExit) - saving incomplete response")
        if incomplete_response and session_id:
            llm_manager.save_assistant_turn(session_id, incomplete_response)
            logger.info(
                f"Saved INCOMPLETE response to memory: {incomplete_response[:50]}... ({len(incomplete_response)} chars)"
            )
        raise  # Re-raise to allow Gradio to handle cancellation properly

    except Exception as e:
        rctx.close()
        logger.error("Error in agent_chat_handler: %s", e, exc_info=True)
        # Variables are initialized at function start, so they should always exist
        # Handle context-length overflow gracefully by switching to a larger model (once)
        err_text = str(e).lower()
        is_context_overflow = (
            "maximum context length" in err_text
            or "context length" in err_text
            or "token limit" in err_text
            or "too many tokens" in err_text
        )

        if settings.llm_fallback_enabled and is_context_overflow and messages:
            try:  # Single-shot fallback retry
                # Estimate required tokens and pick a capable fallback model
                # Get current model context window for adaptive overhead calculation
                from kg_engine.llm.model_configs import MODEL_CONFIGS

                current_model_config = MODEL_CONFIGS.get(current_model)
                if not current_model_config:
                    for key in MODEL_CONFIGS:
                        if key != "default" and key in current_model:
                            current_model_config = MODEL_CONFIGS[key]
                            break
                if not current_model_config:
                    current_model_config = MODEL_CONFIGS["default"]
                current_window = int(current_model_config.get("token_limit", 0))

                required_tokens = estimate_accumulated_context(
                    messages,
                    tool_results,
                    context_window=current_window,
                )
                fallback_model = _find_model_for_tokens(required_tokens) or None

                if fallback_model and fallback_model != current_model:
                    logger.warning(
                        "Retrying with fallback model due to context overflow: %s -> %s (required≈%d)",
                        current_model,
                        fallback_model,
                        required_tokens,
                    )

                    # Inform UI about the switch
                    from kg_engine.api.stream_helpers import yield_model_switch_notice

                    model_switch_msg = yield_model_switch_notice(fallback_model)
                    # Add model switch notice to history and yield full history
                    gradio_history.append(model_switch_msg)
                    yield list(gradio_history)

                    # Recreate agent and re-run the stream once
                    agent = _create_rag_agent(override_model=fallback_model)
                    current_model = fallback_model

                    conversation_tokens, _ = estimate_accumulated_tokens(messages, [])
                    agent_context = AgentContext(
                        conversation_tokens=conversation_tokens,
                        accumulated_tool_tokens=0,
                    )

                    answer = ""
                    tool_results = []
                    has_seen_tool_results = False
                    disclaimer_prepended = False  # Track if disclaimer has been prepended to stream

                    async for stream_mode, chunk in agent.astream(
                        {"messages": messages},
                        context=agent_context,
                        stream_mode=["updates", "messages"],
                    ):
                        if stream_mode == "messages":
                            token, metadata = chunk
                            # Collect tool results silently; only stream final text
                            if hasattr(token, "type") and token.type == "tool":
                                tool_results.append(token.content)
                                has_seen_tool_results = True
                                rctx.inter_tool_text = (
                                    ""  # new inter-tool phase; reset reclassification window
                                )
                                # keep agent_context.accumulated_tool_tokens updated
                                _, acc_tool_toks = estimate_accumulated_tokens([], tool_results)
                                agent_context.accumulated_tool_tokens = acc_tool_toks

                                # Show generating answer spinner after tool results in fallback retry
                                if not answer:
                                    from kg_engine.api.stream_helpers import (
                                        update_message_status_in_history,
                                        yield_generating_answer,
                                    )

                                    # Stop SGR planning spinner when starting to generate answer
                                    update_message_status_in_history(
                                        gradio_history, "sgr_planning", "done"
                                    )
                                    generating_msg = yield_generating_answer(
                                        block_id=generating_answer_id
                                    )
                                    gradio_history.append(generating_msg)
                                    yield list(gradio_history)
                                continue

                            if hasattr(token, "tool_calls") and token.tool_calls:
                                # Do not stream tool call reasoning
                                continue

                            if hasattr(token, "content_blocks") and token.content_blocks:
                                for block in token.content_blocks:
                                    if block.get("type") == "text" and block.get("text"):
                                        text_chunk = str(block["text"])
                                        text_chunk, rctx.buffer, rctx.in_block, _ = (
                                            _parse_think_tags(
                                                text_chunk,
                                                rctx.buffer,
                                                rctx.in_block,
                                            )
                                        )
                                        if reasoning_enabled and rctx.buffer:
                                            (
                                                rctx.bubble_id,
                                                rctx.bubble_text,
                                                reasoning_changed,
                                            ) = _upsert_reasoning_bubble(
                                                gradio_history,
                                                rctx.buffer,
                                                rctx.bubble_id,
                                                rctx.bubble_text,
                                            )
                                            if reasoning_changed:
                                                yield list(gradio_history)
                                        if not text_chunk:
                                            continue

                                        # Remove generating_answer block on first text chunk
                                        if not answer and has_seen_tool_results:
                                            remove_message_by_id(
                                                gradio_history, generating_answer_id
                                            )

                                        answer, disclaimer_prepended = (
                                            _process_text_chunk_for_streaming(
                                                text_chunk,
                                                answer,
                                                disclaimer_prepended,
                                                has_seen_tool_results,
                                            )
                                        )
                                        # Update last message (answer) in history and yield full history
                                        _update_or_append_assistant_message(gradio_history, answer)
                                        # Track incomplete response for memory saving if cancelled (pattern from test script)
                                        incomplete_response = answer
                                        final_response = (
                                            answer  # Update final response as we stream
                                        )
                                        yield list(gradio_history)
                        elif stream_mode == "updates":
                            # No-op for UI
                            pass

                    # Inject disclaimer as separate message if it wasn't added during streaming
                    if (
                        not disclaimer_prepended
                        and not _disclaimer_injected_in_history(gradio_history)
                        and answer
                    ):
                        from kg_engine.api.stream_helpers import yield_disclaimer_display

                        gradio_history.append(yield_disclaimer_display())
                        disclaimer_prepended = True
                        logger.info(
                            "Injected disclaimer message (fallback retry, was missing from stream)"
                        )

                    from kg_engine.tools import accumulate_articles_from_tool_results

                    articles = accumulate_articles_from_tool_results(tool_results)
                    if not articles:
                        final_text = answer
                    else:
                        final_text = format_with_citations(answer, articles)

                    # Only update/append if we have actual content (don't overwrite with empty)
                    if final_text and final_text.strip():
                        # Update last message with final formatted text
                        _update_or_append_assistant_message(gradio_history, final_text)
                    elif not final_text or not final_text.strip():
                        # Empty answer - log warning but don't create empty message
                        logger.warning(
                            "Fallback agent completed with empty answer - no text content was produced"
                        )

                    # Update final response tracking
                    final_response = final_text

                    # Save conversation turn
                    if final_response and session_id:
                        llm_manager.save_assistant_turn(session_id, final_response)
                        logger.info(
                            f"Saved complete response to memory ({len(final_response)} chars)"
                        )
                    yield list(gradio_history)
                    # Yield AgentContext so metadata UI can update after fallback retry.
                    try:
                        agent_context.final_answer = final_text or ""
                        agent_context.final_articles = (
                            [_article_to_dict(a) for a in articles] if articles else []
                        )
                        agent_context.executed_queries = _extract_executed_queries(
                            fallback_tool_results
                        )
                        agent_context.diagnostics = {
                            "model": current_model,
                            "fallback_retry": True,
                            "tool_results_count": len(tool_results),
                            "guard": guard_debug_info,
                        }
                        if sgr_plan_dict and not getattr(agent_context, "sgr_plan", None):
                            agent_context.sgr_plan = sgr_plan_dict
                    except Exception:
                        pass
                    _set_turn_timing_and_model(agent_context, turn_start, current_model)
                    yield agent_context
                    return
            except Exception as retry_exc:  # If fallback retry fails, emit original-style error
                logger.error("Fallback retry failed: %s", retry_exc, exc_info=True)

        # Default error path - add error message to history
        error_msg = f"Извините, произошла ошибка / Sorry, an error occurred: {str(e)}"
        # gradio_history should always exist (initialized early), but ensure it's not empty
        if not gradio_history:
            # Add user message if we have it
            if message:
                gradio_history.append({"role": "user", "content": message})

        _update_or_append_assistant_message(gradio_history, error_msg)

        # Remove transient blocks and mark pending spinners done before yielding error
        from kg_engine.api.stream_helpers import update_message_status_in_history

        remove_message_by_id(gradio_history, thinking_id)
        remove_message_by_id(gradio_history, generating_answer_id)
        for i in range(len(gradio_history) - 1, -1, -1):
            msg = gradio_history[i]
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            md = msg.get("metadata")
            if isinstance(md, dict) and md.get("ui_type") == "generating_answer":
                del gradio_history[i]
        update_message_status_in_history(gradio_history, "search_started", "done")
        update_message_status_in_history(gradio_history, "sgr_planning", "done")

        yield list(gradio_history)

        # Always yield a final AgentContext so `chat_with_metadata` can update UI panels.
        if agent_context is None:
            agent_context = AgentContext(conversation_tokens=0, accumulated_tool_tokens=0)
        if sgr_plan_dict and not getattr(agent_context, "sgr_plan", None):
            agent_context.sgr_plan = sgr_plan_dict
        try:
            agent_context.final_answer = error_msg
            agent_context.final_articles = []
            agent_context.diagnostics = {
                "model": current_model,
                "error": str(e),
                "guard": guard_debug_info,
            }
        except Exception:
            pass
        yield agent_context


def query_rag(question: str, provider: str = "gemini", top_k: int = 5) -> str:
    if not question or not question.strip():
        return "Error: Empty question"
    docs = retriever.retrieve(question, top_k=top_k)
    # If no documents found, inject a message into the context
    has_no_results_doc = False
    if not docs:
        from kg_engine.retrieval.retriever import Article

        no_results_msg = (
            "К сожалению, не найдено релевантных материалов / No relevant results found."
        )
        no_results_doc = Article(
            kb_id="",
            content=no_results_msg,
            metadata={"title": "No Results", "kbId": "", "_is_no_results": True},
        )
        docs = [no_results_doc]
        has_no_results_doc = True

    answer = llm_manager.generate(question, docs, provider=provider)
    # If we injected the "no results" message, don't add citations
    if has_no_results_doc:
        return answer  # Don't add citations for "no results" message
    return format_with_citations(answer, docs)


# Configure chatbot height and UI elements based on embedded widget setting
if settings.gradio_embedded_widget:
    # For embedded widget
    chatbot_height = "400px"
    chatbot_max_height = "65vh"
    chat_title = None
else:
    # For standalone app
    chatbot_height = "70vh"  # 70% of viewport height for standalone
    chatbot_max_height = "70vh"  # Same as height for consistency
    chat_title = "Ассистент инженера поддержки"

# Force agent-based handler; legacy direct handler removed.
# handler_fn is assigned after chat_with_metadata is defined (below).

# Load CSS theme from reference agent
css_file_path = Path(__file__).parent.parent / "resources" / "css" / "cmw_copilot_theme.css"

# Setup Gradio static resource paths (for logo and other assets)
# Must use absolute path for GRADIO_ALLOWED_PATHS
RESOURCES_DIR = (Path(__file__).parent.parent / "resources").resolve()
try:
    existing_allowed = os.environ.get("GRADIO_ALLOWED_PATHS", "")
    parts = [p for p in existing_allowed.split(os.pathsep) if p]
    resources_dir_str = str(RESOURCES_DIR)
    if resources_dir_str not in parts:
        parts.append(resources_dir_str)
    os.environ["GRADIO_ALLOWED_PATHS"] = os.pathsep.join(parts)
    logger.info(f"Gradio static allowed paths: {os.environ['GRADIO_ALLOWED_PATHS']}")
except Exception as e:
    logger.warning(f"Could not set GRADIO_ALLOWED_PATHS: {e}")


# Wrapper function to expose retrieve_context tool as API endpoint
# The tool is a StructuredTool, so we need to extract the underlying function
def get_knowledge_base_articles(
    query: str | None = None,
    top_k: int | str | None = None,
    exclude_kb_ids: list[str] | None = None,
    product_version: str | None = None,
    kb_ids: list[str] | None = None,
) -> str:
    """Search and retrieve documentation articles from the Comindware Platform knowledge base.

    Use this tool when you need raw search results with article metadata. For intelligent
    answers with automatic context retrieval, use agent_chat_handler instead.

    Two modes:
    1. Semantic search: provide `query`, optionally `top_k`, `exclude_kb_ids`.
    2. Direct fetch: provide `kb_ids` to fetch full articles by their IDs.

    Args:
        query: Search query or question to find relevant documentation articles.
        top_k: Optional limit on number of articles to return.
        exclude_kb_ids: Optional list of kb_ids to exclude from results.
        product_version: Product version to search. Use 'v5' for version 5.0 (released 2025),
            'v6' for version 6.0 (current, released 2026). Always specify for accurate,
            version-specific results. Defaults to 'v6' when not provided.
        kb_ids: Optional list of article kb_ids to fetch directly (bypasses semantic search).

    Returns:
        JSON string containing structured article data.
    """
    import asyncio

    from kg_engine.tools.retrieve_context import (
        _fetch_articles_by_kb_ids_core,
    )

    effective_product_version = product_version or "v6"

    # Direct kbId fetch path
    if kb_ids:
        if effective_product_version not in ("v5", "v6"):
            raise ValueError(
                f"product_version must be 'v5' or 'v6', got: {effective_product_version!r}"
            )
        return asyncio.run(_fetch_articles_by_kb_ids_core(kb_ids, effective_product_version))

    if not query or not query.strip():
        raise ValueError("query is required when kb_ids is not provided")

    # Convert top_k from string to int if needed (Gradio/MCP may pass strings)
    converted_top_k: int | None = None
    if top_k is not None:
        if isinstance(top_k, str):
            try:
                converted_top_k = int(top_k)
            except (ValueError, TypeError) as e:
                raise ValueError(f"top_k must be a valid integer, got: {top_k!r}") from e
        elif isinstance(top_k, int):
            converted_top_k = top_k
        else:
            raise ValueError(f"top_k must be an integer or None, got: {type(top_k).__name__}")

        # Validate positive integer
        if converted_top_k <= 0:
            raise ValueError(f"top_k must be a positive integer, got: {converted_top_k}")

    if effective_product_version not in ("v5", "v6"):
        raise ValueError(
            f"product_version must be 'v5' or 'v6', got: {effective_product_version!r}"
        )

    # Delegate to the shared async core used by the LangChain tool
    return asyncio.run(
        _retrieve_context_core(
            query=query,
            top_k=converted_top_k,
            exclude_kb_ids=exclude_kb_ids,
            product_version=effective_product_version,
            runtime=None,
        )
    )


# MCP-compatible wrapper for agent_chat_handler
# Collects streaming response into a single string for MCP tools
async def ask_comindware(message: str) -> str:
    """Ask questions about Comindware Platform documentation and get intelligent answers with citations.

    The assistant automatically searches the knowledge base to find relevant articles
    and provides comprehensive answers based on official documentation. Use this for
    technical questions, configuration help, API usage, troubleshooting, and general
    platform guidance.

    Args:
        message: User's current message or question

    Returns:
        Complete response text with citations
    """
    # Collect all chunks from the generator into a single response
    response_parts: list[str] = []
    last_text_response: str | None = None
    final_context: AgentContext | None = None
    generator = None
    try:
        # Call the handler with empty history and None request (MCP context)
        # Note: agent_chat_handler is an async generator function used by ChatInterface
        generator = agent_chat_handler(message=message, history=[], request=None)

        # Consume the entire async generator to collect all responses
        # The generator now yields: full message history lists (for ChatInterface)
        # Extract the final answer from the last assistant message in the history
        async for chunk in generator:
            if chunk is None:
                continue

            # New: final AgentContext yield (preferred for exact final answer)
            if isinstance(chunk, AgentContext):
                final_context = chunk
                continue

            # Handle full history lists (new format - preserves all messages)
            if isinstance(chunk, list):
                # Extract final answer from last assistant message
                for msg in reversed(chunk):
                    if isinstance(msg, dict) and msg.get("role") == "assistant":
                        content = msg.get("content", "")
                        # Skip metadata-only messages (thinking blocks)
                        if content and not msg.get("metadata"):
                            if content.strip():
                                last_text_response = content
                                break
            # Handle string responses (backward compatibility)
            elif isinstance(chunk, str):
                if chunk.strip():  # Only add non-empty strings
                    response_parts.append(chunk)
                    last_text_response = chunk
            # Handle dict responses (backward compatibility)
            elif isinstance(chunk, dict):
                # Only extract text content from dicts, skip pure metadata
                content = chunk.get("content", "")
                if content and isinstance(content, str) and content.strip():
                    response_parts.append(content)
                    last_text_response = content

        # Ensure generator is fully consumed
        if generator:
            try:
                # Try to close the async generator if it's still open
                await generator.aclose()
            except Exception:
                pass

        # Prefer context-captured final answer if available
        if (
            final_context
            and isinstance(final_context.final_answer, str)
            and final_context.final_answer.strip()
        ):
            return final_context.final_answer

        # Return the final accumulated response (last chunk contains the full formatted text)
        if last_text_response:
            return last_text_response
        elif response_parts:
            # Fallback: join all parts if no single final response
            return "\n".join(response_parts)
        else:
            return "No response generated. Please try rephrasing your question."

    except StopIteration:
        # Generator exhausted normally
        if last_text_response:
            return last_text_response
        elif response_parts:
            return "\n".join(response_parts)
        return "No response generated."
    except IndexError as e:
        # Handle specific "pop index out of range" error
        logger.error("IndexError in ask_comindware (pop index): %s", e, exc_info=True)
        import traceback

        logger.error("Traceback: %s", traceback.format_exc())
        # Try to return whatever we collected
        if last_text_response:
            return last_text_response
        elif response_parts:
            return "\n".join(response_parts)
        return f"Error processing response: {str(e)}. Please try again."
    except Exception as e:
        logger.error("Error in ask_comindware: %s", e, exc_info=True)
        import traceback

        error_details = traceback.format_exc()
        logger.error("Full traceback: %s", error_details)
        # Try to return whatever we collected before the error
        if last_text_response:
            return (
                last_text_response
                + f"\n\n[Note: An error occurred during processing: {type(e).__name__}]"
            )
        elif response_parts:
            return "\n".join(response_parts) + f"\n\n[Note: An error occurred: {str(e)}]"
        return f"Error: {str(e)}. Please try rephrasing your question or contact support."


async def ask_comindware_structured(
    message: str,
    *,
    include_per_query_trace: bool = True,
) -> StructuredAgentResult:
    """Non-streaming structured callable for batch processing / datasets.

    Runs the same streaming handler, but captures the final AgentContext object
    yielded at the end of the generator.
    """
    context: AgentContext | None = None
    generator = agent_chat_handler(message=message, history=[], request=None)
    async for chunk in generator:
        if isinstance(chunk, AgentContext):
            context = chunk

    if context is None:
        # Defensive fallback: keep shape stable
        from kg_engine.llm.schemas import SGRPlanResult

        empty_plan = SGRPlanResult(
            spam_score=None,  # None when SGR didn't run
            spam_reason="SGR planning did not execute",
            user_intent="",
            topic="",
            category="",
            intent_confidence=None,  # None when SGR didn't run
            knowledge_base_search_queries=[""],
            action="proceed",
        )
        return StructuredAgentResult(plan=empty_plan, answer_text="")

    from pydantic import ValidationError

    from kg_engine.llm.schemas import SGRPlanResult, UsageBlock, UsageTotals

    plan_dict = context.sgr_plan or {}
    try:
        plan = SGRPlanResult.model_validate(plan_dict)
    except ValidationError:
        plan = SGRPlanResult(
            spam_score=0.0,
            spam_reason="SGR plan validation failed",
            user_intent="",
            topic="",
            category="",
            intent_confidence=0.5,
            knowledge_base_search_queries=[],
            action="proceed",
        )

    # Calculate answer confidence from rerank scores if articles available
    answer_confidence = None
    if context.final_articles:
        scores = []
        for article in context.final_articles:
            metadata = article.get("metadata", {})
            rerank_score = metadata.get("rerank_score")
            if rerank_score is not None:
                scores.append(rerank_score)
        if scores:
            answer_confidence = sum(scores) / len(scores)

    # Build usage block from AgentContext (per-turn) and accumulate per-session conversation usage.
    usage_turn_summary = getattr(context, "usage_turn_summary", {}) or {}
    usage_conversation_summary: dict[str, float] | None = None
    if isinstance(usage_turn_summary, dict):
        # Compute per-session conversation totals (including total_conversation_time_ms).
        session_id = (context.diagnostics or {}).get("session_id") if context.diagnostics else None
        turn_summary = {
            **(usage_turn_summary or {}),
            "turn_time_ms": getattr(context, "turn_time_ms", 0) or 0,
        }
        usage_conversation_summary = accumulate_conversation_usage(
            session_id=session_id,
            turn_summary=turn_summary,
        )

        usage_turn = UsageTotals(
            prompt_tokens=int(usage_turn_summary.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage_turn_summary.get("completion_tokens", 0) or 0),
            total_tokens=int(usage_turn_summary.get("total_tokens", 0) or 0),
            reasoning_tokens=int(usage_turn_summary.get("reasoning_tokens", 0) or 0),
            cached_tokens=int(usage_turn_summary.get("cached_tokens", 0) or 0),
            cache_write_tokens=int(usage_turn_summary.get("cache_write_tokens", 0) or 0),
            cost=float(usage_turn_summary.get("cost", 0.0) or 0.0),
            upstream_cost=float(usage_turn_summary.get("upstream_cost", 0.0) or 0.0),
        )
        if isinstance(usage_conversation_summary, dict):
            usage_conversation = UsageTotals(
                prompt_tokens=int(usage_conversation_summary.get("prompt_tokens", 0) or 0),
                completion_tokens=int(usage_conversation_summary.get("completion_tokens", 0) or 0),
                total_tokens=int(usage_conversation_summary.get("total_tokens", 0) or 0),
                reasoning_tokens=int(usage_conversation_summary.get("reasoning_tokens", 0) or 0),
                cached_tokens=int(usage_conversation_summary.get("cached_tokens", 0) or 0),
                cache_write_tokens=int(
                    usage_conversation_summary.get("cache_write_tokens", 0) or 0
                ),
                cost=float(usage_conversation_summary.get("cost", 0.0) or 0.0),
                upstream_cost=float(usage_conversation_summary.get("upstream_cost", 0.0) or 0.0),
            )
        else:
            usage_conversation = usage_turn
        usage_block: UsageBlock | None = UsageBlock(
            turn=usage_turn,
            conversation=usage_conversation,
        )
    else:
        usage_block = None
        usage_conversation_summary = None

    # Augment diagnostics with usage_conversation and timing/model metadata for downstream mapping.
    diagnostics = dict(getattr(context, "diagnostics", {}) or {})
    last_turn_ms = getattr(context, "turn_time_ms", 0) or 0
    total_conv_ms = (usage_conversation_summary or {}).get(
        "total_conversation_time_ms", last_turn_ms
    ) or 0
    if isinstance(usage_conversation_summary, dict):
        diagnostics["usage_conversation"] = usage_conversation_summary
    diagnostics["last_turn_time_s"] = round(float(last_turn_ms) / 1000.0, 6)
    diagnostics["total_conversation_time_s"] = round(float(total_conv_ms) / 1000.0, 6)
    diagnostics["model_used"] = getattr(context, "model_used", "") or ""

    return StructuredAgentResult(
        plan=plan,
        resolution_plan=getattr(context, "resolution_plan", None),
        executed_queries=getattr(context, "executed_queries", []),
        answer_confidence=answer_confidence,
        per_query_results=context.query_traces if include_per_query_trace else [],
        final_articles=context.final_articles,
        answer_text=context.final_answer,
        diagnostics=diagnostics,
        usage=usage_block,
    )


async def chat_with_metadata(
    message: str,
    history: list[dict],
    cancel_state: dict | None = None,
    request: gr.Request | None = None,
    skip_srp: bool = False,
) -> AsyncGenerator[tuple[list[dict], Any, Any, Any, Any, Any, Any], None]:
    """Streaming UI handler with metadata - yields chatbot during streaming, metadata once at end."""
    last_history: list[dict] = history if history else []
    ctx: AgentContext | None = None
    user_message = message  # Store original message for fallback metadata

    async for chunk in agent_chat_handler(
        message=message,
        history=history,
        cancel_state=cancel_state,
        request=request,
        skip_srp=skip_srp,
    ):
        if isinstance(chunk, list):
            last_history = chunk
            yield (
                chunk,
                gr.update(),  # No-op during streaming
                gr.update(),  # No-op during streaming
                gr.update(),  # No-op during streaming
                gr.update(),  # No-op during streaming
                gr.update(),  # No-op during streaming
            )
        else:
            ctx = chunk

    if ctx is None:
        logger.warning("chat_with_metadata: no AgentContext received, yielding hidden metadata")
        yield yield_hidden_updates(last_history)
        return

    try:
        # Extract plan data with timing
        plan_start = time.perf_counter()
        plan = ctx.sgr_plan or {}
        logger.info(
            f"chat_with_metadata: sgr_plan present={ctx.sgr_plan is not None}, "
            f"plan_keys={list(plan.keys()) if plan else []}, "
            f"user_intent_present={'user_intent' in plan}, "
            f"queries_present={'knowledge_base_search_queries' in plan}, "
            f"action_plan_present={'action_plan' in plan}, "
            f"user_message='{user_message[:50] if user_message else 'None'}...'"
        )
        user_intent = (
            plan.get("user_intent", "") if isinstance(plan.get("user_intent"), str) else ""
        )
        topic = plan.get("topic", "")
        category = plan.get("category", "")
        intent_confidence = plan.get("intent_confidence")
        knowledge_base_search_queries = plan.get("knowledge_base_search_queries", [])
        action_plan = plan.get("action_plan", [])

        # Log if sgr_plan is missing (shouldn't happen if SGR planning executed)
        if not ctx.sgr_plan:
            logger.warning(
                "chat_with_metadata: sgr_plan is None - SGR planning may not have executed. "
                "Will use fallback user_intent from message if available."
            )

        # Fallback: if user_intent is empty but we have a plan, try to derive it from the message
        # This handles cases where SGR planning returned empty values for math/time questions
        if not user_intent and plan and user_message:
            # Use the original user message as a fallback intent
            user_intent = user_message[:200]  # Truncate to reasonable length
            logger.info(
                f"chat_with_metadata: using fallback user_intent from message (len={len(user_intent)})"
            )

        # Ensure knowledge_base_search_queries is a list (even if empty)
        if not isinstance(knowledge_base_search_queries, list):
            knowledge_base_search_queries = []

        # Ensure action_plan is a list (even if empty)
        if not isinstance(action_plan, list):
            action_plan = []
        plan_elapsed = (time.perf_counter() - plan_start) * 1000
        logger.info(
            f"chat_with_metadata: plan extraction took {plan_elapsed:.2f}ms - "
            f"user_intent_len={len(user_intent)}, "
            f"queries_count={len(knowledge_base_search_queries) if isinstance(knowledge_base_search_queries, list) else 0}, "
            f"action_plan_count={len(action_plan) if isinstance(action_plan, list) else 0}"
        )

        conf_start = time.perf_counter()
        query_traces = ctx.query_traces or []
        logger.info(
            f"chat_with_metadata: formatting confidence badge - query_traces_count={len(query_traces)}, "
            f"has_traces={bool(query_traces)}, intent_confidence={intent_confidence}"
        )
        if query_traces:
            for idx, trace in enumerate(query_traces):
                has_conf = trace.get("confidence") is not None if isinstance(trace, dict) else False
                conf_type = (
                    type(trace.get("confidence")).__name__ if isinstance(trace, dict) else "N/A"
                )
                logger.debug(
                    f"chat_with_metadata: trace[{idx}] - has_confidence={has_conf}, "
                    f"confidence_type={conf_type}, articles_count={len(trace.get('articles', [])) if isinstance(trace, dict) else 0}"
                )
        search_confidence = None
        if ctx.final_articles:
            scores = [
                float((article.get("metadata") or {}).get("rerank_score", 0.0))
                for article in ctx.final_articles
                if isinstance((article.get("metadata") or {}).get("rerank_score"), (int, float))
            ]
            if scores:
                min_score = min(scores)
                max_score = max(scores)
                if max_score > min_score:
                    normalized_scores = [(s - min_score) / (max_score - min_score) for s in scores]
                else:
                    normalized_scores = [0.5] * len(scores)
                search_confidence = sum(normalized_scores) / len(normalized_scores)
        conf_elapsed = (time.perf_counter() - conf_start) * 1000
        logger.info(f"chat_with_metadata: search confidence calculation took {conf_elapsed:.2f}ms")

        executed_queries = ctx.executed_queries or []
        search_count = len(executed_queries)
        logger.info(
            f"chat_with_metadata: queries={search_count}, executed_queries={executed_queries}"
        )

        # Extract guard info for metadata
        guard_info = ctx.diagnostics.get("guard") if ctx.diagnostics else None
        has_guard = guard_info is not None

        # Extract SGR plan for metadata
        try:
            # format_articles_dataframe is disabled, returns empty list
            articles_df_data = format_articles_dataframe(ctx.final_articles or [])
        except Exception as exc:
            logger.error("Failed to format articles dataframe: %s", exc, exc_info=True)
            articles_df_data = []

        # Yield badges immediately, store metadata in state for later UI update
        logger.info("chat_with_metadata: yielding badges and storing metadata in state")
        yield_start = time.perf_counter()

        # Prepare metadata for state storage
        # Ensure we always show SGR metadata when plan exists
        has_user_intent = bool(user_intent and isinstance(user_intent, str) and user_intent.strip())
        has_topic = bool(topic and isinstance(topic, str) and topic.strip())
        has_category = bool(category and isinstance(category, str) and category.strip())
        has_intent_confidence = intent_confidence is not None and isinstance(
            intent_confidence, (int, float)
        )
        has_queries = bool(
            isinstance(knowledge_base_search_queries, list)
            and len(knowledge_base_search_queries) > 0
        )
        has_action_plan = bool(isinstance(action_plan, list) and len(action_plan) > 0)
        has_articles = bool(isinstance(articles_df_data, list) and len(articles_df_data) > 0)

        # Usage accounting (per-turn) from AgentContext, if available
        usage_turn_summary = getattr(ctx, "usage_turn_summary", {}) or {}

        # Accumulate per-session conversation usage using salted session_id from diagnostics
        session_id = (ctx.diagnostics or {}).get("session_id") if ctx.diagnostics else None
        turn_summary = {
            **(usage_turn_summary or {}),
            "turn_time_ms": getattr(ctx, "turn_time_ms", 0) or 0,
        }
        usage_conversation_summary = accumulate_conversation_usage(
            session_id=session_id,
            turn_summary=turn_summary,
        )

        # Always show user_intent if we have a user message (even if SGR plan is missing/empty)
        # This ensures metadata appears for math/date questions that don't call retrieve_context
        if not has_user_intent and user_message:
            has_user_intent = True
            user_intent = user_intent or user_message[:200]  # Use fallback if empty
            logger.info(
                f"chat_with_metadata: using fallback user_intent from message - "
                f"sgr_plan_present={ctx.sgr_plan is not None}, user_intent_len={len(user_intent)}"
            )

        # Extract guard info for metadata
        guard_info = ctx.diagnostics.get("guard") if ctx.diagnostics else None
        has_guard = guard_info is not None

        # Extract SGR plan for metadata
        sgr_plan = ctx.sgr_plan if ctx.sgr_plan else {}
        has_sgr_plan = bool(sgr_plan)

        # Store metadata in state for later UI update (after input is unlocked)
        queries_list = (
            knowledge_base_search_queries if isinstance(knowledge_base_search_queries, list) else []
        )

        # Extract SRP plan from context
        srp_plan = ctx.resolution_plan if hasattr(ctx, "resolution_plan") else None
        has_srp_plan = bool(srp_plan and srp_plan.get("engineer_intervention_needed"))

        metadata_dict = {
            "user_intent": user_intent if has_user_intent else "",
            "has_user_intent": has_user_intent,
            "topic": topic if has_topic else "",
            "has_topic": has_topic,
            "category": category if has_category else "",
            "has_category": has_category,
            "intent_confidence": intent_confidence if has_intent_confidence else None,
            "has_intent_confidence": has_intent_confidence,
            "guardian_info": guard_info,
            "has_guardian": has_guard,
            "sgr_plan": sgr_plan,
            "has_sgr_plan": has_sgr_plan,
            "srp_plan": srp_plan,
            "has_srp_plan": has_srp_plan,
            "knowledge_base_search_queries": queries_list,
            "has_queries": has_queries,
            "action_plan": action_plan if isinstance(action_plan, list) else [],
            "has_action_plan": has_action_plan,
            "articles_df_data": articles_df_data,
            "has_articles": has_articles,
            "usage_turn": usage_turn_summary,
            "usage_conversation": usage_conversation_summary,
        }

        logger.info(
            "chat_with_metadata: storing metadata in state - "
            f"user_intent={user_intent[:50] if user_intent else 'empty'}, "
            f"topic={topic}, category={category}, intent_confidence={intent_confidence}, "
            f"has_guardian={has_guard}, "
            f"queries_count={len(knowledge_base_search_queries) if isinstance(knowledge_base_search_queries, list) else 0}, "
            f"action_plan_count={len(action_plan) if isinstance(action_plan, list) else 0}, "
            f"articles_df_rows={len(articles_df_data) if isinstance(articles_df_data, list) else 0}"
        )

        try:
            # Build analysis data for JSON field (times in seconds, 4 decimal places)
            last_turn_ms = getattr(ctx, "turn_time_ms", 0) or 0
            total_conv_ms = usage_conversation_summary.get("total_conversation_time_ms", 0) or 0
            analysis_data = {
                "confidence": search_confidence,
                "queries_count": search_count,
                "queries": executed_queries,
                "usage_turn": usage_turn_summary,
                "usage_conversation": usage_conversation_summary,
                "last_turn_time_s": round(last_turn_ms / 1000, 4),
                "total_conversation_time_s": round(total_conv_ms / 1000, 4),
                "model_used": getattr(ctx, "model_used", "") or "",
            }
            yield yield_badge_updates(
                last_history,
                analysis_data,
                metadata_dict,
            )
            yield_elapsed = (time.perf_counter() - yield_start) * 1000
            logger.info(
                f"chat_with_metadata: badges yield and metadata storage completed, took {yield_elapsed:.2f}ms"
            )
        except Exception as yield_exc:
            logger.error(f"chat_with_metadata: badges yield failed: {yield_exc}", exc_info=True)
            raise

        logger.info("chat_with_metadata: generator completing normally")

    except Exception as exc:
        logger.error("Error in chat_with_metadata metadata processing: %s", exc, exc_info=True)
        # Yield safe fallback (6 values to match outputs)
        yield (
            last_history,
            gr.update(value={}),  # analysis_metadata
            gr.update(value={}),  # guardian_json
            gr.update(value={}),  # sgr_plan_json
            gr.update(value={}),  # srp_plan_json
            gr.update(value=[]),  # articles_df
        )


async def kb_assist_handler(
    message: str,
    history: list[dict],
    cancel_state: dict | None = None,
    request: gr.Request | None = None,
) -> AsyncGenerator[list[dict], None]:
    """Same agent as chat_with_metadata, yields only chatbot history (no metadata panels)."""
    async for result in chat_with_metadata(message, history, cancel_state, request,
                                           skip_srp=True):
        yield result[0]  # chatbot only


def _export_chat(history: list[dict]) -> str | None:
    if not history:
        return None
    lines = []
    for msg_item in history:
        role = msg_item.get("role", "unknown")
        content = msg_item.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        heading = "Пользователь" if role == "user" else "Ассистент"
        lines.append(f"## {heading}\n\n{content}\n")
    dt_info = _get_current_datetime_dict()
    now = datetime.datetime.fromisoformat(dt_info["iso_format"])
    tz_label = dt_info["timezone"]
    ts = f"{now.strftime('%Y-%m-%d %H:%M')} ({tz_label})"
    fn = now.strftime("%Y%m%d-%H%M%S")
    md = f"# Диалог с ИИ-ассистентом\n\n*Экспорт: {ts}*\n\n" + "\n---\n\n".join(lines)
    path = os.path.join(tempfile.mkdtemp(), f"{fn}_chat_export.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return path


def _show_download(history: list[dict]):
    if not history:
        return gr.update(visible=False, value=None)
    path = _export_chat(history)
    if path:
        return gr.update(value=path, visible=True)
    return gr.update(visible=False, value=None)


# Use metadata-enabled wrapper to populate debug UI panels after streaming.
handler_fn = chat_with_metadata
logger.info("Using agent-based (LangChain) handler for chat interface")

with gr.Blocks(
    title=chat_title or "Comindware Platform Documentation Assistant",
) as demo:
    # Product version selector — user session default, overridable per-tool-call by agent
    product_version_state = gr.State(value="v6")

    # Header row: title on the left, version selector on the right
    with gr.Row(visible=True, equal_height=False, elem_classes=["header-row"]):
        if chat_title:
            gr.Markdown(
                f"# {chat_title}",
                elem_classes=["hero-title"],
            )

        version_choices = [
            f"{i18n_resolve('product_version_label')}: v6",
            f"{i18n_resolve('product_version_label')}: v5",
        ]
        version_selector = gr.Dropdown(
            choices=version_choices,
            value=version_choices[0],
            interactive=True,
            scale=0,
            min_width=160,
            show_label=False,
        )

        def _on_version_change(v: str) -> str:
            from kg_engine.tools.retrieve_context import set_ui_product_version

            version = v.rsplit(":", 1)[-1].strip()
            set_ui_product_version(version)
            return v

        version_selector.change(
            fn=_on_version_change,
            inputs=[version_selector],
            outputs=[product_version_state],
            api_visibility="private",
        )

    # Chatbot component (like reference agent - NOT ChatInterface)
    # In Gradio 6, Chatbot uses messages format by default (no type parameter needed)
    # Conditional sizing: embedded widget uses fixed height and follows container, standalone is resizable
    # Stable container for the chatbot + input column (replaces fragile Svelte hash selectors)
    with gr.Column(elem_id="assistant-column", elem_classes=["assistant-column"]):
        chatbot = gr.Chatbot(
            label="Диалог с агентом",
            height=chatbot_height,  # Always set height (400px for embedded, 70vh for standalone)
            max_height=chatbot_max_height,  # Always set max_height (65vh for embedded, 70vh for standalone)
            show_label=True,
            container=True,
            buttons=["copy", "copy_all"],
            elem_id="chatbot-main",
            elem_classes=["chatbot-card"],
            resizable=not settings.gradio_embedded_widget,  # Resizable only in standalone mode, not embedded
        )

        # Message input (regular Textbox, NOT MultimodalTextbox)
        # Small built-in submit and stop buttons (icons) in the Textbox
        # Pattern from test script: dynamic stop button visibility
        with gr.Row(elem_id="input-row", elem_classes=["input-row"]):
            msg = gr.Textbox(
                label="Сообщение",
                placeholder="Введите ваш вопрос...",
                lines=1,
                max_lines=4,
                show_label=False,
                elem_id="message-input",
                elem_classes=["message-card"],
                scale=4,
                submit_btn=True,
                stop_btn=False,
            )
            download_btn = gr.DownloadButton(
                "\uf019",
                elem_id="chat-download-btn",
                elem_classes=["chat-download-btn"],
                visible=False,
                scale=0,
                min_width=30,
            )

    # State to store saved message
    saved_input = gr.State()
    # State to store current session_id for memory clearing
    current_session_id = gr.State(None)
    # Cancellation state - mutable dict so changes propagate to running generator
    cancellation_state = gr.State(value={"cancelled": False})

    # Metadata panels (always visible, populated after streaming completes)
    gr.Markdown(
        f"### {i18n_resolve('analysis_summary_title')}",
        visible=not settings.gradio_embedded_widget,
    )
    analysis_metadata = gr.JSON(label="Analysis", visible=not settings.gradio_embedded_widget)
    guardian_json = gr.JSON(
        label=i18n_resolve("guardian_badge_label"), visible=not settings.gradio_embedded_widget
    )
    sgr_plan_json = gr.JSON(
        label=i18n_resolve("sgr_plan_label"), visible=not settings.gradio_embedded_widget
    )
    srp_plan_json = gr.JSON(
        label=i18n_resolve("srp_plan_label"), visible=not settings.gradio_embedded_widget
    )

    gr.Markdown(
        f"### {i18n_resolve('retrieved_articles_title')}",
        visible=not settings.gradio_embedded_widget,
    )
    articles_df = gr.Dataframe(
        headers=[
            i18n_resolve("articles_rank_header"),
            i18n_resolve("articles_title_header"),
            i18n_resolve("articles_confidence_header"),
            i18n_resolve("articles_normalized_header"),
            i18n_resolve("articles_url_header"),
        ],
        interactive=False,
        visible=not settings.gradio_embedded_widget,
    )

    def handle_stop_click(
        history: list[dict], cancel_state: dict | None
    ) -> tuple[list[dict], dict]:
        """Handle built-in stop button click - set cancellation flag and add UI block.

        Sets cancellation flag in shared state so the running generator can check it,
        and adds a cancellation message as a separate UI block.
        """
        logger.info("Stop button clicked - setting cancellation flag")
        # Ensure cancel_state is a valid dict
        if cancel_state is None or not isinstance(cancel_state, dict):
            cancel_state = {"cancelled": True}
        else:
            cancel_state["cancelled"] = True
        # Add cancellation UI block as separate message (like other UI blocks)
        from kg_engine.api.stream_helpers import yield_cancelled

        cancellation_msg = yield_cancelled()
        history.append(cancellation_msg)
        return history, cancel_state

    def clear_and_save_textbox(message: str) -> tuple[gr.Textbox, str]:
        """Clear textbox and save message to state (pattern from ChatInterface/test script)."""
        return (
            gr.Textbox(value="", interactive=False, placeholder=""),
            message,
        )

    def handle_chatbot_clear(session_id: str | None) -> None:
        """Handle chatbot clear event - also clear memory when chat is cleared."""
        logger.info("Clear button clicked - clearing memory")
        if session_id:
            llm_manager._conversations.clear(session_id)
            logger.info(f"Memory cleared for session {session_id[:8]}...")
        return None  # Clear session_id state

    # Store original stop_btn value (True, but we start with False)
    original_stop_btn = True

    # Submit event - main handler
    # Pattern from ChatInterface/test script: show stop button after submit succeeds, hide when streaming completes
    user_submit = msg.submit(
        fn=clear_and_save_textbox,
        inputs=[msg],
        outputs=[msg, saved_input],  # Clear textbox and save message to state
        queue=False,
        api_visibility="private",
    )

    # Show stop button when submit succeeds (before streaming starts)
    # Pattern from ChatInterface: after_success.success() shows stop button
    user_submit.success(
        lambda: (
            gr.Textbox(submit_btn=False, stop_btn=original_stop_btn),
            gr.update(visible=False, value=None),
        ),
        outputs=[msg, download_btn],
        queue=False,
        api_visibility="private",
    )

    def save_session_id(
        message: str, history: list[dict], request: gr.Request | None
    ) -> str | None:
        """Save session_id to state for memory clearing."""
        base_session_id = getattr(request, "session_hash", None) if request is not None else None
        session_id = salt_session_id(base_session_id, history, message)
        return session_id

    def reset_cancellation_state(cancel_state: dict | None) -> dict:
        """Reset cancellation state at start of new submission."""
        if cancel_state is None or not isinstance(cancel_state, dict):
            cancel_state = {"cancelled": False}
        else:
            cancel_state["cancelled"] = False
        return cancel_state

    # Main streaming handler - chained from user_submit
    # Pattern from ChatInterface: append user message to chatbot first, then call handler
    submit_event = (
        user_submit.then(
            fn=reset_cancellation_state,
            inputs=[cancellation_state],
            outputs=[cancellation_state],
            queue=False,
            api_visibility="private",
        )
        .then(
            lambda message, history: history + [{"role": "user", "content": message}],
            inputs=[saved_input, chatbot],
            outputs=[chatbot],
            queue=False,
            api_visibility="private",
        )
        .then(
            fn=save_session_id,
            inputs=[
                saved_input,
                chatbot,
            ],  # Request is automatically passed to functions that accept it
            outputs=[current_session_id],
            queue=False,
            api_visibility="private",
        )
    )

    def re_enable_textbox_and_hide_stop():
        """Re-enable textbox and hide stop button after handler completion."""
        logger.info("Re-enabling textbox and hiding stop button after handler completion")
        return gr.Textbox(value="", interactive=True, submit_btn=True, stop_btn=False)

    def update_metadata_ui(metadata: dict | None) -> tuple:
        """Update metadata UI components from stored metadata state.

        Called after input is unlocked to populate SGR metadata.
        Note: Metadata fields are always visible - just update values.
        """
        logger.info("update_metadata_ui: starting")
        if settings.gradio_embedded_widget:
            logger.info("update_metadata_ui: embedded widget, returning defaults")
            return tuple(gr.update() for _ in range(8))

        if not metadata:
            logger.info("update_metadata_ui: no metadata to display")
            return (
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value=0),
                gr.update(value={}),
                gr.update(value=[]),
                gr.update(value=[]),
                gr.update(value=[]),
            )

        logger.info(
            f"update_metadata_ui: updating UI with metadata - "
            f"has_user_intent={metadata.get('has_user_intent', False)}, "
            f"has_topic={metadata.get('has_topic', False)}, "
            f"has_category={metadata.get('has_category', False)}, "
            f"has_intent_confidence={metadata.get('has_intent_confidence', False)}, "
            f"has_guardian={metadata.get('has_guardian', False)}, "
            f"has_queries={metadata.get('has_queries', False)}, "
            f"has_action_plan={metadata.get('has_action_plan', False)}, "
            f"has_articles={metadata.get('has_articles', False)}"
        )
        logger.info("update_metadata_ui: starting gr.update calls")
        # Just update values - fields are always visible
        result = (
            gr.update(value=metadata.get("user_intent", "")),
            gr.update(value=metadata.get("topic", "")),
            gr.update(value=metadata.get("category", "")),
            gr.update(value=metadata.get("intent_confidence")),
            gr.update(value=metadata.get("guardian_info", {})),
            gr.update(value=metadata.get("knowledge_base_search_queries", [])),
            gr.update(value=metadata.get("action_plan", [])),
            gr.update(value=metadata.get("articles_df_data", [])),
        )
        logger.info("update_metadata_ui: completed all gr.update calls")
        return result

    submit_event = submit_event.then(
        fn=handler_fn,
        inputs=[saved_input, chatbot, cancellation_state],  # Pass cancellation state to handler
        outputs=[
            chatbot,
            analysis_metadata,
            guardian_json,
            sgr_plan_json,
            srp_plan_json,
            articles_df,
        ],
        concurrency_limit=settings.gradio_default_concurrency_limit,
        api_visibility="private",  # Hide agent_chat_handler from MCP tools
    ).then(
        # Chain re-enable directly from handler completion
        # .then() fires after generator completes and all yields are processed
        fn=re_enable_textbox_and_hide_stop,
        outputs=[msg],
        api_visibility="private",
    ).then(
        fn=_show_download,
        inputs=[chatbot],
        outputs=[download_btn],
        api_visibility="private",
    )

    # Built-in stop button automatically cancels submit_event when stop_btn=True
    # Wire up the stop event to handle cancellation and update history
    # Also hide stop button when stop is clicked
    msg.stop(
        fn=handle_stop_click,
        inputs=[chatbot, cancellation_state],
        outputs=[chatbot, cancellation_state],
        cancels=[submit_event],  # Explicitly cancel submit event (though it's automatic)
        api_visibility="private",
    ).then(
        lambda: gr.Textbox(submit_btn=True, stop_btn=False),  # Hide stop button after cancellation
        outputs=[msg],
        queue=False,
        api_visibility="private",
    ).then(
        fn=_show_download,
        inputs=[chatbot],
        outputs=[download_btn],
        api_visibility="private",
    )

    # Bind to the built-in clear button's clear event
    # Also clear memory when chat is cleared
    chatbot.clear(
        fn=handle_chatbot_clear,
        inputs=[current_session_id],  # Use stored session_id
        outputs=[current_session_id],  # Clear session_id after clearing memory
        api_visibility="private",
    ).then(
        fn=_show_download,
        inputs=[chatbot],
        outputs=[download_btn],
        queue=False,
        api_visibility="private",
    )

    download_btn.click(
        fn=_export_chat,
        inputs=[chatbot],
        api_visibility="private",
    )

    # Explicitly expose MCP tools (public by default when using gr.api())
    # All other functions (agent_chat_handler, lambda, etc.) are set to private above
    # Functions exposed via gr.api() are automatically public and visible in MCP
    gr.api(
        fn=get_knowledge_base_articles,
        api_name="get_knowledge_base_articles",
        api_description="Search the Comindware Platform documentation knowledge base and retrieve relevant articles with full content. Returns structured JSON with article titles, URLs, content, and metadata. Use this for programmatic access to documentation content. For conversational answers, use ask_comindware instead.",
    )
    # Register the working wrapper function with a business-oriented name for MCP consumers
    # This provides a clean API name that's meaningful to external tools like Cursor
    gr.api(
        fn=ask_comindware,
        api_name="ask_comindware",
        api_description="Ask questions about Comindware Platform documentation and get intelligent answers with citations. The assistant automatically searches the knowledge base to find relevant articles and provides comprehensive answers based on official documentation. Use this for technical questions, configuration help, API usage, troubleshooting, and general platform guidance.",
    )

    demo.title = "Comindware Platform Documentation Assistant"


# ── KB Assist UI: same agent, no metadata panels, no header ──────────────────
kb_assist_title = "Ассистент базы знаний"

with gr.Blocks(
    title=kb_assist_title or "Comindware KB Assistant",
) as kb_assist_demo:
    with gr.Column(elem_id="assistant-column", elem_classes=["assistant-column"]):
        chatbot = gr.Chatbot(
            label="Диалог с агентом",
            show_label=True,
            container=True,
            buttons=["copy", "copy_all"],
            elem_id="chatbot-main",
            elem_classes=["chatbot-card"],
            resizable=True,
        )
        with gr.Row(elem_id="input-row", elem_classes=["input-row"]):
            msg = gr.Textbox(
                label="Сообщение",
                placeholder="Введите ваш вопрос...",
                lines=1,
                max_lines=4,
                show_label=False,
                elem_id="message-input",
                elem_classes=["message-card"],
                scale=4,
                submit_btn=True,
                stop_btn=False,
            )
            download_btn = gr.DownloadButton(
                "\uf019",
                elem_id="chat-download-btn",
                elem_classes=["chat-download-btn"],
                visible=False,
                scale=0,
                min_width=30,
            )
    saved_input = gr.State()
    current_session_id = gr.State(None)
    cancellation_state = gr.State(value={"cancelled": False})
    chat_history = gr.BrowserState([], storage_key="kb_chat_history")

    def _kb_handle_stop_click(
        history: list[dict], cancel_state: dict | None
    ) -> tuple[list[dict], dict]:
        from kg_engine.api.stream_helpers import yield_cancelled

        if cancel_state is None or not isinstance(cancel_state, dict):
            cancel_state = {"cancelled": True}
        else:
            cancel_state["cancelled"] = True
        history.append(yield_cancelled())
        return history, cancel_state

    def _kb_clear_and_save_textbox(message: str) -> tuple[gr.Textbox, str]:
        return (
            gr.Textbox(value="", interactive=False, placeholder=""),
            message,
        )

    def _kb_handle_chatbot_clear(session_id: str | None) -> None:
        if session_id:
            llm_manager._conversations.clear(session_id)
        return None

    def _kb_save_session_id(
        message: str, history: list[dict], request: gr.Request | None
    ) -> str | None:
        base_session_id = getattr(request, "session_hash", None) if request is not None else None
        return salt_session_id(base_session_id, history, message)

    def _kb_reset_cancellation_state(cancel_state: dict | None) -> dict:
        if cancel_state is None or not isinstance(cancel_state, dict):
            cancel_state = {"cancelled": False}
        else:
            cancel_state["cancelled"] = False
        return cancel_state

    def _kb_re_enable_textbox():
        return gr.Textbox(value="", interactive=True, submit_btn=True, stop_btn=False)

    def _kb_restore_chat(history):
        return history or []

    def _kb_save_chat(history):
        return history or []

    original_stop_btn = True

    kb_assist_demo.load(
        fn=_kb_restore_chat,
        inputs=[chat_history],
        outputs=[chatbot],
        api_visibility="private",
    ).then(
        fn=_show_download,
        inputs=[chatbot],
        outputs=[download_btn],
        api_visibility="private",
    )

    user_submit = msg.submit(
        fn=_kb_clear_and_save_textbox,
        inputs=[msg],
        outputs=[msg, saved_input],
        queue=False,
        api_visibility="private",
    )
    user_submit.success(
        lambda: (gr.Textbox(interactive=False, submit_btn=False, stop_btn=True), gr.update(visible=False, value=None)),
        outputs=[msg, download_btn],
        queue=False,
        api_visibility="private",
    )

    submit_event = (
        user_submit.then(
            fn=_kb_reset_cancellation_state,
            inputs=[cancellation_state],
            outputs=[cancellation_state],
            queue=False,
            api_visibility="private",
        )
        .then(
            lambda message, history: history + [{"role": "user", "content": message}],
            inputs=[saved_input, chatbot],
            outputs=[chatbot],
            queue=False,
            api_visibility="private",
        )
        .then(
            fn=_kb_save_session_id,
            inputs=[saved_input, chatbot],
            outputs=[current_session_id],
            queue=False,
            api_visibility="private",
        )
    )

    submit_event = submit_event.then(
        fn=kb_assist_handler,
        inputs=[saved_input, chatbot, cancellation_state],
        outputs=[chatbot],
        concurrency_limit=settings.gradio_default_concurrency_limit,
        api_visibility="private",
    ).then(
        fn=_kb_save_chat,
        inputs=[chatbot],
        outputs=[chat_history],
        api_visibility="private",
    ).then(
        fn=_kb_re_enable_textbox,
        outputs=[msg],
        api_visibility="private",
    ).then(
        fn=_show_download,
        inputs=[chatbot],
        outputs=[download_btn],
        api_visibility="private",
    )

    msg.stop(
        fn=_kb_handle_stop_click,
        inputs=[chatbot, cancellation_state],
        outputs=[chatbot, cancellation_state],
        cancels=[submit_event],
        api_visibility="private",
    ).then(
        fn=_kb_save_chat,
        inputs=[chatbot],
        outputs=[chat_history],
        api_visibility="private",
    ).then(
        lambda: gr.Textbox(interactive=True, submit_btn=True, stop_btn=False),
        outputs=[msg],
        queue=False,
        api_visibility="private",
    ).then(
        fn=_show_download,
        inputs=[chatbot],
        outputs=[download_btn],
        api_visibility="private",
    )

    def _kb_clear_chat_history():
        return []

    chatbot.clear(
        fn=_kb_handle_chatbot_clear,
        inputs=[current_session_id],
        outputs=[current_session_id],
        api_visibility="private",
    ).then(
        fn=_kb_clear_chat_history,
        outputs=[chat_history],
        api_visibility="private",
    ).then(
        fn=_show_download,
        inputs=[chatbot],
        outputs=[download_btn],
        queue=False,
        api_visibility="private",
    )

    download_btn.click(
        fn=_export_chat,
        inputs=[chatbot],
        api_visibility="private",
    )

    kb_assist_demo.title = kb_assist_title or "Comindware KB Assistant"


    # CMW Platform API endpoint - works with both direct REST and Gradio API calls
    def cmw_process_support_request(request_id: str | dict, request: gr.Request) -> dict:
        """Process CMW Platform support request via API."""
        # Handle Gradio API dict format
        if isinstance(request_id, dict):
            request_id = request_id.get("request_id")

        if not request_id:
            return {"success": False, "message": None, "error": "Missing request_id"}

        # API key authentication
        if settings.cmw_api_key:
            provided_key = request.headers.get("X-API-Key")
            if provided_key != settings.cmw_api_key:
                logger.warning("Invalid API key attempt to CMW endpoint")
                return {"success": False, "message": None, "error": "Invalid API key"}

        try:
            from kg_engine.cmw_platform.connector import PlatformConnector
        except ImportError:
            logger.error("PlatformConnector not available (cmw_platform module missing)")
            return {"success": False, "message": None, "error": "Platform connector not available"}
        connector = PlatformConnector()
        result = connector.start_request(str(request_id))

        return {
            "success": result.success,
            "message": result.message,
            "error": result.error,
        }

    # Note: FastAPI endpoint at /api/v1/cmw/process-support-request (see below)

if __name__ == "__main__":
    logger = logging.getLogger(__name__)

    logger.info(
        "Starting Gradio server at %s:%s (share=%s)",
        settings.gradio_server_name,
        settings.gradio_server_port,
        settings.gradio_share,
    )

    if settings.gradio_share:
        logger.info(
            "Share link enabled. If share link creation fails, the app will still run locally."
        )
        try:
            from gradio import networking

            share_url = networking.setup_tunnel(
                local_host=settings.gradio_server_name,
                local_port=settings.gradio_server_port,
                share_token=demo.share_token,
                share_server_address=None,
                share_server_tls_certificate=None,
            )
            print(f"* Running on public URL: {share_url}")
            print(
                "\nThis share link expires in 1 week. For free permanent hosting and GPU upgrades, "
                "run `gradio deploy` from the terminal in the working directory to deploy to "
                "Hugging Face Spaces (https://huggingface.co/spaces)"
            )
        except Exception as e:
            logger.warning("Could not create share link: %s", e)

    # Configure queue
    demo.queue(
        default_concurrency_limit=settings.gradio_default_concurrency_limit,
        status_update_rate="auto",
    )

    # Build FastAPI app with CMW Platform endpoint
    from fastapi import FastAPI, Request
    from fastapi.responses import RedirectResponse
    from gradio import mount_gradio_app
    from pydantic import BaseModel

    fastapi_app = FastAPI(title="CMW RAG API")

    @fastapi_app.get("/kb_assist")
    async def _kb_assist_redirect():
        return RedirectResponse(url="/kb_assist/", status_code=301)

    class ProcessSupportRequest(BaseModel):
        request_id: str

    @fastapi_app.post("/api/v1/cmw/process-support-request")
    async def cmw_endpoint(req: ProcessSupportRequest, http_req: Request) -> dict:
        """Process CMW Platform (primary) support request via REST API."""
        return cmw_process_support_request(req.request_id, http_req)

    class SummarizeDocumentRequest(BaseModel):
        request_id: str

    @fastapi_app.post("/api/v1/cmw/summarize-document")
    async def summarize_document_endpoint(req: SummarizeDocumentRequest, http_req: Request) -> dict:
        """Summarize document attached to a CMW Platform record (Lukoil instance).

        Fire-and-forget: verifies record is readable, returns ACK immediately,
        processes document in background thread, writes result to record via API.

        Args:
            request_id: Record ID in ArchitectureManagement.Zaprosinarazrabotky

        Returns:
            {"success": bool, "message": str, "error": str | None}
        """
        # API key authentication
        if settings.cmw2_api_key:
            provided_key = http_req.headers.get("X-API-Key")
            if provided_key != settings.cmw2_api_key:
                logger.warning("Invalid API key attempt to summarize-document endpoint")
                return {"success": False, "message": None, "error": "Invalid API key"}

        try:
            from kg_engine.cmw_platform.summary_connector import DocumentSummaryConnector
        except ImportError:
            logger.error("DocumentSummaryConnector not available (cmw_platform module missing)")
            return {"success": False, "message": None, "error": "Summary connector not available"}

        try:
            connector = DocumentSummaryConnector(platform="secondary")
            result = connector.start(req.request_id)

            return {
                "success": result.success,
                "message": result.message,
                "error": result.error,
            }
        except Exception:
            logger.exception("Document summarization failed to start")
            return {"success": False, "error": "Internal error"}

    # Mount Gradio with all options including MCP
    # Configure static file access for Gradio (see https://www.gradio.app/guides/file-access)
    # We keep the scope narrow by only allowing:
    # - The internal `rag_engine/resources` directory (theme, logo, etc.)
    # - An optional top-level `resources` directory (for shared fonts like OpenSans)
    allowed_paths_list: list[str] = []
    if RESOURCES_DIR.exists():
        allowed_paths_list.append(str(RESOURCES_DIR))
    project_resources_dir = Path.cwd() / "resources"
    if project_resources_dir.exists():
        allowed_paths_list.append(str(project_resources_dir))

    # Mount /kb_assist FIRST — sub-path must precede root mount for Starlette routing
    app = mount_gradio_app(
        fastapi_app,
        kb_assist_demo,
        path="/kb_assist",
        mcp_server=False,
        footer_links=[],
        theme=gr.themes.Soft(),
        css_paths=[css_file_path] if css_file_path.exists() else [],
        allowed_paths=allowed_paths_list or None,
    )

    app = mount_gradio_app(
        fastapi_app,
        demo,
        path="/",
        mcp_server=True,
        footer_links=["api"],
        theme=gr.themes.Soft(),
        css_paths=[css_file_path] if css_file_path.exists() else [],
        allowed_paths=allowed_paths_list or None,
    )

    # Starlette Mount at "/" catches all — move /kb_assist before root mount
    _routes = app.routes
    for i, r in enumerate(_routes):
        if getattr(r, "path", None) == "/kb_assist" and i > 0:
            _routes.insert(0, _routes.pop(i))
            break

    import asyncio
    import logging

    _error_logger = logging.getLogger("uvicorn.error")

    class _FilterCancelled(logging.Filter):
        def filter(self, record):
            if record.exc_info and issubclass(record.exc_info[0], asyncio.CancelledError):
                return False
            return True

    _error_logger.addFilter(_FilterCancelled())

    from kg_engine.api.server import run_gradio_uvicorn

    run_gradio_uvicorn(app)
