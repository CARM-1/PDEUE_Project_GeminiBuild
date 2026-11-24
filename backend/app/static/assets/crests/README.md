# Founding Family Heraldic Crests (`FUTURE · CARMICHAEL — McCORMICK`)

This directory holds the site-wide heraldic crest assets loaded by the horizontal founding brand lockup across all seven PDEUE portals (`/dashboard`, `/member`, `/advisor`, `/admin/tech`, `/lineage/house/{id}`, `/community`, `/companion`):

- `carmichael_crest.svg` — Carmichael family crest (`5:6` aspect ratio, rendered at `40px × 46px` with `object-fit: contain`)
- `mccormick_crest.svg` — McCormick family crest (`5:6` aspect ratio, rendered at `40px × 46px` with `object-fit: contain`)

## Zero-Code-Change Full-Color Upgrade Path

The committed `.svg` files are clean, zero-CDN institutional placeholder emblems. To upgrade to high-resolution full-color heraldic artwork site-wide with **zero code changes**:

1. Replace `carmichael_crest.svg` and `mccormick_crest.svg` in this folder with your final vector `.svg` files (keeping the exact filenames and a `5:6` aspect ratio), **or**
2. Drop in high-resolution transparent `.png` files wrapped/named to match (`carmichael_crest.svg` / `mccormick_crest.svg` or matching filenames if switching extensions in the lockup `<img>` tags).

All assets in this folder are served locally from `/static/assets/crests/` with zero external CDN dependencies (`Play #16B` compliant).
