# Chief Administrator Operational Runbook (Sovereign Chancellor Flight Manual & Succession Handbook)

**College:** Apex School of Sovereign Governance (Executive Chancellor Cockpit)  
**Audience:** Founder & Chief Administrator (Apex Authority) and Designated Read-Only Shadow Successor (`CHIEF_ADMIN_DEPUTY`)  
**Primary Workspace:** `/dashboard` (Live Command) · `/dashboard?role=CHIEF_ADMIN_DEPUTY` (Read-Only Succession Shadow)  
**Operating Principle:** Broad visibility never eliminates deterministic controls, exact-cent conservation, dual control, or auditable handoffs.

---

## 1. Plain-English Overview & Start-of-Watch Checklist

**In Plain English:** Think of `/dashboard` as the bridge of a generational family ship. Today PDEUE sails in **Phase I Paper Mode** (`HOLD_OBSERVATIONS_ONLY`)—testing live market winds with zero real bank dollars connected so the family builds calm operational habits before **Phase II** activates bank custody in **IFAS** (`accounting.narratix.io`) and our **Pay-it-Forward (`FSAP (Phase II)`)** debt-relief pool. Even as Founder and Chief Administrator, you wear one Active Hat at a time (`Directive R-06`), treat blank or pending figures as unknown rather than zero, and never let AI recommendations execute without deliberate human confirmation (`unilateral_execution = False`).

*(Technical & Governance Spec — Start-of-Watch Procedure):*
1. **Verify Identity & Active Hat (`Directive R-06`):** Enter `/dashboard` through the approved identity flow and confirm the Active-Hat pill (`Active Hat: CHIEF_ADMIN` for live command, or `CHIEF_ADMIN_DEPUTY (READ-ONLY)` for shadow observation). Switching from `CHIEF_ADMINISTRATOR` to `PERSONAL_SCMA` (`/member`) explicitly revokes the prior executive hat session and logs an `ACTIVE_HAT_SWITCH` event.
2. **Verify Runtime Posture (`Gate G1`):** Confirm `MODE: PAPER`, `gate_g1_status: HOLD_OBSERVATIONS_ONLY`, `synthetic_fills_present: False`, UTC timestamp, data freshness, `Directive R-04` state (`NORMAL` vs. `HALTED`), active governance stage (`EXECUTIVE_COMMAND` default), and open dual-control queues.
3. **Honor `Directive R-12` Privacy Boundaries:** Technical consoles (`/admin/tech`) remain redacted (`$****.**`, `SCMA-MEM-****`). When granting a time-bounded `T3` CA Override for incident diagnostics, record scope, expiry, and revocation—never transmit override tokens through chat or tickets.
4. **Never Share or Leave Active Sessions Unattended:** Log a concise watch-start note capturing operator, release, active governance stage, unresolved incidents, and pending approvals.

---

## 2. Step-by-Step Operational Checklists for All Four `/dashboard` Tabs

### Tab 1 — Founder SCMA & Executive Overview (`Lineage Executive Overview`)

**In Plain English:** Tab 1 is your one-glance health check for the entire family fleet: total equity, working margin, your mandatory **40% Dry-Powder Cash Cushion** (visualized in the Concentric Asset Engine Rings), open positions, and reconciled settlements. Review warning banners and exceptions before looking at green numbers.

**Tab 1 Operational Checklist:**
1. Inspect `#readModelStatusBanner` and `#dashboardHaltOverlay`; treat `QUALIFICATION_PENDING`, `TRADING_HALTED`, or `DEGRADED_RETRYING` as fail-closed states—never substitute estimated figures.
2. Verify **Lineage Total Equity (`ADR-008`)**, **Committed Margin (`Quarter-Kelly`)**, **Realized Lifetime PnL**, and **40% Dry-Powder Floor Shield** across the Concentric Asset Engine Rings.
3. Confirm the **Enclave-Wide Scoped Custodial Lookup** bar returns authoritative member records across `HOUSE-01` through `HOUSE-12`.
4. Audit the **Active Portfolio Positions & Settlement Reconciliation** table: confirm contract, venue, quantity, VWAP, exact-cent cost basis, and status (`RESTING_MAKER`). Before resolving any settlement, preview the deterministic 87/10/3 `ADR-012` HWM waterfall and verify exact integer-cent conservation (`ADR-008`).

