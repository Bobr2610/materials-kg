"""LangChain 1.0 tool for RAG context retrieval.

This tool is self-sufficient and handles all retrieval mechanics internally.
The agent only needs to import and use the tool - no setup required.

Now supports async execution to prevent blocking the event loop during
concurrent requests.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
from contextvars import ContextVar
from pathlib import Path
from typing import Literal

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, Field, field_validator

from kg_engine.config.settings import get_collection_name, settings
from kg_engine.retrieval.retriever import Article, RAGRetriever
from kg_engine.storage.vector_store import ChromaStore
from kg_engine.utils.context_tracker import AgentContext
from kg_engine.utils.path_utils import normalize_path
from kg_engine.utils.thread_pool import run_in_thread_pool

logger = logging.getLogger(__name__)

ProductVersion = Literal["v5", "v6"]
DEFAULT_PRODUCT_VERSION: ProductVersion = "v6"
_ui_product_version: ContextVar[ProductVersion] = ContextVar("ui_product_version", default="v6")


def set_ui_product_version(version: ProductVersion) -> None:
    _ui_product_version.set(version)


def get_effective_product_version(explicit: ProductVersion | None = None) -> ProductVersion:
    return explicit or _ui_product_version.get()

# Module-level retriever instance (lazy singleton)
_retriever: RAGRetriever | None = None
# When running inside the Gradio app, the app injects its pre-initialized retriever
# so FRIDA/direct embedder is never loaded in a worker thread (avoids crash on Windows).
_app_retriever: RAGRetriever | None = None
_retriever_init_lock = threading.Lock()
# Versioned retriever registry: one per product_version (v5, v6)
_retrievers: dict[str, RAGRetriever] = {}

DEFAULT_CORPORA_ROOT = ".reference-repos/cbap-mkdocs-ru"
V5_CORPUS_SUBDIR = "phpkb_content_rag/798-platform_v5"
V6_CORPUS_SUBDIR = "phpkb_content_rag/896-platform_v6"


def get_corpus_dir(version: str) -> str:
    root = settings.corpora_root or DEFAULT_CORPORA_ROOT
    subdir = V5_CORPUS_SUBDIR if version == "v5" else V6_CORPUS_SUBDIR
    return str(Path(root) / subdir)


def set_app_retriever(retriever: RAGRetriever | None) -> None:
    """Inject the app's pre-initialized retriever for use by the tool.

    When the Gradio app starts, it creates embedder and retriever on the main thread.
    Calling this with that retriever ensures the agent path uses the same instance
    and never loads FRIDA/sentence_transformers in a worker thread (which can
    crash on Windows). Pass None to clear (e.g. tests).
    """
    global _app_retriever
    _app_retriever = retriever


def _get_or_create_retriever(version: str | None = None) -> RAGRetriever:
    """Get or create the retriever instance (lazy singleton, optionally per-version).

    When a version is provided, always creates/returns a version-specific retriever
    with its own ChromaStore pointed at the versioned collection (reusing embedder
    and llm_manager from the app-injected or default retriever to avoid redundant init).
    When no version is given, returns the app-injected retriever if set, otherwise
    lazily creates the default retriever.
    """
    global _retriever

    if version:
        cached = _retrievers.get(version)
        if cached is not None:
            return cached

        # Resolve base (embedder + llm_manager) from whichever source is available
        if _app_retriever is not None:
            base = _app_retriever
        elif _retriever is not None:
            base = _retriever
        else:
            base = None

        collection = get_collection_name(version)
        vector_store = ChromaStore(collection_name=collection)
        if base is not None:
            ret = RAGRetriever(
                embedder=base.embedder,
                vector_store=vector_store,
                llm_manager=base.llm_manager,
                top_k_retrieve=settings.top_k_retrieve,
                top_k_rerank=settings.top_k_rerank,
                rerank_enabled=settings.rerank_enabled,
            )
        else:
            from kg_engine.llm.llm_manager import LLMManager
            from kg_engine.retrieval.embedder import FRIDAEmbedder

            ret = RAGRetriever(
                embedder=FRIDAEmbedder(
                    model_name=settings.embedding_model,
                    device=settings.embedding_device,
                ),
                vector_store=vector_store,
                llm_manager=LLMManager(
                    provider=settings.default_llm_provider,
                    model=settings.default_model,
                    temperature=settings.llm_temperature,
                ),
                top_k_retrieve=settings.top_k_retrieve,
                top_k_rerank=settings.top_k_rerank,
                rerank_enabled=settings.rerank_enabled,
            )
        _retrievers[version] = ret
        return ret

    if _app_retriever is not None:
        return _app_retriever

    if _retriever is None:
        with _retriever_init_lock:
            if _retriever is not None:
                return _retriever
        from kg_engine.llm.llm_manager import LLMManager
        from kg_engine.retrieval.embedder import FRIDAEmbedder

        logger.info("Initializing retriever for retrieve_context tool (first use)")

        embedder = FRIDAEmbedder(
            model_name=settings.embedding_model,
            device=settings.embedding_device,
        )
        vector_store = ChromaStore(
            collection_name=settings.chromadb_collection,
        )
        llm_manager = LLMManager(
            provider=settings.default_llm_provider,
            model=settings.default_model,
            temperature=settings.llm_temperature,
        )

        _retriever = RAGRetriever(
            embedder=embedder,
            vector_store=vector_store,
            llm_manager=llm_manager,
            top_k_retrieve=settings.top_k_retrieve,
            top_k_rerank=settings.top_k_rerank,
            rerank_enabled=settings.rerank_enabled,
        )
        logger.info("Retriever initialized successfully")

    return _retriever


class RetrieveContextSchema(BaseModel):
    """Retrieve relevant context articles from the knowledge base using semantic search.

    This tool searches the Comindware knowledge base for articles relevant to your query.

    It returns formatted context with article titles, URLs, and content ready for consumption.

    **Use this tool:**
    - When you need information from the knowledge base to answer a user's question
    - When the user's request is vague or ambiguous call this tool multiple times
      with unique queries to find comprehensive information
    - When you need to explore different aspects of a topic
    - When initial results are insufficient and you want to refine your search

    **Query best practices:**
    - Always query the knowledge base in Russian, even if the question is in English.
    - Use specific, focused queries for better results (e.g., "настройка аутентификации" not "аутентификация").
    - Combine results from multiple queries to build a comprehensive understanding.
    - Usually 1-3 quality search queries (with reasonable top_k) are enough to answer the question.
    - If no results found, try broader, alternative phrasings, synonyms or related terms.
    - Break down vague or complex questions into multiple focused queries with different query angles.
    - The knowledge base is focused to the Comindware Platform and its use cases, hence:
      - DO NOT include the "Comindware Platform" term in search queries unless really needed.
      - For general, business or industry-specific questions extract technical and platform-relevant search queries (excluding industry/business keywords).

    **Query decomposition:**
    - For better search results, paraphrase and split the user question into several unique queries, using different phrases and keywords.
    - Call retrieve_context multiple times with unique queries. Do not search for semantically similar queries more than once.

    **Examples:**
    - User question: Как всё настроить?
      - Unique search queries:
        * настройка и запуск ПО
        * подготовка к установке
        * системные требования
    - User question: Как настроить взаимодействие между подразделениями
      - Unique search queries:
        * настройка почты
        * получение и отправка почты
        * подключения и пути передачи данных
        * SMTP/IMAP/Exchange
        * межпроцессное взаимодействие
        * сообщения
        * HTTP/HTTPS
        * REST API
    - User question: "Как писать тройки"
      - Unique search queries:
        * написание выражений на N3
        * синтаксис N3
        * примеры N3
        * справочник по N3
        * язык N3
    - User question: "Как провести отпуск"
      - Unique search queries:
        * бизнес-приложения
        * шаблоны
        * атрибуты
        * записи
        * формы

    Returns:
        JSON string containing structured article data. Format:
        {
          "articles": [
            {
              "kb_id": "string",
              "title": "string",
              "url": "string",
              "content": "string",
              "metadata": {...}
            }
          ],
          "metadata": {
            "query": "string",
            "top_k_requested": "int | null",
            "articles_count": "int",
            "has_results": "bool"
          }
        }

        Each article includes title, URL, content (uncompressed), and complete metadata
        including ranking information (rerank_score, normalized_rank) for citations.
        If no documents found, returns JSON with empty articles array and has_results: false.

    **Note**: You can call this tool multiple times in the same conversation turn to gather
    information from different angles or aspects of a topic. Each call is independent.
    """

    query: str = Field(
        ...,
        description="Search query to find relevant articles from the knowledge base. "
        "This should be unique, clear, specific, focused. "
        "The knowledge base is in Russian — queries should be in Russian for best results, "
        "even if the user's question is in English.",
        min_length=1,
    )
    top_k: int | None = Field(
        default=None,
        description=f"Maximum number of articles to retrieve (1–20). "
        f"Default: {settings.top_k_rerank} articles. "
        "Use 3–5 for focused retrieval, 10+ for comprehensive coverage.",
    )
    exclude_kb_ids: list[str] | None = Field(
        default=None,
        description="Optional list of article kb_ids to exclude from results (for deduplication). "
        "Use this to prevent retrieving articles you've already fetched in previous tool calls. ",
    )
    product_version: ProductVersion | None = Field(
        default=None,
        description="Product version to filter search results. "
        "When omitted, the version selected in the UI is used automatically. "
        "Specify explicitly to search a specific version's docs "
        "(e.g., 'v5' for version 5.0 released 2025, 'v6' for version 6.0 released 2026).",
    )

    @field_validator("query", mode="before")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validate that query is not empty."""
        if isinstance(v, str) and v.strip() == "":
            raise ValueError("query must be a non-empty string")
        return v.strip() if isinstance(v, str) else v

    @field_validator("top_k", mode="before")
    @classmethod
    def validate_top_k(cls, v: int | str | None) -> int | None:
        """Validate that top_k is positive if provided."""
        if v is not None:
            if isinstance(v, str):
                try:
                    v = int(v)
                except ValueError as exc:
                    raise ValueError("top_k must be a valid integer") from exc
            if v <= 0:
                raise ValueError("top_k must be a positive integer")
        return v

    @field_validator("exclude_kb_ids", mode="before")
    @classmethod
    def _convert_exclude_kb_ids(cls, v):
        """Convert exclude_kb_ids to proper format."""
        if v is None:
            return None
        if isinstance(v, str):
            return [v] if v else None
        if isinstance(v, list):
            return [str(item) for item in v] if v else None
        return None


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

        articles_data.append(
            {
                "kb_id": article.kb_id,
                "title": title,
                "url": url,
                "content": article.content,  # Uncompressed content
                "metadata": article_metadata,  # Includes rerank_score, normalized_rank
            }
        )

    result = {
        "articles": articles_data,
        "metadata": {
            "query": query,
            "top_k_requested": top_k,
            "articles_count": len(articles_data),
            "has_results": len(articles_data) > 0,
        },
    }
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


