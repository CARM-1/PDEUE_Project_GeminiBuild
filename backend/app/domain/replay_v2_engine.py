"""Brief #01 Schema 2.0.0 Zero-Synthetic Tape Loader & Maker Fill Engine.

Non-Negotiable Invariants:
- ZERO synthetic fills ("No print, no fill"). Every simulated fill MUST cite exact
  exchange `trade_id`(s) from `OBSERVED_TRADE` (`taker_side == "no"` for YES bids).
- NEVER promote public prints to `CONFIRMED_OWN_FILL` (forbidden in offline replay).
- 3-Unit Exact Integer Math ONLY (`price_pips` = $0.0001, `qty_centi` = 0.01 contracts,
  `micro_dollars` = $0.000001). ZERO `float()` calls anywhere in this module.
- Fail-closed tape integrity verification via `verify_v2_tape_manifest` before replay.
- Recompute derived book values (`best_yes_bid_pips`, `best_yes_ask_pips = 10000 - best_no_bid_pips`,
  `spread_pips`) directly from raw payload fields rather than trusting stored derived fields.
- 100% deterministic: identical inputs produce byte-identical outputs and SHA-256 hashes.
"""
from __future__ import annotations

import bisect
import calendar
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.adapters.collector_v2 import (
    CENTI_PER_CONTRACT,
    DEFAULT_CQP_CONFIG,
    INT64_MAX,
    INT64_MIN,
    PIPS_PER_CENT,
    PIPS_PER_DOLLAR,
    RECORD_TYPES,
    SCHEMA_VERSION_V2,
    compute_micro_dollars,
    is_uniform_1c_grid_10_90,
    parse_price_pips,
    parse_qty_centi,
    verify_v2_tape_manifest,
)

# ---------------------------------------------------------------------------
# Constants (Exact int64 units — ZERO floats)
# ---------------------------------------------------------------------------

NS_PER_SECOND = 1_000_000_000
NS_PER_MILLISECOND = 1_000_000
NS_PER_MINUTE = 60 * NS_PER_SECOND
NS_PER_HOUR = 3600 * NS_PER_SECOND
NS_PER_DAY = 86_400 * NS_PER_SECOND

MIN_LATENCY_L_NS = 2 * NS_PER_SECOND  # L = max(2_000_000_000 ns, p99_rtt_ns)
MICRO_DOLLARS_PER_CENT = 10_000  # $0.01 = 10,000 micro-dollars
KALSHI_FEE_DENOMINATOR = 1_000_000_000_000  # 10^12 for bps * qty_centi * p * (10000 - p) -> cents
DEFAULT_MAKER_FEE_BPS = 0  # v1 scope: uniform 1c-grid, zero-maker-fee Kalshi series
DEFAULT_TAKER_FEE_BPS = 700  # 7.00% Kalshi taker formula coefficient
MARKOUT_HORIZONS_MINUTES: Tuple[int, ...] = (1, 5, 15, 60)
EARLY_EXIT_PROFIT_TARGET_PIPS = 500  # +5c executable bid-side profit target

BENCHMARK_ONLY_CLASSIFICATION = "BENCHMARK_ONLY"
SHORT_HORIZON_CRYPTO_CATEGORY = "SHORT_HORIZON_CRYPTO"


# ---------------------------------------------------------------------------
# 6-Tier Evidence Taxonomy (Brief #01)
# ---------------------------------------------------------------------------


class EvidenceTier(str, Enum):
    """Ratified 6-tier evidence taxonomy for microstructure observation and replay."""

    OBSERVED_L2 = "OBSERVED_L2"
    OBSERVED_TRADE = "OBSERVED_TRADE"
    TOUCH_ONLY = "TOUCH_ONLY"
    TRADE_THROUGH_EVIDENCE = "TRADE_THROUGH_EVIDENCE"
    QUEUE_CONDITIONAL_BOUND = "QUEUE_CONDITIONAL_BOUND"
    CONFIRMED_OWN_FILL = "CONFIRMED_OWN_FILL"


OFFLINE_ALLOWED_FILL_TIERS = frozenset(
    {
        EvidenceTier.TRADE_THROUGH_EVIDENCE,
        EvidenceTier.QUEUE_CONDITIONAL_BOUND,
    }
)


class TapeIntegrityError(ValueError):
    """Fail-closed exception raised on manifest tamper, float injection, or unhandled parse errors."""


def assert_offline_evidence_tier(tier: EvidenceTier) -> EvidenceTier:
    """Reject CONFIRMED_OWN_FILL anywhere in offline replay (Brief #01 zero-synthetic invariant)."""
    if not isinstance(tier, EvidenceTier):
        raise TypeError(f"Expected EvidenceTier, got {type(tier).__name__}")
    if tier == EvidenceTier.CONFIRMED_OWN_FILL:
        raise ValueError(
            "CONFIRMED_OWN_FILL is strictly forbidden in offline replay; "
            "public prints may never be promoted to confirmed own fills."
        )
    return tier


# ---------------------------------------------------------------------------
# Exact Integer Helpers (ZERO float())
# ---------------------------------------------------------------------------


