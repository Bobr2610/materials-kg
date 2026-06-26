"""Tests for tool utility functions."""
from __future__ import annotations

import json

import pytest

from kg_engine.retrieval.retriever import Article
from kg_engine.tools.utils import (
    accumulate_articles_from_tool_results,
    extract_metadata_from_tool_result,
    parse_tool_result_to_articles,
)


class TestParseToolResultToArticles:
    """Tests for parse_tool_result_to_articles function."""

    def test_parse_single_article(self):
        """Test parsing tool result with single article."""
        tool_result = json.dumps({
            "articles": [
                {
                    "kb_id": "123",
                    "content": "Test content",
                    "metadata": {"title": "Test Article", "article_url": "https://example.com/123"},
                }
            ],
            "metadata": {"query": "test", "articles_count": 1, "has_results": True},
        })

        articles = parse_tool_result_to_articles(tool_result)

        assert len(articles) == 1
        assert articles[0].kb_id == "123"
        assert articles[0].content == "Test content"
        assert articles[0].metadata["title"] == "Test Article"

    def test_parse_multiple_articles(self):
        """Test parsing tool result with multiple articles."""
        tool_result = json.dumps({
            "articles": [
                {"kb_id": "1", "content": "Content 1", "metadata": {"title": "Article 1"}},
                {"kb_id": "2", "content": "Content 2", "metadata": {"title": "Article 2"}},
                {"kb_id": "3", "content": "Content 3", "metadata": {"title": "Article 3"}},
            ],
            "metadata": {"query": "test", "articles_count": 3, "has_results": True},
        })

        articles = parse_tool_result_to_articles(tool_result)

        assert len(articles) == 3
        assert articles[0].kb_id == "1"
        assert articles[1].kb_id == "2"
        assert articles[2].kb_id == "3"

    def test_parse_empty_articles(self):
        """Test parsing tool result with no articles."""
        tool_result = json.dumps({
            "articles": [],
            "metadata": {"query": "test", "articles_count": 0, "has_results": False},
        })

        articles = parse_tool_result_to_articles(tool_result)

        assert len(articles) == 0

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON returns empty list."""
        tool_result = "not valid json"

        articles = parse_tool_result_to_articles(tool_result)

        assert len(articles) == 0

    def test_parse_missing_articles_key(self):
        """Test parsing result with missing articles key."""
        tool_result = json.dumps({"metadata": {"query": "test"}})

        articles = parse_tool_result_to_articles(tool_result)

        assert len(articles) == 0


class TestAccumulateArticlesFromToolResults:
    """Tests for accumulate_articles_from_tool_results function."""

    def test_accumulate_single_result(self):
        """Test accumulating articles from single tool call."""
        result1 = json.dumps({
            "articles": [
                {"kb_id": "1", "content": "Content 1", "metadata": {"title": "Article 1"}},
                {"kb_id": "2", "content": "Content 2", "metadata": {"title": "Article 2"}},
            ],
            "metadata": {"articles_count": 2},
        })

        articles = accumulate_articles_from_tool_results([result1])

        assert len(articles) == 2
        assert articles[0].kb_id == "1"
        assert articles[1].kb_id == "2"

    def test_accumulate_multiple_results(self):
        """Test accumulating articles from multiple tool calls."""
        result1 = json.dumps({
            "articles": [
                {"kb_id": "1", "content": "Content 1", "metadata": {"title": "Article 1"}},
                {"kb_id": "2", "content": "Content 2", "metadata": {"title": "Article 2"}},
            ],
            "metadata": {"articles_count": 2},
        })

        result2 = json.dumps({
            "articles": [
                {"kb_id": "3", "content": "Content 3", "metadata": {"title": "Article 3"}},
            ],
            "metadata": {"articles_count": 1},
        })

        result3 = json.dumps({
            "articles": [
                {"kb_id": "4", "content": "Content 4", "metadata": {"title": "Article 4"}},
                {"kb_id": "5", "content": "Content 5", "metadata": {"title": "Article 5"}},
            ],
            "metadata": {"articles_count": 2},
        })

        articles = accumulate_articles_from_tool_results([result1, result2, result3])

        assert len(articles) == 5
        assert [a.kb_id for a in articles] == ["1", "2", "3", "4", "5"]

    def test_accumulate_with_duplicates(self):
        """Test accumulating deduplicates by kb_id to prevent duplicate content."""
        result1 = json.dumps({
            "articles": [
                {"kb_id": "1", "content": "Content 1", "metadata": {"title": "Article 1"}},
            ],
            "metadata": {"articles_count": 1},
        })

        result2 = json.dumps({
            "articles": [
                {"kb_id": "1", "content": "Content 1", "metadata": {"title": "Article 1"}},  # Duplicate
                {"kb_id": "2", "content": "Content 2", "metadata": {"title": "Article 2"}},
            ],
            "metadata": {"articles_count": 2},
        })

        articles = accumulate_articles_from_tool_results([result1, result2])

        # NEW BEHAVIOR: Deduplication happens during accumulation by kb_id
        # This prevents the LLM from seeing duplicate article content
        assert len(articles) == 2  # Only unique articles
        assert articles[0].kb_id == "1"  # First occurrence kept
        assert articles[1].kb_id == "2"  # Second unique article

    def test_accumulate_empty_results(self):
        """Test accumulating from empty tool results."""
        articles = accumulate_articles_from_tool_results([])

        assert len(articles) == 0

    def test_accumulate_with_some_empty(self):
        """Test accumulating when some tool calls return no articles."""
        result1 = json.dumps({
            "articles": [
                {"kb_id": "1", "content": "Content 1", "metadata": {"title": "Article 1"}},
            ],
            "metadata": {"articles_count": 1},
        })

        result2 = json.dumps({
            "articles": [],  # No results
            "metadata": {"articles_count": 0, "has_results": False},
        })

        result3 = json.dumps({
            "articles": [
                {"kb_id": "2", "content": "Content 2", "metadata": {"title": "Article 2"}},
            ],
            "metadata": {"articles_count": 1},
        })

        articles = accumulate_articles_from_tool_results([result1, result2, result3])

        assert len(articles) == 2
        assert articles[0].kb_id == "1"
        assert articles[1].kb_id == "2"


class TestExtractMetadataFromToolResult:
    """Tests for extract_metadata_from_tool_result function."""

    def test_extract_metadata(self):
        """Test extracting metadata from tool result."""
        tool_result = json.dumps({
            "articles": [],
            "metadata": {
                "query": "test query",
                "top_k_requested": 5,
                "articles_count": 3,
                "has_results": True,
            },
        })

        metadata = extract_metadata_from_tool_result(tool_result)

        assert metadata["query"] == "test query"
        assert metadata["top_k_requested"] == 5
        assert metadata["articles_count"] == 3
        assert metadata["has_results"] is True

    def test_extract_metadata_invalid_json(self):
        """Test extracting metadata from invalid JSON returns empty dict."""
        tool_result = "not valid json"

        metadata = extract_metadata_from_tool_result(tool_result)

        assert metadata == {}

    def test_extract_metadata_missing_key(self):
        """Test extracting metadata when key is missing."""
        tool_result = json.dumps({"articles": []})

        metadata = extract_metadata_from_tool_result(tool_result)

        assert metadata == {}


class TestIntegrationWithFormatWithCitations:
    """Integration tests with format_with_citations."""

    def test_accumulated_articles_deduplicate_in_citations(self):
        """Test that format_with_citations deduplicates accumulated articles."""
        from kg_engine.utils.formatters import format_with_citations

        # Simulate multiple tool calls with duplicate article
        result1 = json.dumps({
            "articles": [
                {"kb_id": "1", "content": "Content 1", "metadata": {"title": "Article 1", "kbId": "1"}},
                {"kb_id": "2", "content": "Content 2", "metadata": {"title": "Article 2", "kbId": "2"}},
            ],
            "metadata": {"articles_count": 2},
        })

        result2 = json.dumps({
            "articles": [
                {"kb_id": "2", "content": "Content 2", "metadata": {"title": "Article 2", "kbId": "2"}},  # Duplicate
                {"kb_id": "3", "content": "Content 3", "metadata": {"title": "Article 3", "kbId": "3"}},
            ],
            "metadata": {"articles_count": 2},
        })

        # Accumulate articles - NEW BEHAVIOR: deduplicates during accumulation
        all_articles = accumulate_articles_from_tool_results([result1, result2])
        assert len(all_articles) == 3  # Now deduplicates, only unique articles

        # Format with citations - articles already deduplicated
        formatted = format_with_citations("Answer text", all_articles)

        # Should only cite each article once
        assert "1. [Article 1]" in formatted
        assert "2. [Article 2]" in formatted
        assert "3. [Article 3]" in formatted
        assert formatted.count("Article 2") == 1  # Only appears once

    def test_accumulated_articles_preserve_order(self):
        """Test that citations preserve order from first occurrence."""
        from kg_engine.utils.formatters import format_with_citations

        result1 = json.dumps({
            "articles": [
                {"kb_id": "A", "content": "Content A", "metadata": {"title": "Article A", "kbId": "A"}},
            ],
            "metadata": {"articles_count": 1},
        })

        result2 = json.dumps({
            "articles": [
                {"kb_id": "B", "content": "Content B", "metadata": {"title": "Article B", "kbId": "B"}},
            ],
            "metadata": {"articles_count": 1},
        })

        result3 = json.dumps({
            "articles": [
                {"kb_id": "C", "content": "Content C", "metadata": {"title": "Article C", "kbId": "C"}},
            ],
            "metadata": {"articles_count": 1},
        })

        all_articles = accumulate_articles_from_tool_results([result1, result2, result3])
        formatted = format_with_citations("Answer", all_articles)

        # Check order: A, B, C
        assert formatted.index("Article A") < formatted.index("Article B")
        assert formatted.index("Article B") < formatted.index("Article C")