def _read_article(source_file: str) -> str:
    """Read complete article from filesystem, stripping YAML frontmatter."""
    file_path = normalize_path(source_file)
    if not file_path.exists():
        raise FileNotFoundError(f"Article file not found: {source_file}")
    content = file_path.read_text(encoding="utf-8")
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2].strip()
    return content


async def _fetch_articles_by_kb_ids_core(kb_ids: list[str], version: str | None = None) -> str:
    """Fetch articles by kbId from ChromaDB metadata, read full files, format as JSON."""
    version = get_effective_product_version(version)
    collection = get_collection_name(version)
    store = ChromaStore(collection_name=collection)
    articles: list[Article] = []

    for kb_id in kb_ids:
        meta = await store.get_by_kb_id_async(kb_id)
        if meta is None:
            continue
        source_file = meta.get("source_file", "")
        if not source_file:
            continue
        try:
            content = _read_article(source_file)
        except FileNotFoundError:
            continue
        articles.append(
            Article(kb_id=kb_id, content=content, metadata=dict(meta))
        )

    return _format_articles_to_json(articles, query=f"fetch:{','.join(kb_ids)}", top_k=None)


async def _retrieve_context_core(
    query: str,
    top_k: int | None = None,
    exclude_kb_ids: list[str] | None = None,
    product_version: ProductVersion | None = None,
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> str:
    try:
        version = get_effective_product_version(product_version)
        retriever = await run_in_thread_pool(_get_or_create_retriever, version)

        # Use async retrieval directly
        docs = await retriever.retrieve_async(query, top_k=top_k)

        # Determine which kb_ids to exclude (explicit argument takes precedence, then context)
        excluded_set: set[str] = set()
        if exclude_kb_ids:
            excluded_set = set(exclude_kb_ids or [])
        elif runtime and hasattr(runtime, "context") and runtime.context:
            excluded_set = getattr(runtime.context, "fetched_kb_ids", set())

        # Filter out excluded articles
        if excluded_set:
            original_count = len(docs)
            docs = [doc for doc in docs if doc.kb_id not in excluded_set]
            filtered_count = original_count - len(docs)
            if filtered_count > 0:
                logger.info(
                    "Filtered out %d already-fetched articles, returning %d new articles for query: %s",
                    filtered_count,
                    len(docs),
                    query,
                )

        logger.info("Retrieved %d articles for query: %s", len(docs), query)

        # Formatting is fast and CPU-bound, can stay in event loop
        return _format_articles_to_json(docs, query, top_k)
    except Exception as exc:  # noqa: BLE001
        logger.error("Error during retrieval: %s", exc, exc_info=True)
        return json.dumps(
            {
                "error": f"Retrieval failed: {str(exc)}",
                "articles": [],
                "metadata": {
                    "has_results": False,
                    "query": query,
                    "top_k_requested": top_k,
                    "articles_count": 0,
                },
            },
            ensure_ascii=False,
        )


@tool("retrieve_context", args_schema=RetrieveContextSchema, description=RetrieveContextSchema.__doc__)
async def retrieve_context(
    query: str,
    top_k: int | None = None,
    exclude_kb_ids: list[str] | None = None,
    product_version: ProductVersion | None = None,
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> str:
    return await _retrieve_context_core(
        query=query,
        top_k=top_k,
        exclude_kb_ids=exclude_kb_ids,
        product_version=product_version,
        runtime=runtime,
    )


class FetchArticleSchema(BaseModel):
    """Fetch complete knowledge base articles by their kbId.

    Use this tool to retrieve full article content when you already know
    the article IDs (e.g., from previous search results or citations).
    This is faster than semantic search and returns exact article content.

    Returns the same JSON format as retrieve_context for compatibility.
    """

    kb_ids: list[str] = Field(
        default_factory=list,
        description="List of article kbIds to fetch. Use extract_numeric_kbid "
        "to normalize IDs from titles or URLs.",
    )
    product_version: ProductVersion | None = Field(
        default=None,
        description="Product version to filter fetch results. "
        "When omitted, the version selected in the UI is used automatically. "
        "Specify explicitly to fetch from a specific version's docs "
        "(e.g., 'v5' for version 5.0 released 2025, 'v6' for version 6.0 released 2026).",
    )


@tool("fetch_kb_articles", args_schema=FetchArticleSchema, description=FetchArticleSchema.__doc__)
async def fetch_kb_articles(
    kb_ids: list[str],
    product_version: ProductVersion | None = None,
) -> str:
    return await _fetch_articles_by_kb_ids_core(kb_ids, product_version)


class GrepKbArticlesSchema(BaseModel):
    """Search knowledge base articles by regex/pattern matching (ripgrep).

    This tool runs a full-text search over the raw Markdown corpus files
    and returns articles where the pattern matches. Use this when you need
    to find specific terms, error messages, API names, or technical keywords
    that may not surface well through semantic vector search.

    **When to use grep vs semantic search (retrieve_context):**
    - Use **grep** for: exact terms, error codes, API names, identifiers,
      specific N3 syntax, version numbers, or anything pattern-based.
    - Use **retrieve_context** for: natural-language questions, conceptual
      topics, broad exploration, or when you don't know the exact terms.

    Returns the same JSON format as retrieve_context, with additional
    grep-specific metadata (match_count, matched_lines).
    """

    pattern: str = Field(
        ...,
        description="Regex pattern (ripgrep-compatible) to search in corpus. "
        "Examples: 'api_key_env', 'настр\\w+', 'docker\\.com', "
        "'статус\\s+(запроса|задачи)', 'kbId=\\d{4}'.",
    )
    product_version: ProductVersion | None = Field(
        default=None,
        description="Product version corpus to grep. "
        "When omitted, the version selected in the UI is used automatically. "
        "Specify explicitly to grep a specific version's docs "
        "(e.g., 'v5' for version 5.0 released 2025, 'v6' for version 6.0 released 2026).",
    )
    max_matches: int = Field(
        default=20,
        description="Maximum number of matched articles to return (1–50). "
        "Default: 20. Use smaller values (5–10) for focused searches.",
    )
    exclude_kb_ids: list[str] | None = Field(
        default=None,
        description="Optional list of kb_ids to exclude from results.",
    )


def _parse_frontmatter(file_path: str) -> dict[str, str]:
    """Extract kbId and title from YAML frontmatter of a markdown file."""
    try:
        import yaml

        with open(file_path, encoding="utf-8") as f:
            content = f.read()
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm = yaml.safe_load(parts[1])
                if isinstance(fm, dict):
                    return {"kbId": str(fm.get("kbId", "")), "title": str(fm.get("title", ""))}
    except Exception:  # noqa: BLE001
        pass
    return {}


def _grep_kb_articles_core(
    pattern: str,
    product_version: str = "v6",
    max_matches: int = 20,
    exclude_kb_ids: list[str] | None = None,
) -> str:
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid regex pattern: {exc}") from exc

    import shutil
    import sys

    rg_bin = shutil.which("rg")
    if rg_bin is None:
        venv_rg = Path(sys.executable).parent / "rg"
        if venv_rg.exists():
            rg_bin = str(venv_rg)
        else:
            raise FileNotFoundError(
                "ripgrep (rg) not found in PATH or venv. "
                "Install with: pip install ripgrep"
            )

    corpus_dir = get_corpus_dir(product_version)
    result = subprocess.run(  # noqa: S603
        [rg_bin, "--files-with-matches", "--no-messages", pattern, corpus_dir],
        capture_output=True,
        text=True,
    )

    matched_files = [p.strip() for p in result.stdout.splitlines() if p.strip()]
    if result.returncode not in (0, 1):
        return _format_articles_to_json([], query=f"grep:{pattern}", top_k=None)

    exclude_set = set(exclude_kb_ids or [])
    articles: list[Article] = []

    for file_path in matched_files:
        if len(articles) >= max_matches:
            break
        fm = _parse_frontmatter(file_path)
        kb_id = fm.get("kbId", "")
        if kb_id and kb_id in exclude_set:
            continue
        title = fm.get("title", "")
        try:
            content = _read_article(file_path)
        except FileNotFoundError:
            continue
        articles.append(
            Article(
                kb_id=kb_id,
                content=content,
                metadata={
                    "title": title,
                    "kbId": kb_id,
                    "source_file": file_path,
                    "match_source": "grep",
                },
            )
        )

    return _format_articles_to_json(articles, query=f"grep:{pattern}", top_k=None)


@tool(
    "grep_kb_articles",
    args_schema=GrepKbArticlesSchema,
    description=GrepKbArticlesSchema.__doc__,
)
async def grep_kb_articles(
    pattern: str,
    product_version: ProductVersion | None = None,
    max_matches: int = 20,
    exclude_kb_ids: list[str] | None = None,
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> str:
    import asyncio

    if exclude_kb_ids is None and runtime is not None:
        try:
            ctx = runtime.context
            fetched = getattr(ctx, "fetched_kb_ids", None) if ctx else None
            if fetched:
                exclude_kb_ids = list(fetched)
        except TypeError:
            pass

    version = get_effective_product_version(product_version)
    return await asyncio.to_thread(
        _grep_kb_articles_core,
        pattern,
        version,
        max_matches,
        exclude_kb_ids,
    )
