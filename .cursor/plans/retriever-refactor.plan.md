# Retriever Refactor: Clean Separation of Concerns

> **Validation Status**: ✅ **VALIDATED AND APPROVED** (see `retriever-refactor-validation.md`)

> **Last Validated**: 2025-01-28

> All line numbers verified against current codebase.

## Executive Summary

This refactor removes context budgeting and compression logic from the retrieval layer (`retriever.py` and `retrieve_context.py`) and moves it to the agent middleware layer. The retrieval layer will **only** retrieve uncompressed articles with ranking information. The agent middleware (`before_model`) will handle:

1. Accumulating all articles from all tool calls
2. Deduplicating by `kb_id` (preserving highest rank)
3. Checking if fallback LLM is needed
4. Compressing articles proportionally by rank when context limit is approached
5. Updating tool messages with compressed articles

## Architecture Goals

**Clean Separation of Concerns:**

- **Tools** (`retrieve_context.py`): Retrieve and return uncompressed ranked articles. NO token counting, NO budgeting.
- **Retriever** (`retriever.py`): Return all uncompressed articles with preserved ranks. NO compression logic.
- **Agent Middleware** (`before_model` in `app.py`): Handle ALL compression and fallback logic AFTER all tool calls complete.

## Current Architecture Problems

### 1. `retrieve_context.py` (lines 226-254)

**Problem**: Tool counts tokens and passes `reserved_tokens` to retriever

```python
# ❌ WRONG: Tool should not care about tokens
conversation_tokens = runtime.context.conversation_tokens
accumulated_tool_tokens = runtime.context.accumulated_tool_tokens
total_reserved_tokens = conversation_tokens + accumulated_tool_tokens
docs = retriever.retrieve(query, top_k=top_k, reserved_tokens=total_reserved_tokens)
```

**Should be**: Simply retrieve and return uncompressed articles with ranks

```python
# ✅ CORRECT: Just retrieve, no token counting
docs = retriever.retrieve(query, top_k=top_k)
return _format_articles_to_json(docs, query, top_k)
```

### 2. `retriever.py` (line 270)

**Problem**: Calls `_apply_context_budget()` which compresses articles inside the retriever

```python
# ❌ WRONG: Compression should be in agent middleware
articles = self._apply_context_budget(articles, question=query, reserved_tokens=reserved_tokens)
```

**Should be**: Return all articles uncompressed with rank information

```python
# ✅ CORRECT: No compression in retriever
return articles  # All uncompressed, with ranks preserved
```

### 3. `retriever.py` (lines 297-504): `_apply_context_budget()` method

**Problem**: Entire compression logic is in the wrong place

- Compresses articles per tool call instead of after all tool calls
- Creates "lightweight" articles (line 459) instead of using LLM summarization
        - **Validated**: `_create_lightweight_article()` nested function exists at line 459
- Doesn't handle proportional compression by rank across all accumulated articles
- Contains token counting, context window calculation, and budget allocation logic that belongs in agent middleware
        - **Validated**: Method contains context window calculation (line 324), token reservation (lines 330-340), JSON overhead margin (lines 342-349)

**Should be**: Moved to agent middleware that runs `before_model` (after ALL tool calls)

### 4. Missing rank preservation

**Problem**: Reranker scores exist but aren't stored with articles for proportional compression

- Chunks are scored by reranker (lines 205-210 in `retriever.py`)
- Scores are lost when grouping by `kb_id` (lines 218-226; score prefixed with `_` at line 219)
- No rank information in returned articles (validated: no `rerank_score` or `normalized_rank` in codebase)

**Should be**: Store max reranker score per article and normalize ranks (0.0=best, 1.0=worst)

### 5. Compression timing

**Problem**: Compression happens per tool call instead of AFTER ALL tool calls complete

- Each tool call compresses independently
        - **Validated**: `compress_tool_messages()` processes messages individually in reversed order (lines 178-224 in `compression.py`)
- Cannot optimize across all accumulated articles
- Wastes compression opportunities on duplicate articles
        - **Validated**: No deduplication across tool messages in current implementation

**Should be**: Compress once after all tool calls, with deduplication

## Correct Architecture Flow

```
User asks question
    ↓
LLM agent calls retrieve_context tool multiple times
    ↓
retrieve_context tool:
 - Calls retriever.retrieve(query, top_k)
 - Returns uncompressed articles with ranks (JSON)
    ↓
retriever.retrieve():
 - Vector search → rerank chunks → group by kb_id
 - Preserve max reranker score per article
 - Read complete articles from filesystem
 - Store rerank_score and normalized_rank in article.metadata
 - Return ALL articles uncompressed (no budgeting!)
    ↓
Agent accumulates tool results (happens automatically)
    ↓
before_model middleware (AFTER ALL tool calls):
 1. Extract ALL articles from ALL tool messages
 2. Deduplicate by kb_id (preserve highest rerank_score)
 3. Re-normalize ranks after deduplication. High ranks from different retrieval batches must still remain high.
 4. Check total tokens vs context window
 5. Decide: Fallback LLM? OR Compress proportionally by rank?
 6. Update tool messages with compressed articles
    ↓
LLM generates answer with compressed/deduplicated articles
```

