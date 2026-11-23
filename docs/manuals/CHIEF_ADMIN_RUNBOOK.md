# Chief Administrator Operational Runbook

**Audience:** Founder and Chief Administrator, the Apex Authority
**Primary workspace:** `/dashboard`
**Operating principle:** broad visibility does not eliminate deterministic controls, dual control, or audit duties

## 1. Start-of-watch procedure

Enter `/dashboard` only through the approved identity flow and confirm the active Chief Administrator hat. A founder identity in another hat is not implicitly authorized: hat selection is an auditable, least-privilege session boundary, and selecting a new hat revokes the old session. Verify UTC time, deployment identity, qualification status, data freshness, current operating mode, emergency state, open dual-control items, and reconciliation state before approving anything.

Treat “not available,” null, stale, and qualification-pending values as unavailable evidence, never as zero. The cockpit is a control surface over authoritative services; it is not itself the accounting book. Record a watch-start note with operator, release, active mode, unresolved incidents, and outstanding approvals. Never share the session or leave it unattended.

**Directive R-12 Financial Masking** remains in force across technical views: tenant balances are redacted by default, and only a T3 operator with a valid, temporary, page-scoped CA token may unmask them for an approved diagnostic purpose. The Chief Administrator authorizes that narrow visibility grant; the grant does not convey financial authority. Record its scope, expiry, and revocation, and never send the cryptographic token through chat or an incident ticket.

## 2. Operate the four-tab cockpit

### Tab 1 — Lineage Executive Overview

Use Tab 1 to establish the platform posture: total equity, unreserved cash, dry-powder status, CFCP and FAEP balances, active positions, and lineage summaries. Confirm timestamps and qualification states before comparing values. Review exceptions first. A total that cannot be tied to authoritative evidence must remain “qualification pending.” Do not replace unknowns with reassuring sample values.

The lineage tree exposes member state and governed actions. The Sovereign Settlor is protected from subordinate freeze, clamp, or revocation operations. Member-level controls must preserve household scope and the downward-only risk rule. Use the overview to identify an issue, then follow the relevant governed workflow; do not use DOM edits or direct requests as a shortcut.

### Tab 2 — Family Lineal Pools and Sub-Ledgers

Use Tab 2 to reconcile private SCMAs, CFCP safety reserves, FAEP endowment allocations, distributions, and the deterministic 87/10/3 realized waterfall governed by **ADR-012 (Per-SCMA High-Water Mark)** and **Rule A14 (100% SCMA Loss Isolation)**. Separate realized settlement from open exposure. Confirm that realized trading losses stay 100% contained inside the executing SCMA (CFCP and FAEP never decrease to absorb member trading losses), that drawdown recovery gains strictly below each SCMA's prior High-Water Mark remain 100% inside the SCMA (`0¢` CFCP/FAEP skim, eliminating the volatility tax), and that ONLY net new profit above HWM splits 87% SCMA / 10% CFCP (+ residual cents) / 3% FAEP while advancing HWM to the new post-waterfall SCMA peak. Verify that external deposits raise HWM dollar-for-dollar and authorized withdrawals adjust HWM proportionally.

**ADR-008, Exact-Cent Conservation**, requires authoritative monetary state to use 64-bit integer cents and every split to sum exactly to its source. Remainders are routed deterministically to CFCP. Never authorize a manual spreadsheet rounding adjustment. If child amounts do not equal the parent amount, quarantine the event and open an accounting incident.

### Tab 3 — Velocity Radar and Scanner

Use Tab 3 to inspect native evidence from weather, crypto, macro, and sports domains, including source provenance, freshness, eligibility, model probability, venue price, edge, and reason codes. A candidate is research until all admission gates pass. Missing probabilities and pending qualification are not invitations to estimate values manually.

Confirm circuit-breaker state, liquidity protection, concentration, dry powder, venue health, and order capacity before ratifying an execution Action Card. The AI Copilot can assemble a dossier; it cannot place an order or change risk unilaterally. Preserve the candidate and packet identifiers so a later fill or rejection can be traced to point-in-time evidence.

### Tab 4 — Governance and Dual-Control

Use Tab 4 for Action Cards, emergency state, lineage petitions, approval queues, and audit evidence. Review requested action, initiator, scope, affected capital, expiration, evidence digest, required authorities, and current state. Reject expired, altered, ambiguous, or cross-tenant cards. Never approve a card merely because the Copilot produced it.

Lineage proposals reaching the cockpit may have satisfied a House vote threshold, but “ratified pending settlor” is not executed. Review the proposal, roll call, purpose, exact amount, destinations, and required second control. Preserve veto and denial reasons as durable records.

