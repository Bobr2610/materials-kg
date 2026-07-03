from __future__ import annotations

import base64
from pathlib import Path  # noqa: TC003
from typing import Any
from unittest.mock import patch

import pytest

from kg_engine.ingestion.document_blocks import DocumentBlock
from kg_engine.ingestion.document_blocks import DocumentBlockParser
from kg_engine.ingestion.document_blocks import DocumentParseSettings
from kg_engine.ingestion.document_blocks import PageImage
from kg_engine.ingestion.document_blocks import blocks_to_document_input
from kg_engine.scripts.ingest_materials_kg import _load_payload
from kg_engine.llm_core.vision import VisionRequest
from kg_engine.llm_core.vision import build_openai_compatible_vision_messages


class FakeMarkItDown:
    def __init__(self, outputs: dict[str, str]) -> None:
        self.outputs = outputs
        self.calls: list[Path] = []

    def convert(self, path: Path) -> str:
        self.calls.append(path)
        return self.outputs.get(path.suffix.lower(), "")


class FakeRenderer:
    def __init__(self, pages: list[PageImage]) -> None:
        self.pages = pages
        self.calls: list[Path] = []

    def render_pages(self, path: Path) -> list[PageImage]:
        self.calls.append(path)
        return self.pages


class FakeVisionConductor:
    def __init__(self) -> None:
        self.calls: list[Path] = []

    def analyze_image(self, image_path: Path, *, prompt: str, metadata: dict[str, Any]) -> str:
        self.calls.append(image_path)
        assert metadata["page"] == 1
        assert "materials" in prompt.lower()
        return "Figure interpretation: annealing mode increases conductivity."


def test_markitdown_documents_become_source_blocks(tmp_path) -> None:
    source = tmp_path / "report.docx"
    source.write_bytes(b"not a real docx; converter is injected")
    converter = FakeMarkItDown({".docx": "# Report\n\nTi-6Al-4V aged at 480 C."})
    parser = DocumentBlockParser(markitdown=converter)

    blocks = parser.parse(source)

    assert converter.calls == [source]
    assert len(blocks) == 1
    assert blocks[0].block_type == "text"
    assert blocks[0].parser == "markitdown"
    assert blocks[0].source_file == "report.docx"
    assert "Ti-6Al-4V" in blocks[0].text


def test_scanned_pdf_creates_page_image_blocks_without_direct_vl_pdf_call(tmp_path) -> None:
    source = tmp_path / "book.pdf"
    source.write_bytes(b"%PDF fake")
    page_image = tmp_path / "book-page-001.png"
    page_image.write_bytes(b"png")
    converter = FakeMarkItDown({".pdf": ""})
    renderer = FakeRenderer([PageImage(page=1, image_path=page_image)])
    vision = FakeVisionConductor()
    parser = DocumentBlockParser(
        markitdown=converter,
        pdf_renderer=renderer,
        vision_conductor=vision,
        settings=DocumentParseSettings(enable_vision=True),
    )

    blocks = parser.parse(source)

    assert renderer.calls == [source]
    assert vision.calls == [page_image]
    assert all(block.image_path != source for block in blocks)
    assert [block.block_type for block in blocks] == ["image", "image_interpretation"]
    assert blocks[1].metadata["interpretation_of_block_id"] == blocks[0].block_id


def test_text_pdf_becomes_page_level_blocks_before_markitdown(tmp_path) -> None:
    from reportlab.pdfgen.canvas import Canvas

    source = tmp_path / "book.pdf"
    canvas = Canvas(str(source))
    canvas.drawString(72, 720, "Page one: CuCrZr conductivity " * 4)
    canvas.showPage()
    canvas.drawString(72, 720, "Page two: flotation tails " * 4)
    canvas.save()
    converter = FakeMarkItDown({".pdf": "this should not be used"})
    parser = DocumentBlockParser(markitdown=converter)

    blocks = parser.parse(source)

    assert converter.calls == []
    assert [block.page for block in blocks] == [1, 2]
    assert {block.parser for block in blocks} == {"pypdf"}
    assert "CuCrZr" in blocks[0].text


