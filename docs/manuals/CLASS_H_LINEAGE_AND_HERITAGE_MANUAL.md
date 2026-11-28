# Class H Lineage Governance and House Genealogist Manual

**College:** School of Sovereign Lineage & Heritage (Class H Officers `H1`–`H2` & `HOUSE_GENEALOGIST`)  
**Audience:** `H1` House Secretary, `H2` House Head, and `HOUSE_GENEALOGIST` (House Historian & Admissions Archivist)  
**Workspaces:** `/lineage/house/{id}?role=H1`, `/lineage/house/{id}?role=H2`, and `/community/heritage` (Hall of Arms & Curation Studio)  
**Mission:** Preserve steady branch-level stewardship across the 12 Family Houses, safeguard subordinate accounts with surgical circuit breakers, uphold three-stage constitutional governance, and curate authentic Carmichael–McCormick lineage history with zero cross-house leakage or financial commingling.

---

## 1. Plain-English Overview: Three Distinct Lineage Offices, One Clear Standard

**In Plain English:** Today PDEUE operates in **Phase I Paper Mode**—a zero-risk proving ground observing live public markets with zero connected bank accounts and zero real family dollars at risk. Real bank custody, `$25,000` venue float sweeps, and our **Pay-it-Forward (`FSAP (Phase II)`)** debt-relief pool begin strictly in **Phase II** inside our physically separate **IFAS (Independent Financial Accounting System)** at `accounting.narratix.io`.

Within each of the 12 Family Houses (`HOUSE-01` through `HOUSE-12`), stewardship is divided cleanly across three distinct offices so administrative roll call, sovereign branch protection, and historical archive curation never blur into a single unchecked role:
- **`H1` (House Secretary):** Keeps the House organized—tracks attendance, onboarding progress, and PDEUE University literacy bars while all personal dollar balances stay hidden behind stars (`$****.**`).
- **`H2` (House Head):** Serves as the sovereign steward of their assigned House—monitors aggregated House capital, applies surgical downward circuit breakers (`Freeze Dial (0%)` and `Cancel Orders`) on subordinate accounts if trouble arises, and casts their House's ballot when constitutional voting stages are opened by the Chief Administrator.
- **`HOUSE_GENEALOGIST`:** Serves as the trusted family historian and lineage verifier for their assigned House inside the zero-financial **Hall of Arms** (`/community/heritage`), curating House chronicles, Scottish bordure-differenced crests, and allied surname biographies, and preparing lineage verification dossiers when Delegated Onboarding is enabled.

> **Critical Boundary — Never Conflate `H2` with `F2-H`:**  
> **`H2` (House Head)** is a **Class H** branch-level lineage leader governing one of the 12 Houses (`/lineage/house/{id}`). **`F2-H` (Head of Household)** is a **Class F** domestic financial guardian inside `/advisor?role=F2-H` who co-signs household `Directive R-15` withdrawals and upward risk-dial restorations. Even if one family leader holds both offices over time, **`Directive R-06` (Active-Hat Context Switching)** enforces that they wear only one role hat at a time.

*(Technical & Governance Spec — `Directive R-06`, `Directive R-12`, `ADR-008`, `ADR-011`, `ADR-012`, `Rule A14`, `Gate G1`):*
- **Active-Hat & Non-Admin Siloing (`Directive R-06`):** `/lineage/house/{id}` strips cross-role navigation bars for non-admin sessions and validates `X-Actor-Role`, `X-House-ID`, and active-hat JWT claims on every request. Attempting to access or mutate a different House ID returns `HTTP 403`.
- **Financial Privacy Masking (`Directive R-12`):** `H1` desks receive server-side redaction (`$****.**`) across both the roster table and Scoped House Custodial Lookup (`#custodial-lookup-bar`). Balances are never leaked to the DOM or client JavaScript for `H1`.
- **Exact-Cent Accounting & High-Water Mark (`ADR-008`, `ADR-012`, `Rule A14`):** All displayed House capital totals (`H2` / `CHIEF_ADMIN`) are formatted at the presentation boundary from 64-bit integer cents. Under `Rule A14`, trading losses remain 100% isolated inside the executing member's SCMA—neither sibling SCMAs, sibling Houses, `CFCP`, nor `FAEP` absorb a member's loss. Under `ADR-012`, the 87% SCMA / 10% CFCP / 3% FAEP waterfall applies strictly to net new realized profit above each SCMA's prior High-Water Mark (`0%` skim during drawdown recovery).
- **Zero Banking Credentials & Air-Gapped Outbox (`ADR-011`):** Neither `/lineage/house/{id}` nor `/community/heritage` ever collects, stores, or transmits bank routing numbers, account numbers, SWIFT codes, or banking API credentials.
- **Zero-Financial Social Firewall (`/community/heritage`):** The Hall of Arms operates on the isolated social plane (`HALL OF ARMS · ZERO FINANCIAL DATA`), importing zero trading engines, zero live balances, and zero execution hooks.