### Tab 2 — 12-House Family Pools & Onboarding (`Family Lineal Pools & Sub-Ledgers`)

**In Plain English:** Tab 2 shows all 12 Family Houses side-by-side along with the shared `CFCP` safety shield (10%), `FAEP` endowment (3%), every member's private walled-off `SCMA`, and your tools to welcome new family members individually or in batches. Every penny stays strictly accounted for, losses never spill across accounts (`Rule A14`), and members recovering from a dip keep 100% of recovery dollars until they pass their High-Water Mark (`ADR-012`).

**Tab 2 Operational Checklist:**
1. Reconcile **CFCP (10% + residual cents)** and **FAEP (3%)** balances against settled realized profits strictly above each SCMA's `high_water_mark_cents` (`ADR-012`, `ADR-008`). Confirm `0¢` CFCP/FAEP skim on drawdown recovery and 100% SCMA containment of trading losses (`Rule A14`).
2. Verify external deposits raise HWM dollar-for-dollar and authorized withdrawals adjust HWM proportionally.
3. **5-Stage Member Onboarding (`+ Onboard Member` / `Batch Provision (JSON / CSV)`):**
   - Validate signed roster, House assignment (`HOUSE-01`..`HOUSE-12`), role tier, `is_custodial` minor flag, exact integer `seed_cents` (`ADR-008`), downward-only risk dial (`0.50%–2.00%`), and opaque `ADR-011` bank reference token (`EXT-REF-[ENTITY]-****[LAST4]` — zero raw account/routing numbers).
   - Run atomic fail-closed batch ingestion (any invalid row rejects the entire batch `HTTP 422` with zero partial writes).
   - Distribute single-use 48-hour invite links and track member upgrade from `PENDING_TUTOR_CERTIFICATION` to `ACTIVE` (`STEWARDSHIP_L1_CERTIFIED`) via `/companion` Chapter 6.
4. Use the **Audit Lens** link (`?supervisory=1&inspector=CHIEF_ADMIN`) to inspect subordinate `/member`, `/advisor`, or `/admin/tech` views in read-only amber Supervisory Audit Lens mode without mutating state.
5. Verify **Sovereign Immune** badge protection on the Founder root SCMA (`SCMA-FOUNDER_-C8575D7E`), preventing subordinate freeze, clamp, or revocation.

### Tab 3 — Velocity Radar & Admin Parallel Shadow Paper Hunch Studio (`Velocity Radar & Scanner`)

**In Plain English:** Tab 3 pairs our live quantitative scanner (Strategy D Inside Maker walk-forward benchmark and active scanner queue) with your permanent **Admin Parallel Shadow Paper Hunch Studio**. Think of the Shadow Studio as a clean side-by-side laboratory: you can test brand-new market verticals and adjudicate family members' F2-H-endorsed hunches in isolated virtual `SHADOW_PAPER` dollars without touching a single penny of live capital.

**Tab 3 Operational Checklist:**
1. Review **Strategy D (Inside Maker Core)** vs. Baselines A/B/C walk-forward curves and inspect the **Active Scanner Queue** (model probability, venue quote, net edge, qualification status). A candidate remains research until all deterministic admission gates pass.
2. **Admin Parallel Shadow Paper Hunch Studio (`pdeue_shadow_hunch.db`, permanent `SHADOW_PAPER` mode):**
   - Test hypotheses across the **6 regulated verticals** (Weather/NOAA, Macro/CPI, Energy/EIA, U.S. Treasuries, Equity Indices, G10 FX) via the 3-Point Validation Audit (`VALIDATED_SHADOW_READY`, `REJECTED_NO_EDGE`, or fail-closed `PROHIBITED_EVENT_CATEGORY` under the **Nov 2026 CFTC / DEATH BETS Act** filter blocking sports, casino, war, terrorism, and death contracts).
   - Stage virtual shadow bids (`$0.00` live capital touched; zero `ADR-011` IFAS outbox events).
   - Adjudicate `PENDING_F3_CLEARANCE` member petitions (already endorsed by `F2-H` in Step 1) by inspecting each member's verified **Shadow Hit-Rate** track record and issuing final **`ALLOWED`**, **`DENIED`**, or post-clearance **`RESCINDED`** determinations.
