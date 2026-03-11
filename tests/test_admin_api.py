"""
Tests for Admin API endpoints (client management CRUD).

Covers: creating clients, reading clients, updating clients,
deleting clients, adding/removing competitors, validation errors.
"""

import pytest
import json
import os
import tempfile
import shutil
from unittest.mock import patch

# Set the env var the API checks for auth
os.environ["WATCHTOWER_API_KEY"] = "test-key-123"
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SLACK_BOT_TOKEN", "test")
os.environ.setdefault("SLACK_CHANNEL_ID", "test")

from dashboard.api import app


@pytest.fixture
def client(tmp_path):
    """Create Flask test client with isolated clients directory."""
    app.config["TESTING"] = True

    # Create a temp clients directory to avoid touching real configs
    clients_dir = str(tmp_path / "clients")
    os.makedirs(clients_dir, exist_ok=True)

    # Seed with one test client
    seed_client = {
        "client_name": "test_client",
        "industry": "testing",
        "slack_channel_id": "C12345",
        "slack_bot_token": "",
        "competitors": [
            {
                "name": "TestCorp",
                "url": "https://www.testcorp.com",
                "pages": ["https://www.testcorp.com/"],
                "active": True,
                "js_render": False,
            }
        ],
    }
    with open(os.path.join(clients_dir, "test_client.json"), "w") as f:
        json.dump(seed_client, f)

    with patch("dashboard.api.CLIENTS_DIR", clients_dir), \
         patch("config.client_loader.CLIENTS_DIR", clients_dir):
        with app.test_client() as c:
            c._clients_dir = clients_dir
            yield c


def auth_header():
    """Helper: returns valid auth header."""
    return {"Authorization": "Bearer test-key-123"}


class TestAdminListClients:
    """Tests for GET /api/admin/clients."""

    def test_list_returns_all_clients(self, client):
        """Should return list of all configured clients."""
        response = client.get("/api/admin/clients", headers=auth_header())
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "clients" in data
        assert data["total"] >= 1
        names = [c["client_name"] for c in data["clients"]]
        assert "test_client" in names

    def test_list_requires_auth(self, client):
        """Should reject unauthenticated requests."""
        response = client.get("/api/admin/clients")
        assert response.status_code == 401


class TestAdminGetClient:
    """Tests for GET /api/admin/clients/<name>."""

    def test_get_existing_client(self, client):
        """Should return full details of existing client."""
        response = client.get("/api/admin/clients/test_client", headers=auth_header())
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["client_name"] == "test_client"
        assert data["industry"] == "testing"
        assert len(data["competitors"]) == 1

    def test_get_nonexistent_client(self, client):
        """Should return 404 for unknown client."""
        response = client.get("/api/admin/clients/nonexistent", headers=auth_header())
        assert response.status_code == 404


class TestAdminCreateClient:
    """Tests for POST /api/admin/clients."""

    def test_create_valid_client(self, client):
        """Should create a new client and return 201."""
        new_client = {
            "client_name": "new_startup",
            "industry": "fintech",
            "competitors": [
                {
                    "name": "Stripe",
                    "url": "https://www.stripe.com",
                }
            ],
        }
        response = client.post(
            "/api/admin/clients",
            data=json.dumps(new_client),
            content_type="application/json",
            headers=auth_header(),
        )
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data["client"]["client_name"] == "new_startup"
        assert data["client"]["competitors"][0]["active"] is True  # default applied

    def test_create_duplicate_client(self, client):
        """Should return 409 if client already exists."""
        duplicate = {
            "client_name": "test_client",
            "industry": "testing",
            "competitors": [],
        }
        response = client.post(
            "/api/admin/clients",
            data=json.dumps(duplicate),
            content_type="application/json",
            headers=auth_header(),
        )
        assert response.status_code == 409

    def test_create_missing_fields(self, client):
        """Should return 400 if required fields are missing."""
        incomplete = {"client_name": "broken"}
        response = client.post(
            "/api/admin/clients",
            data=json.dumps(incomplete),
            content_type="application/json",
            headers=auth_header(),
        )
        assert response.status_code == 400

    def test_create_invalid_url(self, client):
        """Should reject competitors with invalid URLs."""
        bad_url_client = {
            "client_name": "bad_urls",
            "industry": "testing",
            "competitors": [
                {"name": "Evil", "url": "ftp://internal.server.com"}
            ],
        }
        response = client.post(
            "/api/admin/clients",
            data=json.dumps(bad_url_client),
            content_type="application/json",
            headers=auth_header(),
        )
        assert response.status_code == 400

    def test_create_ssrf_blocked(self, client):
        """Should block SSRF attempts in competitor URLs."""
        ssrf_client = {
            "client_name": "ssrf_attempt",
            "industry": "hacking",
            "competitors": [
                {"name": "Internal", "url": "http://localhost:8080/admin"}
            ],
        }
        response = client.post(
            "/api/admin/clients",
            data=json.dumps(ssrf_client),
            content_type="application/json",
            headers=auth_header(),
        )
        assert response.status_code == 400


