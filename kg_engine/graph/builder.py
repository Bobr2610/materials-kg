"""Build knowledge graph from documents using entity extraction."""

from __future__ import annotations

import logging
from typing import Any

from kg_engine.graph.extractor import EntityExtractor
from kg_engine.graph.schemas import (
    ExtractionResult,
    GraphEntity,
    GraphRelation,
)
from kg_engine.graph.store import GraphStore

logger = logging.getLogger(__name__)


class KnowledgeGraphBuilder:
    """Build a knowledge graph from document chunks by extracting entities and relations."""

    def __init__(
        self,
        store: GraphStore,
        extractor: EntityExtractor,
    ) -> None:
        self._store = store
        self._extractor = extractor

    def process_document(
        self,
        text: str,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
        use_llm: bool = True,
    ) -> ExtractionResult:
        entities, relations = self._extractor.extract(
            text=text,
            source=source,
            use_llm=use_llm,
        )

        article_entity = GraphEntity(
            id=source or f"doc_{hash(text) % 10**8}",
            type="article",  # type: ignore
            name=metadata.get("title", source or "Unknown") if metadata else (source or "Unknown"),
            properties=metadata or {},
            source=source,
        )

        entity_ids: set[str] = set()
        for entity in entities:
            self._store.add_entity(entity)
            entity_ids.add(entity.id)
            relations.append(
                GraphRelation(
                    source_id=article_entity.id,
                    target_id=entity.id,
                    type="described_in",  # type: ignore
                    properties={},
                    source=source,
                    confidence=0.8,
                )
            )

        self._store.add_entity(article_entity)

        for relation in relations:
            self._store.add_relation(relation)

        logger.info(
            "Processed document '%s': %d entities, %d relations",
            source or "unknown",
            len(entities),
            len(relations),
        )

        return {
            "entities": entities,
            "relations": relations,
        }

    def process_chunks(
        self,
        chunks: list[dict[str, Any]],
        use_llm: bool = True,
    ) -> dict[str, Any]:
        total_entities = 0
        total_relations = 0

        for chunk in chunks:
            text = chunk.get("content") or chunk.get("text", "")
            source = chunk.get("metadata", {}).get("source") if isinstance(chunk.get("metadata"), dict) else None
            metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
            result = self.process_document(
                text=text,
                source=source,
                metadata=metadata,
                use_llm=use_llm,
            )
            total_entities += len(result.get("entities", []))
            total_relations += len(result.get("relations", []))

        return {
            "total_entities": total_entities,
            "total_relations": total_relations,
            "total_chunks": len(chunks),
        }