## Required Changes

### 1. `retrieve_context.py` — Remove ALL token counting

**Location**: `rag_engine/tools/retrieve_context.py`

**Changes**:

- Remove lines 226-254 (all token counting logic)
- Remove `reserved_tokens` parameter from `retriever.retrieve()` call
- Update docstring to clarify tool returns uncompressed articles

**After**:

```python
@tool("retrieve_context", args_schema=RetrieveContextSchema)
def retrieve_context(
    query: str,
    top_k: int | None = None,
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> str:
    """Retrieve relevant context documents from the knowledge base using semantic search.
    
    Returns uncompressed articles with ranking information.
    The agent middleware will handle deduplication and compression when needed.
    
    **Tool Responsibility**: Pure retrieval - NO token counting, NO budgeting, NO compression.
    **Agent Responsibility**: Context budgeting, deduplication, compression in before_model middleware.
    
    This tool should be called multiple times for comprehensive coverage of vague
    or complex queries. Each call is independent and returns ranked articles.
    """
    try:
        retriever = _get_or_create_retriever()
        
        # NO token counting - just retrieve uncompressed articles with ranks
        docs = retriever.retrieve(query, top_k=top_k)
        logger.info("Retrieved %d articles for query: %s", len(docs), query)
        return _format_articles_to_json(docs, query, top_k)
    except Exception as exc:
        logger.error("Error during retrieval: %s", exc, exc_info=True)
        return json.dumps({
            "error": f"Retrieval failed: {str(exc)}",
            "articles": [],
            "metadata": {"has_results": False, "query": query, "top_k_requested": top_k, "articles_count": 0},
        }, ensure_ascii=False)
```

**Also update** `_format_articles_to_json` to include rank information:

```python
def _format_articles_to_json(articles: list[Article], query: str, top_k: int | None) -> str:
    """Convert Article objects to JSON format with ranking information."""
    articles_data = []
    for article in articles:
        title = article.metadata.get("title", article.kb_id)
        url = (
            article.metadata.get("article_url")
            or article.metadata.get("url")
            or f"https://kb.comindware.ru/article.php?id={article.kb_id}"
        )
        
        # Include all metadata including rank information for proportional compression
        article_metadata = dict(article.metadata)
        # Metadata already contains rerank_score and normalized_rank from retriever
        
        articles_data.append({
            "kb_id": article.kb_id,
            "title": title,
            "url": url,
            "content": article.content,  # Uncompressed content
            "metadata": article_metadata,  # Includes rerank_score, normalized_rank
        })
    
    result = {
        "articles": articles_data,
        "metadata": {
            "query": query,
            "top_k_requested": top_k,
            "articles_count": len(articles_data),
            "has_results": len(articles_data) > 0,
        },
    }
    return json.dumps(result, ensure_ascii=False, separators=(',', ':'))
```

### 2. `retriever.py` — Remove context budgeting, preserve ranks

**Location**: `rag_engine/retrieval/retriever.py`

**Changes**:

#### 2.1 Remove `reserved_tokens` parameter from `retrieve()` method

**Current signature** (line 121):

```python
def retrieve(self, query: str, top_k: int | None = None, reserved_tokens: int = 0) -> list[Article]:
```

**New signature**:

```python
def retrieve(self, query: str, top_k: int | None = None) -> list[Article]:
    """Retrieve complete articles for query using hybrid approach.
    
    Hybrid approach:
  1. Vector search on chunks (top-20)
  2. Rerank chunks (top-10)
  3. Group chunks by kbId and preserve max reranker score
  4. Read complete articles from source_file
  5. Sort by rank and normalize ranks (0.0 = best, 1.0 = worst)
  6. Return ALL articles uncompressed with ranking information
    
    **Returns uncompressed articles with ranking metadata.**
    **Compression happens in agent middleware (before_model), not here.**
    
    Args:
        query: User query string
        top_k: Override top_k_rerank if provided
    
    Returns:
        List of complete Article objects (uncompressed, sorted by rank)
        Each article has metadata["rerank_score"] and metadata["normalized_rank"]
    """
```

#### 2.2 Preserve reranker scores when grouping chunks (lines 216-226)

**Current code** (lines 218-226 in `retriever.py`):

```python
# 3. Group top-ranked chunks by kbId (article identifier)
# Normalize kbIds to handle any edge cases (e.g., old suffixed kbIds)
articles_map: dict[str, list[Any]] = defaultdict(list)
for doc, _score in scored_candidates:  # ❌ Score is ignored!
    # Handle None metadata gracefully
    metadata = getattr(doc, "metadata", None) or {}
    raw_kb_id = metadata.get("kbId", "")
    if raw_kb_id:
        # Normalize kbId for consistent grouping (handles suffixed kbIds)
        kb_id = extract_numeric_kbid(raw_kb_id) or str(raw_kb_id)
        articles_map[kb_id].append(doc)
```

