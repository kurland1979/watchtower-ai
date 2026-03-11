"""
Tests for the smart text chunking module.
Verifies that text is prioritized correctly by section.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parsers.text_chunker import classify_block, smart_chunk


def test_classify_pricing_block():
    """Test that pricing-related text is classified as pricing."""
    assert classify_block("Our pricing starts at $99 per month") == "pricing"
    assert classify_block("Enterprise plan available") == "pricing"


def test_classify_features_block():
    """Test that feature-related text is classified as features."""
    assert classify_block("New integration with cloud platform") == "features"
    assert classify_block("Advanced endpoint detection capabilities") == "features"


def test_classify_announcements_block():
    """Test that announcement-related text is classified as announcements."""
    assert classify_block("We are excited to announce our new partnership") == "announcements"
    assert classify_block("Introducing our latest product release") == "announcements"


def test_classify_general_block():
    """Test that generic text is classified as general."""
    assert classify_block("Welcome to our website") == "general"
    assert classify_block("About us") == "general"


def test_smart_chunk_empty_text():
    """Test smart_chunk with empty input returns empty string."""
    assert smart_chunk("") == ""
    assert smart_chunk("   ") == ""


def test_smart_chunk_within_budget():
    """Test that all text is included when under the budget."""
    text = "Pricing starts at $50\nNew feature launched\nGeneral info"
    result = smart_chunk(text, char_budget=5000)
    assert "Pricing" in result
    assert "feature" in result
    assert "General" in result


def test_smart_chunk_prioritizes_pricing():
    """Test that pricing content is prioritized over general content."""
    # Create text where general content comes first but pricing is more important
    lines = []
    # Fill with general content
    for i in range(50):
        lines.append(f"This is general content line number {i}")
    # Add pricing at the end
    lines.append("Our pricing starts at $99 per month for the enterprise plan")

    text = "\n".join(lines)
    result = smart_chunk(text, char_budget=500)

    # Pricing should be included even though it was at the end
    assert "pricing" in result.lower() or "$99" in result


def test_smart_chunk_respects_budget():
    """Test that the chunk stays within the character budget."""
    text = "\n".join([f"Line {i} with some content to fill space" for i in range(100)])
    result = smart_chunk(text, char_budget=500)
    assert len(result) <= 500


def test_smart_chunk_single_block():
    """Test smart_chunk with only one block of text."""
    text = "Just a single line of text about pricing at $100"
    result = smart_chunk(text, char_budget=5000)
    assert "pricing" in result.lower()
