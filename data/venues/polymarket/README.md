# Polymarket settled archive qualification (WP-8S)

The 30 former `raw_trades_*.json` files contained identical 100-print global
snapshots. Their 41 actual condition IDs have no intersection with
`raw_settled_markets_manifest.json`. All 30 active copies were removed.
A byte-identical original remains at `data/quarantine/polymarket/global_capture.json`.
`quarantine_manifest.json` records its SHA-256, all removed names, and the reason.
The quarantined capture is excluded from batch discovery and the default loader.

There are currently **zero qualified settled Polymarket captures**. The managed
proxy denies `data-api.polymarket.com` with CONNECT 403. A missing market archive
never falls back to a global or foreign feed.

Import independently captured public pages from the backend directory:

```sh
PYTHONPATH=. python -m app.adapters.authentic_venue_harvester \
  --offline-dir ../work/polymarket_pages --page-size 100 --limit 30
```

Each `<full_condition_id>.json` envelope contains `condition_id`, `source_url`
(`https://data-api.polymarket.com/trades?market=<condition_id>`), `retrieved_at`
(ISO timestamp), `page_size`, and `pages` (an array of original response arrays).
A full page requires another page; an empty or short final page terminates
pagination. Missing terminal pages, repeated pages, conflicting duplicate IDs,
foreign conditions, and cross-market overlap fail before capture writes.
Only the manifest's exact YES token is retained. Duplicate manifest markets
are visited once. Missing offline captures are skipped without relabeling data.

Original envelopes are retained under `sources/`. `provenance_manifest.json`
binds source bytes, tape bytes, acquisition URL/time, and manifest bytes by
SHA-256. Integrity does not establish independent authenticity or settlement.
The manifest still needs review against official resolution evidence.
