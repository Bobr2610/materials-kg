---
name: reasoning-safety-net-alignment
overview: Align Harmony reasoning interception with think-tag safety net so that reasoning is fully stripped (but not stored) when disabled, and correctly routed to bubbles/diagnostics when enabled, using TDD/SDD and non-breaking changes.
todos:
  - id: analyze-current-reasoning-flow
    content: Re-read reasoning, Harmony, and diagnostics handling in app.py and llm_manager.py to confirm all entry points and side effects.
    status: pending
  - id: spec-reasoning-enabled-disabled-contracts
    content: Formalize behavior contracts for reasoning enabled vs disabled (UI, diagnostics, bubbles) to guide TDD.
    status: pending
  - id: add-tests-disabled-harmony-safety
    content: Add tests for Harmony reasoning when reasoning is disabled, asserting it is stripped from UI and not stored in diagnostics.
    status: pending
  - id: add-tests-enabled-regressions
    content: Ensure existing or new tests cover reasoning-enabled behavior and prevent regressions (bubbles and diagnostics).
    status: pending
  - id: implement-harmony-strip-only-mode
    content: Update _process_reasoning_chunk, _apply_reasoning_chunk, and Harmony flush paths to support strip-only sanitization independent of reasoning_enabled, while keeping capture behind the flag.
    status: pending
  - id: run-and-verify-tests
    content: Run the focused reasoning-related tests and fix issues until everything passes without breaking other suites.
    status: pending
isProject: false
---

### Goal

Align Harmony reasoning and `<think>` reasoning handling so that:

- **When reasoning is disabled**: any “thoughts” are **sanitized from user-visible output** and **never stored** in diagnostics or bubbles.
- **When reasoning is enabled**: Harmony and `<think>` channels are **captured consistently** into the reasoning buffer, bubble, and diagnostics, without leaking into the main answer.
- All changes are **backed by tests (TDD)** and preserve existing behavior where not explicitly changed.

### High-level approach

- **Understand current behavior**
  - Review reasoning configuration in `[rag_engine/llm/llm_manager.py](rag_engine/llm/llm_manager.py)` (especially `_build_reasoning_extra_body`) and how `llm_reasoning_enabled` is used.
  - Review reasoning streaming and Harmony handling in `[rag_engine/api/app.py](rag_engine/api/app.py)`:
    - `_parse_think_tags`, `_ReasoningCtx`, `_process_reasoning_chunk`, `_apply_reasoning_chunk`.
    - Harmony usage via `HarmonyStreamParser` (feed/flush, `reasoning_content`, `content_blocks` with `type=="reasoning"`).
    - Finalization logic for `_finalize_reasoning_bubble` and diagnostics population.
  - Review existing tests in `[rag_engine/tests/test_api_app.py](rag_engine/tests/test_api_app.py)` that cover reasoning, Harmony parsing, and bubbles.
- **Specify desired behavior (SDD level)**
  - **Reasoning enabled** (`settings.llm_reasoning_enabled=True`):
    - All reasoning channels (Harmony `reasoning_content`, Harmony `content_blocks` of type `"reasoning"`, `<think>...</think>` blocks) feed into `rctx.buffer`.
    - `rctx.buffer` is used to drive the reasoning bubble and `diagnostics["reasoning"]`.
    - No reasoning content appears in the main answer text.
  - **Reasoning disabled** (`settings.llm_reasoning_enabled=False`):
    - The model is configured with `{"reasoning": {"effort": "none", "exclude": true}}` where supported.
    - Do **not** populate `rctx.buffer` or `diagnostics["reasoning"]` from Harmony or `<think>` when disabled.
    - Apply a **minimal strip-only heuristic** for safety:
      - Treat a `<think>...</think>` block as reasoning only when it is a clean **leading block** (Qwen-style) or the **entire** assistant turn; strip it from the answer but do not store it.
      - In all other cases (mid-sentence tags, docs, examples), leave `<think>` text untouched so final answers are not corrupted.
      - For Harmony, optionally strip obvious leaked `analysis` / `commentary` fragments from the answer, but never route them into `rctx.buffer` or diagnostics when disabled.
    - Existing non-reasoning behavior (answers, bubbles unrelated to reasoning, diagnostics for guard/usage) remains unchanged.
- **Design Harmony “safety net” aligned with think-tag safety net**
  - Introduce a clear separation between two roles:
    - **Sanitization role**: remove reasoning-like channels from user-visible content (always-on when Harmony is used).
    - **Capture role**: when `llm_reasoning_enabled=True`, accumulate sanitized reasoning into `rctx.buffer` and diagnostics.
  - Reuse the existing `harmony_strip_only` flag in `_process_reasoning_chunk` and `_apply_reasoning_chunk`:
    - Ensure that **strip-only mode can run even when `reasoning_enabled` is False** (sanitization without capture).
    - Retain current behavior where, when reasoning is enabled, `harmony_strip_only` is used to avoid double-processing of reasoning segments while still capturing content.
