"""Knowledge graph query engine for materials science questions."""

from __future__ import annotations

import logging
from typing import Any

from kg_engine.graph.schemas import (
    EntityType,
    GraphEntity,
    RelationType,
)
from kg_engine.graph.store import GraphStore

logger = logging.getLogger(__name__)


class KnowledgeGraphQuery:
    """High-level query interface for the materials knowledge graph."""

    def __init__(self, store: GraphStore) -> None:
        self._store = store

    def query_by_property(
        self,
        property_name: str,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        prop_entities = self._store.find_entities(
            entity_type=EntityType.PROPERTY,
            name_contains=property_name,
        )
        for prop in prop_entities:
            relations = self._store.get_relations(entity_id=prop.id, relation_type=RelationType.HAS_PROPERTY)
            for rel in relations:
                val = rel.properties.get("value")
                if val is not None:
                    try:
                        num_val = float(val)
                        if min_value is not None and num_val < min_value:
                            continue
                        if max_value is not None and num_val > max_value:
                            continue
                    except (ValueError, TypeError):
                        logger.warning("Could not convert property value '%s' to float for '%s'", val, prop.name)
                material = self._store.get_entity(rel.source_id)
                results.append({
                    "material": material.name if material else rel.source_id,
                    "property": prop.name,
                    "value": rel.properties.get("value"),
                    "unit": rel.properties.get("unit"),
                    "source": rel.source,
                    "confidence": rel.confidence,
                })
        return results

    def query_by_material_and_mode(
        self,
        material_name: str,
        mode_name: str | None = None,
    ) -> list[dict[str, Any]]:
        materials = self._store.find_entities(
            entity_type=EntityType.MATERIAL,
            name_contains=material_name,
        )
        if not materials:
            return []

        results: list[dict[str, Any]] = []
        for mat in materials:
            mat_data: dict[str, Any] = {
                "material": mat.name,
                "material_id": mat.id,
                "modes": [],
                "properties": [],
                "experiments": [],
            }
            relations = self._store.get_relations(entity_id=mat.id)

            for rel in relations:
                if rel.type == RelationType.HAS_MODE:
                    mode_entity = self._store.get_entity(rel.target_id)
                    if mode_name and mode_entity and mode_name.lower() not in mode_entity.name.lower():
                        continue
                    mat_data["modes"].append({
                        "name": mode_entity.name if mode_entity else rel.target_id,
                        "source": rel.source,
                    })

                elif rel.type == RelationType.HAS_PROPERTY:
                    prop_entity = self._store.get_entity(rel.target_id)
                    if prop_entity:
                        mat_data["properties"].append({
                            "name": prop_entity.name,
                            "value": rel.properties.get("value"),
                            "unit": rel.properties.get("unit"),
                            "source": rel.source,
                        })

                elif rel.type == RelationType.USED_IN:
                    exp_entity = self._store.get_entity(rel.target_id)
                    if exp_entity:
                        exp_info: dict[str, Any] = {
                            "name": exp_entity.name,
                            "experiment_id": exp_entity.id,
                            "source": rel.source,
                        }
                        exp_relations = self._store.get_relations(entity_id=exp_entity.id)
                        for er in exp_relations:
                            if er.type == RelationType.MEASURES:
                                p = self._store.get_entity(er.target_id)
                                if p:
                                    exp_info.setdefault("measured_properties", []).append({
                                        "name": p.name,
                                        "value": er.properties.get("value"),
                                        "unit": er.properties.get("unit"),
                                    })
                            elif er.type == RelationType.HAS_CONCLUSION:
                                c = self._store.get_entity(er.target_id)
                                if c:
                                    exp_info.setdefault("conclusions", []).append({
                                        "text": c.name,
                                        "source": er.source,
                                    })
                        mat_data["experiments"].append(exp_info)

            if not mode_name or mat_data["modes"]:
                results.append(mat_data)

        return results

    def query_related(
        self,
        entity_name: str,
        relation_type: RelationType | None = None,
        max_depth: int = 2,
    ) -> list[dict[str, Any]]:
        entities = self._store.find_entities(name_contains=entity_name)
        if not entities:
            return []

        results: list[dict[str, Any]] = []
        seen: set[str] = set()

        for entity in entities:
            if entity.id in seen:
                continue
            seen.add(entity.id)

            entry: dict[str, Any] = {
                "entity": entity.name,
                "type": entity.type.value,
                "neighbors": [],
            }

            neighbors = self._store.get_neighbors(entity.id, max_depth=1)
            for neighbor in neighbors:
                if neighbor.id in seen:
                    continue
                rels = self._store.get_relations(entity_id=entity.id)
                link_type = None
                for r in rels:
                    if r.target_id == neighbor.id or r.source_id == neighbor.id:
                        link_type = r.type.value
                        break
                entry["neighbors"].append({
                    "name": neighbor.name,
                    "type": neighbor.type.value,
                    "relation": link_type,
                })

            results.append(entry)

        return results

    def find_data_gaps(self) -> list[dict[str, Any]]:
        return self._store.find_data_gaps()

    def stats(self) -> dict[str, Any]:
        return self._store.stats()
