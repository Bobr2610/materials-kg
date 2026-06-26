"""Disk space checking utilities for model downloads."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def get_free_space_gb(path: Path | str) -> float:
    """Get free disk space in GB for the given path.

    Args:
        path: Path to check disk space for

    Returns:
        Free space in GB, or -1 if unable to determine
    """
    try:
        path_obj = Path(path).resolve()
        if path_obj.exists():
            stat = shutil.disk_usage(path_obj)
        else:
            # If path doesn't exist, check parent directory
            stat = shutil.disk_usage(path_obj.parent if path_obj.parent.exists() else Path.cwd())
        return stat.free / (1024**3)  # Convert to GB
    except Exception as e:
        logger.warning(f"Unable to determine free disk space: {e}")
        return -1.0


def check_disk_space_available(
    required_gb: float,
    path: Path | str | None = None,
    cache_dir: Path | str | None = None,
) -> tuple[bool, float, str]:
    """Check if sufficient disk space is available.

    Checks both the specified path and cache_dir, using the minimum available space.
    Useful when models are cached separately from the working directory.

    Args:
        required_gb: Required space in GB
        path: Path to check (defaults to current working directory)
        cache_dir: HuggingFace cache directory to check (optional)

    Returns:
        Tuple of (is_available, free_gb, message)
    """
    check_paths = [Path(path) if path else Path.cwd()]
    if cache_dir:
        check_paths.append(Path(cache_dir))

    # Get free space for all paths, filter out invalid results, take minimum
    space_values = [get_free_space_gb(p) for p in check_paths]
    valid_spaces = [s for s in space_values if s >= 0]
    
    if not valid_spaces:
        return True, -1.0, "Unable to check disk space - proceeding with caution"
    
    free_gb = min(valid_spaces)

    buffer_multiplier = 1.2  # 20% buffer for safety
    required_with_buffer = required_gb * buffer_multiplier
    available = free_gb >= required_with_buffer

    if available:
        message = f"Sufficient disk space: {free_gb:.2f} GB available (requires {required_gb:.2f} GB)"
    else:
        needed = required_with_buffer - free_gb
        message = (
            f"Insufficient disk space: {free_gb:.2f} GB available, "
            f"but {required_gb:.2f} GB required (with 20% buffer: {required_with_buffer:.2f} GB). "
            f"Please free up at least {needed:.2f} GB of space."
        )

    return available, free_gb, message


def get_huggingface_cache_dir() -> Path | None:
    """Get HuggingFace cache directory path.

    Returns:
        Path to HuggingFace cache directory, or None if unable to determine
    """
    try:
        import os

        # Try HF_HOME first
        hf_home = os.getenv("HF_HOME")
        if hf_home:
            return Path(hf_home) / "hub"

        # Try default cache location
        cache_home = os.getenv("XDG_CACHE_HOME") or (Path.home() / ".cache")
        if isinstance(cache_home, str):
            cache_home = Path(cache_home)
        return cache_home / "huggingface" / "hub"
    except Exception as e:
        logger.warning(f"Unable to determine HuggingFace cache directory: {e}")
        return None

