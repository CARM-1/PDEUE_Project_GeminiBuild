# PDEUE Member User and Family Observer Quickstart

**Audience:** member users and authorized family observers
**Workspace:** `/member`
**Purpose:** understand personal capital without gaining administrative, technical, or fiduciary authority

## 1. What This Workspace Is (Phase I Paper Mode & Safe View)

The Public Data Event Underwriting Engine (PDEUE) monitors regulated event-contract opportunities and accounts for family capital under explicit governance rules. Today the platform operates in **Phase I Paper Mode**—a calm, zero-risk flight-simulator proving ground using real market prices with zero live bank money connected. The member workspace is the narrowest and safest view of that system. It explains one member's Separate Capital Management Account (SCMA), the protections around it, and settled results. It is not a trading terminal. Viewing a candidate, asking the AI Tutor a question, testing a Shadow Paper hunch, or lowering the risk governor does not grant authority to approve a live order, move pooled capital, alter a model, or operate a service.

Use only your assigned identity and the link supplied by an administrator. Open `/member`; when the account selector is present, confirm that the displayed name and SCMA identifier are yours before relying on any value. A family observer may explain what is visible but must not impersonate the member or treat the screen as authority to act. Sign out, close a shared browser, and report an unexpected identity or account immediately. Never paste credentials, override tokens, private financial details, or banking data into the tutor.

Values may be marked unavailable, stale, pending, or redacted. Those labels are safety states, not zeros. Do not infer that unavailable capital has disappeared or that an empty positions list proves settlement. Refresh once, record the displayed timestamp and identifier, then ask the appropriate administrator to reconcile the authoritative ledger. Screens are explanatory projections; signed ledger events and settled records are authoritative.

## 2. Reading Your Four Capital Cards at a Glance

The top of `/member` presents four cards. Read them together rather than adding or subtracting cards casually:

1. **SCMA balance** is your own private, walled-off family account. Like watertight compartments on a ship, it holds retained, settled proceeds assigned to you under the profit waterfall. It is not necessarily all withdrawable cash: reservations, open positions, settlement timing, and policy floors can constrain availability.
2. **Active float** is capital currently deployed or staged on supported venues. Like a cash-register drawer kept intentionally nimble, the custodial operating float is hard-capped at **$25,000** so orders stay sharp and surplus gains sweep automatically to protected bank custody. This card is not a personal spending balance, bank account, or promise that the whole amount belongs to the displayed member.
3. **CFCP shield** shows your informational relationship to the Central Family Capital Pool safety reserve. CFCP is a shared resilience layer intended to preserve the family capital floor and support Phase II debt-relief stewardship. It is not ordinary trading margin, never absorbs individual trading losses, and cannot be withdrawn merely because it appears on screen.
4. **FAEP endowment** shows the lineage-advancement and platform-stewardship allocation. The Family Advancement Endowment Pool pays for infrastructure and long-horizon family purposes governed separately from your personal SCMA. Visibility does not confer withdrawal, voting, or disbursement authority.

Check the currency, as-of time, qualification state, and any status badge before comparing cards. *(Technical note — **ADR-008 Exact-Cent Conservation**)*: PDEUE represents authoritative money strictly in 64-bit integer cents so that every settlement split conserves every single penny—the child allocations always sum exactly to the settled whole, with deterministic handling of remainder cents. Display formatting may show dollars, but operators must never recreate a ledger entry with binary floating-point arithmetic or assume a rounded display value is the accounting source.

The cards answer different questions. SCMA answers “what is attributed privately?” Active float answers “what is operationally exposed or staged?” CFCP answers “what protects the family floor?” FAEP answers “what is preserved for lineal advancement and platform care?” A card changing after settlement can be expected; a card changing without a new as-of marker or explanation should be escalated, not guessed at.

## 3. Your Brake Pedal: The Downward-Only Risk Governor & 40% Cash Cushion

Think of the risk slider as your personal **brake pedal** (formally the **Downward-Only Risk Governor**), not a bid-size control. Your certified ceiling is established through underwriting and governance. A member can voluntarily reduce exposure anytime—down to the minimum **0.5%**—because choosing more protection never increases risk to the household. To guard against heat-of-the-moment choices, a member cannot use the slider to push above the certified ceiling.

