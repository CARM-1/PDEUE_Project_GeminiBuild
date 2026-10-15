# PDEUE WP-8P Maker Fill Calibration Scorecard

Source: `backend/reports/authentic_batch_replay_scorecard.json`.
Mode: captured trades with **simulated Strategy D maker execution and assumed settlement**.
The spread, five-lot queue, fair-value inputs, and winning payout are assumptions;
these are not observed Level 2 books or official realized venue profits.

| Metric | Unique-capture result |
| --- | ---: |
| Total unique trades | 100 |
| Post-decision token prints replayed | 9 |
| Initialization prints excluded | 2 |
| Maker fill events | 1 |
| Filled volume (lots) | 10 |
| Deployed capital (cents) | 590 |
| Settlement payout (simulated cents) | 1000 |
| Fees (cents) | 0 |
| Net realized PnL (simulated cents) | 410 |

| ADR-008 allocation | Rule | Integer cents |
| --- | --- | ---: |
| SCMA | 87% floor on gains; all losses | 356 |
| FAEP | 3% floor on gains | 12 |
| CFCP | 10% plus residual on gains | 42 |
| Total | Equals net PnL exactly | 410 |

Unique-capture cent conservation: **PASS**.

The batch evaluated 30 files and parsed 3000
records: 1 unique captures and 29 duplicate copies.
File-level admissions/abstentions/rejections: 30/0/0.
Financial headline metrics count each capture once. Repeated-file totals remain
in the JSON for comparison and must not be treated as independent executions.

The initial token print seeds the assumed best bid; ask is bid+2 cents and the
resting inside bid is bid+1. Five lots ahead must clear before fills. Decisions
follow the initial timestamp, and every print at that timestamp is excluded.
Only subsequent SELL prints at or below the limit consume queue; fills are priced
at the resting limit. Other outcome tokens and BUY prints cannot fill that bid.

The corrected harvester uses market-filtered offset pagination, exact condition
and YES-token verification, and cross-market hash uniqueness before writing files.
Fresh harvesting has not been verified for this offline report. Existing duplicate
captures remain preserved; their filename markets do not establish their contents'
settled-market provenance. Official settlement is not available for this simulation.
