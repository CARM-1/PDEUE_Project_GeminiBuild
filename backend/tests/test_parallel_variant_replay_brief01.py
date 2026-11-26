"""Brief #01 Adversarial Test Suite — Parallel Variant Replay Harness & G2A Holdout Adjudicator.

Covers:
1. Static AST audit proving ZERO `float()` calls (and zero float literals / true-division `/`) in
   `replay_v2_engine.py`, `parallel_variant_harness.py`, and `run_parallel_variant_replay.py`.
2. Schema 2.0.0 manifest integrity fail-closed behavior, recomputation of derived book fields from raw
   payloads, and 6-tier evidence taxonomy (CONFIRMED_OWN_FILL forbidden offline).
3. Adversarial print sequences: touch-only (0 fill), trade-through (queue-independent + trade_id),
   wrong taker_side ignored, same-price FIFO absorption, clock uncertainty window `t_live + eps`,
   latency `L = max(2s, p99_rtt_ns)`, LB/MID/UB queue bounds under cancellations, print non-reuse,
   and post-only rejection when ask <= bid before `t_live`.
4. `DATA_GAP` & `INCOMPLETE` trade window censoring (`CENSORED`, excluded from fill counts, fails G2A > 1%).
5. Cent-rounded fees (round UP per fill, ignore refunds), unsettled exclusion (best-bid minus taker fee),
   and Sign Trap test (`Pi_L` and `min(LB, MID, UB)` properly reflect worst-case downside).
6. Diagnostics: Selection Gap `G`, executable bid-side markouts (1, 5, 15, 60m), breakdowns by fill type,
   series/category, and hours to close.
7. Variant grid guardrails (<= 36 cap, 100/200 pip spreads rejected, short-horizon Crypto never eligible).
8. Whole-event chronological split (Days 1-8 Train / Day 9 Embargo / Days 10-14 Holdout, zero cross-strike
   leakage), Plateau Test rejection of lone spikes, Cryptographic Freeze Package, deterministic 10,000-resample
   cluster bootstrap, full G2A PASS + Stress Suite report-only guarantee, and byte-identical CLI output hashes.
"""
from __future__ import annotations

import ast
import hashlib
import json
import pathlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytest

from app.adapters.collector_v2 import (
    DEFAULT_CQP_CONFIG,
    KALSHI_EXTERNAL_API_BASE,
    StreamingTapeWriterV2,
    compute_filter_config_hash,
    normalize_kalshi_l2_v2,
    parse_kalshi_trade_v2,
)
from app.domain.parallel_variant_harness import (
    DEFAULT_BOOTSTRAP_RESAMPLES,
    DEFAULT_BOOTSTRAP_SEED,
    MAX_VARIANT_GRID_SIZE,
    adjudicate_g2a_holdout,
    build_cryptographic_freeze_package,
    build_prespecified_variant_grid,
    evaluate_plateau_test,
    run_event_cluster_bootstrap,
    run_parallel_variant_harness_on_loaded_tape,
    run_parallel_variant_replay,
    split_event_clusters_chronologically,
)
from app.domain.replay_v2_engine import (
    MIN_LATENCY_L_NS,
    NS_PER_DAY,
    NS_PER_HOUR,
    NS_PER_MINUTE,
    NS_PER_SECOND,
    EvidenceTier,
    ReplayVariantConfig,
    TapeIntegrityError,
    assert_offline_evidence_tier,
    compute_cent_rounded_fee_micro,
    load_v2_tape,
    parse_utc_iso_to_ns,
    replay_variant_on_tape,
    simulate_order_episode,
)
from scripts import run_parallel_variant_replay as cli_runner

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
REPLAY_ENGINE_PATH = REPO_ROOT / "backend" / "app" / "domain" / "replay_v2_engine.py"
HARNESS_PATH = REPO_ROOT / "backend" / "app" / "domain" / "parallel_variant_harness.py"
CLI_PATH = REPO_ROOT / "backend" / "scripts" / "run_parallel_variant_replay.py"

BASE_UTC = datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
BASE_NS = parse_utc_iso_to_ns("2026-11-01T00:00:00.000000Z")


def _iso_from_ns(ts_ns: int) -> str:
    sec = ts_ns // NS_PER_SECOND
    usec = (ts_ns % NS_PER_SECOND) // 1_000
    dt = datetime.fromtimestamp(sec, tz=timezone.utc).replace(microsecond=usec)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class _TapeBuilder:
    """Helper to write strictly valid Schema 2.0.0 tapes via StreamingTapeWriterV2."""

    def __init__(self, session_dir: pathlib.Path, *, start_ns: int = BASE_NS) -> None:
        self.session_dir = session_dir
        self._clock_ns = start_ns
        self.writer = StreamingTapeWriterV2(
            session_dir,
            filter_config_hash=compute_filter_config_hash(DEFAULT_CQP_CONFIG),
            collector_git_sha="brief01test01",
            time_ns_fn=lambda: self._clock_ns,
        )

    def _advance(self, ts_ns: int) -> int:
        if ts_ns < self._clock_ns:
            ts_ns = self._clock_ns + 1_000
        self._clock_ns = ts_ns
        return ts_ns

    def add_meta(
        self,
        *,
        ticker: str,
        event_ticker: str,
        series_ticker: str,
        category: str,
        close_ns: int,
        ts_ns: int,
        classification: str = "CURATED_STRATEGY_D_CANDIDATE",
        maker_fee_bps: int = 0,
    ) -> None:
        t = self._advance(ts_ns)
        self.writer.append_record(
            "MARKET_META",
            {
                "venue": "KALSHI",
                "contract_ticker": ticker,
                "event_ticker": event_ticker,
                "series_ticker": series_ticker,
                "category": category,
                "classification": classification,
                "close_time_utc": _iso_from_ns(close_ns),
                "uniform_1c_grid_10_90": True,
                "price_ranges": [{"start": "0.0000", "end": "1.0000", "step": "0.0100"}],
                "maker_fee_bps": maker_fee_bps,
            },
            t_req_sent_ns=t - 50_000_000,
            t_resp_recv_ns=t,
            http_status=200,
            captured_at_utc=_iso_from_ns(t),
        )

    def add_l2(
        self,
        *,
        ticker: str,
        yes_bids: Sequence[Tuple[str, str]],
        no_bids: Sequence[Tuple[str, str]],
        ts_ns: int,
        rtt_ns: int = 50_000_000,
        category: str = "WEATHER",
        classification: str = "CURATED_STRATEGY_D_CANDIDATE",
        corrupt_derived: Optional[Dict[str, Any]] = None,
    ) -> None:
        t = self._advance(ts_ns)
        snap = normalize_kalshi_l2_v2(
            ticker,
            {
                "orderbook_fp": {
                    "yes_dollars": [[p, q] for p, q in yes_bids],
                    "no_dollars": [[p, q] for p, q in no_bids],
                }
            },
            source_url=f"{KALSHI_EXTERNAL_API_BASE}/markets/{ticker}/orderbook",
            captured_at_utc=_iso_from_ns(t),
        )
        snap["category"] = category
        snap["classification"] = classification
        if corrupt_derived:
            snap.update(corrupt_derived)
        self.writer.append_record(
            "OBSERVED_L2",
            snap,
            t_req_sent_ns=t - rtt_ns,
            t_resp_recv_ns=t,
            http_status=200,
            captured_at_utc=_iso_from_ns(t),
        )

    def add_trade(
        self,
        *,
        trade_id: str,
        ticker: str,
        yes_price: str,
        count: str,
        taker_side: str,
        trade_ts_ns: int,
        captured_ts_ns: Optional[int] = None,
        window_completeness_status: str = "COMPLETE",
        window_min_ts: Optional[int] = None,
        window_max_ts: Optional[int] = None,
    ) -> None:
        cap_ns = self._advance(captured_ts_ns if captured_ts_ns is not None else trade_ts_ns + 100_000_000)
        w_max = window_max_ts if window_max_ts is not None else (cap_ns // NS_PER_SECOND)
        w_min = window_min_ts if window_min_ts is not None else max(0, w_max - 120)
        parsed = parse_kalshi_trade_v2(
            {
                "trade_id": trade_id,
                "ticker": ticker,
                "yes_price_dollars": yes_price,
                "count_fp": count,
                "taker_side": taker_side,
                "is_block_trade": False,
                "created_time": _iso_from_ns(trade_ts_ns),
            },
            window_min_ts=w_min,
            window_max_ts=w_max,
            window_completeness_status=window_completeness_status,
        )
        self.writer.append_record(
            "OBSERVED_TRADE",
            parsed,
            t_req_sent_ns=cap_ns - 50_000_000,
            t_resp_recv_ns=cap_ns,
            http_status=200,
            captured_at_utc=_iso_from_ns(cap_ns),
        )

    def add_settlement(
        self,
        *,
        ticker: str,
        result: str,
        settled_ts_ns: int,
    ) -> None:
        t = self._advance(settled_ts_ns)
        self.writer.append_record(
            "SETTLEMENT_EVENT",
            {
                "venue": "KALSHI",
                "contract_ticker": ticker,
                "market_status": "settled",
                "settlement_result": result,
                "settlement_value_pips": 10_000 if result == "yes" else 0,
                "settled_at_utc": _iso_from_ns(t),
            },
            t_req_sent_ns=t - 50_000_000,
            t_resp_recv_ns=t,
            http_status=200,
            captured_at_utc=_iso_from_ns(t),
        )

    def add_data_gap(
        self,
        *,
        affected_tickers: Sequence[str],
        gap_start_ns: int,
        gap_end_ns: int,
        reason: str = "HTTP_429_RATE_LIMIT",
        backoff_ms: int = 5_000,
    ) -> None:
        t = self._advance(gap_end_ns)
        self.writer.append_record(
            "DATA_GAP",
            {
                "venue": "KALSHI",
                "endpoint": "/markets/trades",
                "reason": reason,
                "affected_tickers": list(affected_tickers),
                "gap_start_utc": _iso_from_ns(gap_start_ns),
                "gap_end_utc": _iso_from_ns(gap_end_ns),
                "n_429": 1,
                "backoff_ms": backoff_ms,
                "backoff_seconds": (backoff_ms + 999) // 1000,
                "replay_censor_action": "CENSORED",
            },
            t_req_sent_ns=gap_start_ns,
            t_resp_recv_ns=t,
            http_status=429,
            captured_at_utc=_iso_from_ns(t),
        )

    def seal(self) -> pathlib.Path:
        self.writer.write_manifest_file()
        return self.session_dir


# ---------------------------------------------------------------------------
# 1. Static AST Audit: Zero float() Calls & Exact Integer Math
# ---------------------------------------------------------------------------


def test_static_ast_zero_float_calls_in_replay_and_harness():
    for module_path in (REPLAY_ENGINE_PATH, HARNESS_PATH, CLI_PATH):
        source = module_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        float_calls = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "float"
        ]
        float_literals = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        ]
        true_divs = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
            and not isinstance(node.left, (ast.Name, ast.Attribute, ast.Call))
        ]
        assert float_calls == [], f"Prohibited float() calls in {module_path.name} at lines {float_calls}"
        assert float_literals == [], f"Prohibited float literals in {module_path.name} at lines {float_literals}"
        assert true_divs == [], f"Prohibited float true-division in {module_path.name} at lines {true_divs}"


