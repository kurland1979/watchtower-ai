"""
Tests for the trend analysis module.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.trend_analyzer import calculate_changes, _build_trend_summary


def test_calculate_changes_identical():
    """Test that identical scans show no significant change."""
    scans = [
        {"text": "Hello world", "timestamp": "2026-03-01T08:00:00"},
        {"text": "Hello world", "timestamp": "2026-03-02T08:00:00"},
    ]
    changes = calculate_changes(scans)
    assert len(changes) == 1
    assert changes[0]["similarity_ratio"] == 1.0
    assert changes[0]["is_significant"] is False


def test_calculate_changes_completely_different():
    """Test that completely different scans are flagged as significant."""
    scans = [
        {"text": "AAAA BBBB CCCC DDDD", "timestamp": "2026-03-01T08:00:00"},
        {"text": "XXXX YYYY ZZZZ WWWW", "timestamp": "2026-03-02T08:00:00"},
    ]
    changes = calculate_changes(scans)
    assert len(changes) == 1
    assert changes[0]["is_significant"] is True


def test_calculate_changes_too_few_scans():
    """Test that less than 2 scans returns empty list."""
    assert calculate_changes([]) == []
    assert calculate_changes([{"text": "one", "timestamp": "2026-03-01"}]) == []


def test_calculate_changes_multiple_scans():
    """Test change detection across multiple consecutive scans."""
    scans = [
        {"text": "version 1 of the text", "timestamp": "2026-03-01T08:00:00"},
        {"text": "version 1 of the text", "timestamp": "2026-03-02T08:00:00"},  # same
        {"text": "completely new pricing page launched today!", "timestamp": "2026-03-03T08:00:00"},  # different
    ]
    changes = calculate_changes(scans)
    assert len(changes) == 2
    assert changes[0]["is_significant"] is False  # v1 == v1
    assert changes[1]["is_significant"] is True   # v1 != new pricing


def test_build_trend_summary_no_changes():
    """Test summary when no changes detected."""
    summary = _build_trend_summary("TestCo", 30, 0, None, "stable", 100.0)
    assert "TestCo" in summary
    assert "No significant changes" in summary
    assert "stable" in summary.lower()


def test_build_trend_summary_with_changes():
    """Test summary when changes are detected."""
    summary = _build_trend_summary("TestCo", 30, 5, 6.0, "increasing", 60.0)
    assert "TestCo" in summary
    assert "5 significant changes" in summary
    assert "INCREASING" in summary
