"""Tests for DocumentProcessor."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kg_engine.core.document_processor import Document, DocumentProcessor


class TestDocument:
    def test_stores_content_and_metadata(self) -> None:
        doc = Document(content="hello", metadata={"k": "v"})
        assert doc.content == "hello"
        assert doc.metadata == {"k": "v"}


class TestNormalizeBaseMetadata:
    def test_required_fields(self) -> None:
        meta = DocumentProcessor._normalize_base_metadata(
            kb_id="42",
            title="My Doc",
            source_file="/a/b.md",
            source_type="folder",
        )
        assert meta["kbId"] == "42"
        assert meta["title"] == "My Doc"
        assert meta["source_file"] == "/a/b.md"
        assert meta["source_type"] == "folder"
        assert meta["section_index"] == 0

    def test_section_index_override(self) -> None:
        meta = DocumentProcessor._normalize_base_metadata(
            kb_id="1",
            title="t",
            source_file="f",
            source_type="file",
            section_index=5,
        )
        assert meta["section_index"] == 5

    def test_extra_fields_merged(self) -> None:
        meta = DocumentProcessor._normalize_base_metadata(
            kb_id="1",
            title="t",
            source_file="f",
            source_type="folder",
            extra={"author": "Alice", "tags": ["x"]},
        )
        assert meta["author"] == "Alice"
        assert meta["tags"] == ["x"]

    def test_extra_does_not_override_canonical(self) -> None:
        meta = DocumentProcessor._normalize_base_metadata(
            kb_id="1",
            title="t",
            source_file="f",
            source_type="folder",
            extra={"kbId": "HACK", "title": "HACK"},
        )
        assert meta["kbId"] == "1"
        assert meta["title"] == "t"

    def test_none_extra_is_noop(self) -> None:
        meta = DocumentProcessor._normalize_base_metadata(
            kb_id="1", title="t", source_file="f", source_type="folder", extra=None,
        )
        assert "kbId" in meta


class TestProcessFolder:
    def test_raises_on_missing_folder(self, tmp_path: Path) -> None:
        proc = DocumentProcessor(mode="folder")
        with pytest.raises(FileNotFoundError):
            proc.process(str(tmp_path / "nonexistent"))

    def test_skips_files_without_kbid(self, tmp_path: Path) -> None:
        (tmp_path / "no_kbid.md").write_text("# Title\nBody")
        proc = DocumentProcessor(mode="folder")
        docs = proc.process(str(tmp_path))
        assert docs == []

    def test_processes_valid_md_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("---\nkbId: 1\ntitle: A\n---\nContent A")
        (tmp_path / "b.md").write_text("---\nkbId: 2\ntitle: B\n---\nContent B")
        proc = DocumentProcessor(mode="folder")
        docs = proc.process(str(tmp_path))
        assert len(docs) == 2
        assert {d.metadata["kbId"] for d in docs} == {"1", "2"}

    def test_max_files_limits_results(self, tmp_path: Path) -> None:
        for i in range(5):
            (tmp_path / f"f{i}.md").write_text(f"---\nkbId: {i}\ntitle: T{i}\n---\nBody {i}")
        proc = DocumentProcessor(mode="folder")
        docs = proc.process(str(tmp_path), max_files=2)
        assert len(docs) == 2

    def test_skip_list_for_unparseable(self, tmp_path: Path) -> None:
        (tmp_path / "good.md").write_text("---\nkbId: 1\ntitle: G\n---\nBody")
        bad = tmp_path / "bad.md"
        bad.write_bytes(b"\xff\xfe\x00\x01")  # invalid UTF-8
        proc = DocumentProcessor(mode="folder")
        docs = proc.process(str(tmp_path))
        assert len(docs) == 1


class TestProcessFile:
    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        proc = DocumentProcessor(mode="file")
        with pytest.raises(FileNotFoundError):
            proc.process(str(tmp_path / "nope.md"))

    def test_splits_by_headings(self, tmp_path: Path) -> None:
        content = "---\nkbId: 10\ntitle: Root\n---\n# Section A\nBody A\n# Section B\nBody B"
        f = tmp_path / "multi.md"
        f.write_text(content)
        proc = DocumentProcessor(mode="file")
        docs = proc.process(str(f))
        assert len(docs) >= 2
        assert all(d.metadata["kbId"] == "10" for d in docs)

    def test_returns_empty_when_no_kbid(self, tmp_path: Path) -> None:
        f = tmp_path / "nope.md"
        f.write_text("---\ntitle: No id\n---\nBody")
        proc = DocumentProcessor(mode="file")
        docs = proc.process(str(f))
        assert docs == []


class TestProcessMkdocs:
    def test_falls_back_to_folder_when_no_manifest(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("---\nkbId: 1\ntitle: A\n---\nBody")
        proc = DocumentProcessor(mode="mkdocs")
        docs = proc.process(str(tmp_path))
        assert len(docs) == 1

    def test_reads_manifest(self, tmp_path: Path) -> None:
        (tmp_path / "page.md").write_text("---\nkbId: 99\ntitle: Page\n---\nContent")
        manifest = {"total_files": 1, "files": ["page.md"]}
        (tmp_path / "rag_manifest.json").write_text(json.dumps(manifest))
        proc = DocumentProcessor(mode="mkdocs")
        docs = proc.process(str(tmp_path))
        assert len(docs) == 1
        assert docs[0].metadata["kbId"] == "99"

    def test_max_files_limits_manifest(self, tmp_path: Path) -> None:
        for i in range(3):
            (tmp_path / f"p{i}.md").write_text(f"---\nkbId: {i}\ntitle: T{i}\n---\nBody")
        manifest = {"total_files": 3, "files": [f"p{i}.md" for i in range(3)]}
        (tmp_path / "rag_manifest.json").write_text(json.dumps(manifest))
        proc = DocumentProcessor(mode="mkdocs")
        docs = proc.process(str(tmp_path), max_files=1)
        assert len(docs) == 1


class TestProcessUnknownMode:
    def test_raises_value_error(self, tmp_path: Path) -> None:
        proc = DocumentProcessor(mode="unknown")
        with pytest.raises(ValueError, match="Unknown mode"):
            proc.process(str(tmp_path))


class TestSplitByHeadings:
    def test_splits_h1(self) -> None:
        proc = DocumentProcessor(mode="file")
        sections = proc._split_by_headings("# A\nbody_a\n# B\nbody_b")
        assert len(sections) == 2
        assert sections[0][0] == "A"
        assert sections[1][0] == "B"

    def test_no_headings_returns_single(self) -> None:
        proc = DocumentProcessor(mode="file")
        sections = proc._split_by_headings("Just some text")
        assert len(sections) == 1
        assert sections[0][0] is None
