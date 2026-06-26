"""Context tracking utilities for agent execution.

These utilities help the agent track accumulated context during multi-tool execution,
enabling progressive budgeting and preventing context overflow.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from kg_engine.retrieval.retriever import Article

logger = logging.getLogger(__name__)


class AgentContext(BaseModel):
    """Typed context passed from agent to tools for progressive budgeting.

    This context is passed via the `context` parameter in agent.invoke()
    and accessed by tools via `runtime.context` for clean, typed access.
    Follows LangChain 1.0 official pattern for context sharing.

    Attributes:
        conversation_tokens: Tokens used by conversation history
        accumulated_tool_tokens: Tokens from previous tool calls (deduplicated)
        fetched_kb_ids: Set of kb_ids already fetched in this turn (prevents duplicate retrieval)
    """

    conversation_tokens: int = Field(
        default=0,
        description="Tokens used by conversation history (user/assistant messages)",
    )

    accumulated_tool_tokens: int = Field(
        default=0,
        description="Tokens accumulated from previous tool calls in this turn (deduplicated)",
    )

    fetched_kb_ids: set[str] = Field(
        default_factory=set,
        description="Set of kb_ids already fetched in this turn (prevents duplicate retrieval). "
        "Optional - defaults to empty set if not provided (e.g., for MCP calls).",
    )

    # --- SGR planning + structured trace ---
    # NOTE: sgr_plan is intentionally NOT excluded: it is injected into the LLM context
    # to guide retrieval decisions (subqueries as suggestions, action_plan as guidance).
    sgr_plan: dict[str, Any] | None = Field(
        default=None,
        description="SGR plan (spam score, subqueries, action plan) injected into LLM context.",
    )

    # --- SRP (Support Resolution Plan) ---
    # Generated after answer completion for human support engineers
    resolution_plan: dict[str, Any] | None = Field(
        default=None,
        description="SRP plan (engineer intervention needed, issue summary, next steps).",
    )
    resolution_plan_error: str | None = Field(
        default=None,
        description="Error message if SRP generation failed.",
    )

    # Execution trace + final results are excluded from serialization to the LLM.
    # They are used for batch output and UI debug panels.
    query_traces: list[dict[str, Any]] = Field(
        default_factory=list,
        exclude=True,
        description="Actual executed retrieval calls trace (excluded from LLM context).",
    )
    final_answer: str = Field(
        default="",
        exclude=True,
        description="Final answer text with citations (excluded from LLM context).",
    )
    final_articles: list[dict[str, Any]] = Field(
        default_factory=list,
        exclude=True,
        description="Final deduplicated articles serialized to dicts (excluded from LLM context).",
    )
    executed_queries: list[str] = Field(
        default_factory=list,
        exclude=True,
        description="Deduplicated search queries from tool results (excluded from LLM context).",
    )
    diagnostics: dict[str, Any] = Field(
        default_factory=dict,
        exclude=True,
        description="Run diagnostics (tokens, compression flags) excluded from LLM context.",
    )

    # --- UI-only correlation (excluded from LLM) ---
    pending_ui_messages: list[dict[str, Any]] = Field(
        default_factory=list,
        exclude=True,
        description="UI-only messages enqueued by middleware for immediate display.",
    )
    emitted_ui_ids: set[str] = Field(
        default_factory=set,
        exclude=True,
        description="IDs of UI-only messages already emitted in this turn (dedupe).",
    )

    # --- Usage accounting (per-turn) ---
    # These fields are populated by usage_accounting.UsageAccountingCallback and are
    # excluded from the LLM context. They are intended for diagnostics, UI metadata,
    # and downstream integration (e.g., Comindware Platform).
    usage_calls: list[dict[str, Any]] = Field(
        default_factory=list,
        exclude=True,
        description="Raw usage samples per LLM call (for diagnostics).",
    )
    usage_turn_summary: dict[str, Any] = Field(
        default_factory=dict,
        exclude=True,
        description="Aggregated per-turn usage summary (tokens, cost, caching).",
    )

    # --- Turn timing and model (excluded from LLM) ---
    turn_time_ms: float = Field(
        default=0.0,
        exclude=True,
        description="Last turn execution time in milliseconds (end - start).",
    )
    model_used: str = Field(
        default="",
        exclude=True,
        description="Model used this turn as 'provider: slug' (e.g. openrouter: deepseek/...).",
    )


# ContextVar propagates across async/await; threading.local does not (UsageAccountingCallback runs in same task)
_agent_context_var: ContextVar[AgentContext | None] = ContextVar("agent_context", default=None)


def set_current_context(context: AgentContext | None) -> None:
    """Set the current AgentContext for this execution context.

    Uses ContextVar so it propagates across async/await (callbacks, LLM streaming).
    """
    _agent_context_var.set(context)


def get_current_context() -> AgentContext | None:
    """Get the current AgentContext for this execution context."""
    return _agent_context_var.get()


def compute_context_tokens(
    messages: list[dict | Any],
    tool_results: list[str] | None = None,
    add_json_overhead: bool = True,
) -> tuple[int, int]:
    """Unified function to compute tokens from messages or separate lists.

    Handles both:
    - LangChain message objects from state (with tool messages embedded)
    - Separate dict messages + tool_results lists

    This is the centralized token counting function used throughout the codebase
    for consistent budgeting. It deduplicates articles by kb_id and optionally
    adds JSON overhead percentage for tool results.

    Args:
        messages: List of messages (dict or LangChain objects). If tool_results
                 is None, tool messages are extracted from this list.
        tool_results: Optional separate list of tool result JSON strings. If provided,
                     only these are counted (messages are treated as conversation only).
        add_json_overhead: Whether to add configurable JSON overhead percentage
                          for tool results (default: True)

    Returns:
        Tuple of (conversation_tokens, accumulated_tool_tokens)
        - conversation_tokens: Tokens from non-tool messages
        - accumulated_tool_tokens: Tokens from tool results (deduplicated, with optional JSON overhead)

    Example:
        >>> # From agent state (LangChain messages)
        >>> from kg_engine.utils.context_tracker import compute_context_tokens
        >>> conv_toks, tool_toks = compute_context_tokens(state_messages)
        >>> total = conv_toks + tool_toks

        >>> # From separate lists (dict messages + tool results)
        >>> conv_toks, tool_toks = compute_context_tokens(messages, tool_results)
        >>> total = conv_toks + tool_toks
    """
    from kg_engine.config.settings import settings
    from kg_engine.llm.token_utils import count_tokens
    from kg_engine.tools.utils import parse_tool_result_to_articles

    conversation_tokens = 0
    accumulated_tool_tokens = 0
    seen_kb_ids: set[str] = set()

    # If tool_results is provided, count only those (messages are conversation only)
    if tool_results is not None:
        # Count conversation messages
        for msg in messages:
            content = (
                msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            )
            if isinstance(content, str) and content:
                conversation_tokens += count_tokens(content)

        # Count tool results from separate list
        for tool_result in tool_results:
            if not isinstance(tool_result, str):
                continue
            try:
                articles = parse_tool_result_to_articles(tool_result)
                for article in articles:
                    if article.kb_id and article.kb_id not in seen_kb_ids:
                        seen_kb_ids.add(article.kb_id)
                        accumulated_tool_tokens += count_tokens(article.content)
            except Exception as exc:
                # If parsing fails, fall back to rough estimate
                logger.warning("Failed to parse tool result for token counting: %s", exc)
                accumulated_tool_tokens += count_tokens(tool_result) // 2
    else:
        # Extract tool messages from messages list (LangChain state format)
        for msg in messages:
            # Handle both dict and LangChain message objects
            content = (
                getattr(msg, "content", "") if hasattr(msg, "content") else msg.get("content", "")
            )
            if not isinstance(content, str) or not content:
                continue

            # Check message type
            msg_type = getattr(msg, "type", None) if hasattr(msg, "type") else msg.get("type")

            if msg_type == "tool":
                # Tool message - parse and count articles
                try:
                    articles = parse_tool_result_to_articles(content)
                    for art in articles:
                        if art.kb_id and art.kb_id not in seen_kb_ids:
                            seen_kb_ids.add(art.kb_id)
                            accumulated_tool_tokens += count_tokens(art.content)
                except Exception as exc:
                    # If parsing fails, log and skip rather than guessing; keep accounting strict
                    logger.warning("Failed to parse tool result for token accounting: %s", exc)
                    continue
            else:
                # Conversation message
                conversation_tokens += count_tokens(content)

    # Add configurable JSON overhead percentage if requested
    if add_json_overhead and accumulated_tool_tokens > 0:
        json_overhead_pct = getattr(settings, "llm_tool_results_json_overhead_pct", 0.30)
        accumulated_tool_tokens = int(accumulated_tool_tokens * (1.0 + json_overhead_pct))

    logger.debug(
        "Context tokens: conversation=%d, tools=%d (with JSON overhead=%s, %d unique articles)",
        conversation_tokens,
        accumulated_tool_tokens,
        add_json_overhead,
        len(seen_kb_ids),
    )

    return conversation_tokens, accumulated_tool_tokens


def estimate_accumulated_tokens(
    conversation_messages: list[dict],
    tool_results: list[str],
) -> tuple[int, int]:
    """Estimate tokens from conversation and accumulated tool results.

    This is a convenience wrapper for the unified compute_context_tokens function.
    Maintains backward compatibility with existing code.

    Args:
        conversation_messages: List of user/assistant messages from history
        tool_results: List of JSON strings from tool calls in THIS turn

    Returns:
        Tuple of (conversation_tokens, accumulated_tool_tokens)

    Example:
        >>> messages = [{"role": "user", "content": "Hello"}]
        >>> tool_results = ['{"articles": [...]}', '{"articles": [...]}']
        >>> conv_tokens, tool_tokens = estimate_accumulated_tokens(messages, tool_results)
        >>> total = conv_tokens + tool_tokens  # Pass this to retriever
    """
    return compute_context_tokens(
        conversation_messages,
        tool_results=tool_results,
        add_json_overhead=False,  # Legacy behavior: no JSON overhead
    )


def extract_articles_from_runtime_state(runtime_state: dict) -> list[Article]:
    """Extract articles from runtime state messages (for tool use).

    This is a lightweight helper for the tool to get already-accumulated
    article data from runtime.state without doing heavy parsing.

    Args:
        runtime_state: Runtime state dict with 'messages' key

    Returns:
        List of Article objects from tool result messages

    Example:
        >>> # In tool:
        >>> articles = extract_articles_from_runtime_state(runtime.state)
        >>> # Use for deduplication or other lightweight operations
    """
    from kg_engine.tools.utils import parse_tool_result_to_articles

    articles = []
    messages = runtime_state.get("messages", [])

    for msg in messages:
        # Get message content
        if hasattr(msg, "content"):
            content = msg.content
        else:
            content = msg.get("content", "") if isinstance(msg, dict) else ""

        if isinstance(content, str) and content:
            msg_type = getattr(msg, "type", None)

            if msg_type == "tool":
                # Tool result - parse articles
                try:
                    tool_articles = parse_tool_result_to_articles(content)
                    articles.extend(tool_articles)
                except Exception as exc:
                    logger.warning("Failed to parse articles from runtime state: %s", exc)

    return articles


def compute_thresholds(
    window: int, pre_pct: float = 0.90, post_pct: float = 0.80
) -> tuple[int, int]:
    """Compute context thresholds for pre-agent and post-tool checks.

    Args:
        window: Context window size in tokens
        pre_pct: Pre-agent threshold percentage (default: 0.90 = 90%)
        post_pct: Post-tool threshold percentage (default: 0.80 = 80%)

    Returns:
        Tuple of (pre_threshold, post_threshold) in tokens

    Example:
        >>> from kg_engine.utils.context_tracker import compute_thresholds
        >>> pre, post = compute_thresholds(100000, 0.90, 0.80)
        >>> pre == 90000 and post == 80000
        True
    """
    return int(window * pre_pct), int(window * post_pct)


def compute_overhead_tokens(
    system_prompt: str | None = None,
    tools: list | None = None,
    safety_margin: int | None = None,
) -> int:
    """Compute overhead tokens from actual system prompt and tool schemas.

    Counts actual tokens in:
    - System prompt (if provided, otherwise uses get_system_prompt())
    - Tool schemas (if provided, otherwise uses retrieve_context tool)
    - Safety margin for formatting overhead (if provided, otherwise uses settings)

    Args:
        system_prompt: System prompt string (if None, uses get_system_prompt())
        tools: List of LangChain tools (if None, uses retrieve_context tool)
        safety_margin: Additional safety margin for formatting overhead (if None, uses settings)

    Returns:
        Total overhead tokens (system prompt + tool schemas + safety margin)

    Example:
        >>> from kg_engine.utils.context_tracker import compute_overhead_tokens
        >>> overhead = compute_overhead_tokens()  # Uses defaults
        >>> overhead > 0
        True
    """
    import json

    from kg_engine.config.settings import settings
    from kg_engine.llm.prompts import get_system_prompt
    from kg_engine.llm.token_utils import count_tokens
    from kg_engine.tools.retrieve_context import retrieve_context

    total_overhead = 0

    # Count system prompt tokens
    if system_prompt is None:
        system_prompt = (
            get_system_prompt()
        )  # Use function for consistency, no guidance needed for token counting
    total_overhead += count_tokens(system_prompt)

    # Count tool schema tokens
    if tools is None:
        tools = [retrieve_context]

    for tool in tools:
        # Get tool schema JSON from Pydantic model
        if hasattr(tool, "args_schema") and tool.args_schema:
            try:
                schema_json = tool.args_schema.model_json_schema()
                schema_str = json.dumps(schema_json, separators=(",", ":"))
                total_overhead += count_tokens(schema_str)
            except Exception as exc:
                logger.warning("Failed to get tool schema for token counting: %s", exc)
        # Also count tool description
        if hasattr(tool, "description") and tool.description:
            total_overhead += count_tokens(tool.description)

    # Add safety margin for formatting overhead
    if safety_margin is None:
        safety_margin = getattr(settings, "llm_context_overhead_safety_margin", 2000)
    try:
        safety_margin = int(safety_margin)
    except (TypeError, ValueError):
        safety_margin = 2000  # Default fallback
    total_overhead += safety_margin

    logger.debug(
        "Overhead tokens: system_prompt + tool_schemas + safety_margin = %d",
        total_overhead,
    )

    return total_overhead


def estimate_accumulated_context(
    messages: list[dict],
    tool_results: list[str],
    system_prompt: str | None = None,
    tools: list | None = None,
) -> int:
    """Estimate total tokens for messages + tool results + overhead.

    Uses actual token counts for system prompt and tool schemas,
    not percentage-based estimates.

    Args:
        messages: Conversation messages (dict or LangChain messages)
        tool_results: List of tool result JSON strings
        system_prompt: System prompt string (if None, uses get_system_prompt())
        tools: List of LangChain tools (if None, uses retrieve_context tool)

    Returns:
        Estimated total token count including overhead

    Example:
        >>> from kg_engine.utils.context_tracker import estimate_accumulated_context
        >>> messages = [{"role": "user", "content": "Hello"}]
        >>> tool_results = ['{"articles": [...]}']
        >>> total = estimate_accumulated_context(messages, tool_results)
        >>> total > 0
        True
    """
    from kg_engine.llm.token_utils import count_messages_tokens, count_tokens

    total_tokens = count_messages_tokens(messages)

    # Count tool result tokens (JSON format is verbose!)
    for result in tool_results:
        if isinstance(result, str):
            total_tokens += count_tokens(result)

    # Add overhead from actual system prompt + tool schemas
    overhead_tokens = compute_overhead_tokens(system_prompt, tools)
    total_tokens += overhead_tokens

    return total_tokens
