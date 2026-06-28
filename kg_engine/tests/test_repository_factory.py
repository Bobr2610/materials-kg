from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from kg_engine.repositories.factory import create_materials_repository
from kg_engine.repositories.memory import InMemoryMaterialsKGRepository

TEST_NEO4J_PASSWORD = "unit-test-password"  # noqa: S105


class TestRepositoryFactory:
    def test_returns_memory_repository_when_no_dsn(self) -> None:
        settings = MagicMock()
        settings.materials_neo4j_uri = ""
        settings.materials_pg_dsn = ""
        settings.materials_require_graph_db = False

        repo = create_materials_repository(settings)

        assert isinstance(repo, InMemoryMaterialsKGRepository)

    def test_returns_memory_repository_when_dsn_is_none(self) -> None:
        settings = MagicMock()
        settings.materials_neo4j_uri = ""
        settings.materials_pg_dsn = None
        settings.materials_require_graph_db = False

        repo = create_materials_repository(settings)

        assert isinstance(repo, InMemoryMaterialsKGRepository)

    @patch("kg_engine.repositories.factory.create_neo4j_repository")
    def test_returns_neo4j_repository_when_uri_set(
        self,
        mock_create_neo4j_repository: MagicMock,
    ) -> None:
        settings = MagicMock()
        settings.materials_neo4j_uri = "bolt://127.0.0.1:7687"
        settings.materials_neo4j_user = "neo4j"
        settings.materials_neo4j_password = TEST_NEO4J_PASSWORD
        settings.materials_neo4j_database = "neo4j"
        settings.materials_pg_dsn = "postgresql://localhost/test"
        mock_repo = MagicMock()
        mock_create_neo4j_repository.return_value = mock_repo

        repo = create_materials_repository(settings)

        mock_create_neo4j_repository.assert_called_once_with(
            uri="bolt://127.0.0.1:7687",
            user="neo4j",
            password=TEST_NEO4J_PASSWORD,
            database="neo4j",
        )
        assert repo is mock_repo

    @patch("kg_engine.repositories.factory.create_neo4j_repository")
    def test_neo4j_ensure_schema_called_when_flag_set(
        self,
        mock_create_neo4j_repository: MagicMock,
    ) -> None:
        settings = MagicMock()
        settings.materials_neo4j_uri = "bolt://127.0.0.1:7687"
        settings.materials_neo4j_user = "neo4j"
        settings.materials_neo4j_password = TEST_NEO4J_PASSWORD
        settings.materials_neo4j_database = ""
        settings.materials_pg_dsn = ""
        mock_repo = MagicMock()
        mock_create_neo4j_repository.return_value = mock_repo

        create_materials_repository(settings, ensure_schema=True)

        mock_repo.ensure_schema.assert_called_once()

    def test_strict_runtime_requires_graph_database(self) -> None:
        settings = MagicMock()
        settings.materials_neo4j_uri = ""
        settings.materials_pg_dsn = ""
        settings.materials_require_graph_db = True

        with pytest.raises(RuntimeError, match="requires a graph database"):
            create_materials_repository(settings)

    @patch("kg_engine.repositories.factory.PostgresMaterialsKGRepository")
    def test_returns_postgres_repository_when_dsn_set(
        self,
        mock_pg_repo_cls: MagicMock,
    ) -> None:
        settings = MagicMock()
        settings.materials_neo4j_uri = ""
        settings.materials_pg_dsn = "postgresql://localhost/test"

        mock_psycopg = MagicMock()
        mock_pg_repo_cls.return_value = MagicMock()

        with patch.dict("sys.modules", {"psycopg": mock_psycopg}):
            repo = create_materials_repository(settings)

        mock_psycopg.connect.assert_called_once_with(
            "postgresql://localhost/test",
        )
        assert repo is mock_pg_repo_cls.return_value

    @patch("kg_engine.repositories.factory.PostgresMaterialsKGRepository")
    def test_ensure_schema_called_when_flag_set(
        self,
        mock_pg_repo_cls: MagicMock,
    ) -> None:
        settings = MagicMock()
        settings.materials_neo4j_uri = ""
        settings.materials_pg_dsn = "postgresql://localhost/test"

        mock_repo = MagicMock()
        mock_pg_repo_cls.return_value = mock_repo

        with patch.dict("sys.modules", {"psycopg": MagicMock()}):
            create_materials_repository(settings, ensure_schema=True)

        mock_repo.ensure_schema.assert_called_once()

    @patch("kg_engine.repositories.factory.PostgresMaterialsKGRepository")
    def test_ensure_schema_not_called_by_default(
        self,
        mock_pg_repo_cls: MagicMock,
    ) -> None:
        settings = MagicMock()
        settings.materials_neo4j_uri = ""
        settings.materials_pg_dsn = "postgresql://localhost/test"

        mock_repo = MagicMock()
        mock_pg_repo_cls.return_value = mock_repo

        with patch.dict("sys.modules", {"psycopg": MagicMock()}):
            create_materials_repository(settings)

        mock_repo.ensure_schema.assert_not_called()