def test_scanned_pdf_pages_are_preserved_when_renderer_unavailable(tmp_path) -> None:
    from reportlab.pdfgen.canvas import Canvas

    source = tmp_path / "scan.pdf"
    canvas = Canvas(str(source))
    canvas.showPage()
    canvas.showPage()
    canvas.save()

    class MissingRenderer:
        def render_pages(self, path: Path) -> list[PageImage]:
            raise RuntimeError("PDF page renderer requires PyMuPDF")

    parser = DocumentBlockParser(
        markitdown=FakeMarkItDown({".pdf": ""}),
        pdf_renderer=MissingRenderer(),
        settings=DocumentParseSettings(enable_vision=False),
    )

    blocks = parser.parse(source)

    assert [block.page for block in blocks] == [1, 2]
    assert {block.parser for block in blocks} == {"pypdf_page_placeholder"}
    assert all(block.metadata["parse_status"] == "no_text_extracted" for block in blocks)


def test_blocks_become_text_units_with_provenance(tmp_path) -> None:
    block = DocumentBlock(
        block_id="doc:1:0001",
        source_file="report.md",
        source_path=str(tmp_path / "report.md"),
        page=3,
        block_type="table",
        text="| alloy | UTS |\n| 316L | 610 MPa |",
        raw_fragment="alloy,UTS\n316L,610 MPa",
        confidence=0.92,
        parser="markitdown",
        metadata={"sheet": "results"},
    )

    document = blocks_to_document_input("doc-1", "Report", [block])

    assert "316L" in document.text
    assert "Meaning from report.md, page 3" in document.text_units[0].content
    assert "| 316L | 610 MPa |" in document.text_units[0].content
    assert document.source_ref == str(tmp_path / "report.md")
    assert document.text_units[0].metadata == {
        "block_id": "doc:1:0001",
        "source_file": "report.md",
        "source_path": str(tmp_path / "report.md"),
        "page": 3,
        "block_type": "table",
        "parser": "markitdown",
        "confidence": 0.92,
        "raw_fragment": "alloy,UTS\n316L,610 MPa",
        "raw_fragment_chars": len("alloy,UTS\n316L,610 MPa"),
        "sheet": "results",
        "semantic_unit": True,
        "semantic_method": "deterministic_compaction_v1",
        "source_text_chars": len("| alloy | UTS |\n| 316L | 610 MPa |"),
        "stored_text_chars": len(document.text_units[0].content),
        "storage_policy": "meaning_with_page_provenance",
    }
    assert document.metadata["text_unit_storage"] == "semantic_compaction"


def test_long_blocks_store_semantic_meaning_not_full_raw_text(tmp_path) -> None:
    repeated_noise = "\n".join(
        f"background paragraph {idx} without useful values"
        for idx in range(120)
    )
    important = "CuCrZr aging at 480 C reached conductivity 82 %IACS and hardness 145 HV."
    raw_text = f"{repeated_noise}\n{important}\n{repeated_noise}"
    block = DocumentBlock(
        block_id="doc:long:0001",
        source_file="large.pdf",
        source_path=str(tmp_path / "large.pdf"),
        page=42,
        block_type="text",
        text=raw_text,
        raw_fragment=raw_text,
        confidence=0.88,
        parser="pypdf",
    )

    document = blocks_to_document_input("doc-1", "Large PDF", [block])
    text_unit = document.text_units[0]

    assert len(text_unit.content) < len(raw_text)
    assert len(text_unit.content) <= 1400
    assert important in text_unit.content
    assert text_unit.metadata["page"] == 42
    assert text_unit.metadata["source_text_chars"] == len(raw_text)
    assert text_unit.metadata["stored_text_chars"] == len(text_unit.content)
    assert len(text_unit.metadata["raw_fragment"]) <= 500
    assert text_unit.metadata["semantic_unit"] is True