- **TDD: extend and add tests first**
  - In `[rag_engine/tests/test_api_app.py](rag_engine/tests/test_api_app.py)`:
    - **Existing tests**: read and keep as behavioral spec for current reasoning-enabled behavior.
    - **New tests for disabled mode**:
      - A test where `llm_reasoning_enabled=False` and a synthetic Qwen-style response includes `<think>hidden</think>Visible answer`:
        - Ensure the **final answer contains `Visible answer` intact**, and `diagnostics` has **no `"reasoning"` key**.
      - A test where `llm_reasoning_enabled=False` but the answer explains `<think>...</think>` literally:
        - Assert that the user-visible content preserves the explanation text unchanged.
      - A test where `llm_reasoning_enabled=False` and a synthetic Harmony-streamed response includes leaked analysis/commentary:
        - Ensure any stripped fragments do not corrupt the final answer and are **not** stored in diagnostics.
    - **New / regression tests for enabled mode**:
      - Qwen-style `<think>hidden</think>Visible answer` with `llm_reasoning_enabled=True`:
        - Assert `Visible answer` is fully present in the answer, and `diagnostics["reasoning"]` (and the reasoning bubble) contain `hidden`.
      - Confirm that existing Harmony reasoning tests still pass:
        - Reasoning is captured into `diagnostics["reasoning"]`.
        - The reasoning bubble shows tail text only, as before.
  - Keep tests **behavior-focused**: assert on visible answer text, presence/absence of diagnostics fields, and bubble text, not on internal call sequences.
- **Implement behavior changes (guided by tests)**
  - In `[rag_engine/api/app.py](rag_engine/api/app.py)`:
    - **Adjust `_process_reasoning_chunk`**:
      - Refactor the `if reasoning_enabled:` block so that Harmony parsing and `<think>` parsing can operate in two modes:
        - **Sanitize-only mode**: invoked when Harmony/think content must be stripped but **not** recorded (e.g., `not reasoning_enabled` but `harmony_strip_only=True`).
        - **Full capture mode**: invoked when `reasoning_enabled=True` allowing updates to `ctx.buffer`, bubbles, and diagnostics.
      - Use the `harmony_strip_only` flag to drive whether `h_reasoning` is appended to `ctx.buffer` or just used to clean text.
    - **Adjust Harmony flush (`harmony_parser.flush()`)**:
      - When reasoning is enabled, continue to append `h_reasoning` to `rctx.buffer` and add `h_final` to the answer.
      - When reasoning is disabled, flush should **only clean/sanitize any dangling Harmony markers** without populating `rctx.buffer`.
    - Keep `_update_or_append_assistant_message` as the final `<think>` safety net but ensure it doesn’t unexpectedly reintroduce reasoning when new Harmony logic is in place.
  - **Do not modify** request-side behavior in `llm_manager.py` beyond using it as a reference; it already correctly configures providers when reasoning is disabled.
- **Wire reasoning diagnostics consistently**
  - Keep diagnostics wiring (at the end of `agent_chat_handler`) so that:
    - `diagnostics["reasoning"]` is set **only** when `llm_reasoning_enabled=True` and `rctx.buffer.strip()` is non-empty.
    - When disabled, tests should confirm `"reasoning" not in diagnostics`.
- **Refine and harden tests**
  - Run the reasoning-related tests focused on API app streaming logic and reasoning bubbles.
  - If needed, add small focused unit tests around `_truncate_reasoning_text` and `_finalize_reasoning_bubble` to ensure no regressions in how much reasoning is shown when it is enabled.
- **Non-breaking and cleanliness checks**
  - Carefully compare behavior for the enabled path against existing tests to ensure no change in public behavior except where explicitly intended.
  - Keep changes minimal and isolated to reasoning/Harmony paths in `app.py`, avoiding broader refactors.
  - Maintain clarity and abstraction: no duplicated parsing logic, reuse helpers like `_parse_think_tags` and `HarmonyStreamParser` cleanly.

### Implementation todos

- **analyze-current-reasoning-flow**: Re-read the reasoning and Harmony handling paths in `app.py` and `llm_manager.py` to confirm all entry points and side effects.
- **spec-reasoning-enabled-disabled-contracts**: Write down exact behavior contracts for reasoning enabled vs disabled (UI, diagnostics, bubbles) and use them to guide tests.
- **add-tests-disabled-harmony-safety**: Add TDD tests for Harmony + reasoning disabled, verifying stripping from UI and absence from diagnostics.
- **add-tests-enabled-regressions**: Add or tighten tests ensuring reasoning-enabled behavior remains unchanged (capture into bubble + diagnostics only).
- **implement-harmony-strip-only-mode**: Adjust `_process_reasoning_chunk`, `_apply_reasoning_chunk`, and Harmony flush handling to support strip-only sanitization when reasoning is disabled.
- **run-and-verify-tests**: Run the targeted test suite and adjust implementation until all reasoning tests pass and existing unrelated tests remain green.

