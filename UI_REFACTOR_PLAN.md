# PDEUE Autonomous UI/UX Decluttering & Companion Playback Refactor Plan (`UI_REFACTOR_PLAN.md`)

**Branch:** `ring1-alpha`  
**Audit Viewport:** `1440×900` Desktop (plus `390×844` Mobile zero-overflow check)  
**Baseline Telemetry Source:** `ui_audit_output/baseline/SUMMARY.md` & `ui_audit_output/baseline/telemetry.json`

---

## Baseline Telemetry Summary (`1440×900`)

| Priority | Page | File | Baseline Height Ratio | Scroll Height | Visible / Total Sections | Visible / Total Controls | Above-Fold Controls | Primary Clutter Issue |
| :---: | :--- | :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| **P1** | `/companion` | `companion.html` | `2.23x` | `2008px` | `6 / 44` | `34 / 85` | `30` | **Critical:** Expanded Orientation (`top: 315–624px`) + 5-row toolbar push Chapter 1 & `.waterfall` illustration (`top: 1419–1604px`) **519px below the fold**; `chapterIds` undefined bug breaks continuous chapter-to-chapter playback. |
| **P2** | `/member` | `member.html` | `4.63x` | `4167px` | `14 / 103` | `13 / 53` | `9` | **Severe scroll wall:** Both full 12-row seed projection tables + 4 long prose cards + Funding Instructions stack open simultaneously. |
| **P3** | `/dashboard` | `dashboard.html` | `1.50x` | `1354px` (Tab 1; much taller on Tabs 2–4) | `11 / 112` | `17 / 169` | `16` | **Above-fold crowding & Tab 3/4 overload:** Header Row 2 wraps onto 2 lines; 4 stacked banners push charts down; Tab 3 & Tab 4 stack dense forms/tables without progressive disclosure. |
| **P4** | `/community/heritage` | `heritage.html` | `5.35x` | `4815px` | `5 / 5` | `15 / 15` | `3` | **Tallest vertical stack:** Founding achievements, 12 House cards, 28 allied surnames, and Genealogist Desk stack vertically with excessive card height. |
| **P5** | `/advisor` | `advisor.html` | `2.24x` | `2018px` | `15 / 21` | `12 / 31` | `6` | Stacked alert + role banner + lookup bar push KPIs and tables down; secondary tables & shadow clearance can use progressive disclosure. |
| **P6** | `/community` | `community.html` | `1.91x` | `1719px` | `5 / 20` | `16 / 24` | `8` | 4 tab buttons wrap awkwardly (`3 + 1` orphan button on row 2); Benefactor banner + header eat above-the-fold space. |
| **P7** | `/admin/tech` | `tech.html` | `1.82x` | `1634px` | `11 / 12` | `12 / 17` | `9` | Stacked banners above KPIs; unspaced card titles (`AUTONOMOUSSCANWORKER`, `SETTLEMENTRECONCILER`); eviction log can be collapsible. |
| **P8** | `/lineage/house/1` | `lineage_house.html` | `1.56x` | `1401px` | `9 / 9` | `8 / 8` | `6` | H1 wraps awkwardly onto 2 lines; `Governance Stage (Executive Command Mode ⓘ)` breaks mid-parenthesis; lookup + status banners consume ~450px. |
| **P9** | `/home` | `home.html` | `1.82x` | `1640px` | `3 / 7` | `4 / 5` | `4` | Already calm; refine vertical rhythm, card hover hierarchy, and compact crest showcase spacing so doorway grid breathes cleanly. |

---

## Strict Invariants & Guardrails Preserved Across All Phases
1. **Zero Feature Loss:** 100% of existing DOM IDs, forms, buttons, JS handlers, `data-plane-doorway` tags, `<abbr class="pdeue-term">` glossary tooltips, and API endpoints remain intact.
2. **Byte-for-Byte Template Sync:** Every edited file in `backend/app/static/<name>.html` is mirrored byte-for-byte to `backend/app/api/v1/<name>.html`.
3. **WP4 Inline Lock:** `advisor.html` and `tech.html` retain zero `<script src=` tags.
4. **Zero-CDN & Offline First:** Zero external stylesheets/scripts; Batch 4 Studio Audio (`/api/v1/portal/companion/state` -> `studio_audio_ready: true` + local `.mp3`/`.vtt`) preserved verbatim.
5. **Design Tokens (`DESIGN_TOKENS.md`):** Locked `#0B132B` / `#1C2541` / `#1E293B` / `#334155` / `#38BDF8` institutional palette, `tabular-nums`, and 3-row institutional header alignment.
6. **Inventory & Lexicon Parity:** Re-sync `docs/PORTAL_COMPONENT_INVENTORY.md` via `portal_discovery.generate_inventory()` so parity tests stay 100% green.

