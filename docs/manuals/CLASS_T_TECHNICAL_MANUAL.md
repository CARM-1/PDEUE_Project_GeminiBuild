# Class T Technical Infrastructure Manual

**College:** Institute of Systems Engineering (Class T Operators `T1`–`T3`)  
**Audience:** `T1` Monitor, `T2` Operations / Engineer, `T2-Household` Scoped Engineer, and `T3` System Admin / CTO  
**Workspace:** `/admin/tech?tier=T1`, `/admin/tech?tier=T2`, `/admin/tech?tier=T2-Household`, or `/admin/tech?tier=T3`  
**Mission:** Maintain reliable, observable, fail-closed infrastructure and pristine audit evidence while strictly preserving the financial privacy wall (`Directive R-12`) and zero financial/House authority.

---

## 1. Plain-English Overview: Protecting the Engine Without Touching the Money

**In Plain English:** Class T engineers are the mechanics and air-traffic controllers of PDEUE. Your job is to keep the servers healthy, the market-data recorders running 24/7, the rate limiters smooth, and the database clean—while **never** looking at family members' personal dollar balances and **never** moving money, approving trades, or overriding financial governance. Today the platform operates in **Phase I Paper Mode** (`HOLD_OBSERVATIONS_ONLY`), recording live market depth with `$0` real bank funds connected; real bank custody and **Pay-it-Forward (`FSAP (Phase II)`)** remain completely isolated in **Phase II** inside **IFAS** (`narratixai.net` / `accounting.narratix.io`).

*(Technical & Governance Spec — Directive R-06 & Tier Boundaries):*
- **`T1` (Monitor — Read-Only Telemetry):** Views service health, worker heartbeats, WebSocket latency, token buckets, queue depth, and redacted order ladders (`$****.**`, `SCMA-MEM-****`). Global daemon triggers, settlement triggers, and CA Override controls are stripped from the DOM and rejected server-side (`HTTP 403`).
- **`T2` (Operations / Systems Engineer):** Authorized for bounded operational controls—triggering single `AutonomousScanWorker` scan cycles and `SettlementReconciler` cycles, diagnosing logs, and maintaining adapters. `T2` cannot unmask `Directive R-12` fields (`HTTP 403`), authorize trades, adjudicate proposals, or clear `Directive R-04`.
- **`T2-Household` (Scoped Household Telemetry):** Confined strictly to an assigned `X-Household-ID` boundary. Cross-household telemetry queries, global triggers, and CA Override requests fail closed (`HTTP 403`).
- **`T3` (System Admin / CTO):** Holds full `T2` technical operations plus the sole Class T ability to submit a time-bounded, audited **Chief Administrator Override** token when diagnostic incident response genuinely requires unmasked figures. `T3` inherits **zero** financial disbursement, House (`Class H`), or Chief Administrator authority and cannot select the Founder hat or clear `Directive R-04`.
- **Start-of-Watch Verification:** Confirm active tier badge, release hash, UTC clock, `/health` and `/healthz` probes (`paper_mode: true`, `gate_g1_status: HOLD_OBSERVATIONS_ONLY`, `synthetic_fills_present: false`), worker heartbeats, Alembic revision, SQLite WAL health, and `Directive R-12` redaction active. Treat null or stale telemetry as unknown, never as zero.

---

## 2. Directive R-12 Strict Financial Masking & Audited `T3` CA Override

**In Plain English:** Privacy blinds are built directly into the server—not just painted over the screen. On `/admin/tech`, every family member's account identifier arrives as `SCMA-MEM-****` and every dollar exposure arrives as `$****.**`. Neither `T1` nor `T2` can ever lift those blinds, and even a `T3` System Admin can only peek temporarily when the Chief Administrator issues a short-lived, single-purpose cryptographic override token.

*(Technical & Governance Spec — `Directive R-12` & `CAOverrideManager`):*
- **Server-Side Immutable Redaction:** Redaction occurs before serialization across `/api/v1/portal/tech/telemetry`, `/api/v1/portal/custodial/lookup` (`TECHNICAL_NODE_RELAY_R12_MASKED`), structured logs, Prometheus labels, and exports. Never log raw member balances, quantities, or before/after deltas that permit derivative reconstruction.
- **Time-Bounded Audited `T3` CA Override Procedure:**
  1. Open an incident record defining diagnostic purpose, target scope, operator, and TTL (hard-capped ≤ 900 seconds).
  2. Obtain an out-of-band short-lived override token from the Chief Administrator—never paste override tokens into chat, tickets, logs, shell history, or source code, and never reuse dev example tokens in production.
  3. Submit once via the `/admin/tech?tier=T3` CA Override modal (`POST /api/v1/portal/tech/ca-override`). Invalid tokens return `HTTP 401`, leave `Directive R-12` active, and write a `CA_OVERRIDE_DENIED` audit event.
  4. Confirm the active grant indicator, capture sanitized conclusions (avoid raw balance screenshots/downloads), and click **Revoke & Remask** (`POST /api/v1/portal/tech/ca-override/revoke`) immediately upon completion.
  5. Refresh and verify `$****.**` and `SCMA-MEM-****` are restored. Visibility grants convey zero financial authority.