**Note**: Validation confirmed score is ignored (prefixed with `_`) at line 219.

**New code**:

```python
# 3. Group chunks by kb_id and preserve MAX reranker score as article rank
articles_map: dict[str, tuple[list[Any], float]] = defaultdict(lambda: ([], -float('inf')))
for doc, score in scored_candidates:
    metadata = getattr(doc, "metadata", None) or {}
    raw_kb_id = metadata.get("kbId", "")
    if raw_kb_id:
        kb_id = extract_numeric_kbid(raw_kb_id) or str(raw_kb_id)
        chunks, best_score = articles_map[kb_id]
        chunks.append(doc)
        # Keep the highest reranker score for this article
        articles_map[kb_id] = (chunks, max(best_score, score))
```

#### 2.3 Store rank scores in article metadata (lines 230-267)

**Current code** (lines 256-262 in `retriever.py`):

```python
article = Article(
    kb_id=kb_id,
    content=article_content,
    metadata=article_metadata,
)
article.matched_chunks = chunks
articles.append(article)
```

**Note**: Validation confirmed no `rerank_score` or `normalized_rank` is stored in metadata.

**New code**:

```python
# 4. Read complete articles and attach ranking information
articles: list[Article] = []
for kb_id, (chunks, max_score) in articles_map.items():
    # ... existing article reading logic (lines 230-255) ...
    article = Article(
        kb_id=kb_id,
        content=article_content,
        metadata=article_metadata,
    )
    article.matched_chunks = chunks
    # Store reranker score in metadata for proportional compression
    article.metadata["rerank_score"] = max_score
    articles.append(article)
```

#### 2.4 Sort articles by rank and normalize ranks

**Add after line 267** (after loading all articles):

```python
# Sort articles by reranker score (highest first = best rank)
articles.sort(key=lambda a: a.metadata.get("rerank_score", -float('inf')), reverse=True)

# Normalize ranks: 0.0 = best rank, 1.0 = worst rank (for proportional compression)
if len(articles) > 1:
    for idx, article in enumerate(articles):
        # Normalized rank: 0.0 = first (best), 1.0 = last (worst)
        article.metadata["normalized_rank"] = idx / (len(articles) - 1)
        article.metadata["article_rank"] = idx  # Position-based rank (0-based)
else:
    if articles:
        articles[0].metadata["normalized_rank"] = 0.0
        articles[0].metadata["article_rank"] = 0

logger.info("Loaded %d complete articles (uncompressed, sorted by rank)", len(articles))
```

#### 2.5 Remove `_apply_context_budget()` call (line 270)

**Current code**:

```python
articles = self._apply_context_budget(articles, question=query, reserved_tokens=reserved_tokens)
return articles
```

**New code**:

```python
# NO _apply_context_budget call - return all uncompressed articles with ranks
return articles
```

#### 2.6 DELETE entire `_apply_context_budget()` method (lines 297-504)

**Action**: Delete the entire method including:

- `_apply_context_budget()` (lines 297-504)
- `_create_lightweight_article()` nested function (lines 459-478)
        - **Validated**: Function exists and is used in the method

**Rationale**:

- Compression should happen in agent middleware, not in retriever
- `_create_lightweight_article()` is superseded by `summarize_to_tokens()` utility
- Token counting logic belongs in agent middleware

### 3. Agent Middleware — Implement proportional compression in `before_model`

**Location**: `rag_engine/llm/compression.py`

**New function**: `compress_all_articles_proportionally_by_rank()`

