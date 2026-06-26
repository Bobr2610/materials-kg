"""LangChain tools for knowledge graph querying."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, Field

from kg_engine.graph.pipeline import GraphPipeline
from kg_engine.utils.context_tracker import AgentContext

logger = logging.getLogger(__name__)

_pipeline: GraphPipeline | None = None


def set_graph_pipeline(pipeline: GraphPipeline | None) -> None:
    global _pipeline
    _pipeline = pipeline


def get_pipeline() -> GraphPipeline:
    if _pipeline is None:
        raise RuntimeError("GraphPipeline not initialized. Call set_graph_pipeline() first.")
    return _pipeline


class QueryMaterialSchema(BaseModel):
    """Query the knowledge graph for information about a specific material.

    Returns properties, experiments, processing modes, and related entities
    for the given material. Supports optional mode filtering.
    """

    material_name: str = Field(..., description="Material name or alloy designation (e.g. Ti6Al4V, Al6061)", min_length=1)
    mode_name: str | None = Field(default=None, description="Optional processing mode filter (e.g. heat treatment, deformation)")


@tool("query_material", args_schema=QueryMaterialSchema, description=QueryMaterialSchema.__doc__)
def query_material(
    material_name: str,
    mode_name: str | None = None,
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> str:
    """Query materials knowledge graph for alloy information.

    Args:
        material_name: Material name or alloy designation
        mode_name: Optional processing mode to filter results

    Returns:
        JSON string with material data, properties, experiments, modes
    """
    try:
        pipeline = get_pipeline()
        result = pipeline.ask(query=material_name, mode=mode_name)
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    except Exception as exc:
        logger.error("Failed to query material '%s': %s", material_name, exc)
        return json.dumps({"error": str(exc), "material": material_name}, ensure_ascii=False)


class QueryPropertySchema(BaseModel):
    """Search for materials by property name and optional value range."""

    property_name: str = Field(..., description="Property name (e.g. strength, hardness, corrosion resistance)", min_length=1)
    min_value: float | None = Field(default=None, description="Minimum property value filter")
    max_value: float | None = Field(default=None, description="Maximum property value filter")


@tool("query_property", args_schema=QueryPropertySchema, description=QueryPropertySchema.__doc__)
def query_property(
    property_name: str,
    min_value: float | None = None,
    max_value: float | None = None,
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> str:
    """Query materials knowledge graph by property name and value range.

    Args:
        property_name: Property to search for
        min_value: Optional minimum value filter
        max_value: Optional maximum value filter

    Returns:
        JSON string with materials matching the property criteria
    """
    try:
        pipeline = get_pipeline()
        results = pipeline.query.query_by_property(property_name, min_value, max_value)
        return json.dumps(results, ensure_ascii=False, separators=(",", ":"))
    except Exception as exc:
        logger.error("Failed to query property '%s': %s", property_name, exc)
        return json.dumps({"error": str(exc), "property": property_name}, ensure_ascii=False)


class QueryRelatedSchema(BaseModel):
    """Find entities related to a given entity name in the knowledge graph."""

    entity_name: str = Field(..., description="Entity name to find relations for", min_length=1)
    max_depth: int = Field(default=2, description="Maximum traversal depth (1-5)", ge=1, le=5)


@tool("query_related", args_schema=QueryRelatedSchema, description=QueryRelatedSchema.__doc__)
def query_related(
    entity_name: str,
    max_depth: int = 2,
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> str:
    """Find related entities in the knowledge graph by name.

    Args:
        entity_name: Name to search for
        max_depth: How many hops to traverse

    Returns:
        JSON string with related entities and their connections
    """
    try:
        pipeline = get_pipeline()
        results = pipeline.query.query_related(entity_name, max_depth=max_depth)
        return json.dumps(results, ensure_ascii=False, separators=(",", ":"))
    except Exception as exc:
        logger.error("Failed to query related '%s': %s", entity_name, exc)
        return json.dumps({"error": str(exc), "entity": entity_name}, ensure_ascii=False)


@tool("graph_data_gaps")
def graph_data_gaps(
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> str:
    """Identify missing data combinations in the knowledge graph.

    Returns materials without measured properties for known property types,
    and materials without experiments under known processing modes.

    Returns:
        JSON string listing data gaps and missing combinations
    """
    try:
        pipeline = get_pipeline()
        gaps = pipeline.find_gaps()
        return json.dumps(gaps, ensure_ascii=False, separators=(",", ":"))
    except Exception as exc:
        logger.error("Failed to find data gaps: %s", exc)
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


@tool("graph_stats")
def graph_stats(
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> str:
    """Get statistics about the knowledge graph.

    Returns entity counts by type, total relations, and overall graph size.

    Returns:
        JSON string with graph statistics
    """
    try:
        pipeline = get_pipeline()
        stats = pipeline.stats()
        return json.dumps(stats, ensure_ascii=False, separators=(",", ":"))
    except Exception as exc:
        logger.error("Failed to get graph stats: %s", exc)
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
