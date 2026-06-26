---
name: Remove Fast Path Token Counting
overview: Remove the fast path approximation (`chars // 4`) from token counting and always use exact tiktoken counting throughout the codebase. This eliminates accuracy issues for Russian text while maintaining acceptable performance (13ms for 200K chars is negligible).
todos:
  - id: remove-fast-path-logic
    content: Remove fast path logic from count_tokens() in token_utils.py - remove threshold check and always use exact tiktoken encoding
    status: pending
  - id: remove-threshold-config
    content: Remove retrieval_fast_token_char_threshold setting from settings.py
    status: pending
  - id: update-token-utils-docs
    content: Update docstrings and comments in token_utils.py to remove fast path references
    status: pending
  - id: update-tests
    content: Update test_llm_token_utils.py to test exact counting instead of fast path
    status: pending
  - id: remove-config-tests
    content: Remove tests for retrieval_fast_token_char_threshold from test_config_settings.py
    status: pending
  - id: update-readme
    content: Remove fast path mentions and RETRIEVAL_FAST_TOKEN_CHAR_THRESHOLD from README.md
    status: pending
  - id: update-agent-factory-docstring
    content: Update tiktoken_counter docstring in agent_factory.py to remove fast path reference
    status: pending
  - id: verify-changes
    content: Run tests and verify all token counting uses exact tiktoken encoding
    status: pending
---

# Remove Fast Path Token Counting

## Overview

Remove the fast path approximation (`chars // 4`) from token counting and always use exact tiktoken counting. Based on benchmark results, tiktoken is fast enough (13ms for 200K chars, 66ms for 1M chars) that the performance gain from approximation (~13-66ms) is not worth the 25-50% accuracy loss for Russian text.

## Files to Modify

### 1. Core Token Counting Logic

**File**: `rag_engine/llm/token_utils.py`

- Remove `_FAST_PATH_CHAR_LEN` constant (line 17)
- Remove fast path check in `count_tokens()` (lines 50-53)
- Always use exact tiktoken encoding: `return len(_ENCODING.encode(content_str))`
- Update docstring to remove references to fast path
- Update example in docstring (remove fast path example)
- Update `count_messages_tokens()` docstring (line 64) to remove fast path reference
- Update `count_messages_tokens()` docstring (line 64) to remove fast path reference

### 2. Configuration Settings

**File**: `rag_engine/config/settings.py`

- Remove `retrieval_fast_token_char_threshold` setting (line 90)
- Remove associated comment (line 89)

### 3. Tests

**File**: `rag_engine/tests/test_llm_token_utils.py`

- Update `test_estimate_tokens_for_request_uses_fast_path_for_large_strings()`:
  - Rename to `test_estimate_tokens_for_request_counts_large_strings()`
  - Change assertion to use exact token count instead of `chars // 4`
  - Calculate expected tokens using actual tiktoken encoding

**File**: `rag_engine/tests/test_config_settings.py`

- Remove `test_retrieval_fast_token_char_threshold_default()` (lines 56-61)
- Remove `test_retrieval_fast_token_char_threshold_can_be_overridden()` (lines 64-70)

### 4. Documentation

**File**: `README.md`

- Remove fast path mention (line 346)
- Remove `RETRIEVAL_FAST_TOKEN_CHAR_THRESHOLD` configuration entry (line 383)

**File**: `rag_engine/llm/agent_factory.py`

- Update comment in `tiktoken_counter()` docstring (line 76) to remove fast path reference

**File**: `rag_engine/tests/test_agent_handler.py`

- Update comment (line 199) to reflect exact counting instead of fast path approximation

**File**: `.env-example`

- Remove `RETRIEVAL_FAST_TOKEN_CHAR_THRESHOLD` entry (line 108)
- Remove associated comment (line 107)

### 5. Documentation Files (Optional - Historical)

**Note**: Progress reports are historical documentation. Consider updating:

- `docs/progress_reports/token_estimation_russian_issue.md` - Mark as resolved
- Other progress reports mentioning fast path - These are historical and can remain as-is

## Implementation Details

### Changes to `count_tokens()` function:

**Before:**

```python
def count_tokens(content: str) -> int:
    """Count tokens in a string using tiktoken with fast path for large content.
    
    For small to medium content (< threshold), uses exact tiktoken encoding.
    For very large content (>= threshold), uses fast approximation (chars // 4).
    """
    if not content:
        return 0
    
    content_str = str(content)
    
    # Fast path for very large content to avoid performance issues
    if len(content_str) > _FAST_PATH_CHAR_LEN:
        return len(content_str) // 4
    
    # Use exact tiktoken counting for smaller content
    return len(_ENCODING.encode(content_str))
```

**After:**

```python
def count_tokens(content: str) -> int:
    """Count tokens in a string using exact tiktoken encoding.
    
    Uses tiktoken's cl100k_base encoding for accurate token counting
    across all languages, including Russian/Cyrillic text.
    """
    if not content:
        return 0
    
    content_str = str(content)
    return len(_ENCODING.encode(content_str))
```

### Test Update Example:

**Before:**

```python
def test_estimate_tokens_for_request_uses_fast_path_for_large_strings():
    """Test that very large strings use fast approximation (chars // 4)."""
    large_string = "x" * 300_000
    out = estimate_tokens_for_request(...)
    # Fast path: 300k chars // 4 = 75k tokens
    assert out["input_tokens"] == 75_000
```

**After:**

```python
def test_estimate_tokens_for_request_counts_large_strings():
    """Test that very large strings are counted accurately using tiktoken."""
    large_string = "x" * 300_000
    out = estimate_tokens_for_request(...)
    # Exact count: should match tiktoken encoding
    expected_tokens = len(tiktoken.get_encoding("cl100k_base").encode(large_string))
    assert out["input_tokens"] == expected_tokens
```

## Verification Steps

1. Run tests: `pytest rag_engine/tests/test_llm_token_utils.py -v`
2. Run config tests: `pytest rag_engine/tests/test_config_settings.py -v`
3. Verify no references to `retrieval_fast_token_char_threshold` remain (except in historical docs)
4. Verify all token counting uses exact tiktoken encoding
5. Test with Russian text to confirm accurate counting

## Impact

- **Accuracy**: 100% accurate token counting for all languages (fixes Russian text issue)
- **Performance**: Minimal impact (~13ms for 200K chars, ~66ms for 1M chars - negligible)
- **Simplicity**: Removes threshold logic and configuration complexity
- **Breaking Changes**: None - all existing code using `count_tokens()` will automatically benefit

## Dependencies

All code using `count_tokens()` will automatically use exact counting:

- `rag_engine/utils/context_tracker.py` - No changes needed
- `rag_engine/llm/compression.py` - No changes needed
- `rag_engine/llm/llm_manager.py` - No changes needed
- `rag_engine/llm/summarization.py` - No changes needed
- `rag_engine/llm/agent_factory.py` - Only docstring update needed