---

## 2. Role & Authority Matrix (`H1` vs. `H2` vs. `HOUSE_GENEALOGIST`)

| Role Token | Everyday Title | Primary Workspace | Scope of Visibility | Mutating / Action Authority | Explicitly Blocked (Fail-Closed `HTTP 403`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`H1`** | **House Secretary** | `/lineage/house/{id}?role=H1` | Assigned House only; member names, SCMA IDs, onboarding status, literacy progress bars; **all balances masked `$****.**`** | Read-only roll call, scoped House lookup (`#custodial-lookup-input`), literacy follow-up reminders | Zero circuit breakers (`Freeze Dial`, `Cancel Orders`), zero governance voting, zero unmasked balances, zero cross-House access, zero heritage DB writes |
| **`H2`** | **House Head** | `/lineage/house/{id}?role=H2` | Assigned House only; Aggregated House Capital, Average Risk Dial, Governance Stage, unmasked subordinate SCMA balances | Surgical `Freeze Dial (0%)` & `Cancel Orders` on non-immune House subordinates; House ballot (`Aye`, `Nay`, Stage 3 `Cast Bicameral Veto`) when unlocked | Cross-House access/mutations, targeting Founder root SCMA (`FOUNDER_APEX_IMMUNITY_VIOLATION`), voting in Stage 1 `EXECUTIVE_COMMAND`, upward risk restoration (`F2-H` / CA only), mutating Immutable Core Invariants |
| **`HOUSE_GENEALOGIST`** | **House Genealogist** | `/community/heritage#genealogist-desk` | Full Hall of Arms gallery (12 Houses + 28+ allied surnames); **zero financial data** | Update assigned House motto & chronicle (`#houseHistoryForm`), add/update allied surname biographies linked to assigned House (`#surnameBioForm`), prepare lineage dossiers under Delegated Onboarding | Editing another House's chronicle or linking surnames to another House (`HTTP 403`), activating funded accounts unilaterally (requires Genealogical Ratification / Chief Admin), viewing SCMA balances or trading controls |

---

## 3. `H1` House Secretary Operations (`/lineage/house/{id}?role=H1`)

**In Plain English:** The `H1` House Secretary is the warm, organized clerk of the House. Your screen shows who belongs to your House, whether each relative is certified through PDEUE University, and where anyone needs encouragement to finish their Stewardship L1 lessons—without ever exposing private dollar amounts.

### 3.1 Desk Controls & Indicators
1. **Header & Active-Hat Pill:** Confirm `CLASS H SOVEREIGN DESK — HOUSE {id}` displays `Active Hat: H1` and the current `MODE: EXECUTIVE_COMMAND` (or active stage) badge.
2. **Fail-Closed Read-Model Banner (`#readModelStatusBanner`):** If the engine is degraded, unseeded, or halted under `Directive R-04`, an explicit banner appears (`QUALIFICATION_PENDING`, `TRADING_HALTED`, or `DEGRADED_RETRYING`). Never improvise numbers when a fail-closed banner is active.
3. **Scoped House Custodial Lookup (`#custodial-lookup-bar`):**
   - Type a member name, member ID, or SCMA prefix into `#custodial-lookup-input` and click **Lookup** (`#custodial-lookup-btn`).
   - Results open in `#custodial-lookup-drawer`, strictly confined to your assigned House with `Directive R-12` masked balances (`$****.**`).
   - Click **Clear** (`#custodial-lookup-clear`) to wipe the drawer client-side and return keyboard focus to the input.
4. **R-12 Masked Roster & Roll Call Table:** Lists every subordinate member in your House with their SCMA identifier, `$****.**` masked balance column, and current membership status (`ACTIVE`, `PENDING_CERTIFICATION`, `PENDING_RATIFICATION`, or `FROZEN`).
5. **PDEUE University Literacy Progress Bars (`<progress>`):** Displays each member's comprehension/certification progress (`85%` for apprentices in progress, `100%` for certified stewards). Use this list to send friendly reminders pointing relatives to `/companion?chapter=6`.

### 3.2 `H1` Hard Guardrails
- `H1` receives zero `Freeze Dial`, `Cancel Orders`, or `Vote` buttons in the rendered DOM.
- Any direct API attempt by `H1` against `POST /api/v1/portal/lineage/house/{id}/circuit-breaker` or `POST /api/v1/portal/lineage/house/{id}/vote` fails closed with `HTTP 403` and writes an audit record.
- Never ask a member or `H2` to screenshot unmasked dollar balances into general chat—respect `Directive R-12` privacy boundaries.

---

## 4. `H2` House Head Operations (`/lineage/house/{id}?role=H2`)

**In Plain English:** As `H2` House Head, you are the watchful steward of your branch. You can inspect your House's aggregate capital and average risk dial at a glance, pull a surgical emergency brake on an individual subordinate account inside your House if needed, and represent your House when the Chief Administrator opens formal governance deliberations.

### 4.1 Metrics & Subordinate Circuit Breakers
1. **Top Summary Strip (`.metrics`):**
   - **Aggregated House Capital:** Exact-cent sum of subordinate SCMA cash balances inside your House (`ADR-008`).
   - **Average Risk Dial:** Mean active risk watermark across your House's accounts.
   - **Governance Stage (`#desk-governance-mode`):** Live constitutional posture (`EXECUTIVE_COMMAND`, `ADVISORY_PETITION_FILTER`, or `BICAMERAL_VETO_ACTIVE`).
2. **Subordinate SCMA Accounts & Lineal Circuit Breakers Table:**
   - Each subordinate row displays Member Name, SCMA ID, exact-cent Balance, Status, and Lineal Controls.
   - **Freeze Dial (0%) (`button.freeze` -> `openFreezeModal(scma)`):** Calls `POST /api/v1/portal/lineage/house/{id}/circuit-breaker` with `action: "FREEZE_DIAL"`. Clamps that specific SCMA's risk dial immediately to `0.00%`, displays confirmation in `#freeze-modal` and `#breaker-feedback`, and leaves every other account and all 11 sibling Houses completely untouched.
   - **Cancel Orders (`button.cancel` -> `openCancelModal(scma)`):** Calls `POST /api/v1/portal/lineage/house/{id}/circuit-breaker` with `action: "CANCEL_ORDERS"`. Purges resting orders for that specific SCMA, displays confirmation in `#cancel-modal` and `#breaker-feedback`, and records an immutable lineage audit entry.
   - **Sovereign Immunity on Founder Root (`🛡️ Sovereign Immune`):** On `HOUSE-01` (or wherever the Founder / Chief Administrator root SCMA resides), the circuit-breaker buttons are replaced with the `🛡️ Sovereign Immune` badge. Any scripted API attempt to freeze or cancel orders on the Founder root SCMA is rejected server-side with `HTTP 403 (FOUNDER_APEX_IMMUNITY_VIOLATION)` and logged to the Governance Audit Ledger.
   - **Downward-Only Asymmetry:** `H2` can clamp risk **down** to `0.00%` or purge orders immediately, but `H2` can **never** unilaterally raise a member's risk dial back upward or lift a platform-wide `Directive R-04` halt. Upward restoration requires `F2-H` / Chief Administrator review after the underlying issue is verified resolved.

### 4.2 Bicameral CFCP Ratification Chamber (`#bicameral`) — All Three Governance Stages
Your House desk adapts dynamically to the platform's live constitutional stage set by the Chief Administrator on `/dashboard` Tab 4:

1. **Stage 1 — `EXECUTIVE_COMMAND` (Default Fledgling & SHTF Safety Mode):**
   - Displays `#governance-dormant-badge` (**"Executive Command Mode Active — Voting Dormant"**).
   - All `#vote-aye`, `#vote-nay`, and `#vote-veto` buttons are stripped from the DOM.
   - Direct POST requests to `/api/v1/portal/lineage/house/{id}/vote` fail closed with `HTTP 403`.
2. **Stage 2 — `ADVISORY_PETITION_FILTER` (Advisory Senate Petitions + Absolute Founder Veto):**
   - Displays `#governance-active-badge` (**"Stage 2: Advisory Petition Filter Active (Founder Veto Preserved)"**).
   - Unlocks `#vote-aye` (**Aye**) and `#vote-nay` (**Nay**) on active eligible proposals (for example, `CFCP-2026-02` Apprentice Literacy Grant Petition).
   - Reaching the 75% supermajority (`9 / 12` Houses voting Aye) updates `#consensus-tally` and transitions the proposal strictly to **`RATIFIED_PENDING_SETTLOR`**—an advisory petition awaiting Chief Administrator review. **Zero capital moves unilaterally.**
   - The Founder / Chief Administrator retains an **Absolute Founder Veto (`VETOED_BY_FOUNDER`)** at any point in Stage 2.
3. **Stage 3 — `BICAMERAL_VETO_ACTIVE` (Configurable Binding Bicameral Veto):**
   - Displays `#governance-active-badge` (**"Stage 3: Bicameral Veto Active (Binding Chamber Veto Enabled)"**).
   - Unlocks `#vote-aye`, `#vote-nay`, and `#vote-veto` (**Cast Bicameral Veto**), along with live `#veto-tally` tracking.
   - Reaching the configured veto threshold (default `9 / 12` authorized chamber votes) transitions an eligible policy or CFCP grant proposal to **`VETOED_BY_BICAMERAL_CHAMBER`**.
   - **Immutable Core Invariant Protection (ALL Stages):** No chamber vote in any stage may amend or weaken the 87/10/3 waterfall, `ADR-012` High-Water Mark, `Rule A14` 100% SCMA loss isolation, Quarter-Kelly bounds, 3% `FAEP`, `ADR-011` banking air-gap, or `Directive R-04` kill switch (`HTTP 403 IMMUTABLE_CORE_INVARIANT`).

---

## 5. `HOUSE_GENEALOGIST` & Hall of Arms Curation Studio (`/community/heritage`)

**In Plain English:** The Hall of Arms is our family's living museum—completely walled off from financial accounts and trading engines. It showcases the full heraldic achievements of the founding **Carmichael** (`IEHOVA SEMPER VIGILANS`, House 01 descending from the eldest McCormick daughter) and **Foundational McCormick** (`Sine Timore`, root stock of Houses 02–12) lines, all 12 Family Houses with Scottish **Bordure Differencing**, and 28+ allied and married-in surnames.

### 5.1 Browsing & Filtering the Hall of Arms
- **Search Input (`#heritageSearchInput`):** Filter Houses, mottos, bordure styles (engrailed, indented, wavy, invected, embattled, compony), or allied surnames in real time.
- **House Dropdown (`#heritageHouseFilter`):** Narrow the gallery to a single House (`House 01` through `House 12`).
- **Reset Filter (`#heritageResetBtn`):** Restores the full 12-House + allied-surname gallery.
- **Individual Chronicle Pages:** Click any House card (`/community/heritage/house/{id}`) or allied surname card (`/community/heritage/surname/{slug}`) to inspect the full chronicle and heraldic description.

### 5.2 Scottish Bordure Differencing & Two-Scale Heraldry Standards
- **Two-Scale Display:** Compact `40×46` shield emblems appear in every portal header; full heraldic achievements (`carmichael_achievement` and `mccormick_achievement`) appear in `#foundingAchievementsShowcase` and `/home`.
- **House 01 (Carmichael Prime):** Honors the eldest McCormick daughter's Carmichael lineage with official motto *IEHOVA SEMPER VIGILANS*, Strategic Air Command armored gauntlet holding lightning bolts and olive branch, displayed-eagle shield with silver Carmichael inescutcheon, visor-up African American knight, and crowned dark-maned Barbary lion supporters.
- **Houses 02–12 (Bordure-Differenced McCormick Branches):** Preserve the foundational three royal-blue eagles and crimson zigzag *fess dancetté* core while distinguishing each branch with its own Scottish heraldic bordure tincture and edge pattern.

### 5.3 Scoped Curatorial Desk (`#genealogist-desk` / `#genealogistDeskDrawer`)
1. Open the collapsible drawer **Curate House History & Allied Surname Biographies** (`#genealogistDeskDrawer`, also directly reachable via `/community/heritage#genealogist-desk`).
2. **Update Assigned House Chronicle (`#houseHistoryForm`):**
   - Select your assigned House in `#editHouseId` (`1–12`).
   - Enter or refine the House motto (`#editHouseMotto`, max 180 chars) and chronicle text (`#editHouseHistory`, max 4,000 chars).
   - Click **Save House History** (`#saveHouseHistoryBtn`), which calls `POST /api/v1/portal/community/heritage/house/{id}` and reports confirmation or rejection in `#houseEditStatus`.
3. **Add or Update Allied Surname (`#surnameBioForm`):**
   - Enter the surname (`#editSurnameName`), link it to your assigned House (`#editSurnameHouseId`), add a concise origin summary (`#editSurnameOrigin`), and write the family biography (`#editSurnameHistory`).
   - Click **Save Surname Biography** (`#saveSurnameBioBtn`), which calls `POST /api/v1/portal/community/heritage/surname` and updates `#surnameEditStatus`.
4. **Server-Enforced Scope & Audit:** Only an active `HOUSE_GENEALOGIST` assigned to that exact House ID in `user_role_assignments` (or `CHIEF_ADMIN`) may persist changes. Cross-House or unauthenticated edits are rejected server-side with `HTTP 403` and recorded in the Governance Audit Ledger.

### 5.4 Delegated Onboarding, Genealogical Ratification & Anti-Tribalism Custody
- **Delegated Onboarding (`PENDING_RATIFICATION`):** When the Chief Administrator enables Delegated Onboarding for a House on `/dashboard` Tab 4, the assigned `HOUSE_GENEALOGIST` (or House leadership) may verify how a prospective family member connects to the lineage tree and submit a welcome onboarding dossier in `PENDING_RATIFICATION` status.
- **Genealogical Admissions Board & Final Ratification:** A `HOUSE_GENEALOGIST` never activates a trading account or moves funds unilaterally. Final admission requires Genealogical Ratification / Chief Administrator sign-off, which emits a signed HMAC-SHA256 `MEMBER_ADMISSION_RATIFIED` `ADR-011` outbox event to IFAS containing zero bank credentials.
- **Anti-Tribalism Custody (`INTRA_HOUSE` vs. `CROSS_HOUSE_ANTI_TRIBAL`):** To strengthen unity across all 12 Houses and prevent cliques, the Chief Administrator can toggle custody mode to `CROSS_HOUSE_ANTI_TRIBAL`, pairing mentors and stewards across different Houses while preserving strict server-side House data boundaries.

---

## 6. Routine Operational Workflows (Weekly & Daily Cadence)

### 6.1 `H1` House Secretary Weekly Roll Call & Literacy Check
1. Open `/lineage/house/{id}?role=H1` and verify your Active-Hat pill (`Active Hat: H1`) and clean `#readModelStatusBanner`.
2. Scan the R-12 Masked Roster (`$****.**`) for any member still in `PENDING_CERTIFICATION` or `PENDING_RATIFICATION`.
3. Review the `<progress>` literacy bars; note any apprentice below `100%`.
4. Use `#custodial-lookup-input` to confirm exact SCMA status for any relative who asked for onboarding help, then click `#custodial-lookup-clear` when finished.
5. Share a welcoming, non-financial reminder in `/community` (Family Hearth) inviting apprentices to complete PDEUE University (`/companion`)—never posting personal SCMA IDs or private disputes in public threads.

### 6.2 `H2` House Head Daily Watch & Stage 2/3 Petition Review
1. Open `/lineage/house/{id}?role=H2` and verify `Active Hat: H2`, Aggregated House Capital, Average Risk Dial, and `#desk-governance-mode`.
2. Inspect every subordinate row in the Subordinate SCMA table for unexpected status changes (`FROZEN`, halted, or anomalous risk posture).
3. Verify `#readModelStatusBanner` shows no active `TRADING_HALTED` or `DEGRADED_RETRYING` alert.
4. If `#desk-governance-mode` is `ADVISORY_PETITION_FILTER` or `BICAMERAL_VETO_ACTIVE`, review the active proposal ID and title inside `#bicameral`, consult your House members thoughtfully, and cast a deliberate ballot (`#vote-aye`, `#vote-nay`, or Stage 3 `#vote-veto`), verifying `#consensus-tally` and `#vote-feedback` confirm recording.

### 6.3 `HOUSE_GENEALOGIST` Monthly Archive Curation
1. Open `/community/heritage` and review your assigned House card and linked allied surnames via `#heritageHouseFilter`.
2. Confirm every allied surname story is accurate, respectful, and completely free of financial balances, bank details, or private PII (such as Social Security numbers or street addresses).
3. Open `#genealogistDeskDrawer`, update `#houseHistoryForm` or `#surnameBioForm` with verified family chronicles, click Save, and confirm the live card refreshes cleanly in `#housesGalleryGrid` or `#alliedSurnamesGrid`.

---

## 7. Outlier & Emergency Playbooks (High-Stress Scenarios)

### Playbook H-E1: Errant Subordinate Containment (Surgical Freeze & Order Purge)
- **Trigger:** A subordinate member in your House reports suspicious account activity, accidental high-velocity practice orders, or domestic distress requiring an immediate trading stop.
- **Steps (`H2` only):**
  1. Open `/lineage/house/{id}?role=H2` and locate the affected relative in the Subordinate SCMA table (verify it is **not** the Founder root account).
  2. Click **Freeze Dial (0%)** (`button.freeze`) on that member's row -> confirms `Governor Clamp (0.0%)` in `#freeze-modal` and `#breaker-feedback`, immediately clamping risk to `0.00%`.
  3. Click **Cancel Orders** (`button.cancel`) on the same row -> confirms `Resting Purge` in `#cancel-modal` and `#breaker-feedback`, canceling any open orders.
  4. Notify the member's `F2-H` Head of Household and Chief Administrator so they can coordinate a disciplined review. Do **not** escalate to a global `Directive R-04` halt for a single-member incident; surgical containment keeps the other 11 Houses undisturbed.
- **Recovery:** Upward risk restoration is intentionally locked downward-only; only `F2-H` (within certified bounds) or Chief Administrator may restore normal parameters once cleared.

### Playbook H-E2: Cross-House `HTTP 403` Boundary Encounter
- **Trigger:** An `H1`, `H2`, or `HOUSE_GENEALOGIST` officer accidentally navigates to a different House URL (e.g., House 02 officer opening `/lineage/house/1` or attempting a lookup/edit on House 01) and receives `HTTP 403 Forbidden`.
- **Steps:**
  1. Treat the `HTTP 403` as healthy fail-closed security—not a software bug. Do **not** retry repeatedly or share credentials with another House officer.
  2. Verify your assigned House number in your Active-Hat profile and navigate back to your own `/lineage/house/{your_house_id}` URL or select your own House in `#editHouseId`.
  3. If a legitimate cross-House operational handoff is required (e.g., an `H2` officer is temporarily unavailable), escalate to the Chief Administrator on `/dashboard` Tab 4—never attempt to bypass `X-House-ID` scoping.

### Playbook H-E3: Governance Snap-Back Mid-Deliberation (`SHTF` Protocol)
- **Trigger:** While Houses are actively voting in Stage 2 (`ADVISORY_PETITION_FILTER`) or Stage 3 (`BICAMERAL_VETO_ACTIVE`), a systemic market, venue, or security emergency causes the Chief Administrator to trigger the **1-Click SHTF Snap-Back** to `EXECUTIVE_COMMAND`.
- **Expected System Behavior:**
  1. `#desk-governance-mode` switches immediately to `EXECUTIVE_COMMAND`.
  2. Upon refresh (or immediately on any pending ballot POST), voting buttons disappear and `#governance-dormant-badge` displays **"Executive Command Mode Active — Voting Dormant"**.
  3. Any in-flight vote POST returns `HTTP 403` cleanly without corrupting prior tallies.
- **Steps (`H1`/`H2`):** Halt branch voting deliberations immediately, verify `#readModelStatusBanner` for any simultaneous `Directive R-04` trading halt, reassure House members that all funds and existing records remain safely preserved, and await official Chief Administrator stand-down notice before resuming petitions.

### Playbook H-E4: Immutable Core Invariant Proposal Attempt
- **Trigger:** A House member or drafting committee proposes a vote to alter the 87/10/3 profit waterfall, disable `ADR-012` High-Water Mark recovery protection, share losses across accounts (violating `Rule A14`), loosen Quarter-Kelly limits, connect raw bank credentials (violating `ADR-011`), or disable `Directive R-04`.
- **Expected System Behavior:** The governance engine permanently blocks the proposal in **all three stages** (`HTTP 403`, error code `IMMUTABLE_CORE_INVARIANT`) and logs the rejection.
- **Steps (`H2`):** Explain plainly to the House that these foundational mathematical safeguards are constitutional invariants protecting every generation equally—no vote can dilute them. Direct members to `/companion` Chapter 6 (`#enclaveGovernanceCharter`) to review the Open-Study Charter.

### Playbook H-E5: Disputed Genealogical Edits & Unauthorized Curation Attempts
- **Trigger:** Two family branches disagree on a House chronicle, an allied surname's linked House, or an unauthorized user attempts to overwrite history in `/community/heritage#genealogist-desk`.
- **Steps (`HOUSE_GENEALOGIST` & `H2`):**
  1. Confirm server-side containment: unauthorized users or cross-House genealogists are blocked automatically (`HTTP 403`) with zero database mutation.
  2. Never engage in rapid edit-wars inside `#houseHistoryForm` or `#surnameBioForm`. Pause edits and gather primary family documentation (lineage records, elder attestations).
  3. Escalate cross-House surname link changes or disputed founding-House (`HOUSE-01`) revisions to the Chief Administrator, who holds audited cross-House curatorial oversight and can verify Governance Audit Ledger timestamps before ratifying the canonical text.

---

## 8. Quick Reference: Constitutional Guardrails for Class H & Genealogists

- **One Hat at a Time (`Directive R-06`):** Confirm your Active-Hat pill before every action; never confuse `H2` (House Head) with `F2-H` (Head of Household).
- **Masked Means Masked (`Directive R-12`):** `H1` desks never display raw dollar balances; `HOUSE_GENEALOGIST` operates on a zero-financial social plane.
- **Surgical First, Never Global:** `H2` freezes or cancels orders on one specific subordinate SCMA—never disrupting healthy siblings or the other 11 Houses.
- **Founder Root Immunity:** Subordinate circuit breakers can never target the Founder / Chief Administrator root SCMA (`FOUNDER_APEX_IMMUNITY_VIOLATION`).
- **No Unilateral Capital Movement:** Even a `9 / 12` ratified petition in Stage 2 or a `HOUSE_GENEALOGIST` onboarding dossier never moves a dollar or activates bank custody without explicit human ratification and `ADR-011` air-gapped handoff to IFAS.

---

## 9. House Delegated Onboarding Intake, Admissions Board & Two-Party Co-Sign

Authorized **`H2` House Leaders** and **`HOUSE_GENEALOGIST`** historians have access to a collapsible **House Delegated Onboarding Intake & Admissions Board** panel directly on `/lineage/house/{id}` (strictly stripped from `H1` House Secretary desks and non-house roles):

1. **Respecting Chief Admin Delegation Scope (`ADMIN_ONLY` / `PER_HOUSE` / `ENCLAVE_WIDE`):** When the enclave is in its fail-closed `ADMIN_ONLY` default, the panel displays a clear notice explaining that delegated intake is paused. Once the Chief Administrator enables `PER_HOUSE` (for your House) or `ENCLAVE_WIDE` on `/dashboard` Tab 4, `H2` and `HOUSE_GENEALOGIST` can submit kinship-verified dossiers (`POST /api/v1/onboarding/delegated-submit`) strictly for their own assigned `X-House-ID` (cross-house attempts fail closed `HTTP 403`).
2. **Staged Safely in `PENDING_RATIFICATION`:** Submitting a House dossier or casting a Genealogical Admissions Board ballot (`APPROVE`, `REQUEST_PROOF`, or `REJECT` via `/board-vote`) never creates an SCMA or moves capital unilaterally. Zero banking credentials or SSNs may ever be entered (`ADR-011`—opaque `EXT-REF-...` tokens only).
3. **Chief Admin Solo Default vs. Toggleable Two-Party Co-Sign (`TWO_PARTY_COSIGN`):** By default in Ring 1 Alpha (`CHIEF_ADMIN_SOLO`), the Chief Administrator ratifies dossiers directly. When the Chief Administrator toggles `TWO_PARTY_COSIGN` on `/dashboard` Tab 4, solo ratification fails closed (`HTTP 409`, `TWO_PARTY_COSIGN_REQUIRED`) until an authorized **`F2-H` Head of Household** for that exact House records their co-sign attestation from `/advisor` (**Pending Member Admission Co-Signs**). Once ratified, the new relative's SCMA and `CLASS_M` private allowlist login are provisioned automatically, a 48-hour invite link is issued for `/activate`, and a signed HMAC-SHA256 `MEMBER_ADMISSION_RATIFIED` event crosses to IFAS.

