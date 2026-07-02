from io import BytesIO
from docx import Document
from openpyxl import Workbook
import pytest

from kg_engine.ingestion.readers import DocumentReaderRegistry
from kg_engine.ingestion.readers import InvalidDocumentSignatureError


def test_docx_reader_preserves_paragraph_and_table_locations() -> None:
    document = Document()
    document.add_heading("IN718 report", level=1)
    document.add_paragraph("Aging at 720 °C increased hardness.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Property"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "Hardness"
    table.cell(1, 1).text = "44 HRC"
    payload = BytesIO()
    document.save(payload)

    parsed = DocumentReaderRegistry().read_bytes("report.docx", payload.getvalue())

    assert parsed.media_type.endswith("wordprocessingml.document")
    assert parsed.fragments[0].locator["paragraph"] == 1
    assert parsed.tables[0].rows[1] == ["Hardness", "44 HRC"]
    assert parsed.tables[0].locator == {"table": 1}


def test_xlsx_reader_preserves_sheet_row_and_formula_value() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Experiments"
    sheet.append(["Material", "Strength, MPa"])
    sheet.append(["316L", 620])
    payload = BytesIO()
    workbook.save(payload)

    parsed = DocumentReaderRegistry().read_bytes("results.xlsx", payload.getvalue())

    assert parsed.tables[0].locator == {"sheet": "Experiments", "range": "A1:B2"}
    assert parsed.tables[0].rows[1] == ["316L", "620"]
    assert parsed.fragments[1].locator == {"sheet": "Experiments", "row": 2}


def test_reader_checksum_is_stable_and_unknown_format_is_rejected() -> None:
    registry = DocumentReaderRegistry()
    first = registry.read_bytes("notes.txt", b"CuCrZr conductivity")
    second = registry.read_bytes("renamed.txt", b"CuCrZr conductivity")

    assert first.checksum == second.checksum
    assert registry.is_supported("sample.exe") is False


def test_binary_reader_rejects_extension_spoofing() -> None:
    registry = DocumentReaderRegistry()

    with pytest.raises(InvalidDocumentSignatureError, match="signature"):
        registry.read_bytes("fake.pdf", b"not a pdf")
