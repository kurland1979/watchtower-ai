"""
Circuit Breaker Pattern.

When a competitor's website is persistently down, retrying every day wastes
time and API resources. The circuit breaker stops retrying after N consecutive
failures and only tests again after a cooldown period.

States:
    CLOSED  — Normal operation. Requests pass through. Failures increment counter.
    OPEN    — Requests are blocked. After timeout, transitions to HALF_OPEN.
    HALF_OPEN — One test request is allowed. Success → CLOSED. Failure → OPEN.

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

import json
import os
import logging
from datetime import datetime, timedelta

from config.settings import settings

logger = logging.getLogger(__name__)

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "circuit_breaker.json")

# States
CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Per-competitor circuit breaker with persistent state.
    State survives across agent runs (stored in JSON file).
    """

    def __init__(self):
        self._states = self._load_state()

    def _load_state(self) -> dict:
        """Loads circuit breaker state from JSON file."""
        if not os.path.exists(STATE_FILE):
            return {}
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            return {}

    def _save_state(self) -> None:
        """Persists current state to JSON file."""
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with open(STATE_FILE, "w") as f:
                json.dump(self._states, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save circuit breaker state: {e}")

    def _get_entry(self, name: str) -> dict:
        """Gets or creates a circuit breaker entry for a competitor."""
        if name not in self._states:
            self._states[name] = {
                "state": CLOSED,
                "failure_count": 0,
                "last_failure": None,
                "opened_at": None,
            }
        return self._states[name]

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
                    self._save_state()
                    logger.info(f"Circuit breaker HALF_OPEN for {name} — allowing test request")
                    return True
            return False

        if state == HALF_OPEN:
            return True  # Allow one test request

        return True  # Default: allow

    def record_success(self, name: str) -> None:
        """Records a successful request. Resets circuit to CLOSED."""
        entry = self._get_entry(name)
        entry["state"] = CLOSED
        entry["failure_count"] = 0
        entry["last_failure"] = None
        entry["opened_at"] = None
        self._save_state()

        if entry.get("state") != CLOSED:
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

        self._save_state()

    def get_status(self) -> dict:
        """Returns status of all circuit breakers. Used by dashboard."""
        return {name: info["state"] for name, info in self._states.items()}

    def reset(self, name: str) -> None:
        """Manually resets a circuit breaker to CLOSED."""
        if name in self._states:
            del self._states[name]
            self._save_state()
            logger.info(f"Circuit breaker manually reset for {name}")
