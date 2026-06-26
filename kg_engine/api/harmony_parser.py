"""Stateful parser for GPT-OSS Harmony-formatted streaming content.

GPT-OSS models use the `Harmony response format`_ which structures output
into three channels:

- **analysis** — chain-of-thought reasoning (internal, not user-facing)
- **commentary** — tool calls, tool responses, and preambles
- **final** — the user-visible answer

When streamed through OpenRouter → LangChain, the special tokens get stripped
and the channel text is flattened into a single string::

    analysisWe need data.assistantcommentary to=functions.retrieve json{...}
    functions.retrieve to=assistantcommentary{...}
    assistantanalysisNow answer.assistantfinal## The Answer

This module provides :class:`HarmonyStreamParser` to incrementally separate
analysis/commentary (→ reasoning bubble) from final (→ chat answer) as tokens
arrive, handling cross-chunk marker boundaries and false positives from
tool-response headers.

.. _Harmony response format:
   https://developers.openai.com/cookbook/articles/openai-harmony/
"""

from __future__ import annotations

CHANNEL_MARKERS: tuple[str, ...] = (
    "assistantfinal",
    "assistantanalysis",
    "assistantcommentary",
)

_MAX_MARKER_LEN: int = max(len(m) for m in CHANNEL_MARKERS)


# ---------------------------------------------------------------------------
# Stateless helpers
# ---------------------------------------------------------------------------

def _find_markers(text: str) -> list[tuple[int, str]]:
    """Locate all Harmony channel markers, skipping tool-response false positives.

    Tool responses flatten to ``functions.xxx to=assistantcommentary{...}`` —
    the ``to=`` prefix distinguishes them from real channel boundaries.
    """
    hits: list[tuple[int, str]] = []
    for marker in CHANNEL_MARKERS:
        start = 0
        while True:
            idx = text.find(marker, start)
            if idx == -1:
                break
            if idx >= 3 and text[idx - 3 : idx] == "to=":
                start = idx + len(marker)
                continue
            hits.append((idx, marker))
            start = idx + len(marker)
    hits.sort()
    return hits


def split(text: str) -> tuple[str, str]:
    """One-shot split of a complete Harmony string into *(reasoning, final)*.

    All ``analysis`` and ``commentary`` content → reasoning.
    All ``assistantfinal`` content → final (user-visible answer).
    Plain text without markers is returned as ``("", text)``.
    """
    if not text:
        return "", ""

    has_markers = any(m in text for m in CHANNEL_MARKERS)
    starts_analysis = text.lstrip().startswith("analysis")

    if not has_markers and not starts_analysis:
        return "", text

    markers = _find_markers(text)

    if not markers:
        stripped = text.lstrip()
        if stripped.startswith("analysis"):
            return stripped[len("analysis"):].lstrip(), ""
        return "", text

    reasoning_parts: list[str] = []
    final_parts: list[str] = []

    # Preamble before the first marker.
    preamble = text[: markers[0][0]].lstrip()
    if preamble:
        if preamble.startswith("analysis"):
            preamble = preamble[len("analysis"):].lstrip()
        if preamble:
            reasoning_parts.append(preamble)

    for i, (pos, marker) in enumerate(markers):
        seg_start = pos + len(marker)
        seg_end = markers[i + 1][0] if i + 1 < len(markers) else len(text)
        segment = text[seg_start:seg_end].strip()
        if not segment:
            continue
        if marker == "assistantfinal":
            final_parts.append(segment)
        else:
            reasoning_parts.append(segment)

    return "\n".join(reasoning_parts).strip(), "\n".join(final_parts).strip()


def _tail_might_be_partial(tail: str) -> bool:
    """Return True if any suffix of *tail* is a prefix of a channel marker."""
    for j in range(len(tail)):
        suffix = tail[j:]
        for marker in CHANNEL_MARKERS:
            if marker.startswith(suffix):
                return True
    return False


# ---------------------------------------------------------------------------
# Stateful streaming parser
# ---------------------------------------------------------------------------

class HarmonyStreamParser:
    """Accumulate streaming chunks and yield *(reasoning_delta, final_delta)*.

    Designed for the Gradio streaming loop — call :meth:`feed` on every new
    text chunk; reasoning deltas go live into the reasoning bubble, final
    deltas go into the chat answer.  Call :meth:`flush` once at end-of-stream
    to emit any content held back for partial-marker safety.

    Usage::

        parser = HarmonyStreamParser()

        for chunk in stream:
            reasoning_delta, final_delta = parser.feed(chunk)
            # reasoning_delta → update reasoning bubble
            # final_delta     → append to chat answer

        reasoning_delta, final_delta = parser.flush()
    """

    __slots__ = ("_buffer", "_prev_reasoning_len", "_prev_final_len")

    def __init__(self) -> None:
        self._buffer: str = ""
        self._prev_reasoning_len: int = 0
        self._prev_final_len: int = 0

    # -- public API ---------------------------------------------------------

    def feed(self, chunk: str) -> tuple[str, str]:
        """Ingest a streaming chunk, return *(new_reasoning, new_final)*."""
        if not chunk:
            return "", ""
        self._buffer += chunk
        return self._extract()

    def flush(self) -> tuple[str, str]:
        """Flush remaining buffer at end-of-stream.

        After this call the parser is reset and can be reused.
        """
        if not self._buffer:
            return "", ""

        reasoning_full, final_full = split(self._buffer)

        r_delta = reasoning_full[self._prev_reasoning_len :]
        f_delta = final_full[self._prev_final_len :]

        self._buffer = ""
        self._prev_reasoning_len = 0
        self._prev_final_len = 0
        return r_delta, f_delta

    # -- internals ----------------------------------------------------------

    def _extract(self) -> tuple[str, str]:
        tail_hold = _MAX_MARKER_LEN - 1

        if len(self._buffer) <= tail_hold:
            return "", ""

        tail = self._buffer[-tail_hold:]
        if _tail_might_be_partial(tail):
            processable = self._buffer[:-tail_hold]
        else:
            processable = self._buffer

        if not processable:
            return "", ""

        reasoning_full, final_full = split(processable)

        r_delta = reasoning_full[self._prev_reasoning_len :]
        f_delta = final_full[self._prev_final_len :]

        self._prev_reasoning_len = len(reasoning_full)
        self._prev_final_len = len(final_full)
        return r_delta, f_delta
