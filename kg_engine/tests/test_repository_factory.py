from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import patch

from kg_engine.repositories.factory import create_materials_repository
from kg_engine.repositories.memory import InMemoryMaterialsKGRepository


class TestRepositoryFactory:
    def test_returns_memory_repository_when_no_dsn(self) -> None:
        settings = MagicMock()
        settings.materials_pg_dsn = ""

        repo = create_materials_repository(settings)

        assert isinstance(repo, InMemoryMaterialsKGRepository)

    def test_returns_memory_repository_when_dsn_is_none(self) -> None:
        settings = MagicMock()
        settings.materials_pg_dsn = None

        repo = create_materials_repository(settings)

        assert isinstance(repo, InMemoryMaterialsKGRepository)

    @patch("kg_engine.repositories.factory.PostgresMaterialsKGRepository")
    def test_returns_postgres_repository_when_dsn_set(
        self,
        mock_pg_repo_cls: MagicMock,
    ) -> None:
        settings = MagicMock()
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
        settings.materials_pg_dsn = "postgresql://localhost/test"

        mock_repo = MagicMock()
        mock_pg_repo_cls.return_value = mock_repo

        with patch.dict("sys.modules", {"psycopg": MagicMock()}):
            create_materials_repository(settings)

        mock_repo.ensure_schema.assert_not_called()
