"""Unified document processor for all 3 input modes."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class Document:
    """Parsed document with metadata."""

    def __init__(self, content: str, metadata: dict[str, Any]):
        self.content = content
        self.metadata = metadata


class DocumentProcessor:
    """Process documents from folder, file, or mkdocs export."""

    def __init__(self, mode: str = "folder"):
        """Initialize processor.

        Args:
            mode: 'folder', 'file', or 'mkdocs'
        """
        self.mode = mode
        logger.info("DocumentProcessor initialized in %s mode", mode)

    def process(self, source: str, max_files: int | None = None) -> list[Document]:
        """Process documents from source.

        Args:
            source: Path to folder, file, or mkdocs export

        Returns:
            List of parsed documents with metadata
        """
        if self.mode == "folder":
            return self._process_folder(source, max_files=max_files)
        if self.mode == "file":
            return self._process_file(source)
        if self.mode == "mkdocs":
            return self._process_mkdocs(source, max_files=max_files)
        raise ValueError(f"Unknown mode: {self.mode}")

    @staticmethod
    def _normalize_base_metadata(
        *,
        kb_id: str,
        title: str,
        source_file: str,
        source_type: str,
        section_index: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Produce a uniform base metadata schema across all modes.

        Fields always present:
        - kbId: stable document identifier (string)
        - title: human-friendly title (string)
        - source_file: absolute path to the source markdown file (string)
        - source_type: one of {folder, file, mkdocs} (string)
        - section_index: integer section index (0 when not applicable)

        Any additional parsed fields are merged in "extra".
        """
        meta: dict[str, Any] = {
            "kbId": kb_id,
            "title": title,
            "source_file": source_file,
            "source_type": source_type,
            "section_index": section_index if section_index is not None else 0,
        }
        if extra:
            # Do not let extras override canonical keys unless explicitly intended
            for k, v in extra.items():
                if k not in meta:
                    meta[k] = v
        return meta

    def _process_folder(self, folder_path: str, max_files: int | None = None) -> list[Document]:
        """Mode 3: Scan folder for MD files."""
        folder = Path(folder_path)
        if not folder.exists():
            raise FileNotFoundError(f"Folder not found: {folder_path}")

        documents: list[Document] = []
        md_files = list(folder.rglob("*.md"))
        md_files.sort()
        if max_files is not None and max_files >= 0:
            md_files = md_files[:max_files]
        logger.info("Found %d markdown files in %s", len(md_files), folder_path)

        for md_file in md_files:
            try:
                content, fm = self._parse_md_with_frontmatter(md_file)
                # Require numeric kbId from frontmatter; skip if missing
                kb_id = fm.get("kbId")
                if not kb_id:
                    logger.warning("Skipping %s: missing kbId in frontmatter", md_file)
                    continue
                base = self._normalize_base_metadata(
                    kb_id=str(kb_id),
                    title=fm.get("title") or md_file.stem,
                    source_file=str(md_file),
                    source_type="folder",
                    section_index=0,
                    extra=fm,
                )
                documents.append(Document(content, base))
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to process %s: %s", md_file, exc)
                continue

        logger.info("Successfully processed %d documents", len(documents))
        return documents

    def _process_file(self, file_path: str) -> list[Document]:
        """Mode 2: Parse single large MD file."""
        file = Path(file_path)
        if not file.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        logger.info("Processing single file: %s", file_path)
        # Parse frontmatter if present, then split the remainder by headings
        content, fm = self._parse_md_with_frontmatter(file)
        # Require numeric kbId from frontmatter; skip entire file if missing
        kb_id = fm.get("kbId")
        if not kb_id:
            logger.warning("Skipping %s: missing kbId in frontmatter", file_path)
            return []
        
        sections = self._split_by_headings(content)

        documents: list[Document] = []
        for i, (title, section_content) in enumerate(sections):
            # Use same numeric kbId from frontmatter for all sections
            base = self._normalize_base_metadata(
                kb_id=str(kb_id),
                title=title or f"Section {i}",
                source_file=str(file),
                source_type="file",
                section_index=i,
                extra=fm,
            )
            documents.append(Document(section_content, base))

        logger.info("Split file into %d sections", len(documents))
        return documents

    def _process_mkdocs(self, export_dir: str, max_files: int | None = None) -> list[Document]:
        """Mode 1: Process MkDocs export with manifest."""
        export_path = Path(export_dir)
        manifest_file = export_path / "rag_manifest.json"

        if not manifest_file.exists():
            logger.warning("No manifest found, falling back to folder mode")
            return self._process_folder(export_dir)

        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        logger.info("Processing MkDocs export: %s files", manifest.get("total_files"))

        documents: list[Document] = []
        files_iter = manifest.get("files", [])
        if max_files is not None and max_files >= 0:
            files_iter = files_iter[:max_files]
        for file_path in files_iter:
            md_file = export_path / file_path
            if md_file.exists():
                content, fm = self._parse_md_with_frontmatter(md_file)
                # Require numeric kbId from frontmatter; skip if missing
                kb_id = fm.get("kbId")
                if not kb_id:
                    logger.warning("Skipping %s: missing kbId in frontmatter", md_file)
                    continue
                base = self._normalize_base_metadata(
                    kb_id=str(kb_id),
                    title=fm.get("title") or md_file.stem,
                    source_file=str(md_file),
                    source_type="mkdocs",
                    section_index=0,
                    extra=fm,
                )
                documents.append(Document(content, base))

        logger.info("Processed %d MkDocs documents", len(documents))
        return documents

    def _parse_md_with_frontmatter(self, file_path: Path) -> tuple[str, dict[str, Any]]:
        """Parse markdown file with optional YAML frontmatter."""
        content = file_path.read_text(encoding="utf-8")

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1])
                    return parts[2].strip(), frontmatter or {}
                except yaml.YAMLError as exc:  # noqa:TRY003
                    logger.warning("Failed to parse frontmatter in %s: %s", file_path, exc)

        return content, {}

    def _split_by_headings(self, content: str) -> list[tuple[str | None, str]]:
        """Split content by H1 headings."""
        lines = content.split("\n")
        sections: list[tuple[str | None, str]] = []
        current_title: str | None = None
        current_content: list[str] = []

        for line in lines:
            if line.startswith("# "):
                if current_content:
                    sections.append((current_title, "\n".join(current_content)))
                current_title = line[2:].strip()
                current_content = [line]
            else:
                current_content.append(line)

        if current_content:
            sections.append((current_title, "\n".join(current_content)))

        return sections


