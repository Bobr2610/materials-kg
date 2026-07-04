"""OpenAI-compatible LLM provider with async streaming and retry."""

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
_OPENAI_BASE_URL = "https://api.openai.com"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api"
_POLZA_BASE_URL = "https://polza.ai/api"
_GROQ_BASE_URL = "https://api.groq.com/openai"
_MISTRAL_BASE_URL = "https://api.mistral.ai"
_YANDEX_BASE_URL = "https://ai.api.cloud.yandex.net"
_PROVIDER_DEFAULT_BASE_URLS = {
    "openai": _OPENAI_BASE_URL,
    "openrouter": _OPENROUTER_BASE_URL,
    "polza": _POLZA_BASE_URL,
    "groq": _GROQ_BASE_URL,
    "mistral": _MISTRAL_BASE_URL,
    "yandex": _YANDEX_BASE_URL,
}


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    """Resolved OpenAI-compatible provider configuration."""

    provider: str
    api_key: str
    base_url: str
    chat_model: str
    embedding_model: str


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _provider_env_prefix(provider: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in provider).upper()


def _setting_or_env(settings: Any, attr: str, env_name: str) -> str:
    return _clean(getattr(settings, attr, "")) or _clean(os.getenv(env_name))


def _openrouter_model_name(model: str) -> str:
    """Return an OpenRouter model slug without forcing OpenAI-only models."""
    model = _clean(model)
    if not model or "/" in model:
        return model
    return f"openai/{model}"


def _openai_compatible_root(base_url: str) -> str:
    """Normalize OpenAI-compatible base URLs before appending /v1 paths."""
    base_url = _clean(base_url).rstrip("/")
    if base_url.lower().endswith("/v1"):
        return base_url[:-3].rstrip("/")
    return base_url


def _openai_compatible_api_base(base_url: str) -> str:
    root = _openai_compatible_root(base_url)
    return f"{root}/v1"


def _selected_provider(settings: Any) -> str:
    return _clean(getattr(settings, "default_llm_provider", "")) or _clean(
        os.getenv("AGENT_PROVIDER")
    )


def _selected_chat_model(settings: Any) -> str:
    return _clean(getattr(settings, "default_model", "")) or _clean(
        os.getenv("AGENT_DEFAULT_MODEL")
    )


def resolve_openai_compatible_config(
    settings: Any,
    *,
    require_provider: bool = False,
) -> OpenAICompatibleConfig | None:
    """Resolve any OpenAI-compatible LLM provider from settings/env.

    Known providers keep their built-in default base URLs. Provider selection is
    explicit: no other provider or generic API key is used as a fallback.
    """
    provider = _selected_provider(settings)
    if not provider:
        if require_provider:
            msg = "DEFAULT_LLM_PROVIDER or AGENT_PROVIDER must be set."
            raise ValueError(msg)
        return None

    provider_key = provider.lower()
    env_prefix = _provider_env_prefix(provider)
    api_key = _setting_or_env(
        settings,
        f"{provider_key}_api_key",
        f"{env_prefix}_API_KEY",
    )
    base_url = (
        _setting_or_env(settings, f"{provider_key}_base_url", f"{env_prefix}_BASE_URL")
        or _PROVIDER_DEFAULT_BASE_URLS.get(provider_key, "")
    )
    if not api_key or not base_url:
        return None

    chat_model = _selected_chat_model(settings)
    embedding_model = _clean(getattr(settings, "default_embedding_model", ""))
    if provider_key == "openrouter":
        chat_model = _openrouter_model_name(chat_model)
        embedding_model = _openrouter_model_name(embedding_model)
    elif provider_key == "yandex":
        folder_id = _clean(getattr(settings, "yandex_folder_id", ""))
        if folder_id:
            chat_model = f"gpt://{folder_id}/{chat_model.lstrip('gpt://')}" if chat_model else ""
            embedding_model = f"emb://{folder_id}/{embedding_model.lstrip('emb://')}" if embedding_model else ""

    return OpenAICompatibleConfig(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        chat_model=chat_model,
        embedding_model=embedding_model,
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
        self.base_url = _openai_compatible_root(base_url)
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
                    delay = (2**attempt) * 5 + random.uniform(0, 2)
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
                delay = self.retry_base_delay * (2**attempt) + random.uniform(0, 0.5)
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
                    delay = (2**attempt) * 5 + random.uniform(0, 2)
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


def create_provider_from_settings(settings: Any) -> LLMProvider | None:
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

    def create_from_config(config: OpenAICompatibleConfig) -> LLMProvider:
        reasoning_effort: str | None = None
        if config.provider == "yandex":
            reasoning_effort = "none"
        return LLMProvider(
            base_url=config.base_url,
            api_key=config.api_key,
            chat_model=config.chat_model,
            embedding_model=config.embedding_model,
            timeout=kwargs["timeout"],
            max_retries=kwargs["max_retries"],
            retry_base_delay=kwargs["retry_base_delay"],
            reasoning_effort=reasoning_effort,
        )

    selected_provider = _selected_provider(settings)
    if selected_provider:
        config = resolve_openai_compatible_config(settings, require_provider=True)
        return create_from_config(config) if config is not None else None

    return None


def create_langchain_chat_model_from_settings(settings: Any) -> tuple[Any, str]:
    """Create a LangChain-compatible chat model from shared LLM settings."""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        msg = (
            "langchain-openai is required for Deep Agents. "
            "Install kg_engine/requirements.txt before using deepagents mode."
        )
        raise RuntimeError(msg) from exc

    config = resolve_openai_compatible_config(settings, require_provider=True)
    if config is None:
        provider = _selected_provider(settings)
        if not provider:
            msg = "DEFAULT_LLM_PROVIDER or AGENT_PROVIDER must be set."
        else:
            msg = (
                f"API key and base URL for provider '{provider}' are not configured. "
                "Use provider-specific env vars for the selected provider."
            )
        raise RuntimeError(msg)

    model = ChatOpenAI(
        model=config.chat_model,
        api_key=config.api_key,
        base_url=_openai_compatible_api_base(config.base_url),
        temperature=getattr(settings, "llm_temperature", 0.7),
        timeout=getattr(settings, "llm_timeout_seconds", _DEFAULT_TIMEOUT),
        max_retries=getattr(settings, "llm_max_retries", _MAX_RETRIES),
    )
    return model, f"{config.provider}:{config.chat_model}"


def create_provider_from_env() -> LLMProvider | None:
    """Create provider from global settings if API key is available."""
    from kg_engine.config.settings import settings

    return create_provider_from_settings(settings)
