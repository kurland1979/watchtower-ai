"""
Structured JSON Logging.

In production, structured logs are essential for:
1. Log aggregation (ELK, Datadog, CloudWatch) — JSON is parseable
2. Filtering by fields (client_name, competitor, level)
3. Alerting on specific patterns
4. Correlation across distributed services

This replaces the default text-based logging with JSON format
when ENVIRONMENT=production is set.
"""

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.

    Output example:
    {"timestamp":"2024-01-15T08:00:01Z","level":"INFO","logger":"agents.watchtower_agent",
     "message":"Pipeline completed","client":"TestClient"}
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include extra fields if present (e.g., client_name, competitor)
        if hasattr(record, "client_name"):
            log_entry["client"] = record.client_name
        if hasattr(record, "competitor"):
            log_entry["competitor"] = record.competitor

        # Include exception info if present
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(log_entry, ensure_ascii=False)


def setup_json_logging(level: int = logging.INFO) -> None:
    """
    Configures the root logger to use JSON formatting.
    Call this once at application startup (in main.py) when running in production.

    Usage:
        if os.getenv("ENVIRONMENT") == "production":
            setup_json_logging()
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicate logs
    root_logger.handlers.clear()

    # JSON to stdout (container-friendly — Docker/K8s collect stdout)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)