3. Use the **AI Chancellor Coach** slide-out drawer (`unilateral_execution = False`, `AUTH-01`–`AUTH-04`) to review Constrained Policy Decision Matrices and 5-pillar constitutional invariant checks. AI recommendations only pre-stage UI navigation and never auto-execute.

### Tab 4 — Governance & Dual-Control Audit (`Governance & Dual-Control`)

**In Plain English:** Tab 4 is the constitutional desk: where you control the Three-Stage Governance Lifecycle, manage communal bodies and named voter seats, provision officer roles safely with zero orphaned charges, toggle Anti-Tribalism Custody, ratify delegated admission dossiers, and execute or veto ratified House petitions.

**Tab 4 Operational Checklist:**
1. Verify current governance stage badge (`MODE: EXECUTIVE_COMMAND` default) and `FOUNDER VETO: ACTIVE`.
2. Audit **FUTURE Enclave Registry** communal bodies and named/office voter seats before granting or revoking Stage 3 veto seats.
3. **Multi-User Role Provisioning & Anti-Tribalism Custody:** Confirm strict single-seat occupancy for `CHIEF_ADMIN`, `T3` (CTO), and `F3` (CRO); verify atomic promote/demote leaves zero orphaned custodial charges and immediately revokes stale sessions; toggle `INTRA_HOUSE` vs. `CROSS_HOUSE_ANTI_TRIBAL` custody pairing as the lineage grows.
4. **3-Stage Delegated Onboarding & Genealogical Ratification:** Keep intake scope fail-closed (`ADMIN_ONLY`) until explicitly enabled per-House or enclave-wide; review `PENDING_RATIFICATION` dossiers (and optional Genealogical Admissions Board votes) before clicking **Ratify & Provision**, **Request Proof**, or **Reject**. Ratification atomically provisions the SCMA and emits a signed HMAC-SHA256 `MEMBER_ADMISSION_RATIFIED` `ADR-011` IFAS outbox notice with zero banking credentials.
5. Adjudicate `RATIFIED_PENDING_SETTLOR` / `PENDING_CHIEF_ADMIN_AUTHORIZATION` House petitions through **Authorize Sweep** or **Founder Veto** while preserving immutable `GovernanceAuditLog` records.

---

## 3. Surgical Containment vs. Global Emergency Kill Switch (`Directive R-04`)

**In Plain English:** Not every problem calls for shutting down the whole ship. If one cabin springs a leak, you close that cabin's watertight door (`Surgical Single-SCMA / Single-House Freeze`) so the other 11 Houses continue calmly without disruption. You pull the big red **`Global Emergency Kill Switch (Directive R-04)`** only when a systemic threat—like a venue outage, ledger mismatch, or compromised key—could endanger capital across multiple Houses.

| Control Dimension | Surgical Single-SCMA / Single-House Freeze (Tab 2) | Global Emergency Kill Switch (`Directive R-04` Header / Tab 4) |
| :--- | :--- | :--- |
| **Blast Radius** | Single member SCMA (`freeze-risk` to `0.0%`, `cancel-orders`) OR single Lineage House quarantine (`HOUSE-01`..`HOUSE-12`) | **Platform-wide:** halts all 12 Houses, execution dispatch, and new financial commitments fail-closed |
| **When to Use** | Runaway domestic node, localized risk-dial anomaly, member dispute, household credential issue, or targeted audit | Cross-House VaR breach, unexplained `ADR-008` ledger mismatch, venue distress/ambiguity, suspected platform key compromise, or control failure |
| **Healthy Houses Impacted** | **Zero** — the other 11 Houses continue normal operations untouched | All Houses pause new risk until verified safe recovery |
| **Who Can Trigger** | Chief Administrator (enclave-wide); `H2` House Leader (own House only, Founder root immune) | Chief Administrator OR `F3` Chief Risk Officer (`Directive R-04` failsafe) |
| **Who Can Lift / Restore** | Chief Administrator (or authorized `H2`/`F2-H` within scope) | **Strictly Chief Administrator Only (`CHIEF_ADMINISTRATOR_ONLY`)** via governed recovery & `AUTH-04` closure |
| **Distinction from Technical Halt** | Financial containment on SCMA/House ledger | Financial failsafe — distinct from Class T worker restart; stopping a worker never proves external venue cancellation and never clears `R-04` |