For example, if a certified ceiling is 2.0%, the member may select 1.5%, 1.0%, or 0.5% instantly without asking permission. Selecting 2.5% must be rejected or clamped; it is not a request that the interface can approve. If a member has already reduced the governor to 0.5%, turning it back upward requires an authorized restoration from the **F2-H Head of Household** and must never exceed the certified baseline. A lower setting reduces future sizing; it does not cancel a filled position, reverse a settlement, or guarantee a particular loss limit.

Before decreasing the setting, read the current and proposed percentages, account identifier, and confirmation text. Submit once. Wait for the persisted value and status rather than clicking repeatedly. Preserve any confirmation identifier. If the old value returns after refresh, stop and report the account, time, old value, requested value, and visible message. Do not attempt to bypass the guard with developer tools or a direct API request.

The governor works alongside, rather than replacing, platform protections: conservative **Quarter-Kelly** sizing, eligibility checks, liquidity checks, concentration caps, the mandatory **40% Dry-Powder Cash Cushion**, venue limits, and emergency halts. A reduced governor cannot make an ineligible contract eligible. Likewise, a platform halt can prevent new risk even when the member setting is above its minimum.

## 4. Keeping What You Earn: The 87/10/3 Profit Waterfall & High-Water Mark

Picture your personal **High-Water Mark (HWM)** like a pencil mark on a doorframe recording your account's all-time high balance. PDEUE applies the 87/10/3 profit waterfall strictly to **realized, settled net new profit above your SCMA's prior High-Water Mark**—never to unrealized quotes and never while recovering from a dip. *(Technical note — **ADR-012 Per-SCMA High-Water Mark** & **Rule A14 100% SCMA Loss Isolation**)*: under Rule A14, any realized trading loss stays 100% contained inside the executing SCMA—like watertight rooms on a ship, neither sibling SCMAs nor CFCP or FAEP ever decrease to absorb an individual trading loss.

When a member's SCMA is recovering from a prior loss and its post-trade equity remains at or below its High-Water Mark, **100% of every recovery dollar stays inside the SCMA** (`$0.00` to CFCP and `$0.00` to FAEP). This High-Water Mark rule eliminates the hidden 13% "volatility tax" during choppy or flat recovery stretches. Once settled profit pushes the SCMA above its prior High-Water Mark, ONLY the net new profit strictly above HWM is divided into three destinations:

* **87% to your private SCMA:** retained for your personal compounding balance and advances your SCMA's High-Water Mark to the new post-waterfall equity peak. “Compounding” means future eligible sizing may be calculated from a larger governed base; it does not mean guaranteed returns or unrestricted cash.
* **10% to the CFCP family safety shield (+ residual cents):** strengthens the shared capital floor and resilience reserve. *(Technical note — **ADR-008**)*: SCMA (87%) and FAEP (3%) are floor-truncated in exact integer cents, and any indivisible remainder cents route to CFCP. CFCP is deliberately separated from normal trading deployment and never absorbs individual SCMA trading losses.
* **3% to the FAEP endowment:** preserves a long-term lineal allocation for platform servers, verified public data feeds, education, and governed family purposes—so family members pay `$0` out-of-pocket monthly bills.

Imagine an account at its High-Water Mark that earns $100.00 of eligible realized net new profit. The destinations are $87.00 to SCMA (raising HWM by $87.00), $10.00 to CFCP, and $3.00 to FAEP. By contrast, if that account first lost $50.00 (100% inside SCMA; CFCP and FAEP unchanged) and then won $50.00, 100% of the $50.00 recovery stays in SCMA with $0.00 split to CFCP or FAEP. Capital deposits raise HWM dollar-for-dollar (new deposits are principal, not profit), and authorized withdrawals adjust HWM proportionally so accounts are not artificially trapped below HWM. Never calculate an official allocation from an illustration; use the posted settlement event.

The waterfall is deterministic, but settlement can still be pending. An order can be open, partially filled, awaiting venue confirmation, disputed, or reconciled after a correction. Unrealized profit is not distributable. Fees and settlement rules can affect the eligible net amount before the 87/10/3 HWM split. Once posted, the allocations remain distinct: an SCMA balance is not CFCP, and FAEP is not a spare reserve.