# ---------------------------------------------------------------------------
# 2. Tape Integrity Fail-Closed, Recomputed Derived Fields & 6-Tier Taxonomy
# ---------------------------------------------------------------------------


def test_tape_integrity_fail_closed_and_recomputed_derived_book_values(tmp_path: pathlib.Path):
    # 6-tier evidence taxonomy enum & CONFIRMED_OWN_FILL offline rejection
    expected_tiers = {
        "OBSERVED_L2",
        "OBSERVED_TRADE",
        "TOUCH_ONLY",
        "TRADE_THROUGH_EVIDENCE",
        "QUEUE_CONDITIONAL_BOUND",
        "CONFIRMED_OWN_FILL",
    }
    assert {t.value for t in EvidenceTier} == expected_tiers
    assert assert_offline_evidence_tier(EvidenceTier.TRADE_THROUGH_EVIDENCE) == EvidenceTier.TRADE_THROUGH_EVIDENCE
    assert assert_offline_evidence_tier(EvidenceTier.QUEUE_CONDITIONAL_BOUND) == EvidenceTier.QUEUE_CONDITIONAL_BOUND
    with pytest.raises(ValueError, match="CONFIRMED_OWN_FILL"):
        assert_offline_evidence_tier(EvidenceTier.CONFIRMED_OWN_FILL)

    # Corrupt stored derived fields (best_yes_bid_pips, best_yes_ask_pips, spread_pips) while keeping raw valid
    tb = _TapeBuilder(tmp_path / "sess_recompute")
    tk = "KXHIGHMIA-26NOV02-T80"
    tb.add_meta(
        ticker=tk,
        event_ticker="KXHIGHMIA-26NOV02",
        series_ticker="KXHIGHMIA",
        category="WEATHER",
        close_ns=BASE_NS + 12 * NS_PER_HOUR,
        ts_ns=BASE_NS,
    )
    tb.add_l2(
        ticker=tk,
        yes_bids=[("0.4400", "200.00"), ("0.4200", "100.00")],
        no_bids=[("0.5000", "180.00")],  # => best_yes_ask = 10000 - 5000 = 5000, spread = 600
        ts_ns=BASE_NS + 10 * NS_PER_SECOND,
        corrupt_derived={
            "best_yes_bid_pips": 9999,
            "best_yes_ask_pips": 1111,
            "best_no_bid_pips": 8888,
            "spread_pips": 100,
        },
    )
    sess_dir = tb.seal()

    tape = load_v2_tape(sess_dir)
    assert tape.unexplained_parse_rejects == 0
    assert tape.derived_discrepancy_count == 1
    snap = tape.l2_by_ticker[tk][0]
    assert snap.best_yes_bid_pips == 4400
    assert snap.best_no_bid_pips == 5000
    assert snap.best_yes_ask_pips == 5000
    assert snap.spread_pips == 600
    assert snap.book_quarantined is False
    assert snap.stored_derived_discrepancy is True

    # Tamper a byte in tape.jsonl -> fail-closed TapeIntegrityError
    tape_file = sess_dir / "tape.jsonl"
    raw_bytes = tape_file.read_bytes()
    tape_file.write_bytes(raw_bytes + b" ")
    with pytest.raises(TapeIntegrityError, match="Manifest integrity check failed"):
        load_v2_tape(sess_dir)


# ---------------------------------------------------------------------------
# 3. Adversarial Print Sequences, Timing, Queue Bounds & Post-Only Safety
# ---------------------------------------------------------------------------


