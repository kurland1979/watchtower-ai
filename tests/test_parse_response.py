"""
Tests for _parse_response function in llm/analyzer.py
Tests the LLM response parser with various input formats.
"""
import sys
import os

# Add project root to path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from llm.analyzer import _parse_response


def test_parse_response_with_significant_change():
    """Test parsing a response that indicates a significant change."""
    response = (
        "SIGNIFICANT_CHANGE: YES\n"
        "SUMMARY: CrowdStrike launched a new AI-powered threat detection module\n"
        "IMPLICATION: Direct competition with our core product offering\n"
        "RECOMMENDED_ACTION: Schedule product review meeting to assess feature gap"
    )
    result = _parse_response(response)

    assert result["significant_change"] is True
    assert "CrowdStrike" in result["summary"]
    assert "competition" in result["implication"]
    assert "product review" in result["recommended_action"]


def test_parse_response_no_significant_change():
    """Test parsing a response with no significant changes."""
    response = (
        "SIGNIFICANT_CHANGE: NO\n"
        "SUMMARY: No significant changes detected\n"
        "IMPLICATION: N/A\n"
        "RECOMMENDED_ACTION: N/A"
    )
    result = _parse_response(response)

    assert result["significant_change"] is False
    assert result["summary"] == "No significant changes detected"
    assert result["implication"] == "N/A"
    assert result["recommended_action"] == "N/A"


def test_parse_response_empty_string():
    """Test parsing an empty response returns safe defaults."""
    result = _parse_response("")

    assert result["significant_change"] is False
    assert result["summary"] == "N/A"
    assert result["implication"] == "N/A"
    assert result["recommended_action"] == "N/A"


def test_parse_response_partial_response():
    """Test parsing a response missing some fields."""
    response = (
        "SIGNIFICANT_CHANGE: YES\n"
        "SUMMARY: New pricing page detected"
    )
    result = _parse_response(response)

    assert result["significant_change"] is True
    assert "pricing" in result["summary"]
    assert result["implication"] == "N/A"
    assert result["recommended_action"] == "N/A"


def test_parse_response_extra_whitespace():
    """Test parsing handles extra whitespace correctly."""
    response = (
        "SIGNIFICANT_CHANGE:   YES  \n"
        "SUMMARY:   New partnership announced  \n"
        "IMPLICATION:   Could affect our market position  \n"
        "RECOMMENDED_ACTION:   Monitor closely  "
    )
    result = _parse_response(response)

    assert result["significant_change"] is True
    assert result["summary"].strip() != ""


def test_parse_response_case_insensitive_yes():
    """Test that YES detection is case insensitive."""
    response = "SIGNIFICANT_CHANGE: yes\nSUMMARY: Test\nIMPLICATION: Test\nRECOMMENDED_ACTION: Test"
    result = _parse_response(response)
    assert result["significant_change"] is True


def test_parse_response_malformed_input():
    """Test parsing a completely unexpected response format."""
    response = "This is not in the expected format at all."
    result = _parse_response(response)

    assert result["significant_change"] is False
    assert result["summary"] == "N/A"
