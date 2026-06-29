"""Isolation guard for the active Materials KG package and surface files.

Scans the entire active package discovery scope plus top-level docs/config
to ensure no donor/legacy/forbidden technology references leak into runtime.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PKG_ROOT = _REPO_ROOT / "kg_engine"

_SURFACE_FILES: list[Path] = [
    _REPO_ROOT / "README.md",
    _REPO_ROOT / "pyproject.toml",
    _REPO_ROOT / ".env.example",
    _REPO_ROOT / "docker-compose.yml",
    _REPO_ROOT / "requirements_core.txt",
    _REPO_ROOT / "lint.py",
    _REPO_ROOT / "kg_engine" / "requirements.txt",
    _REPO_ROOT / "kg_engine" / "repositories" / "factory.py",
    _REPO_ROOT / "kg_engine" / "repositories" / "__init__.py",
    _REPO_ROOT / "kg_engine" / "config" / "settings.py",
]

_SKIP_DIRS: set[str] = {
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    ".pytest_cache",
    ".ruff_cache",
    ".codex_deps",
    "tests",
}

_FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "postgres/psycopg/pgvector",
        re.compile(
            r"\bpostgres(?:ql)?\b|\bpsycopg\b|\bpgvector\b|\bMATERIALS_PG_DSN\b|VECTOR\(\d+\)",
            re.IGNORECASE,
        ),
    ),
    ("chroma/chromadb", re.compile(r"\bchroma(?:db)?\b", re.IGNORECASE)),
    ("langchain", re.compile(r"\blangchain\b", re.IGNORECASE)),
    (
        "rag_engine / RAG engine",
        re.compile(r"\brag_engine\b|RAG\s+engine", re.IGNORECASE),
    ),
    (
        "cmw/comindware",
        re.compile(
            r"\bcmw\b|\bcomindware\b|\bkb\.comindware",
            re.IGNORECASE,
        ),
    ),
    ("/neo4j/cypher endpoint", re.compile(r"/neo4j/cypher")),
    ("localhost:7474 browser link", re.compile(r"localhost:7474")),
    ("hardcoded materials123", re.compile(r"materials123")),
]


def _collect_active_py() -> list[Path]:
    """Collect all .py files under kg_engine/ except tests/."""
    files: list[Path] = []
    for p in sorted(_PKG_ROOT.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        files.append(p)
    return files


def _scan(path: Path, pattern: re.Pattern) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return hits
    for lineno, line in enumerate(text.splitlines(), start=1):
        if pattern.search(line):
            hits.append((lineno, line.rstrip()))
    return hits


def test_no_forbidden_references_in_active_package() -> None:
    """Scan all active .py files + surface docs for forbidden technology refs."""
    all_hits: dict[str, list[tuple[str, int, str]]] = {}

    for path in _collect_active_py():
        for label, pattern in _FORBIDDEN_PATTERNS:
            hits = _scan(path, pattern)
            for lineno, line in hits:
                key = str(path.relative_to(_REPO_ROOT))
                all_hits.setdefault(key, []).append((label, lineno, line))

    for surface in _SURFACE_FILES:
        if not surface.exists():
            continue
        for label, pattern in _FORBIDDEN_PATTERNS:
            hits = _scan(surface, pattern)
            for lineno, line in hits:
                key = str(surface.relative_to(_REPO_ROOT))
                all_hits.setdefault(key, []).append((label, lineno, line))

    if all_hits:
        detail_lines = []
        for filepath in sorted(all_hits):
            for label, lineno, line in all_hits[filepath]:
                detail_lines.append(f"  [{label}] {filepath}:{lineno}: {line}")
        raise AssertionError(
            "Forbidden references found in active package/surfaces:\n"
            + "\n".join(detail_lines)
        )
