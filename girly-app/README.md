# Girly 🌸 — Menstrual Cycle Tracker

A private, reassuring cycle companion built from the Stitch design export
(`../stitch_girly_menstrual_cycle_tracker/`) with **Python, JavaScript, CSS
and HTML** — no frameworks, no external dependencies (standard library only).

## Quick start

```bash
cd girly-app
python3 server.py
```

Then open **http://localhost:8080**.

The single `server.py` process runs everything: it serves the frontend and
REST API on port 8080 and starts the companion service
(`assistant/server.py`) in a background thread on port 3000.

## The companion (assistant)

The chat answers questions across three areas, all offline by default:

- **Menstrual health** — cycle basics, first periods, cramps, PMS/PMDD, PCOS,
  endometriosis, discharge, infections, pregnancy & contraception, TSS, …
- **General health** — sleep, stress, nutrition, hydration, weight, skin,
  puberty, fever, supplements, …
- **Personal hygiene** — showering, intimate care, body odour, shaving, hair,
  dental, feet, nails, handwashing, …

Plain greetings ("hi", "hello") get a simple hello back — no extra info
attached. Questions the knowledge base doesn't recognise fall through to an
optional AI layer:

```bash
export GIRLY_AI_API_KEY=sk-...   # or ANTHROPIC_API_KEY
python3 server.py                # unmatched questions now go to the AI
```

Without a key the companion stays fully offline and answers from the built-in
topics only. With a key, the user's question and minimal cycle context (day
and phase — never names or logs) are sent to the AI service. `GIRLY_AI_MODEL`
(default `claude-sonnet-5`) and `GIRLY_AI_API_URL` can override the model and
endpoint.

## Demo accounts

| Email | Password | Notes |
|---|---|---|
| `maya@example.com` | `password123` | Tracking mode, 3 cycles of history |
| `chloe.v@example.com` | `password123` | Learn mode (no period yet) |
| `admin@girly.app` | `admin123` | Root operator — admin console |

## What's inside

```
girly-app/
├── server.py             # entrypoint: routing + static serving + companion thread
├── store.py              # JSON persistence, models, demo seed
├── auth.py               # PBKDF2-SHA256 password hashing, session tokens
├── handlers.py           # REST API (auth, logs, predictions, admin, chat proxy)
├── cycle.py              # cycle-day / phase / fertile-window prediction math
├── mailer.py             # optional SMTP for admin password resets
├── test_cycle.py         # prediction & store tests (python -m unittest)
├── test_assistant.py     # companion knowledge base & AI-layer tests
├── assistant/
│   └── server.py         # Python companion (knowledge base, optional AI layer, /health)
├── web/
│   ├── index.html        # registration & onboarding + sign-in
│   ├── tracker.html      # cycle ring, stats, phase calendar, quick-log sheets
│   ├── learn.html        # education modules, first-period prep, ask bar
│   ├── assistant.html    # chat with the companion
│   ├── profile.html      # profile picture, change password, sign out
│   ├── admin.html        # stats bento, system health, member directory, audit
│   ├── css/girly.css     # design system (tokens, pills, cards, dark mode)
│   ├── js/*.js           # vanilla JS per page + shared helpers
│   └── assets/logo.svg
├── data/girly.json       # created & seeded automatically on first run
└── PROGRESS.md           # build progress tracker
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
