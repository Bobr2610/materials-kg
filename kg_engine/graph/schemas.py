"""Pydantic schemas for materials knowledge graph entities and relationships."""

from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, Field


class EntityType(str, enum.Enum):
    """Types of entities in the materials knowledge graph."""

    MATERIAL = "material"
    PROPERTY = "property"
    EXPERIMENT = "experiment"
    MODE = "mode"
    EQUIPMENT = "equipment"
    TEAM = "team"
    ARTICLE = "article"
    CONCLUSION = "conclusion"


class RelationType(str, enum.Enum):
    """Types of relationships between entities."""

    HAS_PROPERTY = "has_property"
    USED_IN = "used_in"
    MEASURES = "measures"
    USES_EQUIPMENT = "uses_equipment"
    HAS_MODE = "has_mode"
    CONDUCTED_BY = "conducted_by"
    DESCRIBED_IN = "described_in"
    HAS_CONCLUSION = "has_conclusion"
    DEPENDS_ON = "depends_on"
    COMPOSED_OF = "composed_of"
    COMPARED_TO = "compared_to"
    OPTIMIZED_FOR = "optimized_for"


class GraphEntity(BaseModel):
    """A node in the knowledge graph."""

    id: str = Field(description="Unique identifier for the entity")
    type: EntityType = Field(description="Entity type")
    name: str = Field(description="Human-readable name")
    aliases: list[str] = Field(default_factory=list, description="Alternative names")
    properties: dict[str, Any] = Field(default_factory=dict, description="Arbitrary key-value properties")
    source: str | None = Field(default=None, description="Source document identifier")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence score")


class GraphRelation(BaseModel):
    """An edge in the knowledge graph."""

    source_id: str = Field(description="Source entity ID")
    target_id: str = Field(description="Target entity ID")
    type: RelationType = Field(description="Relationship type")
    properties: dict[str, Any] = Field(default_factory=dict, description="Edge properties (e.g. value, unit)")
    source: str | None = Field(default=None, description="Source document identifier")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence score")


ExtractionResult = dict[str, list[GraphEntity] | list[GraphRelation]]
"""Type alias: {entities: [...], relations: [...]}"""
