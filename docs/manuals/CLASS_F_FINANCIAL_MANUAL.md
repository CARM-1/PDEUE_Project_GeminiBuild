# Class F Financial and Lineal Fiduciary Manual

**College:** School of Fiduciary Stewardship (Class F Lineage Advisors `F1`–`F3`)  
**Audience:** `F1` Peer Guide, `F2-H` Head of Household, `F2-A` Lineage Advisor, and `F3` Chief Risk Officer  
**Workspace:** `/advisor?role=F1`, `/advisor?role=F2-H`, `/advisor?role=F2-A`, or `/advisor?role=F3`  
**Mission:** Provide calm, least-privilege family mentoring, domestic custody protection, multi-branch advisory review, and platform-wide macro-risk supervision without blurring human authority boundaries.

---

## 1. Plain-English Overview: Phase I Paper Mode, Active Hats, and Common Rules

**In Plain English:** Today PDEUE runs in **Phase I Paper Mode**—a calm, zero-risk proving ground that reads live market prices without connecting real family bank accounts or risking real bank money. Real bank custody, tax sweeps, and our **Pay-it-Forward (`FSAP (Phase II)`)** debt-relief pool launch strictly in **Phase II** inside our physically separate **IFAS (Independent Financial Accounting System)** at `accounting.narratix.io`. As a Class F steward, your screen is tailored to one job at a time: you never wear two hats at once, you never guess what a blank or starred number means, and you never let an AI helper execute a financial decision on its own.

*(Technical & Governance Spec — Directive R-06, ADR-008, ADR-011, Directive R-12, Gate G1):*
- **Active-Hat Enforcement (`Directive R-06`):** Open `/advisor` through the approved identity flow and verify the active-hat badge (`F1_PEER_GUIDE`, `F2-H_HOUSEHOLD_HEAD`, `F2-A_LINEAGE_ADVISOR`, or `F3_CRO_RISK`) before reading or acting. Cross-tier navigation bars are stripped server-side for non-admin sessions, and attempting to jump across Class F tiers fails closed with `HTTP 403`.
- **Fail-Closed Provenance (`Gate G1`):** Execution defaults fail-closed (`HOLD_OBSERVATIONS_ONLY`, `PDEUE_VENUE_MODE=paper`, `synthetic_fills_present: False`). Distinguish unavailable from zero, unrealized from realized, staged proposal from ratified approval, and read visibility from execution authority.
- **Exact-Cent Accounting (`ADR-008`):** All authoritative monetary values, risk limits, and profit splits use 64-bit integer cents. Floating-point currency arithmetic is strictly prohibited; split components must sum to the exact settled whole.
- **Zero Banking Credentials & Air-Gapped Outbox (`ADR-011`):** PDEUE never stores bank routing numbers, bank account numbers, SWIFT codes, or banking API credentials. External accounts use opaque tokens (`EXT-REF-[ENTITY]-****[LAST4]`), and accounting instructions cross to IFAS solely through HMAC-SHA256 signed JSON-LD outbox envelopes (`/api/v1/accounting/events`, `/api/v1/accounting/reconciliation-ack`).
- **Financial Privacy Masking (`Directive R-12`):** Technical engineers (`Class T`) receive immutable server-side financial redaction (`$****.**`, `SCMA-MEM-****`) unless a temporary, audited Chief Administrator override is active for `T3`. Class F operators must never paste private balances into engineering tickets or chat to bypass `Directive R-12`.

---

## 2. The Four-Tier Class F Hierarchy (`F1` → `F2-H` → `F2-A` → `F3`)

**In Plain English:** Class F is intentionally split into four distinct roles so that friendly mentoring, household spending consent, branch-level investment advice, and platform-wide risk brakes never collapse into one unchecked person. Each tier sees only what it needs to do its job well.

