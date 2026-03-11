import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

STORAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
DB_FILE = os.path.join(STORAGE_DIR, "watchtower.db")


def _get_connection() -> sqlite3.Connection:
    """Creates a connection to the SQLite database and ensures the table exists."""
    os.makedirs(STORAGE_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_name TEXT NOT NULL,
            text TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_scans_competitor
        ON scans (competitor_name, timestamp DESC)
    """)
    conn.commit()
    return conn


def save_scan(competitor_name: str, text: str) -> bool:
    """
    Saves a scan result for a competitor.
    Each scan is a new row — full history is preserved.

    Returns True on success, False on failure.
    Callers can use this to decide whether to proceed or alert.
    """
    conn = None
    try:
        conn = _get_connection()
        conn.execute(
            "INSERT INTO scans (competitor_name, text, timestamp) VALUES (?, ?, ?)",
            (competitor_name, text, datetime.now().isoformat())
        )
        conn.commit()
        logger.info(f"Saved scan for {competitor_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to save scan for {competitor_name}: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def get_previous_scan(competitor_name: str) -> str | None:
    """
    Returns the most recent scan text for a competitor, or None if first time.
    """
    conn = None
    try:
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT text FROM scans WHERE competitor_name = ? ORDER BY timestamp DESC LIMIT 1",
            (competitor_name,)
        )
        row = cursor.fetchone()
        if row:
            return row[0]
        return None
    except Exception as e:
        logger.error(f"Failed to load previous scan for {competitor_name}: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()
