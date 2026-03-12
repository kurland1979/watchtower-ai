"""
Dashboard REST API — Production-Hardened.

Endpoints:
    GET  /api/health      — Liveness probe (no auth required)
    GET  /api/competitors — List all tracked competitors (auth required)
    GET  /api/scans/<name> — Scan history for a competitor (auth required)
    GET  /api/trends      — Trend analysis for all competitors (auth required)
    GET  /api/trends/<name> — Trend analysis for a single competitor (auth required)

Admin Endpoints (Client Management):
    GET    /api/admin/clients              — List all clients
    GET    /api/admin/clients/<name>       — Get a specific client
    POST   /api/admin/clients              — Create a new client
    PUT    /api/admin/clients/<name>       — Update an existing client
    DELETE /api/admin/clients/<name>       — Delete a client
    POST   /api/admin/clients/<name>/competitors — Add a competitor to a client
    DELETE /api/admin/clients/<name>/competitors/<comp> — Remove a competitor

Security:
    - API key authentication via Authorization: Bearer <key> header
    - CORS restricted to configured origins
    - Input validation on all parameters
    - No debug mode in production
"""

import os
import sys
import json
import logging
from functools import wraps
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.storage import _get_connection
from agents.heartbeat import get_health_status
from agents.trend_analyzer import (
    analyze_competitor_trends,
    get_all_competitor_names,
    generate_trend_report,
    get_scans_for_period,
    calculate_changes,
)
from utils.validation import validate_competitor_name, validate_url
from config.client_loader import load_all_clients, load_single_client, CLIENTS_DIR
from config.settings import settings

logger = logging.getLogger(__name__)

DASHBOARD_DIR = os.path.dirname(__file__)

app = Flask(__name__, static_folder=DASHBOARD_DIR)

# CORS — restricted to configured origins
# Includes "null" for local file:// access and localhost:5000 for same-origin fallback
allowed_origins = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5000,null"
).split(",")
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


# --- Dashboard Serving ---
# Serves index.html on the same origin as the API.
# This eliminates CORS issues entirely — browser sees one origin for everything.

@app.route("/")
def serve_dashboard():
    """Serves the dashboard UI from the same Flask server."""
    return send_from_directory(DASHBOARD_DIR, "index.html")


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


# ============================================================
# Report API — Daily / Weekly / Monthly Comparisons
# ============================================================
#
# These endpoints power the dashboard's comparison tabs.
# Each returns structured data with scan-by-scan diffs so the
# frontend can render tables and charts.
# ============================================================


def _build_comparison_data(competitor_name: str, days: int) -> dict:
    """
    Builds comparison data for a competitor over a given period.
    Returns scan pairs with similarity ratios and change detection.
    """
    scans = get_scans_for_period(competitor_name, days)
    changes = calculate_changes(scans)

    entries = []
    for i, change in enumerate(changes):
        prev_scan = scans[i]
        curr_scan = scans[i + 1]

        # Extract a brief diff summary (first 200 chars that differ)
        prev_text = prev_scan["text"]
        curr_text = curr_scan["text"]

        entries.append({
            "date": change["date"],
            "prev_date": prev_scan["timestamp"],
            "similarity": change["similarity_ratio"],
            "is_significant": change["is_significant"],
            "change_percent": round((1 - change["similarity_ratio"]) * 100, 1),
            "prev_length": len(prev_text),
            "curr_length": len(curr_text),
            "length_diff": len(curr_text) - len(prev_text),
        })

    sig_count = sum(1 for e in entries if e["is_significant"])

    return {
        "competitor": competitor_name,
        "period_days": days,
        "total_scans": len(scans),
        "total_comparisons": len(entries),
        "significant_changes": sig_count,
        "entries": entries,
    }