## 3. AUTH-01 through AUTH-04 Action Card ratification

The authorization series is a deterministic lifecycle, not four interchangeable titles:

* **AUTH-01 — authenticated initiation.** A specifically authorized human initiates a typed Action Card. The record binds actor, active hat, action, target, parameters, timestamp, and evidence. AI output alone cannot satisfy AUTH-01.
* **AUTH-02 — independent quorum or co-signature.** A second authorized principal reviews the same immutable payload. Approval must be independent; credential sharing, self-co-signing, or approval of a changed digest is invalid.
* **AUTH-03 — policy and state admission.** Deterministic guards evaluate tenant scope, operating mode, risk envelope, liquidity, concentration, freshness, idempotency, and any directive. A human preference cannot turn a failed gate into a pass.
* **AUTH-04 — execution receipt and audit closure.** The executor records the final decision, effect, authoritative identifiers, timestamps, and before/after state. A timeout or unknown result must be reconciled before retry. AUTH-04 closes the chain; it must not fabricate success.

Read the complete payload at every stage. If a parameter changes, invalidate prior approval and begin again. Use unique action and idempotency identifiers. Denial is a normal safe outcome. The chain embodies the unilateral-AI-execution prohibition: generated recommendations remain proposals until humans and policy ratify them.

## 4. Directive R-04 versus technical service halts

**Directive R-04 Emergency Financial Halt** is the financial failsafe. Invoke it when continued commitment, sizing, dispatch, settlement release, or disbursement could threaten capital or governance: unexplained ledger divergence, compromised financial authority, material risk breach, stale market truth during active exposure, or failed control evidence. R-04 must stop new financial risk and fail closed. Record actor, UTC time, reason, scope, impacted identifiers, and evidence.

A **technical service halt** stops a worker, scheduler, connector, or internal loop to contain a software or infrastructure fault. T2/T3 technical operators may operate services within their claim, but they cannot use a service restart to authorize finance. Stopping a scanner does not necessarily cancel venue orders, move funds, adjudicate a proposal, or assert settlement. The system-halt contract explicitly does not imply external network cancellation.

When uncertain, protect capital: impose R-04 and separately coordinate the technical containment. Keep the states distinct in the incident record. A healthy service does not clear R-04, and clearing R-04 does not prove services healthy. Recovery requires financial authorization for the financial boundary and technical validation for the service boundary.

R-04 recovery checklist: identify root cause; reconcile open orders and venue positions; verify ADR-008 balances; inspect pending ADR-011 events; confirm secrets and identities; run approved tests; obtain required dual control; issue a fresh recovery card; restore in stages; monitor; and close through AUTH-04. Never disengage a kill switch with one credential.

## 5. FBO custodial architecture

PDEUE operates within a **for-benefit-of (FBO) custodial architecture**. Member attribution remains in separate SCMA sub-ledgers while limited operational float may be placed with approved venues. The platform is not a general bank and does not store online-banking credentials. Segregation, attribution, and signed accounting instructions preserve the boundary among private SCMA capital, CFCP reserves, FAEP endowment, and venue float.

The operational float high-water mark is **$25,000**. Amounts above the cap are not extra trading capacity. The FloatSweepMonitor stages an accounting sweep so excess can return through the governed custodial process. Confirm settled balance, reserved amounts, venue reconciliation, sweep amount, SCMA identifier, and duplicate status before approval. Never split a sweep to evade review.

**ADR-011, Signed Accounting Outbox and Custodial Boundary**, requires sequenced, signed envelopes sent to an approved downstream accounting function. Payloads may contain accounting facts and destinations, but prohibited banking credentials must never appear. Validate signature, sequence, schema, source event, integer-cent amount, and idempotency key. Pending means staged, emitted means available for delivery, delivered means acknowledged; none alone proves a bank settled the transfer.

For an ADR-011 sweep approval: reconcile the venue and internal ledger; calculate excess over $25,000 in integer cents; inspect the generated event; obtain required approvals; dispatch through the approved adapter; verify acknowledgement; and reconcile the downstream result. Retry by idempotency key, never by producing a new economic event. Quarantine signature failures, gaps, unexpected fields, or divergent acknowledgements.

## 6. Sovereign Settlor and Lineage House dual control

The 12 Houses can deliberate and ratify a petition according to the established threshold. Ratification stages a request; it does not disburse money. The Sovereign Settlor holds apex adjudication and immunity from subordinate control. This authority must be exercised through recorded controls, not informal instruction.

For a Lineage House disbursement, verify proposal identity, eligible votes, threshold, amount, source pool, beneficiary, purpose, conflicts, and exact-cent accounting. The first authorized control attests the proposal and evidence. The independent second control co-signs the identical digest. The Sovereign Settlor then approves and executes or vetoes through the governed action. If any amount, beneficiary, or purpose changes, prior signatures are void.

