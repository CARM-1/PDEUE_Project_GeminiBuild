# PDEUE Member User and Family Observer Quickstart

**Audience:** member users and authorized family observers
**Workspace:** `/member`
**Purpose:** understand personal capital without gaining administrative, technical, or fiduciary authority

## 1. What this workspace is

The Point-in-Time Deterministic Edge Underwriting Engine (PDEUE) monitors event-contract opportunities and accounts for family capital under explicit governance rules. The member workspace is the narrowest and safest view of that system. It explains one member's Separate Capital Management Account (SCMA), the protections around it, and settled results. It is not a trading terminal. Viewing a candidate, asking the tutor a question, or moving the risk governor does not grant authority to approve an order, move pooled capital, alter a model, or operate a service.

Use only your assigned identity and the link supplied by an administrator. Open `/member`; when the account selector is present, confirm that the displayed name and SCMA identifier are yours before relying on any value. A family observer may explain what is visible but must not impersonate the member or treat the screen as authority to act. Sign out, close a shared browser, and report an unexpected identity or account immediately. Never paste credentials, override tokens, private financial details, or banking data into the tutor.

Values may be marked unavailable, stale, pending, or redacted. Those labels are safety states, not zeros. Do not infer that unavailable capital has disappeared or that an empty positions list proves settlement. Refresh once, record the displayed timestamp and identifier, then ask the appropriate administrator to reconcile the authoritative ledger. Screens are explanatory projections; signed ledger events and settled records are authoritative.

## 2. Read the four-card capital grid

The top of `/member` presents four cards. Read them together rather than adding or subtracting cards casually:

1. **SCMA balance** is the private, member-attributed capital balance. It includes retained, settled proceeds assigned to the member under the waterfall. It is not necessarily all withdrawable cash: reservations, open positions, settlement timing, and policy floors can constrain availability.
2. **Active float** is capital currently deployed or available on supported venues. The system-wide custodial operating float is capped at **$25,000**. This card is not a personal spending balance, bank account, or promise that the whole amount belongs to the displayed member.
3. **CFCP shield** shows the member's informational relationship to the Central Family Capital Pool safety reserve. CFCP is a resilience layer intended to preserve the family capital floor. It is not ordinary trading margin and cannot be withdrawn merely because it appears on screen.
4. **FAEP endowment** shows the lineage-advancement allocation. The Family Advancement Endowment Pool is long-horizon family capital governed separately from the member's SCMA. Visibility does not confer withdrawal, voting, or disbursement authority.

Check the currency, as-of time, qualification state, and any status badge before comparing cards. PDEUE represents authoritative money in integer cents under **ADR-008, Exact-Cent Conservation**. ADR-008 means a settlement split must conserve every cent: the child allocations must sum exactly to the settled whole, with deterministic handling of remainder cents. Display formatting may show dollars, but operators must never recreate a ledger entry with binary floating-point arithmetic or assume a rounded display value is the accounting source.

The cards answer different questions. SCMA answers “what is attributed privately?” Active float answers “what is operationally exposed or staged?” CFCP answers “what protects the family floor?” FAEP answers “what is preserved for lineal advancement?” A card changing after settlement can be expected; a card changing without a new as-of marker or explanation should be escalated, not guessed at.

## 3. The downward-only risk governor

The risk slider is a **Downward-Only Risk Governor**, not a bid-size control. Your certified ceiling is established through underwriting and governance. A member can voluntarily reduce exposure, including to the minimum **0.5%**, because choosing more protection does not increase risk to the household. A member cannot use the slider to exceed the certified ceiling. This asymmetry prevents enthusiasm, temporary gains, or account access from silently becoming authority to risk more family capital.

For example, if a certified ceiling is 2.0%, the member may select 1.5%, 1.0%, or 0.5%. Selecting 2.5% must be rejected or clamped; it is not a request that the interface can approve. If a member has already reduced the governor to 0.5%, moving it back upward may require a separately authorized restoration and must never exceed the certified baseline. A lower setting can reduce future sizing; it does not cancel a filled position, reverse a settlement, or guarantee a particular loss limit.