@app.route("/api/reports/daily", methods=["GET"])
@require_api_key
def report_daily():
    """
    Daily comparison: today vs yesterday for all competitors.
    Returns the latest scan pair for each competitor.
    """
    names = get_all_competitor_names()
    results = []

    for name in names:
        scans = get_scans_for_period(name, days=2)
        if len(scans) < 2:
            results.append({
                "competitor": name,
                "status": "no_comparison",
                "message": "Not enough scans yet (need at least 2)",
                "latest_scan": scans[-1]["timestamp"] if scans else None,
            })
            continue

        # Compare the two most recent scans
        prev_scan = scans[-2]
        curr_scan = scans[-1]
        changes = calculate_changes([prev_scan, curr_scan])

        if changes:
            change = changes[0]
            results.append({
                "competitor": name,
                "status": "compared",
                "scan_date": curr_scan["timestamp"],
                "prev_date": prev_scan["timestamp"],
                "similarity": change["similarity_ratio"],
                "change_percent": round((1 - change["similarity_ratio"]) * 100, 1),
                "is_significant": change["is_significant"],
                "curr_length": len(curr_scan["text"]),
                "prev_length": len(prev_scan["text"]),
                "length_diff": len(curr_scan["text"]) - len(prev_scan["text"]),
            })

    return jsonify({"report": "daily", "competitors": results, "total": len(results)})


@app.route("/api/reports/weekly", methods=["GET"])
@require_api_key
def report_weekly():
    """
    Weekly report: 7-day comparison data for all competitors.
    Returns day-by-day changes with similarity ratios for charting.
    """
    names = get_all_competitor_names()
    results = []

    for name in names:
        data = _build_comparison_data(name, days=7)
        results.append(data)

    return jsonify({"report": "weekly", "period_days": 7, "competitors": results})


@app.route("/api/reports/weekly/<competitor_name>", methods=["GET"])
@require_api_key
def report_weekly_single(competitor_name: str):
    """Weekly report for a single competitor."""
    is_valid, error = validate_competitor_name(competitor_name)
    if not is_valid:
        return jsonify({"error": f"Invalid competitor name: {error}"}), 400

    data = _build_comparison_data(competitor_name, days=7)
    return jsonify(data)


@app.route("/api/reports/monthly", methods=["GET"])
@require_api_key
def report_monthly():
    """
    Monthly report: 30-day comparison data for all competitors.
    Returns day-by-day changes with similarity ratios for charting.
    """
    names = get_all_competitor_names()
    results = []

    for name in names:
        data = _build_comparison_data(name, days=30)
        results.append(data)

    return jsonify({"report": "monthly", "period_days": 30, "competitors": results})


@app.route("/api/reports/monthly/<competitor_name>", methods=["GET"])
@require_api_key
def report_monthly_single(competitor_name: str):
    """Monthly report for a single competitor."""
    is_valid, error = validate_competitor_name(competitor_name)
    if not is_valid:
        return jsonify({"error": f"Invalid competitor name: {error}"}), 400

    data = _build_comparison_data(competitor_name, days=30)
    return jsonify(data)


# ============================================================
# Admin API — Client Management (CRUD)
# ============================================================
#
# These endpoints let the admin (you) manage clients through the API
# instead of manually editing JSON files on the server.
#
# Pattern: All admin endpoints require the same API key as the
# dashboard endpoints. The only person calling these is you.
# ============================================================


def _get_client_file_path(client_name: str) -> str:
    """Converts a client name to its JSON file path."""
    safe_name = client_name.lower().replace(" ", "_")
    return os.path.join(CLIENTS_DIR, f"{safe_name}.json")


def _validate_client_data(data: dict) -> tuple[bool, str]:
    """
    Validates incoming client data for creation or update.
    Returns (is_valid, error_message).
    """
    if not data:
        return False, "Request body is empty"

    # Required fields for new client
    if "client_name" not in data:
        return False, "Missing required field: client_name"
    if "industry" not in data:
        return False, "Missing required field: industry"
    if "competitors" not in data:
        return False, "Missing required field: competitors"

    # Validate client_name
    name = data["client_name"]
    if not name or not name.strip():
        return False, "client_name cannot be empty"
    if len(name) > 100:
        return False, "client_name too long (max 100 characters)"

    # Validate industry
    industry = data["industry"]
    if not industry or not industry.strip():
        return False, "industry cannot be empty"

    # Validate competitors list
    competitors = data["competitors"]
    if not isinstance(competitors, list):
        return False, "competitors must be a list"

    for i, comp in enumerate(competitors):
        if "name" not in comp:
            return False, f"Competitor #{i+1} missing 'name'"
        if "url" not in comp:
            return False, f"Competitor #{i+1} missing 'url'"

        # Validate competitor name
        is_valid, error = validate_competitor_name(comp["name"])
        if not is_valid:
            return False, f"Competitor #{i+1}: {error}"

        # Validate URL
        is_valid, error = validate_url(comp["url"])
        if not is_valid:
            return False, f"Competitor #{i+1} URL: {error}"

        # Validate pages if provided
        for j, page in enumerate(comp.get("pages", [])):
            is_valid, error = validate_url(page)
            if not is_valid:
                return False, f"Competitor #{i+1} page #{j+1}: {error}"

    return True, ""


