"""
Competitor Scraper — Static HTTP scraping with resilience patterns.

Features:
- Exponential backoff with jitter (replaces fixed sleep(2))
- Circuit breaker integration (skip persistently-down competitors)
- URL validation / SSRF prevention
- Centralized settings (no magic numbers)
"""

import httpx
import asyncio
import logging
import random

from config.settings import settings
from utils.validation import validate_url
from utils.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

# Shared circuit breaker instance (persists state across runs)
_circuit_breaker = CircuitBreaker()

# Realistic browser User-Agent to avoid being blocked
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _backoff_delay(attempt: int) -> float:
    """
    Calculates exponential backoff delay with jitter.

    Formula: base * (multiplier ^ attempt) * random_jitter
    Example with defaults: 1.0 * (2^1) * ~1.0 = ~2s, then ~4s, ~8s, ...
    Capped at BACKOFF_MAX to prevent absurdly long waits.
    """
    delay = settings.BACKOFF_BASE * (settings.BACKOFF_MULTIPLIER ** attempt)
    delay = min(delay, settings.BACKOFF_MAX)
    jitter = random.uniform(settings.BACKOFF_JITTER_MIN, settings.BACKOFF_JITTER_MAX)
    return delay * jitter


async def scrape_page(client: httpx.AsyncClient, url: str) -> str | None:
    """
    Scrapes a single page with exponential backoff.
    Returns HTML string on success, None on failure.
    """
    # Validate URL before making request (SSRF prevention)
    is_valid, error = validate_url(url)
    if not is_valid:
        logger.warning(f"URL validation failed for {url}: {error}")
        return None

    for attempt in range(1, settings.SCRAPER_MAX_RETRIES + 1):
        try:
            response = await client.get(
                url, timeout=settings.SCRAPER_TIMEOUT, follow_redirects=True
            )
            response.raise_for_status()
            return response.text

        except httpx.HTTPStatusError as e:
            logger.warning(
                f"HTTP {e.response.status_code} on {url} (attempt {attempt}/{settings.SCRAPER_MAX_RETRIES})"
            )
        except httpx.RequestError as e:
            logger.warning(
                f"Request error on {url} (attempt {attempt}/{settings.SCRAPER_MAX_RETRIES}): {e}"
            )

        # Exponential backoff between retries
        if attempt < settings.SCRAPER_MAX_RETRIES:
            delay = _backoff_delay(attempt)
            logger.debug(f"Backoff: waiting {delay:.1f}s before retry {attempt + 1}")
            await asyncio.sleep(delay)

    logger.error(f"Failed to scrape {url} after {settings.SCRAPER_MAX_RETRIES} attempts")
    return None


async def scrape_competitor(client: httpx.AsyncClient, competitor: dict) -> dict:
    """
    Scrapes all pages of a single competitor sequentially with rate limiting.
    Returns a dict with name, url, combined html content, and status.
    """
    name = competitor["name"]
    url = competitor["url"]
    pages = competitor.get("pages", [url])

    logger.info(f"Scraping {name} - {len(pages)} pages")

    successful_pages = []
    for i, page_url in enumerate(pages):
        html = await scrape_page(client, page_url)
        if html is not None:
            successful_pages.append(html)

        # Rate limiting: wait between requests to the same competitor
        if i < len(pages) - 1:
            delay = random.uniform(
                settings.RATE_LIMIT_DELAY_MIN, settings.RATE_LIMIT_DELAY_MAX
            )
            logger.debug(f"Rate limiting: waiting {delay:.1f}s before next request to {name}")
            await asyncio.sleep(delay)

    if not successful_pages:
        logger.error(f"{name} - all pages failed")
        return {
            "name": name,
            "url": url,
            "html": None,
            "status": "failed"
        }

    combined_html = "\n".join(successful_pages)
    logger.info(f"{name} - scraped {len(successful_pages)}/{len(pages)} pages successfully")

    return {
        "name": name,
        "url": url,
        "html": combined_html,
        "status": "success"
    }


async def scrape_all_competitors(competitors: list) -> list:
    """
    Scrapes all active competitors concurrently.

    Pipeline:
    1. Filter active competitors
    2. Check circuit breaker — skip competitors that are persistently down
    3. Route: js_render=True → Playwright, js_render=False → httpx
    4. Record success/failure in circuit breaker

    Returns a list of result dicts.
    """
    active = [c for c in competitors if c.get("active", False)]

    # Check circuit breakers — skip competitors whose circuit is OPEN
    allowed = []
    skipped = []
    for comp in active:
        if _circuit_breaker.can_execute(comp["name"]):
            allowed.append(comp)
        else:
            skipped.append(comp)
            logger.info(f"Circuit OPEN for {comp['name']} — skipping")

    # Split into static and JS-rendered competitors
    static_competitors = [c for c in allowed if not c.get("js_render", False)]
    js_competitors = [c for c in allowed if c.get("js_render", False)]

    results = []

    # Add skipped competitors as "skipped" status
    for comp in skipped:
        results.append({
            "name": comp["name"],
            "url": comp["url"],
            "html": None,
            "status": "circuit_open"
        })

    # Scrape static competitors with httpx
    if static_competitors:
        async with httpx.AsyncClient(headers=DEFAULT_HEADERS) as client:
            tasks = [scrape_competitor(client, comp) for comp in static_competitors]
            static_results = await asyncio.gather(*tasks)
            results.extend(static_results)

    # Scrape JS-rendered competitors with Playwright
    if js_competitors:
        try:
            from scrapers.js_scraper import scrape_competitor_js, close_browser
            js_tasks = [scrape_competitor_js(comp) for comp in js_competitors]
            js_results = await asyncio.gather(*js_tasks)
            results.extend(js_results)
            await close_browser()
        except ImportError:
            logger.error(
                "Playwright not installed — JS competitors will be scraped with httpx. "
                "Install with: pip install playwright && playwright install chromium"
            )
            async with httpx.AsyncClient(headers=DEFAULT_HEADERS) as client:
                fallback_tasks = [scrape_competitor(client, comp) for comp in js_competitors]
                fallback_results = await asyncio.gather(*fallback_tasks)
                results.extend(fallback_results)

    # Update circuit breaker state based on results
    for result in results:
        if result["status"] == "circuit_open":
            continue  # Already handled
        if result["status"] == "success":
            _circuit_breaker.record_success(result["name"])
        else:
            _circuit_breaker.record_failure(result["name"])

    return results


def get_circuit_breaker() -> CircuitBreaker:
    """Exposes the circuit breaker instance for dashboard/testing."""
    return _circuit_breaker
