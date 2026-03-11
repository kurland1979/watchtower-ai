import sys
import signal
import logging
from dotenv import load_dotenv

load_dotenv()

from config.settings import validate_required_env_vars
from scheduler.job_scheduler import start_scheduler
from agents.watchtower_agent import run

logger = logging.getLogger(__name__)


def _handle_shutdown(signum, frame):
    """
    Graceful shutdown on SIGTERM/SIGINT.
    Allows the current job to finish, then exits cleanly.
    """
    sig_name = signal.Signals(signum).name
    logger.info(f"Received {sig_name} — initiating graceful shutdown")
    sys.exit(0)


if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    # Fail fast if critical env vars are missing
    missing = validate_required_env_vars()
    if missing:
        print(f"FATAL: Missing required environment variables: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in your values.")
        sys.exit(1)

    print("WatchTower AI is starting...")
    start_scheduler(run)