```python
def compress_all_articles_proportionally_by_rank(
    articles: list[dict],
    target_tokens: int,
    guidance: str | None = None,
    llm_manager=None,
) -> tuple[list[dict], int]:
    """Compress articles proportionally to their ranks.
    
    Higher-ranked articles (lower normalized_rank) get less compression.
    Lower-ranked articles (higher normalized_rank) get more compression.
    
    Compression strategy:
  - Best rank (normalized_rank=0.0): Compression ratio ~0.8 (80% of original)
  - Worst rank (normalized_rank=1.0): Compression ratio ~0.3 (30% of original)
  - Intermediate ranks: Linear interpolation
    
    Uses summarize_to_tokens for ALL compression (no lightweight articles).
    
    Args:
        articles: List of article dicts with 'content', 'metadata.normalized_rank'
        target_tokens: Target total tokens after compression
        guidance: User question for summarization guidance
        llm_manager: LLMManager for summarization
    
    Returns:
        Tuple of (compressed_articles, tokens_saved)
    
    Raises:
        ValueError: If articles have invalid normalized_rank values outside [0.0, 1.0]
    """
    import logging
    from rag_engine.llm.token_utils import count_tokens
    from rag_engine.llm.summarization import summarize_to_tokens
    
    logger = logging.getLogger(__name__)
    
    if not articles or not llm_manager:
        return articles, 0
    
    # Count current tokens
    total_tokens = sum(count_tokens(a.get("content", "")) for a in articles)
    tokens_to_save = max(0, total_tokens - target_tokens)
    
    if tokens_to_save == 0:
        return articles, 0  # No compression needed
    
    # Sort by rank (worst first = compress first)
    # Validate normalized_rank values and default to 1.0 (worst) if missing
    for article in articles:
        rank = article.get("metadata", {}).get("normalized_rank")
        if rank is not None:
            # Clamp to valid range [0.0, 1.0]
            article.setdefault("metadata", {})["normalized_rank"] = max(0.0, min(1.0, float(rank)))
        else:
            # Default missing ranks to worst (1.0) for safety
            article.setdefault("metadata", {})["normalized_rank"] = 1.0
    
    sorted_articles = sorted(
        enumerate(articles),
        key=lambda x: x[1].get("metadata", {}).get("normalized_rank", 1.0),
        reverse=True,  # Worst rank first
    )
    
    compressed_articles = list(articles)
    tokens_saved = 0
    
    # Minimum tokens per article (ensures readability)
    min_tokens_per_article = 300
    
    for orig_idx, article in sorted_articles:
        if tokens_saved >= tokens_to_save:
            break
        
        original_content = article.get("content", "")
        if not original_content:
            continue
        
        original_tokens = count_tokens(original_content)
        normalized_rank = article.get("metadata", {}).get("normalized_rank", 1.0)
        
        # Validate and clamp normalized_rank to [0.0, 1.0] range
        normalized_rank = max(0.0, min(1.0, float(normalized_rank)))
        
        # Compression ratio based on rank: 0.3 (worst) to 0.8 (best)
        # Higher normalized_rank (worse) = lower ratio (more compression)
        compression_ratio = 0.3 + (0.5 * (1.0 - normalized_rank))
        article_target_tokens = max(min_tokens_per_article, int(original_tokens * compression_ratio))
        
        try:
            compressed = summarize_to_tokens(
                title=article.get("title", "Article"),
                url=article.get("url", ""),
                matched_chunks=[original_content],  # Use full content as chunk for summarization
                full_body=None,  # Already using full content in matched_chunks
                target_tokens=article_target_tokens,
                guidance=guidance,
                llm=llm_manager,
                max_retries=1,
            )
            
            compressed_tokens = count_tokens(compressed)
            compressed_articles[orig_idx]["content"] = compressed
            if "metadata" not in compressed_articles[orig_idx]:
                compressed_articles[orig_idx]["metadata"] = {}
            compressed_articles[orig_idx]["metadata"]["compressed"] = True
            
            tokens_saved += (original_tokens - compressed_tokens)
            
            logger.debug(
                "Compressed article '%s' (rank=%.2f): %d → %d tokens (ratio=%.2f)",
                article.get("title", "")[:50],
                normalized_rank,
                original_tokens,
                compressed_tokens,
                compression_ratio,
            )
        except Exception as exc:
            logger.warning("Failed to compress article at index %d: %s", orig_idx, exc)
            continue
    
    return compressed_articles, tokens_saved
```

**Update**: `compress_tool_messages()` function to handle proportional compression