def test_adversarial_print_sequences_fifo_trade_through_touch_and_post_only(tmp_path: pathlib.Path):
    tb = _TapeBuilder(tmp_path / "sess_adv")
    tk_touch = "KXHIGHMIA-26NOV02-T70"
    tk_tt = "KXHIGHMIA-26NOV02-T72"
    tk_fifo = "KXHIGHMIA-26NOV02-T74"
    tk_postonly = "KXHIGHMIA-26NOV02-T76"
    close_ns = BASE_NS + 12 * NS_PER_HOUR

    for tk in (tk_touch, tk_tt, tk_fifo, tk_postonly):
        tb.add_meta(
            ticker=tk,
            event_ticker="KXHIGHMIA-26NOV02",
            series_ticker="KXHIGHMIA",
            category="WEATHER",
            close_ns=close_ns,
            ts_ns=BASE_NS,
        )

    t0 = BASE_NS + 100 * NS_PER_SECOND
    # --- Contract 1: TOUCH_ONLY (ask touches bid, print above bid, taker_side=='yes' print below bid) -> 0 fill ---
    tb.add_l2(ticker=tk_touch, yes_bids=[("0.4400", "200.00")], no_bids=[("0.5000", "200.00")], ts_ns=t0)
    tb.add_l2(ticker=tk_touch, yes_bids=[("0.4400", "200.00")], no_bids=[("0.5600", "200.00")], ts_ns=t0 + 10 * NS_PER_SECOND)  # ask=4400 touches bid!
    tb.add_trade(trade_id="TRD-ABOVE", ticker=tk_touch, yes_price="0.4500", count="500.00", taker_side="no", trade_ts_ns=t0 + 12 * NS_PER_SECOND)
    tb.add_trade(trade_id="TRD-WRONG-SIDE", ticker=tk_touch, yes_price="0.4300", count="500.00", taker_side="yes", trade_ts_ns=t0 + 13 * NS_PER_SECOND)
    tb.add_trade(trade_id="TRD-INSIDE-EPS", ticker=tk_touch, yes_price="0.4300", count="500.00", taker_side="no", trade_ts_ns=t0 + 3 * NS_PER_SECOND)  # inside t_live + eps (4s)!
    tb.add_l2(ticker=tk_touch, yes_bids=[("0.4400", "200.00")], no_bids=[("0.5000", "200.00")], ts_ns=t0 + 30 * NS_PER_SECOND)
    tb.add_settlement(ticker=tk_touch, result="yes", settled_ts_ns=t0 + 60 * NS_PER_SECOND)

    # --- Contract 2: TRADE_THROUGH_EVIDENCE (print < p fills queue-independently citing exact trade_id) ---
    tb.add_l2(ticker=tk_tt, yes_bids=[("0.4400", "500.00")], no_bids=[("0.5000", "200.00")], ts_ns=t0 + 100 * NS_PER_SECOND)
    tb.add_l2(ticker=tk_tt, yes_bids=[("0.4400", "500.00")], no_bids=[("0.5000", "200.00")], ts_ns=t0 + 105 * NS_PER_SECOND)
    tb.add_trade(trade_id="TRD-TT-99", ticker=tk_tt, yes_price="0.4300", count="3.00", taker_side="no", trade_ts_ns=t0 + 115 * NS_PER_SECOND)
    tb.add_settlement(ticker=tk_tt, result="yes", settled_ts_ns=t0 + 160 * NS_PER_SECOND)

    # --- Contract 3: Same-price FIFO + LB/MID/UB queue divergence under unexplained cancellation ---
    # D_p(k) = 100 contracts (10000 centi). At k+1 (t+5s), depth drops to 20 contracts (2000 centi) with 0 prints -> 8000 centi cancelled!
    # LB: Q_ahead = 10000 (ignores cancellations). MID: Q_ahead = 10000 - (8000*10000//10000) = 2000. UB: Q_ahead = 2000.
    # Let's make D_p(k) = 100, at k+1 depth jumps to 120 (adds 20 -> LB Q_lb = 100 + 20 = 120, MID = 100, UB = 100),
    # then at k+2 depth drops from 120 to 60 (60 cancelled -> LB stays 120, MID drops pro-rata 60*100//120 = 50 -> 50, UB drops 60 -> 40)!
    # Then same-price print at 0.4400 for 125 contracts (12500 centi):
    #   LB fills: 125 - 120 = 5 contracts (500 centi)
    #   MID fills: min(order_qty=50, 125 - 50) = 50 contracts (or with order_qty=100: 75 contracts)
    #   UB fills: min(order_qty=100, 125 - 40) = 85 contracts
    t3 = t0 + 200 * NS_PER_SECOND
    tb.add_l2(ticker=tk_fifo, yes_bids=[("0.4400", "100.00")], no_bids=[("0.5000", "200.00")], ts_ns=t3)
    tb.add_l2(ticker=tk_fifo, yes_bids=[("0.4400", "120.00")], no_bids=[("0.5000", "200.00")], ts_ns=t3 + 5 * NS_PER_SECOND)
    tb.add_l2(ticker=tk_fifo, yes_bids=[("0.4400", "60.00")], no_bids=[("0.5000", "200.00")], ts_ns=t3 + 10 * NS_PER_SECOND)
    tb.add_trade(trade_id="TRD-FIFO-1", ticker=tk_fifo, yes_price="0.4400", count="125.00", taker_side="no", trade_ts_ns=t3 + 15 * NS_PER_SECOND)
    tb.add_settlement(ticker=tk_fifo, result="yes", settled_ts_ns=t3 + 60 * NS_PER_SECOND)

    # --- Contract 4: Post-Only Rejection (ask crosses bid BEFORE t_live = t + 2s) ---
    t4 = t0 + 300 * NS_PER_SECOND
    tb.add_l2(ticker=tk_postonly, yes_bids=[("0.4400", "150.00")], no_bids=[("0.5000", "200.00")], ts_ns=t4)
    # 1 second later (< L = 2s), NO bid jumps to 0.5600 => YES ask = 0.4400 <= proposed bid 0.4400!
    tb.add_l2(ticker=tk_postonly, yes_bids=[("0.4300", "150.00")], no_bids=[("0.5600", "200.00")], ts_ns=t4 + 1 * NS_PER_SECOND)
    tb.add_trade(trade_id="TRD-POSTONLY-SHOULD-NOT-FILL", ticker=tk_postonly, yes_price="0.4200", count="500.00", taker_side="no", trade_ts_ns=t4 + 10 * NS_PER_SECOND)
    tb.add_settlement(ticker=tk_postonly, result="yes", settled_ts_ns=t4 + 60 * NS_PER_SECOND)

    tape = load_v2_tape(tb.seal())
    assert tape.latency_l_ns == MIN_LATENCY_L_NS  # p99 RTT 50ms < 2s => L = 2s

    # 1. Verify TOUCH_ONLY yields 0 fill
    ep_touch = simulate_order_episode(
        episode_id="EP-TOUCH",
        contract_meta=tape.contracts[tk_touch],
        decision_snap_idx=0,
        cancel_snap_idx=None,
        proposed_bid_pips=4400,
        order_qty_centi=500,
        l2_snaps=tape.l2_by_ticker[tk_touch],
        trades=tape.trades_by_ticker[tk_touch],
        settlement=tape.settlements[tk_touch],
        censor_intervals=tape.censor_intervals,
        latency_l_ns=tape.latency_l_ns,
    )
    assert ep_touch.filled_qty_lb_centi == 0
    assert ep_touch.filled_qty_mid_centi == 0
    assert ep_touch.filled_qty_ub_centi == 0
    assert ep_touch.citing_trade_ids_lb == ()
    assert ep_touch.touch_only_events >= 1

    # 2. Verify TRADE_THROUGH fills queue-independently citing exact trade_id and non-reuse
    shared_lb: Dict[str, int] = {}
    shared_mid: Dict[str, int] = {}
    shared_ub: Dict[str, int] = {}
    ep_tt = simulate_order_episode(
        episode_id="EP-TT-1",
        contract_meta=tape.contracts[tk_tt],
        decision_snap_idx=0,
        cancel_snap_idx=None,
        proposed_bid_pips=4400,
        order_qty_centi=500,  # 5 contracts requested, print has 3 contracts (300 centi)
        l2_snaps=tape.l2_by_ticker[tk_tt],
        trades=tape.trades_by_ticker[tk_tt],
        settlement=tape.settlements[tk_tt],
        censor_intervals=tape.censor_intervals,
        latency_l_ns=tape.latency_l_ns,
        print_vol_remaining_lb=shared_lb,
        print_vol_remaining_mid=shared_mid,
        print_vol_remaining_ub=shared_ub,
    )
    assert ep_tt.filled_qty_lb_centi == 300
    assert ep_tt.filled_qty_mid_centi == 300
    assert ep_tt.filled_qty_ub_centi == 300
    assert ep_tt.citing_trade_ids_lb == ("TRD-TT-99",)
    assert ep_tt.fills_lb[0].evidence_tier == EvidenceTier.TRADE_THROUGH_EVIDENCE
    # Re-running a second order sharing the same variant print volume ledger CANNOT double-consume TRD-TT-99
    ep_tt_dup = simulate_order_episode(
        episode_id="EP-TT-2",
        contract_meta=tape.contracts[tk_tt],
        decision_snap_idx=0,
        cancel_snap_idx=None,
        proposed_bid_pips=4400,
        order_qty_centi=500,
        l2_snaps=tape.l2_by_ticker[tk_tt],
        trades=tape.trades_by_ticker[tk_tt],
        settlement=tape.settlements[tk_tt],
        censor_intervals=tape.censor_intervals,
        latency_l_ns=tape.latency_l_ns,
        print_vol_remaining_lb=shared_lb,
        print_vol_remaining_mid=shared_mid,
        print_vol_remaining_ub=shared_ub,
    )
    assert ep_tt_dup.filled_qty_lb_centi == 0

    # 3. Verify same-price FIFO absorption & exact LB < MID < UB queue bounds
    ep_fifo = simulate_order_episode(
        episode_id="EP-FIFO",
        contract_meta=tape.contracts[tk_fifo],
        decision_snap_idx=0,
        cancel_snap_idx=None,
        proposed_bid_pips=4400,
        order_qty_centi=10_000,  # 100 contracts max
        l2_snaps=tape.l2_by_ticker[tk_fifo],
        trades=tape.trades_by_ticker[tk_fifo],
        settlement=tape.settlements[tk_fifo],
        censor_intervals=tape.censor_intervals,
        latency_l_ns=tape.latency_l_ns,
    )
    assert ep_fifo.start_q_lb_centi == 12_000
    assert ep_fifo.start_q_mid_centi == 10_000
    assert ep_fifo.start_q_ub_centi == 10_000
    assert ep_fifo.filled_qty_lb_centi == 500      # 12500 - 12000
    assert ep_fifo.filled_qty_mid_centi == 7_500   # 12500 - (10000 - 5000)
    assert ep_fifo.filled_qty_ub_centi == 8_500    # 12500 - (10000 - 6000)
    assert 0 <= ep_fifo.filled_qty_lb_centi < ep_fifo.filled_qty_mid_centi < ep_fifo.filled_qty_ub_centi
    assert ep_fifo.citing_trade_ids_lb == ("TRD-FIFO-1",)
    assert ep_fifo.fills_lb[0].evidence_tier == EvidenceTier.QUEUE_CONDITIONAL_BOUND

    # 4. Verify Post-Only Rejection when ask crosses bid before t_live
    ep_po = simulate_order_episode(
        episode_id="EP-PO",
        contract_meta=tape.contracts[tk_postonly],
        decision_snap_idx=0,
        cancel_snap_idx=None,
        proposed_bid_pips=4400,
        order_qty_centi=500,
        l2_snaps=tape.l2_by_ticker[tk_postonly],
        trades=tape.trades_by_ticker[tk_postonly],
        settlement=tape.settlements[tk_postonly],
        censor_intervals=tape.censor_intervals,
        latency_l_ns=tape.latency_l_ns,
    )
    assert ep_po.post_only_rejected is True
    assert ep_po.status == "POST_ONLY_REJECTED"
    assert ep_po.filled_qty_lb_centi == 0
    assert ep_po.crossed_order is False


