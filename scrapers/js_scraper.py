"""
JavaScript-Aware Scraper using Playwright.

Many modern competitor websites (CrowdStrike, SentinelOne, etc.) render content
dynamically via JavaScript. The standard httpx scraper only fetches the static HTML,
missing product pages, pricing tables, and feature lists that render client-side.

This module provides a Playwright-based scraper that:
1. Launches a headless Chromium browser
2. Navigates to the page and waits for JavaScript to finish rendering
3. Returns the fully-rendered HTML (including dynamically loaded content)

Usage:
    The competitor config (competitors.json) can specify "js_render": true
    for competitors that require JavaScript rendering. The main scraper
    will automatically route those competitors through this module.

Dependencies:
    pip install playwright
    playwright install chromium
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

# Lazy import — Playwright is only loaded when actually needed
_browser = None


async def _get_browser():
    """
    Lazy initialization of the Playwright browser.
    Only launches Chromium when the first JS-rendered page is requested.
    This avoids heavy startup cost when no competitors need JS rendering.
    """
    global _browser
    if _browser is None:
        try:
            from playwright.async_api import async_playwright
            playwright = await async_playwright().start()
            _browser = await playwright.chromium.launch(headless=True)
            logger.info("Playwright browser launched successfully")
        except ImportError:
            logger.error(
                "Playwright is not installed. "
                "Run: pip install playwright && playwright install chromium"
            )
            raise
        except Exception as e:
            logger.error(f"Failed to launch Playwright browser: {e}")
            raise
    return _browser


async def scrape_page_js(url: str, wait_timeout: int = 10000) -> str | None:
    """
    Scrapes a single page using a headless browser with JavaScript rendering.

    Uses try/finally to guarantee page cleanup even on exceptions,
    preventing browser memory leaks from orphaned page objects.

    Args:
        url: The URL to scrape.
        wait_timeout: Maximum time (ms) to wait for the page to load.

    Returns:
        The fully-rendered HTML content, or None on failure.
    """
    page = None
    try:
        browser = await _get_browser()
        page = await browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        )

        # Navigate and wait for network to settle (no new requests for 500ms)
        await page.goto(url, wait_until="networkidle", timeout=wait_timeout)

        # Extra wait for any late-loading dynamic content
        await page.wait_for_timeout(2000)

        html = await page.content()

        logger.info(f"JS scrape successful for {url} ({len(html)} chars)")
        return html

    except Exception as e:
        logger.error(f"JS scrape failed for {url}: {e}")
        return None

    finally:
        # Guarantee page cleanup to prevent memory leaks
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass  # Page may already be closed or browser crashed


async def scrape_competitor_js(competitor: dict) -> dict:
    """
    Scrapes all pages of a single competitor using Playwright (JavaScript rendering).
    Sequential with a small delay between pages to avoid rate limiting.

    Args:
        competitor: Dict with 'name', 'url', 'pages' keys.

    Returns:
        Dict with name, url, combined html, and status.
    """
    name = competitor["name"]
    url = competitor["url"]
    pages = competitor.get("pages", [url])

    logger.info(f"JS scraping {name} - {len(pages)} pages")

    successful_pages = []
    for i, page_url in enumerate(pages):
        html = await scrape_page_js(page_url)
        if html is not None:
            successful_pages.append(html)

        # Rate limiting between pages
        if i < len(pages) - 1:
            await asyncio.sleep(2.0)

    if not successful_pages:
        logger.error(f"{name} - all JS pages failed")
        return {
            "name": name,
            "url": url,
            "html": None,
            "status": "failed"
        }

    combined_html = "\n".join(successful_pages)
    logger.info(f"{name} - JS scraped {len(successful_pages)}/{len(pages)} pages")

    return {
        "name": name,
        "url": url,
        "html": combined_html,
        "status": "success"
    }


async def close_browser():
    """Closes the Playwright browser. Call this when shutting down."""
    global _browser
    if _browser is not None:
        await _browser.close()
        _browser = None
        logger.info("Playwright browser closed")
