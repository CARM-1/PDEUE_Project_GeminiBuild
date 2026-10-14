# WP-8L static Bitcoin replay

`static_crypto_history.jsonl` is a **synthetic historical test vector**, not a
captured exchange feed. It freezes 100 chronological Level 2 trade-print events
for `BTC-20250102-100000-YES`, a Bitcoin-at-or-above-$100,000 binary contract.
The tape starts at 2025-01-01 00:00:00 UTC, advances one minute per event, and
uses integer nanosecond timestamps, integer cent prices, and whole-contract
volumes. BUY/SELL denotes the initiating side for YES-contract trades.

SHA-256: `bc43fc32bb4ce91f16f3900d9de46ae1c38e2d0f1faa9f94212e657b1ae03370`.
The test pins this digest; testing never generates or downloads replacement data.
Changes to this vector require deliberate review and an updated expected digest.

Run from `backend/` with `./run_walk_forward_replay.py` or
`python run_walk_forward_replay.py`. `--fixture PATH` selects another validated
local tape. The runner resolves its default path independently of the working
directory, performs no network requests, and emits a deterministic JSON report.

## Scenario assumptions

Trade prints carry neither Bitcoin spot prices nor book snapshots. The harness
therefore makes these inputs explicit in `ReplayScenario`:

- Independent Bitcoin spot and strike: $100,000; annual volatility: 60%; rate: 0.
- Observation two seconds before the tape; maker decision one second before it.
- Expiry: 2025-01-02 00:00:00 UTC; settlement spot: $101,000.
- Initial L2 YES bid: 45 cents with 20 displayed contracts; ask: 49 cents.
- Inside maker limit: 46 cents, with zero displayed depth at that new level.
- Requested quantity: 10; initial capital: 10,000 cents; maker fee: zero cents.

The independent probability is the Black-Scholes risk-neutral terminal
log-normal tail `Phi(d2)`, using a 365-day year. Contract quotes enter only the
execution price and net edge, never the probability estimate. Net edge is
`p_fair - (limit_price_cents + fee_cents_per_contract) / 100`; it must be at least
0.03 before any quantity is posted. A failed gate deploys exactly zero cents.

This single-contract walk-forward vector posts one bid before the tape, then
processes all prints in order. Only subsequent seller-initiated prints at the
limit consume `Q_ahead`, then fill whole contracts in FIFO order. No print below
the limit is assumed to prove a fill. Unknown cancellations, hidden liquidity,
and book changes are not invented; this is a deterministic static-book execution
model, not a full venue simulator. The separate queue tests exercise nonzero
queue depth, exact exhaustion, wrong-side prints, and partial fills.

Unfilled quantity is cancelled at expiry. Settlement spot is used only after all
prints, never for admission or fills. Cost, fees, payout, capital, and the
87/10/3 waterfall use integer cents throughout. The existing SettlementEngine
assigns every residual profit cent to CFCP under ADR-008; losses stay in SCMA.

Default replay: 10 filled contracts, 460 cents deployed, 1,000 cents payout,
540 cents profit, 10,540 cents final capital. The waterfall is 469 cents SCMA,
55 cents CFCP, and 16 cents FAEP.

## Validation on ring1-alpha

Base revision: `3a2e36d922747baa88b6565e852cf1f49e61065f`.

- `cd backend && PYTHONPATH=. pytest tests/ -q`: 522 passed, 27 failed.
- Untouched base in an isolated worktree: 498 passed, the identical 27 failed.
- Focused replay and operator checks: 26 passed (24 new tests, 2 existing tests).
- No new full-suite failures, and no ImportError or ModuleNotFoundError.
- The base reproduces the circular import when Python starts in `app/domain`
  (`operator` -> `typing` -> `collections` -> partially initialized `operator`).
  The renamed module passes that same subprocess regression.

The 27 existing full-suite failures are not import failures: they include the
missing sports adapter `underwrite_game` method, accounting outbox schema
rejection of `source`, container/systemd packaging checks, and a cockpit UI
expectation. The namespace repair does not clear those unrelated failures.
FastAPI TestClient requires local socket access in the execution sandbox; the
full suite was run with the executor's network permission enabled.
