"""
Tests for agents/storage.py

Covers: save_scan (with bool return), get_previous_scan, connection handling,
error recovery, timestamp ordering.
"""

import pytest
import os
import sqlite3
from unittest.mock import patch

from agents.storage import save_scan, get_previous_scan, _get_connection, DB_FILE


@pytest.fixture(autouse=True)
def clean_db(tmp_path):
    """Use a temporary database for each test to avoid cross-contamination."""
    test_db = str(tmp_path / "test_watchtower.db")
    with patch("agents.storage.DB_FILE", test_db):
        with patch("agents.storage.STORAGE_DIR", str(tmp_path)):
            yield test_db


class TestSaveScan:
    """Tests for save_scan function."""

    def test_returns_true_on_success(self, clean_db):
        """save_scan should return True when insert succeeds."""
        with patch("agents.storage.DB_FILE", clean_db):
            with patch("agents.storage.STORAGE_DIR", os.path.dirname(clean_db)):
                result = save_scan("TestCorp", "some content")
                assert result is True

    def test_saves_and_retrieves(self, clean_db):
        """Saved scan should be retrievable via get_previous_scan."""
        with patch("agents.storage.DB_FILE", clean_db):
            with patch("agents.storage.STORAGE_DIR", os.path.dirname(clean_db)):
                save_scan("TestCorp", "content v1")
                result = get_previous_scan("TestCorp")
                assert result == "content v1"

    def test_returns_latest_scan(self, clean_db):
        """get_previous_scan should return the most recent scan."""
        with patch("agents.storage.DB_FILE", clean_db):
            with patch("agents.storage.STORAGE_DIR", os.path.dirname(clean_db)):
                save_scan("TestCorp", "old content")
                save_scan("TestCorp", "new content")
                result = get_previous_scan("TestCorp")
                assert result == "new content"

    def test_separate_competitors(self, clean_db):
        """Scans from different competitors should be independent."""
        with patch("agents.storage.DB_FILE", clean_db):
            with patch("agents.storage.STORAGE_DIR", os.path.dirname(clean_db)):
                save_scan("CorpA", "content A")
                save_scan("CorpB", "content B")
                assert get_previous_scan("CorpA") == "content A"
                assert get_previous_scan("CorpB") == "content B"

    def test_no_previous_scan_returns_none(self, clean_db):
        """get_previous_scan should return None for unknown competitors."""
        with patch("agents.storage.DB_FILE", clean_db):
            with patch("agents.storage.STORAGE_DIR", os.path.dirname(clean_db)):
                result = get_previous_scan("UnknownCorp")
                assert result is None

    def test_returns_false_on_db_error(self):
        """save_scan should return False when database is inaccessible."""
        with patch("agents.storage._get_connection", side_effect=Exception("DB locked")):
            result = save_scan("TestCorp", "content")
            assert result is False

    def test_handles_empty_text(self, clean_db):
        """Should handle empty string text without crashing."""
        with patch("agents.storage.DB_FILE", clean_db):
            with patch("agents.storage.STORAGE_DIR", os.path.dirname(clean_db)):
                result = save_scan("TestCorp", "")
                assert result is True

    def test_handles_unicode_text(self, clean_db):
        """Should handle Unicode content (Hebrew, emoji, etc.)."""
        with patch("agents.storage.DB_FILE", clean_db):
            with patch("agents.storage.STORAGE_DIR", os.path.dirname(clean_db)):
                result = save_scan("TestCorp", "שלום עולם 🚀")
                assert result is True
                retrieved = get_previous_scan("TestCorp")
                assert retrieved == "שלום עולם 🚀"
