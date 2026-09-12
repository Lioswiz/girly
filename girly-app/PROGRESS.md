# 🌸 Girly — Menstrual Cycle Tracker · Build Progress

A full-stack implementation of the Stitch design export
(`../stitch_girly_menstrual_cycle_tracker/`) using **Go + Python + JavaScript + CSS + HTML**.

## Architecture

| Layer | Tech | Role |
|---|---|---|
| Backend (core) | **Go** (stdlib only, `:8080`) | Serves the frontend, REST API: auth/sessions, users, cycle & symptom logs, cycle predictions, admin console endpoints |
| AI service | **Python** (stdlib only, `:3000`) | "Girly companion" chat assistant — knowledge-base replies with cycle-day context, plus `/health` for the admin system-health panel |
| Frontend | **HTML + CSS + JS** (vanilla, no frameworks) | 5 pages: register/sign-in, tracker dashboard, learn mode, AI assistant, admin console — hand-written CSS from the DESIGN.md token system, with dark mode |

Data lives in `data/girly.json` and is created automatically on first run.

## Status legend
- [ ] not started · [~] in progress · [x] done · [!] blocked

## Task list

### Scaffolding
- [x] Read all 6 Stitch design screens + DESIGN.md
- [x] Create this progress file
- [x] Project layout (`go.mod`, `run.sh`, `data/`)

### Go backend
- [x] `store.go` — JSON persistence + models
- [x] `auth.go` — PBKDF2 password hashing, session tokens, cookies
- [x] `cycle.go` — cycle-day / phase / next-period / fertile-window prediction math
- [x] `handlers.go` — REST endpoints (auth, logs, predictions, admin, chat proxy)
- [x] `main.go` — routing + static file serving
- [x] Builds clean (`go vet` + `go build`)

### Python assistant service
- [x] `assistant/server.py` — stdlib HTTP server, `/chat` + `/health`, cycle-aware knowledge base
- [x] Smoke-tested with curl (cramps/bloating/chocolate/blood-color topics + phase context)

### Frontend — shared
- [x] `css/girly.css` — design tokens, components, pills, cards, shadows, dark mode
- [x] `js/api.js` + shared chrome (header, bottom nav, toast, theme toggle)
- [x] Shared header + bottom nav (Tracker / Learn / Assistant / Admin)

### Frontend — pages
- [x] `index.html` — registration & onboarding (period started? → tracker vs learn mode) + sign-in
- [x] `tracker.html` — cycle ring, day counter, stat cards, phase calendar, quick-log sheets
- [x] `learn.html` — education modules, first-period prep, switch-to-tracker flow
- [x] `assistant.html` — chat stream, thinking bubbles, suggested prompt chips
- [x] `admin.html` — stats bento, system health, member directory w/ search & filters, modals, audit log

### Integration & polish
- [x] End-to-end API flow test (register → log period → predictions → chat → admin reset/revoke/delete/telemetry)
- [x] `README.md` with run instructions + demo credentials
- [x] Final progress update

## Verified during build
- Cycle math: Maya's seeded history → **Day 24, Luteal Phase, next period in 5 days** (matches the design mock)
- Session isolation across accounts (found & fixed a seed bug where all demo users shared an empty ID)
- Admin RBAC: non-admin gets `403 admin access required`
- Chat proxy weaves cycle context into replies ("Your next period is estimated in about 4 days…")
- Static assets all 200; JS/CSS brace-balance checks pass
- Timezone-safe date math (local-date-as-UTC-midnight normalization)

## Changelog
- **2026-09-11** — Build complete. All layers implemented and verified end-to-end. Both services running (`run.sh` relaunches them).