---

## Page-by-Page Refactor Specification

### 1. `companion.html` (P1 — Orientation/Illustration Split + Continuous Guided Playback + Toolbar Declutter)
- **Compact Institutional Header:** Keep exact 3-row `.portal-header-shell.portal-header-compact` structure and twin `40×46` crests; tighten H1 to single-line at `1440px` and compact row padding (~150px total height vs 245px).
- **Side-by-Side Orientation + Active Chapter Stage (`#simulator-layout`):**
  - On desktop (`>= 1024px`), render `#chapter-orientation` as a sleek left collapsible side drawer (`330px` wide) beside the right-hand Learning Stage (`1fr`: compact `.toolbar` + `.chapters`).
  - Inside `#chapter-orientation`, tighten typography, stack the 3 orientation pillars cleanly as compact rows, and keep `#playOrientationBtn`, `#toggleOrientationBtn`, and `#orientationStatus` immediately visible.
  - When collapsed (`Hide Orientation Card` -> `Show Orientation Card`), `#chapter-orientation` collapses to a slim 1-line top strip (`Show Orientation Card` + `▶ Listen to 30-Second Welcome`), expanding the Chapter stage to full width.
  - Inside `#chapter-waterfall`, arrange the Plain-English summary compactly above a 2-column split placing the `.waterfall` SVG illustration alongside the integer-cent inputs & live output cards so **both Orientation AND `.waterfall` Illustration remain 100% visible above the fold at `1440×900`** (`bottom <= 900`).
