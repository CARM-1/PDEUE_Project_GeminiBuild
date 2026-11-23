# PDEUE Agent Operating Instructions (`AGENTS.md`)

All coding agents (Google Jules, Gemini CLI, Codex, CI runners) operating on `CARM-1/PDEUE_Project_GeminiBuild` MUST read and obey these three controlling files before modifying any code:

1. `GEMINI.md` — Architectural invariants (`ADR-008`, `ADR-011`, `ADR-012`, `AUTH-01`–`AUTH-04`), owner-gated protected boundaries, and the 3-retry circuit breaker / step-back critic protocol.
2. `DESIGN_TOKENS.md` — Locked dark-navy institutional palette, typography, role badges, hover tooltips, and fail-closed UI states.
3. `docs/PDEUE_MASTER_CHECKLIST.md` — Master completion & verification ledger (`A1`–`G4`).

## Quick Execution Rules
- **Authoritative Base Branch:** `ring1-alpha` (branch all PRs from `ring1-alpha`, never `main`).
- **Mandatory Local Check:** `cd backend && pytest -q` (767+ passed, 0 failed).
- **UI Verification:** For any frontend or route change, run Playwright against the live FastAPI server, assert zero console/network errors and zero external CDN tags, and attach screenshots to the PR.
- **Honesty Mandate:** Never fabricate data, mock away failing invariants, or mark a checklist item complete without passing its verification gate.
