"""Hybrid search combining vector similarity with graph traversal."""

from __future__ import annotations

import logging
from typing import Any

from kg_engine.graph.query import KnowledgeGraphQuery
from kg_engine.graph.schemas import GraphEntity
from kg_engine.graph.store import GraphStore

logger = logging.getLogger(__name__)


class HybridSearch:
    """Combine graph traversal with vector similarity for enriched search results."""

    def __init__(
        self,
        store: GraphStore,
        vector_search_fn: Any | None = None,
    ) -> None:
        self._store = store
        self._vector_search = vector_search_fn
        self._query = KnowledgeGraphQuery(store)

    def search(
        self,
        query: str,
        top_k: int = 10,
        include_vector: bool = True,
        include_graph: bool = True,
    ) -> list[dict[str, Any]]:
        vector_results: list[dict[str, Any]] = []
        graph_results: list[dict[str, Any]] = []

        if include_vector and self._vector_search is not None:
            try:
                vector_results = self._vector_search(query, top_k=top_k)
            except Exception as exc:
                logger.warning("Vector search failed: %s", exc)

        if include_graph:
            seen_names: set[str] = set()
            for result in self._query.query_by_material_and_mode(query):
                mat_name = result.get("material", "")
                if mat_name and mat_name.lower() not in seen_names:
                    seen_names.add(mat_name.lower())
                    graph_results.append({
                        "source": "graph",
                        "type": "material",
                        "name": mat_name,
                        "details": result,
                        "score": 0.9,
                    })
            for result in self._query.query_related(query, max_depth=1):
                entity_name = result.get("entity", "")
                if entity_name and entity_name.lower() not in seen_names:
                    seen_names.add(entity_name.lower())
                    graph_results.append({
                        "source": "graph",
                        "type": result.get("type", "unknown"),
                        "name": entity_name,
                        "details": result,
                        "score": 0.8,
                    })

        combined: list[dict[str, Any]] = []
        seen_keys: set[str] = set()

        for r in vector_results:
            key = str(r.get("kb_id", r.get("id", hash(str(r)))))
            if key not in seen_keys:
                seen_keys.add(key)
                r["source"] = "vector"
                combined.append(r)

        for r in graph_results:
            key = r.get("name", str(hash(str(r))))
            if key not in seen_keys:
                seen_keys.add(key)
                combined.append(r)

        return combined[:top_k]
