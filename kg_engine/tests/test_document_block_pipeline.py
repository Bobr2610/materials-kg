from __future__ import annotations

import base64
from pathlib import Path  # noqa: TC003
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from kg_engine.ingestion.document_blocks import DocumentBlock
from kg_engine.ingestion.document_blocks import DocumentBlockParser
from kg_engine.ingestion.document_blocks import DocumentParseSettings
from kg_engine.ingestion.document_blocks import GrobidClient
from kg_engine.ingestion.document_blocks import PageImage
from kg_engine.ingestion.document_blocks import _grobid_tei_to_blocks
from kg_engine.ingestion.document_blocks import blocks_to_document_input
from kg_engine.scripts.ingest_materials_kg import _load_payload
from kg_engine.llm_core.vision import VisionRequest
from kg_engine.llm_core.vision import build_vision_messages


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


def test_vision_messages_are_chat_completions_image_payload(tmp_path) -> None:
    image = tmp_path / "figure.png"
    image.write_bytes(b"image bytes")
    request = VisionRequest(
        image_path=image,
        prompt="Describe only visible labels and numeric values.",
        mime_type="image/png",
    )

    messages = build_vision_messages(request)

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


# ---------------------------------------------------------------------------
# GROBID tests
# ---------------------------------------------------------------------------

_SAMPLE_TEI = """\
<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title>Effect of aging on CuCrZr conductivity</title>
      </titleStmt>
      <publicationStmt><publisher>Test</publisher></publicationStmt>
      <sourceDesc><p>A PDF</p></sourceDesc>
    </fileDesc>
  </teiHeader>
  <profileDesc>
    <abstract>
      <p>This study investigates how thermal aging at 480 C affects CuCrZr.</p>
    </abstract>
  </profileDesc>
  <text>
    <body>
      <div>
        <head>Introduction</head>
        <p>CuCrZr alloys are widely used in fusion reactors.</p>
        <p>Conductivity targets exceed 80 %IACS.</p>
      </div>
      <div>
        <head>Results</head>
        <p>Aging at 480 C for 100 h yields 82 %IACS and 145 HV.</p>
      </div>
    </body>
    <back>
      <div type="references">
        <listBibl>
          <biblStruct>
            <analytic><title>Conductivity of CuCrZr</title></analytic>
            <monogr><journal><title>J. Nucl. Mater.</title></journal></monogr>
            <author><persName><surname>Smith</surname><givenName>J.</givenName></persName></author>
            <date when="2020"/>
          </biblStruct>
          <biblStruct>
            <analytic><title>Hardness recovery in CuCrZr</title></analytic>
            <author><persName><surname>Lee</surname><givenName>K.</givenName></persName></author>
            <date when="2021"/>
          </biblStruct>
        </listBibl>
      </div>
    </back>
  </text>
</TEI>"""


def test_grobid_tei_produces_title_abstract_section_reference_blocks(tmp_path) -> None:
    source = tmp_path / "cuartz.pdf"
    blocks = _grobid_tei_to_blocks(_SAMPLE_TEI, source=source)

    block_types = [b.block_type for b in blocks]
    assert "title" in block_types
    assert "abstract" in block_types
    assert "section" in block_types
    assert "reference" in block_types

    title_block = next(b for b in blocks if b.block_type == "title")
    assert "CuCrZr" in title_block.text
    assert title_block.parser == "grobid"
    assert title_block.metadata["doi"] == ""
    assert title_block.metadata["source_marker"] == "grobid"

    abstract_block = next(b for b in blocks if b.block_type == "abstract")
    assert "thermal aging" in abstract_block.text.lower()
    assert abstract_block.parser == "grobid"

    sections = [b for b in blocks if b.block_type == "section"]
    assert len(sections) == 2
    assert sections[0].metadata["section"] == "Introduction"
    assert sections[0].metadata["section_index"] == 0
    assert sections[1].metadata["section"] == "Results"
    assert "82 %IACS" in sections[1].text

    refs = [b for b in blocks if b.block_type == "reference"]
    assert len(refs) == 2
    assert refs[0].metadata["reference_index"] == 0
    assert "Smith" in refs[0].text
    assert "2020" in refs[0].metadata["year"]
    assert "Lee" in refs[1].text
    assert refs[1].metadata["authors"] == ["K. Lee"]


