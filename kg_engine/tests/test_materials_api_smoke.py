from __future__ import annotations

import json

import anyio
from fastapi.testclient import TestClient

from kg_engine.agents.hypothesis_tools import create_hypothesis_tools
from kg_engine.api import materials_core
from kg_engine.api.materials_core import create_materials_app
from kg_engine.config.settings import Settings
from kg_engine.ingestion.document_blocks import DocumentBlock
from kg_engine.repositories.memory import InMemoryMaterialsKGRepository
from kg_engine.services.materials_kg import MaterialsKGService


def deterministic_settings() -> Settings:
    return Settings(
        materials_hypothesis_engine="deterministic",
        materials_enable_destructive_api=False,
    )


def load_task_materials_job(client: TestClient, **params) -> dict:
    started = client.post("/demo/load-task-materials", params=params)
    assert started.status_code == 202
    job = started.json()
    assert job["status"] in {"queued", "running"}
    assert job["job_id"]
    for _ in range(500):
        job = client.get(f"/demo/load-task-materials/jobs/{job['job_id']}").json()
        if job["status"] not in {"queued", "running"}:
            break
        anyio.run(anyio.sleep, 0.02)
    assert job["status"] == "completed", job
    assert job["processed_files"] == job["total_files"]
    assert job["result"] is not None
    return job["result"]


def generate_hypotheses_job(client: TestClient, payload: dict) -> dict:
    started = client.post("/hypotheses/generate", json=payload)
    assert started.status_code == 202
    job = started.json()
    assert job["status"] in {"queued", "running"}
    assert job["job_id"]
    for _ in range(100):
        job = client.get(f"/hypotheses/jobs/{job['job_id']}").json()
        if job["status"] not in {"queued", "running"}:
            break
        anyio.run(anyio.sleep, 0.01)
    assert job["status"] == "completed", job
    assert job["result"] is not None
    return job["result"]


