<!-- c94e6ce4-6406-4a68-b4eb-e3a9e65b0aca 05833df8-9722-4553-abb3-6919768a65c9 -->
# Phase 1 – MkDocs RAG MVP (Chroma + FRIDA) with Lean Reranking

## Goal

Minimal RAG agent per `mkdocs-rag-engine.plan.md` Phase 1: index compiled MkDocs markdown into Chroma with FRIDA embeddings, retrieve with optional reranking, stream answers in a Gradio ChatInterface with citations. **Default input: compiled MD folder (Mode 3)** with optional MkDocs hook export (Mode 1) and single combined MD file support (Mode 2).

**Estimated Timeline:** 6-8 weeks for single developer

## ⚠️ Critical Design Update (Hybrid Approach)

**Key Changes from Original Approach:**

1. **Chunk size: 500 tokens** (down from 700) - fits FRIDA's 512-token embedding window
2. **Chunk overlap: 150 tokens** (down from 300) - proportional reduction
3. **Chunks for search only** - small chunks ensure accurate embeddings
4. **Rerank chunks, not articles** - CrossEncoder works best on 500-token chunks (more efficient than 8K articles)
5. **Complete articles for LLM** - read from filesystem via `source_file` metadata after reranking
6. **Context budgeting** - include articles sequentially until token limit reached
7. **No chunk merging** - eliminates complex reconstruction logic

**Rationale:**
- FRIDA's max_seq_length is 512 tokens; chunks must fit within this window
- **CrossEncoders are most efficient on shorter text** (500 tokens vs 8K tokens)
- Reranking chunks saves computation and only loads articles with top-ranked chunks
- Providing complete articles to LLM gives better context than disconnected chunks
- Reading from source files is simpler than storing/reconstructing from chunk fragments
- Summarization can be added in Phase 2 if needed

## References