def test_grobid_pdf_parser_does_not_call_pypdf_when_grobid_succeeds(tmp_path) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF fake")

    grobid_client = MagicMock(spec=GrobidClient)
    grobid_client.process_fulltext_document.return_value = _SAMPLE_TEI

    parser = DocumentBlockParser(
        grobid_client=grobid_client,
        settings=DocumentParseSettings(grobid_min_text_chars=80),
    )

    with patch.object(parser, "_pypdf_text_blocks") as mock_pypdf, \
         patch.object(parser, "markitdown") as mock_markitdown:
        blocks = parser.parse(source)

        # GROBID succeeded with enough text — pypdf and markitdown must not be called
        mock_pypdf.assert_not_called()
        mock_markitdown.assert_not_called()

    assert all(b.parser == "grobid" for b in blocks)
    grobid_client.process_fulltext_document.assert_called_once_with(source)


def test_grobid_empty_response_falls_back_to_scanned_pdf_path(tmp_path) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF fake")
    page_image = tmp_path / "page-0001.png"
    page_image.write_bytes(b"png")

    grobid_client = MagicMock(spec=GrobidClient)
    grobid_client.process_fulltext_document.return_value = "<tei:TEI/>"  # minimal, no body
    # Actually, let's make it raise to trigger the fallback
    grobid_client.process_fulltext_document.side_effect = RuntimeError("GROBID down")

    page_images = [PageImage(page=1, image_path=page_image)]
    renderer = FakeRenderer(page_images)
    vision = FakeVisionConductor()
    converter = FakeMarkItDown({".pdf": ""})

    parser = DocumentBlockParser(
        grobid_client=grobid_client,
        markitdown=converter,
        pdf_renderer=renderer,
        vision_conductor=vision,
        settings=DocumentParseSettings(
            enable_vision=True,
            grobid_min_text_chars=80,
        ),
    )

    blocks = parser.parse(source)

    # GROBID failed → should fall back to page rendering + VL
    grobid_client.process_fulltext_document.assert_called_once()
    assert renderer.calls == [source]
    assert any(b.block_type == "image" for b in blocks)
    assert any(b.block_type == "image_interpretation" for b in blocks)
    # Verify scanned PDF is NOT sent as raw PDF to VL — it's rendered to images first
    image_blocks = [b for b in blocks if b.block_type == "image"]
    assert all(b.image_path != source for b in image_blocks)


def test_grobid_insufficient_text_falls_back_to_pypdf(tmp_path) -> None:
    from reportlab.pdfgen.canvas import Canvas

    source = tmp_path / "minimal.pdf"
    canvas = Canvas(str(source))
    canvas.drawString(72, 720, "Page one: CuCrZr conductivity " * 4)
    canvas.showPage()
    canvas.save()

    # GROBID returns TEI with very little text (just a title, no body)
    minimal_tei = """\
    <?xml version="1.0" encoding="UTF-8"?>
    <TEI xmlns="http://www.tei-c.org/ns/1.0">
      <teiHeader>
        <fileDesc>
          <titleStmt><title>X</title></titleStmt>
          <publicationStmt><publisher>T</publisher></publicationStmt>
          <sourceDesc><p>A PDF</p></sourceDesc>
        </fileDesc>
      </teiHeader>
      <text><body><div><p>a</p></div></body></text>
    </TEI>"""

    grobid_client = MagicMock(spec=GrobidClient)
    grobid_client.process_fulltext_document.return_value = minimal_tei

    converter = FakeMarkItDown({".pdf": ""})
    parser = DocumentBlockParser(
        grobid_client=grobid_client,
        markitdown=converter,
        settings=DocumentParseSettings(grobid_min_text_chars=80),
    )

    blocks = parser.parse(source)

    # GROBID returned < 80 chars of useful text → fallback to pypdf
    grobid_client.process_fulltext_document.assert_called_once()
    assert converter.calls == []  # pypdf succeeded, no need for markitdown
    assert {b.parser for b in blocks} == {"pypdf"}
    assert "CuCrZr" in blocks[0].text


def test_grobid_disabled_url_skips_grobid_entirely(tmp_path) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF fake")

    # Empty grobid_url means no client created
    parser = DocumentBlockParser(
        settings=DocumentParseSettings(grobid_url=""),
    )
    assert parser.grobid_client is None

    # When GROBID is disabled, _grobid_pdf_blocks should return []
    grobid_blocks = parser._grobid_pdf_blocks(source)
    assert grobid_blocks == []
