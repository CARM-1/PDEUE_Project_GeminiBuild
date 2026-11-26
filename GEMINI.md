# PDEUE Governance & Autonomous Engineering Charter (`GEMINI.md`)

**Canonical Repository:** `CARM-1/PDEUE_Project_GeminiBuild`  
**Authoritative Branch:** `ring1-alpha` (NEVER overwrite `ring1-alpha` with files from `main`)  
**Controlling Scope:** Public Data Event Underwriting Engine (PDEUE) & Independent Financial Accounting System (IFAS) Bridge

---

## 1. Non-Negotiable Architectural & Financial Invariants

Every human or automated commit MUST preserve these invariants without exception:

1. **ADR-008 — Exact-Cent Integer Accounting:** All monetary balances, order sizes, waterfall splits, and ledgers use 64-bit integer cents. Floating-point currency arithmetic is strictly prohibited.
2. **ADR-011 — Zero Banking Credentials & Air-Gapped Outbox:** PDEUE MUST NEVER store bank routing numbers, account numbers, SWIFT codes, or banking API credentials. External accounts use opaque tokens (`EXT-REF-[ENTITY]-****[LAST4]`). Accounting instructions cross to IFAS solely via HMAC-SHA256 signed JSON-LD outbox events (`/api/v1/accounting/events`, `/api/v1/accounting/reconciliation-ack`).
3. **ADR-012 / Rule A14 — High-Water Mark & 100% SCMA Loss Isolation:** Trading losses remain 100% contained inside the executing member's SCMA; CFCP and FAEP never absorb individual trading losses. The 87% SCMA / 10% CFCP / 3% FAEP Transaction Profit Waterfall applies strictly to net new profit above each SCMA's prior High-Water Mark (floor-truncated, remainder cents to CFCP).
4. **Gate G1 & Zero-Synthetic Provenance:** Execution defaults fail-closed (`HOLD_OBSERVATIONS_ONLY`, `paper` mode). Synthetic historical fills are permanently banned (`synthetic_fills_present: False`). Never weaken assertions or fabricate fills/depth to pass a test.
5. **AI Authority Envelope (`AUTH-01`–`AUTH-04`):** `unilateral_execution = False` across all AI assistants (Tutor, Copilot, Chancellor Coach, Research Studio). AI outputs may only propose deterministic Action Cards requiring authenticated human confirmation.
6. **Zero-CDN & Offline Containment (`Play #16B`):** Zero external `<script>` or `<link>` CDN tags in `backend/` HTML templates. All UI styling, charts, tooltips, and animations use self-contained/vendored CSS, SVG, or Canvas.
7. **Role Siloing, Active-Hat & Sovereign Settlor Doctrine (`Directives R-06`, `R-12`, `R-15`):**
   - Multi-role operators must explicitly switch Active Hats; privileges never blend.
   - Non-admin portals (`/member`, `/advisor`, `/admin/tech`, `/lineage/house/{id}`) strip cross-role navigation bars and enforce server-side `HTTP 403` isolation.
   - Class T consoles mask balances (`$****.**`) and SCMA IDs (`SCMA-MEM-****`) under Directive R-12 unless an audited Chief Admin override is active.
   - Bicameral 9/12 House votes act strictly as advisory petitions; the Founder/Chief Administrator holds an absolute veto and root-account quarantine immunity.

---

## 2. Owner-Gated Protected Boundaries (STOP & ESCALATE)

Automated agents (Jules, Gemini CLI, CI bots) MUST NOT modify or bypass any of the following without explicit Founder authorization in the task prompt:
- Live venue API credentials, `CredentialBroker` live-key hooks, or `.env` secrets.
- Gate G1 fail-closed defaults (`HOLD_OBSERVATIONS_ONLY`, `PDEUE_VENUE_MODE=paper`).
- Core `ADR-008`, `ADR-011`, or `ADR-012` accounting formulas or security-hygiene tests (`backend/tests/test_play16_security_hygiene.py`).
- Branch protection rules, live cloud spend provisioning, or real-money capital movement.

