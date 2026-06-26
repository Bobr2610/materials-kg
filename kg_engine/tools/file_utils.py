"""File handling utilities for reading text and binary files.

Modular utilities with encoding fallback and Pydantic validation.
"""

import os
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class FileInfo(BaseModel):
    """Pydantic model for file information."""

    exists: bool = Field(description="Whether the file exists and is accessible")
    path: str | None = Field(None, description="Full file path")
    name: str | None = Field(None, description="File name with extension")
    size: int = Field(0, description="File size in bytes")
    extension: str = Field("", description="File extension (lowercase)")
    error: str | None = Field(None, description="Error message if file access failed")

    @field_validator("size")
    @classmethod
    def validate_size(cls, v):
        if v < 0:
            raise ValueError("File size cannot be negative")
        return v


class TextFileResult(BaseModel):
    """Pydantic model for text file reading results."""

    success: bool = Field(description="Whether the file was successfully read")
    content: str | None = Field(None, description="File content as text")
    encoding: str | None = Field(None, description="Encoding used to read the file")
    file_info: FileInfo | None = Field(None, description="File information")
    error: str | None = Field(None, description="Error message if reading failed")


class ToolResponse(BaseModel):
    """Pydantic model for standardized tool responses."""

    type: str = Field(default="tool_response", description="Response type identifier")
    tool_name: str = Field(description="Name of the tool that generated the response")
    result: str | None = Field(None, description="Tool result content")
    error: str | None = Field(None, description="Error message if tool failed")
    file_info: FileInfo | None = Field(None, description="File information if applicable")


class FileUtils:
    """Utility class for common file operations."""

    TEXT_EXTENSIONS = {
        ".txt",
        ".md",
        ".log",
        ".json",
        ".xml",
        ".yaml",
        ".yml",
        ".html",
        ".htm",
        ".css",
        ".js",
        ".py",
        ".sql",
        ".ini",
        ".cfg",
        ".conf",
        ".env",
        ".csv",
        ".tsv",
        ".rst",
        ".tex",
    }

    @staticmethod
    def file_exists(file_path: str) -> bool:
        """Check if file exists and is accessible."""
        return os.path.exists(file_path) and os.path.isfile(file_path)

    @staticmethod
    def get_file_size(file_path: str) -> int:
        """Get file size in bytes."""
        try:
            return os.path.getsize(file_path)
        except OSError:
            return 0

    @staticmethod
    def get_file_info(file_path: str) -> FileInfo:
        """Get comprehensive file information with Pydantic validation."""
        if not FileUtils.file_exists(file_path):
            return FileInfo(exists=False, error=f"File not found: {file_path}")

        try:
            return FileInfo(
                exists=True,
                path=file_path,
                name=os.path.basename(file_path),
                size=FileUtils.get_file_size(file_path),
                extension=Path(file_path).suffix.lower(),
            )
        except Exception as e:
            return FileInfo(exists=False, error=f"Error getting file info: {str(e)}")

    @staticmethod
    def read_text_file(file_path: str, encodings: list = None) -> TextFileResult:
        """Read text file with multiple encoding fallback.

        Args:
            file_path: Path to the text file
            encodings: List of encodings to try (default: ['utf-8', 'latin-1', 'cp1252'])

        Returns:
            TextFileResult with validated content, encoding used, and metadata
        """
        if encodings is None:
            encodings = ["utf-8", "latin-1", "cp1252"]

        file_info = FileUtils.get_file_info(file_path)
        if not file_info.exists:
            return TextFileResult(success=False, error=file_info.error, file_info=file_info)

        for encoding in encodings:
            try:
                with open(file_path, encoding=encoding) as f:
                    content = f.read()

                return TextFileResult(
                    success=True,
                    content=content,
                    encoding=encoding,
                    file_info=file_info,
                )
            except UnicodeDecodeError:
                continue
            except Exception as e:
                return TextFileResult(
                    success=False, error=f"Error reading file: {str(e)}", file_info=file_info
                )

        return TextFileResult(
            success=False,
            error="File appears to be binary and cannot be read as text",
            file_info=file_info,
        )

    @staticmethod
    def is_text_file(file_path: str) -> bool:
        """Check if file is likely a text file based on extension."""
        return Path(file_path).suffix.lower() in FileUtils.TEXT_EXTENSIONS

    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """Format file size in human-readable format."""
        if size_bytes == 0:
            return "0 bytes"
        elif size_bytes < 1024:
            return f"{size_bytes} bytes"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes // 1024} KB"
        else:
            return f"{size_bytes // (1024 * 1024)} MB"

    @staticmethod
    def create_tool_response(
        tool_name: str,
        result: str = None,
        error: str = None,
        file_info: FileInfo = None,
    ) -> str:
        """Create standardized tool response JSON with Pydantic validation."""
        if file_info:
            sanitized_file_info = FileInfo(
                exists=file_info.exists,
                path=None,
                name=file_info.name,
                size=file_info.size,
                extension=file_info.extension,
                error=file_info.error,
            )
        else:
            sanitized_file_info = None

        response = ToolResponse(
            tool_name=tool_name,
            result=result,
            error=error,
            file_info=sanitized_file_info,
        )

        return response.model_dump_json(indent=2)

    @staticmethod
    def resolve_file_reference(file_reference: str) -> str | None:
        """Resolve file reference (filename or URL) to full file path.

        Args:
            file_reference: Original filename from user upload OR URL

        Returns:
            Full path to the file, or None if not found/not supported
        """
        if file_reference.startswith(("http://", "https://", "ftp://")):
            return FileUtils.download_file_to_path(file_reference)

        return file_reference if FileUtils.file_exists(file_reference) else None

    @staticmethod
    def download_file_to_path(url: str, target_path: str = None) -> str:
        """Download file from URL to local path.

        Args:
            url: URL to download from
            target_path: Local path to save to. If None, creates temp file.

        Returns:
            Path to downloaded file

        Raises:
            IOError: If download fails
        """
        import tempfile
        from urllib.parse import urlparse

        import requests

        try:
            headers = {
                "User-Agent": "CMW-RAG-Engine/1.0 (+https://github.com/arterm-sedov/cmw-rag) Mozilla/5.0"
            }

            response = requests.get(url, headers=headers, stream=True, timeout=60, allow_redirects=True)
            response.raise_for_status()

            if target_path is None:
                parsed_url = urlparse(url)
                filename = os.path.basename(parsed_url.path) or "downloaded_file"
                _, ext = os.path.splitext(filename)
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                target_path = temp_file.name
                temp_file.close()

            with open(target_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return target_path

        except Exception as e:
            raise OSError(f"Error downloading file from {url}: {str(e)}") from e
