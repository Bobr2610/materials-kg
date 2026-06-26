I skimmed `rag_engine/api/app.py` and focused on repeated patterns and logic that could be moved out.

### How much code is duplicated?

- Approximate duplication: **200–250 lines** show repeated patterns across functions (~18–22% of the file).
- Key duplication clusters:
    - **Token counting with tiktoken + fast-path** appears in 3 places: `_estimate_accumulated_context`, `_check_context_fallback`, `tiktoken_counter` (≈50–70 lines).
    - **Model config lookup with partial-match fallback** appears in 4 places: `_find_model_for_tokens`, `_check_context_fallback`, `_create_rag_agent`, `compress_tool_results_if_needed` (≈40–60 lines).
    - **Model fallback selection logic** appears twice: real-time switch mid-run and exception handler retry (≈50–70 lines).
    - **Tool streaming filtering and UI metadata yield** patterns duplicated between normal stream and fallback retry (≈30–50 lines).
    - **JSON tool result parse/compress/rewrite** flows duplicated between `compress_tool_results_if_needed` and stream handlers (≈40–60 lines).
    - There is also conceptual duplication between `_estimate_accumulated_context` and the imported `estimate_accumulated_tokens(...)`.

### How much can be extracted to utility methods?

You can comfortably extract and deduplicate roughly **300–400 lines** (≈25–35% of the file) into cohesive utilities/factories/middleware modules. Suggested extractions:

