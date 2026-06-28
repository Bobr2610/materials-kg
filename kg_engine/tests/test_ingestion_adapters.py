from __future__ import annotations

from kg_engine.domain.models import EntityKind
from kg_engine.ingestion.adapters import DocumentCorpusAdapter
from kg_engine.ingestion.adapters import ExperimentCatalogAdapter
from kg_engine.ingestion.adapters import ReferenceDataAdapter
from kg_engine.ingestion.adapters import StaffDirectoryAdapter
from kg_engine.ingestion.adapters import TagCatalogAdapter


def test_reference_data_adapter_maps_sections_to_entity_kinds() -> None:
    adapter = ReferenceDataAdapter()
    batch = adapter.from_payload(
        {
            "materials": [{"name": "Ti-6Al-4V", "aliases": ["Ti6Al4V"]}],
            "equipment": [{"name": "SEM"}],
            "coverage_rules": [
                {
                    "rule_id": "r1",
                    "name": "matrix",
                    "material_names": ["Ti-6Al-4V"],
                    "mode_names": ["Annealing"],
                    "property_names": ["Hardness"],
                }
            ],
        }
    )

    assert len(batch.entities) == 2
    assert batch.entities[0].kind == EntityKind.MATERIAL
    assert batch.entities[1].kind == EntityKind.EQUIPMENT
    assert len(batch.coverage_rules) == 1


def test_reference_adapter_accepts_generic_entities_with_explicit_kind() -> None:
    batch = ReferenceDataAdapter().from_payload(
        {
            "entities": [
                {
                    "kind": "material",
                    "name": "Сплав 42",
                    "aliases": "alloy-42; sample-42",
                    "плотность": "7.8",
                },
                {
                    "entity_kind": "equipment",
                    "name": "Установка испытаний",
                    "лаборатория": "Лаборатория A",
                },
            ]
        }
    )

    assert [entity.kind for entity in batch.entities] == [
        EntityKind.MATERIAL,
        EntityKind.EQUIPMENT,
    ]
    assert batch.entities[0].aliases == ["alloy-42", "sample-42"]
    assert batch.entities[0].properties["плотность"] == "7.8"
    assert batch.entities[1].properties["лаборатория"] == "Лаборатория A"


def test_reference_adapter_does_not_guess_entity_kind_without_kind() -> None:
    batch = ReferenceDataAdapter().from_payload(
        {"entities": [{"name": "Неизвестная строка", "значение": "42"}]}
    )

    assert batch.entities == []


def test_experiment_catalog_adapter_builds_observations_and_findings() -> None:
    adapter = ExperimentCatalogAdapter()
    experiments = adapter.from_payload(
        [
            {
                "experiment_id": "exp-1",
                "title": "Trial",
                "material_name": "Ti-6Al-4V",
                "observations": [{"property_name": "Hardness", "value": 35.0}],
                "findings": [{"summary": "Hardness retained"}],
            }
        ]
    )

    assert len(experiments) == 1
    assert experiments[0].observations[0].property_name == "Hardness"
    assert experiments[0].findings[0].summary == "Hardness retained"


def test_experiment_adapter_accepts_flat_rows_and_preserves_unknown_columns() -> None:
    experiments = ExperimentCatalogAdapter().from_payload(
        [
            {
                "id": "exp-flat-1",
                "name": "Плоская строка",
                "material": "Сплав 42",
                "mode": "режим-А",
                "property": "прочность",
                "value": "123,5",
                "unit": "MPa",
                "оператор": "Иванов",
            }
        ]
    )

    assert len(experiments) == 1
    assert experiments[0].experiment_id == "exp-flat-1"
    assert experiments[0].material_name == "Сплав 42"
    assert experiments[0].observations[0].property_name == "прочность"
    assert experiments[0].observations[0].value == 123.5


def test_document_adapter_builds_findings_and_text_units() -> None:
    adapter = DocumentCorpusAdapter()
    documents = adapter.from_payload(
        [
            {
                "document_id": "doc-1",
                "title": "Report",
                "text": "full body",
                "material_names": ["Al6061"],
                "findings": [{"summary": "Useful result"}],
                "text_units": [{"content": "chunk body"}],
            }
        ]
    )

    assert len(documents) == 1
    assert documents[0].material_names == ["Al6061"]
    assert documents[0].text_units[0].content == "chunk body"


def test_directory_and_tag_adapters_create_reference_batches() -> None:
    staff_batch = StaffDirectoryAdapter().from_payload(
        [{"name": "Lab A", "members": ["Alice", "Bob"]}]
    )
    tag_batch = TagCatalogAdapter().from_payload([{"name": "fatigue"}])

    assert staff_batch.entities[0].kind == EntityKind.TEAM
    assert staff_batch.entities[0].properties["members"] == ["Alice", "Bob"]
    assert tag_batch.entities[0].kind == EntityKind.TAG
