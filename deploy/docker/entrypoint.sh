#!/bin/sh
set -eu

uvicorn app.main:app --host 0.0.0.0 --port 8000 &
api_pid=$!
stop_children() {
  kill "$api_pid" 2>/dev/null || true
  if [ -n "${runner_pid:-}" ]; then
    kill "$runner_pid" 2>/dev/null || true
    wait "$runner_pid" 2>/dev/null || true
  fi
  wait "$api_pid" 2>/dev/null || true
}
trap stop_children EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

python -m scripts.paper_soak_runner \
  --mode "${PDEUE_SOAK_MODE:-continuous-paper}" \
  --venue-mode "${PDEUE_VENUE_MODE:-paper}" \
  --max-concurrent-orders "${PDEUE_MAX_CONCURRENT_ORDERS:-12}" \
  --output /var/lib/pdeue-paper-soak/health_summary.json \
  --tick-interval-ms "${PDEUE_TICK_INTERVAL_MS:-5000}" &
runner_pid=$!
wait "$runner_pid"
