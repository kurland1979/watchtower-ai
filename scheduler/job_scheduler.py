"""
Job Scheduler — APScheduler-based cron scheduling with graceful shutdown.

Features:
- Dual-job scheduling (main scan + heartbeat verification)
- Graceful shutdown via shutdown() function (called by signal handlers)
- Configurable schedule via environment variables
"""

import logging
import os
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from agents.heartbeat import check_heartbeat, HEARTBEAT_CHECK_OFFSET_HOURS
from notifiers.slack_notifier import send_error_alert

logger = logging.getLogger(__name__)

scheduler = BlockingScheduler()


def _heartbeat_check_job():
    """
    Secondary scheduled job that verifies the daily scan completed successfully.
    Runs at (RUN_HOUR + offset) to check if the scan happened.
    If not, sends an alert to Slack.
    """
    logger.info("Running heartbeat check")
    alerts = check_heartbeat()

    for alert in alerts:
        logger.warning(f"Heartbeat alert: {alert['message']}")
        send_error_alert(f"💓 Heartbeat Alert: {alert['message']}")

    if not alerts:
        logger.info("Heartbeat check passed — all systems healthy")


def shutdown():
    """
    Graceful shutdown — called by signal handlers in main.py.
    Waits for running jobs to finish before stopping the scheduler.
    """
    if scheduler.running:
        logger.info("Scheduler shutting down gracefully (wait_for_jobs=True)...")
        scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped successfully")


def start_scheduler(job_function):
    """
    Starts the scheduler with two jobs:
    1. Main scan job — runs daily at RUN_HOUR:RUN_MINUTE
    2. Heartbeat check — runs daily at (RUN_HOUR + offset) to verify the scan completed

    RUN_HOUR and RUN_MINUTE are loaded from .env
    """
    run_hour = int(os.getenv("RUN_HOUR", 8))
    run_minute = int(os.getenv("RUN_MINUTE", 0))

    # Job 1: Main daily scan
    scheduler.add_job(
        job_function,
        trigger=CronTrigger(hour=run_hour, minute=run_minute),
        id="watchtower_daily_job",
        name="WatchTower Daily Competitor Scan",
        replace_existing=True
    )

    # Job 2: Heartbeat check — runs 1 hour after the scan
    heartbeat_hour = (run_hour + HEARTBEAT_CHECK_OFFSET_HOURS) % 24
    scheduler.add_job(
        _heartbeat_check_job,
        trigger=CronTrigger(hour=heartbeat_hour, minute=run_minute),
        id="watchtower_heartbeat_check",
        name="WatchTower Heartbeat Check",
        replace_existing=True
    )

    logger.info(f"Scheduler started - scan at {run_hour:02d}:{run_minute:02d}, "
                f"heartbeat check at {heartbeat_hour:02d}:{run_minute:02d}")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler interrupted — shutting down")
        shutdown()
