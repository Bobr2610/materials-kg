"""Format-neutral contracts produced by document readers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic import Field


class IngestionWarning(BaseModel):
    """Non-fatal issue associated with a source or fragment."""

    code: str
    severity: str = "warning"
    message: str
    locator: dict[str, Any] = Field(default_factory=dict)


class ParsedFragment(BaseModel):
    """Addressable text fragment with source coordinates."""

    kind: str = "text"
    content: str
    locator: dict[str, Any] = Field(default_factory=dict)
    language: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ParsedTable(BaseModel):
    """Table retaining cell values and its position in the source."""

    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    locator: dict[str, Any] = Field(default_factory=dict)


class ParsedSource(BaseModel):
    """Unified output of all supported document readers."""

    name: str
    media_type: str
    checksum: str
    parser_version: str = "1"
    language: str | None = None
    fragments: list[ParsedFragment] = Field(default_factory=list)
    tables: list[ParsedTable] = Field(default_factory=list)
    warnings: list[IngestionWarning] = Field(default_factory=list)
