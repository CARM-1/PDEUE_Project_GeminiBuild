# WP-8M authentic Polymarket replay

From `backend`, run:

```sh
PYTHONPATH=. python run_walk_forward_replay.py --mode=static
PYTHONPATH=. python run_walk_forward_replay.py --mode=authentic
PYTHONPATH=. python run_walk_forward_replay.py --mode=authentic --tape=/path/to/raw_trades.json --scenario=/path/to/scenario.json
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
L2 book, queue depth, or a settlement outcome. Without a scenario the harness
counts and hashes the tape, reports `reason: ABSTAINED`, leaves `p_fair` and
`net_edge` null, and posts no order. It never substitutes static model assumptions
or derives them from future prints.

The optional scenario JSON must include every `ReplayScenario` field:
`contract_id`, `observed_at_ns`, `decision_at_ns`, `expiry_ns`, `spot`, `strike`,
`volatility`, `rate`, `settlement_spot`, `best_bid_cents`, `best_ask_cents`,
`bid_depth`, `quantity`, `fee_cents_per_contract`, and `initial_capital_cents`.
JSON book price keys are converted to integer cents. The caller must establish
independent point-in-time inputs and the actual contract/settlement interpretation;
this harness supports a single Bitcoin YES binary contract. Contract mismatches,
invalid books, and observations/decision/prints/expiry ordering fail closed.
Settlement is used only after queue replay. Authentic captures are market data;
fills remain simulated executions under the existing queue model.

The static scorecard schema and calculations remain unchanged. Authentic
scorecards use the same execution and integer waterfall implementation, with
`reason` equal to `ADMITTED` or `ABSTAINED` and an `abstention_detail` when needed.
Positive PnL floors SCMA at 87% and FAEP at 3%; CFCP receives 10% plus residual.
Losses remain entirely in SCMA. The digest covers the original file bytes read
once for hashing and parsing.

The named capture was absent from the checkout and current `ring1-alpha` at
implementation time. Its end-to-end test explicitly skips until the file is
provided. Raw-format test vectors are synthetic and do not claim captured venue
provenance. No authentic qualification result should be claimed from that skip.