Before decreasing the setting, read the current and proposed percentages, account identifier, and confirmation text. Submit once. Wait for the persisted value and status rather than clicking repeatedly. Preserve any confirmation identifier. If the old value returns after refresh, stop and report the account, time, old value, requested value, and visible message. Do not attempt to bypass the guard with developer tools or a direct API request.

The governor works alongside, rather than replacing, platform protections: Quarter-Kelly sizing, eligibility checks, liquidity checks, concentration caps, dry-powder policy, venue limits, and emergency halts. A reduced governor cannot make an ineligible contract eligible. Likewise, a platform halt can prevent new risk even when the member setting is above its minimum.

## 4. The 87/10/3 realized waterfall

PDEUE applies the waterfall to **realized, settled proceeds**, not to an attractive quote or unrealized gain. In plain English, every eligible settled gain is divided into three destinations:

* **87% to the private SCMA:** this is retained for the member's compounding balance. “Compounding” means future eligible sizing may be calculated from a larger governed base; it does not mean guaranteed returns or unrestricted cash.
* **10% to the CFCP safety shield:** this strengthens the shared capital floor and resilience reserve. It is deliberately separated from normal trading deployment.
* **3% to the FAEP endowment:** this preserves a long-term lineal allocation for education, advancement, and governed family purposes.

Imagine $100.00 of eligible realized proceeds. The conceptual destinations are $87.00, $10.00, and $3.00. For amounts that do not divide cleanly, ADR-008 supplies deterministic cent treatment so no cent is lost or invented. Never calculate an official allocation from the example; use the posted settlement event.

The waterfall is deterministic but settlement can still be pending. An order can be open, partially filled, awaiting venue confirmation, disputed, or reconciled after a correction. Unrealized profit is not distributable. Fees and settlement rules can affect the eligible net amount before the 87/10/3 split. Once posted, the allocations remain distinct: an SCMA balance is not CFCP, and FAEP is not a spare reserve.

Accounting exports are governed by **ADR-011, Signed Outbox and Custodial Boundary**. ADR-011 requires the platform to stage signed, sequenced accounting events for an approved downstream accounting process rather than store or exercise bank credentials. A visible waterfall record therefore does not mean PDEUE has transferred money to a bank. Duplicate delivery should be handled idempotently by sequence and signature, never by creating another settlement.

## 5. Positions, activity, and status language

The positions area may show contract, venue, side, quantity, average price, and realized or unrealized result. Treat venue prices as observations with timestamps. “Open” means economic exposure may remain. “Resting” means an order can still fill. “Partially filled” means neither the unfilled portion nor the filled exposure should be ignored. “Settled” should be supported by reconciliation, not assumed from market expiration.

Common safety labels have precise meanings:

* **Qualification pending** means required evidence is incomplete; it does not mean approved.
* **Redacted** means the current role is intentionally denied the underlying value.
* **Stale** means freshness policy was not met; do not make a current-state claim.
* **Halted** means some or all new financial activity is stopped pending authorized recovery.
* **Pending settlement** means the venue and internal ledger have not reached a final reconciled result.

If displayed totals appear inconsistent, do not manually “fix” them. Capture identifiers and timestamps without exposing private data, then escalate. ADR-008 conservation and ADR-011 signed outbox processing exist so reconciliation can be repeated deterministically.

## 6. Use the AI Literacy Tutor safely

The AI Literacy Tutor accepts educational questions in everyday language. Good prompts include “Why can I lower but not raise my risk governor?”, “Explain the difference between realized and unrealized results”, “What does the CFCP shield protect?”, and “Show a simple 87/10/3 example.” Ask one concept at a time and compare the answer with status labels and this manual.

The tutor is educational. It cannot approve orders, increase a risk ceiling, move capital, provide a binding fiduciary decision, reveal another member's account, unmask technical telemetry, or override a halt. A generated Action Card or suggestion is not execution. Do not interpret fluent language as a guarantee, financial advice, or an authenticated ledger statement. If the answer conflicts with a policy control, the policy control wins.

