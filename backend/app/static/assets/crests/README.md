# Founding Family & Hall of Arms Heraldic Crests (`FUTURE · CARMICHAEL — McCORMICK`)

This directory holds the site-wide heraldic crest assets loaded by the horizontal founding brand lockup across all nine PDEUE portals (`/home`, `/dashboard`, `/member`, `/advisor`, `/admin/tech`, `/lineage/house/{id}`, `/community`, `/community/heritage`, `/companion`) and the Hall of Arms gallery:

- `carmichael_crest.svg` — Carmichael founding family crest (`5:6` aspect ratio, rendered at `40px × 46px` in headers and `5:6` framed cards in the Hall of Arms)
- `mccormick_crest.svg` — McCormick founding family crest (`5:6` aspect ratio, rendered at `40px × 46px` in headers and `5:6` framed cards in the Hall of Arms)
- `house_crest_frame.svg` — Standardized `5:6` crest frame for the 12 family Houses in the Hall of Arms
- `allied_crest_frame.svg` — Standardized `5:6` crest frame for the 28+ allied / married-in surnames in the Hall of Arms

## Zero-Code-Change Full-Color Upgrade Path

The committed `.svg` files are clean, zero-CDN institutional placeholder emblems. To upgrade to high-resolution full-color heraldic artwork site-wide with **zero code changes**:

1. Replace `carmichael_crest.svg` and `mccormick_crest.svg` in this folder with your final vector `.svg` files (keeping the exact filenames and a `5:6` aspect ratio), **or**
2. Drop in per-House or per-surname `.svg`/`.png` artwork into this directory (e.g., `/static/assets/crests/vance.svg`) and assign its local path via the House Genealogist editor in the Hall of Arms.

All assets in this folder are served locally from `/static/assets/crests/` with zero external CDN dependencies (`Play #16B` compliant).
