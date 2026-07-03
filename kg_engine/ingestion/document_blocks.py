"""Document parsing layer that normalizes files into provenance-rich blocks."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
import re
from typing import Any

from pydantic import BaseModel
from pydantic import Field

from kg_engine.domain.models import DocumentInput
from kg_engine.domain.models import TextUnitInput

logger = logging.getLogger(__name__)

_TEXT_SUFFIXES = {".md", ".txt"}
_MARKITDOWN_SUFFIXES = {".docx", ".xlsx", ".xls", ".pdf", ".html", ".htm"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
_RAW_FRAGMENT_MAX_CHARS = 500
_SEMANTIC_UNIT_MAX_CHARS = 1400
_SEMANTIC_LINE_LIMIT = 14
_UNIT_PATTERN = re.compile(
    r"(?i)\b(?:mpa|gpa|kpa|pa|hv|hrc|hb|iacs|wt\.?%|at\.?%|mass\s*%|"
    r"vol\.?%|ppm|nm|um|µm|mm|cm|m/s|kg|g|mg|mol|c|°c|kwh|v|a)\b|[%℃°]"
)
_NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)?")
_MATERIAL_PATTERN = re.compile(
    r"\b(?:[A-Z][a-z]?\d*){2,}\b|"
    r"\b(?:Ti-?6Al-?4V|CuCrZr|316L|AlSi10Mg|Inconel|NiTi|FeCrAl)\b"
)
_DOMAIN_TERMS = (
    "alloy",
    "anneal",
    "aging",
    "calcination",
    "catalyst",
    "chemical",
    "composition",
    "conductivity",
    "concentration",
    "condition",
    "crack",
    "density",
    "experiment",
    "flotation",
    "grade",
    "hardness",
    "heat treatment",
    "leaching",
    "material",
    "microstructure",
    "ore",
    "phase",
    "pressure",
    "process",
    "property",
    "reagent",
    "recovery",
    "sample",
    "sinter",
    "strength",
    "temperature",
    "tensile",
    "yield",
    "сплав",
    "отжиг",
    "старение",
    "выщелачивание",
    "флотация",
    "материал",
    "образец",
    "прочность",
    "твёрдость",
    "твердость",
    "температура",
    "свойство",
    "концентрация",
    "извлечение",
    "реагент",
    "руда",
    "фаза",
)


class DocumentBlock(BaseModel):
    """Normalized parser output with enough provenance for graph grounding."""

    block_id: str
    source_file: str
    source_path: str
    page: int | None = Field(default=None)
    block_type: str = Field(default="text")
    text: str = Field(default="")
    raw_fragment: str | None = Field(default=None)
    image_path: Path | None = Field(default=None)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    parser: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class PageImage:
    """Rendered PDF page image used by the VL conductor."""

    page: int
    image_path: Path
    confidence: float = 1.0
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class DocumentParseSettings:
    """Routing knobs for the document parser."""

    scanned_pdf_text_threshold: int = 80
    enable_vision: bool = True
    vision_prompt: str = (
        "Read the rendered materials science document page. Extract only visible "
        "materials, processing modes, properties, numeric values, units, table "
        "headers, figure labels, and captions. Mark uncertain readings explicitly."
    )
    pdf_render_dpi: int = 180
    max_pdf_pages: int | None = None
    preserve_pdf_pages_without_text: bool = True


class MarkItDownAdapter:
    """Lazy MarkItDown wrapper for text-like file conversion."""

    def __init__(self) -> None:
        self._converter: Any | None = None

    def _get_converter(self) -> Any:
        if self._converter is None:
            try:
                from markitdown import MarkItDown
            except ImportError as exc:
                msg = (
                    "MarkItDown is required for DOCX/XLSX/PDF/HTML parsing. "
                    "Install the optional document parsing dependencies."
                )
                raise RuntimeError(msg) from exc
            self._converter = MarkItDown()
        return self._converter

    def convert(self, path: Path) -> str:
        result = self._get_converter().convert(str(path))
        text = getattr(result, "text_content", None)
        if text is None:
            text = getattr(result, "markdown", None)
        return str(text if text is not None else result)


class PdfPageRenderer:
    """Render PDF pages to images without passing PDFs directly to VL models."""

    def __init__(
        self,
        *,
        output_dir: Path | None = None,
        dpi: int = 180,
        max_pages: int | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.dpi = dpi
        self.max_pages = max_pages

    def render_pages(self, path: Path) -> list[PageImage]:
        try:
            import fitz
        except ImportError as exc:
            msg = (
                "PDF page renderer requires PyMuPDF. Install optional document "
                "parsing dependencies or inject a renderer."
            )
            raise RuntimeError(msg) from exc

        output_dir = self.output_dir or path.parent / ".kg_parse_cache" / path.stem
        output_dir.mkdir(parents=True, exist_ok=True)
        pages: list[PageImage] = []
        with fitz.open(path) as document:
            page_count = len(document)
            limit = page_count if self.max_pages is None else min(page_count, self.max_pages)
            for page_index in range(limit):
                page = document.load_page(page_index)
                pixmap = page.get_pixmap(dpi=self.dpi)
                image_path = output_dir / f"page-{page_index + 1:04d}.png"
                pixmap.save(image_path)
                pages.append(PageImage(page=page_index + 1, image_path=image_path))
        return pages


class DocumentBlockParser:
    """Route files into DocumentBlock records before graph extraction."""

    def __init__(
        self,
        *,
        markitdown: Any | None = None,
        pdf_renderer: Any | None = None,
        vision_conductor: Any | None = None,
        settings: DocumentParseSettings | None = None,
    ) -> None:
        self.markitdown = markitdown or MarkItDownAdapter()
        self.pdf_renderer = pdf_renderer
        self.vision_conductor = vision_conductor
        self.settings = settings or DocumentParseSettings()

    def parse(self, path: str | Path) -> list[DocumentBlock]:
        source = Path(path)
        suffix = source.suffix.lower()
        if suffix in _IMAGE_SUFFIXES:
            return self._image_blocks(source)
        if suffix == ".pdf":
            return self._pdf_blocks(source)
        if suffix in _TEXT_SUFFIXES:
            text = source.read_text(encoding="utf-8", errors="replace")
            return [self._text_block(source, text, parser="text")]
        if suffix in _MARKITDOWN_SUFFIXES:
            text = self.markitdown.convert(source)
            return [self._text_block(source, text, parser="markitdown")]
        msg = f"Unsupported document parser input: {source}"
        raise ValueError(msg)

    def _pdf_blocks(self, source: Path) -> list[DocumentBlock]:
        page_text_blocks = self._pypdf_text_blocks(source)
        extracted_text_len = sum(
            len(block.text.strip())
            for block in page_text_blocks
            if block.parser != "pypdf_page_placeholder"
        )
        if extracted_text_len >= self.settings.scanned_pdf_text_threshold:
            return page_text_blocks

        try:
            text = self.markitdown.convert(source).strip()
        except Exception:
            logger.debug("MarkItDown PDF conversion failed for %s", source, exc_info=True)
            text = ""
        if len(text) >= self.settings.scanned_pdf_text_threshold:
            return [self._text_block(source, text, parser="markitdown", page=None)]

        renderer = self.pdf_renderer or PdfPageRenderer(
            dpi=self.settings.pdf_render_dpi,
            max_pages=self.settings.max_pdf_pages,
        )
        try:
            page_images = renderer.render_pages(source)
        except RuntimeError:
            if page_text_blocks:
                return page_text_blocks
            raise
        blocks: list[DocumentBlock] = []
        for image in page_images:
            image_block = self._image_block(
                source,
                image.image_path,
                page=image.page,
                confidence=image.confidence,
                parser="pdf_page_renderer",
                metadata=image.metadata or {},
            )
            blocks.append(image_block)
            if self.settings.enable_vision and self.vision_conductor is not None:
                interpretation = self.vision_conductor.analyze_image(
                    image.image_path,
                    prompt=self.settings.vision_prompt,
                    metadata={
                        "source_file": source.name,
                        "source_path": str(source),
                        "page": image.page,
                        "block_id": image_block.block_id,
                    },
                )
                if interpretation.strip():
                    blocks.append(
                        self._text_block(
                            source,
                            interpretation,
                            parser="vl_conductor",
                            page=image.page,
                            block_type="image_interpretation",
                            confidence=min(0.7, image.confidence),
                            metadata={
                                "interpretation_of_block_id": image_block.block_id,
                                "image_path": str(image.image_path),
                            },
                        )
                    )
        return blocks

    def _pypdf_text_blocks(self, source: Path) -> list[DocumentBlock]:
        try:
            from pypdf import PdfReader
        except ImportError:
            logger.debug("pypdf not available for page-level PDF parsing")
            return []

        blocks: list[DocumentBlock] = []
        try:
            with open(source, "rb") as fh:
                reader = PdfReader(fh)
                page_count = len(reader.pages)
                limit = (
                    page_count
                    if self.settings.max_pdf_pages is None
                    else min(page_count, self.settings.max_pdf_pages)
                )
                for page_index in range(limit):
                    try:
                        text = (reader.pages[page_index].extract_text() or "").strip()
                    except Exception:
                        logger.debug(
                            "pypdf extraction failed for %s page %s",
                            source,
                            page_index + 1,
                            exc_info=True,
                        )
                        continue
                    page_number = page_index + 1
                    if text:
                        block = self._text_block(
                            source,
                            text,
                            parser="pypdf",
                            page=page_number,
                        )
                    elif self.settings.preserve_pdf_pages_without_text:
                        block = self._text_block(
                            source,
                            (
                                f"PDF page preserved without extracted text: "
                                f"{source.name} page {page_number}."
                            ),
                            parser="pypdf_page_placeholder",
                            page=page_number,
                            block_type="page_placeholder",
                            confidence=0.1,
                            metadata={"parse_status": "no_text_extracted"},
                        )
                    else:
                        continue
                    blocks.append(block)
                reader.stream.close()
        except Exception:
            logger.debug("pypdf PDF parsing failed for %s", source, exc_info=True)
            return []
        return blocks

    def _image_blocks(self, source: Path) -> list[DocumentBlock]:
        image_block = self._image_block(
            source,
            source,
            page=None,
            parser="image_file",
            confidence=1.0,
            metadata={},
        )
        blocks = [image_block]
        if self.settings.enable_vision and self.vision_conductor is not None:
            interpretation = self.vision_conductor.analyze_image(
                source,
                prompt=self.settings.vision_prompt,
                metadata={
                    "source_file": source.name,
                    "source_path": str(source),
                    "block_id": image_block.block_id,
                },
            )
            if interpretation.strip():
                blocks.append(
                    self._text_block(
                        source,
                        interpretation,
                        parser="vl_conductor",
                        block_type="image_interpretation",
                        confidence=0.7,
                        metadata={
                            "interpretation_of_block_id": image_block.block_id,
                            "image_path": str(source),
                        },
                    )
                )
        return blocks

    def _text_block(
        self,
        source: Path,
        text: str,
        *,
        parser: str,
        page: int | None = None,
        block_type: str = "text",
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> DocumentBlock:
        return DocumentBlock(
            block_id=_stable_block_id(source, page, block_type, text),
            source_file=source.name,
            source_path=str(source),
            page=page,
            block_type=block_type,
            text=text,
            raw_fragment=text[:_RAW_FRAGMENT_MAX_CHARS],
            confidence=confidence,
            parser=parser,
            metadata=metadata or {},
        )

    def _image_block(
        self,
        source: Path,
        image_path: Path,
        *,
        page: int | None,
        parser: str,
        confidence: float,
        metadata: dict[str, Any],
    ) -> DocumentBlock:
        return DocumentBlock(
            block_id=_stable_block_id(source, page, "image", str(image_path)),
            source_file=source.name,
            source_path=str(source),
            page=page,
            block_type="image",
            text="",
            raw_fragment=None,
            image_path=image_path,
            confidence=confidence,
            parser=parser,
            metadata=metadata,
        )


def blocks_to_document_input(
    document_id: str,
    title: str,
    blocks: list[DocumentBlock],
) -> DocumentInput:
    """Convert parsed blocks into compact semantic units for graph ingestion."""
    text_blocks = [block for block in blocks if block.text.strip()]
    semantic_units = [
        _semantic_text_unit(block)
        for block in text_blocks
    ]
    text_units = [
        TextUnitInput(content=content, metadata=metadata)
        for content, metadata in semantic_units
    ]
    source_ref = blocks[0].source_path if blocks else document_id
    return DocumentInput(
        document_id=document_id,
        title=title,
        text="\n\n".join(
            _block_text_for_extraction(block, content)
            for block, (content, _metadata) in zip(text_blocks, semantic_units, strict=True)
        ),
        source_ref=source_ref,
        text_units=text_units,
        metadata={
            "source_path": source_ref,
            "parsed_block_count": len(blocks),
            "text_block_count": len(text_blocks),
            "semantic_text_unit_count": len(text_units),
            "text_unit_storage": "semantic_compaction",
            "parsers": sorted({block.parser for block in blocks}),
        },
    )


def parse_document_file(
    path: str | Path,
    *,
    parser: DocumentBlockParser | None = None,
) -> DocumentInput:
    """Parse a file into a DocumentInput ready for graph ingestion."""
    source = Path(path)
    active_parser = parser or DocumentBlockParser()
    blocks = active_parser.parse(source)
    return blocks_to_document_input(str(source), source.stem, blocks)


def _block_metadata(block: DocumentBlock) -> dict[str, Any]:
    metadata = {
        "block_id": block.block_id,
        "source_file": block.source_file,
        "source_path": block.source_path,
        "page": block.page,
        "block_type": block.block_type,
        "parser": block.parser,
        "confidence": block.confidence,
    }
    if block.raw_fragment is not None:
        metadata["raw_fragment"] = block.raw_fragment[:_RAW_FRAGMENT_MAX_CHARS]
        metadata["raw_fragment_chars"] = min(len(block.raw_fragment), _RAW_FRAGMENT_MAX_CHARS)
    if block.image_path is not None:
        metadata["image_path"] = str(block.image_path)
    metadata.update(block.metadata)
    return metadata


def _semantic_text_unit(block: DocumentBlock) -> tuple[str, dict[str, Any]]:
    metadata = _block_metadata(block)
    source_ref = block.source_file
    page_ref = "unknown page" if block.page is None else f"page {block.page}"
    meaning = _semantic_meaning(block.text)
    content = (
        f"Meaning from {source_ref}, {page_ref}; "
        f"block={block.block_id}; type={block.block_type}; parser={block.parser}. "
        f"{meaning}"
    )
    content = _truncate_text(content, _SEMANTIC_UNIT_MAX_CHARS)
    metadata.update(
        {
            "semantic_unit": True,
            "semantic_method": "deterministic_compaction_v1",
            "source_text_chars": len(block.text),
            "stored_text_chars": len(content),
            "storage_policy": "meaning_with_page_provenance",
        }
    )
    return content, metadata


def _semantic_meaning(text: str) -> str:
    lines = [_compact_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    if len(lines) == 1:
        return f"Semantic summary: {_truncate_text(lines[0], _SEMANTIC_UNIT_MAX_CHARS)}"

    selected_indices: set[int] = set()
    for idx in range(min(2, len(lines))):
        selected_indices.add(idx)

    scored = sorted(
        ((_semantic_line_score(line, idx), idx) for idx, line in enumerate(lines)),
        key=lambda item: (-item[0], item[1]),
    )
    for score, idx in scored:
        if len(selected_indices) >= _SEMANTIC_LINE_LIMIT:
            break
        if score <= 0:
            continue
        selected_indices.add(idx)

    if len(selected_indices) < min(4, len(lines)):
        for idx in range(len(lines)):
            selected_indices.add(idx)
            if len(selected_indices) >= min(4, len(lines)):
                break

    summary_lines = [lines[idx] for idx in sorted(selected_indices)]
    summary = " / ".join(summary_lines)
    return f"Semantic summary: {_truncate_text(summary, _SEMANTIC_UNIT_MAX_CHARS)}"


def _semantic_line_score(line: str, index: int) -> int:
    lower = line.casefold()
    score = 0
    if index < 2:
        score += 2
    if _NUMBER_PATTERN.search(line):
        score += 3
    if _UNIT_PATTERN.search(line):
        score += 3
    if _MATERIAL_PATTERN.search(line):
        score += 3
    if any(term in lower for term in _DOMAIN_TERMS):
        score += 2
    if "|" in line or "\t" in line or "," in line:
        score += 1
    if len(line) <= 180:
        score += 1
    return score


def _compact_line(line: str) -> str:
    return " ".join(line.strip().split())


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _block_text_for_extraction(block: DocumentBlock, semantic_content: str) -> str:
    page = "" if block.page is None else f" page={block.page}"
    return (
        f"[block_id={block.block_id}{page} type={block.block_type} "
        f"parser={block.parser} storage=semantic]\n{semantic_content}"
    )


def _stable_block_id(
    source: Path,
    page: int | None,
    block_type: str,
    fragment: str,
) -> str:
    digest = hashlib.sha1(
        f"{source}|{page}|{block_type}|{fragment[:500]}".encode("utf-8", "replace")
    ).hexdigest()[:12]
    page_part = "nopage" if page is None else f"p{page}"
    return f"{source.stem}:{page_part}:{block_type}:{digest}"