```python
def compress_tool_messages(
    messages: list,
    runtime,
    llm_manager,
    threshold_pct: float = 0.85,
    target_pct: float = 0.80,
) -> list | None:
    """Compress tool messages if context exceeds threshold.
    
    NEW BEHAVIOR:
  1. Extracts ALL articles from ALL tool messages
  2. Deduplicates by kb_id (preserves highest rerank_score)
  3. Re-normalizes ranks after deduplication
  4. Compresses proportionally by rank across all articles
  5. Updates tool messages with compressed articles
    
    This runs in @before_model middleware AFTER all tool calls complete.
    
    Args:
        messages: List of message objects
        runtime: Runtime object with access to model config
        llm_manager: LLMManager instance for compression
        threshold_pct: Threshold percentage for triggering compression (default: 0.85)
        target_pct: Target percentage after compression (default: 0.80)
    
    Returns:
        Updated list of messages if compression occurred, None otherwise
    """
    import json
    from rag_engine.config.settings import settings
    from rag_engine.llm.llm_manager import get_context_window
    from rag_engine.llm.token_utils import count_messages_tokens, count_tokens
    from rag_engine.utils.message_utils import (
        is_tool_message,
        get_message_content,
        update_tool_message_content,
        extract_user_question,
    )
    
    if not messages:
        return None
    
    # Get current model's context window
    current_model = getattr(runtime, "model", None) or settings.default_model
    context_window = get_context_window(current_model)
    threshold = int(context_window * threshold_pct)
    
    # Count total tokens in messages
    total_tokens = count_messages_tokens(messages)
    
    # Check if we need compression
    if total_tokens <= threshold:
        return None  # All good, no changes needed
    
    # Find all tool message indices
    tool_message_indices = []
    for idx, msg in enumerate(messages):
        if is_tool_message(msg):
            tool_message_indices.append(idx)
    
    if not tool_message_indices:
        return None  # No tool messages to compress
    
    logger.warning(
        "Context at %d tokens (%.1f%% of %d window), compressing articles proportionally by rank",
        total_tokens,
        100 * total_tokens / context_window,
        context_window,
    )
    
    # Extract ALL articles from ALL tool messages (with deduplication by kb_id)
    all_articles_dict: dict[str, dict] = {}  # kb_id -> article dict (preserve highest rank)
    
    for idx in tool_message_indices:
        msg = messages[idx]
        content = get_message_content(msg)
        if not content:
            continue
        
        try:
            result = json.loads(content)
            articles = result.get("articles", [])
            
            for article in articles:
                kb_id = article.get("kb_id")
                if not kb_id:
                    continue
                
                # Deduplicate: keep article with highest rerank_score
                existing = all_articles_dict.get(kb_id)
                existing_score = existing.get("metadata", {}).get("rerank_score", -float('inf')) if existing else -float('inf')
                new_score = article.get("metadata", {}).get("rerank_score", -float('inf'))
                
                if not existing or new_score > existing_score:
                    all_articles_dict[kb_id] = article
        
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Failed to parse tool message %d: %s", idx, exc)
            continue
    
    if not all_articles_dict:
        return None
    
    # Convert to list and sort by rank (best first)
    all_articles = list(all_articles_dict.values())
    all_articles.sort(
        key=lambda a: a.get("metadata", {}).get("rerank_score", -float('inf')),
        reverse=True,
    )
    
    # Re-normalize ranks after deduplication
    if len(all_articles) > 1:
        for idx, article in enumerate(all_articles):
            # Normalized rank: 0.0 = first (best), 1.0 = last (worst)
            normalized_rank = idx / (len(all_articles) - 1)
            article.setdefault("metadata", {})["normalized_rank"] = normalized_rank
            article.setdefault("metadata", {})["article_rank"] = idx
    else:
        if all_articles:
            all_articles[0].setdefault("metadata", {})["normalized_rank"] = 0.0
            all_articles[0].setdefault("metadata", {})["article_rank"] = 0
    
    # Calculate target tokens
    target_tokens = int(context_window * target_pct)
    
    # Count non-tool message tokens (conversation + system prompts)
    non_tool_tokens = sum(
        count_messages_tokens([m]) 
        for m in messages 
        if not is_tool_message(m)
    )
    
    # Available budget for articles (with safety margin for JSON overhead)
    available_for_articles = max(0, int((target_tokens - non_tool_tokens) * 0.95))  # 5% margin
    
    # Get user question for summarization guidance
    user_question = extract_user_question(messages)
    
    # Compress ALL articles proportionally by rank
    compressed_articles, tokens_saved = compress_all_articles_proportionally_by_rank(
        articles=all_articles,
        target_tokens=available_for_articles,
        guidance=user_question,
        llm_manager=llm_manager,
    )
    
    if tokens_saved == 0:
        return None  # Compression didn't help
    
    # Create mapping: kb_id -> compressed article
    compressed_by_kb_id = {a["kb_id"]: a for a in compressed_articles}
    
    # Update tool messages with compressed articles
    updated_messages = list(messages)
    for idx in tool_message_indices:
        msg = updated_messages[idx]
        content = get_message_content(msg)
        if not content:
            continue
        
        try:
            result = json.loads(content)
            original_articles = result.get("articles", [])
            
            # Replace with compressed versions if available
            compressed_result_articles = []
            for orig_article in original_articles:
                kb_id = orig_article.get("kb_id")
                if kb_id in compressed_by_kb_id:
                    compressed_result_articles.append(compressed_by_kb_id[kb_id])
                else:
                    compressed_result_articles.append(orig_article)
            
            result["articles"] = compressed_result_articles
            if "metadata" not in result:
                result["metadata"] = {}
            result["metadata"]["compressed_articles_count"] = sum(
                1 for a in compressed_result_articles 
                if a.get("metadata", {}).get("compressed")
            )
            result["metadata"]["tokens_saved_by_compression"] = tokens_saved
            
            # Create new compact JSON
            new_content = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
            updated_messages = update_tool_message_content(updated_messages, idx, new_content)
        
        except Exception as exc:
            logger.warning("Failed to update tool message %d: %s", idx, exc)
            continue
    
    if tokens_saved > 0:
        logger.info(
            "Proportional compression by rank complete: saved %d tokens (%.1f%% reduction), "
            "new total ~%d (%.1f%% of window)",
            tokens_saved,
            100 * tokens_saved / total_tokens,
            total_tokens - tokens_saved,
            100 * (total_tokens - tokens_saved) / context_window,
        )
        return updated_messages
    
    return None
```

