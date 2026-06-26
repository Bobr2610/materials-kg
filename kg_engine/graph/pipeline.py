"""End-to-end knowledge graph building pipeline."""

from __future__ import annotations

import logging
from typing import Any

from kg_engine.graph.builder import KnowledgeGraphBuilder
from kg_engine.graph.extractor import EntityExtractor
from kg_engine.graph.query import KnowledgeGraphQuery
from kg_engine.graph.search import HybridSearch
from kg_engine.graph.store import GraphStore

logger = logging.getLogger(__name__)


class GraphPipeline:
    """Orchestrates document ingestion, entity extraction, and graph construction."""

    def __init__(
        self,
        store: GraphStore | None = None,
        llm_manager: Any | None = None,
        vector_search_fn: Any | None = None,
    ) -> None:
        self.store = store or GraphStore()
        self.extractor = EntityExtractor(llm_manager=llm_manager)
        self.builder = KnowledgeGraphBuilder(store=self.store, extractor=self.extractor)
        self.query = KnowledgeGraphQuery(store=self.store)
        self.search = HybridSearch(store=self.store, vector_search_fn=vector_search_fn)

    def index_document(
        self,
        text: str,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
        use_llm: bool = True,
    ) -> dict[str, Any]:
        return self.builder.process_document(
            text=text,
            source=source,
            metadata=metadata,
            use_llm=use_llm,
        )

    def index_chunks(
        self,
        chunks: list[dict[str, Any]],
        use_llm: bool = True,
    ) -> dict[str, Any]:
        return self.builder.process_chunks(chunks, use_llm=use_llm)

    def ask(
        self,
        query: str,
        mode: str | None = None,
    ) -> dict[str, Any]:
        material_results = self.query.query_by_material_and_mode(query, mode_name=mode)
        gap_results = self.query.find_data_gaps()
        related = self.query.query_related(query, max_depth=1)
        stats = self.query.stats()

        property_results = self.query.query_by_property(query)

        return {
            "query": query,
            "mode_filter": mode,
            "materials": material_results,
            "properties": property_results,
            "related_entities": related,
            "data_gaps": gap_results,
            "stats": stats,
        }

    def find_gaps(self) -> list[dict[str, Any]]:
        return self.query.find_data_gaps()

    def stats(self) -> dict[str, Any]:
        return self.query.stats()

    def save(self, path: str) -> None:
        self.store.save(path)

    @classmethod
    def load(cls, path: str, **kwargs: Any) -> GraphPipeline:
        store = GraphStore.load(path)
        return cls(store=store, **kwargs)
