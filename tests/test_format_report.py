"""
Tests for format_report function in notifiers/slack_notifier.py
Tests the Slack message formatting logic.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from notifiers.slack_notifier import format_report


def test_format_report_with_results():
    """Test formatting a report with significant changes."""
    results = [
        {
            "name": "CrowdStrike",
            "url": "https://crowdstrike.com",
            "summary": "New AI module launched",
            "implication": "Direct competition",
            "recommended_action": "Review our roadmap"
        }
    ]
    report = format_report(results)

    assert "WatchTower Daily Report" in report
    assert "CrowdStrike" in report
    assert "New AI module launched" in report
    assert "Direct competition" in report
    assert "Review our roadmap" in report


def test_format_report_empty_results():
    """Test formatting a report with no significant changes."""
    report = format_report([])

    assert "WatchTower Daily Report" in report
    assert "No significant" in report


def test_format_report_multiple_competitors():
    """Test formatting with multiple competitors."""
    results = [
        {
            "name": "CompanyA",
            "url": "https://a.com",
            "summary": "Change A",
            "implication": "Impact A",
            "recommended_action": "Action A"
        },
        {
            "name": "CompanyB",
            "url": "https://b.com",
            "summary": "Change B",
            "implication": "Impact B",
            "recommended_action": "Action B"
        }
    ]
    report = format_report(results)

    assert "CompanyA" in report
    assert "CompanyB" in report
    assert "Change A" in report
    assert "Change B" in report
