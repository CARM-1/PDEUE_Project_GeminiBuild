"""Build Order Brief 01 — Collector v2.0 verification suite.

Covers:
1. 3-unit exact-integer ADR-008 parser (price_pips, qty_centi, micro_dollars, zero float()).
2. Kalshi YES/NO ladder normalization, external-api.kalshi.com base URL, locked/crossed quarantine.
3. CQP-001-v0.1 Admission vs. Retention (anti-survivorship +1 post-settlement snapshot) vs.
   Strategy D spread/depth/consecutive tradeability + Polymarket BENCHMARK_ONLY (cap 16, 1c retained).
4. Tiered polling (batched /markets/orderbooks, 120s overlapping /markets/trades cursor pagination
   & trade_id dedup, <= 2 req/s governor, HTTP 429 exponential backoff + cadence ladder + DATA_GAP).
5. Append-only JSONL v2.0.0 7-record-type envelope & O(1) rolling SHA-256 manifest in collector_heartbeat.json.
"""
from __future__ import annotations

import ast
import hashlib
import json
import pathlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import httpx
import pytest
import yaml

from app.adapters.collector_v2 import (
    CURATED_CADENCE_LADDER,
    DEFAULT_CQP_CONFIG,
    KALSHI_EXTERNAL_API_BASE,
    MAX_CURATED_KALSHI_CONTRACTS,
    MAX_POLYMARKET_BENCHMARK_CONTRACTS,
    RECORD_TYPES,
    SCHEMA_VERSION_V2,
    ContractLifecycleTracker,
    ObservedL2CollectorV2,
    RateLimitGovernor,
    StreamingTapeWriterV2,
    TradeDeduplicator,
    assert_fail_closed_paper_mode,
    compute_filter_config_hash,
    compute_micro_dollars,
    evaluate_kalshi_admission,
    is_uniform_1c_grid_10_90,
    normalize_kalshi_l2_v2,
    normalize_polymarket_l2_v2,
    parse_book_level,
    parse_price_pips,
    parse_qty_centi,
    verify_v2_tape_manifest,
)
from app.adapters.live_l2_tape_recorder import KALSHI_PUBLIC_BASE, verify_tape_manifest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
COLLECTOR_V2_PATH = REPO_ROOT / "backend" / "app" / "adapters" / "collector_v2.py"
COMPOSE_PAPER_PATH = REPO_ROOT / "deploy" / "docker-compose.paper.yml"


# ---------------------------------------------------------------------------
# 1. 3-Unit Exact-Integer Parser (ADR-008 Upgrade)
# ---------------------------------------------------------------------------


def test_3unit_exact_integer_parsing_and_zero_float():
    # Standard exact-cent quote
    p_raw, p_pips = parse_price_pips("0.4500")
    assert p_raw == "0.4500"
    assert p_pips == 4500
    assert isinstance(p_pips, int)
    assert p_pips % 100 == 0

    # Sub-cent quote (0.0010 = 10 pips) must parse cleanly without crashing
    sub_raw, sub_pips = parse_price_pips("0.0010")
    assert sub_raw == "0.0010"
    assert sub_pips == 10
    assert sub_pips % 100 != 0

    # Centi-contracts: 100.25 -> 10025 with fractional_quantity_flag=True
    q_raw, q_centi, frac = parse_qty_centi("100.25")
    assert q_raw == "100.25"
    assert q_centi == 10025
    assert frac is True

    # Whole contracts: 100.00 -> 10000 with fractional_quantity_flag=False
    wq_raw, wq_centi, wfrac = parse_qty_centi("100.00")
    assert wq_raw == "100.00"
    assert wq_centi == 10000
    assert wfrac is False

    # Exact int64 identity: price_pips * qty_centi == micro_dollars
    micro = compute_micro_dollars(p_pips, q_centi)
    assert micro == 45_112_500
    assert p_pips * q_centi == micro

    sub_micro = compute_micro_dollars(sub_pips, q_centi)
    assert sub_micro == 100_250
    assert sub_pips * q_centi == sub_micro

    lv = parse_book_level("0.4500", "100.25")
    assert lv["price_raw"] == "0.4500"
    assert lv["price_pips"] == 4500
    assert lv["qty_raw"] == "100.25"
    assert lv["qty_centi"] == 10025
    assert lv["micro_dollars"] == 45_112_500
    assert lv["exact_cent"] is True
    assert lv["fractional_quantity_flag"] is True

    # Floats & booleans strictly rejected
    with pytest.raises(TypeError, match="Floating-point"):
        parse_price_pips(0.45)
    with pytest.raises(TypeError, match="Floating-point"):
        parse_qty_centi(100.25)
    with pytest.raises(TypeError):
        parse_price_pips(True)
    with pytest.raises(TypeError):
        compute_micro_dollars(4500, True)  # type: ignore[arg-type]

    # Static AST audit: collector_v2.py must never call float() anywhere
    tree = ast.parse(COLLECTOR_V2_PATH.read_text(encoding="utf-8"))
    float_calls = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "float"
    ]
    assert float_calls == [], f"Prohibited float() calls found in collector_v2.py at lines {float_calls}"


