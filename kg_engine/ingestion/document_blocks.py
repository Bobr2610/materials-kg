"""Document parsing layer that normalizes files into provenance-rich blocks."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic import Field

from kg_engine.domain.models import DocumentInput
from kg_engine.domain.models import TextUnitInput

logger = logging.getLogger(__name__)

_TEXT_SUFFIXES = {".md", ".txt"}
_MARKITDOWN_SUFFIXES = {".docx", ".xlsx", ".xls", ".pdf", ".html", ".htm"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}


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
    enable_vision: bool = False
    vision_prompt: str = (
        "Read the rendered materials science document page. Extract only visible "
        "materials, processing modes, properties, numeric values, units, table "
        "headers, figure labels, and captions. Mark uncertain readings explicitly."
    )
    pdf_render_dpi: int = 180
    max_pdf_pages: int | None = None


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
        text = self.markitdown.convert(source).strip()
        if len(text) >= self.settings.scanned_pdf_text_threshold:
            return [self._text_block(source, text, parser="markitdown", page=None)]

        renderer = self.pdf_renderer or PdfPageRenderer(
            dpi=self.settings.pdf_render_dpi,
            max_pages=self.settings.max_pdf_pages,
        )
        page_images = renderer.render_pages(source)
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
            raw_fragment=text[:2000],
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
    """Convert parsed blocks into the existing document ingestion DTO."""
    text_blocks = [block for block in blocks if block.text.strip()]
    text_units = [
        TextUnitInput(content=block.text, metadata=_block_metadata(block))
        for block in text_blocks
    ]
    source_ref = blocks[0].source_path if blocks else document_id
    return DocumentInput(
        document_id=document_id,
        title=title,
        text="\n\n".join(_block_text_for_extraction(block) for block in text_blocks),
        source_ref=source_ref,
        text_units=text_units,
        metadata={
            "source_path": source_ref,
            "parsed_block_count": len(blocks),
            "text_block_count": len(text_blocks),
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
        metadata["raw_fragment"] = block.raw_fragment
    if block.image_path is not None:
        metadata["image_path"] = str(block.image_path)
    metadata.update(block.metadata)
    return metadata


def _block_text_for_extraction(block: DocumentBlock) -> str:
    page = "" if block.page is None else f" page={block.page}"
    return (
        f"[block_id={block.block_id}{page} type={block.block_type} "
        f"parser={block.parser}]\n{block.text}"
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
