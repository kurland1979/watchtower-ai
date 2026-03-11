"""
Trend Analysis Module.

Leverages the SQLite scan history to detect patterns across multiple days.
While the main agent only compares today vs. yesterday, this module provides
weekly and monthly summaries with pattern detection:

- "CrowdStrike changed their pricing page 3 times in 30 days"
- "SentinelOne has been adding new features consistently every week"
- "Palo Alto Networks has had no significant changes in 3 weeks"

Architecture:
    - Queries historical scans from the SQLite database
    - Uses difflib to calculate content similarity between consecutive scans
    - Detects change frequency, velocity trends, and stability periods
    - Generates structured summary reports for Slack
"""

import sqlite3
import os
import logging
from datetime import datetime, timedelta
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

STORAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
DB_FILE = os.path.join(STORAGE_DIR, "watchtower.db")

# A change below this similarity ratio is considered "significant"
SIGNIFICANT_CHANGE_THRESHOLD = 0.85


def _get_connection() -> sqlite3.Connection:
    """Creates a connection to the SQLite database."""
    return sqlite3.connect(DB_FILE)


def get_scans_for_period(
    competitor_name: str,
    days: int = 30,
) -> list[dict]:
    """
    Retrieves all scans for a competitor within the specified period.

    Args:
        competitor_name: Name of the competitor.
        days: Number of days to look back (default: 30).

    Returns:
        List of dicts with 'text' and 'timestamp' keys, ordered by time ASC.
    """
    try:
        conn = _get_connection()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        cursor = conn.execute(
            """SELECT text, timestamp FROM scans
               WHERE competitor_name = ? AND timestamp >= ?
               ORDER BY timestamp ASC""",
            (competitor_name, cutoff)
        )

        rows = cursor.fetchall()
        conn.close()

        return [{"text": row[0], "timestamp": row[1]} for row in rows]

    except Exception as e:
        logger.error(f"Failed to get scans for {competitor_name}: {e}")
        return []


def calculate_changes(scans: list[dict]) -> list[dict]:
    """
    Compares consecutive scans and identifies changes.

    Uses SequenceMatcher to calculate similarity ratio between each
    consecutive pair of scans. A similarity below the threshold
    indicates a significant content change.

    Returns:
        List of change dicts with date, similarity_ratio, and is_significant.
    """
    if len(scans) < 2:
        return []

    changes = []
    for i in range(1, len(scans)):
        prev_text = scans[i - 1]["text"]
        curr_text = scans[i]["text"]

        # SequenceMatcher gives a ratio between 0 (completely different) and 1 (identical)
        similarity = SequenceMatcher(None, prev_text, curr_text).ratio()

        changes.append({
            "date": scans[i]["timestamp"],
            "similarity_ratio": round(similarity, 3),
            "is_significant": similarity < SIGNIFICANT_CHANGE_THRESHOLD,
        })

    return changes


def analyze_competitor_trends(competitor_name: str, days: int = 30) -> dict:
    """
    Performs trend analysis for a single competitor over a time period.

    Returns a dict with:
        - total_scans: Number of scans in the period
        - significant_changes: Number of significant content changes
        - change_frequency: Average days between significant changes
        - stability_score: Percentage of days with no significant change
        - trend_direction: 'increasing', 'decreasing', or 'stable'
        - summary: Human-readable trend summary
    """
    scans = get_scans_for_period(competitor_name, days)

    if len(scans) < 2:
        return {
            "competitor": competitor_name,
            "period_days": days,
            "total_scans": len(scans),
            "significant_changes": 0,
            "change_frequency": None,
            "stability_score": 100.0,
            "trend_direction": "insufficient_data",
            "summary": f"Not enough scan history for {competitor_name} (need at least 2 scans)",
        }

    changes = calculate_changes(scans)
    significant = [c for c in changes if c["is_significant"]]
    total_changes = len(changes)
    sig_count = len(significant)

    # Calculate stability score (% of comparisons with no significant change)
    stability = ((total_changes - sig_count) / total_changes * 100) if total_changes > 0 else 100.0

    # Calculate change frequency
    if sig_count > 0:
        freq = days / sig_count
    else:
        freq = None  # No changes detected

    # Determine trend direction by comparing first half vs second half
    midpoint = len(changes) // 2
    first_half_changes = sum(1 for c in changes[:midpoint] if c["is_significant"])
    second_half_changes = sum(1 for c in changes[midpoint:] if c["is_significant"])

    if second_half_changes > first_half_changes + 1:
        trend = "increasing"
    elif first_half_changes > second_half_changes + 1:
        trend = "decreasing"
    else:
        trend = "stable"

    # Build human-readable summary
    summary = _build_trend_summary(competitor_name, days, sig_count, freq, trend, stability)

    return {
        "competitor": competitor_name,
        "period_days": days,
        "total_scans": len(scans),
        "significant_changes": sig_count,
        "change_frequency": round(freq, 1) if freq else None,
        "stability_score": round(stability, 1),
        "trend_direction": trend,
        "summary": summary,
    }