def test_uniform_1c_grid_10_90_and_sub_cent_snapshot_never_crashes():
    # Uniform 1c grid across [10c, 90c] (even with sub-cent edges outside [10c, 90c])
    assert is_uniform_1c_grid_10_90(
        [
            {"start": "0.0000", "end": "0.1000", "step": "0.0010"},
            {"start": "0.1000", "end": "0.9000", "step": "0.0100"},
            {"start": "0.9000", "end": "1.0000", "step": "0.0010"},
        ]
    ) is True

    # Non-uniform sub-cent grid inside [10c, 90c] -> False
    assert is_uniform_1c_grid_10_90(
        [{"start": "0.0000", "end": "1.0000", "step": "0.0010"}]
    ) is False

    # 5c grid inside [10c, 90c] -> False
    assert is_uniform_1c_grid_10_90(
        [{"start": "0.0000", "end": "1.0000", "step": "0.0500"}]
    ) is False

    # Sub-cent quote (0.0010) on Kalshi book must NOT crash; records with exact_cent_eligible=False
    snap = normalize_kalshi_l2_v2(
        "KXHIGHMIA-26NOV27-T80",
        {
            "orderbook_fp": {
                "yes_dollars": [["0.4500", "150.00"], ["0.0010", "50.25"]],
                "no_dollars": [["0.5000", "120.00"]],
            }
        },
        source_url=f"{KALSHI_EXTERNAL_API_BASE}/markets/orderbooks",
    )
    assert snap["exact_cent_eligible"] is False
    assert snap["fractional_quantity_flag"] is True
    assert snap["best_yes_bid_pips"] == 4500
    assert snap["best_yes_ask_pips"] == 5000
    assert snap["spread_pips"] == 500
    assert any(lv["price_raw"] == "0.0010" and lv["price_pips"] == 10 for lv in snap["yes_bids"])


# ---------------------------------------------------------------------------
# 2. Kalshi Binary Book Normalization & Locked/Crossed Quarantine
# ---------------------------------------------------------------------------


def test_kalshi_yes_no_normalization_and_locked_crossed_quarantine():
    assert KALSHI_EXTERNAL_API_BASE == "https://external-api.kalshi.com/trade-api/v2"
    assert KALSHI_PUBLIC_BASE == "https://external-api.kalshi.com/trade-api/v2"

    # Normal book: YES bid 0.4400 (4400), NO bid 0.5000 -> YES ask = 10000 - 5000 = 5000 -> spread = 600 pips (6c)
    normal = normalize_kalshi_l2_v2(
        "KXHIGHNYC-26NOV27-T55",
        {
            "orderbook_fp": {
                "yes_dollars": [["0.4400", "150.00"], ["0.4100", "200.00"]],
                "no_dollars": [["0.5000", "120.00"], ["0.4800", "100.00"]],
            }
        },
        source_url=f"{KALSHI_EXTERNAL_API_BASE}/markets/orderbooks",
    )
    assert normal["best_yes_bid_pips"] == 4400
    assert normal["best_no_bid_pips"] == 5000
    assert normal["best_yes_ask_pips"] == 5000
    assert normal["spread_pips"] == 600
    assert normal["book_quarantined"] is False
    assert normal["quarantine_reason"] is None
    assert normal["exact_cent_eligible"] is True
    assert normal["yes_asks"][0]["no_bid_price_raw"] == "0.5000"
    assert normal["yes_asks"][0]["no_bid_price_pips"] == 5000
    assert normal["yes_asks"][0]["price_pips"] == 5000

    # Locked book: YES bid 0.5000 (5000), NO bid 0.5000 -> YES ask = 5000 -> spread = 0 -> QUARANTINED
    locked = normalize_kalshi_l2_v2(
        "KXHIGHNYC-26NOV27-T55",
        {
            "orderbook_fp": {
                "yes_dollars": [["0.5000", "200.00"]],
                "no_dollars": [["0.5000", "200.00"]],
            }
        },
        source_url=f"{KALSHI_EXTERNAL_API_BASE}/markets/orderbooks",
    )
    assert locked["spread_pips"] == 0
    assert locked["book_quarantined"] is True
    assert locked["quarantine_reason"] == "LOCKED_BOOK"

    # Crossed book: YES bid 0.5300 (5300), NO bid 0.5000 -> YES ask = 5000 -> spread = -300 -> QUARANTINED
    crossed = normalize_kalshi_l2_v2(
        "KXHIGHNYC-26NOV27-T55",
        {
            "orderbook_fp": {
                "yes_dollars": [["0.5300", "200.00"]],
                "no_dollars": [["0.5000", "200.00"]],
            }
        },
        source_url=f"{KALSHI_EXTERNAL_API_BASE}/markets/orderbooks",
    )
    assert crossed["spread_pips"] == -300
    assert crossed["book_quarantined"] is True
    assert crossed["quarantine_reason"] == "CROSSED_BOOK"

    tracker = ContractLifecycleTracker()
    assert tracker.evaluate_snapshot_tradeability("KXHIGHNYC-26NOV27-T55", locked)["strategy_d_eligible"] is False
    assert tracker.evaluate_snapshot_tradeability("KXHIGHNYC-26NOV27-T55", crossed)["strategy_d_eligible"] is False


