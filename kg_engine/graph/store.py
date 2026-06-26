"""In-memory graph store using NetworkX with import/export support."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

import networkx as nx

from kg_engine.graph.schemas import (
    EntityType,
    GraphEntity,
    GraphRelation,
    RelationType,
)

logger = logging.getLogger(__name__)


class GraphStore:
    """Thread-safe in-memory knowledge graph store backed by NetworkX.

    Provides add/remove/query operations for entities and relations,
    with JSON serialization for persistence.
    """

    def __init__(self) -> None:
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self._lock = threading.Lock()

    # ── Entity operations ─────────────────────────────────────────────────

    def add_entity(self, entity: GraphEntity) -> str:
        with self._lock:
            if self._graph.has_node(entity.id):
                existing = self._graph.nodes[entity.id]
                existing["name"] = entity.name
                existing["type"] = entity.type.value
                existing["properties"] = {**existing.get("properties", {}), **entity.properties}
                if entity.source:
                    existing["source"] = entity.source
                existing["confidence"] = max(existing.get("confidence", 0), entity.confidence)
                aliases = set(existing.get("aliases", [])) | set(entity.aliases)
                existing["aliases"] = list(aliases)
                logger.debug("Updated entity: %s (%s)", entity.id, entity.name)
            else:
                self._graph.add_node(
                    entity.id,
                    name=entity.name,
                    type=entity.type.value,
                    entity_type=entity.type.value,
                    aliases=list(entity.aliases),
                    properties=dict(entity.properties),
                    source=entity.source,
                    confidence=entity.confidence,
                )
                logger.debug("Added entity: %s (%s)", entity.id, entity.name)
            return entity.id

    def remove_entity(self, entity_id: str) -> bool:
        with self._lock:
            if not self._graph.has_node(entity_id):
                return False
            self._graph.remove_node(entity_id)
            logger.debug("Removed entity: %s", entity_id)
            return True

    def get_entity(self, entity_id: str) -> GraphEntity | None:
        with self._lock:
            if not self._graph.has_node(entity_id):
                return None
            data = dict(self._graph.nodes[entity_id])
            return GraphEntity(
                id=entity_id,
                type=EntityType(data.get("type", data.get("entity_type", "material"))),
                name=data.get("name", ""),
                aliases=data.get("aliases", []),
                properties=data.get("properties", {}),
                source=data.get("source"),
                confidence=data.get("confidence", 1.0),
            )

    def find_entities(
        self,
        entity_type: EntityType | None = None,
        name_contains: str | None = None,
        limit: int = 100,
    ) -> list[GraphEntity]:
        results: list[GraphEntity] = []
        with self._lock:
            for node_id, data in self._graph.nodes(data=True):
                if entity_type and data.get("entity_type") != entity_type.value:
                    continue
                if name_contains and name_contains.lower() not in data.get("name", "").lower():
                    matched = False
                    for alias in data.get("aliases", []):
                        if name_contains.lower() in alias.lower():
                            matched = True
                            break
                    if not matched:
                        continue
                results.append(
                    GraphEntity(
                        id=node_id,
                        type=EntityType(data.get("entity_type", "material")),
                        name=data.get("name", ""),
                        aliases=data.get("aliases", []),
                        properties=data.get("properties", {}),
                        source=data.get("source"),
                        confidence=data.get("confidence", 1.0),
                    )
                )
                if len(results) >= limit:
                    break
        return results

    def count_entities(self, entity_type: EntityType | None = None) -> int:
        with self._lock:
            if entity_type is None:
                return self._graph.number_of_nodes()
            return sum(
                1 for _, d in self._graph.nodes(data=True) if d.get("entity_type") == entity_type.value
            )

    # ── Relation operations ───────────────────────────────────────────────

    def add_relation(self, relation: GraphRelation) -> str:
        key = f"{relation.source_id}--{relation.type.value}--{relation.target_id}"
        with self._lock:
            if not self._graph.has_node(relation.source_id):
                logger.warning("Source entity not found: %s", relation.source_id)
                return key
            if not self._graph.has_node(relation.target_id):
                logger.warning("Target entity not found: %s", relation.target_id)
                return key
            self._graph.add_edge(
                relation.source_id,
                relation.target_id,
                key=key,
                type=relation.type.value,
                relation_type=relation.type.value,
                properties=dict(relation.properties),
                source=relation.source,
                confidence=relation.confidence,
            )
            logger.debug("Added relation: %s", key)
            return key

    def remove_relation(self, source_id: str, target_id: str, relation_type: RelationType) -> bool:
        with self._lock:
            edges = list(self._graph.edges(source_id, target_id, keys=True))
            for u, v, k in edges:
                edge_data = self._graph.get_edge_data(u, v, k) or {}
                if edge_data.get("relation_type") == relation_type.value:
                    self._graph.remove_edge(u, v, k)
                    return True
            return False

    def get_relations(
        self,
        entity_id: str | None = None,
        relation_type: RelationType | None = None,
    ) -> list[GraphRelation]:
        results: list[GraphRelation] = []
        with self._lock:
            edges = list(self._graph.edges(keys=True, data=True))
            for u, v, k, d in edges:
                if entity_id and u != entity_id and v != entity_id:
                    continue
                if relation_type and d.get("relation_type") != relation_type.value:
                    continue
                results.append(
                    GraphRelation(
                        source_id=u,
                        target_id=v,
                        type=RelationType(d.get("relation_type", "depends_on")),
                        properties=d.get("properties", {}),
                        source=d.get("source"),
                        confidence=d.get("confidence", 1.0),
                    )
                )
        return results

    def count_relations(self, relation_type: RelationType | None = None) -> int:
        with self._lock:
            if relation_type is None:
                return self._graph.number_of_edges()
            return sum(
                1 for _, _, d in self._graph.edges(data=True) if d.get("relation_type") == relation_type.value
            )

    # ── Graph traversal ───────────────────────────────────────────────────

    def get_neighbors(
        self,
        entity_id: str,
        relation_type: RelationType | None = None,
        max_depth: int = 1,
    ) -> list[GraphEntity]:
        """Get neighbor entities within *max_depth* hops, optionally filtered by relation type."""
        visited: set[str] = set()
        results: list[GraphEntity] = []
        queue: list[tuple[str, int]] = [(entity_id, 0)]

        with self._lock:
            while queue:
                current_id, depth = queue.pop(0)
                if current_id in visited:
                    continue
                visited.add(current_id)

                if current_id != entity_id and self._graph.has_node(current_id):
                    data = dict(self._graph.nodes[current_id])
                    results.append(
                        GraphEntity(
                            id=current_id,
                            type=EntityType(data.get("entity_type", "material")),
                            name=data.get("name", ""),
                            aliases=data.get("aliases", []),
                            properties=data.get("properties", {}),
                            source=data.get("source"),
                            confidence=data.get("confidence", 1.0),
                        )
                    )

                if depth >= max_depth:
                    continue

                for neighbor in self._graph.successors(current_id):
                    if relation_type:
                        edge_data = self._graph.get_edge_data(current_id, neighbor)
                        if edge_data:
                            for k, d in edge_data.items():
                                if isinstance(d, dict) and d.get("relation_type") == relation_type.value:
                                    queue.append((neighbor, depth + 1))
                    else:
                        queue.append((neighbor, depth + 1))

                for neighbor in self._graph.predecessors(current_id):
                    if relation_type:
                        edge_data = self._graph.get_edge_data(neighbor, current_id)
                        if edge_data:
                            for k, d in edge_data.items():
                                if isinstance(d, dict) and d.get("relation_type") == relation_type.value:
                                    queue.append((neighbor, depth + 1))
                    else:
                        queue.append((neighbor, depth + 1))

        return results

    def find_path(self, source_id: str, target_id: str, max_length: int = 5) -> list[list[str]]:
        with self._lock:
            try:
                paths = list(nx.all_simple_paths(self._graph, source_id, target_id, cutoff=max_length))
                return paths
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                return []

    # ── Gap analysis ──────────────────────────────────────────────────────

    def find_data_gaps(self) -> list[dict[str, Any]]:
        """Identify missing combinations of materials, modes, and properties."""
        gaps: list[dict[str, Any]] = []

        materials = self.find_entities(entity_type=EntityType.MATERIAL)
        modes = self.find_entities(entity_type=EntityType.MODE)
        properties = self.find_entities(entity_type=EntityType.PROPERTY)

        for mat in materials:
            mat_relations = self.get_relations(entity_id=mat.id)
            mat_modes = {r.target_id for r in mat_relations if r.type == RelationType.HAS_MODE}
            mat_props = {r.target_id for r in mat_relations if r.type == RelationType.HAS_PROPERTY}

            for mode in modes:
                if mode.id not in mat_modes:
                    gaps.append({
                        "type": "missing_mode",
                        "material": mat.name,
                        "material_id": mat.id,
                        "missing": mode.name,
                        "mode_id": mode.id,
                        "description": f"No experiment found for {mat.name} under mode {mode.name}",
                    })

            for prop in properties:
                if prop.id not in mat_props:
                    gaps.append({
                        "type": "missing_property",
                        "material": mat.name,
                        "material_id": mat.id,
                        "missing": prop.name,
                        "property_id": prop.id,
                        "description": f"Property {prop.name} not measured for {mat.name}",
                    })

        return gaps

    # ── Serialization ─────────────────────────────────────────────────────

    def to_json(self) -> str:
        with self._lock:
            data: dict[str, Any] = {
                "entities": [],
                "relations": [],
            }
            for node_id, node_data in self._graph.nodes(data=True):
                data["entities"].append({
                    "id": node_id,
                    "type": node_data.get("entity_type", "material"),
                    "name": node_data.get("name", ""),
                    "aliases": node_data.get("aliases", []),
                    "properties": node_data.get("properties", {}),
                    "source": node_data.get("source"),
                    "confidence": node_data.get("confidence", 1.0),
                })
            for u, v, edge_data in self._graph.edges(data=True):
                data["relations"].append({
                    "source_id": u,
                    "target_id": v,
                    "type": edge_data.get("relation_type", "depends_on"),
                    "properties": edge_data.get("properties", {}),
                    "source": edge_data.get("source"),
                    "confidence": edge_data.get("confidence", 1.0),
                })
            return json.dumps(data, ensure_ascii=False, indent=2)

    def from_json(self, json_str: str) -> int:
        """Load graph from JSON. Returns number of entities loaded."""
        data = json.loads(json_str)
        count = 0
        for ent in data.get("entities", []):
            self.add_entity(
                GraphEntity(
                    id=ent["id"],
                    type=EntityType(ent["type"]),
                    name=ent["name"],
                    aliases=ent.get("aliases", []),
                    properties=ent.get("properties", {}),
                    source=ent.get("source"),
                    confidence=ent.get("confidence", 1.0),
                )
            )
            count += 1
        for rel in data.get("relations", []):
            self.add_relation(
                GraphRelation(
                    source_id=rel["source_id"],
                    target_id=rel["target_id"],
                    type=RelationType(rel["type"]),
                    properties=rel.get("properties", {}),
                    source=rel.get("source"),
                    confidence=rel.get("confidence", 1.0),
                )
            )
        return count

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.write_text(self.to_json(), encoding="utf-8")
        logger.info("Graph saved to %s (%d entities, %d relations)", path, self.count_entities(), self.count_relations())

    @classmethod
    def load(cls, path: str | Path) -> GraphStore:
        store = cls()
        data = Path(path).read_text(encoding="utf-8")
        count = store.from_json(data)
        logger.info("Graph loaded from %s (%d entities)", path, count)
        return store

    # ── Stats ─────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        with self._lock:
            by_type: dict[str, int] = {}
            for et in EntityType:
                by_type[et.value] = sum(
                    1 for _, d in self._graph.nodes(data=True)
                    if d.get("entity_type") == et.value
                )
            return {
                "entities": self._graph.number_of_nodes(),
                "relations": self._graph.number_of_edges(),
                "by_type": by_type,
            }
