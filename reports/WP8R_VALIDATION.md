# WP-8R validation and remaining acceptance gaps

Base: `ring1-alpha` at `a45575c7bfa4345d2b7e2ecc2d5f7d2af9056aa3`.

## Replay verification

`cd backend && PYTHONPATH=. python scripts/run_batch_authentic_replay.py --calibrate`
completed successfully. The default command produces the same scorecard.

| Metric | Result |
| --- | ---: |
| Files: Polymarket / Kalshi / Weather | 30 / 2 / 2 |
| Parsed trades / observations | 3,021 / 10 |
| Unique captures / duplicate copies | 5 / 29 |
| Maker fills / lots | 6 / 30 |
| Deployed capital (cents) | 1,230 |
| Assumed settlement payout (cents) | 3,000 |
| Simulated net PnL (cents) | 1,770 |
| SCMA / CFCP / FAEP (cents) | 1,538 / 180 / 52 |

Financial headlines count duplicate captures once. ADR-008 sums per-capture floor
allocations and CFCP residuals; it does not re-round aggregate PnL. Conservation
passes exactly. Kalshi and execution-enabled weather fixtures fill. Existing
Polymarket captures produce no fills with the initial-time selection policy; the
cross-venue regression vector separately verifies Polymarket Strategy D fills.
Observation-only KORD abstains with `NO_EXECUTION_TAPE`.

## Tests

```sh
cd backend
PYTHONPATH=. pytest --rootdir=. tests/test_authentic* tests/test_batch_authentic_replay.py tests/test_walk_forward_replay_harness.py tests/test_wp8r_calibrated_replay.py -v
```

Result: **186 passed**, zero failures, skips, or errors. Coverage includes future
contract/price/end-time invariance, token selection, queue consumption, BUY and
same-timestamp exclusion, expiry, invalid L2, corrupt weather executions, scenario
precedence, losing weather settlement, CLI defaults/opt-out, and cent accounting.

Requested full command:

```sh
cd backend
PYTHONPATH=. pytest --rootdir=. tests/ -v
```

This branch: **700 passed, 29 failed**, zero skips/errors (8 warnings).
An untouched detached worktree at the base commit: **681 passed, the same 29
failed**, zero skips/errors (8 warnings). There are **no new failing test IDs**.
The full-suite green acceptance condition remains unmet. Failures include
existing IF-038 schema/source-field mismatch, dispatch methods, packaging
assertions, and adapter expectations. Verification required network permission
for local FastAPI TestClient asynchronous sockets; the default sandbox stalled.

## Authentic fixture acquisition remains blocked

Direct Kalshi acquisition returned HTTP CONNECT 403 from the managed outbound
policy. No venue credentials or archived captures were configured. The four new
files declare `SYNTHETIC_REPRESENTATIVE` provenance and `authentic_capture=false`.
Weather GeoJSON values and strike definitions are constructed schema vectors,
not NOAA measurements. The report marks fresh harvest, authentic provenance,
and official settlement unverified.

Calibration's 0.99 fair probability, ten-lot order, zero fees, and winning payout
are simulation assumptions. Authentic-capture acceptance remains unmet pending
archived source data or permitted venue/NOAA acquisition. This PR should remain
a draft until authentic inputs and full regression clearance are available.
