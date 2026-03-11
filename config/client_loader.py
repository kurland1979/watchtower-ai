"""
Multi-Client Configuration Loader.

Supports two modes:
1. Legacy mode — reads from config/competitors.json (single client, backward compatible)
2. Multi-client mode — reads from config/clients/*.json (one file per client)

Each client profile contains:
- client_name: Unique identifier
- industry: Injected into the LLM prompt for tailored analysis
- slack_channel_id: Target Slack channel for this client's reports
- slack_bot_token: (Optional) Per-client Slack token, falls back to env var
- competitors: List of competitors with their URLs and settings

Architecture decision:
    Each client file is a standalone JSON — no shared state between clients.
    This makes it safe to add/remove clients without affecting others.
"""

import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.join(os.path.dirname(__file__))
CLIENTS_DIR = os.path.join(CONFIG_DIR, "clients")
LEGACY_CONFIG = os.path.join(CONFIG_DIR, "competitors.json")


def load_single_client(file_path: str) -> dict | None:
    """
    Loads a single client config from a JSON file.
    Returns the parsed dict, or None if the file is invalid.
    """
    try:
        with open(file_path, "r") as f:
            data = json.load(f)

        # Validate required fields
        required = ["client_name", "industry", "competitors"]
        for field in required:
            if field not in data:
                logger.error(f"Client config {file_path} missing required field: {field}")
                return None

        logger.info(f"Loaded client: {data['client_name']} ({len(data['competitors'])} competitors)")
        return data

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {file_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to load client config {file_path}: {e}")
        return None


def load_all_clients() -> list[dict]:
    """
    Loads all client configs from the clients/ directory.
    Falls back to legacy competitors.json if no client files exist.

    Returns:
        A list of client config dicts. Each dict contains:
        - client_name, industry, competitors, slack_channel_id, slack_bot_token
    """
    clients = []

    # Try multi-client mode first
    if os.path.isdir(CLIENTS_DIR):
        client_files = sorted(Path(CLIENTS_DIR).glob("*.json"))

        for file_path in client_files:
            client = load_single_client(str(file_path))
            if client is not None:
                clients.append(client)

    if clients:
        logger.info(f"Multi-client mode: loaded {len(clients)} clients")
        return clients

    # Fallback to legacy mode
    if os.path.exists(LEGACY_CONFIG):
        logger.info("Falling back to legacy single-client config (competitors.json)")
        try:
            with open(LEGACY_CONFIG, "r") as f:
                data = json.load(f)

            legacy_client = {
                "client_name": "default",
                "industry": data.get("industry", "technology startup"),
                "slack_channel_id": os.getenv("SLACK_CHANNEL_ID", ""),
                "slack_bot_token": os.getenv("SLACK_BOT_TOKEN", ""),
                "competitors": data.get("competitors", []),
            }
            return [legacy_client]

        except Exception as e:
            logger.error(f"Failed to load legacy config: {e}")

    logger.error("No client configs found in clients/ or competitors.json")
    return []


def get_client_by_name(name: str) -> dict | None:
    """
    Loads a specific client by name.
    Useful for running a single client manually (e.g. for testing).
    """
    all_clients = load_all_clients()
    for client in all_clients:
        if client["client_name"] == name:
            return client
    logger.warning(f"Client '{name}' not found")
    return None