### 4. Update `compress_tool_results` middleware

**Location**: `rag_engine/api/app.py`

**Update**: `compress_tool_results()` middleware to use new compression function

```python
def compress_tool_results(state: dict, runtime) -> dict | None:
    """Compress tool results before LLM call if approaching context limit.
    
    This middleware runs right before each LLM invocation, AFTER all tool calls complete.
    It extracts ALL articles from ALL tool messages, deduplicates, and compresses
    proportionally based on normalized_rank (0.0 = best, 1.0 = worst).
    
    Args:
        state: Agent state containing messages
        runtime: Runtime object with access to model config
    
    Returns:
        Updated state dict with compressed messages, or None
    """
    from rag_engine.config.settings import settings
    from rag_engine.llm.compression import compress_tool_messages
    
    messages = state.get("messages", [])
    if not messages:
        return None
    
    # Apply compression if needed (proportional by rank)
    # Note: llm_manager is module-level singleton in app.py
    updated_messages = compress_tool_messages(
        messages=messages,
        runtime=runtime,
        llm_manager=llm_manager,  # Module-level singleton from app.py
        threshold_pct=float(getattr(settings, "llm_compression_threshold_pct", 0.85)),
        target_pct=float(getattr(settings, "llm_compression_target_pct", 0.80)),
    )
    
    if updated_messages:
        return {"messages": updated_messages}
    
    return None
```

### 5. Fallback LLM Integration (Optional Enhancement)

**Note**: Fallback LLM switching happens at agent creation time (in `_create_rag_agent()`), not in middleware. The middleware can detect the need for fallback, but the actual switch requires recreating the agent with the new model.

If fallback detection is desired in middleware, it should:

1. Check if context exceeds threshold significantly (e.g., >90% of context window)
2. Log the need for fallback
3. The agent factory will handle the actual model switch

## Summary of Changes

### Files to Modify

1. **`rag_engine/tools/retrieve_context.py`**

                        - Remove lines 226-254 (token counting)
                        - Remove `reserved_tokens` parameter from `retriever.retrieve()` call
                        - Update `_format_articles_to_json()` to ensure rank metadata is included

2. **`rag_engine/retrieval/retriever.py`**

                        - Remove `reserved_tokens` parameter from `retrieve()` method signature
                        - Preserve reranker scores when grouping chunks (lines 216-226)
                        - Store `rerank_score` and `normalized_rank` in article metadata
                        - Sort articles by rank and normalize ranks
                        - Remove `_apply_context_budget()` call (line 270)
                        - Delete entire `_apply_context_budget()` method (lines 297-504)

3. **`rag_engine/llm/compression.py`**

                        - Add `compress_all_articles_proportionally_by_rank()` function
                        - Update `compress_tool_messages()` to:
                                        - Extract ALL articles from ALL tool messages
                                        - Deduplicate by `kb_id` (preserve highest rank)
                                        - Re-normalize ranks after deduplication
                                        - Compress proportionally by rank
                                        - Update tool messages with compressed articles

4. **`rag_engine/api/app.py`**

                        - Update `compress_tool_results()` middleware to use new compression function

### Key Design Principles

1. **Separation of Concerns**

                        - Retriever: Only retrieval, no budgeting/compression
                        - Tool: Only formatting, no token counting
                        - Agent middleware: All budgeting, compression, fallback logic

2. **Proportional Compression**

                        - Higher-ranked articles (lower `normalized_rank`) → Less compression (80% of original)
                        - Lower-ranked articles (higher `normalized_rank`) → More compression (30% of original)
                        - Linear interpolation for intermediate ranks

3. **Deduplication**

                        - Deduplicate by `kb_id` across ALL tool calls
                        - Preserve article with highest `rerank_score`
                        - Re-normalize ranks after deduplication

4. **Compression Method**

                        - Use `summarize_to_tokens` exclusively (no lightweight articles)
                        - Minimum 300 tokens per article for readability
                        - Compression happens once after all tool calls

## Testing Checklist

- [ ] Single tool call returns uncompressed articles with ranks
- [ ] Multiple tool calls with overlapping articles → deduplication works
- [ ] Rank information preserved through tool → middleware → LLM
- [ ] Proportional compression: best articles compressed less, worst compressed more
- [ ] No token counting in `retrieve_context` tool
- [ ] No `_apply_context_budget` call in retriever
- [ ] `summarize_to_tokens` handles all compression (no lightweight articles)
- [ ] Compression happens only in `before_model` middleware (after all tool calls)
- [ ] Articles sorted by rank (highest rerank_score first)
- [ ] Normalized ranks are 0.0 (best) to 1.0 (worst)

