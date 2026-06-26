from __future__ import annotations

import tiktoken

from kg_engine.core.chunker import split_text


def test_split_text_respects_chunk_size_tokens():
    enc = tiktoken.get_encoding("cl100k_base")
    text = "# Title\n\n" + ("A" * 2000)
    chunks = list(split_text(text, chunk_size=500, chunk_overlap=150))

    # Verify token lengths are within a small buffer of configured chunk size
    # Allow reasonable headroom for separators; splitter aims for ~500 tokens
    assert all(len(enc.encode(chunk)) <= 700 for chunk in chunks)


def test_split_text_preserves_code_fences():
    text = "# Example\n\n```python\nprint('chunking')\n```\n"
    chunks = list(split_text(text, chunk_size=100, chunk_overlap=20))

    code_chunks = [c for c in chunks if "```python" in c]
    assert code_chunks, "Expected chunk with code fence"
    assert all("```" in c.split("```python")[-1] for c in code_chunks)