*(Technical & Governance Spec — `Directive R-04` Recovery Checklist):* Identify root cause → reconcile open venue orders & positions → verify exact-cent `ADR-008` balances & `ADR-012` HWM state → inspect contiguous `ADR-011` outbox sequences → confirm secrets & Active-Hat sessions → pass automated tests → obtain required dual control → execute `POST /api/v1/operator/emergency-resume` as Chief Administrator → restore in stages and close through `AUTH-04`.

---

## 4. `AUTH-01` Through `AUTH-04` Action Card Ratification & FBO Custodial Sweeps (`$25,000` Float Cap)

**In Plain English:** Every consequential action follows four calm checkpoints—who asked, who double-checked, did the computer's safety rules pass, and is the final receipt written down. Meanwhile, any excess cash above our `$25,000` on-venue working drawer sweeps cleanly out to our separate IFAS banking home via signed notices, never by storing bank passwords inside PDEUE.

*(Technical & Governance Spec):*
- **AUTH-01 (Authenticated Initiation):** Authorized human initiates a typed Action Card binding actor, Active Hat, target, parameters, timestamp, and evidence digest. AI output alone never satisfies `AUTH-01`.
- **AUTH-02 (Independent Quorum / Co-Signature):** Second authorized principal attests the identical immutable payload; self-co-signing or altered digests fail closed.
- **AUTH-03 (Deterministic Policy Admission):** Automated checks enforce tenant scope, operating mode, risk envelope, 40% dry-powder floor, liquidity, freshness, idempotency, and `Directive R-04` posture.
- **AUTH-04 (Execution Receipt & Audit Closure):** Records final outcome, authoritative identifiers, UTC timestamp, and before/after state. Unknown/timeout states must be reconciled before idempotent retry.
- **FBO Custodial Architecture, `$25,000` Active Float Cap & `FSAP (Phase II)` (`ADR-011`):**
  - Operational venue float is capped at **\$25,000** (`2,500,000¢`). Excess triggers `FloatSweepMonitor` to stage a signed HMAC-SHA256 `IF-038` `ADR-011` outbox envelope to IFAS (`accounting.narratix.io`).
  - Verify venue + internal ledger reconciliation, exact-cent excess over `2,500,000¢`, contiguous outbox sequence, HMAC-SHA256 signature, zero banking credentials, and idempotency key before dispatch. Track `pending` → `emitted` → `delivered` (`reconciliation-ack`); retry strictly by idempotency key, never by creating a duplicate economic event.
  - In **Phase II**, IFAS also hosts **Pay-it-Forward (`FSAP (Phase II)` — Familial Stability Advance Pool, `IF-038`–`IF-041`)** alongside CFCP with `F2-H` + Chief Admin dual control on direct-to-creditor advances and untouched 87/10/3 PDEUE waterfall math.

---

## 5. Succession & Deputy Administrator Protocol (`CHIEF_ADMIN_DEPUTY`)

**In Plain English:** Generational stewardship means the Founder is never a single point of failure—and a future successor never gets handed live nuclear launch codes on day one. Before any designated successor assumes the single-seat `CHIEF_ADMIN` role, they train inside the live cockpit using **`CHIEF_ADMIN_DEPUTY` Read-Only Shadow Succession Mode** (`/dashboard?role=CHIEF_ADMIN_DEPUTY`). They can see every tab, every 12-House balance, every radar opportunity, and every governance audit log in real time, while every single destructive or mutating button is locked out both visually and on the server (`HTTP 403`).