*(Technical note — **ADR-011 Signed Outbox & Banking Safety Wall**)*: PDEUE never asks for, stores, or exercises bank routing numbers, bank account numbers, or banking logins. Instead, the trading engine stages HMAC-SHA256 signed, sequenced accounting notices for the separate Independent Financial Accounting System (IFAS). A visible waterfall record therefore does not mean PDEUE has transferred money to a bank. Duplicate delivery is handled idempotently by sequence and signature, never by creating another settlement.

## 5. Reading Positions, Activity, and Calm Safety Labels

The positions area may show contract, venue, side, quantity, average price, and realized or unrealized result. Treat venue prices as observations with timestamps. “Open” means economic exposure may remain. “Resting” means an order can still fill. “Partially filled” means neither the unfilled portion nor the filled exposure should be ignored. “Settled” should be supported by reconciliation, not assumed from market expiration.

Common safety labels have precise meanings:

* **Qualification pending** means required evidence is incomplete; it does not mean approved.
* **Redacted** means the current role is intentionally denied the underlying value.
* **Stale** means freshness policy was not met; do not make a current-state claim.
* **Halted** means some or all new financial activity is stopped pending authorized recovery.
* **Pending settlement** means the venue and internal ledger have not reached a final reconciled result.

If displayed totals appear inconsistent, do not manually “fix” them. Capture identifiers and timestamps without exposing private data, then escalate. ADR-008 conservation and ADR-011 signed outbox processing exist so reconciliation can be repeated deterministically.

## 6. Using the Dual-Lane AI Literacy Tutor Safely

The **Dual-Lane AI Literacy Tutor** is live today on both `/member` and `/community` and accepts educational questions in everyday language. Think of it like a helpful librarian with **two clearly labeled shelves**:

1. **Lane 1 — Local Family Canon (`LANE 1 · LOCAL PDEUE CANON`):** Answers questions about PDEUE rules, your 87/10/3 waterfall, High-Water Mark protection, the 40% cash cushion, role boundaries, and withdrawal tiers strictly from our verified local manuals and canonical Lexicon. Good prompts include “Why can I lower but not raise my risk governor?”, “Explain the 87/10/3 waterfall simply”, “How does the High-Water Mark protect me?”, and “What happens if I withdraw $100 from my seed?”
2. **Lane 2 — Public Market Research with Citations (`LANE 2 · PUBLIC RESEARCH`):** Answers broader public-world questions about economics, inflation (CPI), NOAA weather markets, energy inventories, Treasury yields, or G10 FX using read-only public research with **visible source citations**. Lane 2 responses are labeled as *General Public Market Education — Not Financial Advice* and remain strictly isolated from private family ledgers.

Across **both lanes**, the tutor enforces **`unilateral_execution = False`** (`AUTH-01`–`AUTH-04`). It is strictly educational: it cannot approve orders, place trades, increase a risk ceiling, move capital, provide a binding fiduciary decision, reveal another member's account, unmask technical telemetry, or override a halt. A generated Action Card or Yellow-Tier Impact Card preview is never execution. If an AI answer ever conflicts with a policy control, the policy control always wins.

Avoid personal identifiers and secrets in prompts. Never include passwords, access tokens, exchange keys, bank details, override tokens, medical details, or another household's balances. Report a response that appears to reveal restricted information. For account-specific questions, use the displayed reference identifier and contact an authorized human rather than asking the tutor to infer missing data.

## 6A. Testing Ideas Safely: How to Run the Shadow Paper Hunch Studio

If you notice real-world public news—like an extreme heat wave, an upcoming inflation release, or a natural-gas inventory shift—you can test your own market idea risk-free inside the **Shadow Paper Hunch Studio** right on `/member` (under *Live Trading Engine* → *Shadow Paper Hunch Studio (Zero-Risk Practice)*). Shadow Paper mode runs permanently on 100% virtual pretend dollars (`SHADOW_PAPER`), never touches real SCMA cash or IFAS bank records, and preserves `unilateral_execution = False` (members never have an impulsive solo "Buy" button).

