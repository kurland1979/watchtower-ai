"""
Tests for the heartbeat / self-monitoring module.
"""
import sys
import os
import json
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import agents.heartbeat as heartbeat


def _setup_temp_heartbeat(data: dict | None = None):
    """Helper: creates a temp heartbeat file and patches the module to use it."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    if data:
        json.dump(data, tmp)
    tmp.close()
    heartbeat.HEARTBEAT_FILE = tmp.name
    return tmp.name


def _cleanup(path):
    """Helper: removes temp file."""
    if os.path.exists(path):
        os.remove(path)


def test_record_heartbeat():
    """Test that recording a heartbeat writes to file."""
    path = _setup_temp_heartbeat()
    try:
        heartbeat.record_heartbeat("test_client")

        with open(path, "r") as f:
            data = json.load(f)

        assert "test_client" in data
        assert "last_success" in data["test_client"]
        assert data["test_client"]["status"] == "healthy"
    finally:
        _cleanup(path)


def test_check_heartbeat_healthy():
    """Test that a recent heartbeat passes the check."""
    now = datetime.now().isoformat()
    path = _setup_temp_heartbeat({"client1": {"last_success": now, "status": "healthy"}})
    try:
        alerts = heartbeat.check_heartbeat()
        assert len(alerts) == 0
    finally:
        _cleanup(path)


def test_check_heartbeat_stale():
    """Test that an old heartbeat triggers an alert."""
    old_time = (datetime.now() - timedelta(hours=30)).isoformat()
    path = _setup_temp_heartbeat({"client1": {"last_success": old_time, "status": "healthy"}})
    try:
        alerts = heartbeat.check_heartbeat()
        assert len(alerts) == 1
        assert "client1" in alerts[0]["message"]
    finally:
        _cleanup(path)


def test_check_heartbeat_no_data():
    """Test that missing heartbeat file triggers an alert."""
    heartbeat.HEARTBEAT_FILE = "/tmp/nonexistent_heartbeat_test.json"
    alerts = heartbeat.check_heartbeat()
    assert len(alerts) == 1
    assert "No heartbeat data" in alerts[0]["message"]


def test_get_health_status():
    """Test health status returns correct structure."""
    now = datetime.now().isoformat()
    path = _setup_temp_heartbeat({"c1": {"last_success": now, "status": "healthy"}})
    try:
        status = heartbeat.get_health_status()
        assert "c1" in status
        assert status["c1"]["status"] == "healthy"
    finally:
        _cleanup(path)
