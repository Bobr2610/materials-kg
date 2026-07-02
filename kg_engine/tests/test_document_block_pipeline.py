from __future__ import annotations

import base64
from pathlib import Path  # noqa: TC003
from typing import Any

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
        "sheet": "results",
    }


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
    parser = DocumentBlockParser(
        markitdown=converter,
        vision_conductor=vision,
        settings=DocumentParseSettings(enable_vision=True),
    )

    with pytest.raises(RuntimeError, match="PDF page renderer"):
        parser.parse(source)

    assert vision.calls == []


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