---

## 3. Production Data Plane: SQLite WAL, `N=12` Eviction & `pdeue-l2-collector`

**In Plain English:** Think of our production data plane as a flight-data recorder running quietly 24 hours a day. It captures real order-book quotes from regulated venues onto tamper-evident tapes, keeps the local SQLite database crash-safe in Write-Ahead Logging (WAL) mode, and limits active market slots to exactly `N=12` so memory and compute stay lean and deterministic on our Lightsail host (`pdeue-ring1-paper`).

*(Technical & Governance Spec):*
- **SQLite WAL Mode Discipline:** Production SQLite databases MUST retain:
  - `PRAGMA journal_mode=WAL`
  - `PRAGMA synchronous=FULL`
  - Bounded `busy_timeout` and `PRAGMA foreign_keys=ON`
  - Single-writer discipline and controlled checkpointing (`PRAGMA wal_checkpoint(TRUNCATE)` only via approved maintenance windows). **Never delete `-wal` or `-shm` files from a live database.**
- **`N=12` Slot Concurrency & Deterministic Priority Eviction:** The underwriting rack maintains a fixed **N=12** concurrency ceiling (`priority_eviction.py`). When a 13th qualified candidate arrives, deterministic rank and tie-break rules evict the lowest-priority slot rather than silently expanding capacity. Always preserve candidate evidence and eviction reason codes.
- **`pdeue-l2-collector` 24/7 `OBSERVED_L2` Tape Recording:** Runs continuously alongside `pdeue-paper-api` on the isolated Lightsail deployment (`pdeue-ring1-paper`), writing authentic dual-venue order-book depth snapshots (`OBSERVED_L2`) to `/var/lib/pdeue/tapes` with SHA-256 provenance manifests.
  - **Gate G1 Fail-Closed Default:** `PDEUE_VENUE_MODE=paper`, `PDEUE_LIVE_TRADING_ENABLED=false`, `PDEUE_GATE_G1_STATUS=HOLD_OBSERVATIONS_ONLY`, and `synthetic_fills_present: False`. Synthetic historical fills are permanently banned.
  - **Independent Venue Token Buckets:** Kalshi and Polymarket each enforce an independent **10 requests/second** token bucket with jittered backoff (`retry_after_seconds`, e.g., ≤ `0.125s` test jitter). Exhausting one venue's bucket never starves the other venue. Never bypass rate limits with parallel clients or busy-loops.

---

## 4. Isolated `pdeue_shadow_hunch.db`, Modular `BaseLLMClient` & Nov 2026 Compliance Filter

**In Plain English:** Family members and administrators can test market ideas risk-free in the **Shadow Paper Hunch Studio** and ask questions of the **Dual-Lane AI Tutor** and **Role-Scoped Copilots**—all without ever risking live database corruption or surprise cloud AI bills. Shadow Hunch records live in their own completely separate SQLite file (`pdeue_shadow_hunch.db`), and all AI assistants plug through one clean adapter (`BaseLLMClient`) that defaults to a `$0` deterministic mock in CI while supporting Gemini and OpenAI in production.