| Role Tier | Everyday Title | Scope of View | Mutating / Approval Authority | Explicitly Blocked (Fail-Closed `HTTP 403`) |
| :--- | :--- | :--- | :--- | :--- |
| **`F1`** | **Peer Guide** | Assigned mentee(s) only; dollar equity & liquidity redacted (`$****.**`) | Educational guidance, literacy referrals, read-only Shadow Hunch mentoring | Zero domestic co-sign, zero risk-dial mutation, zero proposal staging, zero Shadow Hunch clearance |
| **`F2-H`** | **Head of Household** | Assigned domestic household (independent & `is_custodial` minor accounts) | Domestic `Directive R-15` Red-tier co-sign, upward risk-dial restoration (≤ 2.00% ceiling), **Step 1 Shadow Hunch domestic review** (`PENDING_F2H_CLEARANCE`) | No cross-household authority, no platform macro-risk override, no `Directive R-04` halt/resumption |
| **`F2-A`** | **Lineage Advisor** | Multi-branch assigned households (`HOUSEHOLD-ALPHA`, `HOUSEHOLD-BETA`, etc.) | Multi-branch advisory mentoring; stages **`PENDING`** rebalancing/risk proposals for `F3` review | **Strictly read-only on domestic spending co-sign**, read-only on Shadow Hunch clearance, cannot self-adjudicate staged proposals, cannot mutate risk directly |
| **`F3`** | **Chief Risk Officer (CRO)** | Platform-wide 12-House macro-risk desk, 99% VaR, venue exposure, supervisory queues | Adjudicates `F2-A` proposals (`ALLOWED` / `DENIED`), **Step 2 Shadow Hunch live clearance** (`ALLOWED` / `DENIED` / `RESCINDED`), engages **`Directive R-04` Emergency Halt** & stages dual-signature overrides | Read-only on domestic spending (cannot replace `F2-H`), cannot resume `Directive R-04` (`CHIEF_ADMINISTRATOR_ONLY`), cannot target Founder root SCMA |

---

## 3. `F1` Peer Guide — Mentee-Only Literacy & Encouragement

**In Plain English:** Think of an `F1` Peer Guide as a calm older cousin or family tutor who helps a relative learn how the system works, answers vocabulary questions, and points them to the right chapter in PDEUE University (`/companion`). Because `F1` is purely a mentor role, all household dollar totals are hidden behind stars (`$****.**`), protecting family privacy while keeping mentorship warm and focused.

*(Technical & Governance Spec):*
- **Workspace Scope:** `/advisor?role=F1` renders mentee status, custodial badges, and redacted financial placeholders (`EQUITY REDACTED ($****.**)`).
- **Zero Mutating Authority:** `F1` holds zero co-signature rights, zero risk-dial controls, zero advisory proposal staging, and strictly read-only visibility on the Shadow Hunch Clearance Queue (`HTTP 403` on any review or co-sign POST).
- **Escalation Path:** Refer household spending or risk-dial restoration questions to the member's `F2-H` Head of Household; refer multi-branch allocation questions to `F2-A`. Never attempt to reconstruct redacted balances from adjacent screens.

---

## 4. `F2-H` Head of Household — Domestic Custody, Risk Locks & Step 1 Shadow Review

**In Plain English:** The `F2-H` Head of Household is the guardian of a specific home's kitchen-table finances. Only `F2-H` can approve a household's major Red-tier withdrawal, protect minor accounts, approve turning a member's risk dial back upward after they lowered it, or give the first domestic thumbs-up on a family member's Shadow Paper hunch before it ever reaches the Chief Risk Officer.

*(Technical & Governance Spec):*
- **Head of Household Protection Rule (`F2-H` Exclusive Co-Sign):** `F2-H` alone holds co-signature authority over domestic distributions (`/api/v1/portal/advisor/co-sign`). `F2-A` and `F3` remain strictly read-only auditors on domestic distributions and receive `HTTP 403` if they attempt to co-sign.
- **Directive R-15 Three-Tier Distribution Gateway:**
  - *Green Tier (≤ \$150.00):* Autonomous member draw within policy limits.
  - *Yellow Tier (\$150.01–\$500.00):* Educational opportunity-cost Impact Card acknowledgement required.
  - *Red Tier (> \$500.00 / Principal Lock):* Mandatory **24-hour cooling time-lock** plus independent `F2-H` (and Chief Admin where required) co-signature over the exact immutable request digest. Verify beneficiary, category, exact-cent amount, custodial status, and protected liquidity floor before signing once.
