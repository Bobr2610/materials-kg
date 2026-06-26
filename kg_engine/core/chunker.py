"""Token-aware, code-safe chunker."""
from __future__ import annotations

from typing import Iterable, List

from langchain_text_splitters import RecursiveCharacterTextSplitter

from kg_engine.llm.token_utils import TOKEN_ENCODING_NAME


def create_code_safe_text_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    """Create a code-safe splitter using sensible separators.

    Uses tiktoken-backed splitter for token-aware behavior.
    """
    separators: List[str] = [
        "\n\n```",  # code fences
        "\n\n### ",
        "\n\n## ",
        "\n\n# ",
        "\n\n",
        "\n",
        " ",
        "",
    ]
    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=TOKEN_ENCODING_NAME,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=separators,
    )


def split_text(text: str, chunk_size: int, chunk_overlap: int) -> Iterable[str]:
    splitter = create_code_safe_text_splitter(chunk_size, chunk_overlap)
    return splitter.split_text(text)


