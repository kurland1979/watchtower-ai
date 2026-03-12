# WatchTower AI

AI-powered competitive intelligence platform for startups. Monitors competitor websites daily, detects significant changes using LLM analysis, and delivers structured reports to Slack. Includes a real-time dashboard and a multi-tenant Admin API for managing multiple clients.

## How It Works

WatchTower runs a daily pipeline:

1. **Scheduler** triggers the agent at a configured time (default: 8:00 AM)
2. **Scraper** fetches HTML from competitor websites (async with retry logic and circuit breaker)
3. **Parser** extracts clean text from relevant sections (headings, paragraphs, lists)
4. **Text Chunker** classifies content blocks by type (pricing, features, announcements) and prioritizes within token budget
5. **LLM Analyzer** compares today's content with yesterday's using Claude Haiku — detects new features, pricing changes, partnerships
6. **Notifier** sends a structured report to Slack with findings and recommendations
7. **Heartbeat** tracks system health per client for monitoring

## Features

- **Multi-Client Support** — Each client gets a separate config file with its own competitors, industry, and Slack channel
- **Admin API** — Full CRUD endpoints for managing clients and competitors remotely, no need to edit JSON files on the server
- **Dashboard** — React-based SPA with 6 tabs: System Health, Trend Analysis, Scan History, Daily Comparison, Weekly Report, Monthly Report
- **Report API** — Daily / Weekly / Monthly comparison endpoints with scan-by-scan diffs and change percentages
- **Input Validation** — SSRF prevention, SQL injection blocking, duplicate detection on all endpoints
- **Circuit Breaker** — Automatic failure isolation: if a site is down, the agent skips it instead of retrying endlessly
- **174 Unit Tests** across 18 test modules

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
WATCHTOWER_API_KEY=your-api-key-for-dashboard
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5000,null
```

### Client Configuration

Client configs live in `config/clients/`. Each file defines one client with its competitors:

```json
{
  "client_name": "cybersecurity_startup",
  "industry": "cybersecurity",
  "slack_channel_id": "C0AHT0M0PD4",
  "slack_bot_token": "",
  "competitors": [
    {
      "name": "CrowdStrike",
      "url": "https://www.crowdstrike.com",
      "pages": [
        "https://www.crowdstrike.com/en-us/",
        "https://www.crowdstrike.com/en-us/products/"
      ],
      "active": true,
      "js_render": false
    }
  ]
}
```

You can manage clients via the Admin API instead of editing files manually (see API section below).

## Running

### Start the Agent (Daily Scans)

```bash
python main.py
```

The agent starts the scheduler and runs daily at the configured time.

### Start the Dashboard

```bash
python dashboard/api.py
```

Open `http://localhost:5000` in your browser. The dashboard and API are served from the same Flask server (no CORS issues).

## Dashboard

The dashboard provides 6 tabs:

- **System Health** — Live status of each client and competitor (last scan time, health badges)
- **Trend Analysis** — Change trends over configurable time periods with severity indicators
- **Scan History** — Browsable scan archive per competitor with text previews
- **Daily Comparison** — Today vs. yesterday for every competitor: change %, size diff, status badges
- **Weekly Report** — 7-day change chart and detail table per competitor
- **Monthly Report** — 30-day change chart and detail table per competitor

## API Reference

All protected endpoints require: `Authorization: Bearer <your-api-key>`

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | System health (no auth) |
| GET | `/api/competitors` | List tracked competitors |
| GET | `/api/scans/<name>` | Scan history for a competitor |
| GET | `/api/trends` | Trend analysis for all competitors |
| GET | `/api/trends/<name>` | Trend analysis for one competitor |

### Report Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/reports/daily` | Today vs. yesterday for all competitors |
| GET | `/api/reports/weekly` | 7-day comparison for all competitors |
| GET | `/api/reports/weekly/<name>` | 7-day comparison for one competitor |
| GET | `/api/reports/monthly` | 30-day comparison for all competitors |
| GET | `/api/reports/monthly/<name>` | 30-day comparison for one competitor |

### Admin Endpoints (Client Management)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/clients` | List all clients |
| GET | `/api/admin/clients/<name>` | Get a specific client |
| POST | `/api/admin/clients` | Create a new client |
| PUT | `/api/admin/clients/<name>` | Update an existing client |
| DELETE | `/api/admin/clients/<name>` | Delete a client |
| POST | `/api/admin/clients/<name>/competitors` | Add a competitor |
| DELETE | `/api/admin/clients/<name>/competitors/<comp>` | Remove a competitor |

## Running Tests

```bash
pytest tests/ -v
```

174 tests across 18 modules covering all agents, API endpoints, validation, and integration.

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
├── agents/             # Core agent logic, storage, heartbeat, trend analyzer
├── scrapers/           # Async web scraping with retry and circuit breaker
├── parsers/            # HTML cleaning, text extraction, smart chunking
├── llm/                # Claude API integration and change analysis
├── notifiers/          # Slack report delivery
├── scheduler/          # APScheduler daily job
├── config/             # Settings and client configurations
│   ├── clients/        # Per-client JSON configs (one file per client)
│   └── settings.py     # Global settings with environment variable support
├── dashboard/          # Flask API server + React SPA dashboard
│   ├── api.py          # REST API (core + reports + admin + dashboard serving)
│   └── index.html      # React dashboard with 6 tabs
├── utils/              # Input validation (URL, name, SSRF prevention)
├── logs/               # Run logs and SQLite scan database
├── tests/              # 174 unit tests across 18 modules
├── main.py             # Entry point
└── requirements.txt    # Dependencies
```

## Tech Stack

- **Python 3.12** — Core language
- **Flask** — REST API and dashboard serving
- **HTTPX** — Async HTTP client with retry logic
- **BeautifulSoup4** — HTML parsing
- **Anthropic Claude API** — LLM-powered change detection
- **Slack SDK** — Report delivery
- **APScheduler** — Job scheduling
- **SQLite** — Scan history storage
- **React + Tailwind + Chart.js** — Dashboard UI

## Developer

**Marina Kurland** — AI Agent Developer
