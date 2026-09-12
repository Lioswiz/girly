# Girly 🌸 — Menstrual Cycle Tracker

A private, reassuring cycle companion built from the Stitch design export
(`../stitch_girly_menstrual_cycle_tracker/`) with **Go, Python, JavaScript,
CSS and HTML** — no frameworks, no external dependencies.

## Quick start

```bash
cd girly-app
./run.sh
```

Then open **http://localhost:8080**.

`run.sh` starts two services:

| Service | Tech | Port | What it does |
|---|---|---|---|
| App server | Go (stdlib) | 8080 | Serves the frontend, REST API, auth & sessions, cycle predictions, admin endpoints |
| Companion | Python (stdlib) | 3000 | The in-app AI assistant: cycle-aware knowledge-base chat + health probe |

To enable general Gemini Flash answers, set `GEMINI_API_KEY` before starting the
companion. The local health knowledge base remains available as a fallback.

```powershell
$env:GEMINI_API_KEY = "your-key"
$env:GEMINI_MODEL = "gemini-2.5-flash"
py assistant/server.py
```

## What's inside

```
girly-app/
├── main.go              # entrypoint: routing + static serving
├── store.go             # JSON persistence and models
├── auth.go              # PBKDF2-SHA256 password hashing, session tokens
├── handlers.go          # REST API (auth, logs, predictions, admin, chat proxy)
├── cycle.go             # cycle-day / phase / fertile-window prediction math
├── assistant/
│   └── server.py        # Python companion (chat knowledge base + /health)
├── web/
│   ├── index.html       # registration & onboarding + sign-in
│   ├── tracker.html     # cycle ring, stats, phase calendar, quick-log sheets
│   ├── learn.html       # education modules, first-period prep, ask bar
│   ├── assistant.html   # chat with the companion
│   ├── admin.html       # stats bento, system health, member directory, audit
│   ├── css/girly.css    # design system (tokens, pills, cards, dark mode)
│   ├── js/*.js          # vanilla JS per page + shared helpers
│   └── assets/logo.svg
├── data/girly.json      # created & seeded automatically on first run
├── run.sh               # starts Python + Go together
└── PROGRESS.md          # build progress tracker
```

## How predictions work

- Girly averages the gaps between your logged period starts (clamped to
  21–45 days; falls back to 28) → **average cycle length**
- Your current **cycle day** counts from your latest logged start
- **Next period** = latest start + average cycle length, shown with a ±2 day
  prediction window on the calendar
- **Ovulation** ≈ 14 days before the projected next period; the **fertile
  window** spans the 5 days before that plus ovulation day

## Privacy

All data lives in a single local JSON file (`data/girly.json`). Passwords are
hashed with PBKDF2-SHA256 (12,000 iterations). Sessions are HttpOnly cookies.
Delete the data file + restart to reset everything.

*Girly gives estimates based on learned cycle patterns and is not medical
advice.*
