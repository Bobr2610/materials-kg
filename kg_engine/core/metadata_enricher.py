"""Minimal metadata enrichment utilities."""
from __future__ import annotations

import re
from typing import Any, Dict, List


CODE_BLOCK_PATTERN = re.compile(r"```(\w+)?[\s\S]*?```", re.MULTILINE)


def detect_code_languages(text: str) -> List[str]:
    languages: List[str] = []
    for match in CODE_BLOCK_PATTERN.finditer(text):
        lang = match.group(1)
        if lang:
            languages.append(lang.lower())
    return sorted(set(languages))


def enrich_metadata(base_meta: Dict[str, Any], content: str, chunk_index: int) -> Dict[str, Any]:
    has_code = bool(CODE_BLOCK_PATTERN.search(content))
    code_languages = detect_code_languages(content) if has_code else []
    char_count = len(content)

    enriched = dict(base_meta)
    enriched.update(
        {
            "chunk_index": chunk_index,
            "has_code": has_code,
            "code_languages": code_languages,
            "char_count": char_count,
        }
    )
    return enriched


