"""
Integration Tests — end-to-end pipeline verification.

Tests the interaction between modules without external dependencies
(Anthropic API, Slack API, live websites are all mocked).
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from agents.watchtower_agent import run_client


@pytest.fixture
def full_client_config():
    """Complete client config for integration tests."""
    return {
        "client_name": "IntegrationTest",
        "industry": "cybersecurity",
        "competitors": [
            {
                "name": "CrowdStrike",
                "url": "https://crowdstrike.com",
                "active": True,
                "pages": ["https://crowdstrike.com/products"],
                "js_render": False,
            }
        ],
        "slack_channel_id": "#test-integration",
        "slack_bot_token": "xoxb-integration-test",
    }


class TestEndToEndPipeline:
    """Integration tests for the full Scrape → Parse → Analyze → Notify pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_success(self, full_client_config):
        """Complete pipeline should flow from scrape to Slack notification."""
        with patch("agents.watchtower_agent.scrape_all_competitors", new_callable=AsyncMock) as mock_scrape, \
             patch("agents.watchtower_agent.parse_all_competitors") as mock_parse, \
             patch("agents.watchtower_agent.analyze_all_competitors", new_callable=AsyncMock) as mock_analyze, \
             patch("agents.watchtower_agent.send_report", return_value=True) as mock_send, \
             patch("agents.watchtower_agent.record_heartbeat") as mock_hb:

            mock_scrape.return_value = [
                {"name": "CrowdStrike", "url": "https://crowdstrike.com",
                 "html": "<html><body>Product page</body></html>", "status": "success"}
            ]
            mock_parse.return_value = [
                {"name": "CrowdStrike", "url": "https://crowdstrike.com",
                 "text": "CrowdStrike Falcon platform - endpoint protection", "status": "success"}
            ]
            mock_analyze.return_value = [
                {"name": "CrowdStrike", "url": "https://crowdstrike.com",
                 "summary": "New Falcon feature", "implication": "Competitive threat",
                 "recommended_action": "Evaluate feature gap"}
            ]

            await run_client(full_client_config)

            # Verify full pipeline executed
            mock_scrape.assert_called_once()
            mock_parse.assert_called_once()
            mock_analyze.assert_called_once()
            mock_send.assert_called_once()
            mock_hb.assert_called_once_with("IntegrationTest")

            # Verify Slack was called with correct channel
            send_kwargs = mock_send.call_args
            assert send_kwargs.kwargs.get("channel_id") == "#test-integration"
            assert send_kwargs.kwargs.get("client_name") == "IntegrationTest"

    @pytest.mark.asyncio
    async def test_partial_scrape_continues(self, full_client_config):
        """Pipeline should continue even if some scrapes fail."""
        full_client_config["competitors"].append({
            "name": "FailCorp", "url": "https://fail.com", "active": True
        })

        with patch("agents.watchtower_agent.scrape_all_competitors", new_callable=AsyncMock) as mock_scrape, \
             patch("agents.watchtower_agent.parse_all_competitors") as mock_parse, \
             patch("agents.watchtower_agent.analyze_all_competitors", new_callable=AsyncMock) as mock_analyze, \
             patch("agents.watchtower_agent.send_report", return_value=True), \
             patch("agents.watchtower_agent.send_error_alert"), \
             patch("agents.watchtower_agent.record_heartbeat"):

            mock_scrape.return_value = [
                {"name": "CrowdStrike", "url": "u", "html": "<html>ok</html>", "status": "success"},
                {"name": "FailCorp", "url": "u", "html": None, "status": "failed"},
            ]
            mock_parse.return_value = [
                {"name": "CrowdStrike", "url": "u", "text": "content", "status": "success"}
            ]
            mock_analyze.return_value = [{"name": "CrowdStrike", "summary": "ok"}]

            await run_client(full_client_config)

            # Parse and analyze should still be called with successful scrapes
            mock_parse.assert_called_once()
            mock_analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_circuit_open_reported(self, full_client_config):
        """Circuit-open competitors should appear in results but not block pipeline."""
        with patch("agents.watchtower_agent.scrape_all_competitors", new_callable=AsyncMock) as mock_scrape, \
             patch("agents.watchtower_agent.parse_all_competitors") as mock_parse, \
             patch("agents.watchtower_agent.analyze_all_competitors", new_callable=AsyncMock) as mock_analyze, \
             patch("agents.watchtower_agent.send_report", return_value=True), \
             patch("agents.watchtower_agent.send_error_alert"), \
             patch("agents.watchtower_agent.record_heartbeat"):

            # Simulate circuit_open status from scraper
            mock_scrape.return_value = [
                {"name": "CrowdStrike", "url": "u", "html": None, "status": "circuit_open"}
            ]

            await run_client(full_client_config)

            # No successful scrapes means parse should NOT be called
            mock_parse.assert_not_called()


class TestConfigIntegration:
    """Tests for configuration loading integration."""

    def test_settings_singleton(self):
        """Settings should be a singleton loaded from env."""
        from config.settings import settings
        assert settings.SCRAPER_TIMEOUT > 0
        assert settings.SCRAPER_MAX_RETRIES > 0
        assert settings.CIRCUIT_BREAKER_THRESHOLD > 0

    def test_validation_functions_accessible(self):
        """Validation utilities should be importable and functional."""
        from utils.validation import validate_url, validate_competitor_name

        valid, _ = validate_url("https://example.com")
        assert valid

        valid, _ = validate_competitor_name("TestCorp")
        assert valid
