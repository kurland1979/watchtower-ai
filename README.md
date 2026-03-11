# WatchTower AI

AI-powered competitive intelligence agent for early-stage startups. Monitors competitor websites daily, detects significant changes using LLM analysis, and delivers structured reports to Slack.

## How It Works

WatchTower runs a daily pipeline:

1. **Scheduler** triggers the agent at a configured time (default: 8:00 AM)
2. **Scraper** fetches HTML from competitor websites (async with retry logic)
3. **Parser** extracts clean text from relevant sections (headings, paragraphs, lists)
4. **LLM Analyzer** compares today's content with yesterday's using Claude Haiku — detects new features, pricing changes, partnerships
5. **Notifier** sends a structured report to Slack with findings and recommendations

## Installation

```bash
git clone https://github.com/kurland1979/watchtower-ai.git
cd WatchTower-AI
pip install -r requirements.txt
```

## Configuration

### Environment Variables

Copy `.env.example` or create `.env` with:

```
ANTHROPIC_API_KEY=your-anthropic-api-key
SLACK_BOT_TOKEN=your-slack-bot-token
SLACK_CHANNEL_ID=your-slack-channel-id
RUN_HOUR=8
RUN_MINUTE=0
```

### Competitor List

Edit `config/competitors.json` to add your competitors:

```json
{
  "industry": "your industry here",
  "competitors": [
    {
      "name": "CompetitorName",
      "url": "https://competitor.com",
      "pages": [
        "https://competitor.com/",
        "https://competitor.com/pricing",
        "https://competitor.com/products"
      ],
      "active": true
    }
  ]
}
```

The `industry` field is injected into the LLM prompt so the analysis is tailored to your market.

## Running

```bash
python main.py
```

The agent will start the scheduler and run daily at the configured time.

## Running Tests

```bash
pytest tests/ -v
```

## Slack Output Example

```
🔍 WatchTower Daily Report

🏢 CrowdStrike
📌 What changed: New AI-powered threat detection module announced
⚠️ Implication: Direct competition with our core detection feature
✅ Recommended action: Schedule product review to assess feature gap
🔗 https://www.crowdstrike.com
─────────────────────
```

## Project Structure

```
WatchTower-AI/
├── agents/             # Core agent logic and storage
├── scrapers/           # Async web scraping with retry
├── parsers/            # HTML cleaning and text extraction
├── llm/                # Claude API integration and analysis
├── notifiers/          # Slack report delivery
├── scheduler/          # APScheduler daily job
├── config/             # Competitor list and settings
├── logs/               # Run logs and scan database
├── tests/              # Unit tests
├── main.py             # Entry point
└── requirements.txt    # Dependencies
```

## Tech Stack

- **Python 3.12** — Core language
- **HTTPX** — Async HTTP client with retry logic
- **BeautifulSoup4** — HTML parsing
- **Anthropic Claude API** — LLM-powered change detection
- **Slack SDK** — Report delivery
- **APScheduler** — Job scheduling
- **SQLite** — Scan history storage

## Developer

**Marina Kurland** — AI Agent Developer
