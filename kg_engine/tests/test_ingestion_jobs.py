from pathlib import Path

from fastapi.testclient import TestClient

from kg_engine.api.materials_core import create_materials_app
from kg_engine.repositories.memory import InMemoryMaterialsKGRepository
from kg_engine.services.ingestion_jobs import IngestionJobService
from kg_engine.services.materials_kg import MaterialsKGService


def test_ingestion_job_isolated_failure_and_fragment_lookup(tmp_path: Path) -> None:
    graph = MaterialsKGService(InMemoryMaterialsKGRepository())
    jobs = IngestionJobService(tmp_path / "jobs.sqlite3", graph_service=graph)
    app = create_materials_app(service=graph, ingestion_job_service=jobs)

    response = TestClient(app).post(
        "/ingestion/jobs",
        files=[
            ("files", ("notes.txt", b"CuCrZr conductivity 80 %IACS", "text/plain")),
            ("files", ("malware.exe", b"bad", "application/octet-stream")),
        ],
        headers={"X-User": "researcher", "X-Role": "researcher"},
    )

    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "partial"
    assert job["processed_files"] == 1
    assert job["failed_files"] == 1
    source_id = job["source_ids"][0]
    fragments = TestClient(app).get(f"/sources/{source_id}/fragments")
    assert fragments.status_code == 200
    assert fragments.json()["fragments"][0]["locator"] == {"line": 1}


def test_duplicate_source_is_not_ingested_twice(tmp_path: Path) -> None:
    graph = MaterialsKGService(InMemoryMaterialsKGRepository())
    jobs = IngestionJobService(tmp_path / "jobs.sqlite3", graph_service=graph)

    first = jobs.submit([("a.txt", b"same")], actor="test")
    second = jobs.submit([("b.txt", b"same")], actor="test")

    assert first.processed_files == 1
    assert second.duplicate_files == 1
    assert second.processed_files == 0
