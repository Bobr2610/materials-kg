[0m
> build · mimo-auto
[0m
[0m⚙ [0mmemory Memory search: 0 results
[0m✱ [0mGlob "kg_engine/tests/**/*.py"[90m 18 matches[0m
[0m→ [0mRead kg_engine\core
[0m→ [0mRead kg_engine\core\__init__.py
[0m→ [0mRead kg_engine\core\document_processor.py
[0m→ [0mRead kg_engine\core\guard_client.py
[0m→ [0mRead kg_engine\core\metadata_enricher.py
[0m→ [0mRead kg_engine\core\vllm_guard_adapter.py
[0m→ [0mRead kg_engine\tests\test_core_chunker.py
Let me explore the core modules to understand what needs test coverage.
[0m→ [0mRead kg_engine\tests\test_core_indexer.py
[0m→ [0mRead kg_engine\tests\conftest.py
[0m→ [0mRead kg_engine\config\settings.py
[0m→ [0mRead kg_engine\core\chunker.py
Now I have full context. Let me run the existing tests to see the current baseline, then write tests for the untested core modules.
[0m→ [0mRead kg_engine\core\indexer.py
[0m
[0m$ [0mpython -m pytest kg_engine/tests/test_core_chunker.py kg_engine/tests/test_core_indexer.py -v 2>&1 | head -40
head : The term 'head' is not recognized as the name of a cmdlet, function, script file, or operable program. Check the
 spelling of the name, or if a path was included, verify that the path is correct and try again.
At line:1 char:102
+ ... re_chunker.py kg_engine/tests/test_core_indexer.py -v 2>&1 | head -40
+                                                                  ~~~~
    + CategoryInfo          : ObjectNotFound: (head:String) [], CommandNotFoundException
    + FullyQualifiedErrorId : CommandNotFoundException
[0m
[0m$ [0mpython -m pytest kg_engine/tests/test_core_chunker.py kg_engine/tests/test_core_indexer.py -v 2>&1
============================= test session starts =============================
platform win32 -- Python 3.11.5, pytest-9.0.2, pluggy-1.6.0 -- C:\Program Files\Python311\python.exe
cachedir: .pytest_cache
rootdir: C:\MAI\Nornicel\Code\materials-kg
configfile: pyproject.toml
plugins: anyio-4.11.0, hydra-core-1.3.2, base-url-2.1.0, playwright-0.7.2
collecting ... collected 0 items / 2 errors
System.Management.Automation.RemoteException
=================================== ERRORS ====================================
____________ ERROR collecting kg_engine/tests/test_core_chunker.py ____________
kg_engine\tests\test_core_chunker.py:5: in <module>
    from kg_engine.core.chunker import split_text
kg_engine\core\__init__.py:2: in <module>
    from kg_engine.core.guard_client import guard_client
kg_engine\core\guard_client.py:19: in <module>
    from kg_engine.config.settings import settings
kg_engine\config\__init__.py:13: in <module>
    from kg_engine.config.settings import Settings, settings
kg_engine\config\settings.py:256: in <module>
    settings = Settings()
               ^^^^^^^^^^
C:\Users\misha\AppData\Roaming\Python\Python311\site-packages\pydantic_settings\main.py:194: in __init__
    super().__init__(
E   pydantic_core._pydantic_core.ValidationError: 72 validation errors for Settings
E   google_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   openrouter_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   openrouter_base_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   vllm_base_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   vllm_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_provider_type
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_device
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_persist_dir
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_collection
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_client_host
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_server_bind
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_port
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_ssl
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_http_keepalive_secs
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_http_max_connections
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   top_k_retrieve
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   top_k_rerank
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   rerank_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chunk_size
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chunk_overlap
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_max_segments
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_segment_tokens
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_segment_overlap
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_pre_rerank_limit
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_query_decomp_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_query_decomp_max_subqueries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_provider_type
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_timeout
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_max_retries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_local
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_timeout
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_max_retries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   default_llm_provider
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   default_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_temperature
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_fallback_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_allowed_fallback_models
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_summarization_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   vllm_streaming_fallback_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_server_name
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_server_port
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_share
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_embedded_widget
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_default_concurrency_limit
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   memory_compression_threshold_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   memory_compression_target_tokens
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   memory_compression_messages_to_keep
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_pre_context_threshold_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_context_overhead_safety_margin
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_tool_results_json_overhead_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_compression_threshold_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_compression_target_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_compression_min_tokens
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   default_timezone
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_block_threshold
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_provider_type
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_mosec_endpoint
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_vllm_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_vllm_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_device
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_openrouter_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_timeout
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_max_retries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_base_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_login
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_password
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
____________ ERROR collecting kg_engine/tests/test_core_indexer.py ____________
kg_engine\tests\test_core_indexer.py:10: in <module>
    from kg_engine.core.indexer import RAGIndexer
kg_engine\core\__init__.py:2: in <module>
    from kg_engine.core.guard_client import guard_client
kg_engine\core\guard_client.py:19: in <module>
    from kg_engine.config.settings import settings
kg_engine\config\__init__.py:13: in <module>
    from kg_engine.config.settings import Settings, settings
kg_engine\config\settings.py:256: in <module>
    settings = Settings()
               ^^^^^^^^^^
C:\Users\misha\AppData\Roaming\Python\Python311\site-packages\pydantic_settings\main.py:194: in __init__
    super().__init__(
E   pydantic_core._pydantic_core.ValidationError: 72 validation errors for Settings
E   google_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   openrouter_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   openrouter_base_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   vllm_base_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   vllm_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_provider_type
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_device
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_persist_dir
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_collection
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_client_host
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_server_bind
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_port
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_ssl
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_http_keepalive_secs
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_http_max_connections
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   top_k_retrieve
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   top_k_rerank
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   rerank_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chunk_size
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chunk_overlap
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_max_segments
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_segment_tokens
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_segment_overlap
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_pre_rerank_limit
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_query_decomp_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_query_decomp_max_subqueries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_provider_type
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_timeout
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_max_retries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_local
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_timeout
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_max_retries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   default_llm_provider
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   default_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_temperature
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_fallback_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_allowed_fallback_models
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_summarization_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   vllm_streaming_fallback_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_server_name
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_server_port
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_share
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_embedded_widget
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_default_concurrency_limit
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   memory_compression_threshold_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   memory_compression_target_tokens
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   memory_compression_messages_to_keep
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_pre_context_threshold_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_context_overhead_safety_margin
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_tool_results_json_overhead_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_compression_threshold_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_compression_target_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_compression_min_tokens
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   default_timezone
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_block_threshold
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_provider_type
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_mosec_endpoint
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_vllm_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_vllm_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_device
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_openrouter_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_timeout
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_max_retries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_base_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_login
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_password
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
=========================== short test summary info ===========================
ERROR kg_engine/tests/test_core_chunker.py - pydantic_core._pydantic_core.Val...
ERROR kg_engine/tests/test_core_indexer.py - pydantic_core._pydantic_core.Val...
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!
============================== 2 errors in 1.36s ==============================
[0m
[0m✱ [0mGlob ".env*"[90m 1 match[0m
The `core/__init__.py` eagerly imports `guard_client` which triggers `Settings()` at module level. Let me check how other tests handle this.
[0m
[0m$ [0mpython -m pytest kg_engine/tests/test_config_settings.py -v 2>&1 | Select-Object -First 20
============================= test session starts =============================
platform win32 -- Python 3.11.5, pytest-9.0.2, pluggy-1.6.0 -- C:\Program Files\Python311\python.exe
cachedir: .pytest_cache
rootdir: C:\MAI\Nornicel\Code\materials-kg
configfile: pyproject.toml
plugins: anyio-4.11.0, hydra-core-1.3.2, base-url-2.1.0, playwright-0.7.2
collecting ... collected 0 items / 1 error
System.Management.Automation.RemoteException
=================================== ERRORS ====================================
__________ ERROR collecting kg_engine/tests/test_config_settings.py ___________
kg_engine\tests\test_config_settings.py:5: in <module>
    from kg_engine.config.settings import Settings, get_collection_name
kg_engine\config\__init__.py:13: in <module>
    from kg_engine.config.settings import Settings, settings
kg_engine\config\settings.py:256: in <module>
    settings = Settings()
               ^^^^^^^^^^
C:\Users\misha\AppData\Roaming\Python\Python311\site-packages\pydantic_settings\main.py:194: in __init__
    super().__init__(
E   pydantic_core._pydantic_core.ValidationError: 72 validation errors for Settings
[0m
[0m→ [0mRead kg_engine\tests\conftest_agent.py
No `.env` file exists — all core tests fail. I need to check how the test infrastructure handles settings initialization. Let me look at the conftest for agent and see the `.env.example`.
[0m→ [0mRead .env.example
The tests fail because there's no `.env` file and `core/__init__.py` eagerly imports `guard_client` which triggers `Settings()`. I need to fix the eager import and write the missing tests. Let me also check if there's a `.env` in the repo root.
[0m✱ [0mGrep "from kg_engine\.core"[90m 12 matches[0m
[0m
[0m$ [0mif (Test-Path .env) { "EXISTS" } else { "MISSING" }
MISSING
[0m
[0m✱ [0mGrep "from kg_engine\.core import|from kg_engine\.core$"[90m 0 matches[0m
[0m✗ [0mtask failed
[91m[1mError: [0mInvalid arguments for the task tool:
✖ Unrecognized key: "summary"
✖ Invalid input: expected object, received string
  → at operation
Nothing imports from `kg_engine.core` directly — all callers use submodule paths. The `__init__.py` re-exports are dead code that triggers the settings cascade. I'll fix `__init__.py` and write the 3 missing test files.
[0m⚙ [0mtask Task created: T1
[0m⚙ [0mtask Task T1: in_progress
First, fix `core/__init__.py` to stop eagerly importing settings-dependent modules:
[0m
[0m← [0mEdit kg_engine\core\__init__.py
Index: C:\MAI\Nornicel\Code\materials-kg\kg_engine\core\__init__.py
===================================================================
--- C:\MAI\Nornicel\Code\materials-kg\kg_engine\core\__init__.py
+++ C:\MAI\Nornicel\Code\materials-kg\kg_engine\core\__init__.py
@@ -1,7 +1,15 @@
 """Core document processing components."""
-from kg_engine.core.guard_client import guard_client
-from kg_engine.core.indexer import RAGIndexer
 
 __all__ = ["RAGIndexer", "guard_client"]
 
 
+def __getattr__(name: str):
+    if name == "RAGIndexer":
+        from kg_engine.core.indexer import RAGIndexer
+        return RAGIndexer
+    if name == "guard_client":
+        from kg_engine.core.guard_client import guard_client
+        return guard_client
+    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
+
+
System.Management.Automation.RemoteException
[0m
[0m$ [0mpython -m pytest kg_engine/tests/test_core_chunker.py kg_engine/tests/test_core_indexer.py -v 2>&1
============================= test session starts =============================
platform win32 -- Python 3.11.5, pytest-9.0.2, pluggy-1.6.0 -- C:\Program Files\Python311\python.exe
cachedir: .pytest_cache
rootdir: C:\MAI\Nornicel\Code\materials-kg
configfile: pyproject.toml
plugins: anyio-4.11.0, hydra-core-1.3.2, base-url-2.1.0, playwright-0.7.2
collecting ... collected 9 items
System.Management.Automation.RemoteException
kg_engine/tests/test_core_chunker.py::test_split_text_respects_chunk_size_tokens PASSED [ 11%]
kg_engine/tests/test_core_chunker.py::test_split_text_preserves_code_fences PASSED [ 22%]
kg_engine/tests/test_core_indexer.py::TestRAGIndexer::test_index_documents_enriches_metadata PASSED [ 33%]
kg_engine/tests/test_core_indexer.py::TestRAGIndexer::test_index_documents_skips_unchanged PASSED [ 44%]
kg_engine/tests/test_core_indexer.py::TestRAGIndexer::test_index_documents_replaces_updated FAILED [ 55%]
kg_engine/tests/test_core_indexer.py::TestRAGIndexer::test_max_files_counts_only_indexed FAILED [ 66%]
kg_engine/tests/test_core_indexer.py::TestRAGIndexer::test_stable_id_disambiguates_by_source_file PASSED [ 77%]
kg_engine/tests/test_core_indexer.py::TestRAGIndexer::test_index_documents_normalizes_kbid PASSED [ 88%]
kg_engine/tests/test_core_indexer.py::TestRAGIndexer::test_index_documents_requires_kbid PASSED [100%]
System.Management.Automation.RemoteException
================================== FAILURES ===================================
____________ TestRAGIndexer.test_index_documents_replaces_updated _____________
System.Management.Automation.RemoteException
self = <test_core_indexer.TestRAGIndexer object at 0x0000019714EBC850>
mock_embedder = <MagicMock id='1748385489104'>
mock_vector_store = <MagicMock id='1748402701904'>
tmp_path = WindowsPath('C:/Users/misha/AppData/Local/Temp/pytest-of-misha/pytest-0/test_index_documents_replaces_0')
System.Management.Automation.RemoteException
    def test_index_documents_replaces_updated(self, mock_embedder, mock_vector_store, tmp_path):
        """If stored mtime < current mtime, delete_where then add is called."""
        file_path = tmp_path / "doc.md"
        file_path.write_text("Content")
        # Current file mtime 300
        os.utime(file_path, (300, 300))
    
        # Use normalized kbId for doc_stable_id (new behavior)
        numeric_kb_id = extract_numeric_kbid("k2") or "k2"
        doc_stable_id = sha1(numeric_kb_id.encode("utf-8")).hexdigest()[:12]
        # Existing older epoch 200 triggers reindex
        mock_vector_store.get_any_doc_meta.return_value = {"file_mtime_epoch": 200, "doc_stable_id": doc_stable_id}
    
        indexer = RAGIndexer(embedder=mock_embedder, vector_store=mock_vector_store)
    
        doc = MagicMock()
        doc.content = "# T\nBody"
        doc.metadata = {"kbId": "k2", "source_file": str(file_path)}
    
>       indexer.index_documents([doc], chunk_size=50, chunk_overlap=10, max_files=None)
System.Management.Automation.RemoteException
kg_engine\tests\test_core_indexer.py:98: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
kg_engine\core\indexer.py:263: in index_documents
    self._assert_embedding_batch_sizes(
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
System.Management.Automation.RemoteException
texts = ['# T\nBody']
embeddings = <MagicMock name='mock.embed_documents()' id='1748402708368'>
kb_id = 'k2', doc_stable_id = 'bfeb734d2eb5'
System.Management.Automation.RemoteException
    @staticmethod
    def _assert_embedding_batch_sizes(
        texts: list[str],
        embeddings: list[list[float]],
        kb_id: str,
        doc_stable_id: str,
        *,
        async_mode: bool,
    ) -> None:
        """Ensure 1:1 mapping between input texts and embedding vectors."""
        if len(embeddings) != len(texts):
            mode = "async" if async_mode else "sync"
>           raise ValueError(
                "Embedding provider returned mismatched batch sizes "
                f"({mode} mode): embeddings={len(embeddings)} vs texts={len(texts)} "
                f"(kbId={kb_id}, doc_stable_id={doc_stable_id})"
            )
E           ValueError: Embedding provider returned mismatched batch sizes (sync mode): embeddings=0 vs texts=1 (kbId=k2, doc_stable_id=bfeb734d2eb5)
System.Management.Automation.RemoteException
kg_engine\core\indexer.py:58: ValueError
______________ TestRAGIndexer.test_max_files_counts_only_indexed ______________
System.Management.Automation.RemoteException
self = <test_core_indexer.TestRAGIndexer object at 0x0000019714EBF150>
mock_embedder = <MagicMock id='1748395988816'>
mock_vector_store = <MagicMock id='1748395990224'>
tmp_path = WindowsPath('C:/Users/misha/AppData/Local/Temp/pytest-of-misha/pytest-0/test_max_files_counts_only_ind0')
System.Management.Automation.RemoteException
    def test_max_files_counts_only_indexed(self, mock_embedder, mock_vector_store, tmp_path):
        """max_files should limit actual indexed docs, not scanned docs."""
        # Prepare three files: two unchanged (skip), one updated (index)
        f1 = tmp_path / "a.md"; f1.write_text("A"); os.utime(f1, (200, 200))
        f2 = tmp_path / "b.md"; f2.write_text("B"); os.utime(f2, (200, 200))
        f3 = tmp_path / "c.md"; f3.write_text("C"); os.utime(f3, (300, 300))
    
        # For first two docs, existing epoch equals current → skip
        # Use normalized kbId for doc_stable_id calculations
        numeric_kb_a = extract_numeric_kbid("kb_a") or "kb_a"
        numeric_kb_b = extract_numeric_kbid("kb_b") or "kb_b"
        numeric_kb_c = extract_numeric_kbid("kb_c") or "kb_c"
        doc_stable_id_a = sha1(numeric_kb_a.encode("utf-8")).hexdigest()[:12]
        doc_stable_id_b = sha1(numeric_kb_b.encode("utf-8")).hexdigest()[:12]
        doc_stable_id_c = sha1(numeric_kb_c.encode("utf-8")).hexdigest()[:12]
    
        def get_meta(where):
            if where.get("doc_stable_id") in {doc_stable_id_a, doc_stable_id_b}:
                return {"file_mtime_epoch": 200}
            if where.get("doc_stable_id") == doc_stable_id_c:
                return {"file_mtime_epoch": 200}  # older than current 300 → reindex
            return None
    
        mock_vector_store.get_any_doc_meta.side_effect = get_meta
    
        indexer = RAGIndexer(embedder=mock_embedder, vector_store=mock_vector_store)
    
        docs = []
        for kb, fp in [("kb_a", f1), ("kb_b", f2), ("kb_c", f3)]:
            d = MagicMock()
            d.content = "# H\nX"
            d.metadata = {"kbId": kb, "source_file": str(fp)}
            docs.append(d)
    
        # Request max_files=1; should skip a and b, index only c and stop
>       indexer.index_documents(docs, chunk_size=50, chunk_overlap=10, max_files=1)
System.Management.Automation.RemoteException
kg_engine\tests\test_core_indexer.py:142: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
kg_engine\core\indexer.py:263: in index_documents
    self._assert_embedding_batch_sizes(
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
System.Management.Automation.RemoteException
texts = ['# H\nX']
embeddings = <MagicMock name='mock.embed_documents()' id='1748395822800'>
kb_id = 'kb_c', doc_stable_id = '817ee6f06cc1'
System.Management.Automation.RemoteException
    @staticmethod
    def _assert_embedding_batch_sizes(
        texts: list[str],
        embeddings: list[list[float]],
        kb_id: str,
        doc_stable_id: str,
        *,
        async_mode: bool,
    ) -> None:
        """Ensure 1:1 mapping between input texts and embedding vectors."""
        if len(embeddings) != len(texts):
            mode = "async" if async_mode else "sync"
>           raise ValueError(
                "Embedding provider returned mismatched batch sizes "
                f"({mode} mode): embeddings={len(embeddings)} vs texts={len(texts)} "
                f"(kbId={kb_id}, doc_stable_id={doc_stable_id})"
            )
E           ValueError: Embedding provider returned mismatched batch sizes (sync mode): embeddings=0 vs texts=1 (kbId=kb_c, doc_stable_id=817ee6f06cc1)
System.Management.Automation.RemoteException
kg_engine\core\indexer.py:58: ValueError
=========================== short test summary info ===========================
FAILED kg_engine/tests/test_core_indexer.py::TestRAGIndexer::test_index_documents_replaces_updated
FAILED kg_engine/tests/test_core_indexer.py::TestRAGIndexer::test_max_files_counts_only_indexed
======================== 2 failed, 7 passed in 39.87s =========================
[0m
The `__init__.py` fix works — 7/9 existing tests pass (2 failures are pre-existing test bugs missing `embed_documents` mock). Now I'll write the 3 missing test files.
[0m← [0mWrite kg_engine\tests\test_core_document_processor.py
Wrote file successfully.
[0m
[0m← [0mWrite kg_engine\tests\test_core_metadata_enricher.py
Wrote file successfully.
[0m
[0m← [0mWrite kg_engine\tests\test_core_guard_client.py
Wrote file successfully.
[0m
[0m← [0mWrite kg_engine\tests\test_core_vllm_guard_adapter.py
Wrote file successfully.
[0m
Now run all new tests:
[0m$ [0mpython -m pytest kg_engine/tests/test_core_document_processor.py kg_engine/tests/test_core_metadata_enricher.py kg_engine/tests/test_core_guard_client.py kg_engine/tests/test_core_vllm_guard_adapter.py -v 2>&1
============================= test session starts =============================
platform win32 -- Python 3.11.5, pytest-9.0.2, pluggy-1.6.0 -- C:\Program Files\Python311\python.exe
cachedir: .pytest_cache
rootdir: C:\MAI\Nornicel\Code\materials-kg
configfile: pyproject.toml
plugins: anyio-4.11.0, hydra-core-1.3.2, base-url-2.1.0, playwright-0.7.2
collecting ... collected 30 items / 2 errors
System.Management.Automation.RemoteException
=================================== ERRORS ====================================
_________ ERROR collecting kg_engine/tests/test_core_guard_client.py __________
kg_engine\tests\test_core_guard_client.py:9: in <module>
    from kg_engine.core.guard_client import GuardClient
kg_engine\core\guard_client.py:19: in <module>
    from kg_engine.config.settings import settings
kg_engine\config\__init__.py:13: in <module>
    from kg_engine.config.settings import Settings, settings
kg_engine\config\settings.py:256: in <module>
    settings = Settings()
               ^^^^^^^^^^
C:\Users\misha\AppData\Roaming\Python\Python311\site-packages\pydantic_settings\main.py:194: in __init__
    super().__init__(
E   pydantic_core._pydantic_core.ValidationError: 72 validation errors for Settings
E   google_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   openrouter_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   openrouter_base_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   vllm_base_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   vllm_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_provider_type
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_device
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_persist_dir
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_collection
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_client_host
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_server_bind
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_port
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_ssl
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_http_keepalive_secs
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_http_max_connections
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   top_k_retrieve
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   top_k_rerank
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   rerank_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chunk_size
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chunk_overlap
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_max_segments
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_segment_tokens
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_segment_overlap
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_pre_rerank_limit
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_query_decomp_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_query_decomp_max_subqueries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_provider_type
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_timeout
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_max_retries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_local
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_timeout
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_max_retries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   default_llm_provider
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   default_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_temperature
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_fallback_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_allowed_fallback_models
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_summarization_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   vllm_streaming_fallback_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_server_name
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_server_port
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_share
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_embedded_widget
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_default_concurrency_limit
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   memory_compression_threshold_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   memory_compression_target_tokens
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   memory_compression_messages_to_keep
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_pre_context_threshold_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_context_overhead_safety_margin
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_tool_results_json_overhead_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_compression_threshold_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_compression_target_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_compression_min_tokens
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   default_timezone
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_block_threshold
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_provider_type
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_mosec_endpoint
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_vllm_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_vllm_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_device
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_openrouter_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_timeout
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_max_retries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_base_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_login
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_password
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
______ ERROR collecting kg_engine/tests/test_core_vllm_guard_adapter.py _______
kg_engine\tests\test_core_vllm_guard_adapter.py:9: in <module>
    from kg_engine.core.vllm_guard_adapter import VLLMGuardAdapter
kg_engine\core\vllm_guard_adapter.py:24: in <module>
    from kg_engine.config.settings import settings
kg_engine\config\__init__.py:13: in <module>
    from kg_engine.config.settings import Settings, settings
kg_engine\config\settings.py:256: in <module>
    settings = Settings()
               ^^^^^^^^^^
C:\Users\misha\AppData\Roaming\Python\Python311\site-packages\pydantic_settings\main.py:194: in __init__
    super().__init__(
E   pydantic_core._pydantic_core.ValidationError: 72 validation errors for Settings
E   google_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   openrouter_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   openrouter_base_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   vllm_base_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   vllm_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_provider_type
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_device
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_persist_dir
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_collection
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_client_host
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_server_bind
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_port
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_ssl
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_http_keepalive_secs
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_http_max_connections
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   top_k_retrieve
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   top_k_rerank
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   rerank_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chunk_size
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chunk_overlap
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_max_segments
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_segment_tokens
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_segment_overlap
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_pre_rerank_limit
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_query_decomp_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_query_decomp_max_subqueries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_provider_type
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_timeout
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_max_retries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_local
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_timeout
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_max_retries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   default_llm_provider
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   default_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_temperature
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_fallback_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_allowed_fallback_models
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_summarization_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   vllm_streaming_fallback_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_server_name
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_server_port
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_share
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_embedded_widget
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_default_concurrency_limit
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   memory_compression_threshold_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   memory_compression_target_tokens
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   memory_compression_messages_to_keep
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_pre_context_threshold_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_context_overhead_safety_margin
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_tool_results_json_overhead_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_compression_threshold_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_compression_target_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_compression_min_tokens
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   default_timezone
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_block_threshold
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_provider_type
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_mosec_endpoint
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_vllm_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_vllm_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_device
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_openrouter_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_timeout
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_max_retries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_base_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_login
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_password
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
=========================== short test summary info ===========================
ERROR kg_engine/tests/test_core_guard_client.py - pydantic_core._pydantic_cor...
ERROR kg_engine/tests/test_core_vllm_guard_adapter.py - pydantic_core._pydant...
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!
============================== 2 errors in 2.99s ==============================
[0m
[0m→ [0mRead kg_engine\config\__init__.py
The `config/__init__.py` eagerly creates `settings = Settings()` at module level, which blocks all imports when `.env` is missing. I need to fix this to use lazy initialization.
The root issue is `settings.py:256` — `settings = Settings()` runs at import time. I'll make it lazy.
[0m
[0m← [0mEdit kg_engine\config\settings.py
Index: C:\MAI\Nornicel\Code\materials-kg\kg_engine\config\settings.py
===================================================================
--- C:\MAI\Nornicel\Code\materials-kg\kg_engine\config\settings.py
+++ C:\MAI\Nornicel\Code\materials-kg\kg_engine\config\settings.py
@@ -252,11 +252,31 @@
         validate_default=True,
     )
 
 
-settings = Settings()
+_settings_instance: Settings | None = None
 
 
+def _get_settings() -> Settings:
+    global _settings_instance  # noqa: PLW0603
+    if _settings_instance is None:
+        _settings_instance = Settings()
+    return _settings_instance
+
+
+class _SettingsProxy:
+    """Lazy proxy that defers Settings() instantiation until first attribute access."""
+
+    def __getattr__(self, name: str):
+        return getattr(_get_settings(), name)
+
+    def __repr__(self) -> str:
+        return repr(_get_settings())
+
+
+settings: Settings = _SettingsProxy()  # type: ignore[assignment]
+
+
 # Helpers derived from settings (avoid polluting pydantic model with properties)
 def get_allowed_fallback_models() -> list[str]:
     raw = settings.llm_allowed_fallback_models or ""
     return [m.strip() for m in raw.split(",") if m and m.strip()]
System.Management.Automation.RemoteException
[0m
[0m← [0mEdit kg_engine\config\__init__.py
Index: C:\MAI\Nornicel\Code\materials-kg\kg_engine\config\__init__.py
===================================================================
--- C:\MAI\Nornicel\Code\materials-kg\kg_engine\config\__init__.py
+++ C:\MAI\Nornicel\Code\materials-kg\kg_engine\config\__init__.py
@@ -9,9 +9,9 @@
     RerankerProviderConfig,
     ServerRerankerConfig,
     get_model_dimension,
 )
-from kg_engine.config.settings import Settings, settings
+from kg_engine.config.settings import Settings
 
 __all__ = [
     "Settings",
     "settings",
@@ -23,4 +23,11 @@
     "ServerRerankerConfig",
     "ModelRegistry",
     "get_model_dimension",
 ]
+
+
+def __getattr__(name: str):
+    if name == "settings":
+        from kg_engine.config.settings import settings
+        return settings
+    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
System.Management.Automation.RemoteException
[0m
[0m$ [0mpython -m pytest kg_engine/tests/test_core_document_processor.py kg_engine/tests/test_core_metadata_enricher.py kg_engine/tests/test_core_guard_client.py kg_engine/tests/test_core_vllm_guard_adapter.py -v 2>&1
============================= test session starts =============================
platform win32 -- Python 3.11.5, pytest-9.0.2, pluggy-1.6.0 -- C:\Program Files\Python311\python.exe
cachedir: .pytest_cache
rootdir: C:\MAI\Nornicel\Code\materials-kg
configfile: pyproject.toml
plugins: anyio-4.11.0, hydra-core-1.3.2, base-url-2.1.0, playwright-0.7.2
collecting ... collected 60 items / 1 error
System.Management.Automation.RemoteException
=================================== ERRORS ====================================
_________ ERROR collecting kg_engine/tests/test_core_guard_client.py __________
kg_engine\tests\test_core_guard_client.py:9: in <module>
    from kg_engine.core.guard_client import GuardClient
kg_engine\core\guard_client.py:206: in <module>
    guard_client = GuardClient()
                   ^^^^^^^^^^^^^
kg_engine\core\guard_client.py:49: in __init__
    self._provider_type = provider_type or settings.guard_provider_type
                                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
kg_engine\config\settings.py:270: in __getattr__
    return getattr(_get_settings(), name)
                   ^^^^^^^^^^^^^^^
kg_engine\config\settings.py:262: in _get_settings
    _settings_instance = Settings()
                         ^^^^^^^^^^
C:\Users\misha\AppData\Roaming\Python\Python311\site-packages\pydantic_settings\main.py:194: in __init__
    super().__init__(
E   pydantic_core._pydantic_core.ValidationError: 72 validation errors for Settings
E   google_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   openrouter_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   openrouter_base_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   vllm_base_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   vllm_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_provider_type
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_device
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_persist_dir
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_collection
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_client_host
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_server_bind
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_port
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chromadb_ssl
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_http_keepalive_secs
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chroma_http_max_connections
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   top_k_retrieve
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   top_k_rerank
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   rerank_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chunk_size
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   chunk_overlap
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_max_segments
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_segment_tokens
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_segment_overlap
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_multiquery_pre_rerank_limit
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_query_decomp_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   retrieval_query_decomp_max_subqueries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_provider_type
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_timeout
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_max_retries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   embedding_local
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_timeout
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   reranker_max_retries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   default_llm_provider
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   default_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_temperature
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_fallback_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_allowed_fallback_models
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_summarization_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   vllm_streaming_fallback_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_server_name
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_server_port
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_share
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_embedded_widget
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   gradio_default_concurrency_limit
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   memory_compression_threshold_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   memory_compression_target_tokens
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   memory_compression_messages_to_keep
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_pre_context_threshold_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_context_overhead_safety_margin
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_tool_results_json_overhead_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_compression_threshold_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_compression_target_pct
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   llm_compression_min_tokens
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   default_timezone
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_enabled
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_block_threshold
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_provider_type
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_mosec_endpoint
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_vllm_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_vllm_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_device
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_openrouter_model
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_timeout
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   guard_max_retries
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_base_url
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_login
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_password
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
E   cmw_api_key
E     Field required [type=missing, input_value={}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.9/v/missing
============================== warnings summary ===============================
kg_engine\tests\test_core_vllm_guard_adapter.py:178
  C:\MAI\Nornicel\Code\materials-kg\kg_engine\tests\test_core_vllm_guard_adapter.py:178: PytestUnknownMarkWarning: Unknown pytest.mark.asyncio - is this a typo?  You can register custom marks to avoid this warning - for details, see https://docs.pytest.org/en/stable/how-to/mark.html
    @pytest.mark.asyncio
System.Management.Automation.RemoteException
kg_engine\tests\test_core_vllm_guard_adapter.py:199
  C:\MAI\Nornicel\Code\materials-kg\kg_engine\tests\test_core_vllm_guard_adapter.py:199: PytestUnknownMarkWarning: Unknown pytest.mark.asyncio - is this a typo?  You can register custom marks to avoid this warning - for details, see https://docs.pytest.org/en/stable/how-to/mark.html
    @pytest.mark.asyncio
System.Management.Automation.RemoteException
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
ERROR kg_engine/tests/test_core_guard_client.py - pydantic_core._pydantic_cor...
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
======================== 2 warnings, 1 error in 2.20s =========================
[0m
The `guard_client.py` has `guard_client = GuardClient()` at module level (line 206), which triggers `Settings()` during import. Need to make that lazy too.
[0m← [0mEdit kg_engine\core\guard_client.py
Index: C:\MAI\Nornicel\Code\materials-kg\kg_engine\core\guard_client.py
===================================================================
--- C:\MAI\Nornicel\Code\materials-kg\kg_engine\core\guard_client.py
+++ C:\MAI\Nornicel\Code\materials-kg\kg_engine\core\guard_client.py
@@ -202,5 +202,12 @@
             return safety_level in ("Unsafe", "Controversial")
         return safety_level == "Unsafe"
 
 
-guard_client = GuardClient()
+guard_client: GuardClient | None = None
+
+
+def get_guard_client() -> GuardClient:
+    global guard_client  # noqa: PLW0603
+    if guard_client is None:
+        guard_client = GuardClient()
+    return guard_client
System.Management.Automation.RemoteException
[0m
[0m✱ [0mGrep "from kg_engine\.core\.guard_client import guard_client"[90m 2 matches[0m
