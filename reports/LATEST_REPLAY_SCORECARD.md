# PDEUE WP-8Q Multi-Category Replay Scorecard

Source: `backend/reports/authentic_batch_replay_scorecard.json`.
Mode: **INDEPENDENT_SCENARIO_REPLAY**.
Financial results use provided scenarios, or explicitly opted-in Polymarket
calibration assumptions. Missing external scenarios abstain. NOAA temperatures
remain observations and never create trade prices, lots, or maker fills.

| Venue | Coverage | Files | Markets identified | Trade prints | Observations | Admitted / abstained |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| polymarket | EVALUATED | 30 | 41 | 3000 | 0 | 0 / 30 |
| kalshi | NO_TAPES | 0 | 0 | 0 | 0 | 0 / 0 |
| weather | NO_TAPES | 0 | 0 | 0 | 0 | 0 / 0 |

| Metric | Unique-capture result |
| --- | ---: |
| Total unique trades | 100 |
| Markets with independent scenarios | 0 |
| Total unique weather observations | 0 |
| Post-decision token prints replayed | 0 |
| Initialization prints excluded | 0 |
| Maker fill events | 0 |
| Filled volume (lots) | 0 |
| Deployed capital (cents) | 0 |
| Settlement payout (scenario cents) | 0 |
| Fees (cents) | 0 |
| Net realized PnL (scenario cents) | 0 |

| ADR-008 allocation | Rule | Integer cents |
| --- | --- | ---: |
| SCMA | 87% floor on gains; all losses | 0 |
| FAEP | 3% floor on gains | 0 |
| CFCP | 10% plus residual on gains | 0 |
| Total | Equals net PnL exactly | 0 |

Unique-capture cent conservation: **PASS**.

The batch evaluated 30 files and parsed 3000
records: 1 unique captures and 29 duplicate copies.
File-level admissions/abstentions/rejections: 0/30/0.
Financial headline metrics count each capture once. Repeated-file totals remain
in the JSON for comparison and must not be treated as independent executions.

Kalshi uses explicit external fair probability, binary payout, book, capital, and
point-in-time bounds. Strategy D SELL flow at or below the resting bid clears queue
before filling at that bid; BUY flow cannot fill it. Independent settlement inputs
do not alter prior fills. Kalshi does not accept synthetic auto-scenarios.

Weather bounds must match the selected strike's station and expiry. Brackets are
half-open [lower, upper); post-expiry or late-published observations are excluded.
Even qualified observation evaluation abstains with NO_EXECUTION_TAPE when no
execution data exists. These are not official station settlement certifications.

Explicit Polymarket calibration can seed a spread from the first token timestamp,
excluding that timestamp from execution. Its spread, five-lot queue, model, and
winning payout remain assumptions. It is disabled by default in the batch CLI.

The corrected harvester uses market-filtered offset pagination, exact condition
and YES-token verification, and cross-market hash uniqueness before writing files.
Fresh harvesting has not been verified for this offline report. Existing duplicate
captures remain preserved; their filename markets do not establish their contents'
settled-market provenance. Official settlement is not available for this simulation.
Missing venue datasets: kalshi, weather.
