# Kalshi replay fixtures

`raw_trades_macro.json` and `raw_trades_rates.json` are deterministic,
**SYNTHETIC_REPRESENTATIVE** qualification fixtures, not authentic exchange
captures. Each file declares this in `provenance`. Direct venue access was denied
by the managed environment's outbound policy; no venue credentials were available.

The public trade response shape follows `authentic_kalshi_tape_loader.py`:
`trades[]` contains trade ID, ticker, nanosecond timestamp, integer YES price,
lot count, and taker side. `taker_side=no` normalizes to aggressive YES selling.
`initial_book` is a separate normalized L2 snapshot with integer cent/lot levels
and an explicit timestamp and contract. Its levels are representative assumptions.

Vectors cover same-timestamp initialization, BUY exclusion, queue depletion,
partial maker fills, price-through SELL flow, and out-of-horizon exclusion.
They are suitable for regression replay, not historical profit certification.
Replace them with archived responses and verifiable acquisition metadata before
claiming authentic coverage. Public API reference:
https://docs.kalshi.com/api-reference/market/get-trades