### 5.1 Read-Only Shadow Observation Cockpit (`CHIEF_ADMIN_DEPUTY`)
- **Entry & Role Recognition:** Access via `/dashboard?role=CHIEF_ADMIN_DEPUTY` or authenticated header `X-PDEUE-Role: CHIEF_ADMIN_DEPUTY` (verified server-side through `/api/v1/portal/dashboard/state`).
- **Visual Guardrail:** `/dashboard` renders a persistent, high-contrast amber banner at the top of the screen:
  > `🛡️ DEPUTY OBSERVER MODE (CHIEF_ADMIN_DEPUTY) — READ-ONLY SUCCESSION SHADOW. Destructive & mutating actions are locked.`
- **Fail-Closed Backend Lock (`HTTP 403 · DEPUTY_READ_ONLY_OBSERVER`):** Every mutating Chief Admin endpoint—including Emergency Kill Switch / Resume, Governance Stage transitions & SHTF Snap-Back, Enclave Body/Seat changes, Role Provisioning / Atomic Promote / Demote, Custody Mode toggles, Member Onboarding / Batch Provisioning / Dossier Ratification, House/SCMA Freeze & Order Revocation, Stage Order & Settlement Resolution, and Shadow Hunch evaluation/live-clearance adjudication—rejects `CHIEF_ADMIN_DEPUTY` fail-closed with **`HTTP 403` (`DEPUTY_READ_ONLY_OBSERVER`)** and writes a `DEPUTY_READ_ONLY_MUTATION_BLOCKED` entry to `GovernanceAuditLog`.
- **Full Read-Only Visibility Preserved:** All 4 `/dashboard` tabs, House accordions, Concentric Asset Engine Rings, Enclave-Wide Scoped Custodial Lookup (read-only), Shadow Hunch track records, Glossary drawer, and audit streams remain 100% navigable so the Deputy can shadow every operational routine realistically.

### 5.2 Mandatory Shadow Observation Window & Atomic Succession Handoff
1. **Observation Window:** A designated `CHIEF_ADMIN_DEPUTY` must complete a **minimum 30-day continuous read-only shadow observation window** (covering at least 15 daily watch starts, 4 weekly exact-cent reconciliations, 2 dry-run onboarding audits, and 1 full governance review cycle) plus pass PDEUE University (`/companion`) certification across all colleges.
2. **Dry-Run Attestation:** The Deputy logs parallel written watch-start and watch-end assessments (citing exact-cent totals, 40% dry-powder ratios, and `AUTH-01`–`AUTH-04` dispositions) audited by the incumbent Chief Administrator and `F3` CRO.
3. **Atomic Single-Seat Succession:** Only after all 3 incident-response readiness scenarios below are signed off does the Chief Administrator (or emergency succession custodian) execute an explicit **Atomic Single-Seat Succession Handoff** (`atomic_succession: true` on `/api/v1/governance/roles/promote`), immediately revoking stale sessions and logging the immutable succession record.

### 5.3 Three-Scenario Incident-Response Readiness Checklist (Required Before Succession)

Every `CHIEF_ADMIN_DEPUTY` candidate must walk through and pass all three operational tabletop / staging drills with zero protocol errors:

1. **Scenario 1 — Liquidity Shock (Cross-Venue Stress / VaR Breach):**
   - *Trigger:* Rapid venue spread blowout, Kalshi/Polymarket outage, or 99% VaR warning breach threatening the 40% Dry-Powder Floor.
   - *Required Deputy Drill:* Confirm `ReadModelEnvelope` freshness (never guess from stale data) → coordinate with `F3` CRO on `/advisor?role=F3` → verify whether `Directive R-04` Global Emergency Halt is required → keep technical worker state strictly separate from external venue cancellation claims → draft the full `AUTH-01`–`AUTH-04` Chief-Admin-Only staged recovery checklist before lifting any halt.
2. **Scenario 2 — Runaway Domestic Node (Localized Household / SCMA Anomaly):**
   - *Trigger:* Errant order bursts, compromised household credentials, or unauthorized risk activity isolated to a single SCMA or single House (e.g., `HOUSE-04`).
   - *Required Deputy Drill:* Demonstrate **Surgical Containment** discipline—select **Tab 2 Single-SCMA Freeze (`0.0%`) / Revoke Orders** or **Single-House Quarantine** instead of pulling the global `Directive R-04` kill switch, leaving the other 11 Houses undisturbed → inspect affected member safely via **Supervisory Audit Lens** (`?supervisory=1`) → verify **Founder Quarantine Immunity** remains intact → preserve `GovernanceAuditLog` evidence before authorizing staged restoration.
