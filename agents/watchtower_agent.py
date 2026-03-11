"""
WatchTower Agent — orchestrates the full monitoring pipeline.

Features:
- Multi-client support (each client has its own config, Slack channel)
- Overall job timeout (prevents hung pipelines from blocking the scheduler)
- Per-client error isolation (one client's failure doesn't stop others)
"""

import asyncio
import json
import logging
import os
import logging.handlers
from dotenv import load_dotenv

from scrapers.competitor_scraper import scrape_all_competitors
from parsers.competitor_parser import parse_all_competitors
from llm.analyzer import analyze_all_competitors
from notifiers.slack_notifier import send_report, send_error_alert
from config.client_loader import load_all_clients
from config.settings import settings
from agents.heartbeat import record_heartbeat

load_dotenv()


log_file = os.path.join(os.path.dirname(__file__), "..", "logs", "watchtower.log")
os.makedirs(os.path.dirname(log_file), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            log_file, maxBytes=5_000_000, backupCount=3
        )
    ]
)
logger = logging.getLogger(__name__)

# Legacy config path — kept for backward compatibility
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "competitors.json")


def load_competitors() -> list:
    """
    Loads competitor list from competitors.json (legacy single-client mode).
    Kept for backward compatibility.
    """
    with open(CONFIG_PATH, "r") as f:
        data = json.load(f)
    return data["competitors"]


async def run_client(client: dict):
    """
    Runs the full pipeline for a single client.
    Each client has its own industry, competitors, and Slack channel.

    Pipeline: Load → Scrape → Parse → Analyze → Notify
    """
    client_name = client["client_name"]
    industry = client["industry"]
    competitors = client["competitors"]

    # Determine Slack credentials — per-client or fallback to env
    slack_channel = client.get("slack_channel_id") or os.getenv("SLACK_CHANNEL_ID")
    slack_token = client.get("slack_bot_token") or os.getenv("SLACK_BOT_TOKEN")

    logger.info(f"[{client_name}] Starting pipeline - {len(competitors)} competitors")

    # Step 1 - Scrape
    logger.info(f"[{client_name}] Starting scraping phase")
    scrape_results = await scrape_all_competitors(competitors)

    failed_scrapes = [r for r in scrape_results if r["status"] == "failed"]
    if failed_scrapes:
        names = ", ".join([r["name"] for r in failed_scrapes])
        logger.warning(f"[{client_name}] Scraping failed for: {names}")
        send_error_alert(
            f"[{client_name}] Scraping failed for: {names}",
            channel_id=slack_channel,
            bot_token=slack_token,
        )

    successful_scrapes = [r for r in scrape_results if r["status"] == "success"]
    if not successful_scrapes:
        logger.error(f"[{client_name}] All scrapes failed - aborting")
        send_error_alert(
            f"[{client_name}] WatchTower aborted - all scrapes failed",
            channel_id=slack_channel,
            bot_token=slack_token,
        )
        return

    # Step 2 - Parse
    logger.info(f"[{client_name}] Starting parsing phase")
    parse_results = parse_all_competitors(successful_scrapes)

    failed_parses = [r for r in parse_results if r["status"] == "failed"]
    if failed_parses:
        names = ", ".join([r["name"] for r in failed_parses])
        logger.warning(f"[{client_name}] Parsing failed for: {names}")

    successful_parses = [r for r in parse_results if r["status"] == "success"]
    if not successful_parses:
        logger.error(f"[{client_name}] All parses failed - aborting")
        send_error_alert(
            f"[{client_name}] WatchTower aborted - all parsing failed",
            channel_id=slack_channel,
            bot_token=slack_token,
        )
        return

    # Step 3 - Analyze with LLM (passes industry for tailored prompt)
    logger.info(f"[{client_name}] Starting LLM analysis phase")
    try:
        analysis_results = await analyze_all_competitors(
            successful_parses, industry=industry
        )
    except Exception as e:
        logger.error(f"[{client_name}] LLM analysis failed: {e}")
        send_error_alert(
            f"[{client_name}] LLM analysis failed: {e}",
            channel_id=slack_channel,
            bot_token=slack_token,
        )
        return

    # Step 4 - Send report to Slack
    logger.info(f"[{client_name}] Sending report to Slack")
    success = send_report(
        analysis_results,
        channel_id=slack_channel,
        bot_token=slack_token,
        client_name=client_name,
    )

    if success:
        logger.info(f"[{client_name}] Pipeline completed successfully")
        record_heartbeat(client_name)
    else:
        logger.error(f"[{client_name}] Failed to send Slack report")
        send_error_alert(
            f"[{client_name}] Failed to send the daily report to Slack",
            channel_id=slack_channel,
            bot_token=slack_token,
        )


async def run_agent():
    """
    Main agent flow — multi-client support with overall job timeout.

    Loads all client configs from config/clients/ directory.
    Falls back to legacy competitors.json if no client files exist.
    Runs each client's pipeline sequentially to avoid API rate limits.

    The entire run is wrapped in asyncio.wait_for() to enforce
    OVERALL_JOB_TIMEOUT — prevents hung pipelines from blocking
    the scheduler indefinitely.
    """
    logger.info("WatchTower Agent started")

    # Load all client configs
    try:
        clients = load_all_clients()
        if not clients:
            logger.error("No client configs found - aborting")
            send_error_alert("WatchTower: No client configs found")
            return
        logger.info(f"Loaded {len(clients)} client(s)")
    except Exception as e:
        logger.error(f"Failed to load client configs: {e}")
        send_error_alert(f"WatchTower failed to load configs: {e}")
        return

    # Run pipeline for each client with overall timeout
    try:
        await asyncio.wait_for(
            _run_all_clients(clients),
            timeout=settings.OVERALL_JOB_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error(
            f"WatchTower Agent timed out after {settings.OVERALL_JOB_TIMEOUT}s"
        )
        send_error_alert(
            f"WatchTower pipeline timed out after {settings.OVERALL_JOB_TIMEOUT}s. "
            "Some clients may not have been processed."
        )

    logger.info("WatchTower Agent — all clients completed")


async def _run_all_clients(clients: list) -> None:
    """Runs pipeline for each client sequentially."""
    for client in clients:
        try:
            await run_client(client)
        except Exception as e:
            logger.error(f"[{client['client_name']}] Unexpected error: {e}")


def run():
    """
    Entry point - runs the agent.
    """
    asyncio.run(run_agent())


if __name__ == "__main__":
    run()
