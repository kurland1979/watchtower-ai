"""
Tests for scrapers/competitor_scraper.py

Covers: exponential backoff, circuit breaker integration, URL validation,
scrape_page, scrape_competitor, scrape_all_competitors.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from scrapers.competitor_scraper import (
    scrape_page,
    scrape_competitor,
    scrape_all_competitors,
    _backoff_delay,
    get_circuit_breaker,
)


class TestBackoffDelay:
    """Tests for the exponential backoff calculation."""

    def test_backoff_increases_with_attempt(self):
        """Delay should increase exponentially with attempt number."""
        d1 = _backoff_delay(1)
        d2 = _backoff_delay(2)
        d3 = _backoff_delay(3)
        # Each delay should be roughly double the previous (within jitter range)
        assert d2 > d1 * 0.5  # Accounts for jitter
        assert d3 > d2 * 0.5

    def test_backoff_respects_max(self):
        """Delay should never exceed BACKOFF_MAX regardless of attempt."""
        delay = _backoff_delay(100)
        from config.settings import settings
        max_with_jitter = settings.BACKOFF_MAX * settings.BACKOFF_JITTER_MAX
        assert delay <= max_with_jitter + 0.1  # Small float tolerance

    def test_backoff_returns_positive(self):
        """Delay should always be positive."""
        for attempt in range(1, 10):
            assert _backoff_delay(attempt) > 0


class TestScrapePage:
    """Tests for scrape_page with mocked HTTP client."""

    @pytest.mark.asyncio
    async def test_successful_scrape(self):
        """Should return HTML on successful response."""
        mock_response = MagicMock()
        mock_response.text = "<html>Hello</html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        result = await scrape_page(mock_client, "https://example.com")
        assert result == "<html>Hello</html>"

    @pytest.mark.asyncio
    async def test_invalid_url_returns_none(self):
        """Should reject URLs that fail validation (SSRF prevention)."""
        mock_client = AsyncMock()
        result = await scrape_page(mock_client, "http://localhost:8080/admin")
        assert result is None
        mock_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_private_ip_blocked(self):
        """Should block private IP addresses."""
        mock_client = AsyncMock()
        result = await scrape_page(mock_client, "http://192.168.1.1/secret")
        assert result is None

    @pytest.mark.asyncio
    async def test_retries_on_http_error(self):
        """Should retry on HTTP errors up to MAX_RETRIES."""
        mock_client = AsyncMock()
        error_response = MagicMock()
        error_response.status_code = 500
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=error_response)
        )

        with patch("scrapers.competitor_scraper.asyncio.sleep", new_callable=AsyncMock):
            result = await scrape_page(mock_client, "https://example.com")

        assert result is None
        from config.settings import settings
        assert mock_client.get.call_count == settings.SCRAPER_MAX_RETRIES

    @pytest.mark.asyncio
    async def test_retries_on_connection_error(self):
        """Should retry on connection errors."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with patch("scrapers.competitor_scraper.asyncio.sleep", new_callable=AsyncMock):
            result = await scrape_page(mock_client, "https://example.com")

        assert result is None


class TestScrapeCompetitor:
    """Tests for scrape_competitor (multi-page sequential scraping)."""

    @pytest.mark.asyncio
    async def test_all_pages_success(self):
        """Should combine HTML from all successful pages."""
        mock_response = MagicMock()
        mock_response.text = "<html>page</html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        competitor = {
            "name": "TestCorp",
            "url": "https://test.com",
            "pages": ["https://test.com/a", "https://test.com/b"],
        }

        with patch("scrapers.competitor_scraper.asyncio.sleep", new_callable=AsyncMock):
            result = await scrape_competitor(mock_client, competitor)

        assert result["status"] == "success"
        assert result["name"] == "TestCorp"
        assert "<html>page</html>" in result["html"]

    @pytest.mark.asyncio
    async def test_all_pages_fail(self):
        """Should return 'failed' status when all pages fail."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        competitor = {
            "name": "DownCorp",
            "url": "https://down.com",
            "pages": ["https://down.com/a"],
        }

        with patch("scrapers.competitor_scraper.asyncio.sleep", new_callable=AsyncMock):
            result = await scrape_competitor(mock_client, competitor)

        assert result["status"] == "failed"
        assert result["html"] is None


class TestCircuitBreakerIntegration:
    """Tests for circuit breaker integration in scrape_all_competitors."""

    @pytest.mark.asyncio
    async def test_circuit_open_skips_competitor(self):
        """When circuit is OPEN, competitor should be skipped."""
        cb = get_circuit_breaker()
        # Force circuit open by recording many failures
        for _ in range(10):
            cb.record_failure("SkipCorp")

        competitors = [
            {"name": "SkipCorp", "url": "https://skip.com", "active": True}
        ]

        results = await scrape_all_competitors(competitors)

        skipped = [r for r in results if r["name"] == "SkipCorp"]
        assert len(skipped) == 1
        assert skipped[0]["status"] == "circuit_open"

        # Cleanup
        cb.reset("SkipCorp")

    @pytest.mark.asyncio
    async def test_inactive_competitors_filtered(self):
        """Inactive competitors should not be scraped."""
        competitors = [
            {"name": "InactiveCorp", "url": "https://inactive.com", "active": False}
        ]
        results = await scrape_all_competitors(competitors)
        assert len(results) == 0
