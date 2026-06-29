"""Repository bootstrap helpers for the graph-first materials KG core."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kg_engine.repositories.memory import InMemoryMaterialsKGRepository
from kg_engine.repositories.neo4j import Neo4jMaterialsKGRepository
from kg_engine.repositories.neo4j import create_neo4j_repository

if TYPE_CHECKING:
    from kg_engine.config.settings import Settings


def create_materials_repository(
    settings: Settings,
    *,
    ensure_schema: bool = False,
) -> InMemoryMaterialsKGRepository | Neo4jMaterialsKGRepository:
    """Create the materials KG repository from environment-driven settings.

    Neo4j is the only production backend. In-memory is allowed only when
    ``MATERIALS_REQUIRE_GRAPH_DB`` is ``False`` (unit tests / local dev).
    """
    if getattr(settings, "materials_neo4j_uri", ""):
        repository = create_neo4j_repository(
            uri=settings.materials_neo4j_uri,
            user=getattr(settings, "materials_neo4j_user", "neo4j"),
            password=getattr(settings, "materials_neo4j_password", ""),
            database=getattr(settings, "materials_neo4j_database", "") or None,
        )
        if ensure_schema:
            repository.ensure_schema()
        return repository

    if getattr(settings, "materials_require_graph_db", False):
        msg = (
            "Neo4j is required for runtime. "
            "Set MATERIALS_NEO4J_URI to connect to a Neo4j instance, or "
            "disable MATERIALS_REQUIRE_GRAPH_DB for tests only."
        )
        raise RuntimeError(msg)

    return InMemoryMaterialsKGRepository()
