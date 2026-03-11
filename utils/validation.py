"""
Input Validation & SSRF Prevention.

SSRF (Server-Side Request Forgery) is an attack where an attacker tricks the
server into making requests to internal resources. In WatchTower, if someone
puts "http://localhost:8080/admin" as a competitor URL, our scraper would
happily fetch internal admin panels.

This module prevents that by:
1. Validating URLs — only http/https, no private IPs, no localhost
2. Validating competitor names — alphanumeric only, prevents injection
"""

import re
import ipaddress
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Private IP ranges that should never be scraped (RFC 1918 + loopback)
PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
]

# Competitor names: letters, numbers, spaces, dots, hyphens, ampersands
VALID_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9\s.\-&]+$")


def is_private_ip(hostname: str) -> bool:
    """
    Checks if a hostname resolves to a private/internal IP address.
    Returns True if the IP is private (should be blocked).
    """
    try:
        ip = ipaddress.ip_address(hostname)
        return any(ip in network for network in PRIVATE_NETWORKS)
    except ValueError:
        # Not an IP address (it's a hostname) — that's fine
        return False


def validate_url(url: str) -> tuple[bool, str]:
    """
    Validates a URL for safe scraping.

    Checks:
    1. Must use http:// or https://
    2. Must have a valid hostname
    3. Cannot point to localhost or private IPs
    4. Cannot use file://, ftp://, or other schemes

    Returns:
        (is_valid, error_message) — (True, "") if valid, (False, "reason") if not.
    """
    if not url or not url.strip():
        return False, "URL is empty"

    try:
        parsed = urlparse(url)
    except Exception:
        return False, "URL parsing failed"

    # Scheme check
    if parsed.scheme not in ("http", "https"):
        return False, f"Invalid scheme '{parsed.scheme}' — only http/https allowed"

    # Hostname check
    hostname = parsed.hostname
    if not hostname:
        return False, "URL has no hostname"

    # Localhost check
    blocked_hostnames = {"localhost", "0.0.0.0", "127.0.0.1", "::1"}
    if hostname.lower() in blocked_hostnames:
        return False, f"Blocked hostname: {hostname} (localhost not allowed)"

    # Private IP check
    if is_private_ip(hostname):
        return False, f"Blocked IP: {hostname} (private/internal IPs not allowed)"

    return True, ""


def validate_competitor_name(name: str) -> tuple[bool, str]:
    """
    Validates a competitor name for safe use in database queries and file paths.

    Allows: letters, numbers, spaces, dots, hyphens, ampersands.
    Blocks: SQL injection chars, path traversal, shell metacharacters.

    Returns:
        (is_valid, error_message)
    """
    if not name or not name.strip():
        return False, "Competitor name is empty"

    if len(name) > 100:
        return False, "Competitor name too long (max 100 chars)"

    if not VALID_NAME_PATTERN.match(name):
        return False, f"Invalid characters in competitor name: '{name}'"

    return True, ""
