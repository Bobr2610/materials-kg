<!-- 7ca608fd-8a34-4ec0-a212-f7b04406cb57 7605257c-774f-4b84-b6d4-aee9e1a077f3 -->
# Conversational Memory, Citations, and Copy (Gradio-only)

## Scope

- Keep existing Gradio `gr.ChatInterface` in `rag_engine/api/app.py`.
- Add LangChain memory with strict per-session isolation (Gradio session hash).
- Append deduped “Sources” footer to final assistant text; also store citations as metadata.
- Enable Chatbot copy button.

## Key Changes

- **Session ID**
- Use Gradio session hash as `session_id` (no Redis); pass it from `chat_handler` into the chain.

- **Memory (LangChain)**
- Add minimal `ConversationStore` (in-memory) `rag_engine/utils/conversation_store.py`.
- Wrap the chain with `RunnableWithMessageHistory` in `rag_engine/llm/llm_manager.py`, keyed by `session_id`.
- Do not store the system prompt in memory; inject it only at invocation time.

- **Context control**
- Window/trim with `rag_engine/llm/token_utils.py`.
- Compression at threshold: when estimated request tokens exceed `MEMORY_COMPRESSION_THRESHOLD_PCT` of the model window (env), compress all earlier turns except the latest two into one assistant summary using `rag_engine/llm/summarization.summarize_to_tokens` with a dedicated memory-compression prompt in `rag_engine/llm/prompts.py`.
- The compressed message is not shown to the user, replaces older turns in memory, and preserves all reference links inline (compact footer) and as metadata. Target tokens for the compressed turn come from `MEMORY_COMPRESSION_TARGET_TOKENS` (env).

- **Sources/links**
- Ensure URLs available (`metadata.url`/`article_url`, else construct via `kbId`).
- Deduplicate by `kbId`; otherwise by normalized URL (strip anchors/query/trailing slash; lowercase host). No title-based dedup. No formatter-side cap.

- **Gradio UI**
- Keep `type="messages"`, `save_history=True`.
- Set `chatbot=gr.Chatbot(show_copy_button=True)`.

## Env/Settings

- Add to `.env` and surface in `rag_engine/config/settings.py`:
- `MEMORY_COMPRESSION_THRESHOLD_PCT=85`
- `MEMORY_COMPRESSION_TARGET_TOKENS=1000`

## Files to Touch

- `rag_engine/api/app.py`: pass session hash as `session_id`; enable copy button; append footer on final yield only.
- `rag_engine/llm/llm_manager.py`: memory wrapper, request assembly (system prompt inject), compression logic (threshold + target tokens), return text+citations metadata.
- `rag_engine/llm/prompts.py`: add memory-compression prompt.
- `rag_engine/llm/summarization.py`: reuse `summarize_to_tokens` for compression path.
- `rag_engine/retrieval/retriever.py`: ensure article URLs present (`article_url` or `url`).
- `rag_engine/utils/conversation_store.py`: in-memory store keyed by `session_id`.
- `README.md`: brief section on memory, citations, copy button, session isolation, and compression env vars.

## Tests (update/extend)

- Memory isolation across different `session_id`s.
- Footer presence in assistant text; citations also present in metadata.
- Dedup by `kbId`/normalized URL only (no title dedup); no duplicates in edge cases.
- Compression triggers at configured threshold; keeps last two turns intact; compressed turn stored (not shown) and aggregates links; system prompt not persisted.

## References

- Gradio ChatInterface: https://www.gradio.app/guides/chatinterface-examples#lang-chain, https://www.gradio.app/docs/gradio/chatinterface
- LangChain memory/runnables: https://python.langchain.com/docs/concepts/memory/, https://python.langchain.com/docs/concepts/runnables/
- Inspiration only (keep lean): `.reference-repos/.cmw-platform-agent/agent_ng/session_manager.py`, `langchain_memory.py`

## To-dos

- [x] Thread Gradio session hash as `session_id` in `chat_handler`
- [x] Add in-memory `ConversationStore` keyed by `session_id`
- [x] Wrap chain with `RunnableWithMessageHistory` in `llm_manager`
- [x] Implement compression (threshold pct and target tokens from env); keep last two turns; inject system prompt only at call time
- [x] Append footer (dedup by `kbId`/URL) to final assistant message; store citations metadata; ensure URLs in retriever
- [x] Enable `show_copy_button` on Chatbot
- [x] Tests: isolation; footer+metadata; dedup robustness; compression behavior; system prompt not persisted
- [x] Update README.md with memory, citations, copy, session isolation, and compression env vars