Follow these **four simple steps**:

1. **Step 1 — Write a Grounded Hypothesis (or Click *Load Example Hunch*):**
   Describe an objectively verifiable real-world event in one of **six regulated verticals**: **Weather (NOAA)**, **Macro / CPI (BLS)**, **Energy / EIA Storage**, **U.S. Treasuries**, **Equity Indices**, or **G10 FX**. If you want to test-drive the studio in one click without guessing, click **Load Example Hunch** to pre-fill a clean worked example:
   * *Worked Example:* `"NOAA forecasts a 95°F heat wave in Phoenix this week, making the high-temp contract underpriced at 42¢"` — Vertical: `WEATHER`, Modeled Fair Value: `58¢`, Market Quote: `42¢`, Fee Friction: `2¢` → Net Edge: `+14¢` (`58¢ - 42¢ - 2¢ = +14¢`, calculated in exact whole cents).
   * *Automatically Blocked Categories (Nov 2026 CFTC Event-Contract Scope & DEATH BETS Act):* **Sports/athletics**, **casino gambling**, **war or armed conflict**, **terrorism**, and **death/mortality wagers** are permanently blocked fail-closed.
2. **Step 2 — Run the 3-Point Check (*Run 3-Point Validation Audit*):**
   The studio automatically runs three checks—(1) public fact corroboration, (2) regulated contract & oracle mapping, and (3) exact-cent edge after fees—and displays a clear status badge:
   * **`VALIDATED` (`VALIDATED_SHADOW_READY`):** Positive exact-cent edge after fees; cleared for zero-risk Shadow Paper practice.
   * **`REJECTED_NO_EDGE`:** The exact-cent math does not beat fees and spread (net edge ≤ `0¢`); the studio explains why in plain English so you never chase an overpriced contract.
   * **`PROHIBITED_EVENT_CATEGORY`:** Blocked automatically because the topic falls into a prohibited regulatory category (sports, casino, war, terrorism, or death).
3. **Step 3 — Log a Zero-Risk Shadow Paper Bid (*Place Shadow Paper Bid*):**
   Once validated, enter a virtual practice stake (for example `10000` cents = `$100.00` virtual) and click **Place Shadow Paper Bid (Zero Risk)**. Every virtual bid tracks against real market prices with `$0.00` real cash touched and builds your verifiable **Shadow Hit-Rate** track record inside your personal dossier list.
4. **Step 4 — Optional Live Clearance (*Request Live Clearance*):**
   Shadow practice alone never moves real money. To petition for higher-authority review of a vetted shadow idea for real SCMA consideration, **all three safeguards** must be met:
   * **(a) Stewardship Certification:** You hold an active `STEWARDSHIP_L1_CERTIFIED` badge from PDEUE University (`/companion`).
   * **(b) Active Risk Dial:** Your member risk governor is active and non-frozen.
   * **(c) Two-Step Human Review:** Your petition enters **Step 1 (`PENDING_F2H_CLEARANCE`)**, where your **F2-H Head of Household** reviews domestic suitability and your Shadow Hit-Rate to either endorse (*Advance to F3 Review*) or deny it. Endorsed petitions advance to **Step 2 (`PENDING_F3_CLEARANCE`)**, where the **F3 Chief Risk Officer** or **Chief Administrator** checks platform-wide risk limits and issues a final **`ALLOWED`**, **`DENIED`**, or post-clearance **`RESCINDED`** determination. F1 Peer Guides and F2-A Lineage Advisors remain strictly read-only throughout.

## 7. Family Observer Boundaries

An observer may help a member read labels, understand educational material, and identify an escalation route. Observation creates no co-signature authority. Domestic disbursement co-signature belongs to the authorized F2-H Head of Household; advisory staging, CRO adjudication, technical operations, and Chief Administrator powers remain in their own workspaces. An observer must not borrow a higher-role session or ask a higher-role user to leave one open.

Respect household separation. Do not compare screenshots across households, export another member's data, or assemble redacted values from other signals. The least-privilege rule applies even inside a family. If care or accessibility support is required, arrange an authorized workflow rather than sharing credentials.

