"""
Circuit Breaker Pattern — SQLite-Backed Persistence.

When a competitor's website is persistently down, retrying every day wastes
time and API resources. The circuit breaker stops retrying after N consecutive
failures and only tests again after a cooldown period.

States:
    CLOSED  — Normal operation. Requests pass through. Failures increment counter.
    OPEN    — Requests are blocked. After timeout, transitions to HALF_OPEN.
    HALF_OPEN — One test request is allowed. Success → CLOSED. Failure → OPEN.

Persistence:
    State is stored in SQLite (same DB as scans) instead of a JSON file.
    Why? SQLite handles concurrent writes safely, supports atomic updates,
    and doesn't corrupt on unexpected process termination.

Usage:
    cb = CircuitBreaker()
    if cb.can_execute("CrowdStrike"):
        result = scrape("CrowdStrike")
        if result.success:
            cb.record_success("CrowdStrike")
        else:
            cb.record_failure("CrowdStrike")
    else:
        logger.info("Circuit OPEN for CrowdStrike — skipping")
"""

import sqlite3
import os
import logging
from datetime import datetime, timedelta

from config.settings import settings

logger = logging.getLogger(__name__)

# Use the same database as storage — keeps everything in one place
DB_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "watchtower.db")

# States
CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"

# Module-level flag — table creation runs only once
_cb_initialized = False


def _init_cb_table() -> None:
    """Creates the circuit_breaker table if it doesn't exist. Runs once per process."""
    global _cb_initialized
    if _cb_initialized:
        return

    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS circuit_breaker (
                name TEXT PRIMARY KEY,
                state TEXT NOT NULL DEFAULT 'closed',
                failure_count INTEGER NOT NULL DEFAULT 0,
                last_failure TEXT,
                opened_at TEXT
            )
        """)
        conn.commit()
        _cb_initialized = True
    finally:
        conn.close()


def _get_cb_connection() -> sqlite3.Connection:
    """Returns a SQLite connection with the circuit_breaker table ready."""
    _init_cb_table()
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn


class CircuitBreaker:
    """
    Per-competitor circuit breaker with SQLite-backed persistence.
    State survives process restarts, is safe for concurrent access,
    and won't corrupt on unexpected shutdown.
    """

    def _get_entry(self, name: str) -> dict:
        """Gets circuit breaker entry for a competitor. Creates default if missing."""
        conn = _get_cb_connection()
        try:
            row = conn.execute(
                "SELECT state, failure_count, last_failure, opened_at FROM circuit_breaker WHERE name = ?",
                (name,)
            ).fetchone()

            if row:
                return {
                    "state": row["state"],
                    "failure_count": row["failure_count"],
                    "last_failure": row["last_failure"],
                    "opened_at": row["opened_at"],
                }

            # Insert default entry
            conn.execute(
                "INSERT INTO circuit_breaker (name, state, failure_count) VALUES (?, ?, ?)",
                (name, CLOSED, 0)
            )
            conn.commit()
            return {
                "state": CLOSED,
                "failure_count": 0,
                "last_failure": None,
                "opened_at": None,
            }
        finally:
            conn.close()

    def _save_entry(self, name: str, entry: dict) -> None:
        """Persists a circuit breaker entry to SQLite."""
        conn = _get_cb_connection()
        try:
            conn.execute("""
                INSERT INTO circuit_breaker (name, state, failure_count, last_failure, opened_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    state = excluded.state,
                    failure_count = excluded.failure_count,
                    last_failure = excluded.last_failure,
                    opened_at = excluded.opened_at
            """, (name, entry["state"], entry["failure_count"], entry["last_failure"], entry["opened_at"]))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to save circuit breaker state for {name}: {e}")
        finally:
            conn.close()

    def can_execute(self, name: str) -> bool:
        """
        Checks if a request to this competitor should be allowed.

        Returns True if circuit is CLOSED or HALF_OPEN (allow one test).
        Returns False if circuit is OPEN (block until timeout).
        """
        entry = self._get_entry(name)
        state = entry["state"]

        if state == CLOSED:
            return True

        if state == OPEN:
            # Check if timeout has passed → transition to HALF_OPEN
            opened_at = entry.get("opened_at")
            if opened_at:
                opened_time = datetime.fromisoformat(opened_at)
                timeout = timedelta(hours=settings.CIRCUIT_BREAKER_TIMEOUT_HOURS)
                if datetime.now() - opened_time > timeout:
                    entry["state"] = HALF_OPEN
                    self._save_entry(name, entry)
                    logger.info(f"Circuit breaker HALF_OPEN for {name} — allowing test request")
                    return True
            return False

        if state == HALF_OPEN:
            return True  # Allow one test request

        return True  # Default: allow

    def record_success(self, name: str) -> None:
        """Records a successful request. Resets circuit to CLOSED."""
        entry = self._get_entry(name)
        was_open = entry["state"] != CLOSED

        entry["state"] = CLOSED
        entry["failure_count"] = 0
        entry["last_failure"] = None
        entry["opened_at"] = None
        self._save_entry(name, entry)

        if was_open:
            logger.info(f"Circuit breaker CLOSED for {name} — competitor is back online")

    def record_failure(self, name: str) -> None:
        """
        Records a failed request. Opens circuit after threshold failures.
        """
        entry = self._get_entry(name)
        entry["failure_count"] = entry.get("failure_count", 0) + 1
        entry["last_failure"] = datetime.now().isoformat()

        if entry["failure_count"] >= settings.CIRCUIT_BREAKER_THRESHOLD:
            entry["state"] = OPEN
            entry["opened_at"] = datetime.now().isoformat()
            logger.warning(
                f"Circuit breaker OPEN for {name} — "
                f"{entry['failure_count']} consecutive failures"
            )
        elif entry["state"] == HALF_OPEN:
            # Test request failed → back to OPEN
            entry["state"] = OPEN
            entry["opened_at"] = datetime.now().isoformat()
            logger.warning(f"Circuit breaker re-OPENED for {name} — test request failed")

        self._save_entry(name, entry)

    def get_status(self) -> dict:
        """Returns status of all circuit breakers. Used by dashboard."""
        conn = _get_cb_connection()
        try:
            rows = conn.execute("SELECT name, state FROM circuit_breaker").fetchall()
            return {row["name"]: row["state"] for row in rows}
        finally:
            conn.close()

    def reset(self, name: str) -> None:
        """Manually resets a circuit breaker to CLOSED."""
        conn = _get_cb_connection()
        try:
            conn.execute("DELETE FROM circuit_breaker WHERE name = ?", (name,))
            conn.commit()
            logger.info(f"Circuit breaker manually reset for {name}")
        finally:
            conn.close()