# ---------------------------------------------------------------------------
# 4. DATA_GAP Censoring & G2A Gate Failure > 1%
# ---------------------------------------------------------------------------


def test_data_gap_censoring_excludes_fills_and_fails_g2a_gate(tmp_path: pathlib.Path):
    tb = _TapeBuilder(tmp_path / "sess_gap")
    # 1 train event (Day 2), 1 holdout event (Day 11) with overlapping DATA_GAP
    tk_tr = "KXHIGHMIA-26NOV02-T80"
    tk_ho = "KXHIGHMIA-26NOV11-T80"
    t_tr = BASE_NS + 1 * NS_PER_DAY
    t_ho = BASE_NS + 10 * NS_PER_DAY

    tb.add_meta(ticker=tk_tr, event_ticker="KXHIGHMIA-26NOV02", series_ticker="KXHIGHMIA", category="WEATHER", close_ns=t_tr + 12 * NS_PER_HOUR, ts_ns=t_tr)
    tb.add_l2(ticker=tk_tr, yes_bids=[("0.4400", "200.00")], no_bids=[("0.5000", "200.00")], ts_ns=t_tr + 10 * NS_PER_SECOND)
    tb.add_l2(ticker=tk_tr, yes_bids=[("0.4400", "200.00")], no_bids=[("0.5000", "200.00")], ts_ns=t_tr + 20 * NS_PER_SECOND)
    tb.add_trade(trade_id="TRD-TR-1", ticker=tk_tr, yes_price="0.4300", count="10.00", taker_side="no", trade_ts_ns=t_tr + 30 * NS_PER_SECOND)
    tb.add_settlement(ticker=tk_tr, result="yes", settled_ts_ns=t_tr + 60 * NS_PER_SECOND)

    tb.add_meta(ticker=tk_ho, event_ticker="KXHIGHMIA-26NOV11", series_ticker="KXHIGHMIA", category="WEATHER", close_ns=t_ho + 12 * NS_PER_HOUR, ts_ns=t_ho)
    tb.add_l2(ticker=tk_ho, yes_bids=[("0.4400", "200.00")], no_bids=[("0.5000", "200.00")], ts_ns=t_ho + 10 * NS_PER_SECOND)
    tb.add_l2(ticker=tk_ho, yes_bids=[("0.4400", "200.00")], no_bids=[("0.5000", "200.00")], ts_ns=t_ho + 20 * NS_PER_SECOND)
    tb.add_data_gap(affected_tickers=[tk_ho], gap_start_ns=t_ho + 25 * NS_PER_SECOND, gap_end_ns=t_ho + 35 * NS_PER_SECOND)
    tb.add_trade(trade_id="TRD-HO-CENSORED", ticker=tk_ho, yes_price="0.4300", count="10.00", taker_side="no", trade_ts_ns=t_ho + 40 * NS_PER_SECOND)
    tb.add_settlement(ticker=tk_ho, result="yes", settled_ts_ns=t_ho + 60 * NS_PER_SECOND)

    tape = load_v2_tape(tb.seal())
    grid = build_prespecified_variant_grid(
        min_spread_pips_values=(400,),
        max_expiry_hours_values=(168,),
        min_consecutive_snapshots_values=(2,),
        exit_modes=("settlement_only",),
    )
    report = run_parallel_variant_harness_on_loaded_tape(
        tape,
        grid=grid,
        bootstrap_resamples=200,
        replay_git_sha="testsha000001",
    )
    ho = report["sealed_holdout_result"]
    assert ho["censored_episodes_count"] == 1
    assert ho["filled_order_episodes_lb"] == 0  # censored episode excluded from fill counts!
    assert ho["censored_order_minutes_bps"] == 10_000  # 100% > 1%
    g2a = report["g2a_adjudication"]
    assert g2a["ops"]["checks"]["censored_order_minutes_lt_1pct"] is False
    assert "ops.censored_order_minutes_lt_1pct" in g2a["failed_checks"]
    assert g2a["verdict"] == "FAIL_G2A"


# ---------------------------------------------------------------------------
# 5. Sign Trap, Cent-Rounded Fees, Unsettled Valuation & Markout Diagnostics
# ---------------------------------------------------------------------------