- **Streamlined 2-Row Playback Toolbar:** Consolidate the 5 sprawling stacked toolbar rows into 2 tight horizontal rows (Row 1: Mode + Chapter pills + Badge; Row 2: Play/Pause, Beat/Skip, **Auto-Advance toggle**, Speed, Voice, Mute, Audio Badge + slim timeline scrubber + compact caption bar).
- **Continuous Guided Tour Playback (Functional Fix #2):**
  - Fix undefined `chapterIds` reference that previously threw when auto-scrolling across chapter transitions.
  - Add `<button id="autoAdvanceToggle" type="button" class="active" aria-pressed="true">Auto-Advance: On</button>` in `.transport`.
  - Wire `audio.onended`, `SpeechSynthesisUtterance.onend`, and `requestAnimationFrame` visual timer fallback cleanly:
    - When **Auto-Advance: On**, playback progresses continuously beat-to-beat (`Beat 1 -> 18`) and chapter-to-chapter (`Ch 1 -> Ch 6`) without cutting off Studio Audio `.mp3` tracks early and without requiring manual clicks on chapter transitions.
    - When **Auto-Advance: Off**, playback pauses cleanly at the end of the active beat while preserving manual jump (`Prev/Next Beat`, `Prev/Next Ch`, chapter pills, timeline scrub) and Play/Pause controls.

### 2. `member.html` (P2 — Collapse 4.63x Scroll Wall to Clean Progressive-Disclosure Workspace)
- **Compact ReadModel Status Strip:** Slimmer single-row horizontal status banner so Workspace Switcher + Hero appear cleanly above the fold.
- **`viewOrientation` Declutter:**
  - Keep `#welcomeCard` (tightened typography), 87/10/3 `.pillar-grid`, and `#unifiedProjectionChart` (`#projectionCompareSvg` + seed filter buttons) immediately visible.
  - Wrap `#projectionTables` (the two 12-row exact-cent schedules, ~1,400px tall) in a sleek collapsible `<details id="projectionTablesDrawer" class="disclosure-drawer">` ("📊 View Full 12-Month Exact-Cent Schedule Tables ($100 & $1,000 Seeds)").
  - Organize `Steady-State Cash-Flow Engine`, `Multi-Market Diversification Blueprint`, and `Lineage Governance & Family Covenant` into clean collapsible `<details>` panels inside a 2-column institutional layout so `viewOrientation` drops from `4.63x` (~4,167px) down to **~1.9x–2.3x** while keeping 100% of prose & schedules 1 click away!
  - Make `#fundingInstructionsCard` sleeker and tighter below (preserving `#fundingBankRefToken`, `#ifasHandoffBtn`, `#ifasAirGapNotice` visible for C1/PR82 E2E tests).
- **`viewEngine` Declutter:**
  - Compact 4-card KPI row + 3-column SVG visualizations (`Asset Engine Rings`, `My Trajectory`, `High-Yield Radar`).
  - Wrap the 12-Slot Concurrency Rack in a crisp `<details id="glassEngineRackDrawer" class="card" open>` (or compact 6-column grid at 1440px so 12 slots take 2 neat rows instead of 3 tall rows).
  - Keep Risk Governor, Distribution Drawer, and AI Literacy Tutor cleanly arranged in a tight visual hierarchy above the existing collapsible `<details id="shadowHunchStudioDetails">`.

### 3. `dashboard.html` (P3 — Header Row 2 Single-Line Fix, Side-by-Side Utility Strip, Tab 3 & Tab 4 Progressive Disclosure)
- **Header Row 2 Single-Line Alignment:** Tighten `.hub-btn` / `.curr-btn` pill padding so all 5 Portal Hub pills + Glossary/Currency controls sit on **1 single line** at `1440px`.
- **Compact Top Utility Strip:** Place `.qualification-drawer` and `#custodial-lookup-bar` side-by-side on desktop (`>= 1024px`) and slim `#readModelStatusBanner`, freeing ~110px above the tabs so ALL 4 KPI cards AND both Concentric Asset Rings & Equity Curve sit cleanly above the fold!
- **Tab 3 (`#tab-panel-3`) Progressive Disclosure:** Wrap `#adminShadowHunchCard` inside a sleek collapsible `<details id="adminShadowHunchDrawer" class="card">` preserving all inner IDs (`#adminShadowHunchCard`, `#adminEvalHunchBtn`, etc.).
- **Tab 4 (`#tab-panel-4`) Progressive Disclosure:** Group static `Immutable Architectural Invariants` into a compact collapsible `<details>` drawer, tighten form spacing across Enclave Registry, Role Provisioning, and Delegated Onboarding, and ensure zero horizontal overflow.

### 4. Remaining 6 Portals (P4–P9 — Consistent Card Hierarchy, Spacing & Typography Polish)
- **`heritage.html` (P4):** Compact crest achievement frames (`max-height: 280px` instead of giant vertical boxes), upgrade Houses Gallery & Allied Surnames to responsive 4-column desktop grids (cutting height ratio drastically from `5.35x` to `~2.6x`), and wrap `#genealogist-desk` form controls cleanly in a collapsible `<details>` that auto-opens when `#genealogist-desk` hash is targeted.
- **`advisor.html` (P5):** Slim status + role banners into a single compact alert stack, tighten lookup bar padding, organize lower operational cards (`#operations`, `#shadowHunchClearanceSection`) with clean 2-column spacing and collapsible `<details>` wrappers where safe (keeping all E2E-tested locators visible!).
- **`community.html` (P6):** Make `.tabs` sit cleanly on **1 single horizontal row** at `1440px` (no orphan 4th tab wrapping!), tighten Benefactor banner padding, and refine announcement/message card hierarchy.
- **`tech.html` (P7):** Fix unspaced KPI titles (`Autonomous Scan Worker`, `Settlement Reconciler`), slim stacked banners, and wrap secondary eviction history log in a collapsible `<details>` while keeping `#techCopilotCard`, `#trigger-daemon`, `#trigger-settlement`, and `#custodial-lookup-bar` immediately accessible.
- **`lineage_house.html` (P8):** Prevent awkward H1 and KPI label line-breaks (`Governance Stage`), tighten lookup bar and status banner padding, and polish table hierarchy.
- **`home.html` (P9):** Tighten hero & doorway card spacing and refine card elevation/hover states so all 4 doorways and the heraldic showcase look crisp and cohesive.

---

## Verification Plan (Phase 3)
1. Sync all 9 modified templates byte-for-byte between `backend/app/static/` and `backend/app/api/v1/`.
2. Re-generate `docs/PORTAL_COMPONENT_INVENTORY.md` so UI-to-Lexicon-to-Curriculum parity passes 100%.
3. Run:
   - `cd backend && python3 -m pytest tests/test_batch4_cross_domain_nav_and_studio_audio.py tests/test_play16_security_hygiene.py -q`
   - Full backend unit/integration suite (`cd backend && python3 -m pytest --ignore=tests/e2e -q`)
   - Playwright E2E suites (`test_batch4_cross_domain_and_audio_e2e.py`, `test_pr83_university_header_e2e.py`, `test_e3_e5_ux_e2e.py`, `test_c1_onboarding_e2e.py`, `test_pr82_home_hub_heritage_e2e.py`, etc.)
4. Re-run `python3 backend/scripts/audit_ui_screenshots.py` into `ui_audit_output/` and visually compare all before/after screenshots to confirm:
   - Zero horizontal overflow (`<= 2px`) across all 9 portals
   - Companion Orientation + Illustration BOTH visible above the fold at `1440×900` when expanded
   - Continuous guided tour playback verified in Playwright across beats & chapters with Auto-Advance On/Off toggle
   - Cleaner visual hierarchy and significantly lower vertical scroll depth across all portals.

---

## Verified Phase 3 Results (`1440×900` Before vs. After)

| Page | File | Before Height | After Height | Height Delta | Overflow | Errors / CDN | Key Layout Improvement |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| `/companion` | `companion.html` | `2.23x` (`2008px`) | **`1.44x` (`1296px`)** | **-35.5%** | `0px` | `0` | Side-by-side Orientation (`245..879px`) + unclipped Waterfall SVG (`742..884px`) both 100% above fold; single-row transport + continuous Auto-Advance On/Off playback (`chapterIds` + `step="0.1"` quantization bugs fixed). |
| `/member` | `member.html` | `4.63x` (`4167px`) | **`2.54x` (`2285px`)** | **-45.2%** | `0px` | `0` | Collapsible exact-cent schedule tables (`#projectionTablesDrawer`), collapsible secondary orientation deep dives, and 6-column `#glassEngineRackDrawer` with 100% of 53 controls preserved. |
| `/dashboard` | `dashboard.html` | `1.50x` (`1354px`) | **`1.22x` (`1101px`)** | **-18.7%** | `0px` | `0` | Single-line Header Row 2 pills, side-by-side Qualification + Lookup utility strip, Concentric Rings & Equity Curve both above fold, collapsible drawers on Tabs 3 & 4. |
| `/community/heritage` | `heritage.html` | `5.35x` (`4815px`) | **`3.73x` (`3359px`)** | **-30.2%** | `0px` | `0` | Compacted Founding Achievements (both fully above fold), 4-column desktop Houses & Allied Surnames grids, collapsible `#genealogistDeskDrawer` with `#genealogist-desk` hash auto-open. |
| `/admin/tech` | `tech.html` | `1.82x` (`1634px`) | **`1.45x` (`1305px`)** | **-20.1%** | `0px` | `0` | Balanced 5-column KPI row, tightened alert/lookup stack, preserved WP4 zero-`<script src=>` lock and canonical worker labels. |
| `/lineage/house/1` | `lineage_house.html` | `1.56x` (`1401px`) | **`1.33x` (`1197px`)** | **-14.6%** | `0px` | `0` | Refined H1 scale, balanced 3-KPI strip, Subordinate SCMA & circuit breakers visible above fold. |
| `/community` | `community.html` | `1.91x` (`1719px`) | **`1.75x` (`1576px`)** | **-8.3%** | `0px` | `0` | All 4 tabs aligned cleanly on 1 horizontal row (eliminated 3+1 orphan wrap), compact Benefactor banner. |
| `/advisor` | `advisor.html` | `2.24x` (`2018px`) | **`2.05x` (`1845px`)** | **-8.6%** | `0px` | `0` | Compacted alert/lookup stack so all 4 KPIs + Subordinate SCMA table appear cleanly above fold; preserved WP4 zero-`<script src=>` lock. |
| `/home` | `home.html` | `1.82x` (`1640px`) | **`1.81x` (`1631px`)** | **-0.5%** | `0px` | `0` | Crisp 2×2 calm doorway grid framed symmetrically above fold. |

