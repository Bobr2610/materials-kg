"""OpenAI-compatible LLM provider via httpx."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 60.0


class LLMProvider:
    """Thin client for OpenAI-compatible chat and embedding endpoints."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        chat_model: str = "gpt-4o-mini",
        embedding_model: str = "text-embedding-3-small",
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        self.timeout = timeout
        self._client = httpx.Client(
            timeout=self.timeout,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

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
        try:
            resp = self._client.post(f"{self.base_url}/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception:
            logger.exception("LLM chat call failed")
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
        try:
            resp = self._client.post(f"{self.base_url}/v1/embeddings", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return [item["embedding"] for item in data["data"]]
        except Exception:
            logger.exception("Embedding call failed")
            return [[] for _ in texts]

    def close(self) -> None:
        self._client.close()


def create_provider_from_env() -> LLMProvider | None:
    """Create provider from settings if API key is available."""
    from kg_engine.config.settings import settings

    chat = settings.default_model or "gpt-4o-mini"
    embedding = settings.embedding_model or "text-embedding-3-small"

    if settings.openai_api_key:
        return LLMProvider(
            base_url="https://api.openai.com",
            api_key=settings.openai_api_key,
            chat_model=chat,
            embedding_model=embedding,
        )
    if settings.vllm_base_url and settings.vllm_api_key:
        return LLMProvider(
            base_url=settings.vllm_base_url,
            api_key=settings.vllm_api_key,
            chat_model=chat,
            embedding_model=embedding,
        )
    if settings.openrouter_api_key and settings.openrouter_base_url:
        return LLMProvider(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            chat_model=f"openai/{chat}",
            embedding_model=f"openai/{embedding}",
        )
    return None