- **Downward-Only Risk Dial & Custodial Minor Safeguards (`is_custodial: true`):** Members may lower their risk dial autonomously down to `0.50%`, but any upward restoration requires explicit `F2-H` review and can never exceed the certified `2.00%` ceiling. For custodial minors (`is_custodial: true`), self-service risk changes and distributions are locked; `F2-H` governs conservative `0.50%–1.00%` bounds and co-signs all sweeps.
- **Step 1 Shadow Hunch Domestic Review (`PENDING_F2H_CLEARANCE`):** Before a member's vetted `SHADOW_PAPER` idea can reach `F3`, `F2-H` inspects the dossier, confirms `STEWARDSHIP_L1_CERTIFIED` status, active non-frozen risk dial, and verifiable **Shadow Hit-Rate** track record, then either endorses (*Advance to F3 Review* → `PENDING_F3_CLEARANCE`) or denies (`DENIED`). Endorsement never executes a trade (`unilateral_execution = False`).

---

## 5. `F2-A` Lineage Advisor — Multi-Branch Advisory Mentoring & Staged Proposals

**In Plain English:** An `F2-A` Lineage Advisor serves as a multi-household strategist across assigned family branches. You can compare households in your branch, study point-in-time trade rationale, and draft structured rebalancing or risk-dial proposals—but you can never spend a household's domestic money or approve your own recommendations. Every proposal you submit waits safely in `PENDING` status for an independent `F3` Chief Risk Officer decision.

*(Technical & Governance Spec):*
- **Multi-Branch Scope:** `/advisor?role=F2-A` exposes the assigned household switcher (`HOUSEHOLD-ALPHA`, `HOUSEHOLD-BETA`, etc.), subordinate SCMA rosters, point-in-time decision audits, and the **Stage Advisory Proposal** workflow (`POST /api/v1/portal/advisor/proposals?role=F2-A`).
- **Staged Non-Executing Pipeline (`PENDING`):** Submitting a proposal creates an immutable `PENDING` artifact recording target SCMA, current vs. proposed dial within certified bounds, fiduciary justification, submitter, and UTC timestamp. `F2-A` receives `HTTP 403` if it attempts to adjudicate its own proposal (`/adjudicate`), co-sign domestic spending (`/co-sign`), mutate custodial risk directly (`/custodial-risk-dial`), or approve Shadow Hunch clearance (`/api/v1/hunch/{dossier_id}/review`).
- **Read-Only Domestic Spending Guard:** On `/advisor?role=F2-A`, every domestic distribution item displays `READ-ONLY AUDIT: F2-H SIGNATURE REQUIRED` (`aria-disabled="true"`), making the boundary between branch advice (`F2-A`) and household custody (`F2-H`) unmistakable.

---

## 6. `F3` Chief Risk Officer — Platform-Wide 12-House Macro-Risk, Adjudication & Directive R-04

**In Plain English:** The `F3` Chief Risk Officer watches the entire 12-House fleet from 30,000 feet. Instead of micromanaging household bills, `F3` monitors total family risk, cross-House concentration, and venue exposure across Kalshi and Polymarket. `F3` is the independent judge who approves or denies `F2-A` proposals, makes the final live-clearance call on F2-H-endorsed Shadow Hunches, and holds an immediate emergency brake (`Directive R-04`) if market conditions turn dangerous.

*(Technical & Governance Spec):*
- **Macro-Risk Desk (`/advisor?role=F3`):** Displays Global **99% VaR (24h)** gauge, Cross-House Gross Margin and utilization percentage, **12-House Exposure Rollup Table**, Exchange Counterparty Concentration (Kalshi vs. Polymarket; each independently rate-limited to 10 requests/second), active `Directive R-04` status, and Dual-Signature Override queue.
- **Tri-State Advisory Proposal Adjudication (`PENDING → ALLOWED / DENIED`):** `F3` evaluates `F2-A` proposals against certified ceilings, household and platform concentration, liquidity, venue exposure, and `Directive R-04` posture, issuing terminal `ALLOWED` or `DENIED` decisions (`POST /api/v1/portal/advisor/proposals/{id}/adjudicate?role=F3`). Do not silently bypass a denial; new evidence requires a new linked proposal.
- **Step 2 Shadow Hunch Live Clearance (`PENDING_F3_CLEARANCE → ALLOWED / DENIED / RESCINDED`):** `F3` (or Chief Administrator) verifies platform-wide risk limits, regulated vertical eligibility, and member Shadow Hit-Rate before recording `ALLOWED`, `DENIED`, or post-clearance `RESCINDED` via `POST /api/v1/hunch/{dossier_id}/review`. Clearance never auto-executes a live trade (`unilateral_execution = False`).
- **Directive R-04 Emergency Financial Halt & Dual-Signature Override:** `F3` may immediately engage **`Directive R-04` Emergency Halt** (`POST /api/v1/portal/advisor/emergency-halt?role=F3`) when aggregate VaR, venue distress, ledger uncertainty, or control failure threatens capital, and may stage Dual-Signature Risk Overrides (`POST /api/v1/portal/advisor/dual-signature-override?role=F3`). **Resumption (`emergency-resume`) and counter-signature are strictly reserved to the Chief Administrator (`CHIEF_ADMINISTRATOR_ONLY`, `HTTP 403` for `F3` and all subordinate roles).** Founder root identity and SCMA remain permanently immune from subordinate override targets (`FOUNDER_APEX_IMMUNITY_VIOLATION`).

