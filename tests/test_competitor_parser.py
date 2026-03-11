"""
Tests for parse_competitor function in parsers/competitor_parser.py
Tests the HTML parser with various input scenarios.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parsers.competitor_parser import parse_competitor


def test_parse_competitor_success():
    """Test parsing valid HTML extracts text correctly."""
    scrape_result = {
        "name": "TestCompany",
        "url": "https://test.com",
        "html": "<html><body><h1>Our Product</h1><p>Best security solution</p></body></html>",
        "status": "success"
    }
    result = parse_competitor(scrape_result)

    assert result["status"] == "success"
    assert result["name"] == "TestCompany"
    assert "Our Product" in result["text"]
    assert "Best security solution" in result["text"]


def test_parse_competitor_removes_nav_and_footer():
    """Test that nav and footer elements are removed."""
    scrape_result = {
        "name": "TestCompany",
        "url": "https://test.com",
        "html": (
            "<html><body>"
            "<nav><a href='/'>Home</a><a href='/about'>About</a></nav>"
            "<h1>Main Content</h1>"
            "<p>Important text here</p>"
            "<footer><p>Copyright 2026</p></footer>"
            "</body></html>"
        ),
        "status": "success"
    }
    result = parse_competitor(scrape_result)

    assert result["status"] == "success"
    assert "Main Content" in result["text"]
    assert "Important text" in result["text"]
    assert "Home" not in result["text"]
    assert "Copyright" not in result["text"]


def test_parse_competitor_removes_script_and_style():
    """Test that script and style tags are completely removed."""
    scrape_result = {
        "name": "TestCompany",
        "url": "https://test.com",
        "html": (
            "<html><head><style>body { color: red; }</style></head>"
            "<body><h1>Real Content</h1>"
            "<script>alert('hack');</script>"
            "<p>Visible text</p></body></html>"
        ),
        "status": "success"
    }
    result = parse_competitor(scrape_result)

    assert result["status"] == "success"
    assert "Real Content" in result["text"]
    assert "alert" not in result["text"]
    assert "color: red" not in result["text"]


def test_parse_competitor_failed_scrape():
    """Test handling of a failed scrape result."""
    scrape_result = {
        "name": "FailedCompany",
        "url": "https://failed.com",
        "html": None,
        "status": "failed"
    }
    result = parse_competitor(scrape_result)

    assert result["status"] == "failed"
    assert result["text"] is None
    assert result["name"] == "FailedCompany"


def test_parse_competitor_empty_html():
    """Test that empty HTML is treated as failed (no content to parse)."""
    scrape_result = {
        "name": "EmptyCompany",
        "url": "https://empty.com",
        "html": "",
        "status": "success"
    }
    result = parse_competitor(scrape_result)

    # Empty string is falsy in Python — parser correctly treats it as no data
    assert result["status"] == "failed"
    assert result["text"] is None


def test_parse_competitor_extracts_list_items():
    """Test that list items (li) are extracted."""
    scrape_result = {
        "name": "ListCompany",
        "url": "https://list.com",
        "html": (
            "<html><body>"
            "<h2>Features</h2>"
            "<ul><li>Feature A</li><li>Feature B</li><li>Feature C</li></ul>"
            "</body></html>"
        ),
        "status": "success"
    }
    result = parse_competitor(scrape_result)

    assert result["status"] == "success"
    assert "Features" in result["text"]
    assert "Feature A" in result["text"]
    assert "Feature B" in result["text"]
    assert "Feature C" in result["text"]


def test_parse_competitor_preserves_heading_hierarchy():
    """Test that h1, h2, h3 are all extracted."""
    scrape_result = {
        "name": "HeadingCompany",
        "url": "https://heading.com",
        "html": (
            "<html><body>"
            "<h1>Main Title</h1>"
            "<h2>Section Title</h2>"
            "<h3>Subsection</h3>"
            "<p>Details here</p>"
            "</body></html>"
        ),
        "status": "success"
    }
    result = parse_competitor(scrape_result)

    assert result["status"] == "success"
    assert "Main Title" in result["text"]
    assert "Section Title" in result["text"]
    assert "Subsection" in result["text"]
    assert "Details here" in result["text"]
