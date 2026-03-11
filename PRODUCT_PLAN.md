# WatchTower AI - Product Plan

## Overview
AI Agent for early-stage startups to monitor competitors daily and deliver structured business intelligence insights automatically.

## Target Audience
- Early-stage startups (Seed / Series A)
- Founders + Product Managers + Marketing teams

## Core Problem
- Startups don't have time to manually track competitors
- Missing critical market changes (new features, pricing, partnerships)
- No structured process for competitive intelligence

---

## Architecture & Flow

```
Scheduler → Config → Scraper → Parser → LLM → Notifier (Slack)
```

| Component | Responsibility |
|-----------|---------------|
| Scheduler | Triggers the agent daily at a configured time |
| Config | Holds competitor list and settings |
| Scraper | Fetches raw HTML from competitor websites (multiple pages) |
| Parser | Cleans HTML and extracts relevant text only |
| LLM | Analyzes content and identifies significant changes |
| Storage | Saves scans and compares to previous day |
| Notifier | Sends structured report to Slack |

---

## Error Handling Strategy

| Error Type | Action |
|------------|--------|
| Site temporarily down | Retry 3 times, then skip page |
| Site structure changed | Alert Marina for maintenance |
| LLM API failure | Log error, skip analysis, notify client |
| Slack API failure | Log error, retry once |

---

## ✅ COMPLETED (Phase 1 - Project Structure)

- ✅ agents/ - Core agent logic
- ✅ scrapers/ - Web scraping module
- ✅ parsers/ - HTML cleaning and extraction
- ✅ llm/ - LLM API integration
- ✅ notifiers/ - Slack notification module
- ✅ scheduler/ - Job scheduling
- ✅ config/ - Competitors list and settings
- ✅ logs/ - Error and run logging
- ✅ tests/ - Unit and integration tests
- ✅ competitors.json - Competitor list with name, URLs, active status
- ✅ .env - API keys and secrets
- ✅ .gitignore - Protect sensitive files
- ✅ requirements.txt - Project dependencies
- ✅ README.md - Project documentation
- ✅ PRODUCT_PLAN.md - This file

---

## ✅ COMPLETED (Phase 2 - Scraper & Parser)

- ✅ Fetch HTML from multiple pages per competitor (async)
- ✅ Handle request errors (timeout, blocked, 404)
- ✅ Retry logic (3 attempts before marking as failed)
- ✅ follow_redirects support (301 handling)
- ✅ Strip HTML tags and extract clean text
- ✅ Focus on key sections: features, pricing, announcements
- ✅ Ignore: navigation, footer, design elements

---

## ✅ COMPLETED (Phase 3 - LLM Integration)

- ✅ Connected to Anthropic Claude API
- ✅ Prompt engineering for change detection
- ✅ Identifies significant changes (features, pricing, partnerships)
- ✅ Ignores insignificant changes (design, minor text edits)
- ✅ Memory & comparison - compares today vs yesterday

---

## ✅ COMPLETED (Phase 4 - Slack Notifier)

- ✅ Connected to Slack API
- ✅ Sends structured daily report to designated channel
- ✅ Error alerts when something fails

---

## ✅ COMPLETED (Phase 5 - Scheduler)

- ✅ Daily run time configured via .env
- ✅ APScheduler integration
- ✅ Logging of each run (success / failure)

---

## ✅ COMPLETED (Phase 6 - Storage & Memory)

- ✅ Saves scan results to logs/previous_scans.json
- ✅ Loads previous scan on next run
- ✅ LLM compares today vs yesterday for real change detection

---

## ✅ COMPLETED (Phase 7 - Logging)

- ✅ Logs to terminal and to logs/watchtower.log
- ✅ Rotating log files (max 5MB, 3 backups)

---

## 🚧 TODO (Phase 8 - Dashboard)

### Visual Dashboard (Future Version)
- [ ] Web interface for viewing reports history
- [ ] Competitor comparison charts
- [ ] Trend analysis over time
- [ ] React + Tailwind CSS

---

## Technology Stack

### Core
- **Python 3.12**
- **APScheduler** - Job scheduling
- **BeautifulSoup4** - HTML parsing
- **HTTPX** - Async web scraping

### AI
- **Anthropic Claude API** - Content analysis and change detection

### Notifications
- **Slack SDK** - Report delivery

### Configuration
- **JSON** - Competitor configuration
- **python-dotenv** - Environment variable management

### Future (Dashboard)
- **React** - Frontend framework
- **Tailwind CSS** - Styling

---

## Business Model

- **Setup fee** - One-time agent build per client
- **Monthly retainer** - Maintenance, updates, and improvements

---

## Developer

**Marina Kurland** - AI Agent Developer
- Specialization: Custom intelligent agents for early-stage startups
- Stack: Python, LLM APIs, Slack integrations

---

**Last Updated:** March 5, 2026
**Version:** 1.0.0 (Production Ready)