3. **Scenario 3 — `$25k` Sweep Audit (Active Float Cap & `ADR-011` Outbox Verification):**
   - *Trigger:* Settled on-venue float exceeds the `$25,000` (`2,500,000¢`) custodial cap and `FloatSweepMonitor` stages an `IF-038` sweep.
   - *Required Deputy Drill:* Reconcile venue cash against internal SCMA sub-ledgers in exact integer cents (`ADR-008`) → confirm `ADR-012` HWM waterfall conservation (`87/10/3`, remainder cents to CFCP, `0%` skim on recovery) → inspect the signed HMAC-SHA256 `ADR-011` outbox envelope (`sequence`, `signature`, `idempotency_key`, opaque `EXT-REF-...` token with **zero** raw banking credentials) → verify IFAS `/api/v1/accounting/reconciliation-ack` delivery without ever creating a duplicate economic event.

---

## 6. Routine Cadence, Incident Playbooks & Prohibited Shortcuts

**In Plain English:** Calm daily rhythm prevents emergencies. Reconcile every day, fix errors with transparent compensating entries rather than silent edits, and never let urgency blur financial and technical roles.

*(Technical & Governance Spec):*
- **Daily Cadence:** Watch start (identity, UTC, `Gate G1`, `R-04`, governance stage) → exception queue & reconciliation check → `AUTH-01`–`AUTH-04` verification before any approval → daily reconciliation (venue positions vs. internal book, 87/10/3 + `ADR-012` HWM conservation, `$25,000` float cap, contiguous `ADR-011` outbox sequences) → watch-end handoff naming every uncertainty explicitly.
- **Core Incident Playbooks:**
  - *Ledger Mismatch:* Engage `Directive R-04` if new risk is affected; freeze retries; preserve source records; compare exact integer cents (`ADR-008`) and outbox sequences; correct strictly via auditable compensating event.
  - *Venue Ambiguity:* Halt new dispatch to affected venue; preserve request IDs; query authoritative adapter state before canceling/replacing.
  - *Suspected Credential Compromise:* Halt affected finance; revoke sessions & AWS Secrets Manager leases; rotate keys; audit access logs; require fresh dual control.
  - *Outbox Backlog:* Keep economic events immutable; diagnose generation vs. dispatch vs. ACK failure; replay idempotently without raising venue float above `$25,000`.
- **Prohibited Shortcuts:** Never self-co-sign `AUTH-02`, reuse a `T3` override token, treat AI prose as execution authority, infer zero from null, edit historical ledger rows directly, restart workers around `Directive R-04`, store raw bank credentials, send unsigned outbox messages, or bypass `CHIEF_ADMIN_DEPUTY` read-only locks.

---

## 7. Three-Stage Governance Lifecycle & FUTURE Enclave Charter (Executive Command -> Advisory Filter -> Configurable Bicameral Veto & SHTF Protocol)

**In Plain English:** PDEUE is built to mature peacefully across generations without exposing the family treasury to premature committee politics during its early years—and without freezing leadership during a crisis. All fresh deployments start safely in Stage 1 (`EXECUTIVE_COMMAND`), and only the Chief Administrator can open Stage 2 advisory voting or Stage 3 binding bicameral vetoes, or snap back instantaneously in an emergency (`SHTF`).

*(Technical & Governance Spec — Relational Persistence & `GovernanceAuditLog`):*
PDEUE governance operates through **three explicit, Chief-Administrator-controlled stages** backed by relational persistence (`governance_config`, `governance_bodies`, `governance_voter_seats`, `governance_petitions`, `governance_votes`) and an append-only `GovernanceAuditLog`:

