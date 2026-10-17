# PDEUE WP-8S Data Provenance and Replay Scorecard

Source: `backend/reports/authentic_batch_replay_scorecard.json`.
Mode: **OBSERVATIONS_ONLY**.
Batch status: **INCOMPLETE**. Authentic qualification: **BLOCKED**.
Qualification blockers: MISSING_AUTHENTIC_VENUE_COVERAGE, OFFICIAL_SETTLEMENT_AND_HISTORICAL_L2_NOT_INDEPENDENTLY_VERIFIED.
Financial results use provided scenarios or default calibrated simulation assumptions.
Calibrated fair probability (0.99), winning payout, and inferred spreads are assumptions.
NOAA temperatures remain observations and never create trade prices, lots, or maker fills.
Weather maker fills require a separate validated exchange execution tape.
Retained source integrity passes for 3 unique tapes.
Source hashes verify retained bytes; official contract settlement remains independently unverified.
Production data contains archived station observations; representative trade fixtures live under tests.

| Venue | Coverage | Files | Markets identified | Trade prints | Observations | Admitted / abstained | Maker fills | Capital (cents) | Net PnL (scenario cents) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| polymarket | NO_TAPES | 0 | 0 | 0 | 0 | 0 / 0 | 0 | 0 | 0 |
| kalshi | NO_TAPES | 0 | 0 | 0 | 0 | 0 / 0 | 0 | 0 | 0 |
| weather | EVALUATED | 3 | 0 | 0 | 3 | 0 / 3 | 0 | 0 | 0 |

| Metric | Unique-capture result |
| --- | ---: |
| Total unique trades | 0 |
| Markets with independent scenarios | 0 |
| Total unique weather observations | 3 |
| Post-decision token prints replayed | 0 |
| Initialization prints excluded | 0 |
| Maker fill events | 0 |
| Filled / posted lot rate | 0.00% |
| Filled volume (lots) | 0 |
| Deployed capital (cents) | 0 |
| Capital deployment rate | 0.00% |
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

Adversarial stress status: **NO_EXECUTION_TAPES**.

| Assumed stress case | Captures | Fill rate | Capital (cents) | Net PnL (scenario cents) |
| --- | ---: | ---: | ---: | ---: |
| No exchange execution tapes | 0 | 0% | 0 | 0 |

Stress cases require exchange prints. Slippage requires SELL flow at least two cents
through our bid; widened spreads above eight cents block new orders; queue exhaustion
uses full-horizon seller volume plus one lot as an adversarial bound. Zero-payout
resolution measures losses with unchanged fills. These are explicit simulations.

The batch evaluated 3 files and parsed 0
records: 3 unique captures and 0 duplicate copies.
File-level admissions/abstentions/rejections: 0/3/0.
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
The former 30 identical Polymarket captures have been removed from active replay.
One byte-identical original remains in `data/quarantine/polymarket/global_capture.json`;
`data/venues/polymarket/quarantine_manifest.json` records all purged names and hashes.
Its 41 condition IDs do not match the settled-market manifest. No such prints qualify
as distinct settled events. Authentic Kalshi archives are still missing.
Weather observations have no verified strike terms, official daily climate settlement,
or exchange executions. Their availability is conservatively set to archive retrieval
because historical publication times are unknown. No station observation can produce PnL.
Missing venue datasets: polymarket, kalshi.