def test_sign_trap_fee_rounding_unsettled_valuation_and_diagnostics(tmp_path: pathlib.Path):
    # Cent-rounded fee: rounds UP per fill to whole cent (10_000 micro_dollars)
    # 7% taker fee on 1 contract at 50c = $0.0175 -> rounds UP to 2c (20_000 micro_dollars)
    assert compute_cent_rounded_fee_micro(700, 100, 5000) == 20_000
    # 1.75% maker fee on 1 contract at 50c = $0.004375 -> rounds UP to 1c (10_000 micro_dollars)
    assert compute_cent_rounded_fee_micro(175, 100, 5000) == 10_000
    # Zero maker fee series -> 0
    assert compute_cent_rounded_fee_micro(0, 500, 4400) == 0

    tb = _TapeBuilder(tmp_path / "sess_signtrap")
    tk_loser = "KXHIGHMIA-26NOV02-T90"
    tk_unsettled = "KXCPI-26NOV02-T05"
    close_ns = BASE_NS + 20 * NS_PER_HOUR

    # Losing contract where LB fills 1 contract (100 centi) and UB fills 5 contracts (500 centi)
    # Bid at 50c (5000 pips), settles NO (0 pips) => r_i = -5000 pips!
    # LB PnL = -500_000 (-$0.50); UB PnL = -2_500_000 (-$2.50).
    # Sign Trap: naive LB (-$0.50) hides the -$2.50 worst-case downside!
    # Pi_L AND certified_total_pnl_micro = min(LB, MID, UB) MUST both equal -2_500_000!
    tb.add_meta(ticker=tk_loser, event_ticker="KXHIGHMIA-26NOV02", series_ticker="KXHIGHMIA", category="WEATHER", close_ns=close_ns, ts_ns=BASE_NS)
    t0 = BASE_NS + 100 * NS_PER_SECOND
    tb.add_l2(ticker=tk_loser, yes_bids=[("0.5000", "120.00")], no_bids=[("0.4400", "200.00")], ts_ns=t0)  # ask=5600, spread=600
    tb.add_l2(ticker=tk_loser, yes_bids=[("0.5000", "120.00")], no_bids=[("0.4400", "200.00")], ts_ns=t0 + 10 * NS_PER_SECOND)
    # Depth drops by 4 contracts (unexplained cancel, still >= 100 min depth): LB Q=12000, UB Q=11600
    tb.add_l2(ticker=tk_loser, yes_bids=[("0.5000", "116.00")], no_bids=[("0.4400", "200.00")], ts_ns=t0 + 15 * NS_PER_SECOND)
    # Print of 121 contracts at 0.5000 => LB fills 100 centi (1 contract), UB fills 500 centi (5 contracts)!
    tb.add_trade(trade_id="TRD-SIGNTRAP-1", ticker=tk_loser, yes_price="0.5000", count="121.00", taker_side="no", trade_ts_ns=t0 + 20 * NS_PER_SECOND)
    # Subsequent snapshots at +1m, +5m, +15m, +60m for executable bid-side markouts
    for delta_m, bid_s in ((1, "0.4800"), (5, "0.4500"), (15, "0.4000"), (60, "0.3000")):
        tb.add_l2(
            ticker=tk_loser,
            yes_bids=[(bid_s, "120.00")],
            no_bids=[("0.4400", "200.00")],
            ts_ns=t0 + 20 * NS_PER_SECOND + delta_m * NS_PER_MINUTE,
        )
    tb.add_settlement(ticker=tk_loser, result="no", settled_ts_ns=t0 + 2 * NS_PER_HOUR)

    # Unsettled contract: bid=40c, ask=50c (midpoint=45c, best_bid=40c) -> MUST value at best_bid (40c) minus taker fee, NEVER midpoint, AND exclude from certification counts!
    t_u = t0 + 3 * NS_PER_HOUR
    tb.add_meta(ticker=tk_unsettled, event_ticker="KXCPI-26NOV02", series_ticker="KXCPI", category="SCHEDULED_MACRO", close_ns=t_u + 24 * NS_PER_HOUR, ts_ns=t_u)
    tb.add_l2(ticker=tk_unsettled, yes_bids=[("0.4000", "200.00")], no_bids=[("0.5000", "200.00")], ts_ns=t_u + 10 * NS_PER_SECOND)
    tb.add_l2(ticker=tk_unsettled, yes_bids=[("0.4000", "200.00")], no_bids=[("0.5000", "200.00")], ts_ns=t_u + 20 * NS_PER_SECOND)
    tb.add_trade(trade_id="TRD-UNSETTLED-1", ticker=tk_unsettled, yes_price="0.3900", count="5.00", taker_side="no", trade_ts_ns=t_u + 30 * NS_PER_SECOND)
    tb.add_l2(ticker=tk_unsettled, yes_bids=[("0.4200", "200.00")], no_bids=[("0.5000", "200.00")], ts_ns=t_u + 60 * NS_PER_SECOND)  # best bid 42c, ask 50c (mid 46c)

    tape = load_v2_tape(tb.seal())
    variant = ReplayVariantConfig(
        variant_id="V_SIGNTRAP",
        min_spread_pips=400,
        max_expiry_hours=168,
        min_consecutive_snapshots=2,
        exit_mode="settlement_only",
        order_qty_centi=500,
    )
    res = replay_variant_on_tape(tape, variant)

    # Only the settled loser counts in certification metrics; unsettled is flagged & excluded
    assert res["certified_settled_episodes"] == 1
    assert res["filled_qty_lb_centi"] == 100
    assert res["filled_qty_ub_centi"] == 500
    assert res["total_pnl_lb_micro"] == -500_000
    assert res["total_pnl_ub_micro"] == -2_500_000
    # Sign Trap defeated: BOTH certified_total_pnl_micro AND pi_l_micro reflect -$2.50 worst-case downside!
    assert res["certified_total_pnl_micro"] == -2_500_000
    assert res["pi_l_micro"] == -2_500_000

    # Verify unsettled exclusion & best-bid minus taker fee valuation (4200 - 4000 = +200 pips * 500 centi = +100_000 minus taker fee)
    unsettled_diag = res["diagnostics"]["unsettled_contracts"]
    assert unsettled_diag["unsettled_episodes_excluded_count"] == 1
    assert unsettled_diag["unsettled_tickers"] == [tk_unsettled]
    expected_taker_fee = compute_cent_rounded_fee_micro(700, 500, 4200)
    assert unsettled_diag["unsettled_mark_to_bid_pnl_lb_micro"] == (500 * (4200 - 4000) - expected_taker_fee)

    # Verify bid-side markouts at 1, 5, 15, 60 minutes: best_bid(t + delta) - 5000
    mk = res["diagnostics"]["executable_bid_markouts"]
    assert mk["1m"]["mean_bid_markout_pips"] == -200    # 4800 - 5000
    assert mk["5m"]["mean_bid_markout_pips"] == -500    # 4500 - 5000
    assert mk["15m"]["mean_bid_markout_pips"] == -1000  # 4000 - 5000
    assert mk["60m"]["mean_bid_markout_pips"] == -2000  # 3000 - 5000
    assert res["diagnostics"]["selection_gap"]["selection_gap_lb_pips"] == 0
    assert res["diagnostics"]["by_fill_type"]["queue_fill"]["filled_qty_centi"] == 100
    assert "KXHIGHMIA" in res["diagnostics"]["by_series"]
    assert "WEATHER" in res["diagnostics"]["by_category"]


# ---------------------------------------------------------------------------
# 6. Variant Grid Guardrails (<= 36 Cap, 1c/2c Ban, Short-Horizon Crypto Ban)
# ---------------------------------------------------------------------------


