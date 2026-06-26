"""Tests for knowledge graph schemas, store, query, and extraction."""

from __future__ import annotations

from kg_engine.graph.schemas import EntityType, GraphEntity, GraphRelation, RelationType
from kg_engine.graph.store import GraphStore


class TestEntityType:
    def test_enum_values(self) -> None:
        assert EntityType.MATERIAL.value == "material"
        assert EntityType.PROPERTY.value == "property"
        assert EntityType.EXPERIMENT.value == "experiment"
        assert EntityType.MODE.value == "mode"
        assert EntityType.EQUIPMENT.value == "equipment"
        assert EntityType.TEAM.value == "team"
        assert EntityType.ARTICLE.value == "article"
        assert EntityType.CONCLUSION.value == "conclusion"


class TestRelationType:
    def test_enum_values(self) -> None:
        assert RelationType.HAS_PROPERTY.value == "has_property"
        assert RelationType.USED_IN.value == "used_in"
        assert RelationType.MEASURES.value == "measures"


class TestGraphEntity:
    def test_minimal_entity(self) -> None:
        e = GraphEntity(id="mat_1", type=EntityType.MATERIAL, name="Ti6Al4V")
        assert e.id == "mat_1"
        assert e.type == EntityType.MATERIAL
        assert e.name == "Ti6Al4V"
        assert e.aliases == []
        assert e.properties == {}
        assert e.source is None
        assert e.confidence == 1.0

    def test_full_entity(self) -> None:
        e = GraphEntity(
            id="mat_2",
            type=EntityType.MATERIAL,
            name="Al6061",
            aliases=["Al-Mg-Si", "6061"],
            properties={"density": 2.7},
            source="doc_123",
            confidence=0.85,
        )
        assert e.aliases == ["Al-Mg-Si", "6061"]
        assert e.properties == {"density": 2.7}
        assert e.source == "doc_123"
        assert e.confidence == 0.85

    def test_confidence_bounds(self) -> None:
        e = GraphEntity(id="e1", type=EntityType.MATERIAL, name="test", confidence=0.99)
        assert 0.0 <= e.confidence <= 1.0


class TestGraphRelation:
    def test_minimal_relation(self) -> None:
        r = GraphRelation(
            source_id="mat_1",
            target_id="prop_1",
            type=RelationType.HAS_PROPERTY,
        )
        assert r.source_id == "mat_1"
        assert r.target_id == "prop_1"
        assert r.type == RelationType.HAS_PROPERTY

    def test_relation_with_value(self) -> None:
        r = GraphRelation(
            source_id="mat_1",
            target_id="prop_1",
            type=RelationType.HAS_PROPERTY,
            properties={"value": "500", "unit": "MPa"},
            source="exp_1",
            confidence=0.9,
        )
        assert r.properties["value"] == "500"
        assert r.properties["unit"] == "MPa"


