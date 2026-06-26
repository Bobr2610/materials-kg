from __future__ import annotations

from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from kg_engine.utils.context_tracker import get_current_context

USAGE_NUMERIC_FIELDS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "reasoning_tokens",
    "cached_tokens",
    "cache_write_tokens",
    "cost",
    "upstream_cost",
)

_conversation_usage_totals: dict[str, dict[str, float]] = {}


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def normalize_openrouter_token_usage(token_usage: dict[str, Any] | None) -> dict[str, float]:
    """Normalize OpenRouter-style token_usage dict to a flat numeric summary.

    The shape matches the usage object described in the OpenRouter docs:
    - https://openrouter.ai/docs/guides/guides/usage-accounting#response-format
    """
    if not isinstance(token_usage, dict):
        return dict.fromkeys(USAGE_NUMERIC_FIELDS, 0.0)

    prompt_tokens = _safe_int(token_usage.get("prompt_tokens"))
    completion_tokens = _safe_int(token_usage.get("completion_tokens"))
    total_tokens = _safe_int(token_usage.get("total_tokens") or (prompt_tokens + completion_tokens))

    completion_details = token_usage.get("completion_tokens_details") or {}
    if not isinstance(completion_details, dict):
        completion_details = {}
    reasoning_tokens = _safe_int(completion_details.get("reasoning_tokens"))

    prompt_details = token_usage.get("prompt_tokens_details") or {}
    if not isinstance(prompt_details, dict):
        prompt_details = {}
    cached_tokens = _safe_int(prompt_details.get("cached_tokens"))
    cache_write_tokens = _safe_int(prompt_details.get("cache_write_tokens"))

    cost = _safe_float(token_usage.get("cost"))
    cost_details = token_usage.get("cost_details") or {}
    if not isinstance(cost_details, dict):
        cost_details = {}
    upstream_cost = _safe_float(cost_details.get("upstream_inference_cost"))

    return {
        "prompt_tokens": float(prompt_tokens),
        "completion_tokens": float(completion_tokens),
        "total_tokens": float(total_tokens),
        "reasoning_tokens": float(reasoning_tokens),
        "cached_tokens": float(cached_tokens),
        "cache_write_tokens": float(cache_write_tokens),
        "cost": cost,
        "upstream_cost": upstream_cost,
    }


class UsageAccountingCallback(BaseCallbackHandler):
    """LangChain callback that accumulates OpenRouter usage on the current AgentContext.

    This callback is attached to the underlying ChatOpenAI model so that every LLM
    call (SGR, main answer, SRP, etc.) contributes to a per-turn usage summary.
    """

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:  # type: ignore[override]
        ctx = get_current_context()
        if ctx is None:
            return

        llm_output = response.llm_output if isinstance(response.llm_output, dict) else {}
        token_usage = llm_output.get("token_usage")
        if not isinstance(token_usage, dict):
            return

        normalized = normalize_openrouter_token_usage(token_usage)

        # Store raw sample for diagnostics / debugging.
        try:
            calls = getattr(ctx, "usage_calls", None)
            if calls is not None and isinstance(calls, list):
                calls.append(
                    {
                        "model_name": llm_output.get("model_name"),
                        "model_provider": llm_output.get("model_provider"),
                        "token_usage": token_usage,
                        "normalized": normalized,
                    }
                )
        except Exception:
            # Diagnostics must never break the main flow.
            pass

        # Accumulate per-turn summary numerically.
        try:
            summary = getattr(ctx, "usage_turn_summary", None) or {}
            if not isinstance(summary, dict):
                summary = {}
            for field in USAGE_NUMERIC_FIELDS:
                prev = float(summary.get(field, 0.0) or 0.0)
                summary[field] = prev + float(normalized.get(field, 0.0) or 0.0)
            ctx.usage_turn_summary = summary  # type: ignore[attr-defined]
        except Exception:
            # Usage accounting must not affect core behavior.
            pass


def accumulate_conversation_usage(
    session_id: str | None, turn_summary: dict[str, Any] | None
) -> dict[str, float]:
    """Accumulate per-session usage totals from a single turn summary.

    This is a lightweight in-memory accumulator keyed by salted session_id.
    It is intentionally side-effect free for None / empty inputs.
    Also accumulates turn_time_ms into total_conversation_time_ms per session.
    """
    if not session_id:
        # No stable session identifier; return turn summary as-is.
        if isinstance(turn_summary, dict):
            out = {key: float(turn_summary.get(key, 0.0) or 0.0) for key in USAGE_NUMERIC_FIELDS}
            out["total_conversation_time_ms"] = float(turn_summary.get("turn_time_ms", 0.0) or 0.0)
            return out
        result = dict.fromkeys(USAGE_NUMERIC_FIELDS, 0.0)
        result["total_conversation_time_ms"] = 0.0
        return result

    if not isinstance(turn_summary, dict):
        turn_summary = {}

    existing = _conversation_usage_totals.get(session_id) or {}
    if not isinstance(existing, dict):
        existing = {}

    updated: dict[str, float] = {}
    for key in USAGE_NUMERIC_FIELDS:
        prev = float(existing.get(key, 0.0) or 0.0)
        delta = float(turn_summary.get(key, 0.0) or 0.0)
        updated[key] = prev + delta

    turn_time_ms = turn_summary.get("turn_time_ms")
    if turn_time_ms is not None and isinstance(turn_time_ms, (int, float)):
        prev_total = float(existing.get("total_conversation_time_ms", 0.0) or 0.0)
        updated["total_conversation_time_ms"] = prev_total + float(turn_time_ms)
    else:
        updated["total_conversation_time_ms"] = float(
            existing.get("total_conversation_time_ms", 0.0) or 0.0
        )

    _conversation_usage_totals[session_id] = updated
    return updated.copy()
