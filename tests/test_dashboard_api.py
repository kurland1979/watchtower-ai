"""
Tests for dashboard/api.py

Covers: authentication middleware, input validation,
API endpoints, error handling.
"""

import pytest
import json
import os
from unittest.mock import patch, MagicMock

# Set the env var the API actually checks for auth
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
    """Helper: returns valid auth header."""
    return {"Authorization": "Bearer test-key-123"}


class TestAuthentication:
    """Tests for API key authentication middleware."""

    def test_no_auth_returns_401(self, client):
        """Should reject requests without auth header."""
        response = client.get("/api/competitors")
        assert response.status_code == 401

    def test_invalid_key_returns_401(self, client):
        """Should reject requests with wrong API key."""
        response = client.get(
            "/api/competitors",
            headers={"Authorization": "Bearer wrong-key"}
        )
        assert response.status_code == 401

    def test_valid_key_passes(self, client):
        """Should accept requests with valid API key."""
        with patch("agents.trend_analyzer.get_all_competitor_names", return_value=["TestCorp"]):
            response = client.get("/api/competitors", headers=auth_header())
            assert response.status_code == 200

    def test_health_no_auth_required(self, client):
        """Health endpoint should work without authentication."""
        response = client.get("/api/health")
        assert response.status_code == 200


class TestHealthEndpoint:
    """Tests for /api/health."""

    def test_returns_ok(self, client):
        """Should return status 'ok'."""
        response = client.get("/api/health")
        data = json.loads(response.data)
        assert data["status"] == "ok"


class TestCompetitorsEndpoint:
    """Tests for /api/competitors."""

    def test_returns_competitors(self, client):
        """Should return competitor names list."""
        with patch("dashboard.api.get_all_competitor_names", return_value=["CorpA", "CorpB"]):
            response = client.get("/api/competitors", headers=auth_header())
            data = json.loads(response.data)
            assert "competitors" in data
            assert "CorpA" in data["competitors"]


class TestScansEndpoint:
    """Tests for /api/scans/<competitor_name>."""

    def test_valid_competitor_name(self, client):
        """Should accept valid competitor names and return scans."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, "TestCorp", "some content here", "2024-01-15T08:00:00")
        ]
        mock_conn.execute.return_value = mock_cursor

        with patch("dashboard.api._get_connection", return_value=mock_conn):
            response = client.get("/api/scans/TestCorp", headers=auth_header())
            assert response.status_code == 200

    def test_invalid_competitor_name(self, client):
        """Should reject names with invalid characters."""
        response = client.get("/api/scans/evil;DROP%20TABLE", headers=auth_header())
        assert response.status_code == 400


class TestTrendsEndpoint:
    """Tests for /api/trends/<competitor_name>."""

    def test_returns_trends(self, client):
        """Should return trend analysis results."""
        mock_result = {"competitor": "TestCorp", "changes": []}
        with patch("dashboard.api.analyze_competitor_trends", return_value=mock_result):
            response = client.get("/api/trends/TestCorp", headers=auth_header())
            assert response.status_code == 200

    def test_returns_all_trends(self, client):
        """Should return trends for all competitors."""
        with patch("dashboard.api.get_all_competitor_names", return_value=["A"]), \
             patch("dashboard.api.generate_trend_report", return_value=[]):
            response = client.get("/api/trends", headers=auth_header())
            assert response.status_code == 200