def test_materials_api_health_and_ingest_query_flow() -> None:
    app = create_materials_app(
        settings=deterministic_settings(),
        service=MaterialsKGService(InMemoryMaterialsKGRepository()),
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
    assert 'id="loadTaskMaterials"' in dashboard.text
    assert 'id="exportHypothesesJson"' in dashboard.text
    assert 'id="exportHypothesesCsv"' in dashboard.text
    assert 'id="clearChat"' in dashboard.text
    assert 'id="sourceSearch"' in dashboard.text
    assert 'id="sourceSummary"' in dashboard.text
    assert 'id="sourceNote"' in dashboard.text
    assert 'id="hypothesisPanel"' in dashboard.text
    assert 'id="targetKpi"' in dashboard.text
    assert 'id="generateHypotheses"' in dashboard.text
    assert "/hypotheses/generate" in dashboard.text
    assert "renderHypotheses" in dashboard.text
    assert "/demo/load-task-materials" in dashboard.text
    assert "/hypotheses/export?format=" in dashboard.text
    assert "/metrics/feedback" in dashboard.text
    assert "Evidence IDs" in dashboard.text
    assert "Observation IDs" in dashboard.text
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

    hypotheses_body = generate_hypotheses_job(
        client,
        {
            "target_kpi": "Tensile Strength",
            "material": "Ti-6Al-4V",
            "max_hypotheses": 3,
        },
    )
    assert hypotheses_body["hypotheses"]
    assert hypotheses_body["hypotheses"][0]["score"]["final_score"] > 0
    assert hypotheses_body["evidence"] or hypotheses_body["data_gaps"]


def test_task_materials_loader_and_hypothesis_exports(tmp_path, monkeypatch) -> None:
    task_dir = tmp_path / "Задача 1"
    task_dir.mkdir()
    (task_dir / "reference.json").write_text(
        json.dumps(
            {
                "entities": [
                    {"kind": "material", "name": "CuCrZr"},
                    {"kind": "mode", "name": "Aging"},
                    {"kind": "property", "name": "Conductivity"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (task_dir / "experiments.json").write_text(
        json.dumps(
            [
                {
                    "experiment_id": "task1-exp",
                    "title": "Task 1 conductivity check",
                    "material_name": "CuCrZr",
                    "mode_name": "Aging",
                    "observations": [
                        {
                            "property_name": "Conductivity",
                            "value": 58.0,
                            "unit": "%IACS",
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    (task_dir / "notes.md").write_text(
        "# Task 1 notes\nCuCrZr aging improves conductivity.",
        encoding="utf-8",
    )
    (task_dir / "scan.pdf").write_bytes(b"%PDF unsupported by Agent 2")
    monkeypatch.setattr(materials_core, "_TASK_MATERIALS_DIRS", (task_dir,))

    app = create_materials_app(
        settings=deterministic_settings(),
        service=MaterialsKGService(InMemoryMaterialsKGRepository())
    )
    client = TestClient(app)

    loaded_body = load_task_materials_job(client)
    assert len(loaded_body["uploaded"]) == 4
    assert loaded_body["unsupported_files"] == []
    assert loaded_body["reference"]["entities"] == 3
    assert loaded_body["experiments"]["observations"] == 1
    assert loaded_body["documents_ingested"] == 2

    result = generate_hypotheses_job(
        client,
        {
            "target_kpi": "Conductivity",
            "material": "CuCrZr",
            "max_hypotheses": 2,
        },
    )
    assert result["hypotheses"]

    json_export = client.post(
        "/hypotheses/export?format=json",
        json={"result": result},
    )
    assert json_export.status_code == 200
    assert json_export.headers["content-disposition"].endswith(
        'filename="materials-hypotheses.json"'
    )
    assert json_export.json()["target_kpi"] == "Conductivity"

    csv_export = client.post(
        "/hypotheses/export?format=csv",
        json={"result": result},
    )
    assert csv_export.status_code == 200
    assert "text/csv" in csv_export.headers["content-type"]
    assert "supporting_observation_ids" in csv_export.text
    assert "Conductivity" in csv_export.text


def test_task_materials_loader_uses_packaged_fallback(tmp_path, monkeypatch) -> None:
    missing_task_dir = tmp_path / "missing-task"
    fallback_dir = tmp_path / "sample_sources"
    fallback_dir.mkdir()
    (fallback_dir / "reference_pack.json").write_text(
        json.dumps(
            {
                "materials": [{"name": "CuCrZr"}],
                "properties": [{"name": "Electrical Conductivity"}],
                "modes": [{"name": "Solution Treated"}],
            }
        ),
        encoding="utf-8",
    )
    (fallback_dir / "experiment_rows.csv").write_text(
        "experiment_id,title,material,mode,property,value,unit,finding\n"
        "FALLBACK-001,CuCrZr fallback conductivity,CuCrZr,"
        "Solution Treated,Electrical Conductivity,58,%IACS,"
        "Fallback row becomes a structured observation",
        encoding="utf-8",
    )
    monkeypatch.setattr(materials_core, "_TASK_MATERIALS_DIRS", (missing_task_dir,))
    monkeypatch.setattr(
        materials_core,
        "_TASK_MATERIALS_FALLBACK_DIRS",
        (fallback_dir,),
    )

    app = create_materials_app(
        settings=deterministic_settings(),
        service=MaterialsKGService(InMemoryMaterialsKGRepository()),
    )
    client = TestClient(app)

    loaded_body = load_task_materials_job(client)
    assert loaded_body["used_fallback"] is True
    assert "sample_sources" in loaded_body["task_materials_dir"]
    assert loaded_body["warnings"]
    assert loaded_body["reference"]["entities"] == 3
    assert loaded_body["experiments"]["experiments"] == 1
    assert loaded_body["experiments"]["observations"] == 1


def test_task_materials_base_loader_skips_examples_and_saves_snapshot(
    tmp_path,
    monkeypatch,
) -> None:
    task_dir = tmp_path / "Задача 1"
    example_dir = task_dir / "Пример 1"
    base_dir = task_dir / "Регламенты"
    example_dir.mkdir(parents=True)
    base_dir.mkdir()
    (base_dir / "base.md").write_text(
        "# Регламент\nВ базе описан материал CuCrZr и показатель Conductivity.",
        encoding="utf-8",
    )
    (example_dir / "case.md").write_text(
        "# Пример\nЭтот файл не должен попасть в базовый граф.",
        encoding="utf-8",
    )
    snapshot_path = tmp_path / "base_graph.json"
    monkeypatch.setattr(materials_core, "_TASK_MATERIALS_DIRS", (task_dir,))

    app = create_materials_app(
        settings=deterministic_settings(),
        service=MaterialsKGService(InMemoryMaterialsKGRepository()),
    )
    client = TestClient(app)

    body = load_task_materials_job(
        client,
        exclude_examples="true",
        snapshot_path=str(snapshot_path),
    )
    assert body["excluded_examples"] is True
    uploaded_name = body["uploaded"][0]["name"].replace("\\", "/")
    assert uploaded_name == "Регламенты/base.md"
    skipped = [name.replace("\\", "/") for name in body["skipped_example_files"]]
    assert skipped == ["Пример 1/case.md"]
    assert body["snapshot"]["path"] == str(snapshot_path)
    assert snapshot_path.exists()

    restored_service = MaterialsKGService(InMemoryMaterialsKGRepository())
    restored_counts = restored_service.load_graph_snapshot(snapshot_path)
    assert restored_counts["entities"] == body["snapshot"]["entities"]
    assert restored_service.search_evidence_units("CuCrZr", limit=5)


def test_task_example_tailings_excel_is_navigable_for_graph_agent(
    tmp_path,
    monkeypatch,
) -> None:
    task_dir = tmp_path / "Задача 1"
    example_dir = task_dir / "Пример 1"
    example_dir.mkdir(parents=True)
    source = example_dir / "Хвосты КГМК.xlsx"
    source.write_bytes(b"fake xlsx; parser is injected")

    class TailingsExcelParser:
        def parse(self, path):
            text = (
                "Комплексный анализ хвостов обогатительных фабрик. "
                "Хвосты являются отвальными продуктами флотационного обогащения. "
                "Породные и пирротиновые хвосты содержат потерянные элементы 28 и 29. "
                "Классы крупности: +125; -125 +71; -71 +45; -45 +20; -20 +10; -10. "
                "Минералогический анализ: для элемента 28 потенциально извлекаемы "
                "раскрытый Pnt, закрытый Pnt и миллерит; для элемента 29 извлекаемы "
                "раскрытый и закрытый Pnt/Cp."
            )
            return [
                DocumentBlock(
                    block_id="tailings-xlsx-block",
                    source_file=path.name,
                    source_path=str(path),
                    page=None,
                    block_type="text",
                    text=text,
                    raw_fragment=text,
                    confidence=1.0,
                    parser="test_excel_parser",
                    metadata={"sheet": "analysis"},
                )
            ]

    monkeypatch.setattr(materials_core, "_TASK_MATERIALS_DIRS", (task_dir,))
    monkeypatch.setattr(
        materials_core,
        "_api_document_parser",
        lambda *args, **kwargs: TailingsExcelParser(),
    )

    repository = InMemoryMaterialsKGRepository()
    service = MaterialsKGService(repository)
    app = create_materials_app(settings=deterministic_settings(), service=service)
    client = TestClient(app)

    body = load_task_materials_job(
        client,
        enable_llm_extraction="false",
        enable_embeddings="false",
    )
    assert body["documents_ingested"] == 1
    assert body["uploaded"][0]["name"].replace("\\", "/") == "Пример 1/Хвосты КГМК.xlsx"

    graph = client.get(
        "/graph/data",
        params={"sources": "Пример 1/Хвосты КГМК.xlsx"},
    )
    assert graph.status_code == 200
    graph_body = graph.json()
    document_nodes = [
        node for node in graph_body["nodes"] if node["kind"] == "document"
    ]
    assert document_nodes
    assert graph_body["edges"]

    tools = {tool.__name__: tool for tool in create_hypothesis_tools(service)}
    hits = tools["kg_search_evidence"](
        "хвосты элемент 28 Pnt крупности",
        source_ids=["Пример 1/Хвосты КГМК.xlsx"],
    )
    related = tools["kg_query_related"](document_nodes[0]["id"], depth=1)

    assert hits
    assert "Pnt" in hits[0]["content"]
    assert related["root_entity"]["kind"] == "document"
    assert related["relations"]
    assert related["evidence"]


def test_metrics_api_offline_quality_flow() -> None:
    app = create_materials_app(
        settings=deterministic_settings(),
        service=MaterialsKGService(InMemoryMaterialsKGRepository())
    )
    client = TestClient(app)
    client.post(
        "/ingest/reference",
        json={
            "entities": [
                {"kind": "material", "name": "CuCrZr", "canonical_id": "mat-cucrzr"},
                {"kind": "mode", "name": "Aged", "canonical_id": "mode-aged"},
                {
                    "kind": "property",
                    "name": "Conductivity",
                    "canonical_id": "prop-conductivity",
                },
            ]
        },
    )
    client.post(
        "/ingest/experiments",
        json=[
            {
                "experiment_id": "exp-metrics",
                "title": "Metrics trial",
                "material_name": "CuCrZr",
                "mode_name": "Aged",
                "observations": [
                    {
                        "property_name": "Conductivity",
                        "value": 78.0,
                        "unit": "%IACS",
                    }
                ],
            }
        ],
    )

    coverage = client.post("/metrics/coverage", json={})
    assert coverage.status_code == 200
    assert coverage.json()["coverage_ratio"] == 1.0

    explicit_coverage = client.post(
        "/metrics/coverage",
        json={
            "axes": {
                "material_ids": ["mat-cucrzr"],
                "mode_ids": ["mode-aged"],
                "property_ids": ["prop-conductivity", "prop-hardness"],
            }
        },
    )
    assert explicit_coverage.status_code == 200
    assert explicit_coverage.json()["coverage_ratio"] == 0.5

    extraction = client.post(
        "/metrics/extraction",
        json={
            "samples": [
                {
                    "sample_id": "doc-1",
                    "expected_entities": [{"kind": "material", "name": "CuCrZr"}],
                    "extracted_entities": [{"kind": "material", "name": "CuCrZr"}],
                }
            ]
        },
    )
    assert extraction.status_code == 200
    assert extraction.json()["entity"]["f1"] == 1.0

    context = client.post(
        "/metrics/context",
        json={
            "expected_context_ids": ["ev-1", "ev-2"],
            "retrieved_context_ids": ["ev-1"],
            "expected_entity_ids": ["mat-cucrzr"],
            "retrieved_entity_ids": ["mat-cucrzr"],
        },
    )
    assert context.status_code == 200
    assert context.json()["context_recall"] == 0.5

    hypotheses = client.post(
        "/metrics/hypotheses",
        json={
            "run": {
                "name": "deterministic",
                "result": {
                    "target_kpi": "Conductivity",
                    "generation_engine": "deterministic",
                    "hypotheses": [
                        {
                            "id": "grounded-1",
                            "target_kpi": "Conductivity",
                            "statement": "Validate measured CuCrZr conductivity",
                            "rationale": "ev-1 and obs-1 support the claim",
                            "test_plan": "Repeat measurement",
                            "score": {
                                "novelty": 0.4,
                                "risk": 0.2,
                                "value": 0.7,
                                "evidence_strength": 0.8,
                                "final_score": 0.72,
                            },
                            "supporting_entity_ids": [
                                "mat-cucrzr",
                                "mode-aged",
                                "prop-conductivity",
                            ],
                            "supporting_evidence_ids": ["ev-1"],
                            "supporting_observation_ids": ["obs-1"],
                        }
                    ],
                },
                "context": {
                    "evidence_ids": ["ev-1"],
                    "observation_ids": ["obs-1"],
                    "entity_ids": [
                        "mat-cucrzr",
                        "mode-aged",
                        "prop-conductivity",
                    ],
                },
                "coverage": {
                    "axes": {
                        "material_ids": ["mat-cucrzr"],
                        "mode_ids": ["mode-aged"],
                        "property_ids": ["prop-conductivity"],
                    },
                    "cells": [
                        {
                            "material_id": "mat-cucrzr",
                            "mode_id": "mode-aged",
                            "property_id": "prop-conductivity",
                            "measured": True,
                            "observation_count": 1,
                            "observation_ids": ["obs-1"],
                        }
                    ],
                },
            }
        },
    )
    assert hypotheses.status_code == 200
    hypotheses_body = hypotheses.json()
    assert hypotheses_body["average_faithfulness"] == 1.0
    assert hypotheses_body["average_groundedness"] == 1.0
    assert hypotheses_body["average_novelty"] == 0.0
    assert hypotheses_body["items"][0]["coverage_status"] == "measured"

    compare = client.post(
        "/metrics/runs/compare",
        json={
            "left": {
                "name": "deterministic",
                "result": {
                    "target_kpi": "Conductivity",
                    "generation_engine": "deterministic",
                    "hypotheses": [
                        {
                            "id": "det-1",
                            "target_kpi": "Conductivity",
                            "statement": "Test deterministic",
                            "rationale": "ev-1",
                            "test_plan": "Measure",
                            "score": {
                                "novelty": 0.4,
                                "risk": 0.2,
                                "value": 0.6,
                                "evidence_strength": 0.6,
                                "final_score": 0.6,
                            },
                            "supporting_evidence_ids": ["ev-1"],
                        }
                    ],
                },
                "context": {"evidence_ids": ["ev-1"]},
            },
            "right": {
                "name": "agent",
                "result": {
                    "target_kpi": "Conductivity",
                    "generation_engine": "agent",
                    "hypotheses": [
                        {
                            "id": "agent-1",
                            "target_kpi": "Conductivity",
                            "statement": "Test agent",
                            "rationale": "missing",
                            "test_plan": "Measure",
                            "score": {
                                "novelty": 0.4,
                                "risk": 0.2,
                                "value": 0.8,
                                "evidence_strength": 0.8,
                                "final_score": 0.8,
                            },
                            "supporting_evidence_ids": ["missing"],
                        }
                    ],
                },
                "context": {"evidence_ids": ["ev-1"]},
            },
        },
    )
    assert compare.status_code == 200
    assert compare.json()["deltas"]["average_final_score"] == 0.2

    feedback = client.post(
        "/metrics/feedback",
        json={
            "hypothesis_id": "det-1",
            "rating": 5,
            "score": {
                "novelty": 0.4,
                "risk": 0.2,
                "value": 0.6,
                "evidence_strength": 0.6,
                "final_score": 0.6,
            },
        },
    )
    assert feedback.status_code == 200
    assert feedback.json()["saved"] == 1
    assert feedback.json()["invalid_feedback_lines"] == 0

    weights = client.get("/metrics/feedback/weights")
    assert weights.status_code == 200
    assert weights.json()["sample_size"] >= 1
    assert weights.json()["weights"]["total"] == 1.0

    correlation = client.get("/metrics/feedback/correlation")
    assert correlation.status_code == 200
    assert correlation.json()["sample_size"] >= 1
    assert correlation.json()["invalid_feedback_lines"] == 0


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


def test_task_materials_loader_and_hypothesis_exports(tmp_path, monkeypatch) -> None:
    task_dir = tmp_path / "Задача 1"
    task_dir.mkdir()
    (task_dir / "reference.json").write_text(
        json.dumps(
            {
                "entities": [
                    {"kind": "material", "name": "CuCrZr"},
                    {"kind": "mode", "name": "Aging"},
                    {"kind": "property", "name": "Conductivity"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (task_dir / "experiments.json").write_text(
        json.dumps(
            [
                {
                    "experiment_id": "task1-exp",
                    "title": "Task 1 conductivity check",
                    "material_name": "CuCrZr",
                    "mode_name": "Aging",
                    "observations": [
                        {
                            "property_name": "Conductivity",
                            "value": 58.0,
                            "unit": "%IACS",
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    (task_dir / "notes.md").write_text(
        "# Task 1 notes\nCuCrZr aging improves conductivity.",
        encoding="utf-8",
    )
    (task_dir / "scan.pdf").write_bytes(b"%PDF unsupported by Agent 2")
    monkeypatch.setattr(materials_core, "_TASK_MATERIALS_DIRS", (task_dir,))

    app = create_materials_app(
        settings=deterministic_settings(),
        service=MaterialsKGService(InMemoryMaterialsKGRepository())
    )
    client = TestClient(app)

    loaded_body = load_task_materials_job(client)
    assert len(loaded_body["uploaded"]) == 4
    assert loaded_body["unsupported_files"] == []
    assert loaded_body["reference"]["entities"] == 3
    assert loaded_body["experiments"]["observations"] == 1
    assert loaded_body["documents_ingested"] == 2

    result = generate_hypotheses_job(
        client,
        {
            "target_kpi": "Conductivity",
            "material": "CuCrZr",
            "max_hypotheses": 2,
        },
    )
    assert result["hypotheses"]

    json_export = client.post(
        "/hypotheses/export?format=json",
        json={"result": result},
    )
    assert json_export.status_code == 200
    assert json_export.headers["content-disposition"].endswith(
        'filename="materials-hypotheses.json"'
    )
    assert json_export.json()["target_kpi"] == "Conductivity"

    csv_export = client.post(
        "/hypotheses/export?format=csv",
        json={"result": result},
    )
    assert csv_export.status_code == 200
    assert "text/csv" in csv_export.headers["content-type"]
    assert "supporting_observation_ids" in csv_export.text
    assert "Conductivity" in csv_export.text


def test_task_materials_loader_uses_packaged_fallback(tmp_path, monkeypatch) -> None:
    missing_task_dir = tmp_path / "missing-task"
    fallback_dir = tmp_path / "sample_sources"
    fallback_dir.mkdir()
    (fallback_dir / "reference_pack.json").write_text(
        json.dumps(
            {
                "materials": [{"name": "CuCrZr"}],
                "properties": [{"name": "Electrical Conductivity"}],
                "modes": [{"name": "Solution Treated"}],
            }
        ),
        encoding="utf-8",
    )
    (fallback_dir / "experiment_rows.csv").write_text(
        "experiment_id,title,material,mode,property,value,unit,finding\n"
        "FALLBACK-001,CuCrZr fallback conductivity,CuCrZr,"
        "Solution Treated,Electrical Conductivity,58,%IACS,"
        "Fallback row becomes a structured observation",
        encoding="utf-8",
    )
    monkeypatch.setattr(materials_core, "_TASK_MATERIALS_DIRS", (missing_task_dir,))
    monkeypatch.setattr(
        materials_core,
        "_TASK_MATERIALS_FALLBACK_DIRS",
        (fallback_dir,),
    )

    app = create_materials_app(
        settings=deterministic_settings(),
        service=MaterialsKGService(InMemoryMaterialsKGRepository()),
    )
    client = TestClient(app)

    loaded_body = load_task_materials_job(client)
    assert loaded_body["used_fallback"] is True
    assert "sample_sources" in loaded_body["task_materials_dir"]
    assert loaded_body["warnings"]
    assert loaded_body["reference"]["entities"] == 3


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
