from __future__ import annotations

from typing import Self

from kg_engine.domain.models import Entity
from kg_engine.repositories.neo4j import Neo4jMaterialsKGRepository
from kg_engine.repositories.neo4j import create_neo4j_repository

TEST_NEO4J_PASSWORD = "unit-test-password"  # noqa: S105


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.entities: dict[str, dict] = {}

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def run(self, query: str, **params: object) -> list[dict]:
        self.calls.append((query, dict(params)))
        if "MERGE (n:Entity" in query:
            payload = dict(params["payload"])
            self.entities[str(params["id"])] = payload
            return [{"n": payload}]
        if "MATCH (n:Entity {id: $id})" in query:
            entity = self.entities.get(str(params["id"]))
            return [{"n": entity}] if entity else []
        return []


class FakeDriver:
    def __init__(self) -> None:
        self.session_obj = FakeSession()
        self.closed = False

    def session(self, **kwargs: object) -> FakeSession:
        self.session_kwargs = kwargs
        return self.session_obj

    def close(self) -> None:
        self.closed = True


def test_create_neo4j_repository_uses_official_driver_contract() -> None:
    captured: dict[str, object] = {}

    def fake_driver_factory(uri: str, *, auth: tuple[str, str]) -> FakeDriver:
        captured["uri"] = uri
        captured["auth"] = auth
        return FakeDriver()

    repository = create_neo4j_repository(
        uri="bolt://127.0.0.1:7687",
        user="neo4j",
        password=TEST_NEO4J_PASSWORD,
        database="neo4j",
        driver_factory=fake_driver_factory,
    )

    assert isinstance(repository, Neo4jMaterialsKGRepository)
    assert captured == {
        "uri": "bolt://127.0.0.1:7687",
        "auth": ("neo4j", TEST_NEO4J_PASSWORD),
    }


def test_neo4j_repository_round_trips_entity_with_fake_driver() -> None:
    driver = FakeDriver()
    repository = Neo4jMaterialsKGRepository(driver, database="neo4j")
    entity = Entity(
        id="mat_cucrzr",
        kind="material",
        canonical_name="CuCrZr",
        aliases=["Cu-Cr-Zr"],
        source_refs=["sample"],
    )

    stored = repository.upsert_entity(entity)
    loaded = repository.get_entity("mat_cucrzr")

    assert stored.id == "mat_cucrzr"
    assert loaded is not None
    assert loaded.canonical_name == "CuCrZr"
    assert driver.session_kwargs == {"database": "neo4j"}
    assert any("MERGE (n:Entity" in call[0] for call in driver.session_obj.calls)
