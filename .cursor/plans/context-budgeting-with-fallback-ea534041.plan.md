<!-- ea534041-88dc-4ccd-a262-f568e9b2edea 8d4c6a81-547c-439d-aee6-557b40f1fac2 -->
# Summarization-First Budgeting with Immediate Fallback

## Overview

- If fallback is enabled, immediately switch to a larger allowed model when estimated tokens exceed the current model.
- If still over budget, prefer LLM-based summarization of lowest‑rank articles to a target token budget, guided by the original user question.
- Only if summarization cannot fit the window, fall back to lightweight chunk stitching (title + URL + matched chunks).

## Changes

### 0) Token utility (shared)

- Add `rag_engine/llm/token_utils.py`:
- `estimate_tokens_for_request(system_prompt: str, question: str, context: str, max_output_tokens: int, overhead: int = 100) -> dict`
- Used by LLMManager and Retriever (single source of truth)

### 1) Config: Allowed fallback + summarization (.env + settings)

- Add `LLM_FALLBACK_ENABLED=false`
- Add `LLM_ALLOWED_FALLBACK_MODELS="gemini-2.5-pro,x-ai/grok-4-fast"`
- Add `LLM_SUMMARIZATION_ENABLED=true`
- Add `LLM_SUMMARIZATION_TARGET_TOKENS_PER_ARTICLE=1200` (or use a global cap `LLM_SUMMARIZATION_TARGET_TOKENS_TOTAL_RATIO=0.25`)
- Parse comma list and provide sane defaults

### 2) LLM Manager: token estimate + immediate fallback

- `_estimate_request_tokens(question, context)` (tiktoken: system+question+context+overhead+max_output)
- `_get_fallback_model(required_tokens, allowed)`; `_create_manager_for(model)`
- `stream_response(question, docs, enable_fallback, allowed_models)` does immediate fallback before any trimming/summarization

### 3) Summarization helper (new, question-guided, dual-source)

- Add `rag_engine/llm/summarization.py`:
- `summarize_to_tokens(title: str, url: str, matched_chunks: list[str], full_body: str | None, target_tokens: int, guidance: str, llm: LLMManager, max_retries=2) -> str`
- The function itself decides source inclusion:
- Start with matched_chunks as primary source.
- Use shared token utility to check if adding `full_body` (with system+question context) still fits the model window; if yes, include it; otherwise, proceed with chunks-only.
- Prompt: stored in `rag_engine/llm/prompts.py` (separation of concerns). Guidance: focus on answering the user question using ONLY provided content; prioritize matched chunks; boost code/config/CLI examples; avoid speculation; adhere to target tokens.
- On failure or if output still exceeds target after retries, fall back to deterministic stitching: `# {title}\n\nURL: {url}\n\n` + joined chunks.

### 4) Retriever: summarization-first budgeting

- Extract `_create_lightweight_article(article)` for reuse
- Extend `_apply_context_budget(articles, question: str = "", system_prompt: str = "")`:

1. Compute reserved tokens (system + question + output + overhead)
2. Run first pass (full articles) until near budget
3. For overflow articles (lowest rank first): if `LLM_SUMMARIZATION_ENABLED`, summarize each to `target_tokens` and replace; re-check budget after each summary
4. If still over: convert remaining full articles to lightweight until it fits

- Update `retrieve()` to pass `question=query`

### 5) API app integration

- Pass fallback flags and allowed models to `llm_manager.stream_response`
- No UI/state changes; chat history remains visible

## Key Points (Lean/DRY)

- Single token-counter (tiktoken) reused in manager + retriever
- Summarizer is a tiny, isolated utility; uses same LLM instance
- Minimal change surface; preserves current flow; trimming remains as last resort

## Files Modified / Added

- Modify: `rag_engine/config/settings.py` (new envs, parsing)
- Modify: `rag_engine/llm/llm_manager.py` (estimate tokens, fallback helpers)
- Modify: `rag_engine/retrieval/retriever.py` (summarization-first budgeting, helper extraction)
- Modify: `rag_engine/api/app.py` (wire settings)
- Add: `rag_engine/llm/summarization.py` (helper)

## .env additions (example)

- `LLM_FALLBACK_ENABLED=false`
- `LLM_ALLOWED_FALLBACK_MODELS="gemini-2.5-pro,x-ai/grok-4-fast"`
- `LLM_SUMMARIZATION_ENABLED=true`
- `LLM_SUMMARIZATION_TARGET_TOKENS_PER_ARTICLE=1200`

## Todos

- cfg-fallback: Add fallback flags and allowed models list parsing to settings
- cfg-summarization: Add summarization flags and target tokens parsing
- llm-estimate-fallback: Add token estimate and immediate fallback logic to LLMManager
- summarize-helper: Add summarization helper module using same LLM
- retriever-summarize-first: Extend budgeting to summarize overflow articles before chunk stitching
- retriever-lightweight-helper: Extract lightweight creation helper
- retriever-pass-question: Pass question to budgeting in retrieve()
- api-wire-fallback: Wire flags/models into stream_response call

### To-dos

- [ ] Add _is_lightweight flag to Article class
- [ ] Extract lightweight creation logic into reusable _create_lightweight_article helper method
- [ ] Extend _apply_context_budget to accept question/system_prompt and add iterative trimming pass
- [ ] Update retrieve method to pass question to _apply_context_budget
- [ ] Add accurate token counting method to LLMManager using tiktoken
- [ ] Add model fallback methods (_get_fallback_model, _create_fallback_manager) to LLMManager
- [ ] Update stream_response to use accurate counting and optional fallback
- [ ] Add get_system_prompt() method to LLMManager for retriever access
- [ ] Add llm_fallback_enabled and llm_fallback_models settings with list parser
- [ ] Update chat_handler to pass fallback settings and system_prompt to retriever/llm_manager