def _save_client_file(client_data: dict) -> bool:
    """Saves a client config to its JSON file. Returns True on success."""
    try:
        os.makedirs(CLIENTS_DIR, exist_ok=True)
        file_path = _get_client_file_path(client_data["client_name"])
        with open(file_path, "w") as f:
            json.dump(client_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved client config: {client_data['client_name']}")
        return True
    except Exception as e:
        logger.error(f"Failed to save client config: {e}")
        return False


@app.route("/api/admin/clients", methods=["GET"])
@require_api_key
def admin_list_clients():
    """Returns a list of all configured clients with their competitors."""
    clients = load_all_clients()
    result = []
    for client in clients:
        result.append({
            "client_name": client["client_name"],
            "industry": client["industry"],
            "competitor_count": len(client.get("competitors", [])),
            "competitors": [c["name"] for c in client.get("competitors", [])],
            "slack_channel_id": client.get("slack_channel_id", ""),
        })
    return jsonify({"clients": result, "total": len(result)})


@app.route("/api/admin/clients/<client_name>", methods=["GET"])
@require_api_key
def admin_get_client(client_name: str):
    """Returns full details of a specific client."""
    clients = load_all_clients()
    for client in clients:
        if client["client_name"] == client_name:
            return jsonify(client)
    return jsonify({"error": f"Client '{client_name}' not found"}), 404


@app.route("/api/admin/clients", methods=["POST"])
@require_api_key
def admin_create_client():
    """
    Creates a new client configuration.

    Expected JSON body:
    {
        "client_name": "acme_cybersecurity",
        "industry": "cybersecurity",
        "slack_channel_id": "C123456",
        "slack_bot_token": "",
        "competitors": [
            {
                "name": "CrowdStrike",
                "url": "https://www.crowdstrike.com",
                "pages": ["https://www.crowdstrike.com/en-us/"],
                "active": true,
                "js_render": false
            }
        ]
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    # Validate
    is_valid, error = _validate_client_data(data)
    if not is_valid:
        return jsonify({"error": error}), 400

    # Check if client already exists
    file_path = _get_client_file_path(data["client_name"])
    if os.path.exists(file_path):
        return jsonify({"error": f"Client '{data['client_name']}' already exists"}), 409

    # Ensure defaults
    client_data = {
        "client_name": data["client_name"],
        "industry": data["industry"],
        "slack_channel_id": data.get("slack_channel_id", ""),
        "slack_bot_token": data.get("slack_bot_token", ""),
        "competitors": data["competitors"],
    }

    # Set defaults for each competitor
    for comp in client_data["competitors"]:
        comp.setdefault("active", True)
        comp.setdefault("js_render", False)
        comp.setdefault("pages", [comp["url"]])

    if _save_client_file(client_data):
        return jsonify({
            "message": f"Client '{data['client_name']}' created successfully",
            "client": client_data,
        }), 201
    else:
        return jsonify({"error": "Failed to save client configuration"}), 500


@app.route("/api/admin/clients/<client_name>", methods=["PUT"])
@require_api_key
def admin_update_client(client_name: str):
    """
    Updates an existing client configuration.
    Only provided fields are updated — others remain unchanged.
    """
    # Find existing client
    file_path = _get_client_file_path(client_name)
    if not os.path.exists(file_path):
        return jsonify({"error": f"Client '{client_name}' not found"}), 404

    existing = load_single_client(file_path)
    if existing is None:
        return jsonify({"error": "Failed to load existing client config"}), 500

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    # Merge updates into existing config
    if "industry" in data:
        existing["industry"] = data["industry"]
    if "slack_channel_id" in data:
        existing["slack_channel_id"] = data["slack_channel_id"]
    if "slack_bot_token" in data:
        existing["slack_bot_token"] = data["slack_bot_token"]
    if "competitors" in data:
        # Full replacement of competitors list
        existing["competitors"] = data["competitors"]

        # Validate the new competitors
        is_valid, error = _validate_client_data(existing)
        if not is_valid:
            return jsonify({"error": error}), 400

        # Set defaults for each competitor
        for comp in existing["competitors"]:
            comp.setdefault("active", True)
            comp.setdefault("js_render", False)
            comp.setdefault("pages", [comp["url"]])

    if _save_client_file(existing):
        return jsonify({
            "message": f"Client '{client_name}' updated successfully",
            "client": existing,
        })
    else:
        return jsonify({"error": "Failed to save client configuration"}), 500


@app.route("/api/admin/clients/<client_name>", methods=["DELETE"])
@require_api_key
def admin_delete_client(client_name: str):
    """Deletes a client configuration file."""
    file_path = _get_client_file_path(client_name)
    if not os.path.exists(file_path):
        return jsonify({"error": f"Client '{client_name}' not found"}), 404

    try:
        os.remove(file_path)
        logger.info(f"Deleted client config: {client_name}")
        return jsonify({"message": f"Client '{client_name}' deleted successfully"})
    except Exception as e:
        logger.error(f"Failed to delete client config: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/clients/<client_name>/competitors", methods=["POST"])
@require_api_key
def admin_add_competitor(client_name: str):
    """
    Adds a single competitor to an existing client.

    Expected JSON body:
    {
        "name": "Fortinet",
        "url": "https://www.fortinet.com",
        "pages": ["https://www.fortinet.com/", "https://www.fortinet.com/products"],
        "active": true,
        "js_render": false
    }
    """
    file_path = _get_client_file_path(client_name)
    if not os.path.exists(file_path):
        return jsonify({"error": f"Client '{client_name}' not found"}), 404

    existing = load_single_client(file_path)
    if existing is None:
        return jsonify({"error": "Failed to load existing client config"}), 500

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    # Validate competitor fields
    if "name" not in data:
        return jsonify({"error": "Missing required field: name"}), 400
    if "url" not in data:
        return jsonify({"error": "Missing required field: url"}), 400

    is_valid, error = validate_competitor_name(data["name"])
    if not is_valid:
        return jsonify({"error": error}), 400

    is_valid, error = validate_url(data["url"])
    if not is_valid:
        return jsonify({"error": error}), 400

    # Check for duplicate
    existing_names = [c["name"].lower() for c in existing.get("competitors", [])]
    if data["name"].lower() in existing_names:
        return jsonify({"error": f"Competitor '{data['name']}' already exists in this client"}), 409

    # Build competitor entry with defaults
    new_competitor = {
        "name": data["name"],
        "url": data["url"],
        "pages": data.get("pages", [data["url"]]),
        "active": data.get("active", True),
        "js_render": data.get("js_render", False),
    }

    # Validate pages
    for i, page in enumerate(new_competitor["pages"]):
        is_valid, error = validate_url(page)
        if not is_valid:
            return jsonify({"error": f"Page #{i+1}: {error}"}), 400

    existing["competitors"].append(new_competitor)

    if _save_client_file(existing):
        return jsonify({
            "message": f"Competitor '{data['name']}' added to '{client_name}'",
            "competitor": new_competitor,
            "total_competitors": len(existing["competitors"]),
        }), 201
    else:
        return jsonify({"error": "Failed to save client configuration"}), 500


@app.route("/api/admin/clients/<client_name>/competitors/<competitor_name>", methods=["DELETE"])
@require_api_key
def admin_remove_competitor(client_name: str, competitor_name: str):
    """Removes a specific competitor from a client."""
    file_path = _get_client_file_path(client_name)
    if not os.path.exists(file_path):
        return jsonify({"error": f"Client '{client_name}' not found"}), 404

    existing = load_single_client(file_path)
    if existing is None:
        return jsonify({"error": "Failed to load existing client config"}), 500

    # Find and remove the competitor
    original_count = len(existing["competitors"])
    existing["competitors"] = [
        c for c in existing["competitors"]
        if c["name"].lower() != competitor_name.lower()
    ]

    if len(existing["competitors"]) == original_count:
        return jsonify({"error": f"Competitor '{competitor_name}' not found in '{client_name}'"}), 404

    if _save_client_file(existing):
        return jsonify({
            "message": f"Competitor '{competitor_name}' removed from '{client_name}'",
            "remaining_competitors": len(existing["competitors"]),
        })
    else:
        return jsonify({"error": "Failed to save client configuration"}), 500


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    app.run(debug=debug, host="127.0.0.1", port=5000)