Never let a House vote, F2-H domestic co-signature, F2-A proposal, F3 risk decision, or technical override substitute for Settlor authorization. Conversely, Settlor authority does not erase ADR-008 conservation, ADR-011 outbox controls, sanctions or legal constraints, or an active R-04 halt. Preserve dissent and veto reasoning.

## 7. Routine operating cadence

At watch start, establish identity and state. During the watch, review exception queues, reconciliation, worker freshness, venue concentration, risk limits, stale data, proposals, and outbox gaps. Before every approval, use the four AUTH checks. At watch end, record open exposure, resting orders, pending settlements, active halts, unacknowledged outbox entries, dual-control items, and the next accountable owner.

For daily reconciliation, compare venue positions with internal position books; compare settled proceeds with waterfall entries; verify SCMA, CFCP, and FAEP conservation; inspect the $25,000 float cap; and confirm contiguous ADR-011 sequences. Investigate mismatches instead of netting them away.

## 8. Incident playbooks

### Ledger mismatch

Invoke R-04 if the mismatch can affect new risk. Freeze retries, preserve source records, compare event sequence and signature, verify integer cents, identify the last reconciled point, and assign accounting and technical owners. Correct through an auditable compensating event, never by editing history.

### Venue ambiguity

Stop new dispatch to the affected venue. Preserve request identifiers and timestamps. Query through the approved adapter and reconcile fills before cancellation or replacement. Remember that an internal halt does not authorize or prove external cancellation.

### Suspected credential compromise

Halt affected finance, revoke sessions and secret leases, rotate through the secrets process, inspect access logs, reconcile activity, and require fresh dual control. Never place credentials in an incident ticket or Copilot prompt.

### Outbox backlog

Keep economic events immutable, determine whether failure is generation, dispatch, or acknowledgement, verify sequence continuity and signatures, then replay idempotently. Do not increase venue float above the cap while hoping delivery catches up.

## 9. Prohibited shortcuts

Do not approve your own second-control step, reuse an override token, treat AI prose as authorization, infer zero from null, edit balances directly, suppress reason codes, restart around R-04, store banking credentials, send unsigned accounting instructions, exceed the float cap, or claim external cancellation from an internal service response. Do not let urgency collapse financial and technical authority into one role.

## 10. End-of-watch attestation

Before handoff, attest that the active mode and R-04 state are explicit; all material amounts use reconciled integer cents; outstanding Action Cards identify their AUTH stage; Lineage House items show vote and Settlor status; float and outbox items are accounted for; secrets were not exposed; and the next operator has received a read-only summary through the approved channel. A safe handoff names uncertainty rather than hiding it.

The Apex Authority is strongest when it remains constrained and reproducible. The cockpit supplies breadth, while AUTH-01 through AUTH-04, dual control, ADR-008, ADR-011, R-04, and role separation make every material act explainable after the fact.

## PDEUE University curriculum alignment (Canonical Lexicon v0.5)

This runbook is the field guide for the **Apex School of Sovereign Governance (Executive Chancellor Cockpit)**. The `/companion` campus rehearses the six canonical controls without changing production state. Use it for onboarding and recurrent qualification, never as approval evidence by itself.

Emergency authority remains deliberately split. **Directive R-04** is the financial kill-switch: fail closed, prevent new commitments, preserve evidence, reconcile, and require governed dual-control recovery. A **T3 override** is a narrow, expiring, CA-authorized visibility grant under R-12; it may unmask only the approved diagnostic scope and can neither move funds nor clear R-04. For **mass onboarding**, validate the signed roster, House and role mappings, duplicate identities, SCMA segregation, custodial F2-H assignments, default downward-only ceilings, and exact-cent opening totals in a dry run. Require an independent count-and-digest review, stage bounded batches, reconcile each batch, quarantine exceptions, and retain rollback and audit evidence before activating identities.

## 11. Three-Stage Governance Lifecycle & FUTURE Enclave Charter (Executive Command -> Advisory Filter -> Configurable Bicameral Veto & SHTF Protocol)

PDEUE is built to mature peacefully across generations without exposing the family treasury to premature committee politics during its fledgling years or freezing decision-making during a crisis. Governance therefore operates through **three explicit, Chief-Administrator-controlled stages** backed by relational persistence (`governance_config`, `governance_bodies`, `governance_voter_seats`, `governance_petitions`, `governance_votes`) and an append-only `GovernanceAuditLog`:

