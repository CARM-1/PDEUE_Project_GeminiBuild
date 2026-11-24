# Two-Scale Heraldic Crest System (`FUTURE · CARMICHAEL — McCORMICK`)

This directory holds the self-contained, zero-CDN heraldic crest assets served locally from `/static/assets/crests/` (`Play #16B` compliant) across all nine PDEUE portals (`/home`, `/dashboard`, `/member`, `/advisor`, `/admin/tech`, `/lineage/house/{id}`, `/community`, `/community/heritage`, `/companion`).

## Two-Scale Architecture (`emblem` vs. `achievement`)

Intricate heraldic supporters, helms, and mantling shine in large showcase frames, whereas a `40px × 46px` top-left header slot demands crisp, high-contrast shield geometry. PDEUE separates heraldry into two coordinated scales:

### 1. Compact Header Shield Lockup (`emblem` view — `40px × 46px` across all 9 portals)
- `carmichael_crest.svg` — High-contrast Carmichael shield emblem featuring the blue/crimson wreathed fess over silver with a gold, black, and green heritage accent trim (`5:6` aspect ratio).
- `mccormick_crest.svg` — High-contrast foundational McCormick shield emblem featuring three royal-blue eagles, crimson zigzag `fess dancetté`, and black engrailed border on silver (`5:6` aspect ratio).
- Clicking the compact twin-crest lockup on any portal opens `/community/heritage` (Hall of Arms), where the full heraldic achievements are showcased at large scale.

### 2. Full Heraldic Achievements (`achievement` view — Hall of Arms `/community/heritage` & `/home`)
- `carmichael_achievement.svg` — Full Carmichael heraldic achievement featuring the Hyndford eagle & blue/crimson wreathed inescutcheon, armored arm holding a broken spear, `TOUJOURS PREST` scroll, armored knight supporter with warm medium-brown skin tone, crowned golden African lion supporter, Scottish thistles, and gold/black/green heritage accent ribbon.
- `mccormick_achievement.svg` — Full foundational McCormick heraldic achievement featuring three royal-blue eagles, crimson zigzag `fess dancetté`, black engrailed border, royal-blue eagle crest over helm and mantling, twin golden Highland stags, Scottish thistles, and `SINE TIMORE` scroll.

### 3. 12 Houses (Carmichael + 11 Scottish Bordure-Differenced McCormick Houses) & 28 Allied Surnames
- **House 01 (Carmichael Prime):** Descends from the eldest McCormick daughter (`carmichael_crest.svg` / `carmichael_achievement.svg`).
- **Houses 02–12 (`house_02_mccormick_bordure.svg` – `house_12_mccormick_bordure.svg`):** Descend from foundational McCormick stock, preserving the three royal-blue eagles and crimson zigzag `fess dancetté` shield core while applying distinct Scottish **bordure differencing** (engrailed, indented, wavy, invected, embattled, and compony borders in Sable, Or, Azure, Vert, and Gules).
- `house_crest_frame.svg` & `allied_crest_frame.svg` — Standardized `5:6` institutional frames for custom House uploads and the 28+ allied / married-in surnames.

## Zero-Code-Change Full-Color Upgrade Path

Every asset in this directory supports full-color vector `.svg` or high-resolution `.png` drop-in replacement with **zero code changes**:

1. Replace `carmichael_crest.svg`, `mccormick_crest.svg`, `carmichael_achievement.svg`, `mccormick_achievement.svg`, or any `house_XX_mccormick_bordure.svg` in place (preserving filenames and aspect ratios), **or**
2. Drop in per-House or per-surname `.svg`/`.png` artwork (e.g., `/static/assets/crests/vance.png`) and assign its local path via the scoped House Genealogist editor in the Hall of Arms.