class TestGraphStore:
    def test_add_and_get_entity(self) -> None:
        store = GraphStore()
        entity = GraphEntity(id="mat_1", type=EntityType.MATERIAL, name="Ti6Al4V")
        store.add_entity(entity)
        retrieved = store.get_entity("mat_1")
        assert retrieved is not None
        assert retrieved.name == "Ti6Al4V"
        assert retrieved.type == EntityType.MATERIAL

    def test_get_nonexistent_entity(self) -> None:
        store = GraphStore()
        assert store.get_entity("nonexistent") is None

    def test_remove_entity(self) -> None:
        store = GraphStore()
        entity = GraphEntity(id="mat_1", type=EntityType.MATERIAL, name="Ti6Al4V")
        store.add_entity(entity)
        assert store.remove_entity("mat_1") is True
        assert store.get_entity("mat_1") is None

    def test_remove_nonexistent(self) -> None:
        store = GraphStore()
        assert store.remove_entity("nonexistent") is False

    def test_find_entities_by_type(self) -> None:
        store = GraphStore()
        store.add_entity(GraphEntity(id="m1", type=EntityType.MATERIAL, name="Al"))
        store.add_entity(GraphEntity(id="p1", type=EntityType.PROPERTY, name="strength"))
        materials = store.find_entities(entity_type=EntityType.MATERIAL)
        assert len(materials) == 1
        assert materials[0].name == "Al"

    def test_find_entities_by_name(self) -> None:
        store = GraphStore()
        store.add_entity(GraphEntity(id="m1", type=EntityType.MATERIAL, name="Ti6Al4V"))
        store.add_entity(GraphEntity(id="m2", type=EntityType.MATERIAL, name="Al6061"))
        results = store.find_entities(name_contains="Ti")
        assert len(results) == 1
        assert results[0].name == "Ti6Al4V"

    def test_add_and_get_relation(self) -> None:
        store = GraphStore()
        store.add_entity(GraphEntity(id="mat_1", type=EntityType.MATERIAL, name="Ti6Al4V"))
        store.add_entity(GraphEntity(id="prop_1", type=EntityType.PROPERTY, name="strength"))
        relation = GraphRelation(
            source_id="mat_1",
            target_id="prop_1",
            type=RelationType.HAS_PROPERTY,
            properties={"value": "950", "unit": "MPa"},
        )
        store.add_relation(relation)
        relations = store.get_relations(entity_id="mat_1")
        assert len(relations) == 1
        assert relations[0].type == RelationType.HAS_PROPERTY
        assert relations[0].properties["value"] == "950"

    def test_get_neighbors(self) -> None:
        store = GraphStore()
        store.add_entity(GraphEntity(id="mat_1", type=EntityType.MATERIAL, name="Ti6Al4V"))
        store.add_entity(GraphEntity(id="prop_1", type=EntityType.PROPERTY, name="strength"))
        store.add_entity(GraphEntity(id="exp_1", type=EntityType.EXPERIMENT, name="tensile_test"))
        store.add_relation(GraphRelation(source_id="mat_1", target_id="prop_1", type=RelationType.HAS_PROPERTY))
        store.add_relation(GraphRelation(source_id="mat_1", target_id="exp_1", type=RelationType.USED_IN))
        neighbors = store.get_neighbors("mat_1")
        assert len(neighbors) == 2
        names = {n.name for n in neighbors}
        assert "strength" in names
        assert "tensile_test" in names

    def test_find_path(self) -> None:
        store = GraphStore()
        store.add_entity(GraphEntity(id="a", type=EntityType.MATERIAL, name="A"))
        store.add_entity(GraphEntity(id="b", type=EntityType.MODE, name="B"))
        store.add_entity(GraphEntity(id="c", type=EntityType.PROPERTY, name="C"))
        store.add_relation(GraphRelation(source_id="a", target_id="b", type=RelationType.HAS_MODE))
        store.add_relation(GraphRelation(source_id="b", target_id="c", type=RelationType.DEPENDS_ON))
        paths = store.find_path("a", "c")
        assert len(paths) == 1
        assert paths[0] == ["a", "b", "c"]

    def test_count_entities(self) -> None:
        store = GraphStore()
        assert store.count_entities() == 0
        store.add_entity(GraphEntity(id="m1", type=EntityType.MATERIAL, name="Al"))
        store.add_entity(GraphEntity(id="m2", type=EntityType.MATERIAL, name="Fe"))
        store.add_entity(GraphEntity(id="p1", type=EntityType.PROPERTY, name="strength"))
        assert store.count_entities() == 3
        assert store.count_entities(EntityType.MATERIAL) == 2
        assert store.count_entities(EntityType.PROPERTY) == 1

    def test_count_relations(self) -> None:
        store = GraphStore()
        store.add_entity(GraphEntity(id="m1", type=EntityType.MATERIAL, name="Al"))
        store.add_entity(GraphEntity(id="p1", type=EntityType.PROPERTY, name="strength"))
        store.add_relation(GraphRelation(source_id="m1", target_id="p1", type=RelationType.HAS_PROPERTY))
        assert store.count_relations() == 1

    def test_serialization_roundtrip(self) -> None:
        store = GraphStore()
        store.add_entity(GraphEntity(id="m1", type=EntityType.MATERIAL, name="Al6061"))
        store.add_entity(GraphEntity(id="p1", type=EntityType.PROPERTY, name="yield_strength"))
        store.add_relation(GraphRelation(
            source_id="m1", target_id="p1", type=RelationType.HAS_PROPERTY,
            properties={"value": "276", "unit": "MPa"},
        ))
        json_str = store.to_json()
        store2 = GraphStore()
        count = store2.from_json(json_str)
        assert count == 2
        assert store2.count_entities() == 2
        assert store2.count_relations() == 1
        retrieved = store2.get_entity("m1")
        assert retrieved is not None
        assert retrieved.name == "Al6061"

    def test_stats(self) -> None:
        store = GraphStore()
        store.add_entity(GraphEntity(id="m1", type=EntityType.MATERIAL, name="Al"))
        store.add_entity(GraphEntity(id="p1", type=EntityType.PROPERTY, name="strength"))
        stats = store.stats()
        assert stats["entities"] == 2
        assert stats["relations"] == 0
        assert stats["by_type"]["material"] == 1
        assert stats["by_type"]["property"] == 1