- Token utils (centralize all token counting)
    - **Add** to `rag_engine/llm/token_utils.py`:
        - `count_text_tokens(content: str) -> int` with exact/fast-path logic (chars//4 for >50K chars).
        - `count_messages_tokens(messages: list[dict|LCMessage]) -> int` using the above and handling dict/LC messages.
    - **Replace** all in-file `tiktoken` counting implementations and references to `_estimate_accumulated_context` with shared utilities. Also reconcile with existing `estimate_accumulated_tokens` to eliminate overlap.

- Model config helpers
    - **Add** to `rag_engine/llm/llm_manager.py` (or new `llm/model_config.py`):
        - `get_model_config(model_name: str) -> dict` with partial-match fallback.
        - `get_context_window(model_name: str) -> int`
        - `find_fallback_model(required_tokens: int, allowed: list[str]) -> str|None` (with 10% buffer).
    - **Replace** repeated config lookup and scanning logic in `_find_model_for_tokens`, `_check_context_fallback`, `_create_rag_agent`, `compress_tool_results_if_needed`.

- Context thresholds and budgeting
    - **Add** to `rag_engine/utils/context_tracker.py`:
        - `compute_thresholds(window: int, pre_pct: float, post_pct: float) -> tuple[int,int]`
        - `estimate_accumulated_context(messages, tool_results) -> int` (merge with existing `estimate_accumulated_tokens` to avoid parallel implementations).
    - **Use** the same functions in `_check_context_fallback`, mid-turn fallback checks, and error fallback retry.

- Tool message parsing and accumulation
    - You already have `parse_tool_result_to_articles` and `accumulate_articles_from_tool_results`.
    - **Add** to `rag_engine/tools/utils.py`:
        - `is_tool_message(msg) -> bool`
        - `extract_user_question(messages) -> str`
        - `update_tool_message_content(messages, index, new_json_str) -> list`
    - **Replace** scattered checks for `msg.type == "tool"`, and repeated extraction of user question.

- Compression utilities
    - **New** `rag_engine/llm/compression.py`:
        - `compress_articles_to_target_tokens(articles, target_ratio=0.30, min_tokens=300, guidance: str|None, llm_manager) -> tuple[new_articles, saved_tokens]`
        - `compress_tool_messages_if_needed(messages, runtime, llm_manager, threshold_pct=0.85, target_pct=0.80)`
    - **Move** `compress_tool_results_if_needed` logic into this module; keep only a thin middleware wrapper in `app.py`.

- Agent factory
    - **New** `rag_engine/llm/agent_factory.py`:
        - `create_rag_agent(override_model: str|None, settings, retrieve_context, AgentContext, middleware...)`
    - **Move** `_create_rag_agent` there. `app.py` should just call the factory.

- Fallback management
    - **New** `rag_engine/llm/fallback.py`:
        - `check_context_fallback(messages) -> str|None` (unify `_check_context_fallback` with shared token counters + model config helpers).
        - `maybe_switch_model_mid_turn(current_model, messages, tool_results, allowed_fallbacks) -> str|None`
    - **Replace** the duplicated mid-turn switch and exception-retry logic to call shared helpers.

- Streaming/UI metadata helpers
    - **New** `rag_engine/api/stream_helpers.py`:
        - `yield_search_started() -> dict`
        - `yield_search_completed(count: int|None) -> dict`
        - `yield_model_switch_notice(model: str) -> dict`
        - `append_text_stream(answer: str, chunk: str) -> str`
    - **Replace** duplicated UI metadata yields and answer text concatenation.

- Session id salt
    - **Move** `_salt_session_id(...)` to `rag_engine/utils/conversation_store.py` or `rag_engine/utils/git_utils.py` sibling utility, since it’s generic.

Net result: `app.py` becomes a slim orchestrator: config, wiring, and Gradio view; business logic lives in utilities/modules.

- **Benefit**: Lower cyclomatic complexity, clear separation of concerns, easier testability (you can add targeted tests under `rag_engine/tests` for tokenization, fallback selection, compression, and stream filtering), and fewer places to fix when behavior changes.

If you want, I can create the utility modules and refactor `app.py` accordingly in small, safe edits with Ruff checks after each step.

I'll scan `rag_engine/api/app.py` to quantify duplication and identify refactorable utility functions.

[1 tool called]

I’m going to review `rag_engine/api/app.py` for duplicated logic and extractable utilities, focusing on token counting, model config selection, and agent context updates.

### How much code is duplicated?

- Roughly 8–12% of the file repeats similar patterns (token counting logic, model config resolution, context-window thresholds, and agent-context updates).
- You have 4+ instances of near-identical token counting and 4–5 places resolving `MODEL_CONFIGS` with partial-match fallback, plus two places updating `runtime.context`.

Examples (code references):

```156:171:C:\Users\webma\.cursor\worktrees\cmw-rag\zhS3y\rag_engine\api\app.py
    from rag_engine.llm.llm_manager import MODEL_CONFIGS

    # Get current model config
    model_config = MODEL_CONFIGS.get(settings.default_model)
    if not model_config:
        # Try partial match
        for key in MODEL_CONFIGS:
            if key != "default" and key in settings.default_model:
                model_config = MODEL_CONFIGS[key]
                break
    if not model_config:
        model_config = MODEL_CONFIGS["default"]
```
```568:577:C:\Users\webma\.cursor\worktrees\cmw-rag\zhS3y\rag_engine\api\app.py
    model_config = MODEL_CONFIGS.get(selected_model)
    if not model_config:
        # Try partial match
        for key in MODEL_CONFIGS:
            if key != "default" and key in selected_model:
                model_config = MODEL_CONFIGS[key]
                break
    if not model_config:
        model_config = MODEL_CONFIGS["default"]
```
```173:190:C:\Users\webma\.cursor\worktrees\cmw-rag\zhS3y\rag_engine\api\app.py
    encoding = tiktoken.get_encoding("cl100k_base")
    fast_path_threshold = 50_000  # chars
    total_tokens = 0
    for msg in messages:
        # Handle both dict (Gradio) and LangChain message objects
        if hasattr(msg, "content"):
            content = msg.content  # LangChain message object
        else:
            content = msg.get("content", "")  # Dict from Gradio
        if isinstance(content, str) and content:
            # Use fast approximation for very large content
            if len(content) > fast_path_threshold:
                total_tokens += len(content) // 4
            else:
                total_tokens += len(encoding.encode(content))
```
```584:609:C:\Users\webma\.cursor\worktrees\cmw-rag\zhS3y\rag_engine\api\app.py
    encoding = tiktoken.get_encoding("cl100k_base")
    fast_path_threshold = 50_000  # chars

    def tiktoken_counter(messages: list) -> int:
        ...
        for msg in messages:
            if hasattr(msg, "content"):
                content = msg.content
            else:
                content = msg.get("content", "")
            if isinstance(content, str) and content:
                if len(content) > fast_path_threshold:
                    total += len(content) // 4
                else:
                    total += len(encoding.encode(content))
```
```472:483:C:\Users\webma\.cursor\worktrees\cmw-rag\zhS3y\rag_engine\api\app.py
        if hasattr(runtime, "context") and runtime.context:
            runtime.context.conversation_tokens = conv_toks
            runtime.context.accumulated_tool_tokens = tool_toks
            logger.debug(
                "Updated runtime.context: conversation_tokens=%d, accumulated_tool_tokens=%d",
                conv_toks,
                tool_toks,
            )
```
```510:519:C:\Users\webma\.cursor\worktrees\cmw-rag\zhS3y\rag_engine\api\app.py
            if state and runtime is not None and hasattr(runtime, "context") and runtime.context:
                conv_toks, tool_toks = _compute_context_tokens_from_state(state.get("messages", []))
                runtime.context.conversation_tokens = conv_toks
                runtime.context.accumulated_tool_tokens = tool_toks
                logger.debug(
                    "[ToolBudget] runtime.context updated before tool: conv=%d, tools=%d",
                    conv_toks,
                    tool_toks,
                )
```

### How much can be extracted to utility methods?

You can extract ~150–200 lines into small, reusable utilities. Suggested extractions:

- Model configuration helpers:
    - `get_model_config(model_name: str) -> dict`
    - `get_context_window(model_name: str) -> int`
- Token counting utilities:
    - `count_text_tokens(text: str) -> int` (tiktoken with fast-path)
    - `count_messages_tokens(messages: list) -> int`
- Message helpers:
    - `get_message_content(msg) -> str`
    - `get_message_type(msg) -> str | None`
- Context budgeting and fallback:
    - `estimate_required_tokens(messages: list, tool_jsons: list[str]) -> int`
    - `find_fallback_model(required_tokens: int) -> str | None` (generalize `_find_model_for_tokens`)
    - `should_fallback(messages: list, current_model: str, pct: float) -> str | None` (wraps `_check_context_fallback`)
- Agent context synchronization:
    - `update_runtime_context_tokens(messages: list, runtime_context: AgentContext) -> None` (shared by middleware and `update_context_budget`)
- Tool result processing:
    - `parse_tool_result_articles(json_str: str) -> list[Article]` (centralize parsing and error handling)
    - `compress_articles_to_budget(articles, target_tokens, guidance, llm_manager) -> tuple[articles, tokens_saved]`
- Session utilities:
    - `_salt_session_id` is already standalone; keep as-is.

### Impact

- Reduces duplication and cognitive load.
- Centralizes token counting and model-window logic, making thresholds consistent.
- Makes middleware and handler code leaner and easier to test.

If you’d like, I can implement these utilities in `rag_engine/utils/` and refactor `app.py` accordingly, then run Ruff on the changed files.

- I found repeated blocks for token counting, model config lookup, and context updates. I can extract small utilities to cut ~150–200 lines from `app.py` and improve consistency across handlers and middleware.

I'll scan `rag_engine/api/app.py` to quantify duplication and identify refactorable utilities. Then I'll report concrete extraction candidates.

[1 tool called]

I skimmed the whole `rag_engine/api/app.py` to quantify duplication and spot clean extractions.

### How much code is duplicated?

- Overall near-duplicate or copy/variant logic is about 180–220 lines, roughly 16–19% of the file.
- After consolidating into helpers, you could likely remove 120–150 lines net (10–13% of file), improving clarity and testability.

### High-signal duplication and extraction candidates

- Token counting of messages (tiktoken fast-path)
    - Appears in 3 places with very similar logic:
        - ```56:95:rag_engine/api/app.py

def _estimate_accumulated_context(messages: list[dict], tool_results: list) -> int:

import tiktoken

encoding = tiktoken.get_encoding("cl100k_base")

fast_path_threshold = 50_000

total_tokens = 0

# ... counts messages, then tool JSONs, adds a big overhead ...

return total_tokens

````
    - ```173:193:rag_engine/api/app.py
    # Estimate tokens using tiktoken with fast path for large strings
    encoding = tiktoken.get_encoding("cl100k_base")
    fast_path_threshold = 50_000  # chars
    total_tokens = 0
    for msg in messages:
        # Handle both dict and LC message objects, encode or approx chars//4
        # ...
````

        - ```583:610:rag_engine/api/app.py

# Custom token counter using tiktoken with fast path for large strings

encoding = tiktoken.get_encoding("cl100k_base")

fast_path_threshold = 50_000  # chars

def tiktoken_counter(messages: list) -> int:

total = 0

for msg in messages:

# Handle dict or LC message, encode or approx chars//4

# ...

return total

````
  - Extract to `rag_engine/llm/token_utils.py`:
    - `count_text_tokens_fast(text: str) -> int`
    - `count_messages_tokens_fast(messages: list[Any]) -> int`
    - Optional: `estimate_messages_plus_tool_json_tokens(messages, tool_jsons, overhead=40000)`

- Model config lookup (with partial match and default)
  - Same “get config for model or its family key” appears 4 times:
    - ```158:170:rag_engine/api/app.py
from rag_engine.llm.llm_manager import MODEL_CONFIGS
# ... get settings.default_model, partial match fallback, use default
````

        - ```568:577:rag_engine/api/app.py

model_config = MODEL_CONFIGS.get(selected_model)

# ... partial match, then default

````
    - ```276:285:rag_engine/api/app.py
current_model = getattr(runtime, "model", None) or settings.default_model
model_config = MODEL_CONFIGS.get(current_model)
# ... partial match, then default
````

        - ```788:791:rag_engine/api/app.py

model_config = MODEL_CONFIGS.get(current_model, MODEL_CONFIGS["default"])

context_window = model_config.get("token_limit", 262144)

```

    - Extract to `rag_engine/llm/llm_manager.py` or `rag_engine/llm/token_utils.py`:
        - `get_model_config_for(model_name: str) -> dict`
        - `get_model_context_window(model_name: str, default: int = 262144) -> int`

- Mid-turn context fallback check and thresholds
    - Threshold and fallback logic spread across:
        - Pre-agent check: ```143:245:rag_engine/api/app.py``` (90% threshold, +35k overhead)
        - Mid-tool check: ```792:825:rag_engine/api/app.py``` (80% threshold, uses `_estimate_accumulated_context` and `_find_model_for_tokens`)
        - Error retry path: ```917:945:rag_engine/api/app.py``` (recompute, `_find_model_for_tokens`)
    - Extract to a single strategy:
        - `should_fallback_for_context(messages, tool_jsons, threshold_pct, overhead, buffer_pct) -> tuple[bool, required_tokens]`
        - Reuse `_find_model_for_tokens(required_tokens)`

- Stream handling duplication (filtering tool calls vs text, metadata)
    - The streaming loop filters tool messages, yields metadata, accumulates text; similar logic duplicated in fallback retry loop:
        - Main loop core: ```740:882:rag_engine/api/app.py```
        - Retry loop core: ```951:975:rag_engine/api/app.py```
    - Extract helpers to `rag_engine/api/stream_utils.py`:
        - `process_stream_chunk(token, tool_executing_state) -> StreamAction`
        - Or a wrapper generator: `stream_agent_text_only(agent, messages, context) -> Iterator[str]` that also returns `tool_results` via out-params/callback.

- Uniform “partial message” handling for LangChain vs dict messages
    - The pattern `content = msg.content if hasattr(msg, "content") else msg.get("content", "")` repeats across multiple blocks; centralize via a tiny accessor:
        - `get_message_content(msg: Any) -> str | None`
        - `get_message_type(msg: Any) -> str | None`
    - Then reuse in token estimation and stream processing.

- Reusable logging and UI metadata events
    - “🔍 Searching…” and “✅ Found … articles” metadata blocks appear multiple times; extract constants or a small emitter:
        - `emit_searching_metadata()`, `emit_found_metadata(count)`

### Concrete refactorable units (where to move)

- To `rag_engine/llm/token_utils.py` (already exists; stay LangChain-pure):
    - `count_text_tokens_fast`
    - `count_messages_tokens_fast`
    - `estimate_messages_plus_tool_json_tokens`
    - `get_model_config_for` (or keep in `llm_manager`) and `get_model_context_window`

- To `rag_engine/api/stream_utils.py` (new):
    - `get_message_content`, `get_message_type`
    - `process_stream_token(...)` or a `stream_agent_text_only(...)` helper
    - Metadata emitters (pure dict constructors)

- Keep `_find_model_for_tokens` here or move to `llm_manager` to consolidate model fallback policy.

### Ballpark impact

- Remove 3 separate tiktoken implementations → -90 to -120 lines.
- Remove 3–4 model config lookup blocks → -30 to -40 lines.
- Consolidate mid-turn and retry streaming filters → -40 to -60 lines.
- Net reduction: ~120–150 lines, with improved cohesion and easier testing.

### Optional quick wins

- Replace local token counting in `_check_context_fallback` with `count_messages_tokens_fast`.
- Replace direct `MODEL_CONFIGS` reads with `get_model_config_for`.
- Factor shared streaming filters used in both main and retry loops.

- I can implement these extractions next, keeping behavior identical and running Ruff on the touched files only.