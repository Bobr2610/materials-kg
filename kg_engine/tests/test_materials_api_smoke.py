from __future__ import annotations

import json

from fastapi.testclient import TestClient

from kg_engine.api.materials_core import create_materials_app
from kg_engine.config.settings import Settings
from kg_engine.repositories.memory import InMemoryMaterialsKGRepository
from kg_engine.services.materials_kg import MaterialsKGService


def deterministic_settings() -> Settings:
    return Settings(
        materials_hypothesis_engine="deterministic",
        materials_enable_destructive_api=False,
    )


def test_materials_api_health_and_ingest_query_flow() -> None:
    app = create_materials_app(
        settings=deterministic_settings(),
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
    from unittest.mock import MagicMock

    mock_llm = MagicMock()
    mock_llm.chat.return_value = "Найдены данные по Ti-6Al-4V: Tensile Strength 950 MPa."
    mock_llm.chat_json.side_effect = [
        {
            "reference": {
                "entities": [
                    {
                        "kind": "material",
                        "name": "Ti-6Al-4V",
                        "aliases": ["Ti6Al4V"],
                    },
                    {"kind": "mode", "name": "Annealed"},
                    {"kind": "property", "name": "Tensile Strength"},
                ]
            },
            "experiments": [],
            "documents": [],
        },
        {
            "reference": {},
            "experiments": [
                {
                    "experiment_id": "exp-ui",
                    "title": "UI test",
                    "material_name": "Ti6Al4V",
                    "mode_name": "Annealed",
                    "observations": [
                        {
                            "property_name": "Tensile Strength",
                            "value": 950.0,
                            "unit": "MPa",
                        }
                    ],
                }
            ],
            "documents": [],
        },
    ]

    app = create_materials_app(
        settings=deterministic_settings(),
        service=MaterialsKGService(
            InMemoryMaterialsKGRepository(),
            llm_provider=mock_llm,
        )
    )
    client = TestClient(app)

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Источники" in dashboard.text
    assert "Чат" in dashboard.text
    assert "Добавить источники" in dashboard.text
    assert "/ingest/upload" in dashboard.text
    assert "Введите текст" in dashboard.text
    assert 'id="collapseSources"' in dashboard.text
    assert 'id="restoreSources"' in dashboard.text
    assert 'id="menuButton"' in dashboard.text
    assert 'id="graphToggle"' in dashboard.text
    assert 'id="clearAllSources"' in dashboard.text
    assert 'id="clearChat"' in dashboard.text
    assert 'id="sourceSearch"' in dashboard.text
    assert 'id="sourceSummary"' in dashboard.text
    assert 'id="sourceNote"' in dashboard.text
    assert 'id="hypothesisPanel"' in dashboard.text
    assert 'id="targetKpi"' in dashboard.text
    assert 'id="generateHypotheses"' in dashboard.text
    assert "/hypotheses/generate" in dashboard.text
    assert "renderHypotheses" in dashboard.text
    assert "uploadBatchSize" in dashboard.text
    assert "graphDataUrl" in dashboard.text
    assert "renderSourceList" in dashboard.text
    assert "async function clearAllSources" in dashboard.text

    ref_json = json.dumps(
        {
            "entities": [
                {"kind": "material", "name": "Ti-6Al-4V", "aliases": ["Ti6Al4V"]},
                {"kind": "mode", "name": "Annealed"},
                {"kind": "property", "name": "Tensile Strength"},
            ]
        }
    ).encode()
    exp_json = json.dumps(
        [
            {
                "experiment_id": "exp-ui",
                "title": "UI test",
                "material_name": "Ti6Al4V",
                "mode_name": "Annealed",
                "observations": [
                    {"property_name": "Tensile Strength", "value": 950.0, "unit": "MPa"}
                ],
            }
        ]
    ).encode()
    upload = client.post(
        "/ingest/upload",
        files=[
            ("files", ("ref.json", ref_json, "application/json")),
            ("files", ("exp.json", exp_json, "application/json")),
        ],
    )
    assert upload.status_code == 200
    assert upload.json()["uploaded"]
    assert upload.json()["ingestion"]["llm_structured_files"] == [
        "ref.json",
        "exp.json",
    ]

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


def test_demo_load_sample_powers_notebook_ui_queries() -> None:
    app = create_materials_app(
        settings=deterministic_settings(),
        service=MaterialsKGService(InMemoryMaterialsKGRepository())
    )
    client = TestClient(app)

    sample = client.post("/demo/load-sample")
    assert sample.status_code == 200
    sample_body = sample.json()
    assert sample_body["reference"]["entities"] > 0
    assert sample_body["experiments"]["experiments"] > 0
    assert sample_body["documents"]["documents"] > 0
    assert len(sample_body["uploaded"]) == 3

    graph = client.get("/graph/data")
    assert graph.status_code == 200
    assert graph.json()["nodes"]
    assert graph.json()["edges"]

    answer = client.post(
        "/query/answer",
        json={"question": "Что делали по Ti-6Al-4V после Annealed?"},
    )
    assert answer.status_code == 200
    answer_body = answer.json()
    assert answer_body["answer"]
    assert answer_body["matched_entities"]
    assert answer_body["experiments"]
    assert answer_body["related_entities"]

    hypotheses = client.post(
        "/hypotheses/generate",
        json={
            "target_kpi": "Tensile Strength",
            "material": "Ti-6Al-4V",
            "max_hypotheses": 3,
        },
    )
    assert hypotheses.status_code == 200
    hypotheses_body = hypotheses.json()
    assert hypotheses_body["hypotheses"]
    assert hypotheses_body["hypotheses"][0]["score"]["final_score"] > 0
    assert hypotheses_body["evidence"] or hypotheses_body["data_gaps"]


def test_free_question_material_and_property_fallbacks() -> None:
    app = create_materials_app(
        settings=deterministic_settings(),
        service=MaterialsKGService(InMemoryMaterialsKGRepository())
    )
    client = TestClient(app)

    reference = client.post(
        "/ingest/reference",
        json={
            "entities": [
                {"kind": "material", "name": "IN718", "aliases": ["Inconel 718"]},
                {"kind": "property", "name": "Hardness"},
                {"kind": "mode", "name": "Aged"},
            ]
        },
    )
    assert reference.status_code == 200
    experiments = client.post(
        "/ingest/experiments",
        json=[
            {
                "experiment_id": "exp-in718",
                "title": "IN718 test",
                "material_name": "IN718",
                "mode_name": "Aged",
                "observations": [
                    {"property_name": "Hardness", "value": 42.0, "unit": "HRC"}
                ],
            }
        ],
    )
    assert experiments.status_code == 200

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
            {
                "kind": "material",
                "name": "Ti-6Al-4V",
                "aliases": ["Ti64"],
                "properties": {"density": "4.43 g/cm3"},
            },
            {
                "kind": "property",
                "name": "Tensile Strength",
                "aliases": ["UTS"],
                "properties": {},
            },
        ],
        "experiments": [
            {
                "experiment_id": "LLM-EXP-001",
                "title": "Tensile test of Ti64",
                "material_name": "Ti-6Al-4V",
                "mode_name": "Annealed",
                "observations": [
                    {
                        "property_name": "Tensile Strength",
                        "value": 950,
                        "unit": "MPa",
                        "confidence": 0.9,
                    }
                ],
                "findings": [
                    {
                        "summary": "Annealed Ti64 shows good ductility",
                        "confidence": 0.85,
                    }
                ],
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
    app = create_materials_app(settings=deterministic_settings(), service=service)
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


def test_upload_uses_llm_to_structure_ambiguous_csv_columns() -> None:
    from unittest.mock import MagicMock

    mock_llm = MagicMock()
    mock_llm.chat_json.return_value = {
        "reference": {
            "entities": [
                {"kind": "material", "name": "Alloy-X", "aliases": ["AX"]},
                {"kind": "mode", "name": "Route 7"},
                {"kind": "property", "name": "Yield Strength"},
            ]
        },
        "experiments": [
            {
                "experiment_id": "messy.csv#row-0",
                "title": "Alloy-X Route 7 Yield Strength",
                "material_name": "Alloy-X",
                "mode_name": "Route 7",
                "source_ref": "messy.csv",
                "observations": [
                    {
                        "property_name": "Yield Strength",
                        "value": 810.0,
                        "unit": "MPa",
                        "fragment": "specimen=AX; route=Route 7; KPI=Yield Strength; result=810 MPa",
                        "row_reference": "row 0",
                        "confidence": 0.86,
                    }
                ],
                "metadata": {
                    "llm_column_mapping": {
                        "slot_a": "material_name",
                        "slot_b": "mode_name",
                        "slot_c": "property_name",
                        "slot_d": "value",
                        "slot_e": "unit",
                    }
                },
            }
        ],
        "documents": [],
    }

    repo = InMemoryMaterialsKGRepository()
    service = MaterialsKGService(repo, llm_provider=mock_llm)
    app = create_materials_app(settings=deterministic_settings(), service=service)
    client = TestClient(app)

    csv_body = b"slot_a,slot_b,slot_c,slot_d,slot_e\nAX,Route 7,YS,810,MPa\n"
    upload = client.post(
        "/ingest/upload",
        files=[("files", ("messy.csv", csv_body, "text/csv"))],
    )

    assert upload.status_code == 200
    assert mock_llm.chat_json.called
    assert upload.json()["experiments"]["observations"] == 1
    prompt = mock_llm.chat_json.call_args.args[0][-1]["content"]
    assert "slot_a" in prompt
    assert "llm_column_mapping" in prompt

    query = client.post(
        "/query/material-mode",
        json={
            "material": "Alloy-X",
            "mode": "Route 7",
            "property_name": "Yield Strength",
        },
    )
    assert query.status_code == 200
    body = query.json()
    assert body["observations"][0]["value"] == 810.0
    assert body["evidence"][0]["source_id"] == "messy.csv"


class TestDestructiveEndpoints:
    """Verify DELETE endpoints are guarded by MATERIALS_ENABLE_DESTRUCTIVE_API."""

    def test_delete_source_returns_403_by_default(self) -> None:
        app = create_materials_app(
            settings=deterministic_settings(),
            service=MaterialsKGService(InMemoryMaterialsKGRepository())
        )
        client = TestClient(app)
        resp = client.delete("/sources/some-file.json")
        assert resp.status_code == 403
        assert "Destructive API disabled" in resp.text

    def test_delete_all_sources_returns_403_by_default(self) -> None:
        app = create_materials_app(
            settings=deterministic_settings(),
            service=MaterialsKGService(InMemoryMaterialsKGRepository())
        )
        client = TestClient(app)
        resp = client.delete("/sources")
        assert resp.status_code == 403
        assert "Destructive API disabled" in resp.text
