"""Path normalization utilities for cross-platform compatibility."""
from __future__ import annotations

from pathlib import Path


def normalize_path(path: str | Path) -> Path:
    """Normalize a path string to handle Windows-style backslashes on POSIX systems.

    Converts backslashes to forward slashes to ensure paths work correctly
    on Linux/macOS even when they contain Windows-style separators.

    Args:
        path: Path string or Path object (may contain backslashes)

    Returns:
        Normalized Path object with forward slashes
    """
    if isinstance(path, Path):
        path_str = str(path)
    else:
        path_str = str(path)

    # Convert backslashes to forward slashes for POSIX compatibility
    # This handles Windows-style paths that may be stored in metadata
    normalized = path_str.replace("\\", "/")

    return Path(normalized)
