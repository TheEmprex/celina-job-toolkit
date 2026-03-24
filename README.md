# Celina's Job Toolkit

A personal job search command center — find the right people at any company, get ready-to-use LinkedIn messages, track your applications, and get notified about new jobs.

Built for networking-first job seekers targeting foundations, NGOs, and international organizations.

## What it does

1. **Type a role** → `Program Coordinator at UNICEF`
2. **Get real contacts** → 25 verified LinkedIn profiles (recruiters, managers, team members)
3. **Copy messages** → 3 styles per person (Professional, Friendly, Bold) — all under 300 chars
4. **Track everything** → Dashboard with weekly progress, follow-up reminders, application tracker

## Features

- **People Finder** — searches the web for real employees, verifies they work at the company, filters out ex-employees
- **Smart Messages** — 3 LinkedIn connection request variants + follow-up messages per person
- **Match Score** — compares your profile against the job description (0-100%)
- **Cover Letter** — auto-generated, personalized with your profile data
- **Salary Research** — estimated salary range with sources
- **Interview Prep** — real questions from Glassdoor + behavioral prep
- **Application Tracker** — Kanban board (Applied → Contacted → Interviewing → Offered)
- **Job Scanner** — auto-searches for new jobs every hour, sends push notifications via ntfy
- **CV Parser** — paste your resume, auto-fills your entire profile
- **PDF/CSV Export** — download cover letters as PDF, contacts as CSV

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/celina-job-toolkit.git
cd celina-job-toolkit
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:3000

## First steps

1. Go to **Profile** → paste your CV → profile auto-fills
2. Go to **Search** → type a role like `Program Officer at Red Cross`
3. Copy messages, open LinkedIn profiles, start networking
4. Check **Dashboard** for your weekly progress

## Pages

| Page | URL | What it does |
|---|---|---|
| Search | `/` | Find people and generate messages |
| Dashboard | `/dashboard` | Weekly progress, follow-ups, job leads |
| Tracker | `/tracker` | Kanban board for applications |
| Profile | `/profile/page` | Your info (CV paste to auto-fill) |

## Tech

- Python/Flask backend with SSE streaming
- Vanilla JS frontend (no frameworks)
- SQLite for application tracking
- Web search via DuckDuckGo + Startpage
- Push notifications via ntfy.sh

## Requirements

- Python 3.10+
- No API keys needed (optional: OpenAI for AI cover letters, Hunter.io for verified emails)
