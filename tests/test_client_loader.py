"""
Tests for the multi-client configuration loader.
"""
import sys
import os
import json
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config.client_loader as client_loader


def _create_temp_client_dir(clients: list[dict]) -> str:
    """Helper: creates a temp clients directory with JSON files."""
    tmp_dir = tempfile.mkdtemp()
    clients_dir = os.path.join(tmp_dir, "clients")
    os.makedirs(clients_dir)

    for client in clients:
        file_path = os.path.join(clients_dir, f"{client['client_name']}.json")
        with open(file_path, "w") as f:
            json.dump(client, f)

    return tmp_dir, clients_dir


def test_load_single_client_valid():
    """Test loading a valid client config file."""
    client = {
        "client_name": "test_co",
        "industry": "testing",
        "competitors": [{"name": "Rival", "url": "https://rival.com", "active": True}]
    }
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(client, tmp)
    tmp.close()

    try:
        result = client_loader.load_single_client(tmp.name)
        assert result is not None
        assert result["client_name"] == "test_co"
        assert len(result["competitors"]) == 1
    finally:
        os.remove(tmp.name)


def test_load_single_client_missing_fields():
    """Test that a config missing required fields returns None."""
    bad_client = {"client_name": "incomplete"}  # missing industry and competitors
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(bad_client, tmp)
    tmp.close()

    try:
        result = client_loader.load_single_client(tmp.name)
        assert result is None
    finally:
        os.remove(tmp.name)


def test_load_single_client_invalid_json():
    """Test that invalid JSON returns None."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    tmp.write("this is not json{{{")
    tmp.close()

    try:
        result = client_loader.load_single_client(tmp.name)
        assert result is None
    finally:
        os.remove(tmp.name)


def test_load_all_clients_multi():
    """Test loading multiple client configs from directory."""
    clients = [
        {"client_name": "alpha", "industry": "tech", "competitors": []},
        {"client_name": "beta", "industry": "finance", "competitors": []},
    ]
    tmp_dir, clients_dir = _create_temp_client_dir(clients)

    # Patch the module to use our temp directory
    original_dir = client_loader.CLIENTS_DIR
    client_loader.CLIENTS_DIR = clients_dir

    try:
        result = client_loader.load_all_clients()
        assert len(result) == 2
        names = {c["client_name"] for c in result}
        assert "alpha" in names
        assert "beta" in names
    finally:
        client_loader.CLIENTS_DIR = original_dir
        shutil.rmtree(tmp_dir)
