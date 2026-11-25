# Two-Scale Heraldic Crest System (`FUTURE · CARMICHAEL — McCORMICK`)

This directory holds the self-contained, zero-CDN heraldic crest assets served locally from `/static/assets/crests/` (`Play #16B` compliant) across all nine PDEUE portals (`/home`, `/dashboard`, `/member`, `/advisor`, `/admin/tech`, `/lineage/house/{id}`, `/community`, `/community/heritage`, `/companion`).

## Two-Scale Architecture (`emblem` vs. `achievement`)

Intricate heraldic supporters, helms, and mantling shine in large showcase frames, whereas a `40px × 46px` top-left header slot demands crisp, high-contrast shield geometry. PDEUE separates heraldry into two coordinated scales:

### 1. Compact Header Shield Lockup (`emblem` view — `40px × 46px` across all 9 portals)
- `carmichael_crest.svg` — High-contrast Carmichael shield emblem featuring the blue/crimson wreathed fess over silver with a gold, black, and green heritage accent trim (`5:6` aspect ratio).
- `mccormick_crest.svg` — High-contrast foundational McCormick shield emblem featuring three royal-blue eagles, crimson zigzag `fess dancetté`, and black engrailed border on silver (`5:6` aspect ratio).
- Clicking the compact twin-crest lockup on any portal opens `/community/heritage` (Hall of Arms), where the full heraldic achievements are showcased at large scale.

### 2. Full Heraldic Achievements (`achievement` view — Hall of Arms `/community/heritage`, `/home`, & House History Pages)
- `carmichael_achievement.svg` — Finalized House 01 (Carmichael) full heraldic achievement featuring:
  - **Official Motto:** `IEHOVA SEMPER VIGILANS` on the upper heraldic scroll.
  - **Crest (SAC Homage):** A single seamless bent dark-steel armored arm and articulated gauntlet gripping bright yellow heraldic lightning bolts and a slender green olive branch—paying homage to the Founder's father's Cold War service in the U.S. Air Force Strategic Air Command (SAC).
  - **Shield, Coronet & Mantling:** Gold shield bearing the black displayed eagle with the central silver Carmichael inescutcheon (twisted royal-blue and crimson wreathed fess) accented with a subtle dark-green and gold inner border, surmounted by an ornate jewelled gold coronet, steel helm, and sweeping royal-blue, crimson, and burnished-gold acanthus mantling.
  - **Supporters & Compartment:** On the left, a dignified African American knight in dark steel plate armor accented with subtle gold lightning-bolt trim, wearing his steel helmet with the visor raised; on the right, a crowned golden Barbary lion with a rich dark-brown/black mane—standing upon Scottish purple thistles and a braided gold-and-green heritage ribbon.
- `mccormick_achievement.svg` — Full foundational McCormick heraldic achievement featuring three royal-blue eagles, crimson zigzag `fess dancetté`, black engrailed border, royal-blue eagle crest over helm and mantling, twin golden Highland stags, Scottish thistles, and `SINE TIMORE` scroll.

### 3. 12 Houses (Carmichael + 11 Scottish Bordure-Differenced McCormick Houses) & 28 Allied Surnames
- **House 01 (Carmichael Prime):** Descends from the eldest McCormick daughter (`carmichael_crest.svg` / `carmichael_achievement.svg` or raster drop-in).
- **Houses 02–12 (`house_02_mccormick_bordure.svg` – `house_12_mccormick_bordure.svg`):** Descend from foundational McCormick stock, preserving the three royal-blue eagles and crimson zigzag `fess dancetté` shield core while applying distinct Scottish **bordure differencing** (engrailed, indented, wavy, invected, embattled, and compony borders in Sable, Or, Azure, Vert, and Gules).
- `house_crest_frame.svg` & `allied_crest_frame.svg` — Standardized `5:6` institutional frames for custom House uploads and the 28+ allied / married-in surnames.

## Automatic High-Resolution Raster Drop-In & Zero-Code-Change Upgrade Path

Every achievement asset in this directory supports **automatic high-resolution raster drop-in replacement** resolved at request time by `resolve_heraldic_asset_path()` in `backend/app/domain/heritage_community_service.py` with **zero code changes**:

1. **Drop-In Priority Order (Automatic Raster Over SVG Fallback):**
   - Place `carmichael_achievement.png` or `carmichael_achievement.jpg` (or `mccormick_achievement.png` / `mccormick_achievement.jpg`) directly into `backend/app/static/assets/crests/`.
   - The asset resolver checks filenames in deterministic priority order:
     1. `<stem>.png` (preferred lossless high-resolution raster)
     2. `<stem>.jpg`
     3. `<stem>.jpeg`
     4. `<stem>.svg` (crisp zero-CDN vector fallback when no raster file is present)
   - `/home`, `/community/heritage`, `/community/heritage/house/1`, `/community/heritage/surname/carmichael`, and `/api/v1/portal/community/heritage` automatically detect and serve the high-resolution raster asset—and cleanly fall back to `carmichael_achievement.svg` / `mccormick_achievement.svg` when no raster file is present.
2. **In-Place Vector Replacement or Per-Surname Uploads:**
   - Replace `carmichael_crest.svg`, `mccormick_crest.svg`, `carmichael_achievement.svg`, `mccormick_achievement.svg`, or any `house_XX_mccormick_bordure.svg` in place (preserving filenames and aspect ratios), **or**
   - Drop in per-House or per-surname `.svg`/`.png`/`.jpg` artwork (e.g., `/static/assets/crests/vance.png`) and assign its local path via the scoped House Genealogist editor in the Hall of Arms.