## 8. When Something Looks Off: Calm Support Checklist

For a wrong identity, unexplained balance, failed downward change, or suspicious tutor response:

1. Stop; do not repeat a financial action.
2. Record UTC time, route, SCMA identifier, status text, and correlation or settlement identifier.
3. Note whether the value was unavailable, stale, redacted, pending, or settled.
4. Preserve the confirmation without copying secrets or unrelated household data.
5. Contact the authorized household or platform operator through the approved channel.
6. Follow instructions; do not attempt technical recovery yourself.

*(Technical notes — **Directive R-04** & **Directive R-12**)*: During **Directive R-04 Emergency Financial Halt**, expect new financial commitments to stop while read-only evidence may remain visible; R-04 is a financial safety boundary, not permission for a member to restart services. During **Directive R-12 Financial Masking**, technical operators see immutable star-masked balances (`$****.**`) unless a T3 user obtains a valid, temporary Chief Administrator override. Neither directive changes what a member is authorized to do.

## 9. Your First 5-Minute Walkthrough

Open `/member`, confirm your identity, and locate all four capital cards. Read their as-of and status indicators. Find your certified risk ceiling and current brake-pedal governor without changing it. Review open and settled activity, distinguishing unrealized values from realized settlement. Ask the Dual-Lane AI Tutor to explain the waterfall, then verify that its answer describes 87% SCMA, 10% CFCP, and 3% FAEP. Next, open the Shadow Paper Hunch Studio, click **Load Example Hunch**, and run one zero-risk 3-Point Validation Audit to see how exact-cent edge math works. Finally, identify the support route and sign out.

A successful first session ends with understanding, not live capital movement. You should know which balance is private, why pooled reserves are separate, why risk can move downward without moving above the certified ceiling, why Shadow Paper bids never touch real money, and why an educational answer cannot authorize financial activity.

## 10. Core Member Promises & Guardrails

Keep these rules visible:

* Never treat missing or redacted data as zero.
* Never treat unrealized gain as settled proceeds.
* Never raise risk above the certified ceiling; the member brake pedal is downward-only to 0.5%.
* Never treat CFCP or FAEP as a personal spending account.
* Never share credentials or secrets with the tutor or an observer.
* Never bypass a halt, role boundary, or confirmation.
* Require exact-cent, traceable settlement evidence *(technical standard: **ADR-008**)*.
* Remember that signed accounting notices *(technical standard: **ADR-011**)* are bookkeeping instructions for IFAS, not bank transfers.

These constraints make the member portal intentionally calm and limited. Its purpose is to make stewardship understandable while keeping execution, infrastructure, and fiduciary powers with the people and controls certified to exercise them.

## PDEUE University Curriculum Alignment

This manual is the plain-English field guide for the **College of Foundations (Class M — Member Users)** and aligns with **Canonical Lexicon v0.5 / v0.6**. Open the self-contained campus at `/companion` and walk through **Chapter 0** (Phase I Paper Mode Orientation) plus **Chapters 1–6** before treating the member workspace as familiar:

* **Chapter 1** demonstrates the **87/10/3 Transaction Profit Waterfall (TPW)** *(ADR-008 & ADR-012)* in integer cents: drawdown recovery below each SCMA's prior High-Water Mark stays 100% in the SCMA (`0¢` CFCP/FAEP skim, eliminating the volatility tax), while net new profit above HWM allocates floor-truncated 87% SCMA and 3% FAEP shares with CFCP receiving 10% plus every residual cent.
* **Chapter 2** rehearses your **Brake Pedal (Downward-Only Risk Governor)**: reduce the dial anytime within 0.50%–2.00%, while any upward turn requires F2-H approval and quarantine sets it to 0.00%.
* **Chapter 3** demonstrates **Watertight Rooms (Rule A14 — 100% SCMA Loss Isolation)**: realized losses remain 100% inside the executing SCMA with zero bleed to sibling SCMAs, CFCP, or FAEP.
* **Chapter 4** explains the **$25,000 Cash-Register Float Cap & Banking Safety Wall (ADR-011)**.
* **Chapter 5** teaches **Three-Lane Withdrawals (Directive R-15 Three-Tier Distribution Gateway)**: Green Express is autonomous, Yellow Reflection adds AI educational previews, and Red adds a 24-hour scam shield and dual F2-H co-signing—alongside Phase II **Pay-It-Forward & FSAP** stewardship.
* **Chapter 6** covers **One Hat at a Time & Two-Key Governance**, plus the 3-question Stewardship L1 self-check.
* **Deep-Dive Library (Live Today):** Includes dedicated operational walkthroughs for **Using the Dual-Lane AI Tutor Safely** and the **5-Beat Shadow Paper Hunch Studio Walkthrough**.

