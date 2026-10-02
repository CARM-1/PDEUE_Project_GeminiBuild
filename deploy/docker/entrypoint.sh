#!/bin/sh
set -eu

uvicorn app.main:app --host 0.0.0.0 --port 8000 &
api_pid=$!
trap 'kill "$api_pid" 2>/dev/null || true' EXIT INT TERM

exec python -m scripts.paper_soak_runner \
  --mode "${PDEUE_SOAK_MODE:-continuous-paper}" \
  --venue-mode "${PDEUE_VENUE_MODE:-paper}" \
  --max-concurrent-orders "${PDEUE_MAX_CONCURRENT_ORDERS:-12}" \
  --output /var/lib/pdeue-paper-soak/health_summary.json \
  --tick-interval-ms "${PDEUE_TICK_INTERVAL_MS:-5000}"
