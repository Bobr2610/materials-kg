from __future__ import annotations

from pathlib import Path
import sys

import pytest


@pytest.fixture(scope="session")
def fixtures_path() -> Path:
    return Path(__file__).parent / "_fixtures"


@pytest.fixture(scope="session")
def docs_fixture_path(fixtures_path: Path) -> Path:
    return fixtures_path / "docs"


@pytest.fixture(scope="session")
def mkdocs_export_path(fixtures_path: Path) -> Path:
    return fixtures_path / "mkdocs_export"


# Ensure project root is on sys.path for module imports during tests
_tests_dir = Path(__file__).resolve().parent
_project_root = _tests_dir.parent  # rag_engine/
_repo_root = _project_root.parent  # repo root
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

