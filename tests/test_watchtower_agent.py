"""
Tests for agents/watchtower_agent.py

Covers: run_client pipeline, run_agent multi-client flow,
job timeout, error isolation, heartbeat recording.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from agents.watchtower_agent import run_client, run_agent, _run_all_clients


@pytest.fixture
def sample_client():
    """Sample client config for testing."""
    return {
        "client_name": "TestClient",
        "industry": "cybersecurity",
        "competitors": [
            {"name": "CorpA", "url": "https://a.com", "active": True}
        ],
        "slack_channel_id": "#test",
        "slack_bot_token": "xoxb-test",
    }


class TestRunClient:
    """Tests for the single-client pipeline."""

    @pytest.mark.asyncio
    async def test_successful_pipeline(self, sample_client):
        """Full pipeline should complete successfully."""
        with patch("agents.watchtower_agent.scrape_all_competitors", new_callable=AsyncMock) as mock_scrape, \
             patch("agents.watchtower_agent.parse_all_competitors") as mock_parse, \
             patch("agents.watchtower_agent.analyze_all_competitors", new_callable=AsyncMock) as mock_analyze, \
             patch("agents.watchtower_agent.send_report", return_value=True) as mock_send, \
             patch("agents.watchtower_agent.record_heartbeat") as mock_hb:

            mock_scrape.return_value = [{"name": "CorpA", "url": "u", "html": "<html>", "status": "success"}]
            mock_parse.return_value = [{"name": "CorpA", "url": "u", "text": "parsed", "status": "success"}]
            mock_analyze.return_value = [{"name": "CorpA", "url": "u", "summary": "s", "implication": "i", "recommended_action": "a"}]

            await run_client(sample_client)

            mock_scrape.assert_called_once()
            mock_parse.assert_called_once()
            mock_analyze.assert_called_once()
            mock_send.assert_called_once()
            mock_hb.assert_called_once_with("TestClient")

    @pytest.mark.asyncio
    async def test_all_scrapes_failed_aborts(self, sample_client):
        """Should abort when all scrapes fail."""
        with patch("agents.watchtower_agent.scrape_all_competitors", new_callable=AsyncMock) as mock_scrape, \
             patch("agents.watchtower_agent.parse_all_competitors") as mock_parse, \
             patch("agents.watchtower_agent.send_error_alert") as mock_alert:

            mock_scrape.return_value = [{"name": "CorpA", "url": "u", "html": None, "status": "failed"}]

            await run_client(sample_client)

            # Parse should NOT be called since all scrapes failed
            mock_parse.assert_not_called()
            # Error alert SHOULD be sent
            assert mock_alert.call_count >= 1

    @pytest.mark.asyncio
    async def test_llm_failure_sends_alert(self, sample_client):
        """Should send alert when LLM analysis fails."""
        with patch("agents.watchtower_agent.scrape_all_competitors", new_callable=AsyncMock) as mock_scrape, \
             patch("agents.watchtower_agent.parse_all_competitors") as mock_parse, \
             patch("agents.watchtower_agent.analyze_all_competitors", new_callable=AsyncMock) as mock_analyze, \
             patch("agents.watchtower_agent.send_error_alert") as mock_alert:

            mock_scrape.return_value = [{"name": "CorpA", "url": "u", "html": "<html>", "status": "success"}]
            mock_parse.return_value = [{"name": "CorpA", "url": "u", "text": "parsed", "status": "success"}]
            mock_analyze.side_effect = Exception("API quota exceeded")

            await run_client(sample_client)
            assert mock_alert.call_count >= 1

    @pytest.mark.asyncio
    async def test_slack_failure_does_not_crash(self, sample_client):
        """Should handle Slack failure gracefully."""
        with patch("agents.watchtower_agent.scrape_all_competitors", new_callable=AsyncMock) as mock_scrape, \
             patch("agents.watchtower_agent.parse_all_competitors") as mock_parse, \
             patch("agents.watchtower_agent.analyze_all_competitors", new_callable=AsyncMock) as mock_analyze, \
             patch("agents.watchtower_agent.send_report", return_value=False), \
             patch("agents.watchtower_agent.send_error_alert"):

            mock_scrape.return_value = [{"name": "CorpA", "url": "u", "html": "<html>", "status": "success"}]
            mock_parse.return_value = [{"name": "CorpA", "url": "u", "text": "parsed", "status": "success"}]
            mock_analyze.return_value = [{"name": "CorpA", "summary": "s"}]

            # Should not raise
            await run_client(sample_client)


class TestRunAgent:
    """Tests for the main agent flow."""

    @pytest.mark.asyncio
    async def test_no_clients_aborts(self):
        """Should abort with alert when no clients found."""
        with patch("agents.watchtower_agent.load_all_clients", return_value=[]), \
             patch("agents.watchtower_agent.send_error_alert") as mock_alert:
            await run_agent()
            mock_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_config_load_error(self):
        """Should handle config loading errors."""
        with patch("agents.watchtower_agent.load_all_clients", side_effect=Exception("bad json")), \
             patch("agents.watchtower_agent.send_error_alert") as mock_alert:
            await run_agent()
            mock_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_sends_alert(self):
        """Should send alert when pipeline times out."""
        async def slow_clients(clients):
            await asyncio.sleep(100)  # Simulate very slow pipeline

        with patch("agents.watchtower_agent.load_all_clients", return_value=[{"client_name": "test"}]), \
             patch("agents.watchtower_agent._run_all_clients", side_effect=slow_clients), \
             patch("agents.watchtower_agent.settings") as mock_settings, \
             patch("agents.watchtower_agent.send_error_alert") as mock_alert:

            mock_settings.OVERALL_JOB_TIMEOUT = 0.1  # 100ms timeout

            await run_agent()
            mock_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_one_client_error_continues(self):
        """Error in one client should not prevent others from running."""
        clients = [
            {"client_name": "failing"},
            {"client_name": "succeeding"},
        ]

        call_log = []

        async def mock_run_client(client):
            call_log.append(client["client_name"])
            if client["client_name"] == "failing":
                raise Exception("boom")

        with patch("agents.watchtower_agent.run_client", side_effect=mock_run_client):
            await _run_all_clients(clients)

        assert "failing" in call_log
        assert "succeeding" in call_log
