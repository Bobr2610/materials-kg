"""Shared thread pool executor for blocking I/O operations.

Provides a singleton thread pool executor for running blocking operations
in async contexts without blocking the event loop.
"""
from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")

# Shared thread pool executor for I/O-bound operations
# Default max_workers=8 should handle concurrent requests efficiently
_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def get_executor() -> ThreadPoolExecutor:
    """Get or create the shared thread pool executor.

    Thread-safe singleton pattern for thread pool initialization.

    Returns:
        ThreadPoolExecutor instance (singleton)
    """
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="rag-io")
    return _executor


async def run_in_thread_pool(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a blocking function in the thread pool executor.

    This allows blocking I/O operations (ChromaDB, embedding, file I/O)
    to run without blocking the async event loop.

    Args:
        func: Blocking function to execute
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        Result of func(*args, **kwargs)

    Example:
        >>> async def example():
        ...     result = await run_in_thread_pool(blocking_function, arg1, arg2)
    """
    executor = get_executor()
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, lambda: func(*args, **kwargs))
