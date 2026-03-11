"""
Centralized Configuration — Single Source of Truth.

All configurable values live here instead of being scattered as magic numbers
across the codebase. Values are loaded from environment variables with sensible
defaults, making the system configurable without code changes.

Usage:
    from config.settings import settings
    timeout = settings.SCRAPER_TIMEOUT
"""

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    """
    All configuration values for WatchTower AI.
    Loaded from environment variables with defaults.
    """

    # --- Scraper ---
    SCRAPER_TIMEOUT: int = 10                  # Seconds per HTTP request
    SCRAPER_MAX_RETRIES: int = 3               # Max retries per page
    RATE_LIMIT_DELAY_MIN: float = 1.0          # Min delay between requests (seconds)
    RATE_LIMIT_DELAY_MAX: float = 2.5          # Max delay between requests (seconds)

    # --- Backoff ---
    BACKOFF_BASE: float = 1.0                  # Base delay for exponential backoff
    BACKOFF_MULTIPLIER: float = 2.0            # Multiplier per attempt
    BACKOFF_MAX: float = 32.0                  # Max delay cap (seconds)
    BACKOFF_JITTER_MIN: float = 0.8            # Min jitter multiplier
    BACKOFF_JITTER_MAX: float = 1.2            # Max jitter multiplier

    # --- Circuit Breaker ---
    CIRCUIT_BREAKER_THRESHOLD: int = 5         # Failures before opening circuit
    CIRCUIT_BREAKER_TIMEOUT_HOURS: float = 6.0 # Hours to keep circuit open

    # --- LLM ---
    LLM_CHAR_BUDGET: int = 3000               # Char budget for comparison scans
    LLM_CHAR_BUDGET_FIRST_SCAN: int = 5000    # Char budget for first scan (no comparison)

    # --- Heartbeat ---
    MAX_HEARTBEAT_AGE_HOURS: int = 25          # Max hours before heartbeat is stale
    HEARTBEAT_CHECK_OFFSET_HOURS: int = 1      # Hours after scan to check heartbeat

    # --- Dashboard API ---
    MAX_SCANS_RETURNED: int = 30               # Default scan history limit
    MAX_TREND_DAYS: int = 30                   # Default trend analysis period

    # --- Job ---
    OVERALL_JOB_TIMEOUT: int = 3600            # Max seconds for entire pipeline

    # --- Slack ---
    SLACK_RETRY_MAX: int = 3                   # Max retries for Slack API calls

    # --- Trend Analysis ---
    SIGNIFICANT_CHANGE_THRESHOLD: float = 0.85 # Similarity below this = significant change

    @classmethod
    def from_env(cls) -> "Settings":
        """
        Creates a Settings instance from environment variables.
        Uses env var if set, otherwise falls back to dataclass defaults.
        """
        return cls(
            SCRAPER_TIMEOUT=int(os.getenv("SCRAPER_TIMEOUT", cls.SCRAPER_TIMEOUT)),
            SCRAPER_MAX_RETRIES=int(os.getenv("SCRAPER_MAX_RETRIES", cls.SCRAPER_MAX_RETRIES)),
            LLM_CHAR_BUDGET=int(os.getenv("LLM_CHAR_BUDGET", cls.LLM_CHAR_BUDGET)),
            LLM_CHAR_BUDGET_FIRST_SCAN=int(os.getenv("LLM_CHAR_BUDGET_FIRST_SCAN", cls.LLM_CHAR_BUDGET_FIRST_SCAN)),
            OVERALL_JOB_TIMEOUT=int(os.getenv("OVERALL_JOB_TIMEOUT", cls.OVERALL_JOB_TIMEOUT)),
        )


def validate_required_env_vars() -> list[str]:
    """
    Validates that all critical environment variables are set.
    Returns a list of missing variable names (empty = all good).

    Called at startup — if any are missing, the system should fail fast
    rather than crashing mid-pipeline with a cryptic error.
    """
    required = [
        "ANTHROPIC_API_KEY",
        "SLACK_BOT_TOKEN",
        "SLACK_CHANNEL_ID",
    ]
    missing = [var for var in required if not os.getenv(var)]
    return missing


# Singleton instance — import this everywhere
settings = Settings.from_env()
