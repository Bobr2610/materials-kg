"""LLM manager with dynamic token limits (reuses cmw-platform-agent mechanics)."""
from __future__ import annotations

import logging
from collections.abc import Generator, Iterable
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from kg_engine.config.settings import settings
from kg_engine.llm.model_configs import MODEL_CONFIGS
from kg_engine.llm.openrouter_native import create_openrouter_native_model
from kg_engine.llm.prompts import get_system_prompt
from kg_engine.llm.token_utils import estimate_tokens_for_request
from kg_engine.llm.usage_accounting import UsageAccountingCallback
from kg_engine.utils.conversation_store import ConversationStore
from kg_engine.utils.metadata_utils import extract_numeric_kbid

logger = logging.getLogger(__name__)


def get_model_config(model_name: str) -> dict:
    """Get model configuration with partial-match fallback and .env overrides.

    Tries exact match first, then partial match (e.g., "gemini-2.5-flash-latest"
    matches "gemini-2.5-flash"), then falls back to "default" config.

    Applies .env overrides if set:
    - LLM_TOKEN_LIMIT overrides token_limit
    - LLM_MAX_TOKENS overrides max_tokens (used only for estimation, not passed to model)

    Args:
        model_name: Model identifier to look up

    Returns:
        Model configuration dict with token_limit, max_tokens, temperature
        (with .env overrides applied if set)

    Example:
        >>> from kg_engine.llm.llm_manager import get_model_config
        >>> config = get_model_config("gemini-2.5-flash")
        >>> config["token_limit"] > 0
        True
    """
    # Try exact match first
    base_config = None
    if model_name in MODEL_CONFIGS:
        base_config = MODEL_CONFIGS[model_name]
    else:
        # Try partial match (e.g., "gemini-2.5-flash-latest" → "gemini-2.5-flash")
        for key in MODEL_CONFIGS:
            if key != "default" and key in model_name:
                logger.debug("Using config for %s (matched from %s)", key, model_name)
                base_config = MODEL_CONFIGS[key]
                break

        # Fallback to default
        if base_config is None:
            logger.warning("No config for %s, using default", model_name)
            base_config = MODEL_CONFIGS["default"]

    # Create a copy to avoid mutating the original
    config = base_config.copy()

    # Apply .env overrides only for the configured default local/vLLM model.
    # This prevents unintentionally overriding known external model configs
    # (e.g., Gemini/OpenRouter) in unit tests and production.
    is_default_vllm_model = (
        getattr(settings, "default_llm_provider", "").lower() == "vllm"
        and getattr(settings, "default_model", "") == model_name
    )
    if is_default_vllm_model and settings.llm_token_limit is not None:
        logger.debug("Overriding token_limit with .env value: %d", settings.llm_token_limit)
        config["token_limit"] = settings.llm_token_limit

    if is_default_vllm_model and settings.llm_max_tokens is not None:
        logger.debug("Overriding max_tokens with .env value: %d", settings.llm_max_tokens)
        config["max_tokens"] = settings.llm_max_tokens

    return config


def _build_reasoning_extra_body() -> dict[str, Any] | None:
    """Build OpenRouter-style reasoning configuration from env settings.

    Returns a dict suitable for ChatOpenAI(extra_body=...) or None.
    """
    enabled = getattr(settings, "llm_reasoning_enabled", False)

    # When disabled, explicitly request no reasoning to avoid surprise thinking traces.
    if not enabled:
        return {
            "reasoning": {
                "effort": "none",
                "exclude": True,
            }
        }

    cfg: dict[str, Any] = {"enabled": True}

    # OpenRouter requires that only ONE of reasoning.effort or reasoning.max_tokens
    # is specified in a single request. Prefer an explicit max_tokens budget when
    # both are set, otherwise fall back to effort.
    max_tokens = getattr(settings, "llm_reasoning_max_tokens", None)
    effort = getattr(settings, "llm_reasoning_effort", None)

    if max_tokens:
        cfg["max_tokens"] = max_tokens
    elif effort:
        cfg["effort"] = effort

    exclude = getattr(settings, "llm_reasoning_exclude_from_response", False)
    if exclude:
        cfg["exclude"] = True

    return {"reasoning": cfg}


def get_context_window(model_name: str, default: int = 262144) -> int:
    """Get context window size for a model.

    Args:
        model_name: Model identifier to look up
        default: Default context window if model not found (default: 262144)

    Returns:
        Context window size in tokens

    Example:
        >>> from kg_engine.llm.llm_manager import get_context_window
        >>> window = get_context_window("gemini-2.5-flash")
        >>> window > 0
        True
    """
    config = get_model_config(model_name)
    return config.get("token_limit", default)


