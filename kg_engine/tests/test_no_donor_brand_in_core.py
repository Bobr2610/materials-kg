"""Isolation guard for the active Materials KG public surface."""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_ACTIVE_SURFACES: list[Path] = [
    _REPO_ROOT / "README.md",
    _REPO_ROOT / "pyproject.toml",
    _REPO_ROOT / ".env.example",
    _REPO_ROOT / "kg_engine" / "api" / "materials_core.py",
    _REPO_ROOT / "kg_engine" / "config" / "settings.py",
]

_ACTIVE_DIRS: list[Path] = [
    _REPO_ROOT / "kg_engine" / "domain",
    _REPO_ROOT / "kg_engine" / "repositories",
    _REPO_ROOT / "kg_engine" / "services",
    _REPO_ROOT / "kg_engine" / "ingestion",
    _REPO_ROOT / "kg_engine" / "scripts" / "ingest_materials_kg.py",
    _REPO_ROOT / "kg_engine" / "scripts" / "run_materials_api.py",
    _REPO_ROOT / "kg_engine" / "tests" / "test_materials_kg_core.py",
    _REPO_ROOT / "kg_engine" / "tests" / "test_materials_api_smoke.py",
    _REPO_ROOT / "kg_engine" / "tests" / "test_repository_factory.py",
]

_LEGACY_EXCLUDES: list[Path] = [
    _REPO_ROOT / "kg_engine" / "agent",
    _REPO_ROOT / "kg_engine" / "api" / "app.py",
    _REPO_ROOT / "kg_engine" / "llm",
    _REPO_ROOT / "kg_engine" / "tools",
    _REPO_ROOT / "kg_engine" / "utils",
    _REPO_ROOT / "kg_engine" / "retrieval",
    _REPO_ROOT / "kg_engine" / "graph",
    _REPO_ROOT / "docs" / "mimo-runs",
]

_LEGACY_BRAND_PATTERN = re.compile(
    rf"\b{'c' + 'mw'}\b|{'comind' + 'ware'}|{'kb.' + 'comind' + 'ware.ru'}",
    re.IGNORECASE,
)


def _collect_py_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_file() and p.suffix == ".py":
            files.append(p)
        elif p.is_dir():
            files.extend(sorted(p.rglob("*.py")))
    return files


def _is_excluded(path: Path) -> bool:
    resolved = path.resolve()
    for exclude in _LEGACY_EXCLUDES:
        try:
            resolved.relative_to(exclude.resolve())
            return True
        except ValueError:
            continue
    return False


def _scan_file(path: Path) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return hits
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _LEGACY_BRAND_PATTERN.search(line):
            hits.append((lineno, line.rstrip()))
    return hits


def test_active_files_free_of_legacy_brand_references() -> None:
    all_hits: dict[str, list[tuple[int, str]]] = {}
    for surface in _ACTIVE_SURFACES:
        if surface.exists():
            hits = _scan_file(surface)
            if hits:
                all_hits[str(surface.relative_to(_REPO_ROOT))] = hits
    for path in _collect_py_files(_ACTIVE_DIRS):
        if _is_excluded(path):
            continue
        hits = _scan_file(path)
        if hits:
            all_hits[str(path.relative_to(_REPO_ROOT))] = hits
    if all_hits:
        detail_lines = []
        for filepath, hits in sorted(all_hits.items()):
            for lineno, line in hits:
                detail_lines.append(f"  {filepath}:{lineno}: {line}")
        msg = (
            "Legacy donor brand references found in active Materials KG surfaces:\n"
            + "\n".join(detail_lines)
        )
        raise AssertionError(msg)
