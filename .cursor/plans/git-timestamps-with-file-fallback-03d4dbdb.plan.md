<!-- 03d4dbdb-de30-445f-96c2-c319b34d1a42 5e9d8062-b96b-426d-a70f-2834ece578b8 -->
# Three-Tier Timestamp Fallback: Frontmatter → Git → File Modification

## Summary

Implement a three-tier timestamp fallback system for document indexing that determines file update timestamps in the following priority order:

1. **Frontmatter `updated` field** - Parsed from YAML frontmatter (e.g., `updated: '2024-06-14 12:33:36'`)
2. **Git commit timestamp** - Last commit time for the file from its Git repository
3. **File modification date** - Filesystem `stat().st_mtime` as fallback

This ensures accurate change detection for incremental reindexing while maintaining backward compatibility. The system automatically detects the appropriate Git repository for each file and gracefully falls back through each tier if the previous fails.

## Implementation Plan

### 1. Create Git Utility Function

**File:** `rag_engine/utils/git_utils.py` (new file)

Create a minimal function that:

- Takes a file path (absolute or relative)
- Finds the Git repo root by running `git rev-parse --show-toplevel` from the file's directory
- Gets last commit timestamp via `git log -1 --format=%ct --follow`
- Returns `(epoch: int, iso_string: str)` or `(None, None)` on any failure
- Uses `subprocess.run` with timeout and error handling
- No caching/memoization (keep it lean)

### 2. Create Timestamp Utilities

**File:** `rag_engine/utils/git_utils.py` (same file, add functions)

Add three functions:

1. `_epoch_to_iso(epoch: int) -> str` - Helper to convert epoch to ISO string (DRY - used by all timestamp sources)
2. `parse_frontmatter_timestamp(updated_str: str) -> tuple[int | None, str | None]`:

- Takes a string like `'2024-06-14 12:33:36'` (no timezone)
- Parses it as naive datetime, assumes UTC
- Returns `(epoch: int, iso_string: str)` or `(None, None)` on parse failure
- Uses `_epoch_to_iso()` helper internally

3. `get_git_timestamp()` also uses `_epoch_to_iso()` helper

### 3. Extract Timestamp Resolution Logic (DRY)

**File:** `rag_engine/utils/git_utils.py` (add function)

Add `get_file_timestamp(source_file: str, base_meta: dict) -> tuple[int | None, str | None, str]`:

- Implements the three-tier fallback: frontmatter → Git → file stat
- Returns `(epoch, iso_string, source)` where source is `"frontmatter"`, `"git"`, `"file"`, or `"none"`
- This function is reusable for both indexing and dry-run mode
- DRY: single source of truth for timestamp resolution logic

### 4. Update Retriever with Three-Tier Fallback

**File:** `rag_engine/retrieval/retriever.py`

Modify lines 189-200 in `index_documents()`:

- Replace inline timestamp logic with call to `get_file_timestamp(source_file, base_meta)`
- Extract epoch and iso_string from result
- Keep the same metadata fields: `file_mtime_epoch` and `file_modified_at_iso`

### 5. Add Dry-Run Mode

**File:** `rag_engine/scripts/build_index.py`

Add `--dry-run` argument:

- When enabled, processes documents but skips embedding and vector store writes
- For each document, prints: file path, timestamp source (frontmatter/git/file), epoch, ISO string
- Shows which files would be indexed vs skipped (based on existing timestamps)
- Useful for verifying timestamp fallback behavior without indexing

Implementation:

- Add `--dry-run` argparse flag
- Create a helper function that analyzes timestamps without indexing
- Print tabular output showing file → source → timestamp details

### 6. Testing Considerations

- No new tests required initially (existing tests should continue to work with fallback behavior)
- Files without frontmatter `updated` will use Git or file stats
- Files not in Git repos will use file modification dates
- Dry-run mode can be manually tested to verify timestamp resolution

## Files to Modify

1. `rag_engine/utils/git_utils.py` - new file (~60 lines total)

- `get_git_timestamp()` function
- `parse_frontmatter_timestamp()` function

2. `rag_engine/retrieval/retriever.py` - update timestamp retrieval logic (~25 lines changed)

## Key Design Decisions

- **Lean**: No caching, no complex error handling beyond try/except
- **Three-tier fallback**: Frontmatter → Git → File stats (in order of preference)
- **Automatic repo detection**: Each file's repo is detected independently
- **Graceful degradation**: Each tier fails silently to next tier
- **No config flag**: Always uses the fallback chain automatically

### To-dos

- [ ] Create rag_engine/utils/git_utils.py with get_git_timestamp() function that detects repo per file and returns (epoch, iso_string) or (None, None)
- [ ] Update retriever.py to import and use get_git_timestamp() with fallback to file stat() logic