def _require_int64(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TapeIntegrityError(f"{label} must be strict int, got {type(value).__name__}")
    if value < INT64_MIN or value > INT64_MAX:
        raise TapeIntegrityError(f"{label} overflows int64: {value}")
    return value


def parse_utc_iso_to_ns(raw: Any, *, label: str = "timestamp") -> int:
    """Parse an ISO-8601 UTC string into exact int64 Unix epoch nanoseconds without float()."""
    if not isinstance(raw, str) or not raw.strip():
        raise TapeIntegrityError(f"Missing or non-string UTC timestamp for {label}: {raw!r}")
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise TapeIntegrityError(f"Malformed ISO-8601 timestamp for {label}: {raw!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    epoch_sec = calendar.timegm(dt.utctimetuple())
    return _require_int64(epoch_sec * NS_PER_SECOND + dt.microsecond * 1_000, label)


def compute_p99_ns(samples_ns: Sequence[int]) -> int:
    """Compute exact integer 99th percentile (ceiling order statistic) of non-negative ns samples."""
    valid = sorted(s for s in samples_ns if isinstance(s, int) and not isinstance(s, bool) and s >= 0)
    if not valid:
        return 0
    n = len(valid)
    # Ceiling index: ceil(0.99 * n) - 1 = (99 * n + 99) // 100 - 1
    idx = (99 * n + 99) // 100 - 1
    if idx < 0:
        idx = 0
    elif idx >= n:
        idx = n - 1
    return valid[idx]


def compute_cent_rounded_fee_micro(
    fee_bps: int,
    qty_centi: int,
    price_pips: int,
) -> int:
    """Compute exact cent-rounded fee in micro-dollars (round UP to whole cent; ignore refunds).

    Kalshi binary fee formula:
        fee_dollars = (fee_bps / 10_000) * (qty_centi / 100) * (price_pips / 10_000) * ((10_000 - price_pips) / 10_000)
        fee_cents_exact = fee_bps * qty_centi * price_pips * (10_000 - price_pips) / 10^12
        fee_cents_rounded = ceil(fee_cents_exact)
        fee_micro_dollars = fee_cents_rounded * 10_000
    """
    _require_int64(fee_bps, "fee_bps")
    _require_int64(qty_centi, "qty_centi")
    _require_int64(price_pips, "price_pips")
    if fee_bps <= 0 or qty_centi <= 0 or price_pips <= 0 or price_pips >= PIPS_PER_DOLLAR:
        return 0
    num = fee_bps * qty_centi * price_pips * (PIPS_PER_DOLLAR - price_pips)
    fee_cents = (num + KALSHI_FEE_DENOMINATOR - 1) // KALSHI_FEE_DENOMINATOR
    return _require_int64(fee_cents * MICRO_DOLLARS_PER_CENT, "fee_micro_dollars")


def derive_event_cluster_id(contract_ticker: str, explicit_event_ticker: Optional[str] = None) -> str:
    """Deterministically resolve the event cluster ID so correlated strikes never split."""
    if explicit_event_ticker and isinstance(explicit_event_ticker, str) and explicit_event_ticker.strip():
        return explicit_event_ticker.strip().upper()
    tk = contract_ticker.strip().upper()
    parts = tk.split("-")
    if len(parts) >= 3:
        return "-".join(parts[:-1])
    return tk


def derive_series_ticker(contract_ticker: str, explicit_series_ticker: Optional[str] = None) -> str:
    """Deterministically resolve the series ticker from metadata or Kalshi ticker prefix."""
    if explicit_series_ticker and isinstance(explicit_series_ticker, str) and explicit_series_ticker.strip():
        return explicit_series_ticker.strip().upper()
    tk = contract_ticker.strip().upper()
    parts = tk.split("-")
    return parts[0] if parts else tk


def _infer_category_from_ticker(contract_ticker: str, series_ticker: str) -> Optional[str]:
    allowlist: Dict[str, List[str]] = DEFAULT_CQP_CONFIG.get("series_allowlist") or {}
    priority_order: List[str] = list(DEFAULT_CQP_CONFIG.get("priority_order") or [])
    tk_u = contract_ticker.strip().upper()
    ser_u = series_ticker.strip().upper()
    for cat in priority_order:
        for pref in allowlist.get(cat) or []:
            pu = pref.upper()
            if tk_u.startswith(pu) or ser_u.startswith(pu):
                return cat
    return None


def _is_crypto_or_benchmark(
    venue: str,
    category: Optional[str],
    classification: str,
    contract_ticker: str,
    series_ticker: str,
) -> bool:
    """Enforce Brief #01 guardrail: short-horizon Crypto and BENCHMARK_ONLY are never Strategy D eligible."""
    if venue.strip().upper() != "KALSHI":
        return True
    if classification.strip().upper() in {BENCHMARK_ONLY_CLASSIFICATION, "BROAD_BASELINE", "REJECTED"}:
        return True
    cat_u = (category or "").strip().upper()
    if cat_u == SHORT_HORIZON_CRYPTO_CATEGORY:
        return True
    inferred = _infer_category_from_ticker(contract_ticker, series_ticker)
    if inferred == SHORT_HORIZON_CRYPTO_CATEGORY:
        return True
    return False


# ---------------------------------------------------------------------------
# Core Data Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BookLevelV2:
    price_raw: str
    price_pips: int
    qty_raw: str
    qty_centi: int
    micro_dollars: int
    exact_cent: bool
    fractional_quantity_flag: bool


@dataclass(frozen=True)
class ObservedL2Snapshot:
    venue: str
    contract_ticker: str
    capture_sequence: int
    t_req_sent_ns: int
    t_resp_recv_ns: int
    captured_at_utc: str
    captured_at_ns: int
    yes_bids: Tuple[BookLevelV2, ...]
    yes_asks: Tuple[BookLevelV2, ...]
    yes_bid_depth_by_price: Dict[int, int]
    yes_ask_depth_by_price: Dict[int, int]
    best_yes_bid_pips: Optional[int]
    best_yes_bid_qty_centi: int
    best_no_bid_pips: Optional[int]
    best_yes_ask_pips: Optional[int]
    best_yes_ask_qty_centi: int
    spread_pips: Optional[int]
    book_quarantined: bool
    quarantine_reason: Optional[str]
    uniform_1c_grid_10_90: bool
    exact_cent_eligible: bool
    category: Optional[str]
    classification: str
    post_settlement_snapshot: bool
    stored_derived_discrepancy: bool
    evidence_tier: EvidenceTier = EvidenceTier.OBSERVED_L2


@dataclass(frozen=True)
class ObservedTradePrint:
    venue: str
    trade_id: str
    contract_ticker: str
    yes_price_pips: int
    no_price_pips: int
    count_centi: int
    micro_dollars: int
    taker_side: str
    is_block_trade: bool
    trade_ts_ns: int
    t_req_sent_ns: int
    t_resp_recv_ns: int
    window_min_ts: int
    window_max_ts: int
    window_completeness_status: str
    evidence_tier: EvidenceTier = EvidenceTier.OBSERVED_TRADE


@dataclass(frozen=True)
class ContractMetaV2:
    contract_ticker: str
    event_cluster_id: str
    series_ticker: str
    venue: str
    category: Optional[str]
    classification: str
    close_time_utc: Optional[str]
    close_time_ns: Optional[int]
    uniform_1c_grid_10_90: bool
    maker_fee_bps: int = DEFAULT_MAKER_FEE_BPS


@dataclass(frozen=True)
class SettlementEventV2:
    contract_ticker: str
    settlement_result: Optional[str]
    settlement_value_pips: Optional[int]
    settled_at_utc: str
    settled_at_ns: int


@dataclass(frozen=True)
class CensorIntervalV2:
    source: str
    start_ns: int
    end_ns: int
    affected_tickers: frozenset[str]
    reason: str


@dataclass(frozen=True)
class LoadedTapeV2:
    tape_dir: str
    session_manifests: Tuple[Dict[str, Any], ...]
    combined_manifest_sha256: str
    first_captured_at_utc: Optional[str]
    last_captured_at_utc: Optional[str]
    first_captured_at_ns: int
    last_captured_at_ns: int
    total_records: int
    unexplained_parse_rejects: int
    derived_discrepancy_count: int
    p99_rtt_ns: int
    latency_l_ns: int
    contracts: Dict[str, ContractMetaV2]
    l2_by_ticker: Dict[str, Tuple[ObservedL2Snapshot, ...]]
    trades_by_ticker: Dict[str, Tuple[ObservedTradePrint, ...]]
    settlements: Dict[str, SettlementEventV2]
    censor_intervals: Tuple[CensorIntervalV2, ...]


@dataclass(frozen=True)
class SimulatedFillRecord:
    bound: str  # "lb" | "mid" | "ub"
    trade_id: str
    fill_ts_ns: int
    fill_price_pips: int
    print_price_pips: int
    fill_qty_centi: int
    evidence_tier: EvidenceTier
    fee_micro_dollars: int


@dataclass(frozen=True)
class OrderEpisodeResult:
    episode_id: str
    contract_ticker: str
    event_cluster_id: str
    series_ticker: str
    category: str
    decision_ts_ns: int
    t_live_ns: int
    t_cancel_ns: int
    duration_ns: int
    hours_to_close_bucket: str
    proposed_bid_pips: int
    order_qty_centi: int
    status: str  # "ACTIVE_EVALUATED" | "POST_ONLY_REJECTED" | "CENSORED" | "EXPIRED_BEFORE_LIVE"
    post_only_rejected: bool
    crossed_order: bool
    censored: bool
    censor_reasons: Tuple[str, ...]
    settled: bool
    settlement_value_pips: Optional[int]
    early_exit_triggered: bool
    exit_valuation_pips_lb: int
    exit_valuation_pips_mid: int
    exit_valuation_pips_ub: int
    start_q_lb_centi: int
    start_q_mid_centi: int
    start_q_ub_centi: int
    touch_only_events: int
    filled_qty_lb_centi: int
    filled_qty_mid_centi: int
    filled_qty_ub_centi: int
    fills_lb: Tuple[SimulatedFillRecord, ...]
    fills_mid: Tuple[SimulatedFillRecord, ...]
    fills_ub: Tuple[SimulatedFillRecord, ...]
    citing_trade_ids_lb: Tuple[str, ...]
    citing_trade_ids_mid: Tuple[str, ...]
    citing_trade_ids_ub: Tuple[str, ...]
    gross_pnl_lb_micro: int
    gross_pnl_mid_micro: int
    gross_pnl_ub_micro: int
    fee_lb_micro: int
    fee_mid_micro: int
    fee_ub_micro: int
    net_pnl_lb_micro: int
    net_pnl_mid_micro: int
    net_pnl_ub_micro: int
    pi_l_micro: int


# ---------------------------------------------------------------------------
# 1. Schema 2.0.0 Tape Loader (Fail-Closed & Recomputed Derived Book Fields)
# ---------------------------------------------------------------------------


def _reject_json_float(raw: str) -> Any:
    raise TapeIntegrityError(f"Prohibited floating-point literal in Schema 2.0.0 tape: {raw!r}")


def _recompute_l2_snapshot(
    rec: Dict[str, Any],
    *,
    contract_meta: Optional[ContractMetaV2],
) -> ObservedL2Snapshot:
    """Recompute derived book values strictly from raw payload fields without trusting stored derived values."""
    venue = str(rec.get("venue") or "").strip().upper()
    ticker = str(rec.get("contract_ticker") or "").strip()
    if not venue or not ticker:
        raise TapeIntegrityError(f"OBSERVED_L2 missing venue or contract_ticker: {rec!r}")

    capture_seq = _require_int64(rec.get("capture_sequence"), "capture_sequence")
    t_req_sent_ns = _require_int64(rec.get("t_req_sent_ns"), "t_req_sent_ns")
    t_resp_recv_ns = _require_int64(rec.get("t_resp_recv_ns"), "t_resp_recv_ns")
    captured_at_utc = str(rec.get("captured_at_utc") or "")
    captured_at_ns = parse_utc_iso_to_ns(captured_at_utc, label="captured_at_utc")

    yes_bid_depth: Dict[int, int] = {}
    yes_bid_levels: List[BookLevelV2] = []
    no_bid_depth: Dict[int, int] = {}
    yes_ask_depth: Dict[int, int] = {}
    yes_ask_levels: List[BookLevelV2] = []

    if isinstance(rec.get("orderbook_fp"), dict):
        # Raw Kalshi orderbook_fp payload directly embedded
        ob_fp = rec["orderbook_fp"]
        for entry in ob_fp.get("yes_dollars") or []:
            p_raw, p_pips = parse_price_pips(entry[0], input_unit="dollars", allow_zero=False, allow_dollar_one=False)
            q_raw, q_centi, frac = parse_qty_centi(entry[1])
            if q_centi <= 0:
                continue
            micro = compute_micro_dollars(p_pips, q_centi)
            yes_bid_depth[p_pips] = yes_bid_depth.get(p_pips, 0) + q_centi
            yes_bid_levels.append(
                BookLevelV2(p_raw, p_pips, q_raw, q_centi, micro, (p_pips % PIPS_PER_CENT) == 0, frac)
            )
        for entry in ob_fp.get("no_dollars") or []:
            np_raw, np_pips = parse_price_pips(entry[0], input_unit="dollars", allow_zero=False, allow_dollar_one=False)
            q_raw, q_centi, frac = parse_qty_centi(entry[1])
            if q_centi <= 0:
                continue
            no_bid_depth[np_pips] = no_bid_depth.get(np_pips, 0) + q_centi
            ask_pips = PIPS_PER_DOLLAR - np_pips
            micro = compute_micro_dollars(ask_pips, q_centi)
            yes_ask_depth[ask_pips] = yes_ask_depth.get(ask_pips, 0) + q_centi
            yes_ask_levels.append(
                BookLevelV2(
                    f"{ask_pips // PIPS_PER_DOLLAR}.{ask_pips % PIPS_PER_DOLLAR:04d}",
                    ask_pips,
                    q_raw,
                    q_centi,
                    micro,
                    (ask_pips % PIPS_PER_CENT) == 0,
                    frac,
                )
            )
    else:
        raw_yes_bids = rec.get("yes_bids")
        raw_yes_asks = rec.get("yes_asks")
        raw_no_bids = rec.get("no_bids")
        if raw_yes_bids is None or not isinstance(raw_yes_bids, list):
            raise TapeIntegrityError(f"OBSERVED_L2 missing yes_bids list on seq={capture_seq}")
        if raw_yes_asks is None or not isinstance(raw_yes_asks, list):
            raise TapeIntegrityError(f"OBSERVED_L2 missing yes_asks list on seq={capture_seq}")

        for lv in raw_yes_bids:
            if not isinstance(lv, dict):
                raise TapeIntegrityError(f"Malformed yes_bids entry on seq={capture_seq}")
            if "price_raw" not in lv or "qty_raw" not in lv:
                raise TapeIntegrityError(f"yes_bids entry missing raw fields on seq={capture_seq}")
            raw_p = lv["price_raw"]
            unit = "dollars" if (isinstance(raw_p, str) and "." in raw_p) else "cents"
            p_raw, p_pips = parse_price_pips(raw_p, input_unit=unit, allow_zero=False, allow_dollar_one=False)
            q_raw, q_centi, frac = parse_qty_centi(lv["qty_raw"], truncate_sub_centi=(venue != "KALSHI"))
            if q_centi <= 0:
                continue
            micro = compute_micro_dollars(p_pips, q_centi)
            if "micro_dollars" in lv and lv["micro_dollars"] != micro:
                raise TapeIntegrityError(f"yes_bids micro_dollars mismatch on seq={capture_seq}")
            yes_bid_depth[p_pips] = yes_bid_depth.get(p_pips, 0) + q_centi
            yes_bid_levels.append(
                BookLevelV2(p_raw, p_pips, q_raw, q_centi, micro, (p_pips % PIPS_PER_CENT) == 0, frac)
            )

        if isinstance(raw_no_bids, list) and raw_no_bids:
            for lv in raw_no_bids:
                if not isinstance(lv, dict) or "price_raw" not in lv or "qty_raw" not in lv:
                    raise TapeIntegrityError(f"Malformed no_bids entry on seq={capture_seq}")
                raw_np = lv["price_raw"]
                unit = "dollars" if (isinstance(raw_np, str) and "." in raw_np) else "cents"
                _, np_pips = parse_price_pips(raw_np, input_unit=unit, allow_zero=False, allow_dollar_one=False)
                q_raw, q_centi, frac = parse_qty_centi(lv["qty_raw"], truncate_sub_centi=(venue != "KALSHI"))
                if q_centi <= 0:
                    continue
                no_bid_depth[np_pips] = no_bid_depth.get(np_pips, 0) + q_centi
                ask_pips = PIPS_PER_DOLLAR - np_pips
                micro = compute_micro_dollars(ask_pips, q_centi)
                yes_ask_depth[ask_pips] = yes_ask_depth.get(ask_pips, 0) + q_centi
                yes_ask_levels.append(
                    BookLevelV2(
                        f"{ask_pips // PIPS_PER_DOLLAR}.{ask_pips % PIPS_PER_DOLLAR:04d}",
                        ask_pips,
                        q_raw,
                        q_centi,
                        micro,
                        (ask_pips % PIPS_PER_CENT) == 0,
                        frac,
                    )
                )
        else:
            for lv in raw_yes_asks:
                if not isinstance(lv, dict) or "qty_raw" not in lv:
                    raise TapeIntegrityError(f"Malformed yes_asks entry on seq={capture_seq}")
                q_raw, q_centi, frac = parse_qty_centi(lv["qty_raw"], truncate_sub_centi=(venue != "KALSHI"))
                if q_centi <= 0:
                    continue
                if venue == "KALSHI" and lv.get("no_bid_price_raw") is not None:
                    raw_np = lv["no_bid_price_raw"]
                    unit = "dollars" if (isinstance(raw_np, str) and "." in raw_np) else "cents"
                    _, np_pips = parse_price_pips(raw_np, input_unit=unit, allow_zero=False, allow_dollar_one=False)
                    no_bid_depth[np_pips] = no_bid_depth.get(np_pips, 0) + q_centi
                    ask_pips = PIPS_PER_DOLLAR - np_pips
                    p_raw = f"{ask_pips // PIPS_PER_DOLLAR}.{ask_pips % PIPS_PER_DOLLAR:04d}"
                else:
                    if "price_raw" not in lv:
                        raise TapeIntegrityError(f"yes_asks entry missing price_raw on seq={capture_seq}")
                    raw_ap = lv["price_raw"]
                    unit = "dollars" if (isinstance(raw_ap, str) and "." in raw_ap) else "cents"
                    p_raw, ask_pips = parse_price_pips(raw_ap, input_unit=unit, allow_zero=False, allow_dollar_one=False)
                    if venue == "KALSHI":
                        np_pips = PIPS_PER_DOLLAR - ask_pips
                        no_bid_depth[np_pips] = no_bid_depth.get(np_pips, 0) + q_centi
                micro = compute_micro_dollars(ask_pips, q_centi)
                yes_ask_depth[ask_pips] = yes_ask_depth.get(ask_pips, 0) + q_centi
                yes_ask_levels.append(
                    BookLevelV2(p_raw, ask_pips, q_raw, q_centi, micro, (ask_pips % PIPS_PER_CENT) == 0, frac)
                )

    yes_bid_levels.sort(key=lambda lv: lv.price_pips, reverse=True)
    yes_ask_levels.sort(key=lambda lv: lv.price_pips)

    # Recompute derived top-of-book strictly from raw levels (NEVER trust stored derived fields)
    best_yes_bid_pips: Optional[int] = max(yes_bid_depth.keys()) if yes_bid_depth else None
    best_yes_bid_qty_centi: int = yes_bid_depth[best_yes_bid_pips] if best_yes_bid_pips is not None else 0

    best_no_bid_pips: Optional[int] = max(no_bid_depth.keys()) if no_bid_depth else None
    if venue == "KALSHI":
        best_yes_ask_pips: Optional[int] = (
            (PIPS_PER_DOLLAR - best_no_bid_pips) if best_no_bid_pips is not None else None
        )
    else:
        best_yes_ask_pips = min(yes_ask_depth.keys()) if yes_ask_depth else None
    best_yes_ask_qty_centi: int = yes_ask_depth[best_yes_ask_pips] if best_yes_ask_pips is not None else 0

    spread_pips: Optional[int] = None
    book_quarantined = False
    quarantine_reason: Optional[str] = None
    if best_yes_bid_pips is not None and best_yes_ask_pips is not None:
        spread_pips = best_yes_ask_pips - best_yes_bid_pips
        if spread_pips == 0:
            book_quarantined = True
            quarantine_reason = "LOCKED_BOOK"
        elif spread_pips < 0:
            book_quarantined = True
            quarantine_reason = "CROSSED_BOOK"

    all_levels = yes_bid_levels + yes_ask_levels
    if contract_meta is not None:
        uniform_1c_grid = contract_meta.uniform_1c_grid_10_90
    elif "uniform_1c_grid_10_90" in rec:
        uniform_1c_grid = bool(rec["uniform_1c_grid_10_90"])
    else:
        uniform_1c_grid = True
    all_exact_cent = all(lv.exact_cent for lv in all_levels) if all_levels else False
    exact_cent_eligible = bool(all_exact_cent and uniform_1c_grid)

    stored_discrepancy = (
        ("best_yes_bid_pips" in rec and rec["best_yes_bid_pips"] != best_yes_bid_pips)
        or ("best_yes_ask_pips" in rec and rec["best_yes_ask_pips"] != best_yes_ask_pips)
        or ("spread_pips" in rec and rec["spread_pips"] != spread_pips)
        or (venue == "KALSHI" and "best_no_bid_pips" in rec and rec["best_no_bid_pips"] != best_no_bid_pips)
    )

    category = rec.get("category") or (contract_meta.category if contract_meta else None)
    classification = str(
        rec.get("classification")
        or (contract_meta.classification if contract_meta else "OBSERVATION_ONLY")
    )
    post_settlement = bool(rec.get("post_settlement_snapshot", False))

    return ObservedL2Snapshot(
        venue=venue,
        contract_ticker=ticker,
        capture_sequence=capture_seq,
        t_req_sent_ns=t_req_sent_ns,
        t_resp_recv_ns=t_resp_recv_ns,
        captured_at_utc=captured_at_utc,
        captured_at_ns=captured_at_ns,
        yes_bids=tuple(yes_bid_levels),
        yes_asks=tuple(yes_ask_levels),
        yes_bid_depth_by_price=yes_bid_depth,
        yes_ask_depth_by_price=yes_ask_depth,
        best_yes_bid_pips=best_yes_bid_pips,
        best_yes_bid_qty_centi=best_yes_bid_qty_centi,
        best_no_bid_pips=best_no_bid_pips,
        best_yes_ask_pips=best_yes_ask_pips,
        best_yes_ask_qty_centi=best_yes_ask_qty_centi,
        spread_pips=spread_pips,
        book_quarantined=book_quarantined,
        quarantine_reason=quarantine_reason,
        uniform_1c_grid_10_90=uniform_1c_grid,
        exact_cent_eligible=exact_cent_eligible,
        category=str(category) if category is not None else None,
        classification=classification,
        post_settlement_snapshot=post_settlement,
        stored_derived_discrepancy=stored_discrepancy,
        evidence_tier=EvidenceTier.OBSERVED_L2,
    )


def _recompute_trade_print(rec: Dict[str, Any]) -> ObservedTradePrint:
    """Parse and validate an OBSERVED_TRADE record strictly from raw fields."""
    venue = str(rec.get("venue") or "").strip().upper()
    trade_id = str(rec.get("trade_id") or "").strip()
    ticker = str(rec.get("contract_ticker") or "").strip()
    if not venue or not trade_id or not ticker:
        raise TapeIntegrityError(f"OBSERVED_TRADE missing venue/trade_id/contract_ticker: {rec!r}")

    if "yes_price_raw" in rec and rec["yes_price_raw"] is not None:
        raw_yp = rec["yes_price_raw"]
        unit = "dollars" if (isinstance(raw_yp, str) and "." in raw_yp) else "cents"
        _, yes_price_pips = parse_price_pips(raw_yp, input_unit=unit, allow_zero=True, allow_dollar_one=True)
    else:
        yes_price_pips = _require_int64(rec.get("yes_price_pips"), "yes_price_pips")

    no_price_pips = PIPS_PER_DOLLAR - yes_price_pips

    if "count_raw" in rec and rec["count_raw"] is not None:
        _, count_centi, _ = parse_qty_centi(rec["count_raw"])
    else:
        count_centi = _require_int64(rec.get("count_centi"), "count_centi")

    if count_centi < 0:
        raise TapeIntegrityError(f"Negative count_centi on trade {trade_id!r}")

    micro = compute_micro_dollars(yes_price_pips, count_centi)
    if "micro_dollars" in rec and rec["micro_dollars"] != micro:
        raise TapeIntegrityError(f"Trade {trade_id!r} violated exact 3-unit identity")

    taker_side = str(rec.get("taker_side") or "unknown").strip().lower() or "unknown"
    is_block = bool(rec.get("is_block_trade", False))
    t_req_sent_ns = _require_int64(rec.get("t_req_sent_ns"), "t_req_sent_ns")
    t_resp_recv_ns = _require_int64(rec.get("t_resp_recv_ns"), "t_resp_recv_ns")

    if rec.get("created_time"):
        trade_ts_ns = parse_utc_iso_to_ns(rec["created_time"], label="created_time")
    else:
        trade_ts_ns = t_resp_recv_ns

    w_min = _require_int64(rec.get("window_min_ts", 0), "window_min_ts")
    w_max = _require_int64(rec.get("window_max_ts", 0), "window_max_ts")
    w_status = str(rec.get("window_completeness_status") or "COMPLETE").strip().upper()

    return ObservedTradePrint(
        venue=venue,
        trade_id=trade_id,
        contract_ticker=ticker,
        yes_price_pips=yes_price_pips,
        no_price_pips=no_price_pips,
        count_centi=count_centi,
        micro_dollars=micro,
        taker_side=taker_side,
        is_block_trade=is_block,
        trade_ts_ns=trade_ts_ns,
        t_req_sent_ns=t_req_sent_ns,
        t_resp_recv_ns=t_resp_recv_ns,
        window_min_ts=w_min,
        window_max_ts=w_max,
        window_completeness_status=w_status,
        evidence_tier=EvidenceTier.OBSERVED_TRADE,
    )


def discover_v2_manifests(tape_dir: Path) -> List[Path]:
    """Deterministically discover Schema 2.0.0 tape_manifest.json file(s) under tape_dir."""
    root = Path(tape_dir)
    if not root.exists():
        raise TapeIntegrityError(f"Tape directory does not exist: {root}")
    direct = root / "tape_manifest.json"
    if direct.is_file():
        return [direct]
    found = sorted(root.rglob("tape_manifest.json"), key=lambda p: p.as_posix())
    if not found:
        raise TapeIntegrityError(f"No tape_manifest.json found under {root}")
    return found


def load_v2_tape(tape_dir: Path) -> LoadedTapeV2:
    """Verify Schema 2.0.0 tape integrity fail-closed and load all records with recomputed derived fields."""
    manifest_paths = discover_v2_manifests(tape_dir)

    verified_manifests: List[Dict[str, Any]] = []
    manifest_pairs: List[Tuple[str, str]] = []

    contracts_mut: Dict[str, Dict[str, Any]] = {}
    l2_raw_by_ticker: Dict[str, List[Tuple[Dict[str, Any], int]]] = {}
    trades_dedup: Dict[str, ObservedTradePrint] = {}
    settlements: Dict[str, SettlementEventV2] = {}
    censor_intervals: List[CensorIntervalV2] = []
    rtt_samples_ns: List[int] = []

    total_records = 0
    global_seq_offset = 0
    first_ts_utc: Optional[str] = None
    last_ts_utc: Optional[str] = None
    first_ts_ns: Optional[int] = None
    last_ts_ns: Optional[int] = None

    for mpath in manifest_paths:
        try:
            manifest = verify_v2_tape_manifest(mpath)
        except Exception as exc:
            raise TapeIntegrityError(f"Manifest integrity check failed for {mpath}: {exc}") from exc

        verified_manifests.append(manifest)
        rel_name = mpath.parent.relative_to(Path(tape_dir)).as_posix() if mpath.parent != Path(tape_dir) else "."
        manifest_pairs.append((rel_name, str(manifest["tape_manifest_sha256"])))

        tape_file = mpath.parent / str(manifest["tape_file"])
        if not tape_file.is_file():
            raise TapeIntegrityError(f"Missing tape file referenced by manifest: {tape_file}")

        max_seq_in_file = 0
        with tape_file.open("rb") as fh:
            for line_idx, raw_line in enumerate(fh):
                if not raw_line.strip():
                    continue
                try:
                    rec = json.loads(raw_line.decode("utf-8"), parse_float=_reject_json_float)
                except TapeIntegrityError:
                    raise
                except Exception as exc:
                    raise TapeIntegrityError(f"JSON parse error at {tape_file}:{line_idx}: {exc}") from exc

                if rec.get("schema_version") != SCHEMA_VERSION_V2:
                    raise TapeIntegrityError(f"Schema version mismatch at {tape_file}:{line_idx}")
                if rec.get("synthetic_fills_present") is not False:
                    raise TapeIntegrityError(f"Zero-synthetic violation at {tape_file}:{line_idx}")

                rt = rec.get("record_type")
                if rt not in RECORD_TYPES:
                    raise TapeIntegrityError(f"Unknown record_type {rt!r} at {tape_file}:{line_idx}")

                total_records += 1
                seq = _require_int64(rec.get("capture_sequence"), "capture_sequence")
                if seq > max_seq_in_file:
                    max_seq_in_file = seq

                t_sent = _require_int64(rec.get("t_req_sent_ns"), "t_req_sent_ns")
                t_recv = _require_int64(rec.get("t_resp_recv_ns"), "t_resp_recv_ns")
                if t_recv >= t_sent:
                    rtt_samples_ns.append(t_recv - t_sent)

                cap_utc = str(rec.get("captured_at_utc") or "")
                cap_ns = parse_utc_iso_to_ns(cap_utc, label="captured_at_utc")
                if first_ts_ns is None or cap_ns < first_ts_ns:
                    first_ts_ns = cap_ns
                    first_ts_utc = cap_utc
                if last_ts_ns is None or cap_ns > last_ts_ns:
                    last_ts_ns = cap_ns
                    last_ts_utc = cap_utc

                if rt == "MARKET_META":
                    tk = str(rec.get("contract_ticker") or "").strip()
                    if not tk:
                        raise TapeIntegrityError(f"MARKET_META missing contract_ticker at line {line_idx}")
                    pr = rec.get("price_ranges")
                    if isinstance(pr, list) and pr:
                        u1c = is_uniform_1c_grid_10_90(pr)
                    else:
                        u1c = bool(rec.get("uniform_1c_grid_10_90", True))
                    close_utc = rec.get("close_time_utc")
                    close_ns = parse_utc_iso_to_ns(close_utc, label="close_time_utc") if close_utc else None
                    series_tk = derive_series_ticker(tk, rec.get("series_ticker"))
                    event_id = derive_event_cluster_id(tk, rec.get("event_ticker"))
                    cat = rec.get("category") or _infer_category_from_ticker(tk, series_tk)
                    maker_fee_bps = _require_int64(
                        rec.get("maker_fee_bps", DEFAULT_MAKER_FEE_BPS), "maker_fee_bps"
                    )
                    contracts_mut[tk] = {
                        "contract_ticker": tk,
                        "event_cluster_id": event_id,
                        "series_ticker": series_tk,
                        "venue": str(rec.get("venue") or "KALSHI").strip().upper(),
                        "category": str(cat) if cat is not None else None,
                        "classification": str(rec.get("classification") or "CURATED_STRATEGY_D_CANDIDATE"),
                        "close_time_utc": str(close_utc) if close_utc else None,
                        "close_time_ns": close_ns,
                        "uniform_1c_grid_10_90": u1c,
                        "maker_fee_bps": maker_fee_bps,
                    }

                elif rt == "QUALIFICATION_DECISION":
                    tk = str(rec.get("contract_ticker") or "").strip()
                    if tk and tk not in contracts_mut and rec.get("admitted") is True:
                        close_utc = rec.get("close_time_utc")
                        close_ns = parse_utc_iso_to_ns(close_utc, label="close_time_utc") if close_utc else None
                        series_tk = derive_series_ticker(tk, rec.get("series_ticker"))
                        event_id = derive_event_cluster_id(tk, rec.get("event_ticker"))
                        cat = rec.get("category") or _infer_category_from_ticker(tk, series_tk)
                        contracts_mut[tk] = {
                            "contract_ticker": tk,
                            "event_cluster_id": event_id,
                            "series_ticker": series_tk,
                            "venue": str(rec.get("venue") or "KALSHI").strip().upper(),
                            "category": str(cat) if cat is not None else None,
                            "classification": str(rec.get("classification") or "CURATED_STRATEGY_D_CANDIDATE"),
                            "close_time_utc": str(close_utc) if close_utc else None,
                            "close_time_ns": close_ns,
                            "uniform_1c_grid_10_90": bool(rec.get("uniform_1c_grid_10_90", True)),
                            "maker_fee_bps": DEFAULT_MAKER_FEE_BPS,
                        }

                elif rt == "OBSERVED_L2":
                    tk = str(rec.get("contract_ticker") or "").strip()
                    if not tk:
                        raise TapeIntegrityError(f"OBSERVED_L2 missing contract_ticker at line {line_idx}")
                    l2_raw_by_ticker.setdefault(tk, []).append((rec, global_seq_offset + seq))

                elif rt == "OBSERVED_TRADE":
                    tr = _recompute_trade_print(rec)
                    if tr.trade_id not in trades_dedup:
                        trades_dedup[tr.trade_id] = tr
                    if tr.window_completeness_status == "INCOMPLETE":
                        w_start_ns = (
                            tr.window_min_ts * NS_PER_SECOND if tr.window_min_ts > 0 else min(tr.t_req_sent_ns, tr.trade_ts_ns)
                        )
                        w_end_ns = (
                            tr.window_max_ts * NS_PER_SECOND if tr.window_max_ts > 0 else max(tr.t_resp_recv_ns, tr.trade_ts_ns)
                        )
                        censor_intervals.append(
                            CensorIntervalV2(
                                source="INCOMPLETE_TRADE_WINDOW",
                                start_ns=min(w_start_ns, w_end_ns),
                                end_ns=max(w_start_ns, w_end_ns),
                                affected_tickers=frozenset({tr.contract_ticker}),
                                reason="INCOMPLETE_TRADE_WINDOW",
                            )
                        )

                elif rt == "SETTLEMENT_EVENT":
                    tk = str(rec.get("contract_ticker") or "").strip()
                    if not tk:
                        raise TapeIntegrityError(f"SETTLEMENT_EVENT missing contract_ticker at line {line_idx}")
                    res_raw = rec.get("settlement_result")
                    norm_res = str(res_raw).strip().lower() if res_raw is not None else None
                    # Recompute settlement_value_pips directly from settlement_result when binary
                    if norm_res == "yes":
                        settle_pips: Optional[int] = PIPS_PER_DOLLAR
                    elif norm_res == "no":
                        settle_pips = 0
                    elif rec.get("settlement_value_pips") is not None:
                        settle_pips = _require_int64(rec["settlement_value_pips"], "settlement_value_pips")
                    else:
                        settle_pips = None
                    settled_utc = str(rec.get("settled_at_utc") or cap_utc)
                    settled_ns = parse_utc_iso_to_ns(settled_utc, label="settled_at_utc")
                    settlements[tk] = SettlementEventV2(
                        contract_ticker=tk,
                        settlement_result=norm_res,
                        settlement_value_pips=settle_pips,
                        settled_at_utc=settled_utc,
                        settled_at_ns=settled_ns,
                    )

                elif rt == "DATA_GAP":
                    affected = frozenset(
                        str(t).strip()
                        for t in (rec.get("affected_tickers") or [])
                        if isinstance(t, str) and t.strip()
                    )
                    gap_start_ns = (
                        parse_utc_iso_to_ns(rec["gap_start_utc"], label="gap_start_utc")
                        if rec.get("gap_start_utc")
                        else t_sent
                    )
                    gap_end_ns = (
                        parse_utc_iso_to_ns(rec["gap_end_utc"], label="gap_end_utc")
                        if rec.get("gap_end_utc")
                        else t_recv
                    )
                    backoff_ms = _require_int64(rec.get("backoff_ms", 0), "backoff_ms")
                    start_ns = min(t_sent, gap_start_ns)
                    end_ns = max(t_recv, gap_end_ns, t_recv + max(0, backoff_ms) * NS_PER_MILLISECOND)
                    censor_intervals.append(
                        CensorIntervalV2(
                            source="DATA_GAP",
                            start_ns=start_ns,
                            end_ns=end_ns,
                            affected_tickers=affected,
                            reason=str(rec.get("reason") or "DATA_GAP"),
                        )
                    )

        global_seq_offset += max_seq_in_file

    # Ensure every observed ticker has deterministic ContractMetaV2
    for tk, raw_list in sorted(l2_raw_by_ticker.items()):
        if tk not in contracts_mut:
            first_rec = raw_list[0][0]
            series_tk = derive_series_ticker(tk)
            event_id = derive_event_cluster_id(tk)
            cat = first_rec.get("category") or _infer_category_from_ticker(tk, series_tk)
            contracts_mut[tk] = {
                "contract_ticker": tk,
                "event_cluster_id": event_id,
                "series_ticker": series_tk,
                "venue": str(first_rec.get("venue") or "KALSHI").strip().upper(),
                "category": str(cat) if cat is not None else None,
                "classification": str(first_rec.get("classification") or "OBSERVATION_ONLY"),
                "close_time_utc": None,
                "close_time_ns": None,
                "uniform_1c_grid_10_90": bool(first_rec.get("uniform_1c_grid_10_90", True)),
                "maker_fee_bps": DEFAULT_MAKER_FEE_BPS,
            }

    contracts: Dict[str, ContractMetaV2] = {
        tk: ContractMetaV2(**meta_dict) for tk, meta_dict in sorted(contracts_mut.items())
    }

    # Recompute all OBSERVED_L2 snapshots using contract metadata
    l2_by_ticker: Dict[str, Tuple[ObservedL2Snapshot, ...]] = {}
    discrepancy_count = 0
    for tk, raw_list in sorted(l2_raw_by_ticker.items()):
        meta = contracts.get(tk)
        snaps: List[Tuple[int, int, ObservedL2Snapshot]] = []
        for raw_rec, global_seq in raw_list:
            snap = _recompute_l2_snapshot(raw_rec, contract_meta=meta)
            if snap.stored_derived_discrepancy:
                discrepancy_count += 1
            snaps.append((snap.t_resp_recv_ns, global_seq, snap))
        snaps.sort(key=lambda item: (item[0], item[1]))
        l2_by_ticker[tk] = tuple(item[2] for item in snaps)

    # Group and deterministically sort deduplicated OBSERVED_TRADE prints
    trades_grouped: Dict[str, List[ObservedTradePrint]] = {}
    for tr in trades_dedup.values():
        trades_grouped.setdefault(tr.contract_ticker, []).append(tr)
    trades_by_ticker: Dict[str, Tuple[ObservedTradePrint, ...]] = {}
    for tk, tr_list in sorted(trades_grouped.items()):
        tr_list.sort(key=lambda t: (t.trade_ts_ns, t.trade_id))
        trades_by_ticker[tk] = tuple(tr_list)

    censor_intervals.sort(key=lambda ci: (ci.start_ns, ci.end_ns, ci.source, ci.reason))

    p99_rtt_ns = compute_p99_ns(rtt_samples_ns)
    latency_l_ns = max(MIN_LATENCY_L_NS, p99_rtt_ns)

    if len(manifest_pairs) == 1:
        combined_sha = manifest_pairs[0][1]
    else:
        canonical = json.dumps(manifest_pairs, separators=(",", ":")).encode("utf-8")
        combined_sha = hashlib.sha256(canonical).hexdigest()

    return LoadedTapeV2(
        tape_dir=str(Path(tape_dir)),
        session_manifests=tuple(verified_manifests),
        combined_manifest_sha256=combined_sha,
        first_captured_at_utc=first_ts_utc,
        last_captured_at_utc=last_ts_utc,
        first_captured_at_ns=first_ts_ns or 0,
        last_captured_at_ns=last_ts_ns or 0,
        total_records=total_records,
        unexplained_parse_rejects=0,
        derived_discrepancy_count=discrepancy_count,
        p99_rtt_ns=p99_rtt_ns,
        latency_l_ns=latency_l_ns,
        contracts=contracts,
        l2_by_ticker=l2_by_ticker,
        trades_by_ticker=trades_by_ticker,
        settlements=settlements,
        censor_intervals=tuple(censor_intervals),
    )


# ---------------------------------------------------------------------------
# 2. Zero-Synthetic Maker Fill Engine (LB / MID / UB Bounds)
# ---------------------------------------------------------------------------


def _hours_to_close_bucket(decision_ts_ns: int, close_time_ns: Optional[int]) -> str:
    if close_time_ns is None or close_time_ns <= decision_ts_ns:
        return "unknown"
    rem_hours = (close_time_ns - decision_ts_ns) // NS_PER_HOUR
    if rem_hours < 6:
        return "0_6h"
    if rem_hours < 24:
        return "6_24h"
    if rem_hours < 72:
        return "24_72h"
    if rem_hours <= 168:
        return "72_168h"
    return "gt_168h"


def _overlapping_censor_reasons(
    ticker: str,
    start_ns: int,
    end_ns: int,
    censor_intervals: Sequence[CensorIntervalV2],
) -> Tuple[str, ...]:
    reasons: List[str] = []
    for ci in censor_intervals:
        if ci.affected_tickers and ticker not in ci.affected_tickers:
            continue
        if ci.start_ns <= end_ns and start_ns <= ci.end_ns:
            reasons.append(f"{ci.source}:{ci.reason}")
    return tuple(reasons)


def _taker_sell_volume_at_price(
    trades: Sequence[ObservedTradePrint],
    price_pips: int,
    after_ns: int,
    through_ns: int,
) -> int:
    """Exact sum of taker_side=='no' print volume at price_pips in (after_ns, through_ns]."""
    total = 0
    for tr in trades:
        if tr.trade_ts_ns <= after_ns:
            continue
        if tr.trade_ts_ns > through_ns:
            break
        if tr.taker_side == "no" and tr.yes_price_pips == price_pips:
            total += tr.count_centi
    return total


def _find_early_exit_bid(
    l2_snaps: Sequence[ObservedL2Snapshot],
    *,
    fill_ts_ns: int,
    latency_l_ns: int,
    entry_price_pips: int,
    settlement_ns: Optional[int],
) -> Optional[int]:
    """Executable bid-side early exit for `early_exit_5c` (>= +5c on observed best bid, never midpoint)."""
    earliest_exit_ns = fill_ts_ns + latency_l_ns
    target_bid = entry_price_pips + EARLY_EXIT_PROFIT_TARGET_PIPS
    for snap in l2_snaps:
        if snap.t_resp_recv_ns < earliest_exit_ns:
            continue
        if settlement_ns is not None and snap.t_resp_recv_ns >= settlement_ns:
            break
        if snap.book_quarantined or snap.post_settlement_snapshot:
            continue
        if snap.best_yes_bid_pips is not None and snap.best_yes_bid_qty_centi > 0:
            if snap.best_yes_bid_pips >= target_bid:
                return snap.best_yes_bid_pips
    return None


def _last_executable_bid_pips(l2_snaps: Sequence[ObservedL2Snapshot]) -> int:
    """Return last non-quarantined best_yes_bid_pips for unsettled mark-to-bid valuation (never midpoint)."""
    for snap in reversed(l2_snaps):
        if not snap.book_quarantined and snap.best_yes_bid_pips is not None:
            return snap.best_yes_bid_pips
    return 0


def simulate_order_episode(
    *,
    episode_id: str,
    contract_meta: ContractMetaV2,
    decision_snap_idx: int,
    cancel_snap_idx: Optional[int],
    proposed_bid_pips: int,
    order_qty_centi: int,
    l2_snaps: Sequence[ObservedL2Snapshot],
    trades: Sequence[ObservedTradePrint],
    settlement: Optional[SettlementEventV2],
    censor_intervals: Sequence[CensorIntervalV2],
    latency_l_ns: int,
    clock_offset_ns: int = 0,
    maker_fee_bps: Optional[int] = None,
    taker_fee_bps: int = DEFAULT_TAKER_FEE_BPS,
    exit_mode: str = "settlement_only",
    print_vol_remaining_lb: Optional[Dict[str, int]] = None,
    print_vol_remaining_mid: Optional[Dict[str, int]] = None,
    print_vol_remaining_ub: Optional[Dict[str, int]] = None,
) -> OrderEpisodeResult:
    """Simulate a single maker YES bid episode under LB / MID / UB queue bounds with ZERO synthetic fills."""
    _require_int64(proposed_bid_pips, "proposed_bid_pips")
    _require_int64(order_qty_centi, "order_qty_centi")
    _require_int64(latency_l_ns, "latency_l_ns")
    _require_int64(clock_offset_ns, "clock_offset_ns")
    if order_qty_centi <= 0:
        raise ValueError("order_qty_centi must be positive")
    if latency_l_ns < MIN_LATENCY_L_NS:
        raise ValueError(f"latency_l_ns must be >= {MIN_LATENCY_L_NS}, got {latency_l_ns}")

    eff_maker_fee_bps = contract_meta.maker_fee_bps if maker_fee_bps is None else maker_fee_bps
    snap_k = l2_snaps[decision_snap_idx]
    t_decision_ns = snap_k.t_resp_recv_ns
    t_live_ns = t_decision_ns + latency_l_ns
    eps_ns = clock_offset_ns + latency_l_ns
    t_print_min_ns = t_live_ns + eps_ns

    if cancel_snap_idx is not None:
        t_cancel_ns = l2_snaps[cancel_snap_idx].t_resp_recv_ns + latency_l_ns
    elif settlement is not None:
        t_cancel_ns = settlement.settled_at_ns
    elif contract_meta.close_time_ns is not None and contract_meta.close_time_ns > t_live_ns:
        t_cancel_ns = contract_meta.close_time_ns
    else:
        t_cancel_ns = l2_snaps[-1].t_resp_recv_ns + latency_l_ns

    if settlement is not None and settlement.settled_at_ns < t_cancel_ns:
        t_cancel_ns = settlement.settled_at_ns

    duration_ns = max(0, t_cancel_ns - t_decision_ns)
    bucket = _hours_to_close_bucket(t_decision_ns, contract_meta.close_time_ns)
    cat_label = contract_meta.category or "UNKNOWN"

    settled_flag = bool(settlement is not None and settlement.settlement_value_pips is not None)
    settle_pips = settlement.settlement_value_pips if settled_flag and settlement is not None else None

    def _empty_result(
        *,
        status: str,
        post_only_rejected: bool = False,
        censored: bool = False,
        censor_reasons: Tuple[str, ...] = (),
        start_q_lb: int = 0,
        start_q_mid: int = 0,
        start_q_ub: int = 0,
        touch_events: int = 0,
    ) -> OrderEpisodeResult:
        fallback_val = settle_pips if settle_pips is not None else _last_executable_bid_pips(l2_snaps)
        return OrderEpisodeResult(
            episode_id=episode_id,
            contract_ticker=contract_meta.contract_ticker,
            event_cluster_id=contract_meta.event_cluster_id,
            series_ticker=contract_meta.series_ticker,
            category=cat_label,
            decision_ts_ns=t_decision_ns,
            t_live_ns=t_live_ns,
            t_cancel_ns=t_cancel_ns,
            duration_ns=duration_ns,
            hours_to_close_bucket=bucket,
            proposed_bid_pips=proposed_bid_pips,
            order_qty_centi=order_qty_centi,
            status=status,
            post_only_rejected=post_only_rejected,
            crossed_order=False,
            censored=censored,
            censor_reasons=censor_reasons,
            settled=settled_flag,
            settlement_value_pips=settle_pips,
            early_exit_triggered=False,
            exit_valuation_pips_lb=fallback_val,
            exit_valuation_pips_mid=fallback_val,
            exit_valuation_pips_ub=fallback_val,
            start_q_lb_centi=start_q_lb,
            start_q_mid_centi=start_q_mid,
            start_q_ub_centi=start_q_ub,
            touch_only_events=touch_events,
            filled_qty_lb_centi=0,
            filled_qty_mid_centi=0,
            filled_qty_ub_centi=0,
            fills_lb=(),
            fills_mid=(),
            fills_ub=(),
            citing_trade_ids_lb=(),
            citing_trade_ids_mid=(),
            citing_trade_ids_ub=(),
            gross_pnl_lb_micro=0,
            gross_pnl_mid_micro=0,
            gross_pnl_ub_micro=0,
            fee_lb_micro=0,
            fee_mid_micro=0,
            fee_ub_micro=0,
            net_pnl_lb_micro=0,
            net_pnl_mid_micro=0,
            net_pnl_ub_micro=0,
            pi_l_micro=0,
        )

    # 1. Expired before order could go live
    if t_cancel_ns <= t_live_ns:
        return _empty_result(status="EXPIRED_BEFORE_LIVE")

    # 2. Post-only safety: reject if best ask <= proposed bid at decision or any snapshot <= t_live
    for idx in range(decision_snap_idx, len(l2_snaps)):
        sn = l2_snaps[idx]
        if sn.t_resp_recv_ns > t_live_ns:
            break
        if sn.best_yes_ask_pips is not None and sn.best_yes_ask_pips <= proposed_bid_pips:
            return _empty_result(status="POST_ONLY_REJECTED", post_only_rejected=True)

    # 3. Censoring: any overlapping DATA_GAP or INCOMPLETE trade window censors the episode
    c_reasons = _overlapping_censor_reasons(
        contract_meta.contract_ticker, t_decision_ns, t_cancel_ns, censor_intervals
    )
    if c_reasons:
        return _empty_result(status="CENSORED", censored=True, censor_reasons=c_reasons)

    # 4. Starting queue-ahead bounds at price p
    d_p_k = snap_k.yes_bid_depth_by_price.get(proposed_bid_pips, 0)
    k1_idx: Optional[int] = None
    for idx in range(decision_snap_idx + 1, len(l2_snaps)):
        if l2_snaps[idx].t_resp_recv_ns >= t_live_ns:
            if l2_snaps[idx].t_resp_recv_ns <= t_cancel_ns:
                k1_idx = idx
            break
    if k1_idx is None and (decision_snap_idx + 1) < len(l2_snaps):
        if l2_snaps[decision_snap_idx + 1].t_resp_recv_ns <= t_cancel_ns:
            k1_idx = decision_snap_idx + 1

    if k1_idx is not None:
        snap_k1 = l2_snaps[k1_idx]
        d_p_k1 = snap_k1.yes_bid_depth_by_price.get(proposed_bid_pips, 0)
        v_p_k_to_k1 = _taker_sell_volume_at_price(
            trades, proposed_bid_pips, snap_k.t_resp_recv_ns, snap_k1.t_resp_recv_ns
        )
        start_q_lb = d_p_k + max(0, d_p_k1 - d_p_k + v_p_k_to_k1)
    else:
        start_q_lb = d_p_k
    start_q_mid = d_p_k
    start_q_ub = d_p_k

    # 5. Prepare per-bound state and print volume ledgers (each print consumed at most once per variant)
    vol_rem: Dict[str, Dict[str, int]] = {
        "lb": print_vol_remaining_lb if print_vol_remaining_lb is not None else {},
        "mid": print_vol_remaining_mid if print_vol_remaining_mid is not None else {},
        "ub": print_vol_remaining_ub if print_vol_remaining_ub is not None else {},
    }
    q_ahead: Dict[str, int] = {"lb": start_q_lb, "mid": start_q_mid, "ub": start_q_ub}
    rem_qty: Dict[str, int] = {"lb": order_qty_centi, "mid": order_qty_centi, "ub": order_qty_centi}
    fills: Dict[str, List[SimulatedFillRecord]] = {"lb": [], "mid": [], "ub": []}
    touch_only_events = 0

    # 6. Build deterministic chronological stream of snapshots and eligible prints during (t_live, t_cancel)
    # Event tuple: (ts_ns, kind_order [0=trade, 1=snapshot], tie_breaker, payload)
    events: List[Tuple[int, int, str, Any]] = []

    for idx in range(decision_snap_idx + 1, len(l2_snaps)):
        sn = l2_snaps[idx]
        if sn.t_resp_recv_ns >= t_cancel_ns:
            break
        if sn.t_resp_recv_ns > t_decision_ns:
            events.append((sn.t_resp_recv_ns, 1, f"{sn.capture_sequence:012d}", sn))

    for tr in trades:
        if tr.trade_ts_ns <= t_print_min_ns:
            continue
        if tr.trade_ts_ns >= t_cancel_ns:
            break
        if tr.taker_side != "no":
            continue
        events.append((tr.trade_ts_ns, 0, tr.trade_id, tr))

    events.sort(key=lambda e: (e[0], e[1], e[2]))

    prev_depth_p = d_p_k
    prev_snap_ts_ns = t_decision_ns

    for _ev_ts, ev_kind, _tie, payload in events:
        if ev_kind == 1:
            # L2 snapshot update: update MID (pro-rata) and UB (full) queue ahead for unexplained drops;
            # LB NEVER shrinks on cancellations (all cancellations assumed behind).
            sn: ObservedL2Snapshot = payload
            curr_depth_p = sn.yes_bid_depth_by_price.get(proposed_bid_pips, 0)
            v_p_interval = _taker_sell_volume_at_price(
                trades, proposed_bid_pips, prev_snap_ts_ns, sn.t_resp_recv_ns
            )
            unexplained_drop = max(0, prev_depth_p - curr_depth_p - v_p_interval)

            if unexplained_drop > 0:
                if prev_depth_p > 0 and q_ahead["mid"] > 0:
                    pro_rata = (unexplained_drop * min(q_ahead["mid"], prev_depth_p)) // prev_depth_p
                    q_ahead["mid"] = max(0, q_ahead["mid"] - pro_rata)
                q_ahead["ub"] = max(0, q_ahead["ub"] - unexplained_drop)

            # Touch observation: NEVER generates a fill
            if sn.best_yes_ask_pips is not None and sn.best_yes_ask_pips <= proposed_bid_pips:
                touch_only_events += 1

            prev_depth_p = curr_depth_p
            prev_snap_ts_ns = sn.t_resp_recv_ns

        else:
            # Eligible OBSERVED_TRADE print with taker_side == "no" and t_live + eps < ts < t_cancel
            tr: ObservedTradePrint = payload
            if tr.yes_price_pips > proposed_bid_pips:
                # Trade above our YES bid -> does not fill our bid
                continue

            if tr.yes_price_pips < proposed_bid_pips:
                # Trade-through: queue-independent fill across LB / MID / UB
                tier = assert_offline_evidence_tier(EvidenceTier.TRADE_THROUGH_EVIDENCE)
                for b in ("lb", "mid", "ub"):
                    if rem_qty[b] <= 0:
                        q_ahead[b] = 0
                        continue
                    unalloc = vol_rem[b].get(tr.trade_id, tr.count_centi)
                    if unalloc <= 0:
                        q_ahead[b] = 0
                        continue
                    fill_qty = min(rem_qty[b], unalloc)
                    rem_qty[b] -= fill_qty
                    vol_rem[b][tr.trade_id] = unalloc - fill_qty
                    q_ahead[b] = 0
                    if fill_qty > 0:
                        fee_micro = compute_cent_rounded_fee_micro(eff_maker_fee_bps, fill_qty, proposed_bid_pips)
                        fills[b].append(
                            SimulatedFillRecord(
                                bound=b,
                                trade_id=tr.trade_id,
                                fill_ts_ns=tr.trade_ts_ns,
                                fill_price_pips=proposed_bid_pips,
                                print_price_pips=tr.yes_price_pips,
                                fill_qty_centi=fill_qty,
                                evidence_tier=tier,
                                fee_micro_dollars=fee_micro,
                            )
                        )
            else:
                # Same-price print (tr.yes_price_pips == proposed_bid_pips): FIFO absorption first
                tier = assert_offline_evidence_tier(EvidenceTier.QUEUE_CONDITIONAL_BOUND)
                any_filled = False
                for b in ("lb", "mid", "ub"):
                    if rem_qty[b] <= 0:
                        continue
                    unalloc = vol_rem[b].get(tr.trade_id, tr.count_centi)
                    if unalloc <= 0:
                        continue
                    absorbed = min(q_ahead[b], unalloc)
                    q_ahead[b] -= absorbed
                    leftover = unalloc - absorbed
                    fill_qty = min(rem_qty[b], leftover)
                    if fill_qty > 0:
                        any_filled = True
                        rem_qty[b] -= fill_qty
                        vol_rem[b][tr.trade_id] = unalloc - fill_qty
                        fee_micro = compute_cent_rounded_fee_micro(eff_maker_fee_bps, fill_qty, proposed_bid_pips)
                        fills[b].append(
                            SimulatedFillRecord(
                                bound=b,
                                trade_id=tr.trade_id,
                                fill_ts_ns=tr.trade_ts_ns,
                                fill_price_pips=proposed_bid_pips,
                                print_price_pips=tr.yes_price_pips,
                                fill_qty_centi=fill_qty,
                                evidence_tier=tier,
                                fee_micro_dollars=fee_micro,
                            )
                        )
                if not any_filled:
                    touch_only_events += 1

    # 7. Exact settlement / early-exit / unsettled mark-to-bid valuation
    filled_qty = {b: sum(f.fill_qty_centi for f in fills[b]) for b in ("lb", "mid", "ub")}
    maker_fees = {b: sum(f.fee_micro_dollars for f in fills[b]) for b in ("lb", "mid", "ub")}

    exit_val: Dict[str, int] = {}
    exit_fee: Dict[str, int] = {"lb": 0, "mid": 0, "ub": 0}
    any_early_exit = False
    unsettled_bid = _last_executable_bid_pips(l2_snaps)
    settle_ns = settlement.settled_at_ns if settlement is not None else None

    for b in ("lb", "mid", "ub"):
        early_bid: Optional[int] = None
        if exit_mode == "early_exit_5c" and fills[b]:
            early_bid = _find_early_exit_bid(
                l2_snaps,
                fill_ts_ns=fills[b][0].fill_ts_ns,
                latency_l_ns=latency_l_ns,
                entry_price_pips=proposed_bid_pips,
                settlement_ns=settle_ns,
            )
        if early_bid is not None:
            any_early_exit = True
            exit_val[b] = early_bid
            exit_fee[b] = compute_cent_rounded_fee_micro(taker_fee_bps, filled_qty[b], early_bid)
        elif settled_flag and settle_pips is not None:
            exit_val[b] = settle_pips
            exit_fee[b] = 0
        else:
            # Unsettled contract: executable best bid minus taker fee (NEVER midpoint)
            exit_val[b] = unsettled_bid
            exit_fee[b] = compute_cent_rounded_fee_micro(taker_fee_bps, filled_qty[b], unsettled_bid)

    gross_pnl = {
        b: _require_int64(filled_qty[b] * (exit_val[b] - proposed_bid_pips), f"gross_pnl_{b}")
        for b in ("lb", "mid", "ub")
    }
    total_fee = {b: maker_fees[b] + exit_fee[b] for b in ("lb", "mid", "ub")}
    net_pnl = {b: gross_pnl[b] - total_fee[b] for b in ("lb", "mid", "ub")}

    # Separable adverse payoff lower bound Pi_L:
    # minimum fills on winners (LB), maximum fills on losers (UB)
    pi_l_episode = min(net_pnl["lb"], net_pnl["mid"], net_pnl["ub"])

    return OrderEpisodeResult(
        episode_id=episode_id,
        contract_ticker=contract_meta.contract_ticker,
        event_cluster_id=contract_meta.event_cluster_id,
        series_ticker=contract_meta.series_ticker,
        category=cat_label,
        decision_ts_ns=t_decision_ns,
        t_live_ns=t_live_ns,
        t_cancel_ns=t_cancel_ns,
        duration_ns=duration_ns,
        hours_to_close_bucket=bucket,
        proposed_bid_pips=proposed_bid_pips,
        order_qty_centi=order_qty_centi,
        status="ACTIVE_EVALUATED",
        post_only_rejected=False,
        crossed_order=False,
        censored=False,
        censor_reasons=(),
        settled=settled_flag,
        settlement_value_pips=settle_pips,
        early_exit_triggered=any_early_exit,
        exit_valuation_pips_lb=exit_val["lb"],
        exit_valuation_pips_mid=exit_val["mid"],
        exit_valuation_pips_ub=exit_val["ub"],
        start_q_lb_centi=start_q_lb,
        start_q_mid_centi=start_q_mid,
        start_q_ub_centi=start_q_ub,
        touch_only_events=touch_only_events,
        filled_qty_lb_centi=filled_qty["lb"],
        filled_qty_mid_centi=filled_qty["mid"],
        filled_qty_ub_centi=filled_qty["ub"],
        fills_lb=tuple(fills["lb"]),
        fills_mid=tuple(fills["mid"]),
        fills_ub=tuple(fills["ub"]),
        citing_trade_ids_lb=tuple(f.trade_id for f in fills["lb"]),
        citing_trade_ids_mid=tuple(f.trade_id for f in fills["mid"]),
        citing_trade_ids_ub=tuple(f.trade_id for f in fills["ub"]),
        gross_pnl_lb_micro=gross_pnl["lb"],
        gross_pnl_mid_micro=gross_pnl["mid"],
        gross_pnl_ub_micro=gross_pnl["ub"],
        fee_lb_micro=total_fee["lb"],
        fee_mid_micro=total_fee["mid"],
        fee_ub_micro=total_fee["ub"],
        net_pnl_lb_micro=net_pnl["lb"],
        net_pnl_mid_micro=net_pnl["mid"],
        net_pnl_ub_micro=net_pnl["ub"],
        pi_l_micro=pi_l_episode,
    )


# ---------------------------------------------------------------------------
# 3. Variant Replay Runner & Adverse-Selection Diagnostics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayVariantConfig:
    variant_id: str
    min_spread_pips: int
    max_spread_pips: int = 1000
    max_expiry_hours: int = 168
    min_consecutive_snapshots: int = 2
    exit_mode: str = "settlement_only"
    min_price_pips: int = 1000
    max_price_pips: int = 9000
    min_top_depth_centi: int = 10_000
    order_qty_centi: int = 500  # 5 contracts default
    max_order_notional_micro: int = 5_000_000  # $5.00 max order guardrail
    maker_fee_bps: Optional[int] = None
    taker_fee_bps: int = DEFAULT_TAKER_FEE_BPS

    def __post_init__(self) -> None:
        _require_int64(self.min_spread_pips, "min_spread_pips")
        _require_int64(self.max_spread_pips, "max_spread_pips")
        _require_int64(self.max_expiry_hours, "max_expiry_hours")
        _require_int64(self.min_consecutive_snapshots, "min_consecutive_snapshots")
        _require_int64(self.min_price_pips, "min_price_pips")
        _require_int64(self.max_price_pips, "max_price_pips")
        _require_int64(self.min_top_depth_centi, "min_top_depth_centi")
        _require_int64(self.order_qty_centi, "order_qty_centi")
        _require_int64(self.max_order_notional_micro, "max_order_notional_micro")

        # Brief #01 hard guardrail: 1c (100) and 2c (200) spreads NEVER eligible for Strategy D
        if self.min_spread_pips < 300:
            raise ValueError(
                f"Brief #01 guardrail violation: min_spread_pips={self.min_spread_pips} < 300 "
                "(1c-2c spreads are strictly observation-only and never Strategy D eligible)."
            )
        if self.max_spread_pips > 1000 or self.max_spread_pips < self.min_spread_pips:
            raise ValueError(
                f"Invalid spread band [{self.min_spread_pips}, {self.max_spread_pips}] (must be within [300, 1000])."
            )
        if self.min_price_pips < 1000 or self.max_price_pips > 9000 or self.min_price_pips >= self.max_price_pips:
            raise ValueError("Price band must lie within [1000, 9000] pips (10c-90c).")
        if self.min_consecutive_snapshots < 1:
            raise ValueError("min_consecutive_snapshots must be >= 1")
        if self.max_expiry_hours < 1 or self.max_expiry_hours > 168:
            raise ValueError("max_expiry_hours must be within [1, 168]")
        if self.exit_mode not in {"settlement_only", "early_exit_5c"}:
            raise ValueError(f"Unsupported exit_mode={self.exit_mode!r}")
        if self.order_qty_centi <= 0:
            raise ValueError("order_qty_centi must be > 0")

    def to_canonical_dict(self) -> Dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "min_spread_pips": self.min_spread_pips,
            "max_spread_pips": self.max_spread_pips,
            "max_expiry_hours": self.max_expiry_hours,
            "min_consecutive_snapshots": self.min_consecutive_snapshots,
            "exit_mode": self.exit_mode,
            "min_price_pips": self.min_price_pips,
            "max_price_pips": self.max_price_pips,
            "min_top_depth_centi": self.min_top_depth_centi,
            "order_qty_centi": self.order_qty_centi,
            "max_order_notional_micro": self.max_order_notional_micro,
            "maker_fee_bps": self.maker_fee_bps,
            "taker_fee_bps": self.taker_fee_bps,
        }


def _snapshot_eligible_for_variant(
    snap: ObservedL2Snapshot,
    meta: ContractMetaV2,
    variant: ReplayVariantConfig,
    settlement: Optional[SettlementEventV2],
) -> bool:
    if _is_crypto_or_benchmark(
        meta.venue, meta.category, meta.classification, meta.contract_ticker, meta.series_ticker
    ):
        return False
    if _is_crypto_or_benchmark(
        snap.venue, snap.category, snap.classification, snap.contract_ticker, meta.series_ticker
    ):
        return False
    if snap.book_quarantined or snap.post_settlement_snapshot:
        return False
    if not snap.exact_cent_eligible or not snap.uniform_1c_grid_10_90:
        return False
    if settlement is not None and snap.t_resp_recv_ns >= settlement.settled_at_ns:
        return False
    if snap.best_yes_bid_pips is None or snap.best_yes_ask_pips is None or snap.spread_pips is None:
        return False
    if not (variant.min_price_pips <= snap.best_yes_bid_pips <= variant.max_price_pips):
        return False
    if not (variant.min_price_pips <= snap.best_yes_ask_pips <= variant.max_price_pips):
        return False
    if not (variant.min_spread_pips <= snap.spread_pips <= variant.max_spread_pips):
        return False
    if snap.best_yes_bid_qty_centi < variant.min_top_depth_centi:
        return False
    if snap.best_yes_ask_qty_centi < variant.min_top_depth_centi:
        return False
    if meta.close_time_ns is not None:
        rem_ns = meta.close_time_ns - snap.t_resp_recv_ns
        if rem_ns <= 0 or rem_ns > variant.max_expiry_hours * NS_PER_HOUR:
            return False
    return True


def _compute_bid_markout_at_delta(
    l2_snaps: Sequence[ObservedL2Snapshot],
    snap_timestamps: Sequence[int],
    settlement: Optional[SettlementEventV2],
    fill_ts_ns: int,
    fill_price_pips: int,
    delta_minutes: int,
) -> Optional[int]:
    """Compute executable bid-side markout `best_bid(t + delta) - p` in exact integer pips."""
    target_ns = fill_ts_ns + delta_minutes * NS_PER_MINUTE
    if settlement is not None and settlement.settlement_value_pips is not None and settlement.settled_at_ns <= target_ns:
        return settlement.settlement_value_pips - fill_price_pips
    if not snap_timestamps or snap_timestamps[-1] < target_ns:
        return None
    pos = bisect.bisect_right(snap_timestamps, target_ns) - 1
    while pos >= 0:
        sn = l2_snaps[pos]
        if sn.t_resp_recv_ns < fill_ts_ns:
            return None
        if not sn.book_quarantined and sn.best_yes_bid_pips is not None:
            return sn.best_yes_bid_pips - fill_price_pips
        pos -= 1
    return None


def compute_diagnostics_summary(
    episodes: Sequence[OrderEpisodeResult],
    tape: LoadedTapeV2,
) -> Dict[str, Any]:
    """Compute Selection Gap G, executable bid-side markouts (1,5,15,60m), and breakdowns."""
    settled_eval = [ep for ep in episodes if ep.status == "ACTIVE_EVALUATED" and not ep.censored and ep.settled]
    unsettled_eval = [ep for ep in episodes if ep.status == "ACTIVE_EVALUATED" and not ep.censored and not ep.settled]

    # Selection Gap G = E[S - p | filled] - E[S - p | posted_alive]
    posted_num = 0
    posted_den = 0
    filled_lb_num = 0
    filled_lb_den = 0
    filled_mid_num = 0
    filled_mid_den = 0

    for ep in settled_eval:
        assert ep.settlement_value_pips is not None
        diff_pips = ep.settlement_value_pips - ep.proposed_bid_pips
        posted_num += ep.order_qty_centi * diff_pips
        posted_den += ep.order_qty_centi
        if ep.filled_qty_lb_centi > 0:
            filled_lb_num += ep.filled_qty_lb_centi * diff_pips
            filled_lb_den += ep.filled_qty_lb_centi
        if ep.filled_qty_mid_centi > 0:
            filled_mid_num += ep.filled_qty_mid_centi * diff_pips
            filled_mid_den += ep.filled_qty_mid_centi

    e_posted_pips: Optional[int] = (posted_num // posted_den) if posted_den > 0 else None
    e_filled_lb_pips: Optional[int] = (filled_lb_num // filled_lb_den) if filled_lb_den > 0 else None
    e_filled_mid_pips: Optional[int] = (filled_mid_num // filled_mid_den) if filled_mid_den > 0 else None

    selection_gap_lb_pips: Optional[int] = (
        (e_filled_lb_pips - e_posted_pips)
        if (e_filled_lb_pips is not None and e_posted_pips is not None)
        else None
    )
    selection_gap_mid_pips: Optional[int] = (
        (e_filled_mid_pips - e_posted_pips)
        if (e_filled_mid_pips is not None and e_posted_pips is not None)
        else None
    )

    # Precompute snapshot timestamps per ticker for fast deterministic markouts
    snap_ts_cache: Dict[str, List[int]] = {
        tk: [s.t_resp_recv_ns for s in snaps] for tk, snaps in tape.l2_by_ticker.items()
    }

    markout_sums: Dict[int, int] = {m: 0 for m in MARKOUT_HORIZONS_MINUTES}
    markout_counts: Dict[int, int] = {m: 0 for m in MARKOUT_HORIZONS_MINUTES}

    fill_type_buckets: Dict[str, Dict[str, int]] = {
        "trade_through": {"fill_events": 0, "filled_qty_centi": 0, "net_pnl_micro": 0},
        "queue_fill": {"fill_events": 0, "filled_qty_centi": 0, "net_pnl_micro": 0},
    }
    by_series: Dict[str, Dict[str, int]] = {}
    by_category: Dict[str, Dict[str, int]] = {}
    by_hours_to_close: Dict[str, Dict[str, int]] = {}

    for ep in settled_eval:
        snaps = tape.l2_by_ticker.get(ep.contract_ticker, ())
        snap_ts = snap_ts_cache.get(ep.contract_ticker, [])
        settle = tape.settlements.get(ep.contract_ticker)

        # Fill-type breakdown & bid-side markouts on LB fills
        for fill in ep.fills_lb:
            ft_key = (
                "trade_through"
                if fill.evidence_tier == EvidenceTier.TRADE_THROUGH_EVIDENCE
                else "queue_fill"
            )
            fill_net = fill.fill_qty_centi * (ep.exit_valuation_pips_lb - fill.fill_price_pips) - fill.fee_micro_dollars
            fill_type_buckets[ft_key]["fill_events"] += 1
            fill_type_buckets[ft_key]["filled_qty_centi"] += fill.fill_qty_centi
            fill_type_buckets[ft_key]["net_pnl_micro"] += fill_net

            for delta_min in MARKOUT_HORIZONS_MINUTES:
                mk = _compute_bid_markout_at_delta(
                    snaps, snap_ts, settle, fill.fill_ts_ns, fill.fill_price_pips, delta_min
                )
                if mk is not None:
                    markout_sums[delta_min] += mk
                    markout_counts[delta_min] += 1

        # Breakdowns by series, category, and hours_to_close
        for group_map, group_key in (
            (by_series, ep.series_ticker),
            (by_category, ep.category),
            (by_hours_to_close, ep.hours_to_close_bucket),
        ):
            rec = group_map.setdefault(
                group_key,
                {
                    "episodes_posted": 0,
                    "episodes_filled_lb": 0,
                    "filled_qty_lb_centi": 0,
                    "net_pnl_lb_micro": 0,
                    "pi_l_micro": 0,
                },
            )
            rec["episodes_posted"] += 1
            if ep.filled_qty_lb_centi > 0:
                rec["episodes_filled_lb"] += 1
                rec["filled_qty_lb_centi"] += ep.filled_qty_lb_centi
                rec["net_pnl_lb_micro"] += ep.net_pnl_lb_micro
                rec["pi_l_micro"] += ep.pi_l_micro

    def _finalize_group_ev(group_map: Dict[str, Dict[str, int]]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for key in sorted(group_map.keys()):
            row = dict(group_map[key])
            qty = row["filled_qty_lb_centi"]
            row["lb_ev_pips"] = (row["net_pnl_lb_micro"] // qty) if qty > 0 else None
            out[key] = row
        return out

    markouts_out: Dict[str, Dict[str, Any]] = {}
    for m in MARKOUT_HORIZONS_MINUTES:
        cnt = markout_counts[m]
        markouts_out[f"{m}m"] = {
            "delta_minutes": m,
            "sample_count": cnt,
            "mean_bid_markout_pips": (markout_sums[m] // cnt) if cnt > 0 else None,
        }

    fill_type_out: Dict[str, Dict[str, Any]] = {}
    for ft_key in ("trade_through", "queue_fill"):
        row = dict(fill_type_buckets[ft_key])
        qty = row["filled_qty_centi"]
        row["ev_pips"] = (row["net_pnl_micro"] // qty) if qty > 0 else None
        fill_type_out[ft_key] = row

    unsettled_summary = {
        "unsettled_episodes_excluded_count": len(unsettled_eval),
        "unsettled_tickers": sorted({ep.contract_ticker for ep in unsettled_eval}),
        "unsettled_mark_to_bid_pnl_lb_micro": sum(ep.net_pnl_lb_micro for ep in unsettled_eval),
        "valuation_basis": "EXECUTABLE_BEST_BID_MINUS_TAKER_FEE",
    }

    return {
        "selection_gap": {
            "e_s_minus_p_posted_alive_pips": e_posted_pips,
            "e_s_minus_p_filled_lb_pips": e_filled_lb_pips,
            "e_s_minus_p_filled_mid_pips": e_filled_mid_pips,
            "selection_gap_lb_pips": selection_gap_lb_pips,
            "selection_gap_mid_pips": selection_gap_mid_pips,
        },
        "executable_bid_markouts": markouts_out,
        "by_fill_type": fill_type_out,
        "by_series": _finalize_group_ev(by_series),
        "by_category": _finalize_group_ev(by_category),
        "by_hours_to_close": _finalize_group_ev(by_hours_to_close),
        "unsettled_contracts": unsettled_summary,
    }


def replay_variant_on_tape(
    tape: LoadedTapeV2,
    variant: ReplayVariantConfig,
    *,
    allowed_event_clusters: Optional[Iterable[str]] = None,
    clock_offset_ns: int = 0,
) -> Dict[str, Any]:
    """Deterministically replay a single Strategy D variant over allowed event clusters of a Schema 2.0.0 tape."""
    allowed_set: Optional[frozenset[str]] = (
        frozenset(allowed_event_clusters) if allowed_event_clusters is not None else None
    )

    print_vol_remaining_lb: Dict[str, int] = {}
    print_vol_remaining_mid: Dict[str, int] = {}
    print_vol_remaining_ub: Dict[str, int] = {}

    episodes: List[OrderEpisodeResult] = []
    risk_limit_breaches = 0
    crossed_orders_count = 0
    post_only_rejections = 0
    ep_counter = 0

    for tk in sorted(tape.l2_by_ticker.keys()):
        meta = tape.contracts[tk]
        if allowed_set is not None and meta.event_cluster_id not in allowed_set:
            continue
        if _is_crypto_or_benchmark(
            meta.venue, meta.category, meta.classification, meta.contract_ticker, meta.series_ticker
        ):
            continue

        l2_snaps = tape.l2_by_ticker[tk]
        trades = tape.trades_by_ticker.get(tk, ())
        settlement = tape.settlements.get(tk)

        consec_ok = 0
        active_decision_idx: Optional[int] = None
        active_bid_pips: Optional[int] = None
        active_qty_centi: int = 0
        cooldown_until_ns: int = -1

        for idx, snap in enumerate(l2_snaps):
            eligible = _snapshot_eligible_for_variant(snap, meta, variant, settlement)

            if active_decision_idx is not None:
                # Decide whether to cancel/reprice existing resting order at this decision snapshot
                should_cancel = (
                    (not eligible)
                    or (snap.best_yes_bid_pips != active_bid_pips)
                )
                if should_cancel:
                    ep_counter += 1
                    ep = simulate_order_episode(
                        episode_id=f"{variant.variant_id}:EP-{ep_counter:06d}",
                        contract_meta=meta,
                        decision_snap_idx=active_decision_idx,
                        cancel_snap_idx=idx,
                        proposed_bid_pips=active_bid_pips if active_bid_pips is not None else 0,
                        order_qty_centi=active_qty_centi,
                        l2_snaps=l2_snaps,
                        trades=trades,
                        settlement=settlement,
                        censor_intervals=tape.censor_intervals,
                        latency_l_ns=tape.latency_l_ns,
                        clock_offset_ns=clock_offset_ns,
                        maker_fee_bps=variant.maker_fee_bps,
                        taker_fee_bps=variant.taker_fee_bps,
                        exit_mode=variant.exit_mode,
                        print_vol_remaining_lb=print_vol_remaining_lb,
                        print_vol_remaining_mid=print_vol_remaining_mid,
                        print_vol_remaining_ub=print_vol_remaining_ub,
                    )
                    episodes.append(ep)
                    if ep.post_only_rejected:
                        post_only_rejections += 1
                    if ep.crossed_order:
                        crossed_orders_count += 1
                    cooldown_until_ns = ep.t_cancel_ns
                    active_decision_idx = None
                    active_bid_pips = None
                    active_qty_centi = 0

            if eligible:
                consec_ok += 1
            else:
                consec_ok = 0

            if (
                active_decision_idx is None
                and eligible
                and consec_ok >= variant.min_consecutive_snapshots
                and snap.t_resp_recv_ns >= cooldown_until_ns
                and snap.best_yes_bid_pips is not None
            ):
                proposed_p = snap.best_yes_bid_pips
                # Clamp whole-contract quantity to max_order_notional_micro guardrail
                max_whole_contracts = variant.max_order_notional_micro // (proposed_p * CENTI_PER_CONTRACT)
                qty_centi = min(variant.order_qty_centi, max_whole_contracts * CENTI_PER_CONTRACT)
                if qty_centi <= 0:
                    continue
                if compute_micro_dollars(proposed_p, qty_centi) > variant.max_order_notional_micro:
                    risk_limit_breaches += 1
                    continue
                active_decision_idx = idx
                active_bid_pips = proposed_p
                active_qty_centi = qty_centi

        # Close out any resting order still open at end of contract snapshots
        if active_decision_idx is not None and active_bid_pips is not None:
            ep_counter += 1
            ep = simulate_order_episode(
                episode_id=f"{variant.variant_id}:EP-{ep_counter:06d}",
                contract_meta=meta,
                decision_snap_idx=active_decision_idx,
                cancel_snap_idx=None,
                proposed_bid_pips=active_bid_pips,
                order_qty_centi=active_qty_centi,
                l2_snaps=l2_snaps,
                trades=trades,
                settlement=settlement,
                censor_intervals=tape.censor_intervals,
                latency_l_ns=tape.latency_l_ns,
                clock_offset_ns=clock_offset_ns,
                maker_fee_bps=variant.maker_fee_bps,
                taker_fee_bps=variant.taker_fee_bps,
                exit_mode=variant.exit_mode,
                print_vol_remaining_lb=print_vol_remaining_lb,
                print_vol_remaining_mid=print_vol_remaining_mid,
                print_vol_remaining_ub=print_vol_remaining_ub,
            )
            episodes.append(ep)
            if ep.post_only_rejected:
                post_only_rejections += 1
            if ep.crossed_order:
                crossed_orders_count += 1

    # Aggregate certification metrics strictly over settled, non-censored, active episodes
    cert_episodes = [ep for ep in episodes if ep.status == "ACTIVE_EVALUATED" and not ep.censored and ep.settled]
    censored_episodes = [ep for ep in episodes if ep.censored]

    total_order_ns = sum(ep.duration_ns for ep in episodes if ep.status in {"ACTIVE_EVALUATED", "CENSORED"})
    censored_order_ns = sum(ep.duration_ns for ep in censored_episodes)
    censored_order_minutes_bps = (
        (censored_order_ns * 10_000) // total_order_ns if total_order_ns > 0 else 0
    )

    total_pnl_lb = sum(ep.net_pnl_lb_micro for ep in cert_episodes)
    total_pnl_mid = sum(ep.net_pnl_mid_micro for ep in cert_episodes)
    total_pnl_ub = sum(ep.net_pnl_ub_micro for ep in cert_episodes)
    total_pi_l = sum(ep.pi_l_micro for ep in cert_episodes)
    certified_total_pnl_micro = min(total_pnl_lb, total_pnl_mid, total_pnl_ub)

    filled_centi_lb = sum(ep.filled_qty_lb_centi for ep in cert_episodes)
    filled_centi_mid = sum(ep.filled_qty_mid_centi for ep in cert_episodes)
    filled_centi_ub = sum(ep.filled_qty_ub_centi for ep in cert_episodes)

    filled_ep_count_lb = sum(1 for ep in cert_episodes if ep.filled_qty_lb_centi > 0)
    filled_ep_count_mid = sum(1 for ep in cert_episodes if ep.filled_qty_mid_centi > 0)
    filled_ep_count_ub = sum(1 for ep in cert_episodes if ep.filled_qty_ub_centi > 0)

    lb_ev_pips: Optional[int] = (total_pnl_lb // filled_centi_lb) if filled_centi_lb > 0 else None
    mid_ev_pips: Optional[int] = (total_pnl_mid // filled_centi_mid) if filled_centi_mid > 0 else None
    ub_ev_pips: Optional[int] = (total_pnl_ub // filled_centi_ub) if filled_centi_ub > 0 else None

    diagnostics = compute_diagnostics_summary(episodes, tape)

    return {
        "variant_id": variant.variant_id,
        "variant_config": variant.to_canonical_dict(),
        "synthetic_fills_present": False,
        "evidence_tiers_used": sorted(
            {
                f.evidence_tier.value
                for ep in cert_episodes
                for f in (ep.fills_lb + ep.fills_mid + ep.fills_ub)
            }
        ),
        "total_episodes": len(episodes),
        "certified_settled_episodes": len(cert_episodes),
        "censored_episodes_count": len(censored_episodes),
        "post_only_rejections": post_only_rejections,
        "crossed_orders_count": crossed_orders_count,
        "risk_limit_breaches": risk_limit_breaches,
        "total_order_ns": total_order_ns,
        "censored_order_ns": censored_order_ns,
        "censored_order_minutes_bps": censored_order_minutes_bps,
        "filled_order_episodes_lb": filled_ep_count_lb,
        "filled_order_episodes_mid": filled_ep_count_mid,
        "filled_order_episodes_ub": filled_ep_count_ub,
        "filled_qty_lb_centi": filled_centi_lb,
        "filled_qty_mid_centi": filled_centi_mid,
        "filled_qty_ub_centi": filled_centi_ub,
        "total_pnl_lb_micro": total_pnl_lb,
        "total_pnl_mid_micro": total_pnl_mid,
        "total_pnl_ub_micro": total_pnl_ub,
        "certified_total_pnl_micro": certified_total_pnl_micro,
        "pi_l_micro": total_pi_l,
        "lb_ev_pips": lb_ev_pips,
        "mid_ev_pips": mid_ev_pips,
        "ub_ev_pips": ub_ev_pips,
        "diagnostics": diagnostics,
        "episodes": episodes,
    }