class TestAdminUpdateClient:
    """Tests for PUT /api/admin/clients/<name>."""

    def test_update_industry(self, client):
        """Should update only the industry field."""
        response = client.put(
            "/api/admin/clients/test_client",
            data=json.dumps({"industry": "cybersecurity"}),
            content_type="application/json",
            headers=auth_header(),
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["client"]["industry"] == "cybersecurity"
        # Competitors should remain unchanged
        assert len(data["client"]["competitors"]) == 1

    def test_update_nonexistent(self, client):
        """Should return 404 for unknown client."""
        response = client.put(
            "/api/admin/clients/nonexistent",
            data=json.dumps({"industry": "test"}),
            content_type="application/json",
            headers=auth_header(),
        )
        assert response.status_code == 404


class TestAdminDeleteClient:
    """Tests for DELETE /api/admin/clients/<name>."""

    def test_delete_existing_client(self, client):
        """Should delete client and return success."""
        response = client.delete(
            "/api/admin/clients/test_client",
            headers=auth_header(),
        )
        assert response.status_code == 200

        # Verify it's gone
        response = client.get("/api/admin/clients/test_client", headers=auth_header())
        assert response.status_code == 404

    def test_delete_nonexistent(self, client):
        """Should return 404 for unknown client."""
        response = client.delete(
            "/api/admin/clients/nonexistent",
            headers=auth_header(),
        )
        assert response.status_code == 404


class TestAdminAddCompetitor:
    """Tests for POST /api/admin/clients/<name>/competitors."""

    def test_add_valid_competitor(self, client):
        """Should add a new competitor to existing client."""
        new_comp = {
            "name": "NewCorp",
            "url": "https://www.newcorp.com",
            "pages": ["https://www.newcorp.com/", "https://www.newcorp.com/products"],
        }
        response = client.post(
            "/api/admin/clients/test_client/competitors",
            data=json.dumps(new_comp),
            content_type="application/json",
            headers=auth_header(),
        )
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data["total_competitors"] == 2

    def test_add_duplicate_competitor(self, client):
        """Should reject duplicate competitor names."""
        duplicate = {
            "name": "TestCorp",
            "url": "https://www.testcorp2.com",
        }
        response = client.post(
            "/api/admin/clients/test_client/competitors",
            data=json.dumps(duplicate),
            content_type="application/json",
            headers=auth_header(),
        )
        assert response.status_code == 409

    def test_add_competitor_to_nonexistent_client(self, client):
        """Should return 404 for unknown client."""
        comp = {"name": "Corp", "url": "https://www.corp.com"}
        response = client.post(
            "/api/admin/clients/nonexistent/competitors",
            data=json.dumps(comp),
            content_type="application/json",
            headers=auth_header(),
        )
        assert response.status_code == 404


class TestAdminRemoveCompetitor:
    """Tests for DELETE /api/admin/clients/<name>/competitors/<comp>."""

    def test_remove_existing_competitor(self, client):
        """Should remove competitor and return success."""
        response = client.delete(
            "/api/admin/clients/test_client/competitors/TestCorp",
            headers=auth_header(),
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["remaining_competitors"] == 0

    def test_remove_nonexistent_competitor(self, client):
        """Should return 404 for unknown competitor."""
        response = client.delete(
            "/api/admin/clients/test_client/competitors/FakeCorp",
            headers=auth_header(),
        )
        assert response.status_code == 404
