"""
Tests for llm/analyzer.py

Covers: analyze_competitor, analyze_all_competitors, prompt construction,
error handling, industry parameter.
"""

import pytest
from unittest.mock import MagicMock, patch

from llm.analyzer import analyze_competitor, analyze_all_competitors


def _make_parsed(name="TestCorp", text="Some content"):
    """Helper to build a parsed competitor result with all required fields."""
    return {
        "name": name,
        "url": f"https://{name.lower()}.com",
        "text": text,
        "status": "success",
    }


class TestAnalyzeCompetitor:
    """Tests for single-competitor LLM analysis."""

    @pytest.mark.asyncio
    async def test_successful_analysis(self):
        """Should return parsed analysis dict on success."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = (
            "SIGNIFICANT_CHANGE: YES\n"
            "SUMMARY: New pricing page launched\n"
            "IMPLICATION: May undercut our pricing\n"
            "RECOMMENDED_ACTION: Review our pricing strategy"
        )

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)

        with patch("llm.analyzer._get_client", return_value=mock_client), \
             patch("llm.analyzer.get_previous_scan", return_value=None), \
             patch("llm.analyzer.save_scan"):
            result = await analyze_competitor(_make_parsed())

        assert result["name"] == "TestCorp"
        assert result["status"] == "success"
        assert result["significant_change"] is True

    @pytest.mark.asyncio
    async def test_handles_no_significant_change(self):
        """Should handle 'NO' significant change response."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = (
            "SIGNIFICANT_CHANGE: NO\n"
            "SUMMARY: No significant changes detected\n"
            "IMPLICATION: N/A\n"
            "RECOMMENDED_ACTION: N/A"
        )

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)

        with patch("llm.analyzer._get_client", return_value=mock_client), \
             patch("llm.analyzer.get_previous_scan", return_value=None), \
             patch("llm.analyzer.save_scan"):
            result = await analyze_competitor(_make_parsed())

        assert result["significant_change"] is False

    @pytest.mark.asyncio
    async def test_failed_status_skips_analysis(self):
        """Should skip analysis when parsed result has 'failed' status."""
        result = await analyze_competitor({
            "name": "FailCorp", "url": "u", "text": "", "status": "failed"
        })
        assert result["status"] == "failed"
        assert "unavailable" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_industry_in_prompt(self):
        """Should include industry context in the LLM prompt."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = (
            "SIGNIFICANT_CHANGE: NO\nSUMMARY: No changes\n"
            "IMPLICATION: N/A\nRECOMMENDED_ACTION: N/A"
        )

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)

        with patch("llm.analyzer._get_client", return_value=mock_client), \
             patch("llm.analyzer.get_previous_scan", return_value=None), \
             patch("llm.analyzer.save_scan"):
            await analyze_competitor(_make_parsed(), industry="cybersecurity")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "cybersecurity" in call_kwargs.get("system", "").lower()

    @pytest.mark.asyncio
    async def test_handles_api_error(self):
        """Should handle API errors gracefully and return failed result."""
        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(side_effect=Exception("API timeout"))

        with patch("llm.analyzer._get_client", return_value=mock_client), \
             patch("llm.analyzer.get_previous_scan", return_value=None):
            result = await analyze_competitor(_make_parsed())

        assert result["status"] == "failed"
        assert "failed" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_with_previous_scan(self):
        """Should include previous content when comparison data exists."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = (
            "SIGNIFICANT_CHANGE: YES\nSUMMARY: Pricing changed\n"
            "IMPLICATION: Review needed\nRECOMMENDED_ACTION: Act now"
        )

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)

        with patch("llm.analyzer._get_client", return_value=mock_client), \
             patch("llm.analyzer.get_previous_scan", return_value="Old content"), \
             patch("llm.analyzer.save_scan"):
            result = await analyze_competitor(_make_parsed(text="New content"))

        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_msg = call_kwargs["messages"][0]["content"]
        assert "YESTERDAY" in user_msg


class TestAnalyzeAllCompetitors:
    """Tests for batch competitor analysis."""

    @pytest.mark.asyncio
    async def test_empty_list(self):
        """Should return empty list for empty input."""
        result = await analyze_all_competitors([])
        assert result == []

    @pytest.mark.asyncio
    async def test_filters_non_significant(self):
        """Should only return competitors with significant changes."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = (
            "SIGNIFICANT_CHANGE: NO\nSUMMARY: No changes\n"
            "IMPLICATION: N/A\nRECOMMENDED_ACTION: N/A"
        )

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)

        with patch("llm.analyzer._get_client", return_value=mock_client), \
             patch("llm.analyzer.get_previous_scan", return_value=None), \
             patch("llm.analyzer.save_scan"):
            results = await analyze_all_competitors([_make_parsed()])

        assert len(results) == 0  # No significant changes

    @pytest.mark.asyncio
    async def test_passes_industry(self):
        """Should pass industry parameter to each competitor analysis."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = (
            "SIGNIFICANT_CHANGE: NO\nSUMMARY: No changes\n"
            "IMPLICATION: N/A\nRECOMMENDED_ACTION: N/A"
        )

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)

        with patch("llm.analyzer._get_client", return_value=mock_client), \
             patch("llm.analyzer.get_previous_scan", return_value=None), \
             patch("llm.analyzer.save_scan"):
            await analyze_all_competitors([_make_parsed()], industry="fintech")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "fintech" in call_kwargs.get("system", "").lower()