### Stage 1 — `EXECUTIVE_COMMAND` (Default Fledgling & SHTF Mode)
* **Why it is the default:** Every fresh deployment starts fail-closed in `EXECUTIVE_COMMAND` while the family establishes operational discipline, completes PDEUE University literacy certification, and proves out custody and underwriting rails.
* **Operational effect:** Voting and veto controls are completely stripped from all 12 House desks (`/lineage/house/{id}` displays a calm **"Executive Command Mode Active — Voting Dormant"** status badge), and all voting or petition mutation endpoints reject requests fail-closed (`HTTP 403`, `EXECUTIVE_COMMAND_MODE_ACTIVE`).
* **Open study remains open:** Family members and future successors (`CHIEF_ADMIN_DEPUTY`) can still openly study the entire constitutional progression in `/companion` and these canonical manuals without seeing premature voting buttons, secrets, or live balances.

### Stage 2 — `ADVISORY_PETITION_FILTER` (Dormant Advisory Senate)
* **How it activates:** Only the Founder or certified Chief Administrator successor may transition to Stage 2 via `/dashboard` Tab 4 (`POST /api/v1/governance/mode`). Subordinate roles (`H1`, `H2`, Class T, Class F, Class M, and `CHIEF_ADMIN_DEPUTY`) fail closed (`HTTP 403`).
* **Operational effect:** Unlocks advisory `AYE` / `NAY` voting for authorized `H2` House Leaders (and any active voter seats configured on a communal body). Reaching the configured quorum (default **9 of 12 Houses / 75%**) transitions a proposal to `RATIFIED_PENDING_SETTLOR`. Ratification never moves funds unilaterally; the Chief Administrator retains **Absolute Founder Veto (`VETOED_BY_FOUNDER`)** over every advisory petition.

### Stage 3 — `BICAMERAL_VETO_ACTIVE` (Mature Binding Bicameral Veto)
* **How it activates:** Activated solely by the Chief Administrator once the lineage and enclave institutions reach constitutional maturity.
* **Operational effect:** Unlocks binding `VETO` ballots for authorized communal bodies (`can_exercise_stage3_veto = True`) and voter seats granted `can_veto = True` on eligible policy and CFCP grant proposals. Reaching the body's configured veto threshold transitions the proposal to `VETOED_BY_BICAMERAL_CHAMBER` and permanently blocks execution (`HTTP 403`, `PROPOSAL_VETOED_BY_BICAMERAL_CHAMBER`).

### Configurable FUTURE Enclave Registry (Zero Code Changes Required)
* **Data-driven communal bodies:** While the `COUNCIL_OF_12_HOUSES` (9-of-12 / 75% quorum and veto threshold) is seeded by default, the Chief Administrator can create, rename, or configure additional communal bodies at any time from `/dashboard` Tab 4 (for example, `Council of Elders` or `Enclave Stewardship Assembly`) with custom quorum and Stage 3 veto thresholds.
* **Office seats OR specific named individuals:** Voting and veto rights can be granted either to a House office (`HOUSE_OFFICE`, e.g., House `H2` Head) OR to a specific named individual (`NAMED_INDIVIDUAL` bound to `user_id` and `display_name`), and revoked with one click. Every grant, revocation, and rename is recorded in `GovernanceAuditLog`.

### Immutable Core Guardrail (Protected in ALL Modes)
No House, communal body, or named voter seat may EVER propose or amend the platform's mathematical and custodial bedrock. Proposals targeting any of the following fail closed permanently (`HTTP 403`, `IMMUTABLE_CORE_INVARIANT`) across Stages 1, 2, and 3:
1. **87/10/3 Transaction Profit Waterfall** (`ADR-008` exact integer-cent conservation)
2. **ADR-012 Per-SCMA High-Water Mark** (`0%` CFCP/FAEP skim during drawdown recovery)
3. **Rule A14 100% SCMA Loss Isolation** (zero communal loss bleed)
4. **Quarter-Kelly Risk Bounds & 5% System Risk Ceiling**
5. **3% FAEP Founder Endowment Allocation**
6. **ADR-011 Banking Air-Gap & Signed Outbox Boundary** (zero stored banking credentials)
7. **Directive R-04 Emergency Kill Switch & Sovereign Founder Immunity**

