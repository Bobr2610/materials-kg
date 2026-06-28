"""Core document processing components."""

__all__ = ["RAGIndexer", "guard_client"]


def __getattr__(name: str):
    if name == "RAGIndexer":
        from kg_engine.core.indexer import RAGIndexer
        return RAGIndexer
    if name == "guard_client":
        from kg_engine.core.guard_client import guard_client
        return guard_client
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


