"""
Tests for notifiers/slack_notifier.py

Covers: retry logic, error classification, format_report,
send_report, send_error_alert, per-client token handling.
"""

import pytest
from unittest.mock import patch, MagicMock
from slack_sdk.errors import SlackApiError

from notifiers.slack_notifier import (
    format_report,
    send_report,
    send_error_alert,
    _slack_send_with_retry,
)


class TestFormatReport:
    """Tests for report formatting."""

    def test_empty_results(self):
        """Should return 'no changes' message for empty results."""
        msg = format_report([])
        assert "No significant" in msg

    def test_includes_competitor_name(self):
        """Should include competitor names in report."""
        results = [{
            "name": "TestCorp",
            "url": "https://test.com",
            "summary": "New feature launched",
            "implication": "May affect market share",
            "recommended_action": "Monitor closely",
        }]
        msg = format_report(results)
        assert "TestCorp" in msg

    def test_includes_client_name(self):
        """Should include client name in header when provided."""
        msg = format_report([], client_name="Acme Inc")
        assert "Acme Inc" in msg

    def test_excludes_default_client_name(self):
        """Should not include 'default' in header."""
        msg = format_report([], client_name="default")
        assert "default" not in msg

    def test_multiple_competitors(self):
        """Should format all competitors."""
        results = [
            {"name": "A", "url": "u", "summary": "s", "implication": "i", "recommended_action": "a"},
            {"name": "B", "url": "u", "summary": "s", "implication": "i", "recommended_action": "a"},
        ]
        msg = format_report(results)
        assert "A" in msg
        assert "B" in msg


class TestSlackRetry:
    """Tests for _slack_send_with_retry."""

    def test_success_on_first_try(self):
        """Should return True on immediate success."""
        mock_client = MagicMock()
        mock_client.chat_postMessage = MagicMock()

        result = _slack_send_with_retry(mock_client, "#test", "hello")
        assert result is True
        assert mock_client.chat_postMessage.call_count == 1

    def test_permanent_error_no_retry(self):
        """Should not retry on permanent errors like invalid_auth."""
        mock_client = MagicMock()
        error_response = MagicMock()
        error_response.get = MagicMock(return_value="invalid_auth")
        error_response.__getitem__ = MagicMock(return_value="invalid_auth")
        mock_client.chat_postMessage = MagicMock(
            side_effect=SlackApiError("error", response=error_response)
        )

        result = _slack_send_with_retry(mock_client, "#test", "hello")
        assert result is False
        assert mock_client.chat_postMessage.call_count == 1  # No retries

    @patch("notifiers.slack_notifier.time.sleep")
    def test_transient_error_retries(self, mock_sleep):
        """Should retry on transient errors."""
        mock_client = MagicMock()
        error_response = MagicMock()
        error_response.get = MagicMock(return_value="server_error")
        error_response.headers = {}

        mock_client.chat_postMessage = MagicMock(
            side_effect=SlackApiError("error", response=error_response)
        )

        result = _slack_send_with_retry(mock_client, "#test", "hello")
        assert result is False
        from config.settings import settings
        assert mock_client.chat_postMessage.call_count == settings.SLACK_RETRY_MAX

    @patch("notifiers.slack_notifier.time.sleep")
    def test_rate_limited_respects_retry_after(self, mock_sleep):
        """Should wait for Retry-After duration on rate limit."""
        mock_client = MagicMock()

        rate_response = MagicMock()
        rate_response.get = MagicMock(return_value="ratelimited")
        rate_response.headers = {"Retry-After": "3"}

        success_response = MagicMock()

        mock_client.chat_postMessage = MagicMock(
            side_effect=[
                SlackApiError("rate", response=rate_response),
                success_response,  # Success on retry
            ]
        )

        result = _slack_send_with_retry(mock_client, "#test", "hello")
        assert result is True
        mock_sleep.assert_called_with(3)


class TestSendReport:
    """Tests for send_report."""

    @patch("notifiers.slack_notifier._slack_send_with_retry", return_value=True)
    @patch("notifiers.slack_notifier._get_client")
    @patch("notifiers.slack_notifier._get_channel_id", return_value="#general")
    def test_send_success(self, mock_channel, mock_client, mock_retry):
        """Should return True when send succeeds."""
        result = send_report([])
        assert result is True

    @patch("notifiers.slack_notifier._get_channel_id", return_value=None)
    def test_no_channel_returns_false(self, mock_channel):
        """Should return False when no channel is configured."""
        result = send_report([])
        assert result is False


class TestSendErrorAlert:
    """Tests for send_error_alert."""

    @patch("notifiers.slack_notifier._slack_send_with_retry", return_value=True)
    @patch("notifiers.slack_notifier._get_client")
    @patch("notifiers.slack_notifier._get_channel_id", return_value="#alerts")
    def test_alert_success(self, mock_channel, mock_client, mock_retry):
        """Should return True on successful alert."""
        result = send_error_alert("Something broke")
        assert result is True

    @patch("notifiers.slack_notifier._get_channel_id", return_value=None)
    def test_no_channel_returns_false(self, mock_channel):
        """Should return False when no channel is configured."""
        result = send_error_alert("Something broke")
        assert result is False
