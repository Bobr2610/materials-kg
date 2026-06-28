"""Repository bootstrap helpers for the graph-first materials KG core."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kg_engine.repositories.memory import InMemoryMaterialsKGRepository
from kg_engine.repositories.postgres import PostgresMaterialsKGRepository

if TYPE_CHECKING:
    from kg_engine.config.settings import Settings


def create_materials_repository(
    settings: Settings,
    *,
    ensure_schema: bool = False,
) -> InMemoryMaterialsKGRepository | PostgresMaterialsKGRepository:
    """Create the materials KG repository from environment-driven settings."""
    if not settings.materials_pg_dsn:
        return InMemoryMaterialsKGRepository()

    import psycopg

    connection = psycopg.connect(settings.materials_pg_dsn)
    repository = PostgresMaterialsKGRepository(connection)
    if ensure_schema:
        repository.ensure_schema()
    return repository
