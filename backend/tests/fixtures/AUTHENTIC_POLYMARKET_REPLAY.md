# WP-8M / WP-8N / WP-8P authentic Polymarket replay

From `backend`, run:

```sh
PYTHONPATH=. python run_walk_forward_replay.py --mode=static
PYTHONPATH=. python run_walk_forward_replay.py --mode=authentic
PYTHONPATH=. python run_walk_forward_replay.py --mode=authentic --tape=/path/to/raw_trades.json --scenario=/path/to/scenario.json
PYTHONPATH=. python run_walk_forward_replay.py --mode=authentic --auto-scenario
PYTHONPATH=. python run_walk_forward_replay.py --mode=authentic --auto-scenario --contract-id=0x...
PYTHONPATH=. python scripts/run_batch_authentic_replay.py
```

The default authentic path is repository-relative:
`data/venues/polymarket/raw_trades_0x0c4cd2055d6ea8.json`.
Supply a captured JSON array. The adapter accepts paths to other
`raw_trades_*.json` captures and preserves title as `contract_spec`.
It rejects malformed records and duplicate transaction hashes (including dust),
discards lots whose floored size is nonpositive, and sorts by
`(timestamp_ns, trade_id)`. Equal seconds are valid with strictly increasing IDs.
Python `int(round(price * 100))` supplies the specified round-to-even conversion;
normalized prices may include zero and 100 cents.

A raw trade tape does not supply independent Bitcoin spot, volatility, a prior
L2 book, queue depth, or a settlement outcome. Without a scenario or explicit
`--auto-scenario` opt-in, the harness
counts and hashes the tape, reports `reason: ABSTAINED`, leaves `p_fair` and
`net_edge` null, and posts no order. It never substitutes static model assumptions
or derives them from future prints.

The optional scenario JSON must include every `ReplayScenario` field:
`contract_id`, `observed_at_ns`, `decision_at_ns`, `expiry_ns`, `spot`, `strike`,
`volatility`, `rate`, `settlement_spot`, `best_bid_cents`, `best_ask_cents`,
`bid_depth`, `quantity`, `fee_cents_per_contract`, and `initial_capital_cents`.
JSON book price keys are converted to integer cents. The caller must establish
independent point-in-time inputs and the actual contract/settlement interpretation;
this harness models one Bitcoin YES binary contract. `run_authentic()` validates
the entire raw tape, then filters to the explicit scenario contract. An empty
selection produces a full scorecard with `NO_MATCHING_CONTRACT_PRINTS`. Corrupt
foreign rows still fail validation before filtering. Direct `run_prints()` calls
continue to reject mixed-contract vectors. Invalid books and
observations/decision/prints/expiry ordering fail closed.
Settlement is used only after queue replay. Authentic captures are market data;
fills remain simulated executions under the existing queue model.

The static scorecard schema and calculations remain unchanged. Authentic
scorecards use the same execution and integer waterfall implementation, with
`reason` equal to `ADMITTED` or `ABSTAINED` and an `abstention_detail` when needed.
Positive PnL floors SCMA at 87% and FAEP at 3%; CFCP receives 10% plus residual.
Losses remain entirely in SCMA. The digest covers the original file bytes read
once for hashing and parsing.

`--contract-id` selects a contract from a multi-contract tape. With an explicit
scenario, the IDs must agree. Selecting a contract alone still abstains without
independent inputs. `--auto-scenario` applies only when a scenario file is absent;
an explicit scenario takes precedence. Without a requested ID, auto mode chooses
the highest normalized trade count, breaking ties by contract ID ascending.

Auto mode isolates the initial outcome token, observes its first print, and
decides one nanosecond later. All prints at the initial timestamp seed the
scenario and are excluded from execution. Expiry is 300s after the last selected
token print. The assumed best bid is the initial print level clipped to 1..97
cents, the ask is bid+2, and the resting inside bid is bid+1. Five assumed lots
ahead must clear before fills, independent of visible best-bid depth.
It assumes spot=102000, strike=100000, volatility=0.60, rate=0,
10 requested lots, zero fees,
10000 cents of initial capital, and a winning settlement spot of 101000.
These are disclosed simulation assumptions, not observed pre-trade market data.
The scorecard includes the generated scenario and labels the PnL basis
`SIMULATED_SETTLEMENT` and settlement source `ASSUMED_WIN`.

Auto quotes and sizing do not use future trade prices or volumes. Dominant
contract selection and expiry use full-capture metadata as requested; this
workflow therefore does not certify an independently observed zero-lookahead
trading strategy. The real contract expiry and settlement must be supplied
independently for a historical performance claim. Admission follows the existing
edge and capacity gates; it does not guarantee a fill.

The batch script discovers every `raw_trades_*.json` in the repository-relative
data directory and writes `backend/reports/authentic_batch_replay_scorecard.json`.
The default run also overwrites `reports/LATEST_REPLAY_SCORECARD.md`. Custom JSON
outputs do not update that tracked report unless `--markdown-output` is provided.
Paths work from any working directory. `--tape-dir` and `--output` support other
locations; `--expected-tapes` and `--expected-trades` default to 30 and 3000.
Missing files, count mismatches, or corrupt tapes produce `INCOMPLETE` and a
nonzero CLI exit, with actual counts and per-file rejection details preserved.

Batch totals distinguish raw records, normalized parsed trades, and selected
replayed trades. File totals include duplicate captures; separate digest groups
and unique-capture totals expose repetition. Waterfall totals sum each replay's
allocations and conserve total PnL; they do not re-round the combined PnL.
The executive scorecard prints admitted/abstained/rejected counts, unique-capture
fills, deployed lots and cents, simulated realized PnL, and SCMA/FAEP/CFCP
conservation. Different capture digests with overlapping trade IDs are rejected;
identical captures are disclosed and counted once in the financial headline.

The current 30 files each contain the same 100-trade capture (one unique digest).
The dominant condition has 21 prints, split between 11 Up-token and 10 Down-token
prints. The initial Up-token timestamp excludes two initialization prints; nine
subsequent token prints replay. Strategy D consumes only SELL flow at or below
the resting limit; fills execute at our bid, not the observed trade price. BUY
flow and other tokens cannot consume queue or grant fills. Static replay retains
its existing stricter exact-price-only execution policy.

Deduplicated calibration produces one 10-lot fill at 59 cents, deploying 590
cents. The assumed winning payout is 1000 cents, simulated PnL is 410 cents, and
the waterfall is SCMA 356, FAEP 12, CFCP 42. The 30 existing copies remain intact;
these are one independent capture, not 30 independently harvested markets.

The harvester now reads the saved settled-market manifest, queries the supported
`market` filter with increasing offsets and `takerOnly=false`, verifies the exact
condition ID and YES token, and deduplicates page overlap by transaction hash.
Repeated pages, foreign trades, conflicting duplicate records, overlapping
market hashes, unresolved settlements, or incomplete pagination fail closed.
All captures are staged before any files are written, and full condition IDs
prevent filename prefix collisions.

Run `PYTHONPATH=. python -m app.adapters.authentic_venue_harvester --limit=30`
from `backend` after enabling `data-api.polymarket.com` in the runtime network
policy. This session's fresh harvest attempt received proxy 403 Forbidden and
left the original captures unchanged. Fresh nonoverlapping archive qualification
remains pending; the regenerated scorecards explicitly report an offline simulation.
