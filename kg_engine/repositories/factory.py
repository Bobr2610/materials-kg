"""Repository bootstrap helpers for the graph-first materials KG core."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kg_engine.repositories.memory import InMemoryMaterialsKGRepository
from kg_engine.repositories.neo4j import Neo4jMaterialsKGRepository
from kg_engine.repositories.neo4j import create_neo4j_repository
from kg_engine.repositories.postgres import PostgresMaterialsKGRepository

if TYPE_CHECKING:
    from kg_engine.config.settings import Settings


def create_materials_repository(
    settings: Settings,
    *,
    ensure_schema: bool = False,
) -> InMemoryMaterialsKGRepository | Neo4jMaterialsKGRepository | PostgresMaterialsKGRepository:
    """Create the materials KG repository from environment-driven settings."""
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

    if not settings.materials_pg_dsn:
        if getattr(settings, "materials_require_graph_db", False):
            msg = (
                "Materials Hypothesis Factory runtime requires a graph database. "
                "Set MATERIALS_NEO4J_URI or disable MATERIALS_REQUIRE_GRAPH_DB "
                "for tests only."
            )
            raise RuntimeError(msg)
        return InMemoryMaterialsKGRepository()

    import psycopg

    connection = psycopg.connect(settings.materials_pg_dsn)
    repository = PostgresMaterialsKGRepository(connection)
    if ensure_schema:
        repository.ensure_schema()
    return repository
