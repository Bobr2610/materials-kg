"""OpenAI-compatible LLM provider with async streaming and retry."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
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


def _clean(value: str | None) -> str:
    return (value or "").strip()


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


class LLMProvider:
    """Thin client for OpenAI-compatible chat and embedding endpoints.

    Supports both sync and async operations. Async methods use a lazily
    initialized ``httpx.AsyncClient`` that shares configuration with the
    sync client.
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
    ) -> None:
        self.base_url = _openai_compatible_root(base_url)
        self.api_key = api_key
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self._client = httpx.Client(
            timeout=self.timeout,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        self._async_client: httpx.AsyncClient | None = None

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        return self._async_client

    # ── Sync methods ──────────────────────────────────────────────

    def chat(
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
        if response_format:
            payload["response_format"] = response_format
        for attempt in range(self.max_retries):
            try:
                resp = self._client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
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
                import time

                time.sleep(delay)
            except Exception:
                logger.exception("LLM chat call failed with unexpected error")
                return ""
        return ""

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        raw = self.chat(
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
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(raw[start:end])
                except json.JSONDecodeError:
                    pass
            logger.warning("Failed to parse LLM JSON response")
            return {}

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": self.embedding_model, "input": texts}
        for attempt in range(self.max_retries):
            try:
                resp = self._client.post(f"{self.base_url}/v1/embeddings", json=payload)
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
                        "Embedding call failed after %d attempts", self.max_retries
                    )
                    return [[] for _ in texts]
                delay = self.retry_base_delay * (2**attempt) + random.uniform(0, 0.5)  # noqa: S311
                logger.warning(
                    "Embedding attempt %d/%d failed (%s), retrying in %.1fs",
                    attempt + 1,
                    self.max_retries,
                    exc,
                    delay,
                )
                import time

                time.sleep(delay)
            except Exception:
                logger.exception("Embedding call failed with unexpected error")
                return [[] for _ in texts]
        return [[] for _ in texts]

    # ── Async methods ─────────────────────────────────────────────

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
        payload = {"model": self.embedding_model, "input": texts}

        for attempt in range(self.max_retries):
            try:
                resp = await client.post(f"{self.base_url}/v1/embeddings", json=payload)
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
                        "Async embedding call failed after %d attempts",
                        self.max_retries,
                    )
                    return [[] for _ in texts]
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
                return [[] for _ in texts]
        return [[] for _ in texts]

    # ── Lifecycle ─────────────────────────────────────────────────

    def close(self) -> None:
        self._client.close()

    async def aclose(self) -> None:
        if self._async_client and not self._async_client.is_closed:
            await self._async_client.aclose()


def create_provider_from_settings(settings: Any) -> LLMProvider | None:
    """Create the configured LLM provider from application settings.

    ``default_llm_provider`` is the single source of truth. When it is empty,
    provider selection keeps the historical auto-detect order for compatibility.
    ``AGENT_PROVIDER`` and ``AGENT_DEFAULT_MODEL`` are accepted as agent-style
    aliases for local workflows that already use those names.
    """

    selected_provider = _clean(
        getattr(settings, "default_llm_provider", "")
    ) or _clean(os.getenv("AGENT_PROVIDER"))
    chat = _clean(getattr(settings, "default_model", "")) or _clean(
        os.getenv("AGENT_DEFAULT_MODEL")
    )
    embedding = _clean(getattr(settings, "default_embedding_model", ""))

    kwargs: dict[str, Any] = {
        "chat_model": chat,
        "embedding_model": embedding,
        "max_retries": getattr(settings, "llm_max_retries", _MAX_RETRIES),
        "retry_base_delay": getattr(
            settings, "llm_retry_base_delay", _RETRY_BASE_DELAY
        ),
    }

    def create_openai() -> LLMProvider | None:
        api_key = _clean(getattr(settings, "openai_api_key", None))
        if not api_key:
            return None
        base_url = _clean(getattr(settings, "openai_base_url", ""))
        return LLMProvider(
            base_url=base_url or _OPENAI_BASE_URL,
            api_key=api_key,
            **kwargs,
        )

    def create_vllm() -> LLMProvider | None:
        base_url = _clean(getattr(settings, "vllm_base_url", ""))
        api_key = _clean(getattr(settings, "vllm_api_key", ""))
        if not base_url or not api_key:
            return None
        return LLMProvider(
            base_url=base_url,
            api_key=api_key,
            **kwargs,
        )

    def create_openrouter() -> LLMProvider | None:
        api_key = _clean(getattr(settings, "openrouter_api_key", ""))
        if not api_key:
            return None
        base_url = _clean(getattr(settings, "openrouter_base_url", ""))
        openrouter_kwargs = dict(kwargs)
        openrouter_kwargs["chat_model"] = _openrouter_model_name(chat)
        openrouter_kwargs["embedding_model"] = _openrouter_model_name(embedding)
        return LLMProvider(
            base_url=base_url or _OPENROUTER_BASE_URL,
            api_key=api_key,
            **openrouter_kwargs,
        )

    def create_polza() -> LLMProvider | None:
        api_key = _clean(getattr(settings, "polza_api_key", ""))
        if not api_key:
            return None
        base_url = _clean(getattr(settings, "polza_base_url", ""))
        return LLMProvider(
            base_url=base_url or _POLZA_BASE_URL,
            api_key=api_key,
            **kwargs,
        )

    def create_groq() -> LLMProvider | None:
        api_key = _clean(getattr(settings, "groq_api_key", ""))
        if not api_key:
            return None
        base_url = _clean(getattr(settings, "groq_base_url", ""))
        return LLMProvider(
            base_url=base_url or _GROQ_BASE_URL,
            api_key=api_key,
            **kwargs,
        )

    def create_mistral() -> LLMProvider | None:
        api_key = _clean(getattr(settings, "mistral_api_key", ""))
        if not api_key:
            return None
        base_url = _clean(getattr(settings, "mistral_base_url", ""))
        return LLMProvider(
            base_url=base_url or _MISTRAL_BASE_URL,
            api_key=api_key,
            **kwargs,
        )

    factories = {
        "openai": create_openai,
        "vllm": create_vllm,
        "openrouter": create_openrouter,
        "polza": create_polza,
        "groq": create_groq,
        "mistral": create_mistral,
    }

    if selected_provider:
        factory = factories.get(selected_provider.lower())
        if factory is None:
            logger.warning("Unsupported LLM provider configured: %s", selected_provider)
            return None
        return factory()

    for factory in (
        create_openai,
        create_vllm,
        create_openrouter,
        create_polza,
        create_groq,
        create_mistral,
    ):
        provider = factory()
        if provider is not None:
            return provider
    return None


def create_provider_from_env() -> LLMProvider | None:
    """Create provider from global settings if API key is available."""
    from kg_engine.config.settings import settings

    return create_provider_from_settings(settings)
