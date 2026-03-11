from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

# Sections we want to focus on
RELEVANT_TAGS = ["h1", "h2", "h3", "p", "li"]

# Sections we want to ignore
IGNORE_TAGS = ["nav", "footer", "header", "script", "style", "img"]


def parse_competitor(scrape_result: dict) -> dict:
    """
    Parses raw HTML from a scrape result.
    Extracts clean, relevant text only.
    Returns a dict with name, url, text content, and status.
    """
    name = scrape_result["name"]
    url = scrape_result["url"]

    if scrape_result["status"] == "failed" or not scrape_result["html"]:
        logger.warning(f"Skipping parse for {name} - no HTML available")
        return {
            "name": name,
            "url": url,
            "text": None,
            "status": "failed"
        }

    try:
        soup = BeautifulSoup(scrape_result["html"], "html.parser")

        # Remove irrelevant sections
        for tag in IGNORE_TAGS:
            for element in soup.find_all(tag):
                element.decompose()

        # Extract relevant text
        extracted = []
        for tag in RELEVANT_TAGS:
            for element in soup.find_all(tag):
                text = element.get_text(strip=True)
                if text:
                    extracted.append(text)

        clean_text = "\n".join(extracted)

        logger.info(f"Parsed {name} - extracted {len(extracted)} text blocks")

        return {
            "name": name,
            "url": url,
            "text": clean_text,
            "status": "success"
        }

    except Exception as e:
        logger.error(f"Failed to parse {name}: {e}")
        return {
            "name": name,
            "url": url,
            "text": None,
            "status": "failed"
        }


def parse_all_competitors(scrape_results: list) -> list:
    """
    Parses all scrape results.
    Returns a list of parsed results.
    """
    return [parse_competitor(result) for result in scrape_results]