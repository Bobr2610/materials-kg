from __future__ import annotations

import tiktoken

from kg_engine.llm.token_utils import estimate_tokens_for_request


def test_estimate_tokens_for_request_counts_components():
    out = estimate_tokens_for_request(
        system_prompt="sys",
        question="q",
        context="abc",
        reserved_output_tokens=50,
        overhead=10,
    )
    assert out["output_tokens"] == 50
    assert out["total_tokens"] >= out["output_tokens"]
    assert out["input_tokens"] > 0


def test_estimate_tokens_for_request_counts_large_strings():
    """Test that large-ish strings are counted accurately using tiktoken."""
    # Use a reasonably large, natural-language-like string without relying on
    # pathological long runs of a single character that make tiktoken slow.
    base = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
    large_string = base * 800  # ~50K+ characters
    out = estimate_tokens_for_request(
        system_prompt="",
        question="",
        context=large_string,
        reserved_output_tokens=0,
        overhead=0,
    )
    # Exact count: should match tiktoken encoding
    expected_tokens = len(tiktoken.get_encoding("cl100k_base").encode(large_string))
    assert out["input_tokens"] == expected_tokens
    assert out["total_tokens"] == expected_tokens