class LLMManager:
    """LLM manager with dynamic token limits and multi-provider support."""

    def __init__(self, provider: str, model: str, temperature: float = 0.1):
        self.provider = provider
        self.model_name = model
        self.temperature = temperature
        self._model_config = get_model_config(model)
        self._conversations = ConversationStore()
        logger.info(
            f"LLMManager initialized: {provider}/{model} "
            f"(context: {self._model_config['token_limit']} tokens)"
        )

    def get_current_llm_context_window(self) -> int:
        """Get the context window size for the current LLM model.

        Returns:
            int: Maximum context tokens for the current model
        """
        return self._model_config["token_limit"]

    def get_max_output_tokens(self) -> int:
        """Get the maximum output tokens for the current model.

        Returns:
            int: Maximum output tokens
        """
        return self._model_config["max_tokens"]

    def _apply_structured_output(
        self, model: Any, schema: type[BaseModel] | dict[str, Any]
    ) -> Any:
        """Apply structured output schema to a LangChain chat model if supported."""
        with_structured_output = getattr(model, "with_structured_output", None)
        if with_structured_output is None:
            logger.warning(
                "Model %s does not support with_structured_output(); ignoring schema.",
                type(model).__name__,
            )
            return model

        try:
            # Prefer strict json_schema first: it enforces the schema (not just “some JSON”).
            return with_structured_output(schema, method="json_schema", strict=True)
        except Exception as exc_json_schema:
            try:
                # Fallback for providers/models that don't support json_schema well.
                return with_structured_output(schema, method="json_mode")
            except Exception as exc_json_mode:
                logger.warning(
                    "Failed to apply structured output (json_schema=%s, json_mode=%s). Using regular model.",
                    exc_json_schema,
                    exc_json_mode,
                )
                return model

    def _chat_model(
        self,
        provider: str | None = None,
        structured_output_schema: type[BaseModel] | dict[str, Any] | None = None,
    ):
        """Create chat model instance.

        Args:
            provider: Optional provider override (openrouter, gemini, vllm)
            structured_output_schema: Optional Pydantic model or JSON schema dict to enforce
                structured output. Only supported for ChatOpenAI models (OpenRouter/vLLM).

        Note: max_tokens is not passed to the model as providers have their own limits.
        It's only used for context size estimation.
        """
        p = (provider or self.provider).lower()
        reasoning_body = _build_reasoning_extra_body()
        if p == "gemini":
            model = ChatGoogleGenerativeAI(
                model=self.model_name,
                temperature=self.temperature,
            )
            return self._apply_structured_output(model, structured_output_schema) if structured_output_schema else model
        if p == "openai":
            # True OpenAI API (api.openai.com)
            api_key = settings.openai_api_key
            if not api_key or not api_key.strip():
                raise ValueError(
                    "OPENAI_API_KEY is not set or empty. "
                    "Set it in .env when using DEFAULT_LLM_PROVIDER=openai."
                )
            logger.info(
                "Initializing OpenAI client: model=%s, api_key=%s...",
                self.model_name,
                api_key[:10] if api_key else "",
            )
            model = ChatOpenAI(
                model=self.model_name,
                api_key=api_key,
                temperature=self.temperature,
                extra_body=reasoning_body,
            )
            return self._apply_structured_output(model, structured_output_schema) if structured_output_schema else model
        if p == "openrouter":
            # OpenRouter via native model (full usage accounting in streaming)
            api_key = settings.openrouter_api_key
            if not api_key or not api_key.strip():
                raise ValueError(
                    "OPENROUTER_API_KEY is not set or empty. "
                    "Please set it in your .env file."
                )
            logger.info(
                "Initializing OpenRouter native model: model=%s, base_url=%s",
                self.model_name,
                settings.openrouter_base_url,
            )
            model = create_openrouter_native_model(
                model_name=self.model_name,
                base_url=settings.openrouter_base_url,
                api_key=api_key,
                max_tokens=self._model_config.get("max_tokens"),
                callbacks=[UsageAccountingCallback()],
            )
            return self._apply_structured_output(model, structured_output_schema) if structured_output_schema else model
        if p == "vllm":
            # vLLM via OpenAI-compatible API
            # OpenAI client requires api_key to be set, use "EMPTY" as default if not provided
            api_key = settings.vllm_api_key or "EMPTY"
            base_url = settings.vllm_base_url

            logger.info(
                f"Initializing vLLM client: model={self.model_name}, "
                f"base_url={base_url}, api_key={api_key if api_key == 'EMPTY' else api_key[:10] + '...'}"
            )

            model = ChatOpenAI(
                model=self.model_name,
                api_key=api_key,
                base_url=base_url,
                temperature=self.temperature,
                # Note: streaming is controlled at call site (.stream() vs .invoke()),
                # not at model construction time, to avoid issues with LangChain agents
                extra_body=reasoning_body,
                callbacks=[UsageAccountingCallback()],
            )
            return self._apply_structured_output(model, structured_output_schema) if structured_output_schema else model
        # default fallback to Gemini
        logger.warning(f"Unknown provider {p}, falling back to Gemini")
        model = ChatGoogleGenerativeAI(
            model=self.model_name,
            temperature=self.temperature,
        )
        return self._apply_structured_output(model, structured_output_schema) if structured_output_schema else model

    def get_system_prompt(self) -> str:
        """Expose system prompt for other components (no import cycles)."""
        mild_limit = getattr(settings, "llm_mild_limit", None)
        return get_system_prompt(mild_limit=mild_limit)

    def _format_article_header(self, doc: Any) -> str:
        """Format Article URLs header from document metadata.

        Includes Title, kbId, canonical URL, and tags if available.
        """
        meta = getattr(doc, "metadata", {}) or {}
        title = meta.get("title", "")
        kbid = meta.get("kbId") or getattr(doc, "kb_id", None) or ""
        url = meta.get("url") or meta.get("article_url")
        if not url and kbid:
            # Normalize kbId for URL construction (handles edge cases)
            normalized_kbid = extract_numeric_kbid(str(kbid))
            if normalized_kbid:
                url = f"https://kb.comindware.ru/article.php?id={normalized_kbid}"
        tags = meta.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        header_parts = ["Article details:"]
        if title:
            header_parts.append(title)
        if kbid:
            header_parts.append(f"kbId={kbid}")
        if url:
            header_parts.append(url)
        header = " — ".join(header_parts)
        if tags:
            header += f"\nTags: {', '.join(tags)}"
        return header

    def _estimate_request_tokens(self, question: str, context: str) -> dict:
        return estimate_tokens_for_request(
            system_prompt=get_system_prompt(),  # Use function for consistency, no guidance needed for token counting
            question=question,
            context=context,
            reserved_output_tokens=None,  # Will derive from mild_limit * 3 or safety margin
            overhead=100,
        )

    def _build_messages_with_memory(
        self, session_id: str | None, question: str, context: str
    ) -> list[tuple[str, str]]:
        """Assemble chat messages including prior memory (if any).

        System prompt is injected at call time and never stored in memory.
        """
        messages: list[tuple[str, str]] = []
        mild_limit = getattr(settings, "llm_mild_limit", None)
        system_prompt_text = get_system_prompt(mild_limit=mild_limit)
        messages.append(("system", system_prompt_text + "\n\nContext:\n" + context))
        if session_id:
            history = self._conversations.get(session_id)
            # Replay prior turns
            for role, content in history:
                messages.append((role, content))
        messages.append(("user", question))
        return messages

    def _compress_memory(self, session_id: str | None, question: str, context: str) -> None:
        """Compress older turns into a single assistant message when over threshold.

        Keeps the latest two turns intact; replaces earlier turns with one summary.
        """
        if not session_id:
            return
        history = self._conversations.get(session_id)
        if len(history) < 4:
            return
        # Estimate tokens with current history included
        messages = self._build_messages_with_memory(session_id, question, context)
        concat = "\n\n".join([c for _r, c in messages])
        est = self._estimate_request_tokens(question="", context=concat)
        window = int(self._model_config["token_limit"]) or 0
        threshold_pct = int(getattr(settings, "memory_compression_threshold_pct", 85))
        if window <= 0:
            return
        if est["total_tokens"] * 100 < threshold_pct * window:
            return

        # Compress all but last two turns
        preserved = history[-2:]
        to_compress = history[:-2]
        if not to_compress:
            return

        prior_text = "\n\n".join([f"{r.upper()}: {c}" for r, c in to_compress])
        try:
            from kg_engine.llm.summarization import summarize_to_tokens

            compressed = summarize_to_tokens(
                title="Conversation",
                url="",
                matched_chunks=[prior_text],
                full_body=None,
                target_tokens=int(getattr(settings, "memory_compression_target_tokens", 1000)),
                guidance=question,
                llm=self,
                max_retries=2,
            )
        except Exception:
            compressed = prior_text[:2000]

        new_history: list[tuple[str, str]] = [("assistant", compressed)] + preserved
        self._conversations.set(session_id, new_history)

    def _get_fallback_model(self, required_tokens: int, allowed_models: list[str] | None) -> str | None:
        allowed = set(allowed_models or [])
        # If allowed list is empty, do not fallback
        if not allowed:
            return None
        candidates: list[tuple[str, int]] = []
        for name, cfg in MODEL_CONFIGS.items():
            if name == "default":
                continue
            if name == self.model_name:
                continue
            if name not in allowed:
                continue
            limit = int(cfg.get("token_limit", 0))
            candidates.append((name, limit))
        candidates.sort(key=lambda x: x[1], reverse=True)
        for name, limit in candidates:
            if limit >= required_tokens:
                return name
        return None

    def _infer_provider_for_model(self, model_name: str) -> str:
        """Infer provider if no explicit fallback provider is set.

        - gemini* -> gemini
        - otherwise -> openrouter
        """
        explicit = (getattr(settings, "llm_fallback_provider", None) or "").strip().lower()
        if explicit:
            return explicit
        if model_name.startswith("gemini"):
            return "gemini"
        return "openrouter"

    def _create_manager_for(self, model_name: str) -> LLMManager:
        provider = self._infer_provider_for_model(model_name)
        return LLMManager(provider=provider, model=model_name, temperature=self.temperature)

    def stream_response(
        self,
        question: str,
        context_docs: Iterable,
        enable_fallback: bool = False,
        allowed_fallback_models: list[str] | None = None,
        *,
        session_id: str | None = None,
    ) -> Generator[str, None, None]:
        """Stream LLM response with context from complete articles.

        Supports immediate model fallback if estimated tokens exceed window.
        """
        content_blocks: list[str] = []
        for d in context_docs:
            text = getattr(d, "page_content", None) or getattr(d, "content", "")
            header = self._format_article_header(d)
            content_blocks.append(f"{header}\n\n{text}")
        context = "\n\n---\n\n".join(content_blocks)

        # Accurate token estimate and optional immediate fallback
        est = self._estimate_request_tokens(question, context)
        context_window = int(self._model_config["token_limit"]) or 0
        logger.info(
            "Token estimate: input=%d, output=%d, total=%d (window=%d)",
            est["input_tokens"],
            est["output_tokens"],
            est["total_tokens"],
            context_window,
        )

        if enable_fallback and est["total_tokens"] > context_window:
            fb = self._get_fallback_model(est["total_tokens"], allowed_fallback_models)
            if fb:
                logger.warning(
                    "Total tokens %d exceed window %d for %s. Falling back to %s.",
                    est["total_tokens"],
                    context_window,
                    self.model_name,
                    fb,
                )
                fb_mgr = self._create_manager_for(fb)
                yield from fb_mgr.stream_response(
                    question,
                    context_docs,
                    enable_fallback=False,
                    allowed_fallback_models=None,
                )
                return

        # Maybe compress memory then build messages including memory
        self._compress_memory(session_id, question, context)
        model = self._chat_model()
        messages = self._build_messages_with_memory(session_id, question, context)
        try:
            for chunk in model.stream(messages):
                token = getattr(chunk, "content", None)
                if token:
                    yield token
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if enable_fallback and ("context" in msg or "length" in msg or "400" in msg or "bad request" in msg):
                fb = self._get_fallback_model(est["total_tokens"], allowed_fallback_models)
                if fb:
                    logger.warning("API rejected due to context. Retrying with fallback %s", fb)
                fb_mgr = self._create_manager_for(fb)
                yield from fb_mgr.stream_response(
                        question,
                        context_docs,
                        enable_fallback=False,
                        allowed_fallback_models=None,
                    session_id=session_id,
                    )
                return
            raise
        finally:
            # Append this turn to memory (assistant content will be added by caller)
            if session_id:
                self._conversations.append(session_id, "user", question)

    def generate(
        self, question: str, context_docs: Iterable, provider: str | None = None, *, session_id: str | None = None
    ) -> str:
        """Generate LLM response (non-streaming) with context from complete articles."""
        content_blocks: list[str] = []
        for d in context_docs:
            text = getattr(d, "page_content", None) or getattr(d, "content", "")
            header = self._format_article_header(d)
            content_blocks.append(f"{header}\n\n{text}")
        context = "\n\n---\n\n".join(content_blocks)

        # Maybe compress and include prior memory
        self._compress_memory(session_id, question, context)
        model = self._chat_model(provider)
        messages = self._build_messages_with_memory(session_id, question, context)
        resp = model.invoke(messages)
        content = getattr(resp, "content", "")
        if session_id:
            self._conversations.append(session_id, "user", question)
            self._conversations.append(session_id, "assistant", content)
        return content

    def save_assistant_turn(self, session_id: str | None, content: str) -> None:
        if session_id and content:
            self._conversations.append(session_id, "assistant", content)