## Migration Notes

- **Breaking change**: `retriever.retrieve()` no longer accepts `reserved_tokens` parameter
        - **Validated**: Current signature at line 121: `def retrieve(self, query: str, top_k: int | None = None, reserved_tokens: int = 0)`
- **Breaking change**: `retrieve_context` tool no longer counts tokens or passes `reserved_tokens`
        - **Validated**: Token counting exists at lines 226-254 in `retrieve_context.py`
- **Non-breaking**: Agent middleware handles compression transparently
        - **Validated**: `compress_tool_results()` middleware exists at `app.py:129` and uses `before_model` at line 314
- **Performance**: Compression happens once (after all tool calls) instead of per tool call
        - **Validated**: Current implementation compresses per tool message (reversed order)
- **Quality**: Better compression by considering all articles together with proportional allocation by rank

---

## Implementation Todo Checklist

### Phase 1: Retriever Changes (Foundation)

- [ ] **1.1** Modify `retriever.py`:
                - [ ] Remove `reserved_tokens: int = 0` parameter from `retrieve()` method signature (line 121)
                - [ ] Update `retrieve()` method docstring to reflect new behavior
                - [ ] Modify chunk grouping logic (lines 216-226):
                                - [ ] Change `articles_map` from `dict[str, list[Any]]` to `dict[str, tuple[list[Any], float]]`
                                - [ ] Preserve reranker scores: `articles_map[kb_id] = (chunks, max(best_score, score))`
                - [ ] Update article creation (around line 261):
                                - [ ] Store `rerank_score` in `article.metadata["rerank_score"]`
                - [ ] Add rank sorting and normalization (after line 267):
                                - [ ] Sort articles by `rerank_score` (highest first)
                                - [ ] Calculate and store `normalized_rank` (0.0=best, 1.0=worst)
                                - [ ] Store `article_rank` (position-based index)
                - [ ] Remove `_apply_context_budget()` call (line 270)
                - [ ] Delete entire `_apply_context_budget()` method (lines 297-504)
                - [ ] Delete `_create_lightweight_article()` function if present (lines 459-478)

### Phase 2: Tool Changes (Remove Token Counting)

- [ ] **2.1** Modify `retrieve_context.py`:
                - [ ] Remove token counting logic (lines 226-254):
                                - [ ] Remove `conversation_tokens` calculation
                                - [ ] Remove `accumulated_tool_tokens` calculation
                                - [ ] Remove `total_reserved_tokens` calculation
                                - [ ] Remove logging related to token counting
                - [ ] Update `retrieve_context()` function:
                                - [ ] Remove `reserved_tokens` parameter from `retriever.retrieve()` call
                                - [ ] Update docstring to clarify tool responsibility
                - [ ] Update `_format_articles_to_json()` function:
                                - [ ] Ensure `rerank_score` and `normalized_rank` are included in article metadata
                                - [ ] Verify all article metadata is properly serialized

### Phase 3: Compression Middleware (New Implementation)

- [ ] **3.1** Create `compress_all_articles_proportionally_by_rank()` in `compression.py`:
                - [ ] Implement function signature with correct parameters
                - [ ] Add token counting logic (count current total)
                - [ ] Implement early return if no compression needed
                - [ ] Sort articles by `normalized_rank` (worst first)
                - [ ] Calculate compression ratio per article (0.3 to 0.8 based on rank)
                - [ ] Validate normalized_rank values:
                                - [ ] Clamp ranks to [0.0, 1.0] range if out of bounds
                                - [ ] Default missing ranks to 1.0 (worst) for safety
                - [ ] Loop through articles and compress using `summarize_to_tokens`:
                                - [ ] Set minimum tokens per article (300)
                                - [ ] Calculate target tokens per article
                                - [ ] Validate normalized_rank again before compression ratio calculation
                                - [ ] Call `summarize_to_tokens` with guidance
                                - [ ] Update article content with compressed version
                                - [ ] Mark article as compressed in metadata
                                - [ ] Track tokens saved
                - [ ] Add error handling for compression failures
                - [ ] Add debug logging for compression details
                - [ ] Return `(compressed_articles, tokens_saved)` tuple

- [ ] **3.2** Update `compress_tool_messages()` in `compression.py`:
                - [ ] Update function signature and docstring
                - [ ] Get context window and calculate thresholds
                - [ ] Count total tokens and check threshold
                - [ ] Extract ALL articles from ALL tool messages:
                                - [ ] Find all tool message indices
                                - [ ] Parse JSON from each tool message
                                - [ ] Extract articles from each tool result
                                - [ ] Implement deduplication by `kb_id`:
                                                - [ ] Keep article with highest `rerank_score`
                                                - [ ] Use dictionary: `kb_id -> article_dict`
                - [ ] Sort deduplicated articles by `rerank_score` (best first)
                - [ ] Re-normalize ranks after deduplication
                - [ ] Calculate available token budget for articles
                - [ ] Get user question for compression guidance
                - [ ] Call `compress_all_articles_proportionally_by_rank()`
                - [ ] Map compressed articles back to tool messages:
                                - [ ] Create `kb_id -> compressed_article` mapping
                                - [ ] Update each tool message with compressed articles
                                - [ ] Preserve article order in tool results
                                - [ ] Update tool result metadata (compressed count, tokens saved)
                - [ ] Add comprehensive logging (warnings, info, debug)
                - [ ] Return updated messages or None

