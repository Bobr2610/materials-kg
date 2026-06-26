from __future__ import annotations

from typing import Iterable, List, Optional

from kg_engine.llm.prompts import SUMMARIZATION_PROMPT
from kg_engine.llm.token_utils import estimate_tokens_for_request


def summarize_to_tokens(
    *,
    title: str,
    url: str,
    matched_chunks: List[str],
    full_body: Optional[str],
    target_tokens: int,
    guidance: Optional[str],
    llm,
    max_retries: int = 2,
) -> str:
    """Summarize article content to a target token budget.

    Prefers matched chunks; includes full body only if total would fit the
    model context alongside system+question. Falls back to deterministic
    stitching on failures or persistent budget overflow.
    """
    # Build primary source from matched chunks
    chunks_section = "\n\n---\n\n".join(matched_chunks or [])

    # Decide whether to include full body
    system_prompt = SUMMARIZATION_PROMPT
    question = guidance or ""
    base_context = f"Question: {question}\n\nArticle: {title}\nURL: {url}\n\nRelevant chunks:\n\n{chunks_section}".strip()

    context_with_body = base_context
    if full_body:
        tentative_context = base_context + "\n\nFull article (additional context):\n\n" + full_body
        est = estimate_tokens_for_request(
            system_prompt=system_prompt,
            question=question,
            context=tentative_context,
            reserved_output_tokens=target_tokens,  # Use target_tokens as explicit output reservation
            overhead=100,
        )
        # Include full body only if the summarization request itself fits
        if est["total_tokens"] <= llm.get_current_llm_context_window():
            context_with_body = tentative_context

    # Retry loop: tighten target by ~15% if over target
    model = llm._chat_model()  # Use the same provider/model
    current_target = int(max(200, target_tokens))
    for attempt in range(max(1, int(max_retries) + 1)):
        messages = [
            ("system", system_prompt + f"\n\nTarget tokens: ~{current_target}"),
            ("user", context_with_body),
        ]
        try:
            resp = model.invoke(messages)
            output = getattr(resp, "content", "") or ""
        except Exception:
            output = ""

        if not output.strip():
            # Empty output, try next attempt
            current_target = int(current_target * 0.85)
            continue

        # Estimate output tokens; accept if within target
        # Use reserved_output_tokens=0 to just count the output (not reserve space)
        est_out = estimate_tokens_for_request(
            system_prompt="",
            question="",
            context=output,
            reserved_output_tokens=0,  # Just counting, not reserving
            overhead=0,
        )
        if est_out["input_tokens"] <= current_target:
            # Prepend identity header for citations
            header = f"# {title}\n\nURL: {url}\n\n"
            return header + output.strip()

        # Tighten and retry
        current_target = int(current_target * 0.85)

    # Fallback: deterministic stitching of chunks
    header = f"# {title}\n\nURL: {url}\n\n"
    return header + chunks_section