- LangChain Reference: [reference.langchain.com](https://reference.langchain.com/python)
- LangChain Learn (RAG, runnables, streaming): [docs.langchain.com/oss/python/learn](https://docs.langchain.com/oss/python/learn)
- RAG + Chroma: [docs.langchain.com/oss/python/langchain/rag#chroma](https://docs.langchain.com/oss/python/langchain/rag#chroma)
- Gradio ChatInterface (UI): [gradio.app/docs/gradio/chatinterface](https://www.gradio.app/docs/gradio/chatinterface)
- Gradio API: [gradio.app/docs/gradio/api](https://www.gradio.app/docs/gradio/api)
- FRIDA Embeddings: [huggingface.co/ai-forever/FRIDA](https://huggingface.co/ai-forever/FRIDA)
- Inspirations: Habr article ([habr.com/ru/articles/955798](https://habr.com/ru/articles/955798/)), CodeCutTech notebook ([github.com/CodeCutTech/.../open_source_rag_pipeline_intelligent_qa_system.ipynb](https://github.com/CodeCutTech/Data-science/blob/master/machine_learning/open_source_rag_pipeline_intelligent_qa_system.ipynb))

## Input Modes (Priority Order)

### Mode 3 (Default): Compiled MD Folder

**Simplest for Phase 1 – Recommended starting point**

- Ready-to-use compiled MD files in folder structure
- Parse frontmatter + markdown directly
- Example: `phpkb_content/798. Версия 5.0. Текущая рекомендованная/`
- **Zero setup required – just point to folder**

### Mode 2: Single Combined MD File

**Similar logic to Mode 3**

- Large single-file knowledge base
- Example: `kb.comindware.ru.platform_v5_for_llm_ingestion.md`
- Split by H1 heading markers

### Mode 1: MkDocs Hook Export

**For live MkDocs repos with Jinja2 templates**

- Requires `mkdocs_for_rag_indexing.yml` + `rag_indexing_hook.py`
- Exports compiled MD with resolved Jinja2
- Creates manifest.json
- Can defer to Phase 1.5 if not immediately needed

**All 3 modes are included in implementation; Mode 3 is tested first for fastest MVP.**

## Pragmatic Approach

- **No LangChain purity requirement** – use what's lean and works
- **Embeddings**: `sentence-transformers` directly (FRIDA with prefixes) – simpler than LangChain wrappers
- **Vector store**: Use `langchain-chroma` for convenience (clean API)
- **Reranker**: Direct `sentence-transformers.CrossEncoder` (optional, identity fallback)
- **LLM**: **Reuse robust LLM mechanics from `cmw-platform-agent`** with dynamic token limits, multi-provider support, and streaming
- **Token Management**: Dynamic token limits from LLM manager (not hardcoded)
- **UI**: Gradio ChatInterface + `gr.api()` for REST endpoint
- **Config**: `.env` + `settings.py` (Pydantic Settings); no JSON overrides for MVP

## Architecture

```
Input: Compiled MD Folder (Mode 3 default) / Single MD File (Mode 2) / MkDocs Export (Mode 1)
           ↓
    Document Processor (parse frontmatter, extract structure, all 3 modes)
           ↓
    Chunker (500 tokens, 150 overlap, code-safe with tiktoken)
           ↓
    Metadata Enricher (kbId, title, url, source_file, section_heading, section_anchor, has_code, etc.)
           ↓
    FRIDA Embedder (sentence-transformers with prefixes, 512 token window)
           ↓
    Chroma Vector Store (chunks for search, metadata with source_file paths)
           ↓
    QUERY PIPELINE:
        1. Embed query (search_query prefix)
        2. Vector search on chunks (top-20 chunks)
        3. Rerank chunks with CrossEncoder (top-10 chunks) - efficient on 500-token chunks
        4. Group top-ranked chunks by kbId (article identifier)
        5. Read complete articles from filesystem via source_file metadata
        6. Context budgeting: include articles within LLM context limit (top-5 articles)
        7. LLM streaming with complete article context (Gemini/OpenRouter via LangChain)
        8. Format with citations
           ↓
    Gradio ChatInterface + REST API (gr.api)
```

**Design Principles:**

- **Chunks for search, articles for LLM**: Small chunks (500 tokens) fit FRIDA's 512-token window for accurate embeddings; complete articles provide full context to LLM
- **Chunk-level reranking**: Rerank 500-token chunks (not full articles) for efficiency and accuracy
- **Metadata-driven article retrieval**: Use `source_file` metadata to read complete articles from filesystem after reranking
- **Pragmatic tooling**: use what works (mix of direct libraries + LangChain where useful)
- **Graceful degradation**: reranker falls back to identity if unavailable
- **Citation-first**: always include source links with section anchors

## Reusing Robust LLM Mechanics from cmw-platform-agent

**Why reuse instead of rebuilding?**

The `cmw-platform-agent` repository has a battle-tested LLM management system that we should leverage:

### Features We Reuse:
1. **Dynamic Token Limits**: `get_current_llm_context_window()` returns model-specific token limits
2. **Multi-Provider Support**: Gemini, Groq, OpenRouter, Mistral, GigaChat with unified interface
3. **Token Tracking**: `ConversationTokenTracker` with `get_token_budget_info(context_window)`
4. **Streaming Support**: Built-in streaming for all providers
5. **Model Configurations**: Comprehensive per-model settings (token_limit, max_tokens, temperature)
6. **Robust Error Handling**: Fallbacks, retries, health checks

### Integration Approach:
- **Option A** (Preferred): Copy `llm_manager.py` and `token_counter.py` from cmw-platform-agent, adapt for RAG
- **Option B**: Create lightweight adapter that wraps cmw-platform-agent's LLMManager
- **Key Method**: `get_current_llm_context_window()` → use for dynamic context budgeting in retriever

### Example Token Limit Config (from cmw-platform-agent):
```python
{
    "model": "gemini-2.5-flash",
    "token_limit": 1048576,  # 1M context window
    "max_tokens": 65536,      # Max output
    "temperature": 0
}
```

**This eliminates hardcoded `max_context_tokens=8000` - use dynamic limits instead!**

## Key Design Decision: Chunk-Based Search with Article-Level Context

**Why this approach?**

1. **FRIDA embedding window is 512 tokens** - chunks must fit within this limit for accurate embeddings
2. **Chunks are too fragmented for LLM** - providing 5 disconnected chunks loses article coherence
3. **Complete articles provide better context** - LLM can understand full narrative and relationships

**How it works:**

### Indexing Phase
- Parse articles from source files
- Chunk articles into 500-token pieces (overlap 150 tokens)
- Embed each chunk with FRIDA (search_document prefix)
- Store chunks in ChromaDB with metadata:
  - `kbId`: article identifier (used to group chunks)
  - `source_file`: **absolute path to original article file**
  - `title`, `url`, `section_heading`, `section_anchor`, etc.

### Query Phase
1. **Vector search on chunks**: Embed query, retrieve top-20 matching chunks
2. **Rerank chunks**: Score chunks (500 tokens each) with CrossEncoder, select top-10
3. **Group by article**: Extract unique `kbId` values from top-ranked chunks
4. **Read complete articles**: Use `source_file` metadata to read full article content from filesystem
5. **Context budgeting**: Include articles sequentially until LLM context limit reached (e.g., 8K tokens, ~5 articles)
6. **LLM generation**: Feed complete articles to LLM, not chunks
7. **Citations**: Reference articles with section anchors, not individual chunks

**Benefits:**
- ✅ Accurate embeddings (chunks fit FRIDA's 512-token window)
- ✅ Efficient reranking (CrossEncoder works best on 500-token chunks, not 8K articles)
- ✅ Only load complete articles for documents with top-ranked chunks (saves I/O)
- ✅ Coherent LLM context (complete articles, not fragments)
- ✅ No chunk merging logic needed (read from source files)
- ✅ Better citations (article-level, not chunk-level)
- ✅ Scalable (can add summarization later for very long articles)

## Project Structure

```
rag_engine/
├── config/
│   ├── __init__.py
│   └── settings.py                    # Pydantic Settings with .env
├── core/
│   ├── __init__.py
│   ├── document_processor.py          # All 3 modes (folder/file/mkdocs)
│   ├── chunker.py                     # Token-aware, code-safe
│   └── metadata_enricher.py           # kbId, title, url, sections, etc.
├── retrieval/
│   ├── __init__.py
│   ├── embedder.py                    # Direct sentence-transformers FRIDA
│   ├── vector_search.py               # Top-K wrapper
│   ├── retriever.py                   # Rerank chunks, load complete articles
│   └── reranker.py                    # CrossEncoder for chunks (optional)
├── storage/
│   ├── __init__.py
│   └── vector_store.py                # LangChain Chroma wrapper
├── llm/
│   ├── __init__.py
│   ├── prompts.py                     # System prompts with citations
│   └── llm_manager.py                 # Reuses cmw-platform-agent LLM mechanics (dynamic token limits)
├── api/
│   ├── __init__.py
│   └── app.py                         # Gradio ChatInterface + gr.api()
├── utils/
│   ├── __init__.py
│   ├── formatters.py                  # Citation formatting
│   └── logging_manager.py             # Structured logging
├── mkdocs/
│   ├── mkdocs_for_rag_indexing.yml    # MkDocs config for RAG export
│   └── rag_indexing_hook.py           # MkDocs hook for Jinja2 compilation
├── scripts/
│   ├── build_index.py                 # CLI indexer (all 3 modes)
│   └── run_mkdocs_export.py           # Optional MkDocs hook runner
├── data/
│   └── chromadb_data/                 # Persistent vector store
├── tests/
│   └── test_smoke.py                  # Smoke tests
├── requirements.txt
├── .env.example
├── pyproject.toml                     # Ruff config
└── README.md
```

## Requirements (Complete)

### requirements.txt

```txt
# Core ML/NLP
torch>=2.0.0
transformers>=4.30.0
sentence-transformers>=2.2.2
tiktoken>=0.5.2

# LangChain Core
langchain>=0.1.0
langchain-core>=0.1.0
langchain-text-splitters>=0.0.1

# LangChain Integrations
langchain-chroma>=0.1.0
langchain-google-genai>=0.0.5
langchain-openai>=0.0.5

# Vector Store
chromadb>=0.4.22

# Web UI
gradio>=5.0.0

# Configuration & Utils
pydantic>=2.5.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0
pyyaml>=6.0

# Data Processing
numpy>=1.24.0
tqdm>=4.66.0

# Testing & Linting
pytest>=7.4.0
pytest-asyncio>=0.21.0
ruff>=0.1.0
```

**Key Dependencies Explained:**

- **torch + transformers**: Required by sentence-transformers
- **sentence-transformers**: Direct FRIDA embeddings with prefix support + CrossEncoder reranking
- **langchain-chroma**: Clean API for ChromaDB with metadata filtering
- **langchain-google-genai / langchain-openai**: Streaming chat models
- **gradio**: ChatInterface + `gr.api()` REST endpoint
- **pydantic-settings**: Type-safe config from `.env`

## Configuration

### .env.example

```env
# LLM Providers
GOOGLE_API_KEY=your_key_here
OPENROUTER_API_KEY=your_key_here  # Optional fallback

# Embedding
EMBEDDING_MODEL=ai-forever/FRIDA
EMBEDDING_DEVICE=cpu  # or 'cuda' if GPU available

# ChromaDB
CHROMADB_PERSIST_DIR=./data/chromadb_data
CHROMADB_COLLECTION=mkdocs_kb

# Retrieval
TOP_K_RETRIEVE=20
TOP_K_RERANK=10
CHUNK_SIZE=500
CHUNK_OVERLAP=150

# Reranker (optional, reranks chunks not articles)
RERANK_ENABLED=true
RERANKER_MODEL=DiTy/cross-encoder-russian-msmarco

# LLM
DEFAULT_LLM_PROVIDER=gemini
DEFAULT_MODEL=gemini-1.5-flash
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=4096

# Gradio
GRADIO_SERVER_NAME=0.0.0.0
GRADIO_SERVER_PORT=7860
```

### config/settings.py (Pydantic)

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from .env file."""
    
    # LLM Providers
    google_api_key: str = ""
    openrouter_api_key: str = ""
    
    # Embedding
    embedding_model: str = "ai-forever/FRIDA"
    embedding_device: str = "cpu"
    
    # ChromaDB
    chromadb_persist_dir: str = "./data/chromadb_data"
    chromadb_collection: str = "mkdocs_kb"
    
    # Retrieval
    top_k_retrieve: int = 20
    top_k_rerank: int = 10
    chunk_size: int = 500
    chunk_overlap: int = 150
    
    # Reranker (reranks chunks, not complete articles)
    rerank_enabled: bool = True
    reranker_model: str = "DiTy/cross-encoder-russian-msmarco"
    
    # LLM
    default_llm_provider: str = "gemini"
    default_model: str = "gemini-1.5-flash"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096
    
    # Gradio
    gradio_server_name: str = "0.0.0.0"
    gradio_server_port: int = 7860
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
```

## Commands

### Setup (One-time)

```bash
# WSL/Linux
python3.11 -m venv .venv-wsl
source .venv-wsl/bin/activate

# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install --upgrade pip
pip install -r rag_engine/requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### Indexing (Choose Mode)

```bash
# Mode 3 (Default): Compiled MD Folder
python rag_engine/scripts/build_index.py \
  --source "phpkb_content/798. Версия 5.0. Текущая рекомендованная/" \
  --mode folder

# Mode 2: Single Combined MD File
python rag_engine/scripts/build_index.py \
  --source "kb.comindware.ru.platform_v5_for_llm_ingestion.md" \
  --mode file

# Mode 1: MkDocs Export (optional)
# First export compiled MD
python rag_engine/scripts/run_mkdocs_export.py \
  --project-dir ../CBAP_MKDOCS_RU \
  --inherit-config mkdocs_guide_complete_ru.yml \
  --output-dir ./data/compiled_md_for_rag

# Then index it
python rag_engine/scripts/build_index.py \
  --source ./data/compiled_md_for_rag \
  --mode mkdocs

# Reindex (update existing)
python rag_engine/scripts/build_index.py --source <path> --reindex
```

### Running

```bash
# Start Gradio UI + API
python rag_engine/api/app.py

# Access at:
# - UI: http://localhost:7860
# - API: http://localhost:7860/api/query_rag
```

### Testing & Linting

```bash
# Run smoke tests
pytest tests/test_smoke.py -v

# Lint changed files
ruff check rag_engine/ --fix

# Format code
ruff format rag_engine/
```

## Implementation Code Examples

### 1. FRIDA Embedder (retrieval/embedder.py)

```python
"""Direct sentence-transformers FRIDA embedder with prefixes."""
from typing import List
from sentence_transformers import SentenceTransformer
import logging

logger = logging.getLogger(__name__)


class FRIDAEmbedder:
    """FRIDA embeddings with explicit prefix support for RAG."""
    
    def __init__(
        self,
        model_name: str = "ai-forever/FRIDA",
        device: str = "cpu",
        max_seq_length: int = 512
    ):
        """Initialize FRIDA embedder.
        
        Args:
            model_name: HuggingFace model identifier
            device: 'cpu' or 'cuda'
            max_seq_length: Max tokens per sequence
        """
        logger.info(f"Loading embedder: {model_name} on {device}")
        self.model = SentenceTransformer(model_name, device=device)
        self.model.max_seq_length = max_seq_length
        logger.info(f"Embedder loaded. Dimension: {self.get_embedding_dim()}")
    
    def embed_query(self, query: str) -> List[float]:
        """Embed a search query using search_query prefix."""
        return self.model.encode(
            query,
            prompt_name="search_query",
            normalize_embeddings=True,
            convert_to_numpy=True
        ).tolist()
    
    def embed_documents(
        self,
        texts: List[str],
        batch_size: int = 8,
        show_progress: bool = True
    ) -> List[List[float]]:
        """Embed documents using search_document prefix."""
        embeddings = self.model.encode(
            texts,
            prompt_name="search_document",
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=True,
            convert_to_numpy=True
        )
        return embeddings.tolist()
    
    def get_embedding_dim(self) -> int:
        """Get embedding dimension."""
        return self.model.get_sentence_embedding_dimension()
```

### 2. Gradio App (api/app.py)

```python
"""Gradio UI with ChatInterface and REST API endpoint."""
import gradio as gr
from typing import Generator
import logging

from rag_engine.config.settings import settings
from rag_engine.retrieval.embedder import FRIDAEmbedder
from rag_engine.storage.vector_store import ChromaStore
from rag_engine.retrieval.retriever import RAGRetriever
from rag_engine.llm.llm_manager import LLMManager
from rag_engine.utils.formatters import format_with_citations

logger = logging.getLogger(__name__)

# Initialize components (singleton pattern)
embedder = FRIDAEmbedder(
    model_name=settings.embedding_model,
    device=settings.embedding_device
)
vector_store = ChromaStore(
    persist_dir=settings.chromadb_persist_dir,
    collection_name=settings.chromadb_collection
)
retriever = RAGRetriever(
    embedder=embedder,
    vector_store=vector_store,
    top_k_retrieve=settings.top_k_retrieve,
    top_k_rerank=settings.top_k_rerank,
    rerank_enabled=settings.rerank_enabled
)
llm_manager = LLMManager(
    provider=settings.default_llm_provider,
    model=settings.default_model,
    temperature=settings.llm_temperature
)


def chat_handler(
    message: str,
    history: list
) -> Generator[str, None, None]:
    """Handle chat messages with streaming response.
    
    Args:
        message: User query
        history: Chat history (not used in Phase 1)
    
    Yields:
        Progressive response tokens
    """
    if not message or not message.strip():
        yield "Пожалуйста, введите вопрос / Please enter a question."
        return
    
    try:
        # Retrieve relevant documents
        logger.info(f"Query: {message}")
        docs = retriever.retrieve(message)
        
        if not docs:
            yield "К сожалению, я не нашел релевантной информации / Sorry, I couldn't find relevant information."
            return
        
        # Stream LLM response
        answer = ""
        for token in llm_manager.stream_response(message, docs):
            answer += token
            yield answer
        
        # Add citations
        final = format_with_citations(answer, docs)
        yield final
        
    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        yield f"Ошибка / Error: {str(e)}"


def query_rag(
    question: str,
    provider: str = "gemini",
    top_k: int = 5
) -> str:
    """REST API endpoint for programmatic access.
    
    Args:
        question: User query
        provider: LLM provider (gemini/openrouter)
        top_k: Number of documents to retrieve
    
    Returns:
        Complete answer with citations
    """
    if not question or not question.strip():
        return "Error: Empty question"
    
    try:
        # Retrieve
        docs = retriever.retrieve(question, top_k=top_k)
        
        # Generate (non-streaming for API)
        answer = llm_manager.generate(question, docs, provider=provider)
        
        # Format with citations
        return format_with_citations(answer, docs)
        
    except Exception as e:
        logger.error(f"API error: {e}", exc_info=True)
        return f"Error: {str(e)}"


# Create ChatInterface
demo = gr.ChatInterface(
    fn=chat_handler,
    title="🤖 Comindware Platform Documentation Assistant",
    description="Ask questions about Comindware Platform in Russian or English",
    examples=[
        "Как использовать N3?",
        "How to configure workflows?",
        "Что такое контекст документа?",
        "Explain process templates",
        "Как настроить права доступа?"
    ],
    theme=gr.themes.Soft(),
    retry_btn="🔄 Retry",
    undo_btn="↩️ Undo",
    clear_btn="🗑️ Clear",
)

# Add REST API endpoint
# See: https://www.gradio.app/docs/gradio/api
gr.api(
    fn=query_rag,
    api_name="query_rag"
)

if __name__ == "__main__":
    logger.info(f"Starting Gradio on {settings.gradio_server_name}:{settings.gradio_server_port}")
    demo.queue().launch(
        server_name=settings.gradio_server_name,
        server_port=settings.gradio_server_port,
        share=False
    )
```

### 3. Document Processor (core/document_processor.py)

```python
"""Unified document processor for all 3 input modes."""
import logging
from pathlib import Path
from typing import List, Dict, Any
import yaml

logger = logging.getLogger(__name__)


class Document:
    """Parsed document with metadata."""
    
    def __init__(
        self,
        content: str,
        metadata: Dict[str, Any]
    ):
        self.content = content
        self.metadata = metadata


class DocumentProcessor:
    """Process documents from folder, file, or mkdocs export."""
    
    def __init__(self, mode: str = "folder"):
        """Initialize processor.
        
        Args:
            mode: 'folder', 'file', or 'mkdocs'
        """
        self.mode = mode
        logger.info(f"DocumentProcessor initialized in {mode} mode")
    
    def process(self, source: str) -> List[Document]:
        """Process documents from source.
        
        Args:
            source: Path to folder, file, or mkdocs export
        
        Returns:
            List of parsed documents with metadata
        """
        if self.mode == "folder":
            return self._process_folder(source)
        elif self.mode == "file":
            return self._process_file(source)
        elif self.mode == "mkdocs":
            return self._process_mkdocs(source)
        else:
            raise ValueError(f"Unknown mode: {self.mode}")
    
    def _process_folder(self, folder_path: str) -> List[Document]:
        """Mode 3: Scan folder for MD files."""
        folder = Path(folder_path)
        if not folder.exists():
            raise FileNotFoundError(f"Folder not found: {folder_path}")
        
        documents = []
        md_files = list(folder.rglob("*.md"))
        logger.info(f"Found {len(md_files)} markdown files in {folder_path}")
        
        for md_file in md_files:
            try:
                content, metadata = self._parse_md_with_frontmatter(md_file)
                
                # Generate kbId from relative path
                rel_path = md_file.relative_to(folder)
                kb_id = str(rel_path.with_suffix(""))
                
                # Default metadata (source_file is critical for retrieving complete articles)
                metadata.setdefault("kbId", kb_id)
                metadata.setdefault("title", md_file.stem)
                metadata.setdefault("source_file", str(md_file.absolute()))
                
                documents.append(Document(content, metadata))
                
            except Exception as e:
                logger.error(f"Failed to process {md_file}: {e}")
                continue
        
        logger.info(f"Successfully processed {len(documents)} documents")
        return documents
    
    def _process_file(self, file_path: str) -> List[Document]:
        """Mode 2: Parse single large MD file."""
        file = Path(file_path)
        if not file.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        logger.info(f"Processing single file: {file_path}")
        content = file.read_text(encoding="utf-8")
        
        # Split by H1 headings (# Title)
        sections = self._split_by_headings(content)
        
        documents = []
        for i, (title, section_content) in enumerate(sections):
            metadata = {
                "kbId": f"{file.stem}_{i}",
                "title": title or f"Section {i}",
                "source_file": str(file),
                "section_index": i
            }
            documents.append(Document(section_content, metadata))
        
        logger.info(f"Split file into {len(documents)} sections")
        return documents
    
    def _process_mkdocs(self, export_dir: str) -> List[Document]:
        """Mode 1: Process MkDocs export with manifest."""
        export_path = Path(export_dir)
        manifest_file = export_path / "rag_manifest.json"
        
        if not manifest_file.exists():
            logger.warning(f"No manifest found, falling back to folder mode")
            return self._process_folder(export_dir)
        
        import json
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        logger.info(f"Processing MkDocs export: {manifest.get('total_files')} files")
        
        documents = []
        for file_path in manifest.get("files", []):
            md_file = export_path / file_path
            if md_file.exists():
                content, metadata = self._parse_md_with_frontmatter(md_file)
                metadata.setdefault("kbId", str(Path(file_path).with_suffix("")))
                metadata.setdefault("title", md_file.stem)
                metadata["source_type"] = "mkdocs_export"
                documents.append(Document(content, metadata))
        
        logger.info(f"Processed {len(documents)} MkDocs documents")
        return documents
    
    def _parse_md_with_frontmatter(self, file_path: Path) -> tuple[str, Dict]:
        """Parse markdown file with optional YAML frontmatter."""
        content = file_path.read_text(encoding="utf-8")
        
        # Check for frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1])
                    return parts[2].strip(), frontmatter or {}
                except yaml.YAMLError as e:
                    logger.warning(f"Failed to parse frontmatter in {file_path}: {e}")
        
        return content, {}
    
    def _split_by_headings(self, content: str) -> List[tuple[str, str]]:
        """Split content by H1 headings."""
        lines = content.split("\n")
        sections = []
        current_title = None
        current_content = []
        
        for line in lines:
            if line.startswith("# "):
                if current_content:
                    sections.append((current_title, "\n".join(current_content)))
                current_title = line[2:].strip()
                current_content = [line]
            else:
                current_content.append(line)
        
        # Add last section
        if current_content:
            sections.append((current_title, "\n".join(current_content)))
        
        return sections
```

### 4. Retriever with Complete Article Loading (retrieval/retriever.py)

```python
"""RAG retriever that loads complete articles based on matched chunks."""
from typing import List, Dict, Any
from pathlib import Path
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class Article:
    """Complete article with metadata."""
    
    def __init__(self, kb_id: str, content: str, metadata: Dict[str, Any]):
        self.kb_id = kb_id
        self.content = content
        self.metadata = metadata


class RAGRetriever:
    """Retrieve complete articles based on chunk matches."""
    
    def __init__(
        self,
        embedder,
        vector_store,
        llm_manager,  # NEW: Pass LLM manager for dynamic token limits
        reranker=None,
        top_k_retrieve: int = 20,
        top_k_rerank: int = 10
    ):
        self.embedder = embedder
        self.vector_store = vector_store
        self.llm_manager = llm_manager  # For dynamic context window
        self.reranker = reranker
        self.top_k_retrieve = top_k_retrieve
        self.top_k_rerank = top_k_rerank
    
    def retrieve(self, query: str) -> List[Article]:
        """Retrieve complete articles for query.
        
        Args:
            query: User query string
            
        Returns:
            List of complete articles within context budget
        """
        # 1. Embed query
        query_vec = self.embedder.embed_query(query)
        
        # 2. Vector search on chunks
        chunk_results = self.vector_store.query(
            query_vec,
            top_k=self.top_k_retrieve
        )
        
        if not chunk_results:
            logger.warning("No chunks found for query")
            return []
        
        logger.info(f"Retrieved {len(chunk_results)} chunks from vector store")
        
        # 3. Rerank chunks (more efficient than reranking complete articles)
        if self.reranker:
            chunk_results = self._rerank_chunks(query, chunk_results)
            logger.info(f"Reranked to top-{len(chunk_results)} chunks")
        
        # 4. Group top-ranked chunks by kbId (article identifier)
        articles_map = defaultdict(list)
        for chunk in chunk_results:
            kb_id = chunk.metadata.get("kbId")
            if kb_id:
                articles_map[kb_id].append(chunk)
        
        logger.info(f"Top chunks belong to {len(articles_map)} unique articles")
        
        # 5. Read complete articles from filesystem (only for articles with top-ranked chunks)
        articles = []
        for kb_id, chunks in articles_map.items():
            # Use first chunk's metadata to get source file
            source_file = chunks[0].metadata.get("source_file")
            if not source_file:
                logger.warning(f"No source_file for kbId={kb_id}")
                continue
            
            try:
                article_content = self._read_article(source_file)
                article = Article(
                    kb_id=kb_id,
                    content=article_content,
                    metadata=chunks[0].metadata  # Use first chunk's metadata
                )
                # Store matched chunks for reference
                article.matched_chunks = chunks
                articles.append(article)
            except Exception as e:
                logger.error(f"Failed to read article {source_file}: {e}")
                continue
        
        logger.info(f"Loaded {len(articles)} complete articles")
        
        # 6. Apply context budgeting (select articles that fit within token limit)
        articles = self._apply_context_budget(articles)
        
        return articles
    
    def _read_article(self, source_file: str) -> str:
        """Read complete article from filesystem.
        
        Args:
            source_file: Absolute path to article file
            
        Returns:
            Complete article content
        """
        file_path = Path(source_file)
        if not file_path.exists():
            raise FileNotFoundError(f"Article file not found: {source_file}")
        
        # Read file, skip frontmatter if present
        content = file_path.read_text(encoding="utf-8")
        
        # Remove YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()
        
        return content
    
    def _rerank_chunks(self, query: str, chunks: List) -> List:
        """Rerank chunks with CrossEncoder.
        
        Args:
            query: User query
            chunks: List of chunks to rerank
            
        Returns:
            Top-K reranked chunks
        """
        try:
            # Score all chunks with CrossEncoder (efficient on 500-token chunks)
            chunk_texts = [chunk.text for chunk in chunks]
            scores = self.reranker.score(query=query, documents=chunk_texts)
            
            # Combine chunks with scores and sort
            scored_chunks = list(zip(chunks, scores))
            scored_chunks.sort(key=lambda x: x[1], reverse=True)
            
            # Return top-K chunks
            top_chunks = [chunk for chunk, _ in scored_chunks[:self.top_k_rerank]]
            logger.info(f"Reranked {len(chunks)} → {len(top_chunks)} chunks")
            
            return top_chunks
            
        except Exception as e:
            logger.warning(f"Reranking failed, returning original chunks: {e}")
            return chunks[:self.top_k_rerank]
    
    def _apply_context_budget(self, articles: List[Article]) -> List[Article]:
        """Select articles within context budget using dynamic token limits.
        
        Args:
            articles: Sorted list of articles
            
        Returns:
            Articles that fit within context budget
        """
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        
        # Get dynamic context window from LLM manager (not hardcoded!)
        context_window = self.llm_manager.get_current_llm_context_window()
        
        # Reserve 20% for output + prompt overhead
        max_context_tokens = int(context_window * 0.75)
        
        logger.info(f"Context window: {context_window} tokens, using {max_context_tokens} for articles")
        
        selected = []
        total_tokens = 0
        
        for article in articles:
            article_tokens = len(enc.encode(article.content))
            
            if total_tokens + article_tokens > max_context_tokens:
                logger.info(f"Context budget reached: {total_tokens}/{max_context_tokens} tokens")
                break
            
            selected.append(article)
            total_tokens += article_tokens
        
        logger.info(f"Selected {len(selected)} articles ({total_tokens} tokens, {(total_tokens/context_window*100):.1f}% of context window)")
        return selected
```

### 5. MkDocs Export Hook (rag_engine/mkdocs/rag_indexing_hook.py)

**For Mode 1 (optional, for live MkDocs repos):**

**Location**: `rag_engine/mkdocs/rag_indexing_hook.py`

```python
"""
MkDocs hook to export Jinja2-compiled markdown for RAG indexing.
Stored in rag_engine/mkdocs/ folder for better organization.
"""
import json
from datetime import datetime
from pathlib import Path
import yaml


def on_page_markdown(markdown, page, config, files):
    """Called AFTER Jinja2 processing, BEFORE HTML conversion."""
    page._compiled_md_for_rag = markdown
    return markdown


def on_post_page(output, page, config):
    """Save compiled markdown to RAG folder."""
    try:
        compiled_md = getattr(page, '_compiled_md_for_rag', page.markdown)
        output_dir = Path(config['site_dir'])
        rel_path = Path(page.file.src_path)
        output_file = output_dir / rel_path
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            if page.meta:
                f.write('---\n')
                yaml.dump(page.meta, f, allow_unicode=True, default_flow_style=False)
                f.write('---\n\n')
            f.write(compiled_md)
    except Exception as e:
        print(f"⚠️  Failed to export {page.file.src_path}: {e}")
    
    return output


def on_post_build(config):
    """Create manifest for RAG indexer."""
    output_dir = Path(config['site_dir'])
    md_files = sorted(output_dir.rglob('*.md'))
    manifest = {
        'total_files': len(md_files),
        'files': [str(f.relative_to(output_dir)) for f in md_files],
        'build_date': datetime.now().isoformat(),
        'config_name': config.get('site_name'),
        'source_type': 'mkdocs_pipeline'
    }
    with open(output_dir / 'rag_manifest.json', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"✅ RAG Export: {len(md_files)} compiled MD files → {output_dir}")
```

**MkDocs config for Mode 1 (rag_engine/mkdocs/mkdocs_for_rag_indexing.yml):**

**Location**: `rag_engine/mkdocs/mkdocs_for_rag_indexing.yml`

```yaml
# Inherit from complete guide to resolve all Jinja2 variables
INHERIT: mkdocs_guide_complete_ru.yml

# Override output directory
site_dir: compiled_md_for_rag

# Add custom hook (relative path from MkDocs project root)
hooks:
  - rag_engine/mkdocs/rag_indexing_hook.py

# Disable unnecessary plugins
plugins:
  - search: false
```

**Note**: When using `run_mkdocs_export.py`, the script will copy these files to the MkDocs project's `.rag_export/` folder.

### 6. Ruff Configuration (pyproject.toml)

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
]
ignore = [
    "E501",  # line too long (handled by formatter)
    "B008",  # do not perform function calls in argument defaults
    "C901",  # too complex
]

[tool.ruff.lint.isort]
known-first-party = ["rag_engine"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
python_functions = "test_*"
```

## Reranking (Optional, with Graceful Degradation)

### Prioritized Models (for Chunk Reranking)

1. `DiTy/cross-encoder-russian-msmarco` **(default, optimized for Russian, 512 tokens)**
2. `BAAI/bge-reranker-v2-m3` (multilingual, up to 8K tokens)
3. `jinaai/jina-reranker-v2-base-multilingual` (multilingual fallback)

### Implementation Strategy

**Rerank chunks, then load complete articles:**
1. Vector search retrieves top-20 chunks
2. Rerank chunks with CrossEncoder → top-10 chunks
3. Group top-10 chunks by `kbId` (article identifier)
4. Read complete articles from filesystem for those `kbId` values
5. Apply context budgeting, select top-5 articles
6. Feed complete articles to LLM

**Why rerank chunks instead of articles?**
- ✅ CrossEncoders work best on shorter text (500 tokens optimal)
- ✅ More computationally efficient than scoring 8K-token articles
- ✅ Only load complete articles for documents with highly-ranked chunks
- ✅ Better reranking accuracy (focused chunks vs diluted full articles)

### Config

- `RERANK_ENABLED=true`
- `TOP_K_RETRIEVE=20` (chunks retrieved from vector store)
- `TOP_K_RERANK=10` (chunks after reranking, then grouped into ~5 articles)
- `RERANKER_MODEL=DiTy/cross-encoder-russian-msmarco` (512 tokens, perfect for 500-token chunks)

## Quality Gates & Acceptance Criteria

### Linting

```bash
# All Ruff checks must pass
ruff check rag_engine/ --fix
ruff format rag_engine/
```

### Testing

```bash
# All smoke tests must pass
pytest tests/test_smoke.py -v

# Coverage:
# - Document processing (all 3 modes)
# - Embedding (query + documents)
# - Vector store (add + search + retrieve)
# - Reranker (with model + identity fallback)
# - LLM (streaming response)
# - Gradio (UI loads + API endpoint)
```

### Acceptance Checklist

**Indexing:**

- [ ] Mode 3 (folder): Index ≥10 MD files successfully
- [ ] Mode 2 (file): Parse single large MD file into chunks
- [ ] Mode 1 (mkdocs): Export + index compiled MD (optional but functional)
- [ ] Chroma collection persists with metadata
- [ ] No empty chunks; avg chunk size > 100 chars

**Retrieval:**

- [ ] Query returns ≥1 relevant document with metadata
- [ ] Citations include kbId, title, url, section_anchor
- [ ] Reranker runs when model available
- [ ] Identity fallback works when reranker unavailable

**UI/API:**

- [ ] Gradio ChatInterface loads at localhost:7860
- [ ] Streaming works (tokens appear progressively)
- [ ] Citations formatted as markdown links
- [ ] REST API endpoint `/api/query_rag` responds to POST

**Code Quality:**

- [ ] All Ruff checks pass
- [ ] Smoke tests pass
- [ ] README has setup + usage instructions
- [ ] .env.example has all required keys

## Phase 1 MVP - To-Do List

**Note:** Complete tasks in order; test each component before moving to next.

- [ ] Create project structure with `__init__.py` files in all folders
- [ ] Create `requirements.txt` with all 15 dependencies
- [ ] Create `.env.example` with all configuration keys
- [ ] Create `pyproject.toml` with Ruff configuration
- [ ] Implement `config/settings.py` with Pydantic Settings
- [ ] Test: Settings load from .env correctly
- [ ] Implement `core/document_processor.py` with all 3 modes (folder/file/mkdocs)
- [ ] Implement `core/chunker.py` with tiktoken, 500/150 tokens (fits FRIDA 512 window), code-safe
- [ ] Implement `core/metadata_enricher.py` (kbId, title, url, sections, has_code, etc.)
- [ ] Test: Process sample MD folder successfully
- [ ] Implement `retrieval/embedder.py` (direct sentence-transformers FRIDA with prefixes)
- [ ] Test: Embedder loads FRIDA model and embeds query + documents
- [ ] Implement `storage/vector_store.py` (LangChain Chroma wrapper with persistence)
- [ ] Implement `retrieval/vector_search.py` (top-K search wrapper)
- [ ] Test: Add documents to Chroma and retrieve them
- [ ] Implement `retrieval/reranker.py` (CrossEncoder for 500-token chunks, DiTy default model)
- [ ] Test: Reranker works with chunks and returns top-K
- [ ] Implement `retrieval/retriever.py` (rerank chunks first, group by kbId, read complete articles from source_file, context budgeting)
- [ ] Test: Retrieve returns complete articles for documents with top-ranked chunks
- [ ] Implement `llm/prompts.py` (system prompt with citation instructions, bilingual)
- [ ] Implement `llm/llm_manager.py` (Gemini streaming, OpenRouter fallback via LangChain)
- [ ] Test: LLM generates streaming response
- [ ] Implement `utils/formatters.py` (format_with_citations, context assembly)
- [ ] Implement `utils/logging_manager.py` (structured logging setup)
- [ ] Implement `api/app.py` (Gradio ChatInterface + gr.api() REST endpoint)
- [ ] Test: Gradio UI loads at localhost:7860
- [ ] Test: ChatInterface accepts query and streams response
- [ ] Test: Citations formatted correctly in output
- [ ] Test: REST API endpoint `/api/query_rag` responds
- [ ] Implement `scripts/build_index.py` (CLI with argparse, --source, --mode, --reindex)
- [ ] Test: Index Mode 3 (folder) with sample data
- [ ] Test: Index Mode 2 (file) with sample data
- [ ] Implement `scripts/run_mkdocs_export.py` (optional MkDocs hook runner for Mode 1)
- [ ] Create `rag_indexing_hook.py` for MkDocs export
- [ ] Test: MkDocs export creates compiled MD + manifest (if testing Mode 1)
- [ ] Create `tests/test_smoke.py` with comprehensive test coverage
- [ ] Test: All smoke tests pass
- [ ] Run Ruff on all files and fix issues
- [ ] Write comprehensive `README.md` with setup, usage, examples, troubleshooting
- [ ] Create sample `.env.example` with all keys documented
- [ ] Test full E2E pipeline: index → query → retrieve → rerank → generate → citations
- [ ] Verify Chroma persistence (restart app, data remains)
- [ ] Verify reranker optional (works with and without model)
- [ ] Verify both LLM providers work (Gemini + OpenRouter fallback)
- [ ] Final acceptance testing against all criteria
- [ ] Document any known issues or limitations
- [ ] Mark Phase 1 MVP complete

## Success Criteria (MVP Complete)

Phase 1 MVP is complete when:

- ✅ All 3 input modes functional (Mode 3 tested, Mode 2 works, Mode 1 available)
- ✅ FRIDA embeddings with prefixes working
- ✅ Chroma persistent vector store operational
- ✅ Optional CrossEncoder reranking with identity fallback
- ✅ Gemini/OpenRouter LLM streaming functional
- ✅ Gradio ChatInterface + REST API both operational
- ✅ Citations formatted as markdown links
- ✅ All tests pass, linting clean
- ✅ README with comprehensive documentation

**Estimated time:** 6-8 weeks for single developer

## Troubleshooting

### FRIDA Model Download Fails

```bash
# Pre-download model
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('ai-forever/FRIDA')"
```

### ChromaDB Persistence Issues

```bash
# Check permissions
ls -la data/chromadb_data

# Reset if corrupted
rm -rf data/chromadb_data
```

### Gradio Port Already in Use

```env
# Change port in .env
GRADIO_SERVER_PORT=7861
```

### Gemini API Rate Limits

```env
# Switch to OpenRouter
DEFAULT_LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_key_here
```

### Import Errors

```bash
# Verify venv is activated
which python  # Should show .venv or .venv-wsl path

# Reinstall dependencies
pip install -r rag_engine/requirements.txt --force-reinstall
```

## Next Steps After Phase 1

### Phase 1.5 (Optional Enhancements)

- Advanced reranking with metadata boosts
- Query caching for performance
- Observability (LangSmith/Langfuse integration)
- MMR diversification
- Performance optimizations

### Phase 2 (Future)

- FastAPI backend migration
- Authentication and authorization
- Multi-user support
- Advanced RAG techniques (hypothetical questions, query rewriting)
- A/B testing framework

## Notes

- **Hybrid approach: chunk-level reranking + article-level context** - 500-token chunks for search and reranking (fit FRIDA's 512-token window and CrossEncoder sweet spot), complete articles fed to LLM via `source_file` metadata
- **Efficient reranking** - CrossEncoder scores 500-token chunks (not 8K articles) for better performance and accuracy
- **Dynamic token limits** - LLM manager reports model-specific context windows (`get_current_llm_context_window()`), eliminating hardcoded limits
- **Reuses cmw-platform-agent LLM mechanics** - Battle-tested LLMManager with multi-provider support, token tracking, and streaming
- **MkDocs files in dedicated folder** - Moved to `rag_engine/mkdocs/` for better organization
- **MkDocs export (Mode 1) is fully implemented** - includes hook, YAML config, and export script
- **All 3 modes are included** - Mode 3 tested first for fastest MVP, but all are functional
- **LangChain purity relaxed** - Direct sentence-transformers for embeddings/reranking is pragmatic
- **DiTy reranker for Russian chunks** - Optimized for 512 tokens, perfect for our 500-token chunks
- **Graceful degradation everywhere** - Reranker, API keys, etc. all have fallbacks
- **Citation-first design** - Always include source links with section anchors
- **Type-safe configuration** - Pydantic Settings with .env validation
- **Context budgeting uses 75% of window** - Reserves 25% for prompt overhead and output
- **No summarization in Phase 1** - Can be added later if articles exceed context limits

---

**Last Updated:** October 28, 2025 (Updated: Hybrid approach + dynamic token limits + LLM mechanics reuse)

**Key Updates:**
- Hybrid approach: Rerank chunks (not articles), feed complete articles to LLM
- Dynamic token limits from LLM manager (not hardcoded)
- Reuses robust LLM mechanics from cmw-platform-agent
- MkDocs files moved to `rag_engine/mkdocs/` folder

**Status:** ✅ Ready for implementation

**Timeline:** 6-8 weeks for single developer

### High-Level To-dos

- [ ] Create project tree under rag_engine/ with __init__.py files
- [ ] Implement config/settings.py with knobs and defaults (500/150 chunk size)
- [ ] Implement document_processor.py to scan compiled MD folder (store source_file in metadata)
- [ ] Implement chunker.py with 500/150 token overlap and code-block safety (fits FRIDA 512 window)
- [ ] Implement metadata_enricher.py with minimal fields (ensure source_file is absolute path)
- [ ] Implement retrieval/embedder.py using FRIDA with prefixes (512 max_seq_length)
- [ ] Implement storage/vector_store.py Chroma CRUD + persistence
- [ ] Implement vector_search.py (top-K chunk retrieval)
- [ ] Implement retriever.py (rerank chunks, group by kbId, read complete articles from source_file, context budgeting)
- [ ] Add optional CrossEncoder reranker for chunks (DiTy default); fallback to identity
- [ ] Implement llm_manager.py Gemini streaming; OpenRouter fallback
- [ ] Build Gradio ChatInterface in api/app.py with streaming and citations
- [ ] Add scripts/build_index.py CLI for folder ingestion
- [ ] Add requirements.txt and .env.example; write README.md