### Stage 1 — `EXECUTIVE_COMMAND` (Default Fledgling & SHTF Mode)
* **Why it is the default:** Every fresh deployment starts fail-closed in `EXECUTIVE_COMMAND` while the family establishes operational discipline, completes PDEUE University literacy certification, and proves out custody and underwriting rails.
* **Operational effect:** Voting and veto controls are completely stripped from all 12 House desks (`/lineage/house/{id}` displays a calm **"Executive Command Mode Active — Voting Dormant"** status badge), and all voting or petition mutation endpoints reject requests fail-closed (`HTTP 403`, `EXECUTIVE_COMMAND_MODE_ACTIVE`).
* **Open study remains open:** Family members and future successors can still openly study the entire constitutional progression in `/companion` and these canonical manuals without seeing premature voting buttons, secrets, or live balances.

### Stage 2 — `ADVISORY_PETITION_FILTER` (Dormant Advisory Senate)
* **How it activates:** Only the Founder or certified Chief Administrator successor may transition to Stage 2 via `/dashboard` Tab 4 (`POST /api/v1/governance/mode`). Subordinate roles (`H1`, `H2`, Class T, Class F, Class M) fail closed (`HTTP 403`).
* **Operational effect:** Unlocks advisory `AYE` / `NAY` voting for authorized `H2` House Leaders (and any active voter seats configured on a communal body). Reaching the configured quorum (default **9 of 12 Houses / 75%**) transitions a proposal to `RATIFIED_PENDING_SETTLOR`. Ratification never moves funds unilaterally; the Chief Administrator retains **Absolute Founder Veto (`VETOED_BY_FOUNDER`)** over every advisory petition.

### Stage 3 — `BICAMERAL_VETO_ACTIVE` (Mature Binding Bicameral Veto)
* **How it activates:** Activated solely by the Chief Administrator once the lineage and enclave institutions reach constitutional maturity.
* **Operational effect:** Unlocks binding `VETO` ballots for authorized communal bodies (`can_exercise_stage3_veto = True`) and voter seats granted `can_veto = True` on eligible policy and CFCP grant proposals. Reaching the body's configured veto threshold transitions the proposal to `VETOED_BY_BICAMERAL_CHAMBER` and permanently blocks execution (`HTTP 403`, `PROPOSAL_VETOED_BY_BICAMERAL_CHAMBER`).

### Configurable FUTURE Enclave Registry (Zero Code Changes Required)
* **Data-driven communal bodies:** While the `COUNCIL_OF_12_HOUSES` (9-of-12 / 75% quorum and veto threshold) is seeded by default, the Chief Administrator can create, rename, or configure additional communal bodies at any time from `/dashboard` Tab 4 (for example, `Council of Elders` or `Enclave Stewardship Assembly`) with custom quorum and Stage 3 veto thresholds.
* **Office seats OR specific named individuals:** Voting and veto rights can be granted either to a House office (`HOUSE_OFFICE`, e.g., House `H2` Head) OR to a specific named individual (`NAMED_INDIVIDUAL` bound to `user_id` and `display_name`), and revoked with one click. Every grant, revocation, and rename is recorded in `GovernanceAuditLog`.

### Immutable Core Guardrail (Protected in ALL Modes)
No House, communal body, or named voter seat may EVER propose or amend the platform's mathematical and custodial bedrock. Proposals targeting any of the following fail closed permanently (`HTTP 403`, `IMMUTABLE_CORE_INVARIANT`) across Stages 1, 2, and 3:
1. **87/10/3 Transaction Profit Waterfall** (ADR-008 exact integer-cent conservation)
2. **ADR-012 Per-SCMA High-Water Mark** (0% CFCP/FAEP skim during drawdown recovery)
3. **Rule A14 100% SCMA Loss Isolation** (zero communal loss bleed)
4. **Quarter-Kelly Risk Bounds & 5% System Risk Ceiling**
5. **3% FAEP Founder Endowment Allocation**
6. **ADR-011 Banking Air-Gap & Signed Outbox Boundary** (zero stored banking credentials)
7. **Directive R-04 Emergency Kill Switch & Sovereign Founder Immunity**

### 1-Click SHTF Snap-Back Protocol
During an acute crisis, legal threat, venue failure, or compromised committee process, the Chief Administrator may execute the **1-Click SHTF Snap-Back** (`POST /api/v1/governance/shtf-snapback`) from `/dashboard` Tab 4. Execution instantaneously returns `governance_mode` to `EXECUTIVE_COMMAND`, immediately strips voting/veto buttons from House desks, blocks voting mutations (`HTTP 403`), and records an immutable `GOVERNANCE_SHTF_SNAPBACK` entry in `GovernanceAuditLog`.