### 1-Click SHTF Snap-Back Protocol
During an acute crisis, legal threat, venue failure, or compromised committee process, the Chief Administrator may execute the **1-Click SHTF Snap-Back** (`POST /api/v1/governance/shtf-snapback`) from `/dashboard` Tab 4. Execution instantaneously returns `governance_mode` to `EXECUTIVE_COMMAND`, immediately strips voting/veto buttons from House desks, blocks voting mutations (`HTTP 403`), and records an immutable `GOVERNANCE_SHTF_SNAPBACK` entry in `GovernanceAuditLog`.

---

## 8. Apex Passphrase + MFA Command Sign-In & Lost-Device Session Revocation Checklist

**In Plain English:** Regular family members and routine officers enjoy effortless 6-digit email codes and Magic Links with zero passwords to forget. By contrast, the three highest-privilege seats—**Chief Administrator (`CHIEF_ADMIN`)**, **Chief Technical Officer (`T3`)**, and **Chief Risk Officer (`F3`)**—are permanently locked to **Command Passphrase + 6-Digit MFA** (or FIDO2/WebAuthn hardware key), and `/dashboard` Tab 4 gives you an instant **1-click Revoke Device** button whenever any relative loses a phone or leaves a shared laptop signed in.

### 8.1 Apex & Tier-3 Sign-In Guardrails (`CHIEF_ADMIN`, `T3`, `F3`)
1. **Passwordless Shortcut Blocked (`HTTP 403 · APEX_MFA_REQUIRED`):** Attempting `/api/v1/auth/request-code` for an Apex or Tier-3 email fails closed with zero codes generated and logs `AUTH_PASSWORDLESS_REJECTED_APEX` to `GovernanceAuditLog`.
2. **Command Verification (`POST /api/v1/auth/apex-login`):** Open `/login` → expand **Apex & Tier-3 Command Sign-In** → authenticate with salted PBKDF2-HMAC-SHA256 Passphrase + 6-digit MFA code (or FIDO2/WebAuthn assertion hook).
3. **Strict Session Window:** All Officers and Apex seats enforce an **8-hour absolute active window** and **30-minute idle timeout** (`pdeue_session` signed `HttpOnly`, `SameSite=Lax`, `Secure` over HTTPS).
4. **Directive R-06 Server-Side Active-Hat Rotation (`POST /api/v1/auth/switch-hat`):** Rotating between `CHIEF_ADMINISTRATOR` and `PERSONAL_SCMA` validates strictly against `auth_users.authorized_hats`, updates `auth_sessions.active_hat` server-side, and logs `ACTIVE_HAT_SWITCH`. Passwordless sessions can never escalate into Apex/Tier-3 hats.
5. **Server-Side Tenant Jailing & Supervisory Audit Lens:** Authenticated Class M sessions are strictly jailed to their own `scma_id` (`?scma_id=` tampering fails closed with `HTTP 403`). Chief Admin preserves read-only Supervisory Audit Lens inspection across subordinate portals without mutating member state.

### 8.2 Lost-Device Instant Session Revocation Checklist (Tab 4)
When a family member reports a lost phone, stolen tablet, or forgotten sign-in on a shared computer:
1. Open `/dashboard` → **Tab 4 (Governance & Dual-Control)** → scroll to **Active Family Sessions & Lost-Device Revocation** (`#active-sessions-card`) and click **Refresh Sessions** (`#btn-refresh-sessions`).
2. Locate the affected relative's `session_id`, email, `active_hat`, and `last_activity_at` timestamp.
3. Click **Revoke Device** (`POST /api/v1/auth/sessions/{session_id}/revoke`). *(Note: `CHIEF_ADMIN_DEPUTY` can inspect active sessions read-only, while revocation requires live `CHIEF_ADMIN` authority.)*
4. Confirm the status flips to **`REVOKED`** and record the `audit_event_id` logged to `GovernanceAuditLog` (`AUTH_SESSION_REVOKED`). Any subsequent request using that device's cookie fails closed immediately (`HTTP 401` on APIs / redirect to `/login?reason=session_expired` on HTML portals).
5. Reassure the relative that their SCMA capital and IFAS banking air-gap (`ADR-011`) remain completely untouched, and guide them to sign in on their new device via `/login` using a fresh 6-digit email code.