---

## 7. Profit Waterfall, High-Water Mark Recovery & Loss Isolation (`ADR-012`, `Rule A14`, `ADR-008`)

**In Plain English:** Think of each member's **High-Water Mark (HWM)** as a pencil mark on a doorframe recording their account's all-time highest balance. If an account dips after a losing trade, two ironclad protections kick in: first, the loss stays **100% inside that single account** so it never drags down relatives or the shared family shield (`Rule A14`); second, as the account climbs back up to its old pencil mark, **100% of every recovery dollar stays inside that account (`0%` skim)** so members are never hit with a "volatility tax" (`ADR-012`). Only genuinely new profit above the old peak is shared 87% / 10% / 3%.

*(Technical & Governance Spec):*
- **Rule A14 (100% SCMA Loss Isolation):** Realized trading losses remain 100% contained within the executing member's SCMA. Neither sibling SCMAs nor `CFCP` or `FAEP` ever absorb individual member trading losses.
- **ADR-012 (Per-SCMA High-Water Mark):**
  - Realized recovery profit strictly at or below `high_water_mark_cents` retains `100%` in the executing SCMA (`0¢` to CFCP, `0¢` to FAEP).
  - Net new realized profit strictly above `high_water_mark_cents` splits deterministically in exact integer cents (`ADR-008`): **87% SCMA** (floor-truncated, advancing HWM to the new post-waterfall SCMA peak), **3% FAEP** (floor-truncated), and **10% + indivisible remainder cents to CFCP**.
  - Capital deposits raise HWM dollar-for-dollar (principal is never taxed as profit); authorized withdrawals reduce HWM proportionally so post-withdrawal accounts are not artificially trapped below HWM.
- **Realized Only:** Unrealized mark-to-market quotes or unsettled venue contracts are never distributable.

---

## 8. Phase I Paper Mode vs. Phase II IFAS Custody & Pay-it-Forward (`FSAP (Phase II)`)

**In Plain English:** Keep Phase I and Phase II completely distinct when speaking with family members. Today in **Phase I Paper Mode**, PDEUE is proving out real-data discipline with `$0` real bank capital connected. In **Phase II**, real bank custody activates inside our separate **IFAS** bookkeeping home (`accounting.narratix.io`), capping live venue working float at `$25,000` and launching our **Pay-it-Forward (`FSAP (Phase II)`)** debt-relief pool so stable relatives can help lift another household out of high-interest debt with zero shared trading risk.

*(Technical & Governance Spec — ADR-011 & Domain D5 `IF-038`–`IF-041`):*
- **Custodial Float Cap:** On-venue operational float is capped at **\$25,000** (`2,500,000¢`); surplus sweeps cross to IFAS solely through signed, idempotent `ADR-011` `IF-038` outbox envelopes.
- **Familial Stability Advance Pool (`FSAP (Phase II)`):** Operates as a ring-fenced sub-ledger inside IFAS alongside CFCP under contracts `IF-038`–`IF-041`. Patrons contribute variable **Contributor Participation Capital** (full principal return plus a time-weighted share of actual realized pool income—never a guaranteed fixed rate and never paid from newer deposits).
- **Three-Stage Direct-to-Creditor Relief:** Requires independent `F2-H` + Chief Administrator dual control: (1) direct-to-creditor toxic-debt payoff, (2) isolated starter SCMA seed, and (3) modest household cash cushion. PDEUE trading and the 87/10/3 waterfall remain 100% untouched; repayment occurs automatically downstream in IFAS strictly from excess cash sweeps (50% default, tunable `30%–70%` by `F2-H`). Once a relative's balance reaches `$0.00`, all obligation ends and they make *The Sovereign Choice* voluntarily.
- **Exact-Cent Amortization Discipline:** Verify creditor identity, principal in exact integer cents, approved schedule, and the 40% household dry-powder floor before every Phase II amortization event. Never describe projected debt relief as settled.