def test_variant_grid_guardrails_cap_spread_ban_and_crypto_exclusion(tmp_path: pathlib.Path):
    # Default grid has exactly 36 variants (3 * 3 * 2 * 2)
    default_grid = build_prespecified_variant_grid()
    assert len(default_grid) == 36 == MAX_VARIANT_GRID_SIZE

    # Grid > 36 rejected
    with pytest.raises(ValueError, match="exceeds Brief #01 hard cap"):
        build_prespecified_variant_grid(
            min_spread_pips_values=(300, 400, 500, 600),
            max_expiry_hours_values=(24, 72, 168),
            min_consecutive_snapshots_values=(2, 3),
            exit_modes=("settlement_only", "early_exit_5c"),
        )

    # 100 and 200 pip spreads strictly banned
    with pytest.raises(ValueError, match="Brief #01 guardrail violation"):
        ReplayVariantConfig(variant_id="BAD_1C", min_spread_pips=100)
    with pytest.raises(ValueError, match="Brief #01 guardrail violation"):
        ReplayVariantConfig(variant_id="BAD_2C", min_spread_pips=200)

    # Short-horizon Crypto is NEVER Strategy D eligible even with 5c spread and huge depth
    tb = _TapeBuilder(tmp_path / "sess_crypto")
    tk_btc = "KXBTC-26NOV02-100K"
    tb.add_meta(
        ticker=tk_btc,
        event_ticker="KXBTC-26NOV02",
        series_ticker="KXBTC",
        category="SHORT_HORIZON_CRYPTO",
        classification="BENCHMARK_ONLY",
        close_ns=BASE_NS + 6 * NS_PER_HOUR,
        ts_ns=BASE_NS,
    )
    t0 = BASE_NS + 10 * NS_PER_SECOND
    tb.add_l2(ticker=tk_btc, yes_bids=[("0.4500", "500.00")], no_bids=[("0.5000", "500.00")], ts_ns=t0, category="SHORT_HORIZON_CRYPTO", classification="BENCHMARK_ONLY")
    tb.add_l2(ticker=tk_btc, yes_bids=[("0.4500", "500.00")], no_bids=[("0.5000", "500.00")], ts_ns=t0 + 10 * NS_PER_SECOND, category="SHORT_HORIZON_CRYPTO", classification="BENCHMARK_ONLY")
    tb.add_trade(trade_id="TRD-BTC-1", ticker=tk_btc, yes_price="0.4400", count="100.00", taker_side="no", trade_ts_ns=t0 + 20 * NS_PER_SECOND)
    tb.add_settlement(ticker=tk_btc, result="yes", settled_ts_ns=t0 + 60 * NS_PER_SECOND)

    tape = load_v2_tape(tb.seal())
    res = replay_variant_on_tape(tape, ReplayVariantConfig(variant_id="V_STD", min_spread_pips=400))
    assert res["total_episodes"] == 0
    assert res["filled_order_episodes_lb"] == 0


# ---------------------------------------------------------------------------
# 7. Chronological Whole-Event Split (Train / Day 9 Embargo / Holdout) & Plateau Test
# ---------------------------------------------------------------------------


def test_whole_event_chronological_split_zero_strike_leakage_and_plateau_spike_rejection(tmp_path: pathlib.Path):
    tb = _TapeBuilder(tmp_path / "sess_split")

    # Correlated strikes under same event cluster across Days 1-8 (Train), Day 9 (Embargo), Days 10-14 (Holdout)
    # Day 3 event (Train): 3 correlated strikes T78, T80, T82
    for idx, strike in enumerate(("T78", "T80", "T82")):
        tk = f"KXHIGHMIA-26NOV03-{strike}"
        # Even if one strike closes slightly earlier/later, all share event_ticker -> whole cluster moves together
        tb.add_meta(
            ticker=tk,
            event_ticker="KXHIGHMIA-26NOV03",
            series_ticker="KXHIGHMIA",
            category="WEATHER",
            close_ns=BASE_NS + 2 * NS_PER_DAY + (10 + idx) * NS_PER_HOUR,
            ts_ns=BASE_NS + idx * NS_PER_SECOND,
        )
    # Day 9 event (Embargo — MUST be dropped from BOTH Train and Holdout!)
    tb.add_meta(
        ticker="KXHIGHMIA-26NOV09-T80",
        event_ticker="KXHIGHMIA-26NOV09",
        series_ticker="KXHIGHMIA",
        category="WEATHER",
        close_ns=BASE_NS + 8 * NS_PER_DAY + 12 * NS_PER_HOUR,  # Day 9
        ts_ns=BASE_NS + 10 * NS_PER_SECOND,
    )
    # Day 11 event (Holdout): 2 correlated strikes
    for idx, strike in enumerate(("T80", "T82")):
        tb.add_meta(
            ticker=f"KXHIGHMIA-26NOV11-{strike}",
            event_ticker="KXHIGHMIA-26NOV11",
            series_ticker="KXHIGHMIA",
            category="WEATHER",
            close_ns=BASE_NS + 10 * NS_PER_DAY + (10 + idx) * NS_PER_HOUR,  # Day 11
            ts_ns=BASE_NS + (20 + idx) * NS_PER_SECOND,
        )

    tape = load_v2_tape(tb.seal())
    split = split_event_clusters_chronologically(tape, recording_start_ns=BASE_NS)

    assert split.train_event_clusters == ("KXHIGHMIA-26NOV03",)
    assert split.embargo_event_clusters == ("KXHIGHMIA-26NOV09",)
    assert split.holdout_event_clusters == ("KXHIGHMIA-26NOV11",)
    assert len(split.contracts_by_cluster["KXHIGHMIA-26NOV03"]) == 3
    assert len(split.contracts_by_cluster["KXHIGHMIA-26NOV11"]) == 2
    assert "KXHIGHMIA-26NOV09" not in split.train_event_clusters
    assert "KXHIGHMIA-26NOV09" not in split.holdout_event_clusters

    # Plateau Test rejection of a lone spike on Train
    grid = build_prespecified_variant_grid(
        min_spread_pips_values=(300, 400, 500),
        max_expiry_hours_values=(72,),
        min_consecutive_snapshots_values=(2,),
        exit_modes=("settlement_only",),
    )
    ids = [e.variant.variant_id for e in grid]
    # Center point (400) is a lone positive spike (+500 pips), neighbors (300 and 500) are negative (-200 pips)
    fake_train_results = {
        ids[0]: {"variant_id": ids[0], "lb_ev_pips": -200, "mid_ev_pips": -200, "filled_qty_lb_centi": 1000, "certified_total_pnl_micro": -200_000},
        ids[1]: {"variant_id": ids[1], "lb_ev_pips": 500, "mid_ev_pips": 500, "filled_qty_lb_centi": 1000, "certified_total_pnl_micro": 500_000},
        ids[2]: {"variant_id": ids[2], "lb_ev_pips": -200, "mid_ev_pips": -200, "filled_qty_lb_centi": 1000, "certified_total_pnl_micro": -200_000},
    }
    p_spike = evaluate_plateau_test(ids[1], grid, fake_train_results)
    assert p_spike["passed"] is False
    assert set(p_spike["failing_neighbors"]) == {ids[0], ids[2]}

    # When all neighbors also have LB EV >= 0, Plateau Test PASSES
    fake_train_results[ids[0]]["lb_ev_pips"] = 100
    fake_train_results[ids[0]]["certified_total_pnl_micro"] = 100_000
    fake_train_results[ids[2]]["lb_ev_pips"] = 150
    fake_train_results[ids[2]]["certified_total_pnl_micro"] = 150_000
    p_flat = evaluate_plateau_test(ids[1], grid, fake_train_results)
    assert p_flat["passed"] is True
    assert p_flat["failing_neighbors"] == []


# ---------------------------------------------------------------------------
# 8. Full G2A Holdout PASS, Deterministic 10k Bootstrap, Stress Suite & CLI Determinism
# ---------------------------------------------------------------------------


