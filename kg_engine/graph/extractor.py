"""LLM-powered entity and relationship extraction from materials science texts."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from kg_engine.graph.schemas import (
    EntityType,
    GraphEntity,
    GraphRelation,
    RelationType,
)

logger = logging.getLogger(__name__)

# Regex patterns for materials science entities
_MATERIAL_PATTERN = re.compile(
    r"(?i)\b("
    r"(?:[A-Z][a-z]?\d*)+"                   # Ti6Al4V, Al2O3, Al
    r"(?:\s*[-–/]\s*[A-Z][a-z]?\d*)?"       # Al-Si, Ti/Al
    r")\b"
)

_PROPERTY_PATTERN = re.compile(
    r"(?i)(?:"
    r"(?:прочность|твердость|пластичность|вязкость|модуль|"
    r"strength|hardness|ductility|toughness|modulus|"
    r"предел\s+текучести|предел\s+прочности|относительное\s+удлинение|"
    r"yield\s+strength|tensile\s+strength|elongation|"
    r"коррозионная\s+стойкость|corrosion\s+resistance|"
    r"износостойкость|wear\s+resistance|"
    r"теплопроводность|thermal\s+conductivity|"
    r"электропроводность|electrical\s+conductivity"
    r")"
    r")"
)

_EXTRACTION_PROMPT_TEMPLATE = """You are a materials science entity extractor. Extract entities and relationships from the text below.

## Entity types
- **material**: metals, alloys, ceramics, polymers, composites
- **property**: mechanical, thermal, electrical, physical properties
- **experiment**: test name, experiment description
- **mode**: processing mode (e.g. heat treatment, deformation mode), test conditions
- **equipment**: devices, machines, tools, instruments
- **team**: research groups, laboratories, universities, authors
- **conclusion**: findings, results, observations

## Relationship types
- **has_property**: material -> property (with value and units in properties)
- **used_in**: material -> experiment
- **measures**: experiment -> property
- **uses_equipment**: experiment -> equipment
- **has_mode**: material/experiment -> mode
- **conducted_by**: experiment -> team
- **described_in**: experiment -> article (source document id)
- **has_conclusion**: experiment -> conclusion
- **depends_on**: general dependency between entities
- **composed_of**: material -> material (for composites/alloys)

## Output format
Return ONLY valid JSON with no markdown wrapping or extra text:
```json
{{
  "entities": [
    {{"id": "unique_string_id", "type": "material", "name": "Entity Name", "properties": {{"key": "value"}}}}
  ],
  "relations": [
    {{"source_id": "...", "target_id": "...", "type": "has_property", "properties": {{"value": "500", "unit": "MPa"}}}}
  ]
}}
```

## Text
{text}
"""


class EntityExtractor:
    """Extract materials science entities and relations from text using regex and LLM."""

    def __init__(self, llm_manager: Any | None = None) -> None:
        self._llm_manager = llm_manager
        self._entity_counter: int = 0

    def _next_id(self, prefix: str) -> str:
        self._entity_counter += 1
        return f"{prefix}_{self._entity_counter}"

    def extract_regex(self, text: str, source: str | None = None) -> list[GraphEntity]:
        entities: list[GraphEntity] = []
        seen: set[str] = set()

        for match in _MATERIAL_PATTERN.finditer(text):
            name = match.group(0).strip()
            if name.lower() not in seen and len(name) > 1:
                seen.add(name.lower())
                entities.append(
                    GraphEntity(
                        id=self._next_id("mat"),
                        type=EntityType.MATERIAL,
                        name=name,
                        source=source,
                        confidence=0.5,
                    )
                )

        for match in _PROPERTY_PATTERN.finditer(text):
            name = match.group(0).strip().lower()
            if name not in seen:
                seen.add(name)
                entities.append(
                    GraphEntity(
                        id=self._next_id("prop"),
                        type=EntityType.PROPERTY,
                        name=name,
                        source=source,
                        confidence=0.5,
                    )
                )

        return entities

    def extract_with_llm(
        self,
        text: str,
        source: str | None = None,
    ) -> tuple[list[GraphEntity], list[GraphRelation]]:
        prompt = _EXTRACTION_PROMPT_TEMPLATE.format(text=text[:8000])

        if self._llm_manager is None:
            logger.warning("No LLM manager provided, using regex-only extraction")
            return self.extract_regex(text, source), []

        try:
            response = self._llm_manager.generate(prompt)
            raw = response.strip()
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            data = json.loads(raw)
            entities = [
                GraphEntity(
                    id=e.get("id", self._next_id("llm")),
                    type=EntityType(e.get("type", "material")),
                    name=e.get("name", ""),
                    aliases=e.get("aliases", []),
                    properties=e.get("properties", {}),
                    source=source or e.get("source"),
                    confidence=e.get("confidence", 0.7),
                )
                for e in data.get("entities", [])
            ]
            relations = [
                GraphRelation(
                    source_id=r["source_id"],
                    target_id=r["target_id"],
                    type=RelationType(r.get("type", "depends_on")),
                    properties=r.get("properties", {}),
                    source=source or r.get("source"),
                    confidence=r.get("confidence", 0.7),
                )
                for r in data.get("relations", [])
            ]
            return entities, relations

        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("LLM extraction failed: %s. Falling back to regex.", exc)
            return self.extract_regex(text, source), []

    def extract(
        self,
        text: str,
        source: str | None = None,
        use_llm: bool = True,
    ) -> tuple[list[GraphEntity], list[GraphRelation]]:
        if use_llm and self._llm_manager is not None:
            entities, relations = self.extract_with_llm(text, source)
            if entities:
                return entities, relations

        regex_entities = self.extract_regex(text, source)
        return regex_entities, []
