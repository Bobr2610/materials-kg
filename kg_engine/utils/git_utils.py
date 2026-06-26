"""Git utilities for file timestamp retrieval."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from kg_engine.utils.metadata_utils import _epoch_to_iso, parse_frontmatter_timestamp


def get_git_timestamp(file_path: str | Path) -> tuple[int | None, str | None]:
    """Get the last commit timestamp for a file from Git.

    The function automatically detects which Git repository contains the file,
    even if files come from different repositories.

    Args:
        file_path: Path to the file (absolute or relative, may contain Windows-style backslashes)

    Returns:
        Tuple of (epoch: int, iso_string: str) or (None, None) on failure
    """
    try:
        from kg_engine.utils.path_utils import normalize_path

        # Normalize path to handle Windows-style backslashes on POSIX systems
        file_path = normalize_path(file_path)
        if not file_path.is_absolute():
            file_path = file_path.resolve()

        if not file_path.exists():
            return None, None

        work_dir = file_path.parent

        # Find the Git repository root that contains this file
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )

        if result.returncode != 0:
            return None, None

        repo_root = Path(result.stdout.strip()).resolve()

        # Get relative path from repository root
        try:
            rel_path = file_path.relative_to(repo_root)
        except ValueError:
            return None, None

        # Get last commit timestamp for this specific file
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--follow", "--", str(rel_path)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )

        if result.returncode != 0 or not result.stdout.strip():
            return None, None

        epoch = int(result.stdout.strip())
        iso_string = _epoch_to_iso(epoch)
        return epoch, iso_string

    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None, None
    except Exception:  # noqa: BLE001
        return None, None


def get_file_timestamp(
    source_file: str | Path | None, base_meta: dict[str, Any]
) -> tuple[int | None, str | None, str]:
    """Get file timestamp using three-tier fallback: frontmatter → Git → file stat.

    Args:
        source_file: Path to the source file (can be None)
        base_meta: Document metadata dict (may contain 'updated' from frontmatter)

    Returns:
        Tuple of (epoch: int | None, iso_string: str | None, source: str)
        where source is one of: "frontmatter", "git", "file", or "none"
    """
    # Tier 1: Frontmatter updated field
    updated_str = base_meta.get("updated")
    if updated_str:
        epoch, iso_string = parse_frontmatter_timestamp(str(updated_str))
        if epoch is not None and iso_string is not None:
            return epoch, iso_string, "frontmatter"

    # Tier 2: Git commit timestamp
    if source_file:
        epoch, iso_string = get_git_timestamp(source_file)
        if epoch is not None and iso_string is not None:
            return epoch, iso_string, "git"

    # Tier 3: File modification date
    if source_file:
        try:
            from kg_engine.utils.path_utils import normalize_path

            p = normalize_path(source_file)
            if p.exists():
                stat = p.stat()
                epoch = int(stat.st_mtime)
                iso_string = _epoch_to_iso(epoch)
                return epoch, iso_string, "file"
        except Exception:  # noqa: BLE001
            pass

    return None, None, "none"