*(Technical & Governance Spec):*
- **Isolated `pdeue_shadow_hunch.db` Storage:** `ShadowHunchService` (`backend/app/domain/shadow_hunch_service.py`) writes exclusively to its dedicated SQLite database (`pdeue_shadow_hunch.db`, table `shadow_hunch_dossiers`) in permanent `SHADOW_PAPER` mode. It has **zero foreign keys or write paths** into live SCMA capital ledgers, Gate G1 controls, or the `ADR-011` IFAS outbox. Class T callers are isolated from financial Shadow Hunch dossiers (`HTTP 403`, `ROLE_FORBIDDEN`).
- **Nov 2026 CFTC / DEATH BETS Act Regulatory Filter (`regulatory_filter.py`):** Every hunch evaluation passes through the deterministic fail-closed compliance filter blocking prohibited categories (sports/athletics, casino gambling, war/armed conflict, terrorism, death/mortality) with `PROHIBITED_EVENT_CATEGORY` before persistence or paper-bid staging.
- **Modular `BaseLLMClient` Adapter (`backend/app/domain/ai_clients/`):**
  - `MockLLMClient` — deterministic, `$0`, zero-network default for CI and offline qualification.
  - `GeminiLLMClient` — Google Gemini production adapter (fail-closed fallback on timeout/key absence).
  - `OpenAILLMClient` — OpenAI production adapter (fail-closed fallback on timeout/key absence).
  - **Invariant Lock (`AUTH-01`–`AUTH-04`):** `unilateral_execution = False` across the Dual-Lane AI Tutor (Lane 1 Local Canon / Lane 2 Public Research), Class F Copilot, Class T DevOps Telemetry Copilot (`POST /api/v1/portal/tech/copilot`), and Chief Admin AI Chancellor Coach. Prompt-injection and `Directive R-12` guardrails (`guardrails.py`) strip financial leaks and record `AI_GUARDRAIL_REFUSAL` audit events.

---

## 5. Four-Domain Caddy Air-Gap, `ADR-011` Boundary & Zero-CDN Containment

**In Plain English:** Instead of dumping family photos, member accounts, admin controls, and bank bookkeeping into one messy website, PDEUE separates them into **four clean HTTPS domains** fronted by a lightweight `caddy:2-alpine` reverse proxy—plus a fifth physically isolated domain for bank accounting (`narratixai.net`). On top of that, every single HTML page in PDEUE is **100% self-contained with zero external CDNs** so no third-party tracker or remote script can ever break or snoop on a family portal.

