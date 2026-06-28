"""Context tracking utilities for agent execution."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from pydantic import BaseModel, Field


class AgentContext(BaseModel):
    """Typed context passed from agent to tools for progressive budgeting.

    Attributes:
        conversation_tokens: Tokens used by conversation history
        accumulated_tool_tokens: Tokens from previous tool calls (deduplicated)
        fetched_kb_ids: Set of kb_ids already fetched in this turn (prevents duplicate retrieval)
    """

    conversation_tokens: int = Field(default=0)
    accumulated_tool_tokens: int = Field(default=0)
    fetched_kb_ids: set[str] = Field(default_factory=set)
    sgr_plan: dict[str, Any] | None = Field(default=None)
    resolution_plan: dict[str, Any] | None = Field(default=None)
    resolution_plan_error: str | None = Field(default=None)
    query_traces: list[dict[str, Any]] = Field(default_factory=list, exclude=True)
    final_answer: str = Field(default="", exclude=True)
    final_articles: list[dict[str, Any]] = Field(default_factory=list, exclude=True)
    executed_queries: list[str] = Field(default_factory=list, exclude=True)
    diagnostics: dict[str, Any] = Field(default_factory=dict, exclude=True)
    pending_ui_messages: list[dict[str, Any]] = Field(default_factory=list, exclude=True)
    emitted_ui_ids: set[str] = Field(default_factory=set, exclude=True)
    usage_calls: list[dict[str, Any]] = Field(default_factory=list, exclude=True)
    usage_turn_summary: dict[str, Any] = Field(default_factory=dict, exclude=True)
    turn_time_ms: float = Field(default=0.0, exclude=True)
    model_used: str = Field(default="", exclude=True)


_agent_context_var: ContextVar[AgentContext | None] = ContextVar("agent_context", default=None)


def set_current_context(context: AgentContext | None) -> None:
    """Set the current AgentContext for this execution context."""
    _agent_context_var.set(context)


def get_current_context() -> AgentContext | None:
    """Get the current AgentContext for this execution context."""
    return _agent_context_var.get()
