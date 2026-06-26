from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(level: int = logging.INFO, log_dir: str | None = None) -> None:
    """Setup logging with both console and file output.

    Args:
        level: Logging level (default: INFO)
        log_dir: Directory for log files. If None, uses ./logs
    """
    if logging.getLogger().handlers:
        return

    # Setup log directory
    if log_dir is None:
        log_dir = os.environ.get("LOG_DIR", "./logs")
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)

    # File handler with rotation (10MB per file, keep 5 backups)
    log_file = log_path / "agent.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    # Configure root logger
    logging.basicConfig(level=level, handlers=[console_handler, file_handler])

    # Log startup message
    logging.getLogger(__name__).info("Logging initialized - console and file: %s", log_file)


