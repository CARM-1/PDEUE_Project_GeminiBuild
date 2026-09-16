# PDEUE Class "T" (Technical Infrastructure) Manual

## Service Architecture
* **API Supervisor:** FastAPI application served via Uvicorn ASGI on port 8000.
* **Daemon Workers:** Asynchronous scan workers evaluating order book depth and IF-015 decision packets.
* **Persistence Layer:** SQLite with Write-Ahead Logging (WAL) and idempotent schema migration.

## Telemetry Endpoints
* `GET /api/v1/portal/telemetry`: Active bids count, resting order states, and dry powder status.
* `GET /api/v1/operator/daemon/cycle`: Forces an immediate scan and reconciliation cycle.

## Crash Recovery Procedure
1. Verify syntax and dependencies: `python -m py_compile backend/app/main.py`.
2. Inspect database health: Check WAL file synchronization.
3. Relaunch Uvicorn supervisor: `python -m uvicorn app.main:app --app-dir backend --port 8000 --reload`.
4. Run re-hydration cycle: Execute daemon cycle endpoint to populate in-memory state.