---

## 9. Dual-Lane AI Literacy, Fiduciary Copilot & Nov 2026 Regulatory Filter

**In Plain English:** Both members and Class F advisors have AI helpers—the **Dual-Lane AI Tutor** (Lane 1 Local Family Canon + Lane 2 Public Research with citations) and the **Class F Fiduciary Copilot** (What-If risk modeling and read-only audit summaries). Every AI tool follows one permanent safety law: **`unilateral_execution = False`**. An AI can explain math, model a stress scenario, or draft a proposal card, but it can never place a trade, co-sign a withdrawal, or approve a hunch. In addition, our **Nov 2026 CFTC / DEATH BETS Act** compliance filter permanently blocks prohibited contract categories before any research or shadow test can proceed.

*(Technical & Governance Spec — `AUTH-01`–`AUTH-04` & `regulatory_filter.py`):*
- **AI Authority Envelope (`unilateral_execution = False`):** All Class F Copilot outputs (`POST /api/v1/portal/advisor/copilot`) are role-scoped (`F1`/`F2-H`/`F2-A`/`F3`), compute What-If scenarios in exact integer cents (`ADR-008`), emit zero state mutations, and only stage human-confirmable `AUTH-01`–`AUTH-04` Action Cards.
- **Permitted Regulated Verticals (6 Verticals):** Weather (NOAA), Macro / CPI (BLS), Energy / EIA Storage, U.S. Treasuries, Equity Indices, and G10 FX.
- **Permanently Prohibited Categories (Fail-Closed `PROHIBITED_EVENT_CATEGORY`):** Per **Nov 2026 CFTC event-contract scope and the DEATH BETS Act**, any hypothesis or contract involving **sports/athletics**, **casino gambling**, **war or armed conflict**, **terrorism**, or **death/mortality** is rejected fail-closed across the Shadow Paper Hunch Studio and underwriting pipeline without exception.

---

## 10. Risk Reading, Routine Watch Cadence & Fiduciary Attestation

**In Plain English:** Numbers only help when you read them with calm skepticism. A sudden drop in 99% VaR can mean a missing data feed rather than safer markets; a missing House in the 12-House table is an incomplete report, never zero exposure. When in doubt, stop, preserve timestamps and identifiers, and escalate rather than improvising.

*(Technical & Governance Spec):*
- **99% VaR & 12-House Rollups:** Always read 99% VaR alongside timestamp, 24-hour horizon, data completeness, and gross (un-netted) venue exposure. Verify all 12 Houses appear once and totals reconcile in integer cents. House votes never override risk breaches or execute disbursements.
- **Directive R-04 Incident Discipline:** During an active `Directive R-04` halt, continue read-only reconciliation and evidence preservation. Never co-sign spending, approve proposals, or ask Class T engineers to restart around a financial halt.
- **Routine Review & Handoff:**
  - `F1`: assigned mentee literacy progress and referrals (zero private balances).
  - `F2-H`: pending `Directive R-15` distributions, `is_custodial` minor bounds, upward dial requests, and `PENDING_F2H_CLEARANCE` Shadow Hunches.
  - `F2-A`: branch exposure across assigned households, pending `F2-A` proposals, and point-in-time audit explanations.
  - `F3`: 99% VaR, 12-House rollups, Kalshi/Polymarket concentration, pending `F2-A` proposals, `PENDING_F3_CLEARANCE` Shadow Hunches, `Directive R-04` state, and reconciliation exceptions.
- **Fiduciary Attestation & University Alignment:** Before any material Class F act, verify: correct Active Hat (`R-06`), verified scope, fresh timestamps, exact integer cents (`ADR-008`), separation of `F2-H` domestic consent / `F2-A` non-executing staging / `F3` independent adjudication, `ADR-012` HWM & `Rule A14` integrity, `ADR-011` air-gap compliance, and zero reliance on AI prose as authorization. Completing `/companion` chapters provides curriculum readiness only—never unilateral fiduciary authority.
