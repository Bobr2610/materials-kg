"""Unified file reading tool - handles text files, PDFs, and DOCX.

This tool automatically detects file type and processes accordingly.
Supports local files and URLs.
"""


from langchain.tools import tool
from pydantic import BaseModel, Field

from kg_engine.tools.file_utils import FileUtils
from kg_engine.tools.pdf_utils import PDFUtils


class ReadFileSchema(BaseModel):
    """Input schema for read_file tool."""

    file_reference: str = Field(description="Filename, path, or URL to read")


@tool(args_schema=ReadFileSchema)
def read_file(file_reference: str) -> str:
    """Read text files, PDFs, and DOCX, auto-detecting file type.

    Supported file types:
    - Text files: .txt, .md, .log, .json, .xml, .yaml, .yml, .html, .htm, .css, .js,
      .py, .sql, .ini, .cfg, .conf, .env, .csv, .tsv, .rst, .tex
    - PDF files: .pdf (extracts text as Markdown)
    - DOCX files: .docx (extracts text via direct XML parsing)

    The tool automatically:
    - Detects file type by extension
    - Handles local files and URLs
    - Falls back through multiple encodings (UTF-8, Latin-1, CP1252)
    - Returns JSON with content and metadata

    Args:
        file_reference: Filename, path, or URL to read

    Returns:
        JSON string with extracted content and file metadata
    """
    file_path = FileUtils.resolve_file_reference(file_reference)
    if not file_path:
        return FileUtils.create_tool_response(
            "read_file", error=f"File not found: {file_reference}"
        )

    file_info = FileUtils.get_file_info(file_path)
    if not file_info.exists:
        return FileUtils.create_tool_response(
            "read_file", error=file_info.error, file_info=file_info
        )

    if file_info.extension == ".pdf":
        return _read_pdf(file_path, file_info, file_reference)

    if file_info.extension == ".docx":
        return _read_docx(file_path, file_info, file_reference)

    return _read_text_file(file_path, file_info, file_reference)


def _read_pdf(file_path: str, file_info, file_reference: str) -> str:
    """Read PDF file and extract text as Markdown."""
    if not PDFUtils.is_available():
        return FileUtils.create_tool_response(
            "read_file",
            error="PyMuPDF4LLM not available. Install with: pip install pymupdf4llm",
            file_info=file_info,
        )

    try:
        pdf_result = PDFUtils.extract_text_from_pdf(file_path, use_markdown=True)
        if not pdf_result.success:
            return FileUtils.create_tool_response(
                "read_file", error=pdf_result.error_message, file_info=file_info
            )

        size_str = FileUtils.format_file_size(file_info.size)
        display_name = (
            file_reference
            if file_reference.startswith(("http://", "https://", "ftp://"))
            else file_reference
        )
        result_text = f"File: {display_name} ({size_str})\n\nContent:\n{pdf_result.text_content}"
        return FileUtils.create_tool_response(
            "read_file", result=result_text, file_info=file_info
        )
    except Exception as e:
        return FileUtils.create_tool_response(
            "read_file", error=f"Error processing PDF: {str(e)}", file_info=file_info
        )


def _read_docx(file_path: str, file_info, file_reference: str) -> str:
    """Read DOCX file and extract text via direct XML parsing."""
    try:
        import xml.etree.ElementTree as ET
        import zipfile

        with zipfile.ZipFile(file_path) as zf:
            with zf.open("word/document.xml") as xml_file:
                xml_content = xml_file.read()

        ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        root = ET.fromstring(xml_content)

        paragraphs = []
        for para in root.iter(f"{{{ns}}}p"):
            texts = []
            for t in para.iter(f"{{{ns}}}t"):
                if t.text:
                    texts.append(t.text)
            para_text = "".join(texts).strip()
            if para_text:
                paragraphs.append(para_text)

        text_content = "\n".join(paragraphs)

        size_str = FileUtils.format_file_size(file_info.size)
        display_name = (
            file_reference
            if file_reference.startswith(("http://", "https://", "ftp://"))
            else file_reference
        )
        result_text = f"File: {display_name} ({size_str})\n\nContent:\n{text_content}"
        return FileUtils.create_tool_response(
            "read_file", result=result_text, file_info=file_info
        )
    except zipfile.BadZipFile:
        return FileUtils.create_tool_response(
            "read_file", error="Invalid DOCX file (not a valid ZIP)", file_info=file_info
        )
    except KeyError:
        return FileUtils.create_tool_response(
            "read_file", error="Invalid DOCX file (missing word/document.xml)", file_info=file_info
        )
    except ET.ParseError as e:
        return FileUtils.create_tool_response(
            "read_file", error=f"Failed to parse DOCX XML: {str(e)}", file_info=file_info
        )
    except Exception as e:
        return FileUtils.create_tool_response(
            "read_file", error=f"Error processing DOCX: {str(e)}", file_info=file_info
        )


def _read_text_file(file_path: str, file_info, file_reference: str) -> str:
    """Read text file with encoding fallback."""
    if not FileUtils.is_text_file(file_path):
        return FileUtils.create_tool_response(
            "read_file",
            error=f"Unsupported file type: {file_info.extension}",
            file_info=file_info,
        )

    result = FileUtils.read_text_file(file_path)
    if not result.success:
        return FileUtils.create_tool_response(
            "read_file", error=result.error, file_info=file_info
        )

    size_str = FileUtils.format_file_size(file_info.size)
    display_name = (
        file_reference
        if file_reference.startswith(("http://", "https://", "ftp://"))
        else file_reference
    )
    if result.encoding != "utf-8":
        result_text = f"File: {display_name} ({size_str}, {result.encoding} encoding)\n\nContent:\n{result.content}"
    else:
        result_text = f"File: {display_name} ({size_str})\n\nContent:\n{result.content}"

    return FileUtils.create_tool_response(
        "read_file", result=result_text, file_info=file_info
    )
