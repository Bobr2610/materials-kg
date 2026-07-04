"""Document parsing layer that normalizes files into provenance-rich blocks."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
import re
from typing import Any
import urllib.error
import urllib.request

from defusedxml import ElementTree

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
_PAGE_NUMBER_PATTERN = re.compile(
    r"(?i)^\s*(?:page|p\.?|стр\.?|страница)?\s*\d{1,4}\s*(?:[/\\|-]\s*\d{1,4})?\s*$"
)
_SEPARATOR_PATTERN = re.compile(r"^[\W_]{3,}$")
_WORD_PATTERN = re.compile(r"[A-Za-zА-Яа-яЁё]")
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
    """Rendered PDF page image used by OCR and provenance blocks."""

    page: int | None
    image_path: Path
    confidence: float = 1.0
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class OcrResult:
    """Text and normalized mean word confidence returned by local OCR."""

    text: str
    confidence: float


class TesseractOcrAdapter:
    """Local OCR adapter; no document content leaves the machine."""

    def __init__(
        self,
        *,
        languages: str = "eng+rus",
        timeout_seconds: float = 30.0,
        page_segmentation_mode: int = 6,
    ) -> None:
        self.languages = languages
        self.timeout_seconds = timeout_seconds
        self.page_segmentation_mode = page_segmentation_mode

    def recognize(self, image_path: Path) -> OcrResult:
        try:
            import pytesseract
            from pytesseract import Output
        except ImportError as exc:
            msg = "Local OCR requires pytesseract and the Tesseract executable."
            raise RuntimeError(msg) from exc
        data = pytesseract.image_to_data(
            str(image_path),
            lang=self.languages,
            config=f"--psm {self.page_segmentation_mode}",
            output_type=Output.DICT,
            timeout=self.timeout_seconds,
        )
        line_words: dict[tuple[int, int, int], list[str]] = {}
        line_order: list[tuple[int, int, int]] = []
        confidences: list[float] = []
        rows = zip(
            data.get("block_num", []),
            data.get("par_num", []),
            data.get("line_num", []),
            data.get("text", []),
            data.get("conf", []),
            strict=False,
        )
        for block_num, par_num, line_num, text, raw_confidence in rows:
            word = str(text).strip()
            if not word:
                continue
            key = (int(block_num), int(par_num), int(line_num))
            if key not in line_words:
                line_words[key] = []
                line_order.append(key)
            line_words[key].append(word)
            try:
                confidence = float(raw_confidence)
            except (TypeError, ValueError):
                continue
            if confidence >= 0:
                confidences.append(confidence)
        lines = [" ".join(line_words[key]) for key in line_order]
        mean_confidence = (
            sum(confidences) / len(confidences) / 100.0 if confidences else 0.0
        )
        return OcrResult("\n".join(lines), min(1.0, mean_confidence))


@dataclass(frozen=True)
class DocumentParseSettings:
    """Routing knobs for the document parser."""

    scanned_pdf_text_threshold: int = 80
    enable_vision: bool = True
    enable_ocr: bool = True
    ocr_languages: str = "eng+rus"
    ocr_timeout_seconds: float = 30.0
    ocr_min_text_chars: int = 40
    ocr_min_confidence: float = 0.55
    vision_prompt: str = (
        "Read the rendered materials science document page. Extract only visible "
        "materials, processing modes, properties, numeric values, units, table "
        "headers, figure labels, and captions. Mark uncertain readings explicitly."
    )
    pdf_render_dpi: int = 180
    max_pdf_pages: int | None = None
    preserve_pdf_pages_without_text: bool = True
    grobid_url: str = ""
    grobid_timeout_seconds: float = 45.0
    grobid_min_text_chars: int = 80
    enable_text_compaction: bool = True
    repeated_line_min_pages: int = 2


class GrobidClient:
    """Small GROBID REST client for scientific PDF structure extraction."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 45.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def process_fulltext_document(self, path: Path) -> str:
        boundary = "----materials-kg-grobid"
        body = _multipart_file_body(
            boundary=boundary,
            field_name="input",
            path=path,
            content_type="application/pdf",
        )
        request = urllib.request.Request(  # noqa: S310
            f"{self.base_url}/api/processFulltextDocument",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "application/xml",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310
                request,
                timeout=self.timeout_seconds,
            ) as response:
                return response.read().decode("utf-8", "replace")
        except urllib.error.URLError as exc:
            msg = f"GROBID request failed for {path}: {exc}"
            raise RuntimeError(msg) from exc


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
    """Render PDF pages to images for local OCR and provenance."""

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
        ocr_engine: Any | None = None,
        grobid_client: Any | None = None,
        vision_conductor: Any | None = None,
        settings: DocumentParseSettings | None = None,
    ) -> None:
        self.markitdown = markitdown or MarkItDownAdapter()
        self.pdf_renderer = pdf_renderer
        self.ocr_engine = ocr_engine
        self.grobid_client = grobid_client
        self.vision_conductor = vision_conductor
        self.settings = settings or DocumentParseSettings()
        if self.grobid_client is None and self.settings.grobid_url.strip():
            self.grobid_client = GrobidClient(
                self.settings.grobid_url.strip(),
                timeout_seconds=self.settings.grobid_timeout_seconds,
            )
        if self.ocr_engine is None and self.settings.enable_ocr:
            self.ocr_engine = TesseractOcrAdapter(
                languages=self.settings.ocr_languages,
                timeout_seconds=self.settings.ocr_timeout_seconds,
            )

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
        grobid_blocks = self._grobid_pdf_blocks(source)
        grobid_text_len = sum(len(block.text.strip()) for block in grobid_blocks)
        if grobid_text_len >= self.settings.grobid_min_text_chars:
            return self._compact_text_blocks(grobid_blocks)

        page_text_blocks = self._pypdf_text_blocks(source)
        extracted_text_len = sum(
            len(block.text.strip())
            for block in page_text_blocks
            if block.parser != "pypdf_page_placeholder"
        )
        if extracted_text_len >= self.settings.scanned_pdf_text_threshold:
            return self._compact_text_blocks(page_text_blocks)

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
            ocr_block = self._ocr_text_block(source, image)
            if ocr_block is not None:
                blocks.append(ocr_block)
        return self._compact_text_blocks(blocks)

    def _ocr_text_block(
        self,
        source: Path,
        image: PageImage,
    ) -> DocumentBlock | None:
        if not self.settings.enable_ocr or self.ocr_engine is None:
            return None
        try:
            result = self.ocr_engine.recognize(image.image_path)
        except Exception:
            logger.debug("OCR failed for %s page %s", source, image.page, exc_info=True)
            return None
        text = result.text.strip()
        compaction_stats: dict[str, int] = {}
        original_text_chars = len(text)
        if self.settings.enable_text_compaction:
            text, compaction_stats = _compact_text_noise(text)
        if (
            len(text) < self.settings.ocr_min_text_chars
            or result.confidence < self.settings.ocr_min_confidence
        ):
            return None
        metadata = {
            "image_path": str(image.image_path),
            "ocr_languages": self.settings.ocr_languages,
            "vlm_skipped": True,
            "vlm_skip_reason": "actionable_ocr",
        }
        if sum(compaction_stats.values()) > 0:
            metadata["text_compaction"] = _text_compaction_metadata(
                original_chars=original_text_chars,
                cleaned_chars=len(text),
                stats=compaction_stats,
            )
        return self._text_block(
            source,
            text,
            parser="tesseract_ocr",
            page=image.page,
            block_type="ocr_text",
            confidence=result.confidence,
            metadata=metadata,
        )

    def _grobid_pdf_blocks(self, source: Path) -> list[DocumentBlock]:
        if self.grobid_client is None:
            return []
        try:
            tei_xml = self.grobid_client.process_fulltext_document(source)
        except Exception:
            logger.debug("GROBID PDF parsing failed for %s", source, exc_info=True)
            return []
        try:
            return _grobid_tei_to_blocks(
                tei_xml,
                source=source,
                max_pages=self.settings.max_pdf_pages,
            )
        except Exception:
            logger.debug("GROBID TEI parsing failed for %s", source, exc_info=True)
            return []

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

    def _compact_text_blocks(self, blocks: list[DocumentBlock]) -> list[DocumentBlock]:
        if not self.settings.enable_text_compaction:
            return blocks
        return _compact_document_text_blocks(
            blocks,
            repeated_line_min_pages=self.settings.repeated_line_min_pages,
        )

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
        ocr_block = self._ocr_text_block(
            source,
            PageImage(page=None, image_path=source),
        )
        if ocr_block is not None:
            blocks.append(ocr_block)
            return blocks
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
        return _make_text_block(
            source,
            text,
            parser=parser,
            page=page,
            block_type=block_type,
            confidence=confidence,
            metadata=metadata,
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
    text_blocks = [
        block
        for block in blocks
        if block.text.strip() and block.block_type != "page_placeholder"
    ]
    semantic_units = [
        _semantic_text_unit(block)
        for block in text_blocks
    ]
    text_units = [
        TextUnitInput(content=content, metadata=metadata)
        for content, metadata in semantic_units
    ]
    source_ref = blocks[0].source_path if blocks else document_id
    extraction_text = "\n\n".join(
        _block_text_for_extraction(block, content)
        for block, (content, _metadata) in zip(
            text_blocks, semantic_units, strict=True
        )
    )
    source_text_chars = sum(len(block.text) for block in blocks)
    saved_chars = max(source_text_chars - len(extraction_text), 0)
    return DocumentInput(
        document_id=document_id,
        title=title,
        text=extraction_text,
        source_ref=source_ref,
        text_units=text_units,
        metadata={
            "source_path": source_ref,
            "parsed_block_count": len(blocks),
            "text_block_count": len(text_blocks),
            "semantic_text_unit_count": len(text_units),
            "text_unit_storage": "semantic_compaction",
            "parsers": sorted({block.parser for block in blocks}),
            "source_text_chars": source_text_chars,
            "extraction_input_chars": len(extraction_text),
            "estimated_source_tokens": (source_text_chars + 3) // 4,
            "estimated_extraction_tokens": (len(extraction_text) + 3) // 4,
            "estimated_tokens_saved": saved_chars // 4,
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
    lines = list(dict.fromkeys(lines))
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


def _compact_text_noise(
    text: str,
    *,
    repeated_line_keys: set[str] | None = None,
) -> tuple[str, dict[str, int]]:
    repeated_line_keys = repeated_line_keys or set()
    kept_lines: list[str] = []
    removed_empty_lines = 0
    removed_noise_lines = 0
    removed_repeated_lines = 0
    for raw_line in text.splitlines():
        line = _compact_line(raw_line)
        if not line:
            removed_empty_lines += 1
            continue
        key = _noise_line_key(line)
        if key in repeated_line_keys:
            removed_repeated_lines += 1
            continue
        if _is_digital_noise_line(line):
            removed_noise_lines += 1
            continue
        kept_lines.append(line)
    return "\n".join(kept_lines), {
        "removed_empty_lines": removed_empty_lines,
        "removed_noise_lines": removed_noise_lines,
        "removed_repeated_lines": removed_repeated_lines,
    }


def _compact_document_text_blocks(
    blocks: list[DocumentBlock],
    *,
    repeated_line_min_pages: int = 2,
) -> list[DocumentBlock]:
    repeated_line_keys = _repeated_edge_line_keys(
        blocks,
        min_pages=max(2, repeated_line_min_pages),
    )
    compacted: list[DocumentBlock] = []
    for block in blocks:
        if not block.text.strip() or block.block_type == "page_placeholder":
            compacted.append(block)
            continue
        cleaned_text, stats = _compact_text_noise(
            block.text,
            repeated_line_keys=repeated_line_keys,
        )
        if cleaned_text == block.text:
            compacted.append(block)
            continue
        metadata = dict(block.metadata)
        existing_stats = metadata.get("text_compaction")
        metadata["text_compaction"] = _text_compaction_metadata(
            original_chars=len(block.text),
            cleaned_chars=len(cleaned_text),
            stats=stats,
            existing=existing_stats if isinstance(existing_stats, dict) else None,
        )
        compacted.append(
            block.model_copy(
                update={
                    "text": cleaned_text,
                    "metadata": metadata,
                }
            )
        )
    return compacted


def _repeated_edge_line_keys(
    blocks: list[DocumentBlock],
    *,
    min_pages: int,
) -> set[str]:
    page_keys: dict[int, set[str]] = {}
    for block in blocks:
        if block.page is None or not block.text.strip():
            continue
        lines = [_compact_line(line) for line in block.text.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            continue
        edge_lines = lines[:3] + lines[-3:]
        keys = {
            key
            for line in edge_lines
            if (key := _noise_line_key(line)) and _is_repeatable_margin_line(line)
        }
        if keys:
            page_keys.setdefault(block.page, set()).update(keys)
    counts = Counter(key for keys in page_keys.values() for key in keys)
    return {key for key, count in counts.items() if count >= min_pages}


def _text_compaction_metadata(
    *,
    original_chars: int,
    cleaned_chars: int,
    stats: dict[str, int],
    existing: dict[str, Any] | None = None,
) -> dict[str, int | str]:
    existing = existing or {}
    merged = {
        "removed_empty_lines": int(existing.get("removed_empty_lines", 0))
        + stats.get("removed_empty_lines", 0),
        "removed_noise_lines": int(existing.get("removed_noise_lines", 0))
        + stats.get("removed_noise_lines", 0),
        "removed_repeated_lines": int(existing.get("removed_repeated_lines", 0))
        + stats.get("removed_repeated_lines", 0),
    }
    return {
        "method": "deterministic_pdf_noise_filter_v1",
        "original_chars": int(existing.get("original_chars", original_chars)),
        "cleaned_chars": cleaned_chars,
        "removed_lines": sum(merged.values()),
        **merged,
    }


def _noise_line_key(line: str) -> str:
    line = _compact_line(line).casefold()
    line = re.sub(r"\d+", "#", line)
    line = re.sub(r"\s+", " ", line)
    return line


def _is_repeatable_margin_line(line: str) -> bool:
    if _semantic_line_score(line, 0) >= 7:
        return False
    return len(line) <= 160


def _is_digital_noise_line(line: str) -> bool:
    compact = _compact_line(line)
    if not compact:
        return True
    if _PAGE_NUMBER_PATTERN.match(compact):
        return True
    if _SEPARATOR_PATTERN.match(compact):
        return True
    if _UNIT_PATTERN.search(compact) or _MATERIAL_PATTERN.search(compact):
        return False
    letters = len(_WORD_PATTERN.findall(compact))
    digits = sum(ch.isdigit() for ch in compact)
    meaningful_chars = sum(ch.isalnum() for ch in compact)
    if meaningful_chars == 0:
        return True
    if letters == 0 and digits > 0:
        return True
    return digits >= 5 and digits / max(meaningful_chars, 1) >= 0.75


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


def _make_text_block(
    source: Path,
    text: str,
    *,
    parser: str,
    page: int | None = None,
    block_type: str = "text",
    confidence: float = 1.0,
    metadata: dict[str, Any] | None = None,
) -> DocumentBlock:
    """Module-level helper to build a DocumentBlock."""
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


# ---------------------------------------------------------------------------
# GROBID TEI XML helpers
# ---------------------------------------------------------------------------

_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


def _tei_text(element: ElementTree.Element | None) -> str:
    """Extract all text content from a TEI element, including nested children."""
    if element is None:
        return ""
    return " ".join(element.itertext()).strip()


def _multipart_file_body(
    *,
    boundary: str,
    field_name: str,
    path: Path,
    content_type: str = "application/pdf",
) -> bytes:
    """Build a minimal multipart/form-data body for a single file field."""
    parts: list[bytes] = []
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="{field_name}"; '
        f'filename="{path.name}"\r\n'.encode()
    )
    parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
    parts.append(path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts)


def _grobid_tei_to_blocks(
    tei_xml: str,
    *,
    source: Path,
    max_pages: int | None = None,
) -> list[DocumentBlock]:
    """Parse GROBID TEI XML into structured DocumentBlock objects."""
    _ = max_pages
    root = ElementTree.fromstring(tei_xml)
    body = root.find(".//tei:body", _NS)
    title_el = root.find(".//tei:titleStmt/tei:title", _NS)
    abstract_el = root.find(".//tei:abstract", _NS)

    # Extract DOI if present
    doi = ""
    id_el = root.find(".//tei:idno[@type='DOI']", _NS)
    if id_el is not None and id_el.text:
        doi = id_el.text.strip()

    blocks: list[DocumentBlock] = []
    # --- Title block ---
    title_text = _tei_text(title_el)
    if title_text:
        blocks.append(
            _make_text_block(
                source,
                title_text,
                parser="grobid",
                block_type="title",
                confidence=0.95,
                metadata={
                    "tei_path": "teiHeader/titleStmt/title",
                    "source_marker": "grobid",
                    "doi": doi,
                },
            )
        )

    # --- Abstract block ---
    abstract_text = _tei_text(abstract_el)
    if abstract_text:
        blocks.append(
            _make_text_block(
                source,
                abstract_text,
                parser="grobid",
                block_type="abstract",
                confidence=0.95,
                metadata={
                    "tei_path": "teiHeader/abstract",
                    "source_marker": "grobid",
                    "doi": doi,
                },
            )
        )

    # --- Body section blocks ---
    if body is not None:
        section_index = 0
        for div in body.findall(".//tei:div", _NS):
            head_el = div.find("tei:head", _NS)
            head_text = _tei_text(head_el)
            section_name = head_text or f"section_{section_index + 1}"

            # Gather paragraph text within this div
            paragraphs = div.findall(".//tei:p", _NS)
            section_text_parts: list[str] = []
            for p in paragraphs:
                p_text = _tei_text(p)
                if p_text:
                    section_text_parts.append(p_text)
            section_text = "\n\n".join(section_text_parts)

            if section_text.strip():
                blocks.append(
                    _make_text_block(
                        source,
                        section_text,
                        parser="grobid",
                        block_type="section",
                        confidence=0.90,
                        metadata={
                            "section": section_name,
                            "section_index": section_index,
                            "tei_path": f"body/div[{section_index + 1}]",
                            "source_marker": "grobid",
                            "doi": doi,
                        },
                    )
                )
                section_index += 1

    # --- Bibliography / reference blocks ---
    bibl_struct = root.find(".//tei:back//tei:div[@type='references']", _NS)
    if bibl_struct is None:
        bibl_struct = root.find(".//tei:back//tei:listBibl", _NS)
    if bibl_struct is not None:
        ref_index = 0
        for bibl in bibl_struct.findall(".//tei:biblStruct", _NS):
            # Try analytic + monograph title combination
            analytic_title = _tei_text(
                bibl.find(".//tei:analytic/tei:title", _NS)
            )
            mono_title = _tei_text(
                bibl.find(".//tei:monogr/tei:title", _NS)
            )
            authors = []
            for author in bibl.findall(".//tei:author/tei:persName", _NS):
                surname = _tei_text(author.find("tei:surname", _NS))
                given = _tei_text(author.find("tei:givenName", _NS))
                name = f"{given} {surname}".strip() if given else surname
                if name:
                    authors.append(name)
            year_el = bibl.find(".//tei:date[@when]", _NS)
            year = year_el.get("when", "") if year_el is not None else ""

            ref_title = analytic_title or mono_title
            author_str = ", ".join(authors[:3])
            ref_text = f"{ref_title}"
            if author_str:
                ref_text = f"{author_str}. {ref_text}"
            if year:
                ref_text = f"{ref_text} ({year})."
            ref_text = ref_text.strip()

            if ref_text:
                blocks.append(
                    _make_text_block(
                        source,
                        ref_text,
                        parser="grobid",
                        block_type="reference",
                        confidence=0.85,
                        metadata={
                            "reference_index": ref_index,
                            "authors": authors[:5],
                            "year": year,
                            "tei_path": f"back//biblStruct[{ref_index + 1}]",
                            "source_marker": "grobid",
                            "doi": doi,
                        },
                    )
                )
                ref_index += 1

    return blocks
