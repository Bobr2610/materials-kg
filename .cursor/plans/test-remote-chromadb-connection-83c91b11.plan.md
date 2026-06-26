<!-- 83c91b11-ea69-48f6-901d-94874c297a7c 5045c7ea-9d26-42cc-b7bc-f904c2749d74 -->
# Simple ChromaDB Remote Connection Test

Create a simple script to test connection to a remote ChromaDB server.

## Implementation

### 1. Create `rag_engine/scripts/test_chroma_connection.py`

Simple connection test script that:

- Uses `chromadb.HttpClient` to connect to remote server
- Accepts URL via command-line argument (default: `http://<host>:8000/`)
- Tests basic connectivity:
  - Attempts to connect to server
  - Lists available collections
  - Shows simple connection status and any errors
- Minimal, focused on just verifying the connection works
- Follows patterns from existing scripts for consistency

## Files to Create

- `rag_engine/scripts/test_chroma_connection.py` - Simple connection testing script

## Usage

```bash
# Test connection to default server
python rag_engine/scripts/test_chroma_connection.py

# Test specific server URL
python rag_engine/scripts/test_chroma_connection.py --url http://<host>:8000/
```

### To-dos

- [ ] Create test_chroma_connection.py script with HttpClient support, argument parsing, and connection tests
- [ ] Test the script manually against the remote server to verify it works