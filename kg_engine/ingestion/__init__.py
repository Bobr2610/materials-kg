"""Source-family ingestion adapters for the graph-first materials KG core."""

from kg_engine.ingestion.adapters import DocumentCorpusAdapter
from kg_engine.ingestion.adapters import ExperimentCatalogAdapter
from kg_engine.ingestion.adapters import ReferenceDataAdapter
from kg_engine.ingestion.adapters import StaffDirectoryAdapter
from kg_engine.ingestion.adapters import TagCatalogAdapter

__all__ = [
    "DocumentCorpusAdapter",
    "ExperimentCatalogAdapter",
    "ReferenceDataAdapter",
    "StaffDirectoryAdapter",
    "TagCatalogAdapter",
]