### Phase 4: Middleware Integration

- [ ] **4.1** Update `compress_tool_results()` in `app.py`:
                - [ ] Import new compression function
                - [ ] Update function docstring
                - [ ] Call `compress_tool_messages()` with correct parameters
                - [ ] Handle return value (updated messages or None)
                - [ ] Return state dict with updated messages or None

### Phase 5: Testing & Validation

- [ ] **5.1** Unit tests for retriever:
                - [ ] Test `retrieve()` returns articles with `rerank_score`
                - [ ] Test `retrieve()` returns articles with `normalized_rank`
                - [ ] Test articles are sorted by rank (highest first)
                - [ ] Test `normalized_rank` calculation (0.0=best, 1.0=worst)
                - [ ] Test no `_apply_context_budget()` is called
                - [ ] Test no `reserved_tokens` parameter used

- [ ] **5.2** Unit tests for tool:
                - [ ] Test `retrieve_context()` does not count tokens
                - [ ] Test `retrieve_context()` does not pass `reserved_tokens`
                - [ ] Test `_format_articles_to_json()` includes rank metadata
                - [ ] Test tool returns uncompressed articles

- [ ] **5.3** Unit tests for compression:
                - [ ] Test `compress_all_articles_proportionally_by_rank()`:
                                - [ ] Compresses articles proportionally by rank
                                - [ ] Best articles compressed less (ratio ~0.8)
                                - [ ] Worst articles compressed more (ratio ~0.3)
                                - [ ] Handles edge cases (no articles, no compression needed)
                                - [ ] Returns correct tokens saved
                - [ ] Test `compress_tool_messages()`:
                                - [ ] Extracts articles from all tool messages
                                - [ ] Deduplicates by `kb_id` (preserves highest rank)
                                - [ ] Re-normalizes ranks after deduplication
                                - [ ] Only compresses when threshold exceeded
                                - [ ] Updates tool messages correctly
                                - [ ] Handles empty messages, no tool messages

- [ ] **5.4** Integration tests:
                - [ ] Test single tool call returns uncompressed ranked articles
                - [ ] Test multiple tool calls with overlapping articles:
                                - [ ] Deduplication works correctly
                                - [ ] Highest rank article preserved
                - [ ] Test compression triggers when threshold exceeded
                - [ ] Test compression doesn't trigger when under threshold
                - [ ] Test rank information flows: tool → middleware → LLM
                - [ ] Test proportional compression across all articles
                - [ ] Test compression happens only in `before_model` middleware
                - [ ] Test end-to-end: user question → tool calls → compression → LLM answer

- [ ] **5.5** Manual testing:
                - [ ] Test with small queries (no compression needed)
                - [ ] Test with large queries (compression triggered)
                - [ ] Test with multiple overlapping tool calls
                - [ ] Verify article quality after compression
                - [ ] Check logs for compression metrics
                - [ ] Verify citations still work with compressed articles

### Phase 6: Cleanup & Documentation

- [ ] **6.1** Code cleanup:
                - [ ] Remove unused imports
                - [ ] Update inline comments
                - [ ] Remove deprecated code paths
                - [ ] Run linter (`ruff check`) on modified files
                - [ ] Fix any linting errors

- [ ] **6.2** Documentation updates:
                - [ ] Update docstrings in modified functions
                - [ ] Update README if architecture changed
                - [ ] Document breaking changes
                - [ ] Add migration guide if needed

- [ ] **6.3** Final validation:
                - [ ] Run full test suite
                - [ ] Check for any regressions
                - [ ] Verify performance improvements
                - [ ] Review code for any missed edge cases

---

## Validation Reference

This plan has been validated against the current codebase:

- **Validation Report**: `.cursor/plans/retriever-refactor-validation.md`
- **Validation Date**: 2025-01-28
- **Status**: ✅ **VALIDATED AND APPROVED**
- **Confidence**: HIGH - All line numbers verified, all dependencies exist, architecture assumptions correct

**Key Validation Findings**:

1. ✅ All line numbers accurate (within 1-2 lines)
2. ✅ Code patterns match plan descriptions exactly
3. ✅ All dependencies verified (functions, utilities, middleware)
4. ✅ Architecture flow is sound and addresses identified issues
5. ✅ No blocking issues found

---

**Status**: ✅ Plan validated and ready for implementation