The University is educational, not an authority surface. Simulator outcomes never mutate a ledger, approve a distribution, or restore risk. Complete its self-check, then follow the authenticated workflows in this manual.

## 11. Three-Stage Governance Lifecycle & Family Charter

Every family member and future steward is encouraged to openly study how PDEUE governance grows over time—even before voting buttons are turned on. Our governance charter is intentionally designed in **three calm, predictable stages** *(Formal Governance Reference: `EXECUTIVE_COMMAND` → `ADVISORY_PETITION_FILTER` → `BICAMERAL_VETO_ACTIVE` & emergency `SHTF` Snap-Back protocol)*:

1. **Stage 1 — Executive Command *(technical state: `EXECUTIVE_COMMAND`, Default Fledgling & Emergency `SHTF` Mode)*:**
   When the platform is young (or whenever an emergency occurs), the Founder / Chief Administrator leads directly so the family can focus on learning, literacy certification, and safe compounding without premature committee friction. In this default stage, House desks display a calm **"Executive Command Mode Active — Voting Dormant"** status badge, voting buttons are hidden, and voting endpoints fail closed (`HTTP 403`).
2. **Stage 2 — Advisory Petition Filter *(technical state: `ADVISORY_PETITION_FILTER`)*:**
   When the Chief Administrator determines the 12 Houses are ready to deliberate, Stage 2 unlocks advisory voting (`AYE` / `NAY`) for authorized `H2` House Leaders and seated delegates. A 75% supermajority (default **9 of 12 Houses**) stages an advisory petition (`RATIFIED_PENDING_SETTLOR`) for Chief Administrator review. Advisory petitions never move capital on their own, and the Chief Administrator retains an **Absolute Founder Veto (`VETOED_BY_FOUNDER`)**.
3. **Stage 3 — Configurable Bicameral Veto *(technical state: `BICAMERAL_VETO_ACTIVE`)*:**
   In long-term maturity, the Chief Administrator can enable binding Bicameral Veto rights for authorized communal bodies—whether the founding **Council of 12 Houses** or future enclave councils created in the registry (such as a **Council of Elders** or **Enclave Stewardship Assembly**) with office seats or named individual seats. On eligible policy and CFCP grant proposals, reaching the council's veto threshold transitions the proposal to `VETOED_BY_BICAMERAL_CHAMBER` and blocks execution.

### What Can Never Be Voted Away (Immutable Core Guardrail)
Even in Stage 2 and Stage 3, **no vote or petition may alter the family's core mathematical and custody protections**. Any proposal targeting the **87/10/3 waterfall**, **High-Water Mark protection (ADR-012)**, **100% SCMA loss isolation (Rule A14)**, **Quarter-Kelly risk bounds**, **3% FAEP endowment**, **banking air-gap (ADR-011)**, or the **Emergency Kill Switch (Directive R-04)** is permanently rejected (`HTTP 403`, `IMMUTABLE_CORE_INVARIANT`).

