# PDEUE WP-8R Multi-Venue Calibrated Replay Scorecard

Source: `backend/reports/authentic_batch_replay_scorecard.json`.
Mode: **AUTO_SCENARIO_SIMULATION**.
Financial results use provided scenarios or default calibrated simulation assumptions.
Calibrated fair probability (0.99), winning payout, and inferred spreads are assumptions.
NOAA temperatures remain observations and never create trade prices, lots, or maker fills.
Weather maker fills require a separate validated exchange execution tape.
Representative fixtures are labeled SYNTHETIC_REPRESENTATIVE; authentic provenance remains unverified.

| Venue | Coverage | Files | Markets identified | Trade prints | Observations | Admitted / abstained | Maker fills | Capital (cents) | Net PnL (scenario cents) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| polymarket | EVALUATED | 30 | 41 | 3000 | 0 | 30 / 0 | 0 | 0 | 0 |
| kalshi | EVALUATED | 2 | 2 | 14 | 0 | 2 / 0 | 4 | 770 | 1230 |
| weather | EVALUATED | 2 | 4 | 7 | 10 | 1 / 1 | 2 | 460 | 540 |

| Metric | Unique-capture result |
| --- | ---: |
| Total unique trades | 121 |
| Markets with independent scenarios | 0 |
| Total unique weather observations | 10 |
| Post-decision token prints replayed | 15 |
| Initialization prints excluded | 7 |
| Maker fill events | 6 |
| Filled volume (lots) | 30 |
| Deployed capital (cents) | 1230 |
| Settlement payout (scenario cents) | 3000 |
| Fees (cents) | 0 |
| Net realized PnL (scenario cents) | 1770 |

| ADR-008 allocation | Rule | Integer cents |
| --- | --- | ---: |
| SCMA | 87% floor on gains; all losses | 1538 |
| FAEP | 3% floor on gains | 52 |
| CFCP | 10% plus residual on gains | 180 |
| Total | Equals net PnL exactly | 1770 |

Unique-capture cent conservation: **PASS**.

The batch evaluated 34 files and parsed 3021
records: 5 unique captures and 29 duplicate copies.
File-level admissions/abstentions/rejections: 33/1/0.
Financial headline metrics count each capture once. Repeated-file totals remain
in the JSON for comparison and must not be treated as independent executions.

Calibration chooses contract/token from the initial timestamp only. Observation time
is that timestamp and decision is 1ns later. Expiry is initial + 300s, or a
predeclared weather strike expiry. No future print affects these choices.
A supplied initial L2 book must match the contract/token and be available by the
initial timestamp. Otherwise the first print seeds an assumed two-cent spread.
The resting bid sits one cent above best bid; queue ahead is at least five lots
and at least the initial best-bid depth. Strategy D SELL prints clear queue before
filling at our bid. BUY prints and initialization prints cannot fill.

Weather bounds match the selected strike station and expiry. Brackets are
half-open [lower, upper); late-published and post-expiry observations are excluded.
Observation-only tapes abstain with NO_EXECUTION_TAPE. Execution-enabled weather
fixtures include separate exchange trade records; temperatures never become flow.
The modeled payout is not an official station settlement certification.

External scenarios take precedence over calibration. Use `--no-calibrate` to
require independent scenarios. Invalid tapes abstain, mark validation REJECTED,
and make the batch INCOMPLETE with a nonzero CLI exit.

The corrected harvester uses market-filtered offset pagination, exact condition
and YES-token verification, and cross-market hash uniqueness before writing files.
Fresh harvesting has not been verified for this offline report. Existing duplicate
captures remain preserved; their filename markets do not establish their contents'
settled-market provenance. Official settlement is not available for this simulation.
Missing venue datasets: none.
