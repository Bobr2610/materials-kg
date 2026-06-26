"""Device detection utilities for GPU/CPU selection."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def detect_device(preferred: str = "auto") -> str:
    """Detect the best available device for model inference.

    Args:
        preferred: Preferred device. Options:
            - "auto": Auto-detect (use CUDA if available, else CPU)
            - "cuda": Use CUDA if available, else fallback to CPU
            - "cpu": Force CPU usage

    Returns:
        Device string: "cuda" or "cpu"
    """
    if preferred == "cpu":
        return "cpu"

    try:
        import torch

        if torch.cuda.is_available():
            device_count = torch.cuda.device_count()
            device_name = torch.cuda.get_device_name(0) if device_count > 0 else "Unknown"
            logger.info(
                "GPU detected: %s (device count: %d). Using CUDA for embeddings.",
                device_name,
                device_count,
            )
            return "cuda"
        else:
            logger.info("CUDA not available. Using CPU for embeddings.")
            return "cpu"
    except ImportError:
        logger.warning(
            "PyTorch not available. Cannot detect GPU. Using CPU for embeddings."
        )
        return "cpu"
    except Exception as e:
        logger.warning(
            "Error detecting GPU: %s. Falling back to CPU for embeddings.", e
        )
        return "cpu"
