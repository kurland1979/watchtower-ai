"""
Slack Notifier — sends reports and alerts with retry logic.

Features:
- Exponential backoff on Slack API failures (rate limits, transient errors)
- Per-client token caching for multi-client support
- Structured error reporting
"""

import logging
import os
import time
import random
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config.settings import settings

logger = logging.getLogger(__name__)

# Cache of WebClient instances per bot token (multi-client support)
_clients: dict[str, WebClient] = {}


def _get_client(bot_token: str | None = None) -> WebClient:
    """
    Lazy initialization with per-token caching.
    In multi-client mode, different clients may have different Slack tokens.
    Falls back to SLACK_BOT_TOKEN env var if no token is provided.
    """
    token = bot_token or os.getenv("SLACK_BOT_TOKEN")
    if token not in _clients:
        _clients[token] = WebClient(token=token)
    return _clients[token]


def _get_channel_id() -> str:
    return os.getenv("SLACK_CHANNEL_ID")


def _slack_send_with_retry(client: WebClient, channel: str, text: str) -> bool:
    """
    Sends a Slack message with exponential backoff retry.

    Retries on:
    - rate_limited errors (respects Slack's Retry-After header)
    - Transient server errors (5xx)

    Does NOT retry on:
    - Auth errors (invalid_auth, token_revoked)
    - Channel errors (channel_not_found)
    """
    for attempt in range(1, settings.SLACK_RETRY_MAX + 1):
        try:
            client.chat_postMessage(channel=channel, text=text, mrkdwn=True)
            return True

        except SlackApiError as e:
            error_code = e.response.get("error", "unknown")

            # Non-retryable errors — fail immediately
            if error_code in ("invalid_auth", "token_revoked", "channel_not_found",
                              "not_in_channel", "account_inactive"):
                logger.error(f"Slack permanent error: {error_code} — not retrying")
                return False

            # Rate limited — respect Retry-After header
            if error_code == "ratelimited":
                retry_after = int(e.response.headers.get("Retry-After", 5))
                logger.warning(f"Slack rate limited, waiting {retry_after}s")
                time.sleep(retry_after)
                continue

            # Transient error — exponential backoff
            if attempt < settings.SLACK_RETRY_MAX:
                delay = settings.BACKOFF_BASE * (settings.BACKOFF_MULTIPLIER ** attempt)
                delay *= random.uniform(settings.BACKOFF_JITTER_MIN, settings.BACKOFF_JITTER_MAX)
                logger.warning(
                    f"Slack error '{error_code}' (attempt {attempt}/{settings.SLACK_RETRY_MAX}), "
                    f"retrying in {delay:.1f}s"
                )
                time.sleep(delay)
            else:
                logger.error(
                    f"Slack failed after {settings.SLACK_RETRY_MAX} attempts: {error_code}"
                )
                return False

        except Exception as e:
            logger.error(f"Unexpected Slack error: {e}")
            return False

    return False


def format_report(analysis_results: list, client_name: str | None = None) -> str:
    """
    Formats the analysis results into a structured Slack message.
    Includes client name in the header when running in multi-client mode.
    """
    report_time = datetime.now().strftime("%d/%m/%Y %H:%M")

    header = "WatchTower Daily Report"
    if client_name and client_name != "default":
        header += f" — {client_name}"

    if not analysis_results:
        return f"✅ *{header}*\n📅 {report_time}\nNo significant competitor changes detected today."

    lines = [f"🔍 *{header}*", f"📅 {report_time}\n"]

    for result in analysis_results:
        detected_at = result.get("detected_at") or datetime.now().strftime("%d/%m/%Y %H:%M")
        severity = result.get("severity", "N/A")
        lines.append(f"*🏢 {result['name']}*")
        lines.append(f"🕐 *Detected at:* {detected_at}")
        lines.append(f"🔺 *Severity:* {severity}")
        lines.append(f"📌 *What changed:* {result['summary']}")
        lines.append(f"⚠️ *Implication:* {result['implication']}")
        lines.append(f"✅ *Recommended action:* {result['recommended_action']}")
        lines.append(f"🔗 {result['url']}")
        lines.append("─────────────────────")

    return "\n".join(lines)


def send_report(
    analysis_results: list,
    channel_id: str | None = None,
    bot_token: str | None = None,
    client_name: str | None = None,
) -> bool:
    """
    Sends the daily competitor report to Slack with retry logic.

    Args:
        analysis_results: List of analysis result dicts.
        channel_id: Target Slack channel. Falls back to env var.
        bot_token: Slack bot token. Falls back to env var.
        client_name: Client name for the report header.

    Returns True if successful, False otherwise.
    """
    message = format_report(analysis_results, client_name=client_name)
    target_channel = channel_id or _get_channel_id()

    if not target_channel:
        logger.error("No Slack channel configured — cannot send report")
        return False

    logger.info(f"Sending report to Slack channel {target_channel}")
    client = _get_client(bot_token)
    success = _slack_send_with_retry(client, target_channel, message)

    if success:
        logger.info("Report sent successfully")
    else:
        logger.error("Failed to send report after retries")

    return success


def send_error_alert(
    message: str,
    channel_id: str | None = None,
    bot_token: str | None = None,
) -> bool:
    """
    Sends an error alert to Slack with retry logic.

    Args:
        message: Error message text.
        channel_id: Target Slack channel. Falls back to env var.
        bot_token: Slack bot token. Falls back to env var.

    Returns True if successful, False otherwise.
    """
    target_channel = channel_id or _get_channel_id()

    if not target_channel:
        logger.error("No Slack channel configured — cannot send alert")
        return False

    client = _get_client(bot_token)
    return _slack_send_with_retry(
        client, target_channel, f"🚨 *WatchTower Alert*\n{message}"
    )
