from __future__ import annotations

from pathlib import Path
import sys


# Ensure project root is on sys.path for module imports during tests
_tests_dir = Path(__file__).resolve().parent
_project_root = _tests_dir.parent  # kg_engine/
_repo_root = _project_root.parent  # repo root
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