# ---------------------------------------------------------------------------
# 3. Admission vs. Retention (Anti-Survivorship) vs. Strategy D Spread Filter
# ---------------------------------------------------------------------------


def _mk_market(
    ticker: str,
    *,
    close_dt: datetime,
    status: str = "open",
    volume_24h_fp: str = "5000.00",
    open_interest_fp: str = "10000.00",
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    m: Dict[str, Any] = {
        "ticker": ticker,
        "status": status,
        "close_time": close_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "volume_24h_fp": volume_24h_fp,
        "open_interest_fp": open_interest_fp,
        "price_ranges": [{"start": "0.0000", "end": "1.0000", "step": "0.0100"}],
    }
    if extra:
        m.update(extra)
    return m


def test_admission_priority_bans_cap_and_config_hash():
    now = datetime(2026, 11, 26, 12, 0, 0, tzinfo=timezone.utc)
    window_end = now + timedelta(days=14)
    h1 = compute_filter_config_hash(DEFAULT_CQP_CONFIG)
    h2 = compute_filter_config_hash(DEFAULT_CQP_CONFIG)
    assert len(h1) == 64 and h1 == h2

    # Valid Weather, Macro, Pre-Game Sports, and Crypto (BENCHMARK_ONLY)
    weather_ok = _mk_market("KXHIGHMIA-26NOV27-T80", close_dt=now + timedelta(hours=24))
    macro_ok = _mk_market("KXCPI-26DEC-T03", close_dt=now + timedelta(hours=72))
    sports_ok = _mk_market(
        "KXNFL-26NOV29-BUF",
        close_dt=now + timedelta(hours=48),
        extra={"event_start_time": (now + timedelta(hours=40)).strftime("%Y-%m-%dT%H:%M:%SZ")},
    )
    crypto_ok = _mk_market("KXBTC-26NOV27-100K", close_dt=now + timedelta(hours=12))

    # Banned / rejected cases
    mve_combo = _mk_market("KXMVE-PARLAY-1", close_dt=now + timedelta(hours=24), extra={"is_mve": True})
    in_play_sports = _mk_market(
        "KXNBA-26NOV26-LAL",
        close_dt=now + timedelta(hours=4),
        extra={"in_play": True},
    )
    in_play_started = _mk_market(
        "KXNFL-26NOV26-KC",
        close_dt=now + timedelta(hours=3),
        extra={"event_start_time": (now - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")},
    )
    too_soon = _mk_market("KXHIGHNYC-26NOV26-T50", close_dt=now + timedelta(minutes=30))
    multi_year_novelty = _mk_market("KXHIGHNYC-2029-T99", close_dt=now + timedelta(days=365))
    exceeds_window = _mk_market("KXCPI-26DEC10-T03", close_dt=window_end - timedelta(hours=12))

    assert evaluate_kalshi_admission(weather_ok, now_utc=now, recording_window_end_utc=window_end)["admitted"] is True
    assert evaluate_kalshi_admission(macro_ok, now_utc=now, recording_window_end_utc=window_end)["admitted"] is True
    assert evaluate_kalshi_admission(sports_ok, now_utc=now, recording_window_end_utc=window_end)["admitted"] is True

    crypto_dec = evaluate_kalshi_admission(crypto_ok, now_utc=now, recording_window_end_utc=window_end)
    assert crypto_dec["admitted"] is True
    assert crypto_dec["classification"] == "BENCHMARK_ONLY"
    assert crypto_dec["category"] == "SHORT_HORIZON_CRYPTO"

    for bad in (mve_combo, in_play_sports, in_play_started, too_soon, multi_year_novelty, exceeds_window):
        dec = evaluate_kalshi_admission(bad, now_utc=now, recording_window_end_utc=window_end)
        assert dec["admitted"] is False, f"Expected {bad['ticker']} to be rejected"

    # Curated basket hard cap at 32 contracts prioritizing Weather > Macro > Sports > Crypto
    tracker = ContractLifecycleTracker(recording_window_end_utc=window_end)
    bulk: List[Dict[str, Any]] = []
    for i in range(15):
        bulk.append(_mk_market(f"KXHIGH-W{i:02d}", close_dt=now + timedelta(hours=24)))
    for i in range(15):
        bulk.append(_mk_market(f"KXCPI-M{i:02d}", close_dt=now + timedelta(hours=48)))
    for i in range(10):
        bulk.append(_mk_market(f"KXNFL-S{i:02d}", close_dt=now + timedelta(hours=72)))
    for i in range(5):
        bulk.append(_mk_market(f"KXBTC-C{i:02d}", close_dt=now + timedelta(hours=12)))

    res = tracker.reconcile_admission_scan(bulk, now_utc=now)
    assert len(res["active_tickers"]) == MAX_CURATED_KALSHI_CONTRACTS == 32
    # All 15 Weather + all 15 Macro + 2 Sports admitted; 0 Crypto because cap filled by higher priority
    admitted_cats = [tracker.contracts[t].category for t in res["active_tickers"]]
    assert admitted_cats.count("WEATHER") == 15
    assert admitted_cats.count("SCHEDULED_MACRO") == 15
    assert admitted_cats.count("PRE_GAME_SPORTS") == 2
    assert admitted_cats.count("SHORT_HORIZON_CRYPTO") == 0


def test_retention_anti_survivorship_and_strategy_d_spread_filter():
    now = datetime(2026, 11, 26, 12, 0, 0, tzinfo=timezone.utc)
    window_end = now + timedelta(days=14)
    tracker = ContractLifecycleTracker(recording_window_end_utc=window_end)

    weather_t = "KXHIGHMIA-26NOV27-T80"
    crypto_t = "KXBTC-26NOV27-100K"
    tracker.reconcile_admission_scan(
        [
            _mk_market(weather_t, close_dt=now + timedelta(hours=24)),
            _mk_market(crypto_t, close_dt=now + timedelta(hours=12)),
        ],
        now_utc=now,
    )
    assert set(tracker.active_tickers()) == {weather_t, crypto_t}

    def _snap(ticker: str, yes_bid: str, no_bid: str, qty: str = "150.00") -> Dict[str, Any]:
        raw = normalize_kalshi_l2_v2(
            ticker,
            {"orderbook_fp": {"yes_dollars": [[yes_bid, qty]], "no_dollars": [[no_bid, qty]]}},
            source_url=f"{KALSHI_EXTERNAL_API_BASE}/markets/orderbooks",
            market_meta=tracker.contracts[ticker].market_meta,
        )
        return tracker.evaluate_snapshot_tradeability(ticker, raw)

    # 1. 1c-2c spread rejected for Strategy D (observation-only)
    s_1c = _snap(weather_t, "0.4900", "0.5000")  # ask=50c, spread=1c (100 pips)
    assert s_1c["spread_pips"] == 100
    assert s_1c["spread_bucket"] == "OBSERVATION_ONLY_TIGHT_1C_2C"
    assert s_1c["strategy_d_eligible"] is False
    assert s_1c["strategy_d_replay_variant_eligible"] is False

    s_2c = _snap(weather_t, "0.4800", "0.5000")  # ask=50c, spread=2c (200 pips)
    assert s_2c["spread_pips"] == 200
    assert s_2c["spread_bucket"] == "OBSERVATION_ONLY_TIGHT_1C_2C"
    assert s_2c["strategy_d_eligible"] is False

    # 2. 3c spread flagged as replay-variant eligible only after >= 2 consecutive snapshots
    s_3c_1 = _snap(weather_t, "0.4700", "0.5000")  # 300 pips
    assert s_3c_1["spread_bucket"] == "REPLAY_VARIANT_3C"
    assert s_3c_1["strategy_d_eligible"] is False
    assert s_3c_1["strategy_d_replay_variant_eligible"] is False

    s_3c_2 = _snap(weather_t, "0.4700", "0.5000")  # 2nd consecutive 3c snapshot
    assert s_3c_2["strategy_d_eligible"] is False
    assert s_3c_2["strategy_d_replay_variant_eligible"] is True

    # 3. 4c-10c spread admitted for Strategy D ONLY after >= 2 consecutive snapshots & >= 100 contracts depth
    s_6c_low_depth = _snap(weather_t, "0.4400", "0.5000", qty="50.00")  # depth 50 < 100
    assert s_6c_low_depth["strategy_d_eligible"] is False

    s_6c_1 = _snap(weather_t, "0.4400", "0.5000", qty="100.00")  # 600 pips, depth 100, snap #1
    assert s_6c_1["spread_bucket"] == "STRATEGY_D_DEFAULT_4C_10C"
    assert s_6c_1["consecutive_strategy_d_snapshots"] == 1
    assert s_6c_1["strategy_d_eligible"] is False

    s_6c_2 = _snap(weather_t, "0.4400", "0.5000", qty="100.00")  # snap #2 -> eligible!
    assert s_6c_2["consecutive_strategy_d_snapshots"] == 2
    assert s_6c_2["strategy_d_eligible"] is True

    # 4. Short-horizon Crypto is ALWAYS BENCHMARK_ONLY, NEVER Strategy D eligible
    for _ in range(3):
        c_snap = _snap(crypto_t, "0.4500", "0.5000", qty="500.00")  # 5c spread, huge depth
        assert c_snap["classification"] == "BENCHMARK_ONLY"
        assert c_snap["strategy_d_eligible"] is False
        assert c_snap["strategy_d_replay_variant_eligible"] is False

    # 5. Anti-Survivorship Retention: wide spread / low liquidity / missing from open scan MUST NOT evict
    s_wide = _snap(weather_t, "0.2000", "0.6000", qty="5.00")  # 20c spread, 5 contracts
    assert s_wide["strategy_d_eligible"] is False
    reconcile_empty = tracker.reconcile_admission_scan([], now_utc=now + timedelta(hours=2))
    assert weather_t in reconcile_empty["active_tickers"]  # NEVER silently evicted mid-life!

    # 6. Settlement + 1 post-settlement snapshot required before slot release
    settled_scan = tracker.reconcile_admission_scan(
        [
            _mk_market(
                weather_t,
                close_dt=now + timedelta(hours=24),
                status="settled",
                extra={"result": "yes"},
            )
        ],
        now_utc=now + timedelta(hours=25),
    )
    assert len(settled_scan["settlements"]) == 1
    assert settled_scan["settlements"][0]["settlement_result"] == "yes"
    assert settled_scan["settlements"][0]["settlement_value_pips"] == 10_000
    # Still retained until +1 post-settlement snapshot is captured!
    assert weather_t in tracker.active_tickers()

    post_snap = _snap(weather_t, "0.9900", "0.0100", qty="10.00")
    assert post_snap["post_settlement_snapshot"] is True
    assert post_snap["lifecycle_state"] == "SETTLED_COMPLETE"
    assert weather_t not in tracker.active_tickers()


def test_polymarket_benchmark_only_retains_1c_and_caps_at_16(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PDEUE_VENUE_MODE", "observation")
    monkeypatch.setenv("PDEUE_LIVE_TRADING_ENABLED", "false")

    # 20 Polymarket markets available -> collector MUST hard-cap at 16
    poly_tokens = [f"POLY-TOK-{i:02d}" for i in range(20)]

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "external-api.kalshi.com" in url and "/markets/trades" in url:
            return httpx.Response(200, json={"trades": [], "cursor": ""})
        if "external-api.kalshi.com" in url and "/markets" in url:
            return httpx.Response(200, json={"markets": [], "cursor": ""})
        if "gamma-api.polymarket.com" in url:
            return httpx.Response(
                200,
                json=[
                    {"active": True, "closed": False, "enableOrderBook": True, "clobTokenIds": json.dumps([tok])}
                    for tok in poly_tokens
                ],
            )
        if "clob.polymarket.com/book" in url:
            return httpx.Response(
                200,
                json={"bids": [{"price": "0.50", "size": "400"}], "asks": [{"price": "0.51", "size": "350"}]},
            )
        return httpx.Response(404)

    collector = ObservedL2CollectorV2(
        tmp_path / "tapes",
        poly_benchmark_count=25,  # intentionally above cap -> must clamp to 16
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep_fn=lambda _s: None,
        monotonic_fn=lambda: 100.0,
        log_fn=lambda _m: None,
        session_id="sess_poly_cap",
    )
    try:
        hb = collector.collect_once()
        assert len(collector.poly_tokens) == MAX_POLYMARKET_BENCHMARK_CONTRACTS == 16
        assert hb["polymarket_benchmark_active_count"] == 16
    finally:
        collector.close()

    # Check Polymarket 1c spread retained as BENCHMARK_ONLY, live_execution_eligible=False
    lines = [
        json.loads(ln)
        for ln in (collector.session_dir / "tape.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    poly_l2 = [r for r in lines if r["record_type"] == "OBSERVED_L2" and r["venue"] == "POLYMARKET"]
    assert len(poly_l2) == 16
    for rec in poly_l2:
        assert rec["classification"] == "BENCHMARK_ONLY"
        assert rec["live_execution_eligible"] is False
        assert rec["strategy_d_eligible"] is False
        assert rec["spread_pips"] == 100
        assert rec["spread_bucket"] == "BENCHMARK_TIGHT_1C"


# ---------------------------------------------------------------------------
# 4. Overlapping 120s Trade Pagination Dedup, <=2 req/s Governor & HTTP 429 DATA_GAP
# ---------------------------------------------------------------------------


def test_overlapping_120s_trade_pagination_dedup_and_completeness_states(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PDEUE_VENUE_MODE", "observation")
    monkeypatch.setenv("PDEUE_LIVE_TRADING_ENABLED", "false")

    base_now = datetime(2026, 11, 26, 16, 0, 0, tzinfo=timezone.utc)
    clock = {"now": base_now, "phase": 1}
    seen_trade_queries: List[Dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/markets/trades" in url:
            params = dict(request.url.params)
            seen_trade_queries.append(params)
            cursor = params.get("cursor", "")
            if clock["phase"] == 1:
                if not cursor:
                    return httpx.Response(
                        200,
                        json={
                            "trades": [
                                {
                                    "trade_id": "TRD-001",
                                    "ticker": "KXHIGHMIA-26NOV27-T80",
                                    "yes_price_dollars": "0.4500",
                                    "count_fp": "100.25",
                                    "taker_side": "yes",
                                    "is_block_trade": False,
                                    "created_time": "2026-11-26T15:59:10Z",
                                }
                            ],
                            "cursor": "page-2",
                        },
                    )
                if cursor == "page-2":
                    return httpx.Response(
                        200,
                        json={
                            "trades": [
                                {
                                    "trade_id": "TRD-002",
                                    "ticker": "KXHIGHMIA-26NOV27-T80",
                                    "yes_price_dollars": "0.4600",
                                    "count_fp": "250.00",
                                    "taker_side": "no",
                                    "is_block_trade": True,
                                    "created_time": "2026-11-26T15:59:50Z",
                                }
                            ],
                            "cursor": "",
                        },
                    )
            elif clock["phase"] == 2:
                # Overlapping 120s window returns TRD-002 again (duplicate!) + new TRD-003
                return httpx.Response(
                    200,
                    json={
                        "trades": [
                            {
                                "trade_id": "TRD-002",
                                "ticker": "KXHIGHMIA-26NOV27-T80",
                                "yes_price_dollars": "0.4600",
                                "count_fp": "250.00",
                                "taker_side": "no",
                                "is_block_trade": True,
                                "created_time": "2026-11-26T15:59:50Z",
                            },
                            {
                                "trade_id": "TRD-003",
                                "ticker": "KXHIGHMIA-26NOV27-T80",
                                "yes_price_dollars": "0.0010",  # sub-cent trade must not crash!
                                "count_fp": "10.00",
                                "taker_side": "yes",
                                "is_block_trade": False,
                                "created_time": "2026-11-26T16:00:05Z",
                            },
                        ],
                        "cursor": "",
                    },
                )
            elif clock["phase"] == 3:
                return httpx.Response(200, json={"trades": [], "cursor": ""})
        return httpx.Response(200, json={"markets": [], "cursor": ""})

    collector = ObservedL2CollectorV2(
        tmp_path / "tapes",
        poly_benchmark_count=0,
        kalshi_baseline_count=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep_fn=lambda _s: None,
        monotonic_fn=lambda: 100.0,
        now_utc_fn=lambda: clock["now"],
        log_fn=lambda _m: None,
        session_id="sess_trades",
    )
    try:
        # Phase 1: 2-page cursor pagination -> COMPLETE, 2 unique trades
        r1 = collector.poll_kalshi_public_trades()
        assert r1["pages_fetched"] == 2
        assert r1["trades_emitted"] == 2
        assert r1["duplicates_skipped"] == 0
        assert r1["window_completeness_status"] == "COMPLETE"
        assert int(seen_trade_queries[0]["max_ts"]) - int(seen_trade_queries[0]["min_ts"]) == 120

        # Phase 2: 10 seconds later, overlapping 120s window -> TRD-002 deduplicated, TRD-003 emitted
        clock["now"] = base_now + timedelta(seconds=10)
        clock["phase"] = 2
        r2 = collector.poll_kalshi_public_trades()
        assert r2["trades_emitted"] == 1
        assert r2["duplicates_skipped"] == 1
        assert r2["window_completeness_status"] == "COMPLETE"

        # Phase 3: empty complete window
        clock["now"] = base_now + timedelta(seconds=20)
        clock["phase"] = 3
        r3 = collector.poll_kalshi_public_trades()
        assert r3["trades_emitted"] == 0
        assert r3["window_completeness_status"] == "EMPTY_COMPLETE"
    finally:
        collector.close()

    trades = [
        json.loads(ln)
        for ln in (collector.session_dir / "tape.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert [t["trade_id"] for t in trades] == ["TRD-001", "TRD-002", "TRD-003"]
    assert trades[0]["yes_price_raw"] == "0.4500"
    assert trades[0]["yes_price_pips"] == 4500
    assert trades[0]["count_centi"] == 10025
    assert trades[0]["micro_dollars"] == 45_112_500
    assert trades[0]["taker_side"] == "yes"
    assert trades[0]["is_block_trade"] is False
    assert trades[0]["window_completeness_status"] == "COMPLETE"

    assert trades[1]["is_block_trade"] is True
    assert trades[1]["taker_side"] == "no"

    assert trades[2]["yes_price_pips"] == 10
    assert trades[2]["exact_cent_eligible"] is False
    assert trades[2]["micro_dollars"] == 10_000


def test_rate_limit_governor_2rps_cap_and_429_backoff_cadence_and_data_gap(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PDEUE_VENUE_MODE", "observation")
    monkeypatch.setenv("PDEUE_LIVE_TRADING_ENABLED", "false")

    # 1. Verify hard <= 2 req/s governor sleeps on 3rd request within 1 second
    sim_time = {"t": 100.0}
    gov_sleeps: List[float] = []

    def fake_sleep(dt: float) -> None:
        gov_sleeps.append(dt)
        sim_time["t"] += dt

    gov = RateLimitGovernor(
        max_req_per_sec=2,
        monotonic_fn=lambda: sim_time["t"],
        sleep_fn=fake_sleep,
        jitter_fn=lambda base_ms: 500,  # deterministic +0.5s jitter
    )
    gov.acquire()
    gov.acquire()
    assert gov_sleeps == []
    gov.acquire()  # 3rd request in same 1.0s window -> MUST sleep 1.0s
    assert len(gov_sleeps) == 1 and gov_sleeps[0] >= 0.99

    # 2. Verify 429 exponential backoff up to 300s and cadence ladder 10 -> 15 -> 30 -> 60
    assert gov.current_curated_cadence_seconds == 10
    b1 = gov.record_http_429()
    assert b1["n_429"] == 1
    assert b1["backoff_ms"] == 5500  # 5s + 0.5s jitter
    assert b1["degraded_curated_cadence_seconds"] == 15

    b2 = gov.record_http_429()
    assert b2["n_429"] == 2
    assert b2["backoff_ms"] == 10500  # 10s + 0.5s jitter
    assert b2["degraded_curated_cadence_seconds"] == 30

    b3 = gov.record_http_429()
    assert b3["n_429"] == 3
    assert b3["backoff_ms"] == 20500
    assert b3["degraded_curated_cadence_seconds"] == 60

    # Further 429s clamp at 60s cadence and 300s max backoff
    for _ in range(10):
        bx = gov.record_http_429()
    assert bx["degraded_curated_cadence_seconds"] == 60
    assert bx["backoff_ms"] <= 300_000
    assert bx["backoff_seconds"] <= 300

    # 3. End-to-end simulated HTTP 429 on collector emits explicit DATA_GAP (CENSORED) + logs n_429
    now = datetime(2026, 11, 26, 12, 0, 0, tzinfo=timezone.utc)
    sleeps: List[float] = []

    def handler_429(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/markets/orderbooks" in url:
            return httpx.Response(429, json={"error": "too many requests"})
        if "/markets/trades" in url:
            return httpx.Response(429, json={"error": "too many requests"})
        if "/markets" in url:
            return httpx.Response(
                200,
                json={"markets": [_mk_market("KXHIGHMIA-26NOV27-T80", close_dt=now + timedelta(hours=24))], "cursor": ""},
            )
        return httpx.Response(404)

    collector = ObservedL2CollectorV2(
        tmp_path / "tapes",
        poly_benchmark_count=0,
        kalshi_baseline_count=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler_429)),
        sleep_fn=sleeps.append,
        monotonic_fn=lambda: 1000.0,
        now_utc_fn=lambda: now,
        jitter_fn=lambda _base_ms: 250,
        log_fn=lambda _m: None,
        session_id="sess_429",
    )
    try:
        hb = collector.collect_once()
        assert hb["rate_limited"] is True
        assert hb["n_429"] == 2  # 1 on batched orderbooks + 1 on public trades
        assert hb["curated_cadence_seconds"] == 30  # 10 -> 15 -> 30
        assert hb["data_gaps_total"] == 2
        assert hb["last_trade_window_status"] == "INCOMPLETE"
        assert len(sleeps) >= 2
        assert sleeps[0] >= 5.0
    finally:
        collector.close()

    records = [
        json.loads(ln)
        for ln in (collector.session_dir / "tape.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    gaps = [r for r in records if r["record_type"] == "DATA_GAP"]
    assert len(gaps) == 2
    for g in gaps:
        assert g["http_status"] == 429
        assert g["reason"] == "HTTP_429_RATE_LIMIT"
        assert g["replay_censor_action"] == "CENSORED"
        assert g["n_429"] >= 1
        assert g["backoff_seconds"] >= 5


# ---------------------------------------------------------------------------
# 5. All 7 Record Types, Common Envelope, Rolling SHA-256 Manifest & Fail-Closed
# ---------------------------------------------------------------------------


def test_all_7_record_types_envelope_rolling_manifest_and_fail_closed(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
):
    # Fail-closed guard refuses live mode
    with pytest.raises(RuntimeError, match="FAIL-CLOSED"):
        assert_fail_closed_paper_mode({"PDEUE_VENUE_MODE": "live", "PDEUE_LIVE_TRADING_ENABLED": "false"})
    with pytest.raises(RuntimeError, match="FAIL-CLOSED"):
        assert_fail_closed_paper_mode({"PDEUE_VENUE_MODE": "observation", "PDEUE_LIVE_TRADING_ENABLED": "true"})

    monkeypatch.setenv("PDEUE_VENUE_MODE", "observation")
    monkeypatch.setenv("PDEUE_LIVE_TRADING_ENABLED", "false")

    now = datetime(2026, 11, 26, 12, 0, 0, tzinfo=timezone.utc)
    state = {"cycle": 0}
    seen_auth: List[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        for hdr in ("authorization", "x-api-key", "kalshi-access-key", "poly-api-key"):
            if hdr in request.headers:
                seen_auth.append(hdr)
        url = str(request.url)
        if "/markets/orderbooks" in url:
            return httpx.Response(
                200,
                json={
                    "orderbooks": [
                        {
                            "ticker": "KXHIGHMIA-26NOV27-T80",
                            "orderbook_fp": {
                                "yes_dollars": [["0.4400", "150.00"]],
                                "no_dollars": [["0.5000", "120.00"]],
                            },
                        }
                    ]
                },
            )
        if "/markets/trades" in url:
            if state["cycle"] == 2:
                return httpx.Response(429, json={"error": "rate limit"})
            return httpx.Response(
                200,
                json={
                    "trades": [
                        {
                            "trade_id": "TRD-E2E-1",
                            "ticker": "KXHIGHMIA-26NOV27-T80",
                            "yes_price_dollars": "0.4500",
                            "count_fp": "100.25",
                            "taker_side": "yes",
                            "is_block_trade": False,
                            "created_time": "2026-11-26T12:00:00Z",
                        }
                    ],
                    "cursor": "",
                },
            )
        if "/markets/KXHIGHMIA-26NOV27-T80" in url:
            return httpx.Response(
                200,
                json={
                    "market": _mk_market(
                        "KXHIGHMIA-26NOV27-T80",
                        close_dt=now + timedelta(hours=24),
                        status="settled",
                        extra={"result": "yes"},
                    )
                },
            )
        if "/markets" in url:
            if state["cycle"] == 1:
                return httpx.Response(
                    200,
                    json={
                        "markets": [_mk_market("KXHIGHMIA-26NOV27-T80", close_dt=now + timedelta(hours=24))],
                        "cursor": "",
                    },
                )
            # Cycle 2: market disappeared from status=open -> triggers GET /markets/{ticker} -> SETTLEMENT_EVENT!
            return httpx.Response(200, json={"markets": [], "cursor": ""})
        return httpx.Response(404)

    sim_mono = {"t": 100.0}
    collector = ObservedL2CollectorV2(
        tmp_path / "tapes",
        poly_benchmark_count=0,
        kalshi_baseline_count=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep_fn=lambda _s: None,
        monotonic_fn=lambda: sim_mono["t"],
        now_utc_fn=lambda: now,
        jitter_fn=lambda _b: 100,
        log_fn=lambda _m: None,
        session_id="sess_all7",
        collector_git_sha="deadbeef1234",
    )
    try:
        state["cycle"] = 1
        hb1 = collector.collect_once(force_admission=True, force_curated=True, force_trades=True)
        assert hb1["schema_version"] == SCHEMA_VERSION_V2
        assert hb1["synthetic_fills_present"] is False

        state["cycle"] = 2
        sim_mono["t"] += 950.0  # advance past 15-min admission interval
        hb2 = collector.collect_once(force_admission=True, force_curated=True, force_trades=True)
        assert hb2["n_429"] == 1
    finally:
        collector.close()

    assert seen_auth == []

    # Verify all 7 record types exist in the tape!
    raw_bytes = (collector.session_dir / "tape.jsonl").read_bytes()
    actual_sha = hashlib.sha256(raw_bytes).hexdigest()

    # Rolling SHA-256 in collector_heartbeat.json MUST match disk file byte-for-byte
    hb_disk = json.loads((tmp_path / "tapes" / "collector_heartbeat.json").read_text(encoding="utf-8"))
    assert hb_disk["tape_manifest_sha256"] == actual_sha
    assert hb_disk["rolling_manifest"]["tape_manifest_sha256"] == actual_sha
    assert hb_disk["rolling_manifest"]["bytes_written"] == len(raw_bytes)
    assert hb_disk["synthetic_fills_present"] is False

    # Verify via both verify_v2_tape_manifest and unified verify_tape_manifest (zero floats, monotonic seq, 3-unit math)
    v_manifest = verify_v2_tape_manifest(collector.session_dir / "tape_manifest.json")
    assert v_manifest["tape_manifest_sha256"] == actual_sha
    assert verify_tape_manifest(collector.session_dir / "tape_manifest.json")["schema_version"] == "2.0.0"

    records = [json.loads(ln) for ln in raw_bytes.decode("utf-8").splitlines() if ln.strip()]
    observed_types = {r["record_type"] for r in records}
    assert observed_types == RECORD_TYPES, f"Missing record types: {RECORD_TYPES - observed_types}"

    for rec in records:
        assert rec["schema_version"] == "2.0.0"
        assert rec["collector_git_sha"] == "deadbeef1234"
        assert rec["filter_config_hash"] == collector.filter_config_hash
        assert isinstance(rec["capture_sequence"], int)
        assert isinstance(rec["t_req_sent_ns"], int)
        assert isinstance(rec["t_resp_recv_ns"], int)
        assert rec["t_resp_recv_ns"] >= rec["t_req_sent_ns"]
        assert len(rec["raw_payload_sha256"]) == 64
        assert rec["synthetic_fills_present"] is False

    # Single-byte tamper must fail closed
    tampered = raw_bytes.replace(b"TRD-E2E-1", b"TRD-E2E-9", 1)
    (collector.session_dir / "tape.jsonl").write_bytes(tampered)
    with pytest.raises(ValueError, match="SHA-256 tamper mismatch"):
        verify_v2_tape_manifest(collector.session_dir / "tape_manifest.json")

    # Verify Lightsail docker-compose.paper.yml preserves mem_limit: 128m and fail-closed observation defaults
    compose_doc = yaml.safe_load(COMPOSE_PAPER_PATH.read_text(encoding="utf-8"))
    svc = compose_doc["services"]["pdeue-l2-collector"]
    assert str(svc["mem_limit"]).lower() == "128m"
    assert svc["environment"]["PDEUE_VENUE_MODE"] == "observation"
    assert svc["environment"]["PDEUE_LIVE_TRADING_ENABLED"] == "false"
    assert svc["environment"]["PDEUE_COLLECTOR_SCHEMA_VERSION"] == "2.0.0"
    assert "external-api.kalshi.com/trade-api/v2" in svc["environment"]["PDEUE_KALSHI_PUBLIC_BASE"]


def test_trade_deduplicator_memory_bounded():
    dedup = TradeDeduplicator(max_entries=100)
    for i in range(250):
        assert dedup.mark_if_new(f"T-{i}", i) is True
    assert len(dedup) == 100
    assert dedup.mark_if_new("T-249", 249) is False
