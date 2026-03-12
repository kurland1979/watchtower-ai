"""
Tests for Report API endpoints (daily/weekly/monthly comparisons).

Covers: daily comparison, weekly report, monthly report,
single competitor reports, edge cases with no data.
"""

import pytest
import json
import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# Set auth env var
os.environ["WATCHTOWER_API_KEY"] = "test-key-123"
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SLACK_BOT_TOKEN", "test")
os.environ.setdefault("SLACK_CHANNEL_ID", "test")

from dashboard.api import app


@pytest.fixture
def client():
    """Create Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def auth_header():
    return {"Authorization": "Bearer test-key-123"}


def _make_scans(count, days_back=7):
    """Generate mock scan data for testing."""
    scans = []
    now = datetime.now()
    for i in range(count):
        ts = (now - timedelta(days=days_back - i)).isoformat()
        text = f"Content version {i}. " + ("Changed significantly. " * (10 if i % 2 == 0 else 0))
        scans.append({"text": text, "timestamp": ts})
    return scans


class TestDailyReport:
    """Tests for GET /api/reports/daily."""

    def test_daily_requires_auth(self, client):
        response = client.get("/api/reports/daily")
        assert response.status_code == 401

    def test_daily_returns_report(self, client):
        scans = _make_scans(3, days_back=2)
        with patch("dashboard.api.get_all_competitor_names", return_value=["TestCorp"]), \
             patch("dashboard.api.get_scans_for_period", return_value=scans):
            response = client.get("/api/reports/daily", headers=auth_header())
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["report"] == "daily"
            assert len(data["competitors"]) == 1

    def test_daily_no_comparison_when_single_scan(self, client):
        scans = [{"text": "Only one scan", "timestamp": datetime.now().isoformat()}]
        with patch("dashboard.api.get_all_competitor_names", return_value=["TestCorp"]), \
             patch("dashboard.api.get_scans_for_period", return_value=scans):
            response = client.get("/api/reports/daily", headers=auth_header())
            data = json.loads(response.data)
            assert data["competitors"][0]["status"] == "no_comparison"

    def test_daily_empty_competitors(self, client):
        with patch("dashboard.api.get_all_competitor_names", return_value=[]):
            response = client.get("/api/reports/daily", headers=auth_header())
            data = json.loads(response.data)
            assert data["total"] == 0

    def test_daily_compared_has_fields(self, client):
        scans = _make_scans(2, days_back=2)
        with patch("dashboard.api.get_all_competitor_names", return_value=["TestCorp"]), \
             patch("dashboard.api.get_scans_for_period", return_value=scans):
            response = client.get("/api/reports/daily", headers=auth_header())
            data = json.loads(response.data)
            comp = data["competitors"][0]
            assert comp["status"] == "compared"
            assert "change_percent" in comp
            assert "similarity" in comp
            assert "is_significant" in comp
            assert "scan_date" in comp


class TestWeeklyReport:
    """Tests for GET /api/reports/weekly."""

    def test_weekly_requires_auth(self, client):
        response = client.get("/api/reports/weekly")
        assert response.status_code == 401

    def test_weekly_returns_all_competitors(self, client):
        scans = _make_scans(5, days_back=7)
        with patch("dashboard.api.get_all_competitor_names", return_value=["A", "B"]), \
             patch("dashboard.api.get_scans_for_period", return_value=scans):
            response = client.get("/api/reports/weekly", headers=auth_header())
            data = json.loads(response.data)
            assert data["report"] == "weekly"
            assert data["period_days"] == 7
            assert len(data["competitors"]) == 2

    def test_weekly_single_competitor(self, client):
        scans = _make_scans(4, days_back=7)
        with patch("dashboard.api.get_scans_for_period", return_value=scans):
            response = client.get("/api/reports/weekly/TestCorp", headers=auth_header())
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["competitor"] == "TestCorp"
            assert data["period_days"] == 7
            assert "entries" in data

    def test_weekly_single_invalid_name(self, client):
        response = client.get("/api/reports/weekly/evil;DROP", headers=auth_header())
        assert response.status_code == 400

    def test_weekly_entries_have_required_fields(self, client):
        scans = _make_scans(3, days_back=7)
        with patch("dashboard.api.get_scans_for_period", return_value=scans):
            response = client.get("/api/reports/weekly/TestCorp", headers=auth_header())
            data = json.loads(response.data)
            if data["entries"]:
                entry = data["entries"][0]
                assert "date" in entry
                assert "similarity" in entry
                assert "change_percent" in entry
                assert "is_significant" in entry
                assert "length_diff" in entry


class TestMonthlyReport:
    """Tests for GET /api/reports/monthly."""

    def test_monthly_requires_auth(self, client):
        response = client.get("/api/reports/monthly")
        assert response.status_code == 401

    def test_monthly_returns_all_competitors(self, client):
        scans = _make_scans(10, days_back=30)
        with patch("dashboard.api.get_all_competitor_names", return_value=["X", "Y", "Z"]), \
             patch("dashboard.api.get_scans_for_period", return_value=scans):
            response = client.get("/api/reports/monthly", headers=auth_header())
            data = json.loads(response.data)
            assert data["report"] == "monthly"
            assert data["period_days"] == 30
            assert len(data["competitors"]) == 3

    def test_monthly_single_competitor(self, client):
        scans = _make_scans(8, days_back=30)
        with patch("dashboard.api.get_scans_for_period", return_value=scans):
            response = client.get("/api/reports/monthly/TestCorp", headers=auth_header())
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["competitor"] == "TestCorp"
            assert data["period_days"] == 30

    def test_monthly_single_invalid_name(self, client):
        response = client.get("/api/reports/monthly/evil;DROP%20TABLE", headers=auth_header())
        assert response.status_code == 400

    def test_monthly_empty_scans(self, client):
        with patch("dashboard.api.get_scans_for_period", return_value=[]):
            response = client.get("/api/reports/monthly/TestCorp", headers=auth_header())
            data = json.loads(response.data)
            assert data["total_scans"] == 0
            assert data["entries"] == []


class TestBuildComparisonData:
    """Tests for _build_comparison_data helper."""

    def test_no_scans_returns_empty(self, client):
        with patch("dashboard.api.get_scans_for_period", return_value=[]):
            response = client.get("/api/reports/weekly/TestCorp", headers=auth_header())
            data = json.loads(response.data)
            assert data["total_scans"] == 0
            assert data["significant_changes"] == 0

    def test_single_scan_no_entries(self, client):
        scans = [{"text": "Single scan only", "timestamp": datetime.now().isoformat()}]
        with patch("dashboard.api.get_scans_for_period", return_value=scans):
            response = client.get("/api/reports/weekly/TestCorp", headers=auth_header())
            data = json.loads(response.data)
            assert data["total_scans"] == 1
            assert data["total_comparisons"] == 0