---

## 3. Autonomous Execution & Anti-Rabbit-Hole Protocol

1. **Read-Only Inspect First:** Always inspect existing routes, schemas, and tests before editing. Never assume file paths or API shapes.
2. **Feature Branches & Clean PRs Only:** Never push directly to `ring1-alpha` or `main`. Open one scoped Pull Request per milestone.
3. **Hard Timeouts:** Bound every shell command, server boot, and browser test with explicit timeouts so nothing hangs indefinitely.
4. **3-Retry Circuit Breaker:** Cap automated self-repair at **3 attempts per task**. If the exact same test name and error signature repeats twice in a row, stop immediately.
5. **Mandatory Step-Back Critic Gate:** Before Attempt #3 (or when the circuit breaker trips), perform a clean-context audit comparing the original objective, current `git diff`, and raw failure logs. Explicitly choose one action:
   - **Targeted Fix** (clear root cause),
   - **Revert & Fresh Approach** (`git reset` to last green commit to escape a dead end), or
   - **Escalate to Founder** (halt and write a concise, plain-English diagnosis).
6. **Qualification Gate Before Opening Any PR:**
   - Run `cd backend && pytest -q` (must pass 100% with zero regressions from the 767-test baseline).
   - Follow `DESIGN_TOKENS.md` for all frontend work and attach rendered Playwright screenshots for UI PRs.
   - Update `docs/PDEUE_MASTER_CHECKLIST.md` ONLY for items whose verification gate has actually passed.

---

## 4. Brief #01 Microstructure & Statistical Invariants (Ratified)

All trading collectors, replay engines, underwriting strategies, and automated PR audits targeting `ring1-alpha` MUST enforce the ratified Staff Consultation Brief #01 invariants:

1. **3-Unit Exact Integers:** Represent market microstructure quantities strictly with exact integer units:
   - `price_pips` (`$0.0001` per pip)
   - `qty_centi` (`0.01` contracts per centi-contract)
   - `micro_dollars` (`$0.000001` per micro-dollar)
   - Zero `float()` arithmetic or casting on prices, sizes, or fees.
   - v1 live execution is strictly restricted to uniform 1c-grid, zero-maker-fee Kalshi series.
2. **Zero Synthetic Fills:** *"No print, no fill."* Never fabricate or infer own fills from book movement, and NEVER promote public prints (`OBSERVED_TRADE`) to `CONFIRMED_OWN_FILL`.
3. **Strategy D Spread & Crypto Guardrails:**
   - Default Strategy D spread band is **4c–10c** (`3c` is replay variant only; `1c–2c` is observation only).
   - Short-horizon Crypto markets are strictly `BENCHMARK_ONLY` (never live-traded).
4. **G2A / G2B / G2C Governance Split:**
   - **G2A (Offline Certification):** Certified strictly on a 14-day observed tape split into **Days 1–8 Train / Day 9 Embargo / Days 10–14 Sealed Holdout**.
   - **G2B ($100 Founder Micro-Pilot):** Owner-gated live validation using fixed minimum lots (**$5 max order / $10 max cumulative loss**).
   - **G2C (Scaling):** Capital scaling beyond G2B requires an anytime-valid e-process crossing **`e >= 20`**.
5. **PR Audit Verdict Format:** Every automated PR review targeting `ring1-alpha` MUST provide concise, plain-English bulleted invariant findings and end with a single unambiguous verdict line:
   - `VERDICT: PASS` — Zero invariant violations detected; eligible for Founder review/merge.
   - `VERDICT: RETRY` — Correctable invariant or hygiene defect found; author/agent must remediate within the 3-retry circuit breaker.
   - `VERDICT: ESCALATE` — Protected boundary touched (live credentials, AWS Lightsail/production mutation, Gate G1 fail-closed weakening, `main` target/overwrite, or repeated circuit-breaker trip); halt and escalate to Founder.

