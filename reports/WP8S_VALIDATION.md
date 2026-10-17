# WP-8S provenance work: partial delivery, qualification blocked

Base: `ring1-alpha` at `df4227a0df2ce0432fb28842a1fcbd9cb9df1511`.
Branch: `codex/wp8s-authentic-data-provenance`.

## Delivered

- Archived KORD, KDEN, and KJFK METAR observations with exact nanosecond UTC
  conversions, ASOS tenth-degree temperatures, retained source excerpts, upstream
  Git blob verification, full/excerpt SHA-256, and acquisition metadata.
- NOAA/IEM fetch and offline METAR import modes. Unknown historical publication
  times use conservative retrieval-time availability.
- Removal of 30 byte-identical Polymarket global snapshots from active data.
  One original is preserved under `data/quarantine/polymarket/`; an audit manifest
  lists every removed name and hash. Its 41 actual conditions match none of the
  settled manifest, so no tape is relabeled as a settled market.
- Offline market-specific Polymarket page iteration, terminal-page checks,
  YES-token selection, overlap rejection, and retained source/tape receipts.
- Kalshi offline importer requiring matching settled-market metadata, actual
  trade fields, and an archived historical initial L2 snapshot. It does not
  fabricate data or independently certify source attribution.
- Synthetic Kalshi/weather vectors moved unchanged into test fixtures.
- Explicit slippage, wide-spread, queue-exhaustion, and zero-payout stress cases;
  aggregate fill/deployment rates and ADR-008 conservation; strict qualification
  mode and discovery exclusion for source envelopes/quarantined captures.

## Production replay

```sh
cd backend
PYTHONPATH=. python scripts/run_batch_authentic_replay.py \
  --no-calibrate --require-authentic --stress
```

Expected exit **1**, status **INCOMPLETE**, authentic qualification **BLOCKED**.
The scorecards were regenerated at the required JSON and Markdown paths.

| Measure | Result |
| --- | ---: |
| Archived weather tapes / observations | 3 / 3 |
| Weather source-integrity checks | 3 pass |
| Qualified Polymarket / Kalshi tapes | 0 / 0 |
| Exchange prints / maker fills | 0 / 0 |
| Capital deployed / net PnL, cents | 0 / 0 |
| SCMA / FAEP / CFCP, cents | 0 / 0 / 0 |
| Integer-cent conservation | PASS |
| Authentic execution stress | NO_EXECUTION_TAPES |

No verified strike terms, daily station maxima, or exchange execution prints
exist in the weather source. Empty ladders and zero fills are intentional.
Sparse METAR observations cannot certify weather-contract settlement brackets.

The representative test vectors separately exercise stress mechanics. They
are synthetic and are excluded from the production scorecard:

| Assumed case | Filled / posted lots | Deployed cents | Simulated net cents |
| --- | ---: | ---: | ---: |
| Baseline assumed winning payout | 30 / 30 | 1230 | 1770 |
| Two-cent slippage barrier | 3 / 30 | 123 | 177 |
| Twelve-cent spread, eight-cent guard | 0 / 0 | 0 | 0 |
| Queue exhaustion | 0 / 30 | 0 | 0 |
| Adverse zero-payout resolution | 30 / 30 | 1230 | -1230 |

All cases conserve exact cents. Queue exhaustion deliberately uses total future
eligible flow plus one lot as an ex-post adversarial bound, never as a forecast.

## Regression comparison

Executed the requested full command using the existing environment virtualenv:

```sh
cd backend
PYTHONPATH=. pytest --rootdir=. tests/ -v
```

| Checkout | Passed | Failed |
| --- | ---: | ---: |
| Unchanged base in a separate worktree | 700 | 29 |
| WP-8S branch including 14 new tests | 714 | 29 |
| Focused archive/loader/replay tests | 176 | 0 |

The baseline and branch failing-test identifiers are identical: zero additional
regressions. Existing failures include IF-038 rejecting the `source` property,
legacy Sports/CLOB method mismatches, missing deployment/package files, and
operator/portal wiring assertions. The full regression gate is **not green**.
These pre-existing failures are not hidden, skipped, or weakened in this PR.

## Remaining blockers

Public IEM, NOAA NCEI, Polymarket data API, and Kalshi API requests returned
proxy CONNECT 403 under the managed destination policy. GitHub access worked;
the independent Unidata archive supplied the three station observations.

Completion requires public archived settled Polymarket market-specific pages,
historical Kalshi prints and contemporaneous L2, official settlement/rule
evidence (including weather strike terms and climate settlement observations),
and resolution of the base's 29 failing regression tests. Source SHA-256 verifies
bytes, not the truth of an attribution or official contract resolution.