def test_vision_messages_are_openai_compatible_image_payload(tmp_path) -> None:
    image = tmp_path / "figure.png"
    image.write_bytes(b"image bytes")
    request = VisionRequest(
        image_path=image,
        prompt="Describe only visible labels and numeric values.",
        mime_type="image/png",
    )

    messages = build_openai_compatible_vision_messages(request)

    content = messages[0]["content"]
    assert messages[0]["role"] == "user"
    assert content[0] == {"type": "text", "text": request.prompt}
    assert content[1]["type"] == "image_url"
    url = content[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == b"image bytes"


def test_missing_pdf_renderer_fails_before_vl_receives_pdf(tmp_path) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF fake")
    converter = FakeMarkItDown({".pdf": ""})
    vision = FakeVisionConductor()

    class FakeRendererNoPages:
        def render_pages(self, path: Path) -> list[PageImage]:
            raise RuntimeError("PDF page renderer requires PyMuPDF")

    parser = DocumentBlockParser(
        markitdown=converter,
        pdf_renderer=FakeRendererNoPages(),
        vision_conductor=vision,
        settings=DocumentParseSettings(enable_vision=True),
    )

    with pytest.raises(RuntimeError, match="PDF page renderer"):
        parser.parse(source)


def test_document_loader_accepts_parser_backed_formats(tmp_path) -> None:
    source = tmp_path / "report.docx"
    source.write_bytes(b"fake")
    parser = DocumentBlockParser(
        markitdown=FakeMarkItDown({".docx": "CuCrZr aging reached 82 %IACS."})
    )

    payload = _load_payload(
        str(source),
        family="documents",
        document_parser=parser,
    )

    assert isinstance(payload, list)
    assert payload[0]["document_id"] == str(source)
    assert payload[0]["text_units"][0]["metadata"]["block_type"] == "text"
    assert payload[0]["text_units"][0]["metadata"]["source_file"] == "report.docx"


def test_html_files_parsed_through_markitdown(tmp_path) -> None:
    source = tmp_path / "page.html"
    source.write_bytes(b"<html><body><p>Ti-6Al-4V tensile 950 MPa</p></body></html>")
    converter = FakeMarkItDown({".html": "Ti-6Al-4V tensile 950 MPa"})
    parser = DocumentBlockParser(markitdown=converter)

    blocks = parser.parse(source)

    assert converter.calls == [source]
    assert len(blocks) == 1
    assert blocks[0].parser == "markitdown"
    assert "Ti-6Al-4V" in blocks[0].text


def test_image_blocks_use_vlm_when_available(tmp_path) -> None:
    source = tmp_path / "figure.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\nfake png data")
    vision = FakeVisionConductor()
    vision_with_page = FakeVisionConductorWithPage()
    parser = DocumentBlockParser(
        vision_conductor=vision_with_page,
        settings=DocumentParseSettings(enable_vision=True),
    )

    blocks = parser.parse(source)

    assert len(blocks) == 2
    assert blocks[0].block_type == "image"
    assert blocks[1].block_type == "image_interpretation"
    assert blocks[1].parser == "vl_conductor"
    assert "annealing" in blocks[1].text.lower()


class FakeVisionConductorWithPage:
    def __init__(self) -> None:
        self.calls: list[Path] = []

    def analyze_image(self, image_path: Path, *, prompt: str, metadata: dict[str, Any]) -> str:
        self.calls.append(image_path)
        return "Figure interpretation: annealing mode increases conductivity."


def test_vlm_interpretations_included_in_document_input(tmp_path) -> None:
    source = tmp_path / "figure.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    vision = FakeVisionConductorWithPage()
    parser = DocumentBlockParser(
        vision_conductor=vision,
        settings=DocumentParseSettings(enable_vision=True),
    )

    blocks = parser.parse(source)
    document = blocks_to_document_input("doc-1", "Figure", blocks)

    assert "annealing" in document.text.lower()
    assert len(document.text_units) == 1
    assert document.text_units[0].metadata["block_type"] == "image_interpretation"
