#!/usr/bin/env bash
# Girly 🌸 — one-command launcher
# Starts the Python companion service (port 3000) and the Go app server (port 8080).
set -euo pipefail
cd "$(dirname "$0")"

if [[ -z "${PYTHON:-}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
  elif command -v python >/dev/null 2>&1; then
    PYTHON=python
  elif command -v py >/dev/null 2>&1; then
    PYTHON=py
  else
    echo "❌ Python is not installed. Install Python and retry."
    exit 1
  fi
fi

echo "🌸 Starting Girly…"

# Python companion service
"$PYTHON" assistant/server.py &
PY_PID=$!
trap 'kill "$PY_PID" 2>/dev/null || true' EXIT INT TERM

# Go app server (serves the frontend + API on :8080)
if command -v go >/dev/null 2>&1; then
  go run . &
  GO_PID=$!
  trap 'kill "$PY_PID" "$GO_PID" 2>/dev/null || true' EXIT INT TERM
else
  echo "❌ Go is not installed. Install it from https://go.dev/dl/ and retry."
  exit 1
fi

echo ""
echo "   ➜ App:       http://localhost:8080"
echo "   ➜ Companion: http://localhost:3000/health"
echo ""
echo "Press Ctrl+C to stop both services."
wait