class TestKnowledgeGraphQuery:
    def test_query_by_material_and_mode(self) -> None:
        from kg_engine.graph.query import KnowledgeGraphQuery

        store = GraphStore()
        store.add_entity(GraphEntity(id="mat_1", type=EntityType.MATERIAL, name="Ti6Al4V"))
        store.add_entity(GraphEntity(id="mode_1", type=EntityType.MODE, name="annealing"))
        store.add_entity(GraphEntity(id="prop_1", type=EntityType.PROPERTY, name="hardness"))
        store.add_relation(GraphRelation(source_id="mat_1", target_id="mode_1", type=RelationType.HAS_MODE))
        store.add_relation(GraphRelation(
            source_id="mat_1", target_id="prop_1", type=RelationType.HAS_PROPERTY,
            properties={"value": "36", "unit": "HRC"},
        ))

        query = KnowledgeGraphQuery(store)
        results = query.query_by_material_and_mode("Ti6Al4V")
        assert len(results) == 1
        assert results[0]["material"] == "Ti6Al4V"
        assert len(results[0]["modes"]) == 1
        assert results[0]["modes"][0]["name"] == "annealing"
        assert len(results[0]["properties"]) == 1
        assert results[0]["properties"][0]["name"] == "hardness"
        assert results[0]["properties"][0]["value"] == "36"

    def test_query_by_property(self) -> None:
        from kg_engine.graph.query import KnowledgeGraphQuery

        store = GraphStore()
        store.add_entity(GraphEntity(id="mat_1", type=EntityType.MATERIAL, name="Al6061"))
        store.add_entity(GraphEntity(id="prop_1", type=EntityType.PROPERTY, name="tensile_strength"))
        store.add_relation(GraphRelation(
            source_id="mat_1", target_id="prop_1", type=RelationType.HAS_PROPERTY,
            properties={"value": "310", "unit": "MPa"},
        ))

        query = KnowledgeGraphQuery(store)
        results = query.query_by_property("tensile_strength")
        assert len(results) == 1
        assert results[0]["material"] == "Al6061"
        assert results[0]["value"] == "310"

    def test_query_related(self) -> None:
        from kg_engine.graph.query import KnowledgeGraphQuery

        store = GraphStore()
        store.add_entity(GraphEntity(id="mat_1", type=EntityType.MATERIAL, name="Ti6Al4V"))
        store.add_entity(GraphEntity(id="exp_1", type=EntityType.EXPERIMENT, name="fatigue_test"))
        store.add_relation(GraphRelation(source_id="mat_1", target_id="exp_1", type=RelationType.USED_IN))

        query = KnowledgeGraphQuery(store)
        results = query.query_related("Ti6Al4V")
        assert len(results) == 1
        assert len(results[0]["neighbors"]) == 1
        assert results[0]["neighbors"][0]["name"] == "fatigue_test"


class TestEntityExtractor:
    def test_extract_regex_materials(self) -> None:
        from kg_engine.graph.extractor import EntityExtractor

        extractor = EntityExtractor()
        entities = extractor.extract_regex("Sample of Ti6Al4V and Al2O3 were tested")
        names = {e.name for e in entities}
        assert "Ti6Al4V" in names
        assert "Al2O3" in names

    def test_extract_regex_properties(self) -> None:
        from kg_engine.graph.extractor import EntityExtractor

        extractor = EntityExtractor()
        entities = extractor.extract_regex(
            "The tensile strength and hardness were measured"
        )
        names = {e.name for e in entities}
        assert "tensile strength" in names or "tensile_strength" in names

    def test_extract_russian_properties(self) -> None:
        from kg_engine.graph.extractor import EntityExtractor

        extractor = EntityExtractor()
        entities = extractor.extract_regex(
            "Измеряли прочность и твердость образцов"
        )
        names = {e.name for e in entities}
        assert "прочность" in names or "твердость" in names