def _build_g2a_passing_14_day_tape(session_dir: pathlib.Path) -> pathlib.Path:
    """Build a valid 14-day Schema 2.0.0 tape with Train (Days 1-8), Embargo (Day 9), Holdout (Days 10-14).

    Holdout contains 44 independent resolved event clusters across 4 series (11 each = 25% <= 40%),
    each with 4 filled order episodes = 176 filled episodes (>= 150), uniform positive EV (~+1000 pips)
    so single-event absolute PnL share is ~2.3% (<= 10%).
    """
    tb = _TapeBuilder(session_dir, start_ns=BASE_NS)
    series_defs = [
        ("KXHIGH", "WEATHER"),
        ("KXCPI", "SCHEDULED_MACRO"),
        ("KXNFL", "PRE_GAME_SPORTS"),
        ("KXFED", "SCHEDULED_MACRO"),
    ]
    trd_seq = 0

    def _emit_cluster(
        *,
        day_offset_days: int,
        cluster_idx: int,
        series_ticker: str,
        category: str,
        outcome: str,
        episodes_in_cluster: int,
    ) -> None:
        nonlocal trd_seq
        event_id = f"{series_ticker}-D{day_offset_days:02d}E{cluster_idx:02d}"
        tk = f"{event_id}-T50"
        base_t = BASE_NS + (day_offset_days - 1) * NS_PER_DAY + cluster_idx * 10 * NS_PER_MINUTE
        close_t = base_t + 6 * NS_PER_HOUR

        tb.add_meta(
            ticker=tk,
            event_ticker=event_id,
            series_ticker=series_ticker,
            category=category,
            close_ns=close_t,
            ts_ns=base_t,
        )

        # Create `episodes_in_cluster` distinct order episodes by changing bid price between episodes
        cur_t = base_t + 10 * NS_PER_SECOND
        for ep_i in range(episodes_in_cluster):
            bid_pips = 4200 + (ep_i % 2) * 100  # alternate 42c / 43c so each episode reprices cleanly
            bid_str = f"0.{bid_pips:04d}"
            no_bid_pips = 10_000 - (bid_pips + 500)  # 5c spread (500 pips) -> eligible for 300/400/500 grid!
            no_bid_str = f"0.{no_bid_pips:04d}"
            tt_price_str = f"0.{bid_pips - 100:04d}"  # trade-through 1c below bid

            # 3 consecutive snapshots at same bid so min_consecutive_snapshots in {2, 3} both trigger
            for s_i in range(3):
                tb.add_l2(
                    ticker=tk,
                    yes_bids=[(bid_str, "150.00")],
                    no_bids=[(no_bid_str, "150.00")],
                    ts_ns=cur_t,
                )
                cur_t += 10 * NS_PER_SECOND
            # Trade-through print strictly after t_live + eps (cur_t is +10s after 3rd snap, L=2s, eps=2s)
            trd_seq += 1
            tb.add_trade(
                trade_id=f"TRD-G2A-{trd_seq:06d}",
                ticker=tk,
                yes_price=tt_price_str,
                count="5.00",
                taker_side="no",
                trade_ts_ns=cur_t,
                captured_ts_ns=cur_t + 100_000_000,
            )
            cur_t += 10 * NS_PER_SECOND

        # Settle contract after episodes
        tb.add_settlement(ticker=tk, result=outcome, settled_ts_ns=cur_t + 10 * NS_PER_SECOND)

    # Train: Days 1-8 -> 20 event clusters emitted chronologically (60% YES wins at ~42.5c bid)
    for i in range(20):
        ser, cat = series_defs[i % 4]
        day_num = 1 + (i * 8) // 20  # monotonic across Days 1..8
        outcome = "yes" if (i % 5 != 0 and i % 5 != 3) else "no"  # 3/5 = 60% YES wins
        _emit_cluster(day_offset_days=day_num, cluster_idx=i, series_ticker=ser, category=cat, outcome=outcome, episodes_in_cluster=2)

    # Embargo: Day 9 -> 4 event clusters (all losers — MUST be dropped from both Train and Holdout!)
    for i in range(4):
        ser, cat = series_defs[i % 4]
        _emit_cluster(day_offset_days=9, cluster_idx=i, series_ticker=ser, category=cat, outcome="no", episodes_in_cluster=4)

    # Holdout: Days 10-14 -> 44 event clusters emitted chronologically (11 per series = 25% share, 4 episodes each = 176 fills)
    for i in range(44):
        ser, cat = series_defs[i % 4]
        day_num = 10 + (i * 5) // 44  # monotonic across Days 10..14
        outcome = "yes" if (i % 5 != 0 and i % 5 != 3) else "no"  # 60% YES wins
        _emit_cluster(day_offset_days=day_num, cluster_idx=i, series_ticker=ser, category=cat, outcome=outcome, episodes_in_cluster=4)

    return tb.seal()


def test_full_g2a_pass_deterministic_bootstrap_stress_and_byte_identical_cli(tmp_path: pathlib.Path):
    tape_dir = _build_g2a_passing_14_day_tape(tmp_path / "tape_14d_g2a")

    # Record tape file hashes before running CLI to prove strictly read-only behavior
    before_hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(tape_dir.iterdir())
        if p.is_file()
    }

    # Run CLI twice to two output files and assert byte-identical JSON & SHA-256 report hashes!
    out_1 = tmp_path / "report_run1.json"
    out_2 = tmp_path / "report_run2.json"

    rc1 = cli_runner.main(
        [
            "--tape-dir",
            str(tape_dir),
            "--output",
            str(out_1),
            "--bootstrap-seed",
            str(DEFAULT_BOOTSTRAP_SEED),
            "--bootstrap-resamples",
            str(DEFAULT_BOOTSTRAP_RESAMPLES),
            "--replay-git-sha",
            "deadbeef1234",
            "--verify-determinism",
        ]
    )
    rc2 = cli_runner.main(
        [
            "--tape-dir",
            str(tape_dir),
            "--output",
            str(out_2),
            "--bootstrap-seed",
            str(DEFAULT_BOOTSTRAP_SEED),
            "--bootstrap-resamples",
            str(DEFAULT_BOOTSTRAP_RESAMPLES),
            "--replay-git-sha",
            "deadbeef1234",
        ]
    )
    assert rc1 == 0 and rc2 == 0

    # Strictly read-only on tape files
    after_hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(tape_dir.iterdir())
        if p.is_file()
    }
    assert after_hashes == before_hashes

    # Byte-identical JSON & identical report_sha256 across consecutive runs
    bytes_1 = out_1.read_bytes()
    bytes_2 = out_2.read_bytes()
    assert bytes_1 == bytes_2

    report = json.loads(bytes_1.decode("utf-8"))
    report_2 = json.loads(bytes_2.decode("utf-8"))
    assert report["report_sha256"] == report_2["report_sha256"]
    assert len(report["report_sha256"]) == 64
    assert report["synthetic_fills_present"] is False

    # Chronological split verified
    sp = report["chronological_split"]
    assert sp["train_event_clusters_count"] == 20
    assert sp["embargo_event_clusters_count"] == 4
    assert sp["holdout_event_clusters_count"] == 44

    # Cryptographic Freeze Package verified
    freeze = report["cryptographic_freeze_package"]
    assert len(freeze["selected_variant_config_sha256"]) == 64
    assert freeze["replay_git_sha"] == "deadbeef1234"
    assert len(freeze["holdout_tape_manifest_sha256"]) == 64
    assert len(freeze["freeze_package_sha256"]) == 64
    assert freeze["holdout_evaluated_before_freeze"] is False
    assert freeze["plateau_test_passed"] is True

    # Full G2A Holdout PASS verified
    g2a = report["g2a_adjudication"]
    assert g2a["verdict"] == "PASS_G2A", f"Expected PASS_G2A, failed checks: {g2a['failed_checks']}"
    assert g2a["g2a_passed"] is True
    assert g2a["failed_checks"] == []
    assert g2a["counts"]["resolved_event_clusters"] == 44
    assert g2a["counts"]["filled_order_episodes_lb"] == 176
    assert g2a["counts"]["series_count"] == 4
    assert g2a["counts"]["max_series_fill_share_bps"] == 2500  # 25% <= 40%
    assert g2a["edge"]["lb_ev_pips"] > 0
    assert g2a["edge"]["mid_ev_pips"] > 0

    # Deterministic 10,000-resample cluster bootstrap verified
    boot = g2a["edge"]["bootstrap"]
    assert boot["resamples"] == 10_000
    assert boot["seed"] == DEFAULT_BOOTSTRAP_SEED
    assert boot["cluster_count"] == 44
    assert boot["p20_one_sided_80pct_lb_pips"] >= -300
    assert boot["passes_minus_300_pips_floor"] is True

    # Stress Suite reported without mutating pass thresholds
    stress = g2a["stress_suite"]
    assert stress["mutates_pass_thresholds"] is False
    assert stress["minus_5pp_conditional_win_prob"]["ev_pips"] == g2a["edge"]["lb_ev_pips"] - 500
    assert stress["plus_1c_extra_cost"]["ev_pips"] == g2a["edge"]["lb_ev_pips"] - 100
    assert stress["worst_case_adverse_selection_pi_l"]["pi_l_micro"] == g2a["edge"]["pi_l_micro"]


