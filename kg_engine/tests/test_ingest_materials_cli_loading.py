from __future__ import annotations

import json

from kg_engine.ingestion.adapters import DocumentCorpusAdapter
from kg_engine.ingestion.adapters import ExperimentCatalogAdapter
from kg_engine.ingestion.adapters import ReferenceDataAdapter
from kg_engine.repositories.memory import InMemoryMaterialsKGRepository
from kg_engine.scripts.ingest_materials_kg import _load_bundle
from kg_engine.scripts.ingest_materials_kg import _load_payload
from kg_engine.services.materials_kg import MaterialsKGService


def test_load_payload_accepts_directory_with_mixed_reference_files(tmp_path) -> None:
    (tmp_path / "anything.csv").write_text(
        "kind,name,aliases,поставщик\n"
        "material,Сплав 42,alloy-42;sample-42,internal\n",
        encoding="utf-8",
    )
    (tmp_path / "more.jsonl").write_text(
        json.dumps({"entity_kind": "equipment", "name": "Печь 1"}) + "\n",
        encoding="utf-8",
    )

    payload = _load_payload(str(tmp_path), family="reference")

    assert isinstance(payload, dict)
    assert len(payload["entities"]) == 2
    assert payload["entities"][0]["поставщик"] == "internal"


def test_load_payload_accepts_plain_markdown_documents(tmp_path) -> None:
    (tmp_path / "report.md").write_text(
        "# Отчет по испытаниям\n\nТекст внутреннего документа.",
        encoding="utf-8",
    )

    payload = _load_payload(str(tmp_path), family="documents")

    assert isinstance(payload, list)
    assert payload[0]["title"] == "Отчет по испытаниям"
    assert "Текст внутреннего документа" in payload[0]["text"]


def test_reference_loader_does_not_classify_rows_without_explicit_kind(tmp_path) -> None:
    (tmp_path / "unknown.csv").write_text(
        "название,значение\n"
        "Что-то,42\n",
        encoding="utf-8",
    )

    payload = _load_payload(str(tmp_path), family="reference")

    assert isinstance(payload, dict)
    assert payload.get("entities", []) == []


def test_load_bundle_ingests_mixed_files_and_preserves_unknown_rows(tmp_path) -> None:
    (tmp_path / "001.csv").write_text(
        "kind,name,aliases,поставщик\n"
        "material,Сплав 42,alloy-42;sample-42,internal\n",
        encoding="utf-8",
    )
    (tmp_path / "abc.jsonl").write_text(
        json.dumps(
            {
                "id": "exp-42",
                "name": "Испытание",
                "material": "Сплав 42",
                "mode": "Режим A",
                "property": "Прочность",
                "value": "123,5",
                "unit": "MPa",
                "оператор": "Иванов",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "q.csv").write_text(
        "непонятная_колонка,значение\n"
        "непонятная строка,42\n",
        encoding="utf-8",
    )
    (tmp_path / "whatever.md").write_text(
        "# Свободный отчет\n\nСвободный текст без специального имени файла.",
        encoding="utf-8",
    )

    bundle = _load_bundle(str(tmp_path))

    reference_batch = ReferenceDataAdapter().from_payload(bundle["reference"])
    experiments = ExperimentCatalogAdapter().from_payload(bundle["experiments"])
    documents = DocumentCorpusAdapter().from_payload(bundle["documents"])

    assert len(reference_batch.entities) == 1
    assert len(experiments) == 1
    assert experiments[0].metadata["оператор"] == "Иванов"
    assert len(documents) == 2
    assert any(
        document.metadata["ingestion_role"] == "unclassified_source_preserved"
        for document in documents
    )

    service = MaterialsKGService(InMemoryMaterialsKGRepository())
    service.ingest_reference_data(reference_batch)
    service.ingest_experiments(experiments)
    service.ingest_documents(documents)

    result = service.query_material_mode("Сплав 42", "Режим A", "Прочность")
    assert result.experiments
    assert result.observations[0].value == 123.5
    related = service.query_related("Сплав 42", depth=2)
    assert related.relations
