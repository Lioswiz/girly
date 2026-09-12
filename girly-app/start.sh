#!/bin/sh
set -eu

python assistant/server.py &
PYTHON_PID=$!
cleanup() {
  kill "$PYTHON_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

: "${PORT:=8080}"
export GIRLY_ADDR="0.0.0.0:${PORT}"
exec ./girly-server