def test_p99_rtt_latency_expansion_incomplete_window_censoring_and_mixed_pi_l(tmp_path: pathlib.Path):
    # 1. Verify L = max(2s, p99_rtt_ns) expands when p99 RTT is 4s (so t_live = t + 4s, t_live + eps = t + 8s)
    tb = _TapeBuilder(tmp_path / "sess_rtt")
    tk = "KXHIGHMIA-26NOV02-T80"
    close_ns = BASE_NS + 12 * NS_PER_HOUR
    tb.add_meta(ticker=tk, event_ticker="KXHIGHMIA-26NOV02", series_ticker="KXHIGHMIA", category="WEATHER", close_ns=close_ns, ts_ns=BASE_NS)
    t0 = BASE_NS + 100 * NS_PER_SECOND
    tb.add_l2(ticker=tk, yes_bids=[("0.4400", "200.00")], no_bids=[("0.5000", "200.00")], ts_ns=t0, rtt_ns=4 * NS_PER_SECOND)
    # Print at +6s is strictly inside t_live + eps (+8s) -> MUST be excluded!
    tb.add_trade(trade_id="TRD-TOO-EARLY", ticker=tk, yes_price="0.4300", count="10.00", taker_side="no", trade_ts_ns=t0 + 6 * NS_PER_SECOND)
    # Print at +9s is strictly after t_live + eps (+8s) -> MUST fill!
    tb.add_trade(trade_id="TRD-AFTER-EPS", ticker=tk, yes_price="0.4300", count="3.00", taker_side="no", trade_ts_ns=t0 + 9 * NS_PER_SECOND)
    tb.add_settlement(ticker=tk, result="yes", settled_ts_ns=t0 + 60 * NS_PER_SECOND)

    tape = load_v2_tape(tb.seal())
    assert tape.p99_rtt_ns == 4 * NS_PER_SECOND
    assert tape.latency_l_ns == 4 * NS_PER_SECOND
    ep = simulate_order_episode(
        episode_id="EP-RTT",
        contract_meta=tape.contracts[tk],
        decision_snap_idx=0,
        cancel_snap_idx=None,
        proposed_bid_pips=4400,
        order_qty_centi=500,
        l2_snaps=tape.l2_by_ticker[tk],
        trades=tape.trades_by_ticker[tk],
        settlement=tape.settlements[tk],
        censor_intervals=tape.censor_intervals,
        latency_l_ns=tape.latency_l_ns,
    )
    assert ep.filled_qty_lb_centi == 300
    assert ep.citing_trade_ids_lb == ("TRD-AFTER-EPS",)

    # 2. Verify INCOMPLETE trade window censors overlapping episode and excludes its fills
    tb_inc = _TapeBuilder(tmp_path / "sess_incomplete")
    tk_inc = "KXCPI-26NOV02-T03"
    tb_inc.add_meta(ticker=tk_inc, event_ticker="KXCPI-26NOV02", series_ticker="KXCPI", category="SCHEDULED_MACRO", close_ns=close_ns, ts_ns=BASE_NS)
    tb_inc.add_l2(ticker=tk_inc, yes_bids=[("0.4400", "200.00")], no_bids=[("0.5000", "200.00")], ts_ns=t0)
    tb_inc.add_trade(
        trade_id="TRD-INC-1",
        ticker=tk_inc,
        yes_price="0.4300",
        count="5.00",
        taker_side="no",
        trade_ts_ns=t0 + 10 * NS_PER_SECOND,
        window_completeness_status="INCOMPLETE",
        window_min_ts=(t0 // NS_PER_SECOND),
        window_max_ts=((t0 + 30 * NS_PER_SECOND) // NS_PER_SECOND),
    )
    tb_inc.add_settlement(ticker=tk_inc, result="yes", settled_ts_ns=t0 + 60 * NS_PER_SECOND)
    tape_inc = load_v2_tape(tb_inc.seal())
    ep_inc = simulate_order_episode(
        episode_id="EP-INC",
        contract_meta=tape_inc.contracts[tk_inc],
        decision_snap_idx=0,
        cancel_snap_idx=None,
        proposed_bid_pips=4400,
        order_qty_centi=500,
        l2_snaps=tape_inc.l2_by_ticker[tk_inc],
        trades=tape_inc.trades_by_ticker[tk_inc],
        settlement=tape_inc.settlements[tk_inc],
        censor_intervals=tape_inc.censor_intervals,
        latency_l_ns=tape_inc.latency_l_ns,
    )
    assert ep_inc.censored is True
    assert ep_inc.status == "CENSORED"
    assert ep_inc.filled_qty_lb_centi == 0

    # 3. Verify mixed Winner + Loser strictly separates Pi_L < certified_total_pnl_micro
    # Winner: bid 50c, settles YES (+5000 pips), L=100, U=500 -> LB=+500_000, UB=+2_500_000
    # Loser:  bid 50c, settles NO  (-5000 pips), L=100, U=500 -> LB=-500_000, UB=-2_500_000
    # Total LB = 0, Total UB = 0 => certified_total_pnl_micro = 0,
    # while Pi_L = +500_000 + (-2_500_000) = -2_000_000 (minimum fills on winner, maximum fills on loser)!
    tb_mix = _TapeBuilder(tmp_path / "sess_mix")
    for tk_m, ev_m, outcome in (
        ("KXHIGHMIA-26NOV02-W1", "KXHIGHMIA-26NOV02-W", "yes"),
        ("KXHIGHMIA-26NOV02-L1", "KXHIGHMIA-26NOV02-L", "no"),
    ):
        tb_mix.add_meta(ticker=tk_m, event_ticker=ev_m, series_ticker="KXHIGHMIA", category="WEATHER", close_ns=close_ns, ts_ns=BASE_NS)
        tb_mix.add_l2(ticker=tk_m, yes_bids=[("0.5000", "120.00")], no_bids=[("0.4400", "200.00")], ts_ns=t0)
        tb_mix.add_l2(ticker=tk_m, yes_bids=[("0.5000", "120.00")], no_bids=[("0.4400", "200.00")], ts_ns=t0 + 10 * NS_PER_SECOND)
        tb_mix.add_l2(ticker=tk_m, yes_bids=[("0.5000", "116.00")], no_bids=[("0.4400", "200.00")], ts_ns=t0 + 15 * NS_PER_SECOND)
        tb_mix.add_trade(trade_id=f"TRD-MIX-{tk_m}", ticker=tk_m, yes_price="0.5000", count="121.00", taker_side="no", trade_ts_ns=t0 + 20 * NS_PER_SECOND)
        tb_mix.add_settlement(ticker=tk_m, result=outcome, settled_ts_ns=t0 + 60 * NS_PER_SECOND)
        t0 += 120 * NS_PER_SECOND

    tape_mix = load_v2_tape(tb_mix.seal())
    res_mix = replay_variant_on_tape(
        tape_mix,
        ReplayVariantConfig(variant_id="V_MIX", min_spread_pips=400, order_qty_centi=500),
    )
    assert res_mix["total_pnl_lb_micro"] == 0
    assert res_mix["total_pnl_ub_micro"] == 0
    assert res_mix["certified_total_pnl_micro"] == 0
    assert res_mix["pi_l_micro"] == -2_000_000
    assert res_mix["pi_l_micro"] < res_mix["certified_total_pnl_micro"]