*(Technical & Governance Spec — PR #85 `deploy/caddy/Caddyfile`, `docker-compose.domains.yml`, Play #16B):*
- **4-Domain Caddy Air-Gap + Isolated IFAS Boundary:**
  1. **`narratixai.org`** (with `www.narratixai.org` 301 canonical redirect): Social Plane — `/home`, `/community`, `/community/heritage` (plus Jitsi Meet compatibility). Explicitly blocks `/dashboard`, `/admin/tech`, `/advisor`, `/member`, and financial APIs (`HTTP 403`).
  2. **`narratixai.info`**: Learning Plane — `/companion` (PDEUE University) and canonical manual reader. Explicitly blocks admin/trading mutation surfaces (`HTTP 403`).
  3. **`vault.narratixai.io`**: Member & Custodial Vault Plane — `/member`, `/advisor`, `/lineage/house/{id}`. Explicitly blocks `/dashboard` and `/admin/tech` (`HTTP 403`).
  4. **`admin.narratixai.io`**: Operations & Sovereign Command Plane — `/dashboard` and `/admin/tech`.
  5. **`narratixai.net`** (Isolated IFAS Boundary): Zero-proxy static air-gap landing (`deploy/caddy/ifas_airgap/index.html`) enforcing the `ADR-011` wall between PDEUE trading telemetry and the standalone IFAS banking system (`accounting.narratix.io`).
- **ADR-011 Signed Outbox Contract:** Only HMAC-SHA256 signed, monotonically sequenced, schema-valid, idempotent JSON-LD envelopes (such as `IF-038` float sweeps and `MEMBER_ADMISSION_RATIFIED` notices) cross to IFAS (`/api/v1/accounting/events`, `/api/v1/accounting/reconciliation-ack`). Zero bank routing numbers, account numbers, SWIFT codes, or banking API credentials may ever exist in PDEUE.
- **Zero-CDN Offline Containment (`Play #16B`):** Zero external `<script>` or `<link>` CDN tags anywhere in `backend/` HTML templates. All styling, Concentric Asset Rings SVGs, Canvas walk-forward charts, tooltips (`<abbr data-tooltip>`), and audio controls are self-contained/vendored and verified in CI by `backend/tests/test_play16_security_hygiene.py`.

---

## 6. Worker Cycles (`AutonomousScanWorker`, `SettlementReconciler`) & Accounting Invariants

**In Plain English:** When a `T2` or `T3` engineer triggers a manual scan or settlement check, the engine performs one bounded, auditable cycle—never bypassing a financial halt and never guessing at rounding pennies. Settlement convergence obeys exact-cent math (`ADR-008`), keeps member losses 100% isolated (`Rule A14`), and charges zero skim while a member recovers below their High-Water Mark (`ADR-012`).

*(Technical & Governance Spec):*
- **`AutonomousScanWorker` Manual Cycle (`T2`/`T3` Only):** Before invoking `POST /api/v1/portal/tech/trigger-daemon`, verify ticket/scope, confirm no conflicting migration or active `Directive R-04` halt, inspect circuit-breaker state and source freshness, record prior cycle count/queue depth/outbox sequence, trigger once, and check correlation ID and reason codes. Never retry blindly after a timeout without verifying whether the cycle completed.
- **`SettlementReconciler` Convergence (`T2`/`T3` Only):** Idempotent reconciliation comparing venue outcomes, internal positions, settled cash, and `ADR-011` outbox events (`POST /api/v1/portal/tech/trigger-settlement`):
  - **ADR-008 Exact-Cent Conservation:** 64-bit integer cents exclusively; floor-truncated SCMA (87%) and FAEP (3%) with indivisible remainder cents routed to CFCP. Never fix mismatches via floating-point rounding or manual DB edits.
  - **ADR-012 High-Water Mark & Rule A14 100% SCMA Loss Isolation:** Persist per-SCMA `high_water_mark_cents`; keep realized trading losses 100% inside the executing SCMA (CFCP/FAEP never decrease for member trading losses); retain 100% of recovery profit below HWM inside SCMA (`0¢` CFCP/FAEP skim); split ONLY net new profit above HWM; raise HWM dollar-for-dollar on deposits and adjust proportionally on authorized withdrawals.
- **Directive R-04 vs. Technical Service Halts:** `Directive R-04 Emergency Financial Halt` belongs strictly to financial governance (`F3` / Chief Administrator). A technical service halt stops an internal worker or container to contain a software fault; it does NOT prove external venue order cancellation and NEVER clears `Directive R-04`.

---

## 7. Observability, Migrations, Secrets & Incident Response

**In Plain English:** Good operations mean spotting memory leaks, rate-limit spikes, or database schema drift long before they affect a single family member—while keeping secrets out of code and balances out of logs.

*(Technical & Governance Spec):*
- **Structured Logging & AWS CloudWatch:** Emit structured JSON to stdout containing UTC timestamp, severity, service, release, environment, correlation ID, cycle ID, event type, and sanitized reason code. Strictly exclude secrets, tokens, banking data, raw auth headers, and unredacted tenant balances. Configure alarms for worker heartbeat loss, reconciliation failure, outbox signature failure, rate-limit pressure, and repeated `CA_OVERRIDE_DENIED` attempts.
- **Prometheus & Grafana RSS Metrics:** Scrape protected internal metrics for process resident set size (RSS), CPU, worker heartbeat age, cycle duration/failures, queue depth, reconciliation lag, outbox backlog, rate-limit denials, and circuit states. Enforce low-cardinality non-financial labels (`service`, `environment`, `worker_type`, `venue`, `status`)—never label by member, SCMA, order, or token.
- **Alembic CLI Migration Runbook:** Run strictly from `backend/` under change control (`alembic current`, `alembic history`, `alembic upgrade head`, reviewed `alembic downgrade <rev>`). Back up first, test on a production-shaped copy, verify WAL quiescence where required, and never stamp a database to conceal a failed migration.
- **AWS Secrets Manager & `CredentialBroker`:** Store venue keys, signing material, database secrets, and production override verification keys exclusively in AWS Secrets Manager (never `.env` commits, images, logs, or tickets). Rotate via staged canary, verify dependent services, and revoke old versions. Secret retrieval failures MUST fail closed; hard-coded fallback credentials are prohibited.
- **Technical Incident Matrix & Handoff:**
  - *Heartbeat loss:* `T1` logs UTC timestamps & escalates → `T2` preserves logs & performs approved restart → `T3` owns recurring root cause.
  - *Rate limiting (`HTTP 429`):* Reduce concurrency and honor `retry_after_seconds` backoff; never add parallel clients.
  - *Settlement divergence / Outbox signature failure:* Stop retries, quarantine affected event/signing path, preserve last clean checkpoint, and escalate to financial authority.
  - *`Directive R-12` leak:* Revoke access immediately, preserve sanitized evidence, rotate affected material, and invoke security incident response.
  - *Shift Handoff:* Report tier, release, worker health, cycle counts, `pdeue-l2-collector` heartbeat, WAL size, RSS trend, outbox backlog, `Directive R-04` state, active/revoked `T3` override grants, and next owner—with zero masked values or tokens.
