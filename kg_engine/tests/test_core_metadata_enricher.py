"""Tests for metadata_enricher."""
from __future__ import annotations

from kg_engine.core.metadata_enricher import detect_code_languages, enrich_metadata


class TestDetectCodeLanguages:
    def test_returns_empty_for_no_code(self) -> None:
        assert detect_code_languages("plain text") == []

    def test_detects_python(self) -> None:
        result = detect_code_languages("```python\nprint('hi')\n```")
        assert result == ["python"]

    def test_detects_multiple_languages(self) -> None:
        text = "```python\nx=1\n```\n```javascript\nconsole.log()\n```"
        result = detect_code_languages(text)
        assert result == ["javascript", "python"]  # sorted, deduped

    def test_deduplicates(self) -> None:
        text = "```python\na\n```\n```Python\nb\n```"
        result = detect_code_languages(text)
        assert result == ["python"]

    def test_unlabeled_fence_ignored(self) -> None:
        result = detect_code_languages("```\nsome code\n```")
        assert result == []


class TestEnrichMetadata:
    def test_adds_chunk_index(self) -> None:
        meta = enrich_metadata({"kbId": "1"}, "hello", 3)
        assert meta["chunk_index"] == 3

    def test_detects_code(self) -> None:
        meta = enrich_metadata({}, "```python\nprint()\n```", 0)
        assert meta["has_code"] is True
        assert meta["code_languages"] == ["python"]

    def test_no_code_when_plain(self) -> None:
        meta = enrich_metadata({}, "no code here", 0)
        assert meta["has_code"] is False
        assert meta["code_languages"] == []

    def test_char_count(self) -> None:
        meta = enrich_metadata({}, "abc", 0)
        assert meta["char_count"] == 3

    def test_preserves_base_metadata(self) -> None:
        base = {"kbId": "5", "title": "T"}
        meta = enrich_metadata(base, "body", 0)
        assert meta["kbId"] == "5"
        assert meta["title"] == "T"
        assert meta["chunk_index"] == 0
