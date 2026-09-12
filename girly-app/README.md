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

## Deploy on Render

Create a Docker web service from this repository with the root directory set to
`.` (the repository root). Do not set it to `girly`; that directory does not
exist in the repository. Render uses the included `Dockerfile` and `render.yaml`.

The service starts both the Go app and Python companion, binds to Render's
`PORT`, and persists runtime data under `/app/data`.

`run.sh` starts two services:

| Service | Tech | Port | What it does |
|---|---|---|---|
| App server | Go (stdlib) | 8080 | Serves the frontend, REST API, auth & sessions, cycle predictions, admin endpoints |
| Companion | Python (stdlib) | 3000 | The in-app AI assistant: cycle-aware knowledge-base chat + health probe |

## Demo accounts

| Email | Password | Notes |
|---|---|---|
| `maya@example.com` | `password123` | Tracking mode, 3 cycles of history |
| `chloe.v@example.com` | `password123` | Learn mode (no period yet) |
| `admin@girly.app` | `admin123` | Root operator — admin console |

## What's inside

```
girly-app/
├── main.go              # entrypoint: routing + static serving
├── store.go             # JSON persistence, models, demo seed
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
