# Kalshi archive coverage is missing

No authentic settled-contract trade/L2 archive was available. The former
`raw_trades_macro.json` and `raw_trades_rates.json` files are explicitly synthetic
and moved to `backend/tests/fixtures/representative_venues/kalshi/`.
They cannot qualify authentic venue coverage. The public Kalshi API returns
proxy CONNECT 403 under the managed destination policy.

Import an independently acquired archive:

```sh
cd backend
PYTHONPATH=. python -m app.adapters.kalshi_archive_harvester \
  ../work/settled_kalshi_capture.json --output-dir ../data/venues/kalshi
```

An archive must include `source_url`, `retrieved_at`, an original `market`
response with matching `ticker`, `status="settled"`, and `result="yes"` or
`"no"`, plus `trades` and a historical normalized `initial_book`. Trades
must satisfy `authentic_kalshi_tape_loader.py`. The book identifies the same
contract, has an integer nanosecond timestamp no later than the first trade,
and contains nonempty integer-cent/lot `bids` and `asks` without a crossed spread.
No order book is inferred from trades or a current settled-market book.

The exact source envelope is retained under `sources/`, linked by SHA-256.
Imports validate schema, attribution, contract consistency, settlement shape,
and timing. Byte integrity alone cannot certify attribution or official outcome;
`official_settlement_verified` stays false. Source envelopes are excluded from
batch discovery to prevent counting the same capture twice.
