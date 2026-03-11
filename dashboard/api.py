"""
Dashboard REST API — Production-Hardened.

Endpoints:
    GET /api/health      — Liveness probe (no auth required)
    GET /api/competitors — List all tracked competitors (auth required)
    GET /api/scans/<name> — Scan history for a competitor (auth required)
    GET /api/trends      — Trend analysis for all competitors (auth required)
    GET /api/trends/<name> — Trend analysis for a single competitor (auth required)

Security:
    - API key authentication via Authorization: Bearer <key> header
    - CORS restricted to configured origins
    - Input validation on all parameters
    - No debug mode in production
"""

import os
import sys
from functools import wraps
from flask import Flask, jsonify, request
from flask_cors import CORS

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.storage import _get_connection
from agents.heartbeat import get_health_status
from agents.trend_analyzer import (
    analyze_competitor_trends,
    get_all_competitor_names,
    generate_trend_report,
)
from utils.validation import validate_competitor_name
from config.settings import settings

app = Flask(__name__)

# CORS — restricted to configured origins (not wide open)
allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
CORS(app, origins=[o.strip() for o in allowed_origins])


# --- Authentication Middleware ---

def require_api_key(f):
    """
    Decorator that validates the API key from the Authorization header.
    Pattern: Authorization: Bearer <api_key>

    This is the simplest production-grade auth — every request must include
    a valid API key. For more complex scenarios, use JWT tokens.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        expected_key = os.getenv("WATCHTOWER_API_KEY")

        # If no API key is configured, allow access (dev mode)
        if not expected_key:
            return f(*args, **kwargs)

        auth_header = request.headers.get("Authorization", "")
        provided_key = auth_header.replace("Bearer ", "").strip()

        if not provided_key or provided_key != expected_key:
            return jsonify({"error": "Unauthorized — provide valid API key"}), 401

        return f(*args, **kwargs)
    return decorated


# --- Health Endpoint (no auth — used by Docker/K8s liveness probes) ---

@app.route("/api/health", methods=["GET"])
def health():
    """
    Returns system health status. No authentication required.
    Used as a liveness probe by Docker, Kubernetes, and monitoring tools.
    """
    try:
        status = get_health_status()
        return jsonify({"status": "ok", "clients": status})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 503


# --- Protected Endpoints ---

@app.route("/api/competitors", methods=["GET"])
@require_api_key
def competitors():
    """Returns a list of all tracked competitor names."""
    names = get_all_competitor_names()
    return jsonify({"competitors": names})


@app.route("/api/scans/<competitor_name>", methods=["GET"])
@require_api_key
def scans(competitor_name: str):
    """
    Returns scan history for a specific competitor.
    Query params:
        - limit: Max number of scans to return (default: 30, max: 100)
    """
    # Input validation
    is_valid, error = validate_competitor_name(competitor_name)
    if not is_valid:
        return jsonify({"error": f"Invalid competitor name: {error}"}), 400

    limit = request.args.get("limit", settings.MAX_SCANS_RETURNED, type=int)
    limit = min(limit, 100)  # Cap at 100 to prevent abuse

    try:
        conn = _get_connection()
        cursor = conn.execute(
            """SELECT id, competitor_name, text, timestamp
               FROM scans
               WHERE competitor_name = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (competitor_name, limit)
        )
        rows = cursor.fetchall()
        conn.close()

        scans_list = [
            {
                "id": row[0],
                "competitor": row[1],
                "text_preview": row[2][:200] + "..." if len(row[2]) > 200 else row[2],
                "text_length": len(row[2]),
                "timestamp": row[3],
            }
            for row in rows
        ]

        return jsonify({"competitor": competitor_name, "scans": scans_list})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/trends", methods=["GET"])
@require_api_key
def trends():
    """
    Returns trend analysis for all competitors.
    Query params:
        - days: Look-back period in days (default: 30, max: 365)
    """
    days = request.args.get("days", settings.MAX_TREND_DAYS, type=int)
    days = min(days, 365)  # Cap at 1 year

    names = get_all_competitor_names()
    results = generate_trend_report(names, days)
    return jsonify({"period_days": days, "trends": results})


@app.route("/api/trends/<competitor_name>", methods=["GET"])
@require_api_key
def trend_single(competitor_name: str):
    """
    Returns trend analysis for a single competitor.
    Query params:
        - days: Look-back period in days (default: 30, max: 365)
    """
    is_valid, error = validate_competitor_name(competitor_name)
    if not is_valid:
        return jsonify({"error": f"Invalid competitor name: {error}"}), 400

    days = request.args.get("days", settings.MAX_TREND_DAYS, type=int)
    days = min(days, 365)

    result = analyze_competitor_trends(competitor_name, days)
    return jsonify(result)


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    app.run(debug=debug, host="127.0.0.1", port=5000)
