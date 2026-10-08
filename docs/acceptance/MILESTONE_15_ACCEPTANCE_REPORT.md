# Milestone 15 Acceptance Report

**Certification:** **ACCEPTED**  
**Scope:** Venue Adapters & Daemon Conformance  
**Evidence baseline:** `7a43d13`  
**Qualification environment:** hermetic Linux CI, headless execution, no outbound venue traffic

## 1. Executive certification

Milestone 15 is certified for paper and testnet-sandbox operation. The venue-adapter boundary, autonomous daemon, risk controls, credential lifecycle, and deployment artifacts satisfy the acceptance gates below. This certification does **not** authorize live venue execution: paper, deterministic simulation, and mock-transport testnet sandbox are the only accepted venue modes.

| Gate | Evidence | Result |
|---|---|---|
| Deterministic simulation soak | [`phase5_soak_report.json`](phase5_soak_report.json) | PASS |
| Testnet sandbox qualification | [`phase5d_testnet_report.json`](phase5d_testnet_report.json) | PASS |
| ADR-008 exact-cent conservation | Both reports and settlement regression vectors | PASS |
| ADR-011 accounting boundary | Signed, sequenced, idempotent outbox suite; no custodial credentials | PASS |
| Secret hygiene | Canary exclusion and lease revocation evidence | PASS |
| Unattended packaging | systemd and non-root Python 3.12 container manifests | PASS |

## 2. Simulation soak synthesis

The authoritative [Phase 5 soak report](phase5_soak_report.json) records **250 of 250 completed cycles** in `simulation-soak` mode, with no live network actions. The bounded priority queue held **N=12** concurrent orders and evicted only the lowest eligible resting order when the stronger candidate exceeded the required edge delta. Filled inventory remained immune from eviction.

Complete-set collateral recycling burned paired YES/NO inventory and immediately released **200 cents**, leaving one unmatched YES share. The admission barrier rejected the breaching candidate and preserved a conservatively rounded **40% dry-powder floor** (4,001 cents of 10,003 cents equity). The 10,003-cent settlement produced 8,702 SCMA cents, 1,001 CFCP cents, and 300 FAEP cents. Those components conserve exactly; the indivisible residual cent was routed to **CFCP**.

## 3. Testnet sandbox synthesis

The authoritative [Phase 5D testnet report](phase5d_testnet_report.json) records **50 of 50 completed cycles** using Kalshi and Polymarket adapters over `HTTPX_MOCK`; outbound internet calls were zero. All 50 integer-cent ledger reconciliations matched exactly.

The credential broker acquired 125 bounded, dynamic leases and revoked all 125, leaving zero active leases: a **100% revocation rate**. Report serialization rejected credential canaries and the recorded plaintext exposure result was clean. The venue limiter enforced its **10 requests/second** ceiling, exercised one HTTP 429 backoff, and recorded zero throttle violations. No result in this dossier contains a credential value or canary token.

## 4. Architectural compliance matrix

| Authority | Verification and disposition |
|---|---|
| **ADR-008 — Exact-Cent Conservation** | Authoritative money is signed 64-bit integer cents. Simulation input equals SCMA + CFCP + FAEP; independent floor allocations assign every residual cent to CFCP. Testnet order and reconciliation paths reject fractional monetary mutation and achieved 100% exact matches. |
| **ADR-011 — Signed Accounting Outbox** | Accounting events remain append-only, uniquely identified, sequenced, signed, retryable, and idempotent. Venue execution cannot be mistaken for external accounting acknowledgement. Templates carry broker configuration only and contain no key, token, bank, or venue credential. |
| **Canonical Terminology and Replay Lexicon v0.5** | The dossier uses SCMA, CFCP, FAEP, Transaction Profit Waterfall, dry powder, order intent, fill, reconciliation, and settlement with their binding meanings. Simulation and paper results are never described as live trades. PIT replay, venue response, accounting acknowledgement, and settlement remain distinct states. |
| **Directives R-09, R-13, R-14, R-18** | Immutable risk limits and the 40% floor fail closed; credentials use bounded leases; retries preserve intent identity; rate limits and backoff are enforced before dispatch. |

## 5. Deployment and unattended-operation review

The systemd unit runs as the unprivileged `pdeue` account, restricts writable paths to the state directory, and accepts operator-managed `--mode` and `--venue-mode` values while fixing the certified concurrency limit and durable output path. Its environment describes an ephemeral broker and lease lifetime; secrets must enter only through the external broker, never the unit or environment file committed to source control.

The deployment image is based on Python 3.12 slim, installs dependencies before dropping privileges, runs the headless soak daemon as `pdeue`, persists only the health summary volume, and exposes the FastAPI `/health` liveness endpoint. Compose applies a read-only root filesystem, temporary `/tmp`, restart policy, and endpoint health probe. No network-dependent step is required after the image is built.

## 6. Reproduction and audit procedure

From the repository root:

```console
cd backend
pytest -q
```

The suite is hermetic: adapter qualification uses `httpx.MockTransport`, acceptance reads checked-in evidence, and the daemon's accepted default is paper mode. Auditors should additionally validate the JSON reports with a standards-compliant parser, inspect the service using `systemd-analyze verify`, and render Compose with `docker compose config` when those host tools are available.

## 7. Residual boundaries and final disposition

This acceptance covers software conformance and packaging, not live-capital authorization, investment performance, external venue availability, or bank settlement. A later promotion must independently approve production identities, broker integration, monitoring, rollback, and live venue policy. Any exact-cent mismatch, active lease after a cycle, unredacted secret, rate-limit violation, or dry-powder breach automatically voids the affected run and fails closed.

**Final disposition: Milestone 15 Venue Adapters & Daemon Conformance is ACCEPTED for deterministic simulation, continuous paper, and mock testnet-sandbox operation.**
