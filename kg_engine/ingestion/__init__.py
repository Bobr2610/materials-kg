"""Source-family ingestion adapters for the graph-first materials KG core."""

from kg_engine.ingestion.adapters import DocumentCorpusAdapter
from kg_engine.ingestion.adapters import ExperimentCatalogAdapter
from kg_engine.ingestion.adapters import ReferenceDataAdapter
from kg_engine.ingestion.adapters import StaffDirectoryAdapter
from kg_engine.ingestion.adapters import TagCatalogAdapter
from kg_engine.ingestion.document_blocks import DocumentBlock
from kg_engine.ingestion.document_blocks import DocumentBlockParser
from kg_engine.ingestion.document_blocks import DocumentParseSettings
from kg_engine.ingestion.document_blocks import PageImage
from kg_engine.ingestion.document_blocks import blocks_to_document_input
from kg_engine.ingestion.document_blocks import parse_document_file

__all__ = [
    "DocumentBlock",
    "DocumentBlockParser",
    "DocumentCorpusAdapter",
    "DocumentParseSettings",
    "ExperimentCatalogAdapter",
    "PageImage",
    "ReferenceDataAdapter",
    "StaffDirectoryAdapter",
    "TagCatalogAdapter",
    "blocks_to_document_input",
    "parse_document_file",
]
