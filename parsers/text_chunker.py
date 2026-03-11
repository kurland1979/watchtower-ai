"""
Smart Text Chunker for LLM Analysis.

Instead of blindly cutting text at a character limit (e.g. text[:3000]),
this module prioritizes high-value sections — pricing, features, announcements —
and builds a chunk that fits within a token budget while preserving the most
important content for competitive intelligence.

Architecture:
    1. Classify each text block into a priority section (pricing > features > announcements > general)
    2. Sort blocks by priority (highest first)
    3. Build the final chunk by adding blocks until the character budget is reached
    4. Always preserve complete blocks — never cut a sentence in the middle
"""

import re
import logging

logger = logging.getLogger(__name__)

# --- Section Priority Definitions ---
# Higher priority = more important for competitive intelligence
SECTION_PRIORITIES = {
    "pricing": 4,
    "features": 3,
    "announcements": 2,
    "general": 1,
}

# Keywords used to classify each text block into a section
SECTION_KEYWORDS = {
    "pricing": [
        "pricing", "price", "cost", "plan", "subscription", "tier",
        "enterprise", "free trial", "per month", "per year", "annual",
        "discount", "billing", "quote", "starter", "professional",
        "pay", "payment", "$", "€", "£",
    ],
    "features": [
        "feature", "capability", "integration", "platform", "module",
        "dashboard", "analytics", "automation", "api", "sdk",
        "detection", "protection", "monitoring", "response",
        "endpoint", "cloud", "deploy", "scale",
    ],
    "announcements": [
        "announce", "new", "launch", "release", "update",
        "partnership", "partner", "acquisition", "acquired",
        "introducing", "now available", "coming soon",
        "press release", "newsroom",
    ],
}

# Default character budget per text chunk sent to the LLM
DEFAULT_CHAR_BUDGET = 3000


def classify_block(text: str) -> str:
    """
    Classifies a text block into a section based on keyword matching.
    Returns the section name with the highest keyword match count.
    If no keywords match, returns 'general'.
    """
    text_lower = text.lower()
    scores = {}

    for section, keywords in SECTION_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[section] = score

    if not scores:
        return "general"

    return max(scores, key=scores.get)


def smart_chunk(text: str, char_budget: int = DEFAULT_CHAR_BUDGET) -> str:
    """
    Builds an optimized text chunk for LLM analysis.

    Instead of text[:char_budget], this function:
    1. Splits the text into individual blocks (lines/paragraphs)
    2. Classifies each block by section (pricing, features, announcements, general)
    3. Sorts blocks by priority (pricing first, general last)
    4. Fills the chunk up to char_budget, preserving complete blocks

    Args:
        text: The full extracted text from a competitor website.
        char_budget: Maximum number of characters for the output chunk.

    Returns:
        A string containing the most important content, up to char_budget characters.
    """
    if not text or not text.strip():
        return ""

    # Split into blocks — each line that has meaningful content
    raw_blocks = text.strip().split("\n")
    blocks = [b.strip() for b in raw_blocks if b.strip()]

    if not blocks:
        return ""

    # Classify and tag each block
    classified = []
    for block in blocks:
        section = classify_block(block)
        priority = SECTION_PRIORITIES.get(section, 1)
        classified.append({
            "text": block,
            "section": section,
            "priority": priority,
        })

    # Sort by priority (highest first), preserve original order within same priority
    classified.sort(key=lambda b: b["priority"], reverse=True)

    # Build chunk within budget
    selected = []
    current_length = 0

    for item in classified:
        block_length = len(item["text"]) + 1  # +1 for newline separator
        if current_length + block_length > char_budget:
            continue  # Skip this block — doesn't fit
        selected.append(item)
        current_length += block_length

    if not selected:
        # Fallback: if no complete block fits, take the first block truncated
        return blocks[0][:char_budget]

    # Re-sort selected blocks by their original order for coherent reading
    # We use the original index to restore order
    block_to_index = {b["text"]: i for i, b in enumerate(classified)}
    selected.sort(key=lambda b: block_to_index.get(b["text"], 0))

    chunk = "\n".join(item["text"] for item in selected)

    logger.info(
        f"Smart chunking: {len(blocks)} blocks → {len(selected)} selected "
        f"({current_length}/{char_budget} chars used)"
    )

    return chunk