def _build_trend_summary(
    name: str, days: int, sig_count: int, freq: float | None, trend: str, stability: float
) -> str:
    """Builds a human-readable trend summary string."""
    parts = [f"{name} — {days}-day analysis:"]

    if sig_count == 0:
        parts.append(f"No significant changes detected in {days} days.")
        parts.append("The competitor's website has been stable.")
    else:
        parts.append(f"{sig_count} significant changes detected.")
        if freq:
            parts.append(f"Average frequency: one change every {freq:.0f} days.")

        if trend == "increasing":
            parts.append("Change activity is INCREASING — they may be preparing a launch.")
        elif trend == "decreasing":
            parts.append("Change activity is DECREASING — updates are slowing down.")
        else:
            parts.append("Change activity is STABLE over the period.")

    parts.append(f"Stability score: {stability:.0f}%")

    return " ".join(parts)


def generate_trend_report(competitor_names: list[str], days: int = 30) -> list[dict]:
    """
    Generates trend analysis for multiple competitors.

    Args:
        competitor_names: List of competitor names to analyze.
        days: Look-back period in days.

    Returns:
        List of trend analysis dicts, one per competitor.
    """
    results = []
    for name in competitor_names:
        trend = analyze_competitor_trends(name, days)
        results.append(trend)
        logger.info(f"Trend analysis for {name}: {trend['significant_changes']} changes, "
                     f"trend={trend['trend_direction']}")

    return results


def format_trend_report_slack(trends: list[dict]) -> str:
    """
    Formats the trend analysis results into a Slack message.

    Args:
        trends: List of trend analysis dicts from generate_trend_report().

    Returns:
        Formatted Slack message string.
    """
    lines = ["📊 *WatchTower Trend Analysis Report*\n"]

    for trend in trends:
        emoji = {
            "increasing": "🔺",
            "decreasing": "🔻",
            "stable": "➡️",
            "insufficient_data": "❓",
        }.get(trend["trend_direction"], "❓")

        lines.append(f"*{emoji} {trend['competitor']}*")
        lines.append(f"📅 Period: {trend['period_days']} days | Scans: {trend['total_scans']}")
        lines.append(f"🔄 Significant changes: {trend['significant_changes']}")

        if trend["change_frequency"]:
            lines.append(f"⏱️ Avg frequency: every {trend['change_frequency']} days")

        lines.append(f"🛡️ Stability: {trend['stability_score']}%")
        lines.append(f"📝 {trend['summary']}")
        lines.append("─────────────────────")

    return "\n".join(lines)


def get_all_competitor_names() -> list[str]:
    """
    Returns a list of all unique competitor names in the database.
    Useful for generating a full trend report without knowing the config.
    """
    try:
        conn = _get_connection()
        cursor = conn.execute("SELECT DISTINCT competitor_name FROM scans")
        names = [row[0] for row in cursor.fetchall()]
        conn.close()
        return names
    except Exception as e:
        logger.error(f"Failed to get competitor names: {e}")
        return []
