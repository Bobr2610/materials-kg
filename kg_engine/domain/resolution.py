"""Canonical name resolution helpers for reference-first ingestion."""

from __future__ import annotations

import re

from kg_engine.domain.models import Entity

_SEPARATOR_PATTERN = re.compile(r"[^a-z0-9]+")


def normalize_name(value: str) -> str:
    """Normalize a name for alias matching across noisy scientific sources."""
    lowered = value.strip().lower()
    collapsed = _SEPARATOR_PATTERN.sub("", lowered)
    return collapsed


class ReferenceResolver:
    """Resolve raw names to canonical entities using alias normalization."""

    def __init__(self, entities: list[Entity]) -> None:
        self._index: dict[str, Entity] = {}
        for entity in entities:
            names = [entity.canonical_name, *entity.aliases]
            for name in names:
                self._index[normalize_name(name)] = entity

    def resolve(self, raw_name: str) -> Entity | None:
        """Return the canonical entity if a normalized alias match exists."""
        return self._index.get(normalize_name(raw_name))
