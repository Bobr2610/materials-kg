"""Chroma vector store wrapper (async HTTP client only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import chromadb

from kg_engine.config.settings import settings


@dataclass
class RetrievedDoc:
    page_content: str
    metadata: dict[str, Any]


class ChromaStore:
    """Async-only thin wrapper around Chroma HTTP client for add/query."""

    def __init__(
        self,
        collection_name: str,
        host: str | None = None,
        port: int | None = None,
    ):
        self.collection_name = collection_name
        self.host = host or settings.chroma_client_host
        self.port = port or settings.chromadb_port
        self._async_client: chromadb.AsyncHttpClient | None = None
        self._async_collection = None

    async def _get_async_client(self) -> chromadb.AsyncHttpClient:
        """Lazy initialization of async HTTP client."""
        if self._async_client is None:
            self._async_client = await chromadb.AsyncHttpClient(
                host=self.host,
                port=self.port,
                ssl=settings.chromadb_ssl,
            )
        return self._async_client

    async def get_collection(self):
        """Get or create async collection."""
        if self._async_collection is None:
            client = await self._get_async_client()
            self._async_collection = await client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._async_collection

    async def similarity_search_async(
        self, query_embedding: list[float], k: int = 5
    ) -> list[RetrievedDoc]:
        """Async similarity search."""
        collection = await self.get_collection()
        res = await collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            include=["documents", "metadatas"],
        )
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        return [RetrievedDoc(page_content=d, metadata=m) for d, m in zip(docs, metas)]

    async def add_async(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str] | None = None,
        embeddings: list[list[float]] | None = None,
    ) -> None:
        """Async add documents to collection."""
        collection = await self.get_collection()
        await collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    async def get_any_doc_meta_async(self, where: dict[str, Any]) -> dict[str, Any] | None:
        """Return metadata of any one document matching a metadata filter."""
        collection = await self.get_collection()
        res = await collection.get(where=where, include=["metadatas"], limit=1)
        metas = res.get("metadatas", [])
        if metas:
            return metas[0]
        return None

    async def get_by_kb_id_async(self, kb_id: str) -> dict[str, Any] | None:
        """Return metadata for a single kbId (first chunk), or None if not found."""
        collection = await self.get_collection()
        res = await collection.get(where={"kbId": kb_id}, include=["metadatas"], limit=1)
        metas = res.get("metadatas", [])
        if metas:
            return metas[0]
        return None

    async def delete_where_async(self, where: dict[str, Any]) -> None:
        """Delete all records matching a metadata filter."""
        collection = await self.get_collection()
        await collection.delete(where=where)
