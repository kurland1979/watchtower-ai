import anthropic
import asyncio
import json
import logging
import os
from agents.storage import get_previous_scan, save_scan
from parsers.text_chunker import smart_chunk

logger = logging.getLogger(__name__)

_client = None

# Config path for loading industry context
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "competitors.json")


def _get_client() -> anthropic.Anthropic:
    """Lazy initialization of Anthropic client — only created when first needed."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def _load_industry() -> str:
    """Loads the industry field from competitors.json config."""
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
        return data.get("industry", "technology startup")
    except Exception:
        return "technology startup"


def _build_system_prompt(industry: str) -> str:
    """Builds the system prompt dynamically based on industry context."""
    return f"""You are a competitive intelligence analyst for a {industry}.
Your job is to compare TODAY's competitor website content with YESTERDAY's content and identify significant changes.

Focus ONLY on:
- New features or product launches
- Pricing changes
- Partnership or integration announcements
- Major company announcements

Ignore completely:
- Design or layout changes
- Minor text edits
- Blog posts unrelated to product

If no previous content is provided, analyze the current content for notable information.

Respond in this exact format:
SIGNIFICANT_CHANGE: YES or NO
SUMMARY: (one sentence summary of what changed, or "No significant changes detected")
IMPLICATION: (one sentence on what this means for us, or "N/A")
RECOMMENDED_ACTION: (one sentence recommendation, or "N/A")
"""


async def analyze_competitor(parsed_result: dict, industry: str | None = None) -> dict:
    """
    Sends parsed competitor text to Claude for analysis.
    Compares with previous scan if available.

    Args:
        parsed_result: Dict with name, url, text, status.
        industry: Industry context for the LLM prompt. If None, loads from config.

    Returns a dict with name, url, analysis, and status.
    """
    name = parsed_result["name"]
    url = parsed_result["url"]

    if parsed_result["status"] == "failed" or not parsed_result["text"]:
        logger.warning(f"Skipping analysis for {name} - no text available")
        return {
            "name": name,
            "url": url,
            "significant_change": False,
            "summary": "Data unavailable - scraping failed",
            "implication": "N/A",
            "recommended_action": "Check scraper logs",
            "status": "failed"
        }

    current_text = parsed_result["text"]
    previous_text = get_previous_scan(name)

    # Smart chunking — prioritizes pricing, features, announcements over general text
    current_chunk = smart_chunk(current_text, char_budget=3000)

    if previous_text:
        previous_chunk = smart_chunk(previous_text, char_budget=3000)
        user_message = f"""Compare these two versions of {name}'s website content and identify significant changes.

YESTERDAY'S CONTENT:
{previous_chunk}

TODAY'S CONTENT:
{current_chunk}"""
    else:
        # First scan gets a larger budget — no comparison needed
        current_chunk_large = smart_chunk(current_text, char_budget=5000)
        user_message = f"""Analyze this competitor website content for {name} (first scan - no previous data):

{current_chunk_large}"""

    try:
        logger.info(f"Analyzing {name} with Claude")

        client = _get_client()
        # Use provided industry (multi-client) or fall back to config file
        if industry is None:
            industry = _load_industry()
        system_prompt = _build_system_prompt(industry)

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        )

        response_text = message.content[0].text
        parsed = _parse_response(response_text)

        save_scan(name, current_text)

        logger.info(f"Analysis complete for {name} - significant change: {parsed['significant_change']}")

        return {
            "name": name,
            "url": url,
            **parsed,
            "status": "success"
        }

    except Exception as e:
        logger.error(f"LLM analysis failed for {name}: {e}")
        return {
            "name": name,
            "url": url,
            "significant_change": False,
            "summary": "Analysis failed",
            "implication": "N/A",
            "recommended_action": "Check LLM logs",
            "status": "failed"
        }


def _parse_response(response_text: str) -> dict:
    """
    Parses the structured response from Claude into a dict.
    """
    result = {
        "significant_change": False,
        "summary": "N/A",
        "implication": "N/A",
        "recommended_action": "N/A"
    }

    for line in response_text.strip().split("\n"):
        if line.startswith("SIGNIFICANT_CHANGE:"):
            result["significant_change"] = "YES" in line.upper()
        elif line.startswith("SUMMARY:"):
            result["summary"] = line.replace("SUMMARY:", "").strip()
        elif line.startswith("IMPLICATION:"):
            result["implication"] = line.replace("IMPLICATION:", "").strip()
        elif line.startswith("RECOMMENDED_ACTION:"):
            result["recommended_action"] = line.replace("RECOMMENDED_ACTION:", "").strip()

    return result


async def analyze_all_competitors(parsed_results: list, industry: str | None = None) -> list:
    """
    Analyzes all parsed competitor results concurrently using asyncio.gather.
    Returns only competitors with significant changes.

    Args:
        parsed_results: List of parsed competitor dicts.
        industry: Industry context passed to each analysis call.
    """
    tasks = [analyze_competitor(result, industry=industry) for result in parsed_results]
    all_results = await asyncio.gather(*tasks)

    significant = [r for r in all_results if r["significant_change"]]

    logger.info(f"Analysis complete - {len(significant)}/{len(all_results)} competitors had significant changes")

    return significant