Avoid personal identifiers and secrets in prompts. Never include passwords, access tokens, exchange keys, bank details, override tokens, medical details, or another household's balances. Report a response that appears to reveal restricted information. For account-specific questions, use the displayed reference identifier and contact an authorized human rather than asking the tutor to infer missing data.

## 7. Family observer boundaries

An observer may help a member read labels, understand educational material, and identify an escalation route. Observation creates no co-signature authority. Domestic disbursement co-signature belongs to the authorized F2-H Head of Household; advisory staging, CRO adjudication, technical operations, and Chief Administrator powers remain in their own workspaces. An observer must not borrow a higher-role session or ask a higher-role user to leave one open.

Respect household separation. Do not compare screenshots across households, export another member's data, or assemble redacted values from other signals. The least-privilege rule applies even inside a family. If care or accessibility support is required, arrange an authorized workflow rather than sharing credentials.

## 8. Incident and support checklist

For a wrong identity, unexplained balance, failed downward change, or suspicious tutor response:

1. Stop; do not repeat a financial action.
2. Record UTC time, route, SCMA identifier, status text, and correlation or settlement identifier.
3. Note whether the value was unavailable, stale, redacted, pending, or settled.
4. Preserve the confirmation without copying secrets or unrelated household data.
5. Contact the authorized household or platform operator through the approved channel.
6. Follow instructions; do not attempt technical recovery yourself.

During **Directive R-04 Emergency Financial Halt**, expect new financial commitments to stop while read-only evidence may remain visible. R-04 is a financial safety boundary, not permission for a member to restart services. During **Directive R-12 Financial Masking**, technical operators see immutable redactions unless a T3 user obtains a valid, temporary Chief Administrator override. Neither directive changes what a member is authorized to do.

## 9. First-session walkthrough

Open `/member`, confirm your identity, and locate all four capital cards. Read their as-of and status indicators. Find the certified risk ceiling and current governor without changing it. Review open and settled activity, distinguishing unrealized values from realized settlement. Ask the tutor to explain the waterfall, then verify that its answer describes 87% SCMA, 10% CFCP, and 3% FAEP. Finally, identify the support route and sign out.

A successful first session ends with understanding, not action. You should know which balance is private, why pooled reserves are separate, why risk can move downward without moving above the certified ceiling, and why an educational answer cannot authorize financial activity.

## 10. Member invariants

Keep these rules visible:

* Never treat missing or redacted data as zero.
* Never treat unrealized gain as settled proceeds.
* Never raise risk above the certified ceiling; the member control is downward-only to 0.5%.
* Never treat CFCP or FAEP as a personal spending account.
* Never share credentials or secrets with the tutor or an observer.
* Never bypass a halt, role boundary, or confirmation.
* Require exact-cent, traceable settlement evidence under ADR-008.
* Remember that ADR-011 outbox events are signed accounting instructions, not bank transfers.

These constraints make the member portal intentionally calm and limited. Its purpose is to make stewardship understandable while keeping execution, infrastructure, and fiduciary powers with the people and controls certified to exercise them.

## PDEUE University curriculum alignment (Canonical Lexicon v0.5)

This manual is the field guide for the **College of Foundations (Class M — Member Users)**. Open the self-contained campus at `/companion` and complete Chapters 1, 2, and 5 before treating the member workspace as familiar. Chapter 1 demonstrates the **87/10/3 Transaction Profit Waterfall (TPW)** using integer cents: SCMA and FAEP receive their truncated shares and CFCP receives its 10% share plus every residual cent. Chapter 2 rehearses the **Downward-Only Risk Governor**: the member may reduce the dial within 0.50%–2.00%, while any increase requires F2-H approval; quarantine sets it to 0.00%. Chapter 5 teaches the **Directive R-15 Three-Tier Distribution Gateway**: Green is autonomous, Yellow adds AI educational friction, and Red imposes a 24-hour lock and dual F2-H co-signing.

The University is educational, not an authority surface. Simulator outcomes never mutate a ledger, approve a distribution, or restore risk. Complete its self-check, then follow the authenticated workflows in this manual.