### Strict Desk Boundaries & Emergency Safety Snap-Back
* **House Isolation:** Each House (`HOUSE-01` through `HOUSE-12`) can inspect only its own branch; cross-house access is blocked server-side (`HTTP 403`).
* **H1 Secretary vs. H2 House Head:** `H1` Secretaries assist with roll call and literacy progress while individual member balances stay masked (`$****.**` under Directive R-12) and circuit breakers/voting remain locked out. `H2` House Heads manage downward-only subordinate circuit breakers (while the Founder's SCMA remains Sovereign Immune) and participate in voting only when Stage 2 or Stage 3 is active. Class T technical operators have zero House governance authority.
* **Emergency Safety Snap-Back *(technical `SHTF` Snap-Back protocol)*:** In an emergency, the Chief Administrator can return governance to Stage 1 (`EXECUTIVE_COMMAND`) in one click, immediately pausing voting while logging a permanent audit record.

## 12. How to Sign In & Stay Safe (No Passwords, Magic Links & Lost Devices)

Signing in to our private Carmichael / McCormick family platform is designed to be calm, effortless, and safe for every generation—from teens to grandparents—with **zero passwords to memorize, write on sticky notes, or accidentally leak**.

### Why There Is No Password (Universal 6-Digit Email Code & Magic Link)
* **Private Family Allowlist Only:** There is no public sign-up page. Only approved family email addresses added by leadership can receive a sign-in code. If a stranger types an unknown email on `/login`, the system shows the exact same calm generic message and sends nothing.
* **Same Device (One-Tap Magic Link):** If you check your email on the same phone, tablet, or computer you are using right now, simply tap the one-time **Magic Link** button in your email to step straight into your family workspace.
* **Two Devices (6-Digit Email Code):** If you open `/login` on a laptop or iPad and read your email on your phone, simply type the **6-digit code** into the code box and click **Verify 6-Digit Code & Sign In**.
* **Built-In Safety Limits:** Every 6-digit code and Magic Link **expires after 10 minutes**, locks out after **5 wrong guesses**, and **burns permanently after one use** so nobody can reuse an old email. Sign-in emails never contain dollar balances, bank details, or SCMA account numbers (`Directive R-12`).

### Returning Visits & Automatic Idle Protection
* **Staying Signed In on Your Personal Device:** Once you sign in as a Class M family member, your private signed session stays active on that device for up to **7 days**, while automatically locking your `/member` wealth vault after **2 hours of inactivity** (`2-hour idle timeout`).
* **Signing Out or Switching Devices:** If you click **Sign Out**—or open the portal on a brand-new phone or computer—simply visit `/login` and request a fresh 6-digit code. Always click **Sign Out** when finishing on a shared family computer.
* **Private Account Protection (Server-Side Tenant Jailing):** Your session is locked strictly to your own personal SCMA account on the server. Even if someone edits the web address (`?scma_id=`), the server blocks cross-member viewing fail-closed (`HTTP 403`).

### Why Apex & Tier-3 Officers Use Passphrase + MFA & One Hat at a Time
* **Stronger Locks for Command Seats (`CHIEF_ADMIN`, `T3` CTO, `F3` CRO):** Platform command seats cannot use passwordless email codes. They require a verified long **Command Passphrase** plus a **6-digit MFA code** (with FIDO2/WebAuthn hardware key support) and stay signed in for at most **8 hours** with a **30-minute idle timeout**.
* **One Active Hat at a Time (`Directive R-06`):** Routine officers (`H1`, `H2`, `HOUSE_GENEALOGIST`, `F1`, `F2-H`, `F2-A`, `T1`, `T2`) also use the 8-hour / 30-minute officer session window. If a relative serves in an officer seat as well as holding a personal account, they switch Active Hats explicitly so personal savings and officer duties never blend.

### What to Do If You Lose Your Phone or Laptop
1. **Stay Calm—Your Funds Are Protected:** PDEUE never stores banking logins or bank routing numbers (`ADR-011`), your `/member` vault auto-locks after 2 hours of inactivity, and no member can unilaterally move pooled capital or bypass withdrawal tiers.
2. **Contact the Chief Administrator Immediately:** Call or message the Chief Administrator (or alert your `F2-H` Head of Household / `H2` House Leader to escalate right away).
3. **Instant 1-Click Session Revocation:** From `/dashboard` Tab 4 (**Active Family Sessions & Lost-Device Revocation**), the Chief Administrator clicks **Revoke Device** on your lost phone or laptop. That device's session cookie is invalidated immediately (forced back to `/login`) and logged permanently in `GovernanceAuditLog`.
4. **Sign Back In Safely on Your New Device:** Once your new phone or computer is ready, visit `/login`, request a fresh 6-digit code to your family email, and continue right where you left off.

