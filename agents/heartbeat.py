"""
Self-Monitoring / Heartbeat Module.

Problem: If the agent crashes or the server restarts, the daily scan
simply doesn't happen and no one is notified.

Solution: A heartbeat mechanism that:
1. Records a timestamp after every successful scan
2. Runs a secondary scheduled check that verifies the scan happened
3. Sends an alert to Slack if the daily scan didn't complete by the expected time

Architecture:
    - The heartbeat file (logs/heartbeat.json) stores the last successful run timestamp
    - A separate scheduled job checks this file at a configured offset after the expected run time
    - If the scan didn't run, an alert is sent to Slack

Usage:
    - record_heartbeat() — called at the end of a successful agent run
    - check_heartbeat() — called by the scheduler at (RUN_HOUR + HEARTBEAT_OFFSET)
"""

import json
import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

HEARTBEAT_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
HEARTBEAT_FILE = os.path.join(HEARTBEAT_DIR, "heartbeat.json")

# How many hours after the expected run time to check
# If the scan was supposed to run at 08:00, check at 09:00
HEARTBEAT_CHECK_OFFSET_HOURS = 1

# Maximum age (in hours) of a heartbeat before it's considered stale
MAX_HEARTBEAT_AGE_HOURS = 25  # slightly over 24h to account for timing variance


def record_heartbeat(client_name: str = "default") -> None:
    """
    Records a successful scan completion timestamp.
    Called at the end of each successful pipeline run.

    Args:
        client_name: Which client's pipeline just completed.
    """
    try:
        os.makedirs(HEARTBEAT_DIR, exist_ok=True)

        # Load existing heartbeat data
        data = _load_heartbeat_data()

        # Update the timestamp for this client
        data[client_name] = {
            "last_success": datetime.now().isoformat(),
            "status": "healthy",
        }

        with open(HEARTBEAT_FILE, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Heartbeat recorded for client: {client_name}")

    except Exception as e:
        logger.error(f"Failed to record heartbeat: {e}")


def check_heartbeat() -> list[dict]:
    """
    Checks if all clients had a successful scan within the expected timeframe.
    Returns a list of alerts for clients that are unhealthy.

    Each alert dict contains:
        - client_name: Name of the affected client
        - message: Human-readable alert message
        - last_success: ISO timestamp of the last successful run (or None)
        - hours_since: Hours since the last successful run
    """
    alerts = []

    try:
        data = _load_heartbeat_data()

        if not data:
            alerts.append({
                "client_name": "system",
                "message": "No heartbeat data found — agent may have never run successfully",
                "last_success": None,
                "hours_since": None,
            })
            return alerts

        now = datetime.now()

        for client_name, info in data.items():
            last_success_str = info.get("last_success")
            if not last_success_str:
                alerts.append({
                    "client_name": client_name,
                    "message": f"Client '{client_name}' has no recorded successful run",
                    "last_success": None,
                    "hours_since": None,
                })
                continue

            last_success = datetime.fromisoformat(last_success_str)
            hours_since = (now - last_success).total_seconds() / 3600

            if hours_since > MAX_HEARTBEAT_AGE_HOURS:
                alerts.append({
                    "client_name": client_name,
                    "message": (
                        f"Client '{client_name}' hasn't run successfully in "
                        f"{hours_since:.1f} hours (last: {last_success_str})"
                    ),
                    "last_success": last_success_str,
                    "hours_since": round(hours_since, 1),
                })

        if not alerts:
            logger.info("Heartbeat check passed — all clients are healthy")

    except Exception as e:
        logger.error(f"Heartbeat check failed: {e}")
        alerts.append({
            "client_name": "system",
            "message": f"Heartbeat check error: {e}",
            "last_success": None,
            "hours_since": None,
        })

    return alerts


def get_health_status() -> dict:
    """
    Returns the current health status of all clients.
    Useful for dashboards and monitoring endpoints.

    Returns:
        Dict mapping client_name → {last_success, status, hours_since}
    """
    data = _load_heartbeat_data()
    now = datetime.now()
    status = {}

    for client_name, info in data.items():
        last_success_str = info.get("last_success")
        if last_success_str:
            last_success = datetime.fromisoformat(last_success_str)
            hours_since = (now - last_success).total_seconds() / 3600
            is_healthy = hours_since <= MAX_HEARTBEAT_AGE_HOURS
        else:
            hours_since = None
            is_healthy = False

        status[client_name] = {
            "last_success": last_success_str,
            "status": "healthy" if is_healthy else "unhealthy",
            "hours_since": round(hours_since, 1) if hours_since else None,
        }

    return status


def _load_heartbeat_data() -> dict:
    """Loads heartbeat data from the JSON file, or returns empty dict."""
    if not os.path.exists(HEARTBEAT_FILE):
        return {}
    try:
        with open(HEARTBEAT_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception):
        return {}
