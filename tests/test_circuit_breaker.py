"""
Tests for utils/circuit_breaker.py

Covers: state transitions (CLOSED → OPEN → HALF_OPEN → CLOSED),
threshold behavior, timeout recovery, persistence, manual reset.
"""

import pytest
import os
import json
from unittest.mock import patch
from datetime import datetime, timedelta

from utils.circuit_breaker import CircuitBreaker, CLOSED, OPEN, HALF_OPEN


@pytest.fixture
def cb(tmp_path):
    """Create a CircuitBreaker with a temporary state file."""
    state_file = str(tmp_path / "cb_state.json")
    with patch("utils.circuit_breaker.STATE_FILE", state_file):
        yield CircuitBreaker()


class TestCircuitBreakerStates:
    """Tests for circuit breaker state transitions."""

    def test_initial_state_closed(self, cb):
        """New competitors should start in CLOSED state."""
        assert cb.can_execute("NewCorp") is True

    def test_stays_closed_below_threshold(self, cb):
        """Should stay CLOSED when failures are below threshold."""
        for _ in range(3):
            cb.record_failure("CorpA")
        assert cb.can_execute("CorpA") is True

    def test_opens_at_threshold(self, cb):
        """Should transition to OPEN after threshold failures."""
        from config.settings import settings
        for _ in range(settings.CIRCUIT_BREAKER_THRESHOLD):
            cb.record_failure("CorpB")
        assert cb.can_execute("CorpB") is False

    def test_success_resets_to_closed(self, cb):
        """Recording success should reset circuit to CLOSED."""
        for _ in range(3):
            cb.record_failure("CorpC")
        cb.record_success("CorpC")
        assert cb.can_execute("CorpC") is True

    def test_half_open_success_closes(self, cb):
        """Success in HALF_OPEN should transition to CLOSED."""
        from config.settings import settings
        # Open the circuit
        for _ in range(settings.CIRCUIT_BREAKER_THRESHOLD):
            cb.record_failure("CorpD")

        # Force HALF_OPEN by backdating opened_at
        entry = cb._get_entry("CorpD")
        entry["opened_at"] = (
            datetime.now() - timedelta(hours=settings.CIRCUIT_BREAKER_TIMEOUT_HOURS + 1)
        ).isoformat()
        cb._save_state()

        # Should be HALF_OPEN now
        assert cb.can_execute("CorpD") is True

        # Success → CLOSED
        cb.record_success("CorpD")
        assert cb.can_execute("CorpD") is True

    def test_half_open_failure_reopens(self, cb):
        """Failure in HALF_OPEN should transition back to OPEN."""
        from config.settings import settings
        for _ in range(settings.CIRCUIT_BREAKER_THRESHOLD):
            cb.record_failure("CorpE")

        # Force HALF_OPEN
        entry = cb._get_entry("CorpE")
        entry["state"] = HALF_OPEN
        cb._save_state()

        cb.record_failure("CorpE")
        assert cb.can_execute("CorpE") is False


class TestCircuitBreakerPersistence:
    """Tests for state persistence."""

    def test_state_survives_reload(self, tmp_path):
        """State should persist across CircuitBreaker instances."""
        state_file = str(tmp_path / "cb_persist.json")
        with patch("utils.circuit_breaker.STATE_FILE", state_file):
            cb1 = CircuitBreaker()
            from config.settings import settings
            for _ in range(settings.CIRCUIT_BREAKER_THRESHOLD):
                cb1.record_failure("PersistCorp")

            # New instance should load persisted state
            cb2 = CircuitBreaker()
            assert cb2.can_execute("PersistCorp") is False


class TestCircuitBreakerUtilities:
    """Tests for utility methods."""

    def test_get_status(self, cb):
        """Should return status dict for all tracked competitors."""
        cb.record_success("CorpA")
        status = cb.get_status()
        assert "CorpA" in status
        assert status["CorpA"] == CLOSED

    def test_manual_reset(self, cb):
        """Should allow manual reset of a circuit."""
        from config.settings import settings
        for _ in range(settings.CIRCUIT_BREAKER_THRESHOLD):
            cb.record_failure("ResetCorp")
        assert cb.can_execute("ResetCorp") is False

        cb.reset("ResetCorp")
        assert cb.can_execute("ResetCorp") is True

    def test_reset_unknown_competitor(self, cb):
        """Resetting unknown competitor should not crash."""
        cb.reset("UnknownCorp")  # Should not raise
