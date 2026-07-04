"""Provider-neutral OpenAI-compatible LLM client with async streaming and retry."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 60.0
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0


@dataclass(frozen=True)
class ChatCompletionsConfig:
    """Resolved chat-completions provider configuration."""

    provider: str
    api_key: str
    base_url: str
    chat_model: str
    embedding_model: str


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _setting_or_env(settings: Any, attr: str, env_name: str) -> str:
    return _clean(getattr(settings, attr, "")) or _clean(os.getenv(env_name))


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _cascade_enabled(settings: Any) -> bool:
    value = getattr(settings, "llm_cascade_enabled", None)
    if value is not None:
        return _truthy(value)
    return _truthy(
        os.getenv("LLM_CASCADE_ENABLED")
    )


def _cascade_value(settings: Any, index: int, name: str) -> str:
    attr = f"llm_cascade_{index}_{name.lower()}"
    env_name = f"LLM_CASCADE_{index}_{name.upper()}"
    return _setting_or_env(settings, attr, env_name)


def _prefixed_cascade_enabled(settings: Any, attr_prefix: str, env_prefix: str) -> bool:
    attr = f"{attr_prefix}_cascade_enabled"
    value = getattr(settings, attr, None)
    if value is not None:
        return _truthy(value)
    env_name = f"{env_prefix}_CASCADE_ENABLED"
    return _truthy(os.getenv(env_name))


def _prefixed_cascade_value(
    settings: Any,
    attr_prefix: str,
    env_prefix: str,
    index: int,
    name: str,
) -> str:
    attr = f"{attr_prefix}_cascade_{index}_{name.lower()}"
    env_name = f"{env_prefix}_CASCADE_{index}_{name.upper()}"
    value = getattr(settings, attr, None)
    if value is not None:
        return _clean(value)
    return _clean(os.getenv(env_name))


def _chat_completions_root(base_url: str) -> str:
    """Normalize chat-completions base URLs before appending /v1 paths."""
    base_url = _clean(base_url).rstrip("/")
    if base_url.lower().endswith("/v1"):
        return base_url[:-3].rstrip("/")
    return base_url


def _chat_completions_api_base(base_url: str) -> str:
    root = _chat_completions_root(base_url)
    return f"{root}/v1"


def _selected_provider(settings: Any) -> str:
    return _clean(getattr(settings, "default_llm_provider", "")) or _clean(
        os.getenv("AGENT_PROVIDER")
    )


def _selected_chat_model(settings: Any) -> str:
    return _clean(getattr(settings, "default_model", "")) or _clean(
        os.getenv("AGENT_DEFAULT_MODEL")
    )


def resolve_chat_completions_config(
    settings: Any,
    *,
    require_provider: bool = False,
) -> ChatCompletionsConfig | None:
    """Resolve any OpenAI-compatible LLM provider from settings/env.

    Provider selection is explicit: concrete providers, base URLs, API keys, and
    model names are supplied by Settings or environment variables.
    """
    provider = _selected_provider(settings)
    if not provider:
        if require_provider:
            msg = "DEFAULT_LLM_PROVIDER or AGENT_PROVIDER must be set."
            raise ValueError(msg)
        return None

    api_key = _setting_or_env(settings, "llm_api_key", "LLM_API_KEY")
    base_url = _setting_or_env(settings, "llm_base_url", "LLM_BASE_URL")
    if not api_key or not base_url:
        return None

    chat_model = _selected_chat_model(settings)
    embedding_model = _clean(getattr(settings, "default_embedding_model", ""))

    return ChatCompletionsConfig(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        chat_model=chat_model,
        embedding_model=embedding_model,
    )


def resolve_chat_completions_cascade(
    settings: Any,
    *,
    max_providers: int = 8,
) -> list[ChatCompletionsConfig]:
    """Resolve configured provider/model cascade in priority order."""
    if not _cascade_enabled(settings):
        return []

    return _resolve_prefixed_chat_completions_cascade(
        settings,
        attr_prefix="llm",
        env_prefix="LLM",
        max_providers=max_providers,
    )


def _resolve_prefixed_chat_completions_cascade(
    settings: Any,
    *,
    attr_prefix: str,
    env_prefix: str,
    max_providers: int = 8,
) -> list[ChatCompletionsConfig]:
    """Resolve a configured provider/model cascade for a settings prefix."""
    configs: list[ChatCompletionsConfig] = []
    embedding_model = _clean(getattr(settings, "default_embedding_model", ""))
    for index in range(1, max_providers + 1):
        provider = _prefixed_cascade_value(
            settings,
            attr_prefix,
            env_prefix,
            index,
            "provider",
        )
        model = _prefixed_cascade_value(settings, attr_prefix, env_prefix, index, "model")
        base_url = _prefixed_cascade_value(
            settings,
            attr_prefix,
            env_prefix,
            index,
            "base_url",
        )
        api_key = _prefixed_cascade_value(
            settings,
            attr_prefix,
            env_prefix,
            index,
            "api_key",
        )
        if not provider and not model and not base_url and not api_key:
            continue
        if not provider or not model or not base_url or not api_key:
            logger.info(
                "Skipping incomplete %s cascade entry #%d: provider=%s model=%s "
                "base_url_set=%s api_key_set=%s",
                env_prefix,
                index,
                provider or "(empty)",
                model or "(empty)",
                bool(base_url),
                bool(api_key),
            )
            continue
        configs.append(
            ChatCompletionsConfig(
                provider=provider,
                api_key=api_key,
                base_url=base_url,
                chat_model=model,
                embedding_model=_prefixed_cascade_value(
                    settings,
                    attr_prefix,
                    env_prefix,
                    index,
                    "embedding_model",
                )
                or embedding_model,
            )
        )
    return configs


def resolve_vision_completions_cascade(
    settings: Any,
    *,
    max_providers: int = 8,
) -> list[ChatCompletionsConfig]:
    """Resolve configured Vision-Language provider/model cascade."""
    if not _prefixed_cascade_enabled(
        settings,
        "materials_vision",
        "MATERIALS_VISION",
    ):
        return []
    return _resolve_prefixed_chat_completions_cascade(
        settings,
        attr_prefix="materials_vision",
        env_prefix="MATERIALS_VISION",
        max_providers=max_providers,
    )


class LLMProvider:
    """Thin client for OpenAI-compatible chat and embedding endpoints.

    Async-first client. Legacy sync methods are thin compatibility wrappers
    around the async implementation.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        chat_model: str = "gpt-4o-mini",
        embedding_model: str = "text-embedding-3-small",
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = _MAX_RETRIES,
        retry_base_delay: float = _RETRY_BASE_DELAY,
        reasoning_effort: str | None = None,
    ) -> None:
        self.base_url = _chat_completions_root(base_url)
        self.api_key = api_key
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.reasoning_effort = reasoning_effort
        self._async_client: httpx.AsyncClient | None = None

    def _get_async_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.timeout,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    def _run_async_compat(self, coroutine: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)
        msg = "LLMProvider sync compatibility method called inside an async loop"
        raise RuntimeError(msg)

    # ── Legacy sync compatibility methods ────────────────────────

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        response_format: dict | None = None,
    ) -> str:
        return self._run_async_compat(
            self.chat_async(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )
        )

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        return self._run_async_compat(
            self.chat_json_async(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._run_async_compat(self.embed_async(texts))

    # ── Async methods ─────────────────────────────────────────────

    async def chat_async(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        response_format: dict | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model or self.chat_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        if response_format:
            payload["response_format"] = response_format
        client = self._get_async_client()
        for attempt in range(self.max_retries):
            try:
                resp = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                )
                if resp.status_code == 400:
                    logger.warning(
                        "LLM chat 400: body=%s", resp.text
                    )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except (
                httpx.TimeoutException,
                httpx.HTTPStatusError,
                httpx.ConnectError,
            ) as exc:
                if attempt == self.max_retries - 1:
                    logger.exception(
                        "LLM chat call failed after %d attempts", self.max_retries
                    )
                    return ""
                delay = self.retry_base_delay * (2**attempt) + random.uniform(0, 0.5)  # noqa: S311
                logger.warning(
                    "LLM chat attempt %d/%d failed (%s), retrying in %.1fs",
                    attempt + 1,
                    self.max_retries,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
            except Exception:
                logger.exception("LLM chat call failed with unexpected error")
                return ""
        return ""

    async def chat_json_async(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        raw = await self.chat_async(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        stripped = raw.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            json_lines = [
                line for line in lines
                if not line.strip().startswith("```")
            ]
            try:
                return json.loads("\n".join(json_lines))
            except json.JSONDecodeError:
                pass
        start = stripped.find("{")
        end = stripped.rfind("}") + 1
        if start >= 0 and end > start:
            candidate = stripped[start:end]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        logger.warning("Failed to parse LLM JSON response (%d chars)", len(raw))
        return {}

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """Stream chat completion tokens as an async iterator.

        Yields content string chunks. Retries on transient failures.
        """
        payload: dict[str, Any] = {
            "model": model or self.chat_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        client = self._get_async_client()

        for attempt in range(self.max_retries):
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            return
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
                return
            except (
                httpx.TimeoutException,
                httpx.HTTPStatusError,
                httpx.ConnectError,
            ) as exc:
                if attempt == self.max_retries - 1:
                    logger.exception(
                        "LLM stream failed after %d attempts", self.max_retries
                    )
                    return
                delay = self.retry_base_delay * (2**attempt) + random.uniform(0, 0.5)  # noqa: S311
                logger.warning(
                    "LLM stream attempt %d/%d failed (%s), retrying in %.1fs",
                    attempt + 1,
                    self.max_retries,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
            except Exception:
                logger.exception("LLM stream failed with unexpected error")
                return

    async def chat_stream_collected(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> str:
        """Collect streaming response into a single string."""
        chunks: list[str] = []
        async for chunk in self.chat_stream(messages, **kwargs):
            chunks.append(chunk)
        return "".join(chunks)

    async def embed_async(self, texts: list[str]) -> list[list[float]]:
        """Async embedding with retry."""
        if not texts:
            return []
        client = self._get_async_client()
        results: list[list[float]] = []
        batch_size = 5
        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            batch_result = await self._embed_batch_async(chunk, client)
            if batch_result is not None:
                results.extend(batch_result)
            else:
                for text in chunk:
                    emb = await self._embed_one_async(text, client)
                    results.append(emb)
                    await asyncio.sleep(0.5)
        return results

    async def _embed_batch_async(
        self, texts: list[str], client: httpx.AsyncClient
    ) -> list[list[float]] | None:
        payload = {"model": self.embedding_model, "input": texts}
        for attempt in range(self.max_retries):
            try:
                resp = await client.post(
                    f"{self.base_url}/v1/embeddings", json=payload
                )
                if resp.status_code == 400:
                    return None
                if resp.status_code == 429:
                    delay = (2**attempt) * 5 + random.uniform(0, 2)  # noqa: S311
                    logger.warning(
                        "Async batch embedding rate-limited, retrying in %.1fs",
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                resp.raise_for_status()
                data = resp.json()
                return [item["embedding"] for item in data["data"]]
            except (
                httpx.TimeoutException,
                httpx.HTTPStatusError,
                httpx.ConnectError,
            ) as exc:
                if attempt == self.max_retries - 1:
                    logger.exception(
                        "Async batch embedding call failed after %d attempts",
                        self.max_retries,
                    )
                    return None
                delay = self.retry_base_delay * (2**attempt) + random.uniform(0, 0.5)  # noqa: S311
                logger.warning(
                    "Async batch embedding attempt %d/%d failed (%s), retrying in %.1fs",
                    attempt + 1,
                    self.max_retries,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
            except Exception:
                logger.exception(
                    "Async batch embedding call failed with unexpected error"
                )
                return None
        return None

    async def _embed_one_async(
        self, text: str, client: httpx.AsyncClient
    ) -> list[float]:
        payload = {"model": self.embedding_model, "input": text}
        for attempt in range(self.max_retries):
            try:
                resp = await client.post(
                    f"{self.base_url}/v1/embeddings", json=payload
                )
                if resp.status_code == 429:
                    delay = (2**attempt) * 5 + random.uniform(0, 2)  # noqa: S311
                    logger.warning(
                        "Async individual embedding rate-limited, retrying in %.1fs",
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                resp.raise_for_status()
                data = resp.json()
                return data["data"][0]["embedding"]
            except (
                httpx.TimeoutException,
                httpx.HTTPStatusError,
                httpx.ConnectError,
            ) as exc:
                if attempt == self.max_retries - 1:
                    logger.exception(
                        "Async embedding call failed after %d attempts",
                        self.max_retries,
                    )
                    return []
                delay = self.retry_base_delay * (2**attempt) + random.uniform(0, 0.5)  # noqa: S311
                logger.warning(
                    "Async embedding attempt %d/%d failed (%s), retrying in %.1fs",
                    attempt + 1,
                    self.max_retries,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
            except Exception:
                logger.exception("Async embedding call failed with unexpected error")
                return []
        return []

    # ── Lifecycle ─────────────────────────────────────────────────

    def close(self) -> None:
        self._run_async_compat(self.aclose())

    async def aclose(self) -> None:
        if self._async_client and not self._async_client.is_closed:
            await self._async_client.aclose()
        self._async_client = None


def create_provider_from_settings(settings: Any) -> Any | None:
    """Create the configured LLM provider from application settings.

    ``default_llm_provider`` is the single source of truth. ``AGENT_PROVIDER``
    and ``AGENT_DEFAULT_MODEL`` are accepted as explicit agent-style aliases,
    but no provider is auto-detected from spare API keys.
    """

    kwargs: dict[str, Any] = {
        "chat_model": "",
        "embedding_model": "",
        "timeout": getattr(settings, "llm_timeout_seconds", _DEFAULT_TIMEOUT),
        "max_retries": getattr(settings, "llm_max_retries", _MAX_RETRIES),
        "retry_base_delay": getattr(
            settings, "llm_retry_base_delay", _RETRY_BASE_DELAY
        ),
    }

    def create_from_config(config: ChatCompletionsConfig) -> LLMProvider:
        return _create_llm_provider_from_config(config, **kwargs)

    cascade_configs = resolve_chat_completions_cascade(settings)
    if cascade_configs:
        return create_provider_from_configs(cascade_configs, **kwargs)

    selected_provider = _selected_provider(settings)
    if selected_provider:
        config = resolve_chat_completions_config(settings, require_provider=True)
        return create_from_config(config) if config is not None else None

    return None


def _create_llm_provider_from_config(
    config: ChatCompletionsConfig,
    *,
    chat_model: str = "",
    embedding_model: str = "",
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _MAX_RETRIES,
    retry_base_delay: float = _RETRY_BASE_DELAY,
) -> LLMProvider:
    return LLMProvider(
        base_url=config.base_url,
        api_key=config.api_key,
        chat_model=chat_model or config.chat_model,
        embedding_model=embedding_model or config.embedding_model,
        timeout=timeout,
        max_retries=max_retries,
        retry_base_delay=retry_base_delay,
    )


def create_provider_from_configs(
    configs: list[ChatCompletionsConfig],
    *,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _MAX_RETRIES,
    retry_base_delay: float = _RETRY_BASE_DELAY,
    chat_model: str = "",
    embedding_model: str = "",
) -> Any | None:
    """Create one provider or a fallback chain from resolved configs."""
    if not configs:
        return None
    if len(configs) == 1:
        return _create_llm_provider_from_config(
            configs[0],
            chat_model=chat_model,
            embedding_model=embedding_model,
            timeout=timeout,
            max_retries=max_retries,
            retry_base_delay=retry_base_delay,
        )

    from kg_engine.llm_core.fallback import FallbackChain

    return FallbackChain(
        [
            (
                f"{config.provider}:{config.chat_model}",
                _create_llm_provider_from_config(
                    config,
                    chat_model=chat_model,
                    embedding_model=embedding_model,
                    timeout=timeout,
                    max_retries=max_retries,
                    retry_base_delay=retry_base_delay,
                ),
            )
            for config in configs
        ],
    )


def create_agent_chat_model_from_settings(settings: Any) -> tuple[Any, str]:
    """Create an agent-compatible chat model from the generic LLM provider."""
    cascade_configs = resolve_chat_completions_cascade(settings)
    config = (
        cascade_configs[0]
        if cascade_configs
        else resolve_chat_completions_config(settings, require_provider=True)
    )
    if config is None:
        provider = _selected_provider(settings)
        if not provider:
            msg = "DEFAULT_LLM_PROVIDER or AGENT_PROVIDER must be set."
        else:
            msg = (
                f"API key and base URL for provider '{provider}' are not configured. "
                "Use LLM_API_KEY and LLM_BASE_URL."
            )
        raise RuntimeError(msg)

    try:
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.messages import AIMessage
        from langchain_core.messages import BaseMessage
        from langchain_core.outputs import ChatGeneration
        from langchain_core.outputs import ChatResult
    except ImportError as exc:
        msg = (
            "langchain-core is required for Deep Agents. "
            "Install project dependencies before using deepagents mode."
        )
        raise RuntimeError(msg) from exc

    provider = create_provider_from_settings(settings)
    if provider is None:
        msg = "No complete LLM provider configuration is available."
        raise RuntimeError(msg)

    class ProviderChatModel(BaseChatModel):
        provider: Any
        temperature: float
        max_tokens: int
        _bound_tools: list[Any] | None = None

        @property
        def _llm_type(self) -> str:
            return "materials-kg-chat-completions"

        def bind_tools(
            self,
            tools: list[Any],
            **kwargs: Any,
        ) -> "ProviderChatModel":
            model = ProviderChatModel(
                provider=self.provider,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            model._bound_tools = list(tools)
            return model

        @staticmethod
        def _message_to_dict(message: BaseMessage) -> dict[str, str]:
            role = getattr(message, "type", "user")
            if role == "human":
                role = "user"
            elif role == "ai":
                role = "assistant"
            return {"role": role, "content": str(message.content)}

        def _generate(
            self,
            messages: list[BaseMessage],
            stop: list[str] | None = None,
            run_manager: Any | None = None,
            **kwargs: Any,
        ) -> ChatResult:
            _ = (stop, run_manager)
            content = self.provider.chat(
                [self._message_to_dict(message) for message in messages],
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
            )
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content=content))]
            )

        async def _agenerate(
            self,
            messages: list[BaseMessage],
            stop: list[str] | None = None,
            run_manager: Any | None = None,
            **kwargs: Any,
        ) -> ChatResult:
            _ = (stop, run_manager)
            content = await self.provider.chat_async(
                [self._message_to_dict(message) for message in messages],
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
            )
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content=content))]
            )

    model = ProviderChatModel(
        provider=provider,
        temperature=getattr(settings, "llm_temperature", 0.7),
        max_tokens=getattr(settings, "llm_max_tokens", 4096),
    )
    label = (
        "cascade:"
        + ">".join(f"{item.provider}:{item.chat_model}" for item in cascade_configs)
        if cascade_configs
        else f"{config.provider}:{config.chat_model}"
    )
    return model, label


def create_provider_from_env() -> Any | None:
    """Create provider from global settings if API key is available."""
    from kg_engine.config.settings import settings

    return create_provider_from_settings(settings)
