#!/bin/sh
# Fail-closed startup entrypoint for the PDEUE B2 Paper / Observation container (AWS Lightsail).
set -eu

# 1. Fail-closed paper/observation enforcement (Gate G1 protection)
VENUE_MODE="$(printf '%s' "${PDEUE_VENUE_MODE:-paper}" | tr '[:upper:]' '[:lower:]')"
LIVE_ENABLED="$(printf '%s' "${PDEUE_LIVE_TRADING_ENABLED:-false}" | tr '[:upper:]' '[:lower:]')"
GATE_G1_STATUS="$(printf '%s' "${PDEUE_GATE_G1_STATUS:-HOLD_OBSERVATIONS_ONLY}" | tr '[:upper:]' '[:lower:]')"

case "$VENUE_MODE" in
  paper|observation)
    ;;
  *)
    echo "FATAL [FAIL-CLOSED]: Refusing to boot with PDEUE_VENUE_MODE='${VENUE_MODE}'." >&2
    echo "This B2 container permits strictly 'paper' or 'observation' mode until explicit Gate G1 clearance." >&2
    exit 78
    ;;
esac

case "$LIVE_ENABLED" in
  false|0|no)
    ;;
  *)
    echo "FATAL [FAIL-CLOSED]: Refusing to boot with PDEUE_LIVE_TRADING_ENABLED='${LIVE_ENABLED}'." >&2
    echo "Live trading is permanently blocked in the B2 paper/observation container (Gate G1=${GATE_G1_STATUS})." >&2
    exit 78
    ;;
esac

# Optional collector mode (shares the hardened image without racing SQLite migrations)
if [ "${1:-}" = "collector" ]; then
  shift
  TAPE_DIR="${PDEUE_TAPE_DIR:-/var/lib/pdeue/tapes}"
  mkdir -p "$TAPE_DIR"
  echo "[pdeue-entrypoint] Verified fail-closed OBSERVED_L2 mode (venue=${VENUE_MODE}, live=${LIVE_ENABLED}). Launching collector..."
  exec python -m scripts.observed_l2_collector --tape-dir "$TAPE_DIR" "$@"
fi

# 2. Ensure persistent SQLite data directory exists & run idempotent Alembic migrations
DB_URL="${DATABASE_URL:-sqlite:////var/lib/pdeue/data/pdeue.db}"
export DATABASE_URL="$DB_URL"

case "$DB_URL" in
  sqlite:///*)
    DB_FILE="${DB_URL#sqlite:///}"
    DB_DIR="$(dirname "$DB_FILE")"
    mkdir -p "$DB_DIR"
    ;;
esac

BACKEND_DIR="${PDEUE_BACKEND_DIR:-/opt/pdeue/backend}"
if [ -f "${BACKEND_DIR}/alembic.ini" ]; then
  cd "$BACKEND_DIR"
fi

echo "[pdeue-entrypoint] Verified fail-closed paper mode (venue=${VENUE_MODE}, live=${LIVE_ENABLED}, governance=${PDEUE_GOVERNANCE_MODE:-EXECUTIVE_COMMAND})."
echo "[pdeue-entrypoint] Running idempotent Alembic migrations (alembic upgrade head) against ${DATABASE_URL}..."
alembic upgrade head

# Allow optional verification dry-run mode for automated tests (runs guard + migrations, exits cleanly)
if [ "${PDEUE_ENTRYPOINT_MIGRATE_ONLY:-false}" = "true" ]; then
  echo "[pdeue-entrypoint] Migration-only check completed cleanly."
  exit 0
fi

# 3. Launch single-worker Uvicorn tuned for 512 MB RAM AWS Lightsail
HOST="${PDEUE_HOST:-0.0.0.0}"
PORT="${PDEUE_PORT:-8000}"
echo "[pdeue-entrypoint] Launching uvicorn app.main:app on ${HOST}:${PORT} (--workers 1)..."
exec uvicorn app.main:app --host "$HOST" --port "$PORT" --workers 1
