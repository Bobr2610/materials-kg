from __future__ import annotations

import json

from fastapi.testclient import TestClient

from kg_engine.api.materials_core import create_materials_app
from kg_engine.repositories.memory import InMemoryMaterialsKGRepository
from kg_engine.services.materials_kg import MaterialsKGService


def test_materials_api_health_and_ingest_query_flow() -> None:
    app = create_materials_app(
        service=MaterialsKGService(InMemoryMaterialsKGRepository())
    )
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    reference = client.post(
        "/ingest/reference",
        json={
            "entities": [
                {"kind": "material", "name": "Ti-6Al-4V", "aliases": ["Ti6Al4V"]},
                {"kind": "mode", "name": "Annealing"},
                {"kind": "property", "name": "Hardness"},
            ]
        },
    )
    assert reference.status_code == 200

    experiments = client.post(
        "/ingest/experiments",
        json=[
            {
                "experiment_id": "exp-api",
                "title": "API trial",
                "material_name": "Ti6Al4V",
                "mode_name": "Annealing",
                "observations": [
                    {"property_name": "Hardness", "value": 35.0, "unit": "HRC"}
                ],
            }
        ],
    )
    assert experiments.status_code == 200

    query = client.post(
        "/query/material-mode",
        json={"material": "Ti-6Al-4V", "mode": "Annealing"},
    )
    assert query.status_code == 200
    body = query.json()
    assert body["material"]["canonical_name"] == "Ti-6Al-4V"
    assert len(body["observations"]) == 1


def test_dashboard_and_sample_data_flow() -> None:
    app = create_materials_app(
        service=MaterialsKGService(InMemoryMaterialsKGRepository())
    )
    client = TestClient(app)

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Источники" in dashboard.text
    assert "Чат" in dashboard.text
    assert "Добавить источники" in dashboard.text
    assert "/ingest/upload" in dashboard.text
    assert "Введите текст" in dashboard.text

    ref_json = json.dumps({
        "entities": [
            {"kind": "material", "name": "Ti-6Al-4V", "aliases": ["Ti6Al4V"]},
            {"kind": "mode", "name": "Annealed"},
            {"kind": "property", "name": "Tensile Strength"},
        ]
    }).encode()
    exp_json = json.dumps([
        {
            "experiment_id": "exp-ui",
            "title": "UI test",
            "material_name": "Ti6Al4V",
            "mode_name": "Annealed",
            "observations": [
                {"property_name": "Tensile Strength", "value": 950.0, "unit": "MPa"}
            ],
        }
    ]).encode()
    upload = client.post(
        "/ingest/upload",
        files=[
            ("files", ("ref.json", ref_json, "application/json")),
            ("files", ("exp.json", exp_json, "application/json")),
        ],
    )
    assert upload.status_code == 200
    assert upload.json()["uploaded"]

    query = client.post(
        "/query/answer",
        json={
            "question": "Что уже делали по Ti-6Al-4V после Annealed и как менялась Tensile Strength?",
        },
    )
    assert query.status_code == 200
    body = query.json()
    assert body["answer"]
    assert body["matched_entities"]


def test_free_question_material_and_property_fallbacks() -> None:
    app = create_materials_app(
        service=MaterialsKGService(InMemoryMaterialsKGRepository())
    )
    client = TestClient(app)

    import io
    reference_json = json.dumps({
        "entities": [
            {"kind": "material", "name": "IN718", "aliases": ["Inconel 718"]},
            {"kind": "property", "name": "Hardness"},
            {"kind": "mode", "name": "Aged"},
        ]
    }).encode()
    experiments_json = json.dumps([
        {
            "experiment_id": "exp-in718",
            "title": "IN718 test",
            "material_name": "IN718",
            "mode_name": "Aged",
            "observations": [
                {"property_name": "Hardness", "value": 42.0, "unit": "HRC"}
            ],
        }
    ]).encode()

    upload = client.post(
        "/ingest/upload",
        files=[
            ("files", ("reference.json", reference_json, "application/json")),
            ("files", ("experiments.json", experiments_json, "application/json")),
        ],
    )
    assert upload.status_code == 200

    material_only = client.post(
        "/query/answer",
        json={"question": "Расскажи что известно про IN718"},
    )
    assert material_only.status_code == 200
    assert material_only.json()["resolved_query"]["material"] == "IN718"
    assert material_only.json()["answer"]

    property_only = client.post(
        "/query/answer",
        json={"question": "Какие результаты есть по Hardness?"},
    )
    assert property_only.status_code == 200
    assert property_only.json()["resolved_query"]["property_name"] == "Hardness"
    assert property_only.json()["observations"]

    unknown = client.post(
        "/query/answer",
        json={"question": "Какие результаты есть по совершенно неизвестному объекту?"},
    )
    assert unknown.status_code == 200
    assert unknown.json()["warnings"]


def test_llm_extraction_and_answer_generation() -> None:
    from unittest.mock import MagicMock

    mock_llm = MagicMock()
    mock_llm.embed.return_value = [[0.1] * 128]
    mock_llm.chat_json.return_value = {
        "entities": [
            {"kind": "material", "name": "Ti-6Al-4V", "aliases": ["Ti64"], "properties": {"density": "4.43 g/cm3"}},
            {"kind": "property", "name": "Tensile Strength", "aliases": ["UTS"], "properties": {}},
        ],
        "experiments": [
            {
                "experiment_id": "LLM-EXP-001",
                "title": "Tensile test of Ti64",
                "material_name": "Ti-6Al-4V",
                "mode_name": "Annealed",
                "observations": [
                    {"property_name": "Tensile Strength", "value": 950, "unit": "MPa", "confidence": 0.9}
                ],
                "findings": [{"summary": "Annealed Ti64 shows good ductility", "confidence": 0.85}],
            }
        ],
        "relationships": [],
    }
    mock_llm.chat.return_value = (
        "По данным графа: для Ti-6Al-4V в режиме Annealed найден эксперимент LLM-EXP-001 "
        "с измерением Tensile Strength = 950 MPa. Вывод: отожженный сплав показывает хорошую пластичность."
    )

    repo = InMemoryMaterialsKGRepository()
    service = MaterialsKGService(repo, llm_provider=mock_llm)
    app = create_materials_app(service=service)
    client = TestClient(app)

    doc_text = (
        "Titanium alloy Ti-6Al-4V was tested in annealed condition. "
        "Tensile strength measured at 950 MPa with elongation 14%. "
        "The alloy shows excellent ductility after annealing at 700C for 2 hours."
    )
    upload = client.post(
        "/ingest/upload",
        files=[("files", ("test_doc.txt", doc_text.encode(), "text/plain"))],
    )
    assert upload.status_code == 200
    assert mock_llm.chat_json.called
    assert mock_llm.embed.called

    overview = client.get("/source/overview").json()
    assert overview["total_entities"] > 0

    answer_resp = client.post(
        "/query/answer",
        json={"question": "Какие свойства измеряли для Ti-6Al-4V?"},
    )
    assert answer_resp.status_code == 200
    body = answer_resp.json()
    assert body["answer"]
    assert "950" in body["answer"] or "Tensile" in body["answer"]
