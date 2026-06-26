from __future__ import annotations

from types import SimpleNamespace

from kg_engine.utils.formatters import format_with_citations


def test_format_with_citations_adds_section_links():
    docs = [
        SimpleNamespace(
            metadata={
                "kbId": "42",
                "title": "Intro",
                "url": "https://example.com/intro",
                "section_anchor": "#overview",
            }
        )
    ]

    result = format_with_citations("Answer", docs)

    # Accept both Russian and English headings for sources
    assert any(h in result for h in ("## Источники:", "## Sources:"))


def test_format_with_citations_dedups_by_url_when_kbid_missing():
    class Doc:
        def __init__(self, title: str, url: str):
            self.metadata = {"title": title, "url": url}

    docs = [
        Doc("Dup A", "https://kb.comindware.ru/article.php?id=5000#a"),
        Doc("Dup A", "https://kb.comindware.ru/article.php?id=5000#b"),
        Doc("Unique B", "https://kb.comindware.ru/article.php?id=6000"),
    ]
    out = format_with_citations("Answer", docs)
    # Should contain only two links despite different anchors for the same base URL
    assert out.count("https://kb.comindware.ru/article.php?id=5000") == 1
    assert out.count("https://kb.comindware.ru/article.php?id=6000") == 1


def test_format_with_citations_handles_missing_url():
    docs = [SimpleNamespace(metadata={"kbId": "99", "title": "Doc without URL"})]
    result = format_with_citations("Answer", docs)

    assert "Doc without URL" in result


def test_format_with_citations_no_docs_returns_answer():
    result = format_with_citations("Answer only", [])
    assert result == "Answer only"

