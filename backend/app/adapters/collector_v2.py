"""Collector v2.0 — Read-only microstructure tape collector (Schema v2.0.0, ADR-008 3-unit exact integers, CQP-001-v0.1).

Non-Negotiable Invariants:
- ZERO private API keys, ZERO live order submission, ZERO synthetic fills (`synthetic_fills_present: false`).
- Fail-closed defaults (`PDEUE_VENUE_MODE` in {paper, observation}, `PDEUE_LIVE_TRADING_ENABLED=false`).
- Exact int64 integer arithmetic ONLY for all prices, sizes, spreads, notional values, and fees (zero `float()`).
- Anti-survivorship retention: admitted contracts are recorded through final settlement (+1 post-settlement snapshot).
- Bounded O(1) streaming SHA-256 manifest so Lightsail RAM footprint stays safely under `mem_limit: 128m`.
"""
from __future__ import annotations

import collections
import copy
import hashlib
import json
import os
import random
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx

SCHEMA_VERSION_V2 = "2.0.0"
CQP_POLICY_VERSION = "CQP-001-v0.1"

KALSHI_EXTERNAL_API_BASE = "https://external-api.kalshi.com/trade-api/v2"
POLYMARKET_PUBLIC_BASE = "https://clob.polymarket.com"
POLYMARKET_GAMMA_BASE = "https://gamma-api.polymarket.com"

ALLOWED_PAPER_MODES = frozenset({"paper", "observation"})

RECORD_TYPES = frozenset(
    {
        "OBSERVED_L2",
        "OBSERVED_TRADE",
        "MARKET_META",
        "QUALIFICATION_DECISION",
        "SETTLEMENT_EVENT",
        "DATA_GAP",
        "HEARTBEAT",
    }
)

CURATED_CADENCE_LADDER: Tuple[int, ...] = (10, 15, 30, 60)
MAX_CURATED_KALSHI_CONTRACTS = 32
MAX_POLYMARKET_BENCHMARK_CONTRACTS = 16
TRADES_OVERLAP_WINDOW_SECONDS = 120
ADMISSION_INTERVAL_SECONDS = 900  # 15 minutes
BASELINE_POLL_INTERVAL_SECONDS = 60

# 3-unit exact integer scale factors (ADR-008 Upgrade)
PIPS_PER_CENT = 100
PIPS_PER_DOLLAR = 10_000  # $0.0001 per pip
CENTI_PER_CONTRACT = 100  # 0.01 contracts per centi-contract
INT64_MIN = -(1 << 63)
INT64_MAX = (1 << 63) - 1

DEFAULT_CQP_CONFIG: Dict[str, Any] = {
    "policy_id": CQP_POLICY_VERSION,
    "schema_version": SCHEMA_VERSION_V2,
    "max_curated_kalshi_contracts": MAX_CURATED_KALSHI_CONTRACTS,
    "max_polymarket_benchmark_contracts": MAX_POLYMARKET_BENCHMARK_CONTRACTS,
    "min_hours_to_close": 1,
    "max_hours_to_close": 168,
    "settlement_buffer_hours": 24,
    "recording_window_days": 14,
    "priority_order": [
        "WEATHER",
        "SCHEDULED_MACRO",
        "PRE_GAME_SPORTS",
        "SHORT_HORIZON_CRYPTO",
    ],
    "benchmark_only_categories": ["SHORT_HORIZON_CRYPTO"],
    "series_allowlist": {
        "WEATHER": [
            "KXHIGH",
            "KXLOW",
            "KXTEMP",
            "KXRAIN",
            "KXSNOW",
            "KXWIND",
            "KXWEATHER",
            "KXHURR",
        ],
        "SCHEDULED_MACRO": [
            "KXCPI",
            "KXFED",
            "KXPAYROLLS",
            "KXNFP",
            "KXGDP",
            "KXPCE",
            "KXJOBLESS",
            "KXUNRATE",
            "KXFOMC",
            "KXINFL",
            "KXRATE",
            "KXPPI",
            "KXRETAIL",
        ],
        "PRE_GAME_SPORTS": [
            "KXNFL",
            "KXNBA",
            "KXMLB",
            "KXNHL",
            "KXNCAA",
            "KXSOCCER",
            "KXUFC",
            "KXATP",
            "KXWTA",
            "KXPGA",
            "KXSPORTS",
        ],
        "SHORT_HORIZON_CRYPTO": [
            "KXBTC",
            "KXETH",
            "KXSOL",
            "KXCRYPTO",
        ],
    },
    "banned_prefixes": [
        "KXMVE",
        "KXMV",
        "KXCOMBO",
        "KXPARLAY",
        "KXMULTIGAME",
        "KXMENTION",
        "KXNOVELTY",
    ],
    "banned_categories": [
        "MULTIVARIATE",
        "COMBO",
        "NOVELTY",
        "MULTI_YEAR_NOVELTY",
        "IN_PLAY_SPORTS",
        "ENTERTAINMENT",
        "POP_CULTURE",
        "MENTIONS",
    ],
    "strategy_d_rules": {
        "min_price_pips": 1000,
        "max_price_pips": 9000,
        "default_min_spread_pips": 400,
        "default_max_spread_pips": 1000,
        "replay_variant_spread_pips": 300,
        "observation_only_max_spread_pips": 200,
        "min_consecutive_snapshots": 2,
        "min_top_depth_centi": 10_000,  # 100 whole contracts per side
    },
}

_FORBIDDEN_AUTH_HEADERS = frozenset(
    {
        "authorization",
        "x-api-key",
        "kalshi-access-key",
        "kalshi-access-signature",
        "poly-api-key",
        "poly-signature",
    }
)


def _utc_now_iso(now_dt: Optional[datetime] = None) -> str:
    dt = now_dt or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_utc_iso(raw: Any) -> Optional[datetime]:
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def assert_fail_closed_paper_mode(env: Optional[Dict[str, str]] = None) -> str:
    """Refuse to run if live trading is enabled or venue mode is outside paper/observation."""
    source = env if env is not None else os.environ
    venue_mode = str(source.get("PDEUE_VENUE_MODE", "paper")).strip().lower() or "paper"
    live_flag = str(source.get("PDEUE_LIVE_TRADING_ENABLED", "false")).strip().lower() or "false"
    if venue_mode not in ALLOWED_PAPER_MODES:
        raise RuntimeError(
            f"FAIL-CLOSED: Collector v2.0 refuses PDEUE_VENUE_MODE={venue_mode!r}; "
            f"must be one of {sorted(ALLOWED_PAPER_MODES)}."
        )
    if live_flag not in {"false", "0", "no"}:
        raise RuntimeError(
            f"FAIL-CLOSED: Collector v2.0 refuses PDEUE_LIVE_TRADING_ENABLED={live_flag!r}; "
            "Gate G1 paper/observation isolation requires PDEUE_LIVE_TRADING_ENABLED=false."
        )
    return venue_mode


def resolve_collector_git_sha() -> str:
    """Resolve current git SHA once without ever failing inside stripped containers."""
    env_sha = os.getenv("PDEUE_COLLECTOR_GIT_SHA", "").strip()
    if env_sha:
        return env_sha
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return "unknown"


def compute_filter_config_hash(config: Dict[str, Any]) -> str:
    """Compute canonical SHA-256 hash of a versioned CQP filter configuration."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _check_int64(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be a strict int, got {type(value).__name__}")
    if value < INT64_MIN or value > INT64_MAX:
        raise OverflowError(f"{label} overflows signed int64: {value}")
    return value


def _parse_fixed_point_scaled(
    raw: Any,
    *,
    scale_digits: int,
    label: str,
    allow_negative: bool = False,
    truncate_extra_digits: bool = False,
) -> Tuple[str, int, bool]:
    """Parse a fixed-point decimal string or integer into exact scaled int64 with zero float()."""
    if isinstance(raw, bool):
        raise TypeError(f"Boolean rejected for {label}")
    if isinstance(raw, float):
        raise TypeError(f"Floating-point input rejected for {label}: {raw!r} (ADR-008 exact integer only)")

    scale_factor = 10**scale_digits
    if isinstance(raw, int):
        raw_str = str(raw)
        if not allow_negative and raw < 0:
            raise ValueError(f"Negative value rejected for {label}: {raw_str}")
        scaled = _check_int64(raw * scale_factor, label)
        return raw_str, scaled, False

    if not isinstance(raw, str):
        raise TypeError(f"Unsupported type for {label}: {type(raw).__name__}")

    raw_str = raw.strip()
    if not raw_str:
        raise ValueError(f"Empty string rejected for {label}")

    sign = 1
    body = raw_str
    if body[0] == "-":
        if not allow_negative:
            raise ValueError(f"Negative value rejected for {label}: {raw_str}")
        sign = -1
        body = body[1:]
    elif body[0] == "+":
        body = body[1:]

    if not body:
        raise ValueError(f"Invalid fixed-point string for {label}: {raw_str!r}")
    if "e" in body.lower():
        raise ValueError(f"Scientific notation rejected for {label}: {raw_str!r}")

    parts = body.split(".")
    if len(parts) > 2:
        raise ValueError(f"Malformed fixed-point string for {label}: {raw_str!r}")

    whole_part = parts[0] if parts[0] else "0"
    frac_part = parts[1] if len(parts) == 2 else ""

    if not whole_part.isdigit() or (frac_part and not frac_part.isdigit()):
        raise ValueError(f"Non-numeric fixed-point string for {label}: {raw_str!r}")

    truncated = False
    if len(frac_part) > scale_digits:
        extra = frac_part[scale_digits:]
        if any(ch != "0" for ch in extra):
            if not truncate_extra_digits:
                raise ValueError(
                    f"Precision exceeds {scale_digits} decimal places for {label}: {raw_str!r}"
                )
            truncated = True
        frac_scaled_str = frac_part[:scale_digits]
    else:
        frac_scaled_str = frac_part.ljust(scale_digits, "0")

    whole_int = int(whole_part)
    frac_int = int(frac_scaled_str) if frac_scaled_str else 0
    scaled = sign * (whole_int * scale_factor + frac_int)
    scaled = _check_int64(scaled, label)
    return raw_str, scaled, truncated


# ---------------------------------------------------------------------------
# 1. 3-Unit Exact-Integer Parser (ADR-008 Upgrade)
# ---------------------------------------------------------------------------


def parse_price_pips(
    raw: Any,
    *,
    input_unit: str = "dollars",
    allow_zero: bool = True,
    allow_dollar_one: bool = True,
) -> Tuple[str, int]:
    """Parse a fixed-point price string into exact int64 price_pips ($0.0001 units).

    Examples:
      - "0.4500" -> ("0.4500", 4500)
      - "0.0010" -> ("0.0010", 10)   (sub-cent quote preserved cleanly!)
      - "0.45"   -> ("0.45", 4500)
      - 45 (with input_unit="cents") -> ("45", 4500)
    """
    if input_unit == "cents":
        if isinstance(raw, bool) or isinstance(raw, float):
            raise TypeError(f"Invalid cent price type: {type(raw).__name__}")
        if isinstance(raw, int):
            raw_str = str(raw)
            pips = _check_int64(raw * PIPS_PER_CENT, "price_pips")
        else:
            raw_str, pips, _ = _parse_fixed_point_scaled(raw, scale_digits=2, label="price_pips")
    elif input_unit == "dollars":
        raw_str, pips, _ = _parse_fixed_point_scaled(raw, scale_digits=4, label="price_pips")
    else:
        raise ValueError(f"Unsupported input_unit={input_unit!r}; expected 'dollars' or 'cents'")

    min_pips = 0 if allow_zero else 1
    max_pips = PIPS_PER_DOLLAR if allow_dollar_one else (PIPS_PER_DOLLAR - 1)
    if pips < min_pips or pips > max_pips:
        raise ValueError(f"price_pips out of binary range [{min_pips}, {max_pips}]: {pips} (raw={raw!r})")
    return raw_str, pips


def parse_qty_centi(
    raw: Any,
    *,
    truncate_sub_centi: bool = False,
) -> Tuple[str, int, bool]:
    """Parse a fixed-point quantity string or int into exact int64 qty_centi (0.01 contract units).

    Returns (raw_str, qty_centi, fractional_quantity_flag).
    Examples:
      - "100.25" -> ("100.25", 10025, True)
      - "100.00" -> ("100.00", 10000, False)
      - 200      -> ("200", 20000, False)
    """
    raw_str, qty_centi, truncated = _parse_fixed_point_scaled(
        raw,
        scale_digits=2,
        label="qty_centi",
        allow_negative=False,
        truncate_extra_digits=truncate_sub_centi,
    )
    fractional_flag = bool((qty_centi % CENTI_PER_CONTRACT) != 0 or truncated)
    return raw_str, qty_centi, fractional_flag


def compute_micro_dollars(price_pips: int, qty_centi: int) -> int:
    """Exact int64 notional in micro-dollars ($0.000001): price_pips * qty_centi == micro_dollars."""
    _check_int64(price_pips, "price_pips")
    _check_int64(qty_centi, "qty_centi")
    return _check_int64(price_pips * qty_centi, "micro_dollars")


def is_uniform_1c_grid_10_90(
    price_ranges: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    tick_size_pips: Optional[int] = None,
) -> bool:
    """Return True iff market price grid is a uniform 1c (100 pips) tick across [10c, 90c] ([1000, 9000])."""
    if price_ranges:
        intervals: List[Tuple[int, int, int]] = []
        for rng in price_ranges:
            if not isinstance(rng, dict):
                return False
            try:
                _, start_p = parse_price_pips(rng["start"], allow_zero=True, allow_dollar_one=True)
                _, end_p = parse_price_pips(rng["end"], allow_zero=True, allow_dollar_one=True)
                _, step_p = parse_price_pips(rng["step"], allow_zero=False, allow_dollar_one=True)
            except (KeyError, TypeError, ValueError):
                return False
            if end_p <= start_p:
                continue
            intervals.append((start_p, end_p, step_p))

        if not intervals:
            return False

        # Check all intervals overlapping (1000, 9000) have step == 100 and completely cover [1000, 9000]
        covering: List[Tuple[int, int]] = []
        for start_p, end_p, step_p in intervals:
            ov_start = max(start_p, 1000)
            ov_end = min(end_p, 9000)
            if ov_end > ov_start:
                if step_p != PIPS_PER_CENT:
                    return False
                covering.append((ov_start, ov_end))

        if not covering:
            return False
        covering.sort()
        cursor = 1000
        for s_p, e_p in covering:
            if s_p > cursor:
                return False
            if e_p > cursor:
                cursor = e_p
        return cursor >= 9000

    if tick_size_pips is not None:
        return int(tick_size_pips) == PIPS_PER_CENT

    return True


def _extract_market_uniform_1c_grid(market_meta: Optional[Dict[str, Any]]) -> bool:
    if not market_meta or not isinstance(market_meta, dict):
        return True
    price_ranges = market_meta.get("price_ranges")
    if isinstance(price_ranges, list) and price_ranges:
        return is_uniform_1c_grid_10_90(price_ranges)
    if "tick_size_dollars" in market_meta and market_meta["tick_size_dollars"] is not None:
        try:
            _, step_pips = parse_price_pips(market_meta["tick_size_dollars"], allow_zero=False)
            return is_uniform_1c_grid_10_90(tick_size_pips=step_pips)
        except (TypeError, ValueError):
            return False
    if "tick_size" in market_meta and market_meta["tick_size"] is not None:
        raw_tick = market_meta["tick_size"]
        if isinstance(raw_tick, int) and not isinstance(raw_tick, bool):
            return is_uniform_1c_grid_10_90(tick_size_pips=raw_tick * PIPS_PER_CENT)
        try:
            _, step_pips = parse_price_pips(raw_tick, allow_zero=False)
            return is_uniform_1c_grid_10_90(tick_size_pips=step_pips)
        except (TypeError, ValueError):
            return False
    return True


def parse_book_level(
    raw_price: Any,
    raw_qty: Any,
    *,
    price_input_unit: str = "dollars",
    truncate_sub_centi: bool = False,
) -> Dict[str, Any]:
    """Parse a single price/quantity book level into exact 3-unit int64 representation."""
    price_raw, price_pips = parse_price_pips(
        raw_price,
        input_unit=price_input_unit,
        allow_zero=False,
        allow_dollar_one=False,
    )
    qty_raw, qty_centi, frac_qty = parse_qty_centi(raw_qty, truncate_sub_centi=truncate_sub_centi)
    micro_dollars = compute_micro_dollars(price_pips, qty_centi)
    return {
        "price_raw": price_raw,
        "price_pips": price_pips,
        "qty_raw": qty_raw,
        "qty_centi": qty_centi,
        "micro_dollars": micro_dollars,
        "exact_cent": (price_pips % PIPS_PER_CENT) == 0,
        "fractional_quantity_flag": frac_qty,
    }


def _format_pips_as_dollar_str(pips: int) -> str:
    whole = pips // PIPS_PER_DOLLAR
    frac = pips % PIPS_PER_DOLLAR
    return f"{whole}.{frac:04d}"


# ---------------------------------------------------------------------------
# 2. Kalshi Binary Book Normalization & Polymarket Normalization
# ---------------------------------------------------------------------------


def normalize_kalshi_l2_v2(
    ticker: str,
    payload: Dict[str, Any],
    *,
    source_url: str,
    market_meta: Optional[Dict[str, Any]] = None,
    captured_at_utc: Optional[str] = None,
) -> Dict[str, Any]:
    """Normalize Kalshi YES/NO bid ladders into 3-unit exact integers with quarantine checks.

    - Supports `orderbook_fp` (`yes_dollars`/`no_dollars`) and legacy `orderbook` (`yes`/`no`).
    - `best_yes_ask_pips = 10000 - best_no_bid_pips`
    - `spread_pips = best_yes_ask_pips - best_yes_bid_pips`
    - Quarantines locked/crossed books (`spread_pips <= 0`).
    - Never crashes on sub-cent quotes (e.g. `0.0010`); records them with `exact_cent_eligible: False`.
    """
    if "orderbook_fp" in payload and isinstance(payload["orderbook_fp"], dict):
        ob_fp = payload["orderbook_fp"]
        yes_raw = ob_fp.get("yes_dollars") or []
        no_raw = ob_fp.get("no_dollars") or []
        price_unit = "dollars"
    else:
        ob = payload.get("orderbook", payload) if isinstance(payload, dict) else {}
        if "yes_dollars" in ob or "no_dollars" in ob:
            yes_raw = ob.get("yes_dollars") or []
            no_raw = ob.get("no_dollars") or []
            price_unit = "dollars"
        else:
            yes_raw = ob.get("yes") or []
            no_raw = ob.get("no") or []
            price_unit = "cents"

    yes_bids: List[Dict[str, Any]] = []
    for entry in yes_raw:
        raw_p, raw_q = entry[0], entry[1]
        unit = "dollars" if isinstance(raw_p, str) and "." in raw_p else price_unit
        lv = parse_book_level(raw_p, raw_q, price_input_unit=unit)
        if lv["qty_centi"] > 0:
            yes_bids.append(lv)

    yes_asks: List[Dict[str, Any]] = []
    no_bids: List[Dict[str, Any]] = []
    for entry in no_raw:
        raw_p, raw_q = entry[0], entry[1]
        unit = "dollars" if isinstance(raw_p, str) and "." in raw_p else price_unit
        no_lv = parse_book_level(raw_p, raw_q, price_input_unit=unit)
        if no_lv["qty_centi"] <= 0:
            continue
        no_bids.append(no_lv)
        yes_ask_pips = PIPS_PER_DOLLAR - no_lv["price_pips"]
        yes_asks.append(
            {
                "price_raw": _format_pips_as_dollar_str(yes_ask_pips),
                "price_pips": yes_ask_pips,
                "no_bid_price_raw": no_lv["price_raw"],
                "no_bid_price_pips": no_lv["price_pips"],
                "qty_raw": no_lv["qty_raw"],
                "qty_centi": no_lv["qty_centi"],
                "micro_dollars": compute_micro_dollars(yes_ask_pips, no_lv["qty_centi"]),
                "exact_cent": (yes_ask_pips % PIPS_PER_CENT) == 0,
                "fractional_quantity_flag": no_lv["fractional_quantity_flag"],
            }
        )

    yes_bids.sort(key=lambda lv: lv["price_pips"], reverse=True)
    no_bids.sort(key=lambda lv: lv["price_pips"], reverse=True)
    yes_asks.sort(key=lambda lv: lv["price_pips"])

    best_yes_bid_pips = yes_bids[0]["price_pips"] if yes_bids else None
    best_yes_bid_qty_centi = yes_bids[0]["qty_centi"] if yes_bids else 0
    best_no_bid_pips = no_bids[0]["price_pips"] if no_bids else None
    best_yes_ask_pips = (PIPS_PER_DOLLAR - best_no_bid_pips) if best_no_bid_pips is not None else None
    best_yes_ask_qty_centi = yes_asks[0]["qty_centi"] if yes_asks else 0

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

    all_levels = yes_bids + yes_asks
    uniform_1c_grid = _extract_market_uniform_1c_grid(market_meta)
    all_levels_exact_cent = all(lv["exact_cent"] for lv in all_levels) if all_levels else False
    exact_cent_eligible = bool(all_levels_exact_cent and uniform_1c_grid)
    fractional_quantity_flag = any(lv["fractional_quantity_flag"] for lv in all_levels)

    return {
        "venue": "KALSHI",
        "contract_ticker": ticker.strip(),
        "captured_at_utc": captured_at_utc or _utc_now_iso(),
        "source_url": source_url,
        "data_provenance": "OBSERVED_L2",
        "yes_bids": yes_bids,
        "yes_asks": yes_asks,
        "best_yes_bid_pips": best_yes_bid_pips,
        "best_yes_bid_qty_centi": best_yes_bid_qty_centi,
        "best_no_bid_pips": best_no_bid_pips,
        "best_yes_ask_pips": best_yes_ask_pips,
        "best_yes_ask_qty_centi": best_yes_ask_qty_centi,
        "spread_pips": spread_pips,
        "book_quarantined": book_quarantined,
        "quarantine_reason": quarantine_reason,
        "uniform_1c_grid_10_90": uniform_1c_grid,
        "exact_cent_eligible": exact_cent_eligible,
        "fractional_quantity_flag": fractional_quantity_flag,
        "book_empty": len(all_levels) == 0,
    }


def normalize_polymarket_l2_v2(
    token_id: str,
    payload: Dict[str, Any],
    *,
    source_url: str,
    captured_at_utc: Optional[str] = None,
) -> Dict[str, Any]:
    """Normalize Polymarket CLOB L2 book into 3-unit exact integers (read-only BENCHMARK_ONLY)."""
    bids_raw = payload.get("bids") or []
    asks_raw = payload.get("asks") or []

    yes_bids: List[Dict[str, Any]] = []
    for lv in bids_raw:
        parsed = parse_book_level(
            lv["price"],
            lv["size"],
            price_input_unit="dollars",
            truncate_sub_centi=True,
        )
        if parsed["qty_centi"] > 0:
            yes_bids.append(parsed)

    yes_asks: List[Dict[str, Any]] = []
    for lv in asks_raw:
        parsed = parse_book_level(
            lv["price"],
            lv["size"],
            price_input_unit="dollars",
            truncate_sub_centi=True,
        )
        if parsed["qty_centi"] > 0:
            yes_asks.append(parsed)

    yes_bids.sort(key=lambda lv: lv["price_pips"], reverse=True)
    yes_asks.sort(key=lambda lv: lv["price_pips"])

    best_bid_pips = yes_bids[0]["price_pips"] if yes_bids else None
    best_bid_qty_centi = yes_bids[0]["qty_centi"] if yes_bids else 0
    best_ask_pips = yes_asks[0]["price_pips"] if yes_asks else None
    best_ask_qty_centi = yes_asks[0]["qty_centi"] if yes_asks else 0

    spread_pips: Optional[int] = None
    book_quarantined = False
    quarantine_reason: Optional[str] = None
    if best_bid_pips is not None and best_ask_pips is not None:
        spread_pips = best_ask_pips - best_bid_pips
        if spread_pips == 0:
            book_quarantined = True
            quarantine_reason = "LOCKED_BOOK"
        elif spread_pips < 0:
            book_quarantined = True
            quarantine_reason = "CROSSED_BOOK"

    all_levels = yes_bids + yes_asks
    exact_cent_eligible = all(lv["exact_cent"] for lv in all_levels) if all_levels else False
    fractional_quantity_flag = any(lv["fractional_quantity_flag"] for lv in all_levels)

    if book_quarantined:
        spread_bucket = "QUARANTINED_LOCKED_OR_CROSSED"
    elif spread_pips is None:
        spread_bucket = "ONE_SIDED"
    elif spread_pips == PIPS_PER_CENT:
        spread_bucket = "BENCHMARK_TIGHT_1C"
    else:
        spread_bucket = "BENCHMARK_REFERENCE"

    return {
        "venue": "POLYMARKET",
        "contract_ticker": token_id.strip(),
        "captured_at_utc": captured_at_utc or _utc_now_iso(),
        "source_url": source_url,
        "data_provenance": "OBSERVED_L2",
        "classification": "BENCHMARK_ONLY",
        "live_execution_eligible": False,
        "strategy_d_eligible": False,
        "strategy_d_replay_variant_eligible": False,
        "spread_bucket": spread_bucket,
        "yes_bids": yes_bids,
        "yes_asks": yes_asks,
        "best_yes_bid_pips": best_bid_pips,
        "best_yes_bid_qty_centi": best_bid_qty_centi,
        "best_yes_ask_pips": best_ask_pips,
        "best_yes_ask_qty_centi": best_ask_qty_centi,
        "spread_pips": spread_pips,
        "book_quarantined": book_quarantined,
        "quarantine_reason": quarantine_reason,
        "exact_cent_eligible": exact_cent_eligible,
        "fractional_quantity_flag": fractional_quantity_flag,
        "book_empty": len(all_levels) == 0,
    }


# ---------------------------------------------------------------------------
# 3. Deterministic Qualification & Anti-Survivorship Retention (CQP-001-v0.1)
# ---------------------------------------------------------------------------


def _parse_int_metric_centi(val: Any) -> int:
    """Parse volume/open-interest metric string or int into exact int64 centi-units (zero float)."""
    if val is None or isinstance(val, bool) or isinstance(val, float):
        return 0
    try:
        _, centi, _ = parse_qty_centi(val, truncate_sub_centi=True)
        return centi
    except (TypeError, ValueError, OverflowError):
        return 0


def _is_multivariate_combo(market: Dict[str, Any], banned_prefixes: Sequence[str]) -> bool:
    if market.get("is_mve") is True:
        return True
    if market.get("mve_collection_ticker"):
        return True
    legs = market.get("mve_selected_legs")
    if isinstance(legs, list) and len(legs) > 0:
        return True
    ticker_u = str(market.get("ticker", "")).upper()
    series_u = str(market.get("series_ticker", "")).upper()
    event_u = str(market.get("event_ticker", "")).upper()
    for pref in banned_prefixes:
        pu = pref.upper()
        if ticker_u.startswith(pu) or series_u.startswith(pu) or event_u.startswith(pu):
            return True
    for token in ("MULTIGAME", "PARLAY", "COMBO"):
        if token in ticker_u or token in series_u:
            return True
    return False


def _is_in_play_sports(market: Dict[str, Any], now_utc: datetime) -> bool:
    if market.get("in_play") is True or market.get("is_live") is True or market.get("game_started") is True:
        return True
    status = str(market.get("status", "")).strip().lower()
    if status in {"in_play", "live", "in-play"}:
        return True
    title_l = f"{market.get('title', '')} {market.get('subtitle', '')}".lower()
    if "in-play" in title_l or "in play" in title_l or "live game" in title_l:
        return True
    for key in ("event_start_time", "game_start_time", "start_time"):
        start_dt = _parse_utc_iso(market.get(key))
        if start_dt is not None and start_dt <= now_utc:
            return True
    return False


def classify_kalshi_market(
    market: Dict[str, Any],
    *,
    now_utc: datetime,
    config: Dict[str, Any] = DEFAULT_CQP_CONFIG,
) -> Tuple[Optional[str], str, Optional[int], Optional[str]]:
    """Deterministically classify a Kalshi market under CQP-001-v0.1.

    Returns (category, classification, priority_rank, reject_reason).
    """
    banned_prefixes = config.get("banned_prefixes") or ()
    banned_categories = {c.upper() for c in (config.get("banned_categories") or ())}

    if _is_multivariate_combo(market, banned_prefixes):
        return None, "REJECTED", None, "BANNED_MULTIVARIATE_COMBO"

    explicit_cat = str(market.get("category", "")).strip().upper()
    if explicit_cat in banned_categories:
        return None, "REJECTED", None, f"BANNED_CATEGORY_{explicit_cat}"

    ticker_u = str(market.get("ticker", "")).strip().upper()
    series_u = str(market.get("series_ticker", "")).strip().upper()
    event_u = str(market.get("event_ticker", "")).strip().upper()

    allowlist: Dict[str, List[str]] = config.get("series_allowlist") or {}
    priority_order: List[str] = list(config.get("priority_order") or [])
    benchmark_only_cats = set(config.get("benchmark_only_categories") or [])

    matched_category: Optional[str] = None
    for cat in priority_order:
        prefixes = allowlist.get(cat) or []
        if any(
            ticker_u.startswith(p.upper())
            or series_u.startswith(p.upper())
            or event_u.startswith(p.upper())
            for p in prefixes
        ):
            matched_category = cat
            break

    if matched_category is None:
        return None, "REJECTED", None, "NOT_IN_SERIES_ALLOWLIST"

    if matched_category == "PRE_GAME_SPORTS" and _is_in_play_sports(market, now_utc):
        return matched_category, "REJECTED", None, "BANNED_IN_PLAY_SPORTS"

    priority_rank = priority_order.index(matched_category) + 1
    classification = "BENCHMARK_ONLY" if matched_category in benchmark_only_cats else "CURATED_STRATEGY_D_CANDIDATE"
    return matched_category, classification, priority_rank, None


def evaluate_kalshi_admission(
    market: Dict[str, Any],
    *,
    now_utc: datetime,
    recording_window_end_utc: datetime,
    config: Dict[str, Any] = DEFAULT_CQP_CONFIG,
    filter_config_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate a single Kalshi market against CQP-001-v0.1 admission criteria."""
    cfg_hash = filter_config_hash or compute_filter_config_hash(config)
    ticker = str(market.get("ticker", "")).strip()
    status = str(market.get("status", "open")).strip().lower()
    reasons: List[str] = []

    if not ticker:
        reasons.append("MISSING_TICKER")
    if status not in {"open", "active"}:
        reasons.append(f"STATUS_NOT_OPEN:{status}")

    category, classification, priority_rank, cat_reject = classify_kalshi_market(
        market, now_utc=now_utc, config=config
    )
    if cat_reject:
        reasons.append(cat_reject)

    close_dt = _parse_utc_iso(market.get("close_time") or market.get("expiration_time"))
    seconds_to_close: Optional[int] = None
    if close_dt is None:
        reasons.append("MISSING_OR_INVALID_CLOSE_TIME")
    else:
        seconds_to_close = int((close_dt - now_utc).total_seconds())
        min_sec = int(config["min_hours_to_close"]) * 3600
        max_sec = int(config["max_hours_to_close"]) * 3600
        buffer_sec = int(config["settlement_buffer_hours"]) * 3600
        if seconds_to_close < min_sec:
            reasons.append("CLOSE_TIME_LT_1H")
        elif seconds_to_close > max_sec:
            reasons.append("CLOSE_TIME_GT_168H_NOVELTY_OR_LONG_HORIZON")
        if close_dt + timedelta(seconds=buffer_sec) > recording_window_end_utc:
            reasons.append("SETTLEMENT_EXCEEDS_RECORDING_WINDOW")

    uniform_1c_grid = _extract_market_uniform_1c_grid(market)
    admitted = len(reasons) == 0
    return {
        "venue": "KALSHI",
        "contract_ticker": ticker,
        "policy_id": config.get("policy_id", CQP_POLICY_VERSION),
        "filter_config_hash": cfg_hash,
        "decision": "ADMIT" if admitted else "REJECT",
        "admitted": admitted,
        "category": category,
        "classification": classification if admitted else "REJECTED",
        "priority_rank": priority_rank,
        "live_execution_eligible": False,
        "seconds_to_close": seconds_to_close,
        "close_time_utc": _utc_now_iso(close_dt) if close_dt is not None else None,
        "uniform_1c_grid_10_90": uniform_1c_grid,
        "volume_24h_centi": _parse_int_metric_centi(market.get("volume_24h_fp", market.get("volume_24h"))),
        "open_interest_centi": _parse_int_metric_centi(market.get("open_interest_fp", market.get("open_interest"))),
        "reasons": reasons,
    }


@dataclass
class TrackedContract:
    ticker: str
    category: str
    classification: str  # CURATED_STRATEGY_D_CANDIDATE | BENCHMARK_ONLY
    priority_rank: int
    admitted_at_utc: str
    close_time_utc: Optional[str]
    uniform_1c_grid_10_90: bool = True
    market_meta: Dict[str, Any] = field(default_factory=dict)
    lifecycle_state: str = "ACTIVE"  # ACTIVE | SETTLED_PENDING_FINAL_SNAP | SETTLED_COMPLETE
    settlement_emitted: bool = False
    settlement_result: Optional[str] = None
    post_settlement_snapshots_captured: int = 0
    consecutive_strategy_d_snapshots: int = 0
    consecutive_replay_variant_snapshots: int = 0

    def occupies_basket_slot(self) -> bool:
        return self.lifecycle_state != "SETTLED_COMPLETE"


class ContractLifecycleTracker:
    """Manages deterministic admission, anti-survivorship retention, settlement, and Strategy D tradeability."""

    def __init__(
        self,
        *,
        config: Optional[Dict[str, Any]] = None,
        recording_window_end_utc: Optional[datetime] = None,
    ) -> None:
        self.config: Dict[str, Any] = copy.deepcopy(config or DEFAULT_CQP_CONFIG)
        self.filter_config_hash = compute_filter_config_hash(self.config)
        self.max_curated_cap = int(self.config.get("max_curated_kalshi_contracts", MAX_CURATED_KALSHI_CONTRACTS))
        days = int(self.config.get("recording_window_days", 14))
        self.recording_window_end_utc = recording_window_end_utc or (
            datetime.now(timezone.utc) + timedelta(days=days)
        )
        self.contracts: Dict[str, TrackedContract] = {}

    def active_tickers(self) -> List[str]:
        """Return all admitted tickers that must continue to be polled (including awaiting +1 post-settlement snap)."""
        return sorted(
            t for t, st in self.contracts.items() if st.occupies_basket_slot()
        )

    def mark_settlement_observed(
        self,
        ticker: str,
        *,
        result: Optional[str],
        settlement_value_pips: Optional[int],
        settled_at_utc: Optional[str],
        market_status: str = "settled",
    ) -> Optional[Dict[str, Any]]:
        """Transition a retained contract to SETTLED_PENDING_FINAL_SNAP and build SETTLEMENT_EVENT payload."""
        st = self.contracts.get(ticker)
        if st is None or st.settlement_emitted:
            return None
        st.settlement_emitted = True
        st.settlement_result = result
        st.lifecycle_state = "SETTLED_PENDING_FINAL_SNAP"
        st.consecutive_strategy_d_snapshots = 0
        st.consecutive_replay_variant_snapshots = 0
        return {
            "venue": "KALSHI",
            "contract_ticker": ticker,
            "category": st.category,
            "classification": st.classification,
            "market_status": market_status,
            "settlement_result": result,
            "settlement_value_pips": settlement_value_pips,
            "settled_at_utc": settled_at_utc or _utc_now_iso(),
            "post_settlement_snapshot_required": True,
            "anti_survivorship_retained": True,
        }

    def reconcile_admission_scan(
        self,
        markets: Sequence[Dict[str, Any]],
        *,
        now_utc: datetime,
    ) -> Dict[str, Any]:
        """Reconcile a /markets scan against retained contracts without ever evicting active contracts mid-life."""
        decisions: List[Dict[str, Any]] = []
        newly_admitted: List[Dict[str, Any]] = []
        settlements: List[Dict[str, Any]] = []
        candidates: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []

        markets_by_ticker: Dict[str, Dict[str, Any]] = {}
        for m in markets:
            if isinstance(m, dict) and m.get("ticker"):
                markets_by_ticker[str(m["ticker"]).strip()] = m

        # 1. Check retained contracts for settlement or metadata updates (NEVER evict mid-life!)
        for ticker, st in list(self.contracts.items()):
            if not st.occupies_basket_slot():
                continue
            m = markets_by_ticker.get(ticker)
            if m is not None:
                st.market_meta = dict(m)
                st.uniform_1c_grid_10_90 = _extract_market_uniform_1c_grid(m)
                status = str(m.get("status", "")).strip().lower()
                result = m.get("result")
                if status in {"settled", "finalized", "determined"} or (
                    isinstance(result, str) and result.strip().lower() in {"yes", "no", "all_no", "all_yes", "scalar"}
                ):
                    norm_res = str(result).strip().lower() if result is not None else None
                    settle_pips: Optional[int] = None
                    if norm_res == "yes":
                        settle_pips = PIPS_PER_DOLLAR
                    elif norm_res == "no":
                        settle_pips = 0
                    ev = self.mark_settlement_observed(
                        ticker,
                        result=norm_res,
                        settlement_value_pips=settle_pips,
                        settled_at_utc=m.get("settlement_ts") or m.get("close_time") or _utc_now_iso(now_utc),
                        market_status=status or "settled",
                    )
                    if ev is not None:
                        settlements.append(ev)

            decisions.append(
                {
                    "venue": "KALSHI",
                    "contract_ticker": ticker,
                    "policy_id": self.config.get("policy_id", CQP_POLICY_VERSION),
                    "filter_config_hash": self.filter_config_hash,
                    "decision": "RETAIN",
                    "admitted": True,
                    "category": st.category,
                    "classification": st.classification,
                    "priority_rank": st.priority_rank,
                    "lifecycle_state": st.lifecycle_state,
                    "reasons": ["ANTI_SURVIVORSHIP_RETENTION"],
                }
            )

        # 2. Evaluate new candidate markets
        for ticker, m in sorted(markets_by_ticker.items()):
            if ticker in self.contracts:
                continue
            dec = evaluate_kalshi_admission(
                m,
                now_utc=now_utc,
                recording_window_end_utc=self.recording_window_end_utc,
                config=self.config,
                filter_config_hash=self.filter_config_hash,
            )
            if dec["admitted"]:
                candidates.append((dec, m))
            else:
                decisions.append(dec)

        # 3. Deterministic priority ranking: Priority tier ASC -> 24h volume DESC -> OI DESC -> ticker ASC
        candidates.sort(
            key=lambda pair: (
                int(pair[0]["priority_rank"] or 999),
                -int(pair[0]["volume_24h_centi"]),
                -int(pair[0]["open_interest_centi"]),
                pair[0]["contract_ticker"],
            )
        )

        occupied_slots = sum(1 for st in self.contracts.values() if st.occupies_basket_slot())
        remaining_slots = max(0, self.max_curated_cap - occupied_slots)

        for dec, m in candidates:
            if remaining_slots > 0:
                ticker = dec["contract_ticker"]
                st = TrackedContract(
                    ticker=ticker,
                    category=str(dec["category"]),
                    classification=str(dec["classification"]),
                    priority_rank=int(dec["priority_rank"]),
                    admitted_at_utc=_utc_now_iso(now_utc),
                    close_time_utc=dec["close_time_utc"],
                    uniform_1c_grid_10_90=bool(dec["uniform_1c_grid_10_90"]),
                    market_meta=dict(m),
                )
                self.contracts[ticker] = st
                remaining_slots -= 1
                decisions.append(dec)
                newly_admitted.append(
                    {
                        "venue": "KALSHI",
                        "contract_ticker": ticker,
                        "event_ticker": m.get("event_ticker"),
                        "series_ticker": m.get("series_ticker"),
                        "title": m.get("title"),
                        "status": m.get("status", "open"),
                        "category": st.category,
                        "classification": st.classification,
                        "priority_rank": st.priority_rank,
                        "close_time_utc": st.close_time_utc,
                        "uniform_1c_grid_10_90": st.uniform_1c_grid_10_90,
                        "price_ranges": m.get("price_ranges"),
                        "volume_24h_centi": dec["volume_24h_centi"],
                        "open_interest_centi": dec["open_interest_centi"],
                        "admitted_at_utc": st.admitted_at_utc,
                    }
                )
            else:
                cap_dec = dict(dec)
                cap_dec["decision"] = "REJECT"
                cap_dec["admitted"] = False
                cap_dec["classification"] = "REJECTED"
                cap_dec["reasons"] = list(dec["reasons"]) + ["CURATED_BASKET_CAP_REACHED"]
                decisions.append(cap_dec)

        return {
            "decisions": decisions,
            "newly_admitted": newly_admitted,
            "settlements": settlements,
            "active_tickers": self.active_tickers(),
        }

    def evaluate_snapshot_tradeability(self, ticker: str, snap: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate per-snapshot Strategy D tradeability and anti-survivorship post-settlement completion."""
        rules = self.config["strategy_d_rules"]
        min_price = int(rules["min_price_pips"])
        max_price = int(rules["max_price_pips"])
        min_spread = int(rules["default_min_spread_pips"])
        max_spread = int(rules["default_max_spread_pips"])
        variant_spread = int(rules["replay_variant_spread_pips"])
        obs_only_max_spread = int(rules["observation_only_max_spread_pips"])
        min_consec = int(rules["min_consecutive_snapshots"])
        min_depth = int(rules["min_top_depth_centi"])

        st = self.contracts.get(ticker)
        classification = st.classification if st is not None else snap.get("classification", "OBSERVATION_ONLY")
        category = st.category if st is not None else snap.get("category")

        # Handle +1 post-settlement snapshot tracking
        is_post_settlement_snapshot = False
        if st is not None and st.lifecycle_state == "SETTLED_PENDING_FINAL_SNAP":
            is_post_settlement_snapshot = True
            st.post_settlement_snapshots_captured += 1
            if st.post_settlement_snapshots_captured >= 1:
                st.lifecycle_state = "SETTLED_COMPLETE"

        spread_pips = snap.get("spread_pips")
        best_bid_pips = snap.get("best_yes_bid_pips")
        best_ask_pips = snap.get("best_yes_ask_pips")
        bid_qty = int(snap.get("best_yes_bid_qty_centi") or 0)
        ask_qty = int(snap.get("best_yes_ask_qty_centi") or 0)
        exact_cent = bool(snap.get("exact_cent_eligible"))
        quarantined = bool(snap.get("book_quarantined"))

        if quarantined:
            spread_bucket = "QUARANTINED_LOCKED_OR_CROSSED"
        elif spread_pips is None:
            spread_bucket = "ONE_SIDED"
        elif spread_pips <= obs_only_max_spread:
            spread_bucket = "OBSERVATION_ONLY_TIGHT_1C_2C"
        elif spread_pips == variant_spread:
            spread_bucket = "REPLAY_VARIANT_3C"
        elif min_spread <= spread_pips <= max_spread:
            spread_bucket = "STRATEGY_D_DEFAULT_4C_10C"
        else:
            spread_bucket = "WIDE_GT_10C"

        base_reasons: List[str] = []
        if classification == "BENCHMARK_ONLY":
            base_reasons.append("BENCHMARK_ONLY_NEVER_STRATEGY_D")
        if is_post_settlement_snapshot or (st is not None and st.settlement_emitted):
            base_reasons.append("CONTRACT_SETTLED")
        if quarantined:
            base_reasons.append(f"BOOK_QUARANTINED:{snap.get('quarantine_reason')}")
        if not exact_cent:
            base_reasons.append("NOT_EXACT_CENT_ELIGIBLE")
        if best_bid_pips is None or best_ask_pips is None or spread_pips is None:
            base_reasons.append("INCOMPLETE_TWO_SIDED_BOOK")
        else:
            if not (min_price <= best_bid_pips <= max_price and min_price <= best_ask_pips <= max_price):
                base_reasons.append("PRICE_OUTSIDE_10C_90C_BAND")
        if bid_qty < min_depth or ask_qty < min_depth:
            base_reasons.append("TOP_DEPTH_LT_100_CONTRACTS")

        default_spread_ok = (spread_pips is not None) and (min_spread <= spread_pips <= max_spread)
        variant_spread_ok = (spread_pips is not None) and (spread_pips == variant_spread)

        consec_default = 0
        consec_variant = 0
        if st is not None:
            if not base_reasons and default_spread_ok:
                st.consecutive_strategy_d_snapshots += 1
            else:
                st.consecutive_strategy_d_snapshots = 0

            if not base_reasons and variant_spread_ok:
                st.consecutive_replay_variant_snapshots += 1
            else:
                st.consecutive_replay_variant_snapshots = 0

            consec_default = st.consecutive_strategy_d_snapshots
            consec_variant = st.consecutive_replay_variant_snapshots
        else:
            consec_default = 1 if (not base_reasons and default_spread_ok) else 0
            consec_variant = 1 if (not base_reasons and variant_spread_ok) else 0

        reasons = list(base_reasons)
        if not default_spread_ok:
            reasons.append(f"SPREAD_OUTSIDE_4C_10C:{spread_bucket}")
        elif consec_default < min_consec:
            reasons.append("PENDING_CONSECUTIVE_CONFIRMATION")

        strategy_d_eligible = bool(not base_reasons and default_spread_ok and consec_default >= min_consec)
        strategy_d_replay_variant_eligible = bool(
            not base_reasons and variant_spread_ok and consec_variant >= min_consec
        )

        enriched = dict(snap)
        enriched.update(
            {
                "category": category,
                "classification": classification,
                "live_execution_eligible": False,
                "spread_bucket": spread_bucket,
                "strategy_d_eligible": strategy_d_eligible,
                "strategy_d_replay_variant_eligible": strategy_d_replay_variant_eligible,
                "consecutive_strategy_d_snapshots": consec_default,
                "consecutive_replay_variant_snapshots": consec_variant,
                "strategy_d_ineligibility_reasons": [] if strategy_d_eligible else reasons,
                "post_settlement_snapshot": is_post_settlement_snapshot,
                "lifecycle_state": st.lifecycle_state if st is not None else "UNTRACKED_BASELINE",
            }
        )
        return enriched


# ---------------------------------------------------------------------------
# 4. Rate-Limit Governor (<= 2 req/s) & Adaptive 429 Backoff
# ---------------------------------------------------------------------------


class RateLimitGovernor:
    """Enforces <= max_req_per_sec hard cap and adaptive 429 backoff + cadence degradation."""

    def __init__(
        self,
        *,
        max_req_per_sec: int = 2,
        base_backoff_seconds: int = 5,
        max_backoff_seconds: int = 300,
        cadence_ladder: Tuple[int, ...] = CURATED_CADENCE_LADDER,
        monotonic_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
        jitter_fn: Optional[Callable[[int], int]] = None,
    ) -> None:
        self.max_req_per_sec = max(1, int(max_req_per_sec))
        self.base_backoff_seconds = max(1, int(base_backoff_seconds))
        self.max_backoff_seconds = max(self.base_backoff_seconds, int(max_backoff_seconds))
        self.cadence_ladder = tuple(int(x) for x in cadence_ladder)
        self._monotonic = monotonic_fn
        self._sleep = sleep_fn
        self._jitter_fn = jitter_fn or self._default_jitter_ms

        self._request_timestamps: collections.deque[float] = collections.deque()
        self.cadence_index: int = 0
        self.n_429: int = 0
        self.consecutive_429: int = 0
        self.clean_cycles_since_429: int = 0
        self.total_requests: int = 0

    @staticmethod
    def _default_jitter_ms(base_ms: int) -> int:
        upper = max(1, base_ms // 4)
        return random.randint(0, upper)

    @property
    def current_curated_cadence_seconds(self) -> int:
        return self.cadence_ladder[self.cadence_index]

    def acquire(self) -> None:
        """Block if needed so outbound HTTP requests never exceed max_req_per_sec."""
        now = self._monotonic()
        while self._request_timestamps and (now - self._request_timestamps[0]) >= 1.0:
            self._request_timestamps.popleft()

        if len(self._request_timestamps) >= self.max_req_per_sec:
            wait = 1.0 - (now - self._request_timestamps[0])
            if wait > 0:
                self._sleep(wait)
                now = self._monotonic()
                while self._request_timestamps and (now - self._request_timestamps[0]) >= 1.0:
                    self._request_timestamps.popleft()

        self._request_timestamps.append(now)
        self.total_requests += 1

    def record_http_429(self) -> Dict[str, Any]:
        """Handle HTTP 429 (Kalshi sends no Retry-After): 5s + exp backoff + jitter up to 300s, degrade cadence."""
        self.n_429 += 1
        self.consecutive_429 += 1
        self.clean_cycles_since_429 = 0

        if self.cadence_index < len(self.cadence_ladder) - 1:
            self.cadence_index += 1

        exp_sec = min(
            self.base_backoff_seconds * (1 << min(self.consecutive_429 - 1, 10)),
            self.max_backoff_seconds,
        )
        base_ms = exp_sec * 1000
        max_ms = self.max_backoff_seconds * 1000
        jitter_ms = max(0, int(self._jitter_fn(base_ms)))
        total_ms = min(max_ms, base_ms + jitter_ms)
        total_sec_int = (total_ms + 999) // 1000

        return {
            "n_429": self.n_429,
            "consecutive_429": self.consecutive_429,
            "backoff_ms": total_ms,
            "backoff_seconds": total_sec_int,
            "degraded_curated_cadence_seconds": self.current_curated_cadence_seconds,
        }

    def note_clean_cycle(self, *, recovery_threshold: int = 10) -> None:
        """Gradually step curated cadence back down after sustained 429-free cycles."""
        self.consecutive_429 = 0
        self.clean_cycles_since_429 += 1
        if self.cadence_index > 0 and self.clean_cycles_since_429 >= recovery_threshold:
            self.cadence_index -= 1
            self.clean_cycles_since_429 = 0


# ---------------------------------------------------------------------------
# 5. Public Trades Poller (Overlapping 120s Window + Cursor Pagination + Dedup)
# ---------------------------------------------------------------------------


class TradeDeduplicator:
    """Memory-bounded O(1) trade_id deduplicator safe for 128 MB Lightsail RAM."""

    def __init__(self, max_entries: int = 50_000) -> None:
        self.max_entries = max(100, int(max_entries))
        self._seen: collections.OrderedDict[str, int] = collections.OrderedDict()

    def mark_if_new(self, trade_id: str, ts_epoch_s: int = 0) -> bool:
        tid = trade_id.strip()
        if not tid:
            return False
        if tid in self._seen:
            self._seen.move_to_end(tid)
            return False
        self._seen[tid] = int(ts_epoch_s)
        while len(self._seen) > self.max_entries:
            self._seen.popitem(last=False)
        return True

    def __len__(self) -> int:
        return len(self._seen)


def parse_kalshi_trade_v2(
    raw_trade: Dict[str, Any],
    *,
    window_min_ts: int,
    window_max_ts: int,
    window_completeness_status: str,
) -> Dict[str, Any]:
    """Parse a Kalshi public trade payload into 3-unit exact int64 representation."""
    trade_id = str(raw_trade.get("trade_id", "")).strip()
    ticker = str(raw_trade.get("ticker", raw_trade.get("market_ticker", ""))).strip()

    if "yes_price_dollars" in raw_trade and raw_trade["yes_price_dollars"] is not None:
        yes_price_raw, yes_price_pips = parse_price_pips(
            raw_trade["yes_price_dollars"], input_unit="dollars", allow_zero=True, allow_dollar_one=True
        )
    elif "yes_price" in raw_trade and raw_trade["yes_price"] is not None:
        raw_yp = raw_trade["yes_price"]
        unit = "dollars" if isinstance(raw_yp, str) and "." in raw_yp else "cents"
        yes_price_raw, yes_price_pips = parse_price_pips(
            raw_yp, input_unit=unit, allow_zero=True, allow_dollar_one=True
        )
    elif "price" in raw_trade and raw_trade["price"] is not None:
        yes_price_raw, yes_price_pips = parse_price_pips(
            raw_trade["price"], input_unit="dollars", allow_zero=True, allow_dollar_one=True
        )
    else:
        raise ValueError(f"Kalshi trade {trade_id!r} missing yes_price_dollars/yes_price")

    if "no_price_dollars" in raw_trade and raw_trade["no_price_dollars"] is not None:
        no_price_raw, no_price_pips = parse_price_pips(
            raw_trade["no_price_dollars"], input_unit="dollars", allow_zero=True, allow_dollar_one=True
        )
    elif "no_price" in raw_trade and raw_trade["no_price"] is not None:
        raw_np = raw_trade["no_price"]
        unit = "dollars" if isinstance(raw_np, str) and "." in raw_np else "cents"
        no_price_raw, no_price_pips = parse_price_pips(
            raw_np, input_unit=unit, allow_zero=True, allow_dollar_one=True
        )
    else:
        no_price_pips = PIPS_PER_DOLLAR - yes_price_pips
        no_price_raw = _format_pips_as_dollar_str(no_price_pips)

    raw_count = raw_trade.get("count_fp", raw_trade.get("count"))
    if raw_count is None:
        raise ValueError(f"Kalshi trade {trade_id!r} missing count_fp/count")
    count_raw, count_centi, frac_qty = parse_qty_centi(raw_count)
    micro_dollars = compute_micro_dollars(yes_price_pips, count_centi)

    taker_side = str(raw_trade.get("taker_side", "unknown")).strip().lower() or "unknown"
    is_block_trade = bool(raw_trade.get("is_block_trade", raw_trade.get("block_trade", False)))

    return {
        "venue": "KALSHI",
        "trade_id": trade_id,
        "contract_ticker": ticker,
        "yes_price_raw": yes_price_raw,
        "yes_price_pips": yes_price_pips,
        "no_price_raw": no_price_raw,
        "no_price_pips": no_price_pips,
        "count_raw": count_raw,
        "count_centi": count_centi,
        "micro_dollars": micro_dollars,
        "exact_cent_eligible": (yes_price_pips % PIPS_PER_CENT) == 0,
        "fractional_quantity_flag": frac_qty,
        "taker_side": taker_side,
        "is_block_trade": is_block_trade,
        "created_time": raw_trade.get("created_time"),
        "window_min_ts": int(window_min_ts),
        "window_max_ts": int(window_max_ts),
        "window_completeness_status": window_completeness_status,
    }


def _extract_batched_orderbooks(
    payload: Any,
    requested_tickers: Sequence[str],
) -> Dict[str, Dict[str, Any]]:
    """Extract ticker -> orderbook payload map from Kalshi batched /markets/orderbooks responses."""
    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(payload, dict):
        return out

    obs = payload.get("orderbooks")
    if isinstance(obs, list):
        for item in obs:
            if not isinstance(item, dict):
                continue
            tk = str(item.get("ticker") or item.get("market_ticker") or "").strip()
            if tk:
                out[tk] = item
    elif isinstance(obs, dict):
        for tk, item in obs.items():
            if isinstance(item, dict):
                out[str(tk).strip()] = item
    elif len(requested_tickers) == 1 and ("orderbook_fp" in payload or "orderbook" in payload):
        out[requested_tickers[0]] = payload
    return out


# ---------------------------------------------------------------------------
# 6. Streaming Append-Only JSONL v2.0 Writer & Rolling SHA-256 Manifest
# ---------------------------------------------------------------------------


def _assert_no_floats(obj: Any, path: str = "$") -> None:
    """Recursively assert zero float values exist inside any JSONL v2.0 record."""
    if isinstance(obj, float):
        raise ValueError(f"Floating-point value prohibited in JSONL v2.0 at {path}: {obj!r}")
    if isinstance(obj, dict):
        for k, v in obj.items():
            _assert_no_floats(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for idx, item in enumerate(obj):
            _assert_no_floats(item, f"{path}[{idx}]")


class StreamingTapeWriterV2:
    """Append-only Schema v2.0.0 JSONL writer with O(1)-RAM rolling SHA-256 manifest."""

    def __init__(
        self,
        session_dir: Path,
        *,
        filter_config_hash: str,
        collector_git_sha: Optional[str] = None,
        time_ns_fn: Callable[[], int] = time.time_ns,
    ) -> None:
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.tape_path = self.session_dir / "tape.jsonl"
        self.manifest_path = self.session_dir / "tape_manifest.json"
        self.filter_config_hash = filter_config_hash
        self.collector_git_sha = collector_git_sha or resolve_collector_git_sha()
        self._time_ns = time_ns_fn

        self._rolling_sha256 = hashlib.sha256()
        self.capture_sequence: int = 0
        self.bytes_written: int = 0
        self.record_count: int = 0
        self.record_type_counts: Dict[str, int] = {rt: 0 for rt in sorted(RECORD_TYPES)}
        self.venues: set[str] = set()
        self.first_captured_at_utc: Optional[str] = None
        self.last_captured_at_utc: Optional[str] = None
        self._last_ts_us: int = 0

        # If resuming an existing tape file, stream-hash it in 64 KB chunks (never read_bytes() whole file)
        if self.tape_path.exists() and self.tape_path.stat().st_size > 0:
            self._hydrate_existing_tape_streaming()

    def _hydrate_existing_tape_streaming(self) -> None:
        with self.tape_path.open("rb") as fh:
            for raw_line in fh:
                self._rolling_sha256.update(raw_line)
                self.bytes_written += len(raw_line)
                stripped = raw_line.strip()
                if not stripped:
                    continue
                self.record_count += 1
                try:
                    rec = json.loads(stripped.decode("utf-8"))
                except Exception:
                    continue
                seq = rec.get("capture_sequence")
                if isinstance(seq, int) and seq > self.capture_sequence:
                    self.capture_sequence = seq
                rt = rec.get("record_type")
                if rt in self.record_type_counts:
                    self.record_type_counts[rt] += 1
                if rec.get("venue"):
                    self.venues.add(str(rec["venue"]))
                ts_str = rec.get("captured_at_utc")
                if isinstance(ts_str, str):
                    if self.first_captured_at_utc is None:
                        self.first_captured_at_utc = ts_str
                    self.last_captured_at_utc = ts_str

    def _next_monotonic_utc(self, explicit_utc: Optional[str] = None) -> str:
        if explicit_utc is not None:
            dt = _parse_utc_iso(explicit_utc)
            if dt is not None:
                ts_us = int(dt.timestamp() * 1_000_000)
                if ts_us > self._last_ts_us:
                    self._last_ts_us = ts_us
            return explicit_utc
        now_us = self._time_ns() // 1000
        if now_us <= self._last_ts_us:
            now_us = self._last_ts_us + 1
        self._last_ts_us = now_us
        dt = datetime.fromtimestamp(now_us // 1_000_000, tz=timezone.utc).replace(
            microsecond=now_us % 1_000_000
        )
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def append_record(
        self,
        record_type: str,
        payload: Dict[str, Any],
        *,
        t_req_sent_ns: Optional[int] = None,
        t_resp_recv_ns: Optional[int] = None,
        http_status: Optional[int] = None,
        raw_payload_bytes: Optional[bytes] = None,
        captured_at_utc: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append a single Schema v2.0.0 record and update rolling SHA-256 in O(1) RAM."""
        if record_type not in RECORD_TYPES:
            raise ValueError(f"Unsupported record_type={record_type!r}; expected one of {sorted(RECORD_TYPES)}")

        now_ns = self._time_ns()
        sent_ns = int(t_req_sent_ns) if t_req_sent_ns is not None else now_ns
        recv_ns = int(t_resp_recv_ns) if t_resp_recv_ns is not None else max(sent_ns, now_ns)
        if recv_ns < sent_ns:
            recv_ns = sent_ns

        self.capture_sequence += 1
        ts_iso = self._next_monotonic_utc(captured_at_utc)

        if raw_payload_bytes is None:
            raw_payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        raw_sha = hashlib.sha256(raw_payload_bytes).hexdigest()

        record: Dict[str, Any] = dict(payload)
        record.update(
            {
                "schema_version": SCHEMA_VERSION_V2,
                "record_type": record_type,
                "collector_git_sha": self.collector_git_sha,
                "filter_config_hash": self.filter_config_hash,
                "capture_sequence": self.capture_sequence,
                "t_req_sent_ns": sent_ns,
                "t_resp_recv_ns": recv_ns,
                "http_status": int(http_status) if http_status is not None else None,
                "raw_payload_sha256": raw_sha,
                "synthetic_fills_present": False,
                "data_provenance": "OBSERVED_L2",
                "captured_at_utc": ts_iso,
            }
        )

        _assert_no_floats(record)

        line_bytes = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        with self.tape_path.open("ab") as fh:
            fh.write(line_bytes)

        self._rolling_sha256.update(line_bytes)
        self.bytes_written += len(line_bytes)
        self.record_count += 1
        self.record_type_counts[record_type] += 1
        if record.get("venue"):
            self.venues.add(str(record["venue"]))
        if self.first_captured_at_utc is None:
            self.first_captured_at_utc = ts_iso
        self.last_captured_at_utc = ts_iso
        return record

    def rolling_manifest(self) -> Dict[str, Any]:
        """Return strictly O(1)-size rolling SHA-256 manifest snapshot without re-reading tape.jsonl."""
        return {
            "schema_version": SCHEMA_VERSION_V2,
            "data_provenance": "OBSERVED_L2",
            "tape_file": self.tape_path.name,
            "tape_manifest_sha256": self._rolling_sha256.copy().hexdigest(),
            "bytes_written": self.bytes_written,
            "bytes_hashed": self.bytes_written,
            "record_count": self.record_count,
            "records_hashed": self.record_count,
            "snapshot_count": self.record_type_counts["OBSERVED_L2"],
            "record_type_counts": dict(self.record_type_counts),
            "capture_sequence": self.capture_sequence,
            "collector_git_sha": self.collector_git_sha,
            "filter_config_hash": self.filter_config_hash,
            "venues": sorted(self.venues),
            "first_captured_at_utc": self.first_captured_at_utc,
            "last_captured_at_utc": self.last_captured_at_utc,
            "read_only_capture": True,
            "synthetic_fills_present": False,
        }

    def write_manifest_file(self) -> Dict[str, Any]:
        """Atomically persist tape_manifest.json from the O(1) rolling manifest state."""
        manifest = self.rolling_manifest()
        tmp_path = self.manifest_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_path.replace(self.manifest_path)
        return manifest


def verify_v2_tape_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Fail-closed verifier for Schema v2.0.0 tapes: SHA-256, zero floats, monotonic sequence, exact int math."""
    mpath = Path(manifest_path)
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION_V2:
        raise ValueError(f"Expected schema_version={SCHEMA_VERSION_V2!r}, got {manifest.get('schema_version')!r}")
    if manifest.get("data_provenance") != "OBSERVED_L2":
        raise ValueError("Manifest provenance must be OBSERVED_L2")
    if manifest.get("synthetic_fills_present") is not False:
        raise ValueError("Manifest failed zero-synthetic check")

    tape_path = mpath.parent / manifest["tape_file"]
    hasher = hashlib.sha256()
    line_count = 0
    prev_seq = 0
    prev_ts: Optional[datetime] = None

    def _reject_float(val: str) -> Any:
        raise ValueError(f"Float rejected in v2 tape: {val}")

    required_envelope = (
        "schema_version",
        "record_type",
        "collector_git_sha",
        "filter_config_hash",
        "capture_sequence",
        "t_req_sent_ns",
        "t_resp_recv_ns",
        "http_status",
        "raw_payload_sha256",
        "synthetic_fills_present",
        "captured_at_utc",
    )

    with tape_path.open("rb") as fh:
        for idx, raw_line in enumerate(fh):
            hasher.update(raw_line)
            if not raw_line.strip():
                continue
            line_count += 1
            rec = json.loads(raw_line.decode("utf-8"), parse_float=_reject_float)
            for key in required_envelope:
                if key not in rec:
                    raise ValueError(f"Line {idx} missing envelope key {key!r}")
            if rec["schema_version"] != SCHEMA_VERSION_V2:
                raise ValueError(f"Line {idx} schema_version mismatch: {rec['schema_version']!r}")
            if rec["record_type"] not in RECORD_TYPES:
                raise ValueError(f"Line {idx} invalid record_type: {rec['record_type']!r}")
            if rec["synthetic_fills_present"] is not False:
                raise ValueError(f"Line {idx} violated zero-synthetic invariant")

            seq = rec["capture_sequence"]
            if not isinstance(seq, int) or seq != prev_seq + 1:
                raise ValueError(f"Line {idx} non-monotonic capture_sequence: expected {prev_seq + 1}, got {seq}")
            prev_seq = seq

            ts = _parse_utc_iso(rec["captured_at_utc"])
            if ts is None:
                raise ValueError(f"Line {idx} invalid captured_at_utc: {rec['captured_at_utc']!r}")
            if prev_ts is not None and ts < prev_ts:
                raise ValueError(f"Line {idx} non-monotonic captured_at_utc")
            prev_ts = ts

            if rec["record_type"] == "OBSERVED_L2":
                for side in ("yes_bids", "yes_asks"):
                    for lv in rec.get(side) or []:
                        if lv["price_pips"] * lv["qty_centi"] != lv["micro_dollars"]:
                            raise ValueError(f"Line {idx} violated exact 3-unit identity price_pips * qty_centi == micro_dollars")
            elif rec["record_type"] == "OBSERVED_TRADE":
                if rec["yes_price_pips"] * rec["count_centi"] != rec["micro_dollars"]:
                    raise ValueError(f"Line {idx} trade violated exact 3-unit identity")

    actual_sha = hasher.hexdigest()
    if actual_sha != manifest.get("tape_manifest_sha256"):
        raise ValueError("SHA-256 tamper mismatch between tape_manifest.json and tape.jsonl")
    if line_count != manifest.get("record_count"):
        raise ValueError(f"Record count mismatch: manifest={manifest.get('record_count')}, actual={line_count}")

    return manifest


# ---------------------------------------------------------------------------
# 7. ObservedL2CollectorV2 Orchestrator
# ---------------------------------------------------------------------------


class ObservedL2CollectorV2:
    """Schema v2.0.0 read-only tiered market collector for Gate G1 / G2A 14-day Lightsail recording."""

    def __init__(
        self,
        tape_root: Path,
        *,
        kalshi_base_url: str = KALSHI_EXTERNAL_API_BASE,
        poly_clob_base_url: str = POLYMARKET_PUBLIC_BASE,
        poly_gamma_base_url: str = POLYMARKET_GAMMA_BASE,
        cqp_config: Optional[Dict[str, Any]] = None,
        curated_interval_seconds: int = 10,
        trades_interval_seconds: int = 10,
        baseline_interval_seconds: int = BASELINE_POLL_INTERVAL_SECONDS,
        admission_interval_seconds: int = ADMISSION_INTERVAL_SECONDS,
        trades_window_seconds: int = TRADES_OVERLAP_WINDOW_SECONDS,
        kalshi_baseline_count: int = 4,
        poly_benchmark_count: int = MAX_POLYMARKET_BENCHMARK_CONTRACTS,
        max_req_per_sec: int = 2,
        recording_window_end_utc: Optional[datetime] = None,
        request_timeout_seconds: float = 10.0,
        http_client: Optional[httpx.Client] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
        now_utc_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        time_ns_fn: Callable[[], int] = time.time_ns,
        jitter_fn: Optional[Callable[[int], int]] = None,
        log_fn: Callable[[str], None] = print,
        session_id: Optional[str] = None,
        collector_git_sha: Optional[str] = None,
        trade_dedup_max_entries: int = 50_000,
        curated_fallback_batch_size: int = 16,
    ) -> None:
        self.venue_mode = assert_fail_closed_paper_mode()
        self.tape_root = Path(tape_root)
        self.tape_root.mkdir(parents=True, exist_ok=True)

        self.kalshi_base_url = kalshi_base_url.rstrip("/")
        self.poly_clob_base_url = poly_clob_base_url.rstrip("/")
        self.poly_gamma_base_url = poly_gamma_base_url.rstrip("/")

        self.tracker = ContractLifecycleTracker(
            config=cqp_config,
            recording_window_end_utc=recording_window_end_utc,
        )
        self.filter_config_hash = self.tracker.filter_config_hash

        stamp = session_id or datetime.now(timezone.utc).strftime("session_v2_%Y%m%dT%H%M%SZ")
        session_dir = self.tape_root / stamp
        if session_dir.exists() and (session_dir / "tape.jsonl").exists():
            stamp = f"{stamp}_{int(time.time() * 1_000_000) % 1_000_000:06d}"
            session_dir = self.tape_root / stamp
        self.session_dir = session_dir
        self.heartbeat_path = self.tape_root / "collector_heartbeat.json"

        self.writer = StreamingTapeWriterV2(
            self.session_dir,
            filter_config_hash=self.filter_config_hash,
            collector_git_sha=collector_git_sha,
            time_ns_fn=time_ns_fn,
        )
        self.governor = RateLimitGovernor(
            max_req_per_sec=max_req_per_sec,
            monotonic_fn=monotonic_fn,
            sleep_fn=sleep_fn,
            jitter_fn=jitter_fn,
        )
        self.trade_dedup = TradeDeduplicator(max_entries=trade_dedup_max_entries)

        self._owns_client = http_client is None
        self.client = http_client or httpx.Client(
            timeout=request_timeout_seconds,
            headers={"User-Agent": "PDEUE-ObservedL2-Collector/2.0 (read-only)"},
        )
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn
        self._now_utc = now_utc_fn
        self._time_ns = time_ns_fn
        self._log = log_fn

        self.curated_interval_seconds = max(1, int(curated_interval_seconds))
        self.trades_interval_seconds = max(1, int(trades_interval_seconds))
        self.baseline_interval_seconds = max(1, int(baseline_interval_seconds))
        self.admission_interval_seconds = max(1, int(admission_interval_seconds))
        self.trades_window_seconds = max(10, int(trades_window_seconds))
        self.kalshi_baseline_count = max(0, int(kalshi_baseline_count))
        self.curated_fallback_batch_size = max(1, int(curated_fallback_batch_size))
        self.poly_benchmark_cap = min(
            max(0, int(poly_benchmark_count)),
            int(self.tracker.config.get("max_polymarket_benchmark_contracts", MAX_POLYMARKET_BENCHMARK_CONTRACTS)),
        )

        self.baseline_kalshi_tickers: List[str] = []
        self.poly_tokens: List[str] = []
        self._dead_poly_tokens: set[str] = set()
        self._kalshi_batch_orderbooks_unsupported: bool = False
        self._logged_batch_400_body: bool = False
        self._curated_rr_cursor: int = 0

        self._last_admission_mono: Optional[float] = None
        self._last_curated_mono: Optional[float] = None
        self._last_trades_mono: Optional[float] = None
        self._last_baseline_mono: Optional[float] = None

        self.cycles = 0
        self.snapshots_total = 0
        self.trades_total = 0
        self.data_gaps_total = 0
        self.errors_total = 0
        self.consecutive_errors = 0
        self.last_error: Optional[str] = None
        self.last_trade_window_status: Optional[str] = None
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _http_get(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[httpx.Response, int, int]:
        """Perform a strictly read-only GET through the <= 2 req/s governor with zero auth headers."""
        for hdr in self.client.headers.keys():
            if hdr.lower() in _FORBIDDEN_AUTH_HEADERS:
                raise RuntimeError(f"FAIL-CLOSED: Forbidden auth header {hdr!r} on read-only collector client")
        self.governor.acquire()
        t_sent = self._time_ns()
        resp = self.client.get(url, params=params)
        t_recv = self._time_ns()
        return resp, t_sent, t_recv

    def _emit_data_gap(
        self,
        *,
        venue: str,
        endpoint: str,
        reason: str,
        affected_tickers: Sequence[str],
        http_status: Optional[int],
        t_req_sent_ns: int,
        t_resp_recv_ns: int,
        backoff_info: Optional[Dict[str, Any]] = None,
        gap_start_utc: Optional[str] = None,
        gap_end_utc: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.data_gaps_total += 1
        now_iso = _utc_now_iso(self._now_utc())
        payload: Dict[str, Any] = {
            "venue": venue,
            "endpoint": endpoint,
            "reason": reason,
            "affected_tickers": list(affected_tickers),
            "gap_start_utc": gap_start_utc or now_iso,
            "gap_end_utc": gap_end_utc or now_iso,
            "n_429": self.governor.n_429,
            "backoff_ms": int(backoff_info["backoff_ms"]) if backoff_info else 0,
            "backoff_seconds": int(backoff_info["backoff_seconds"]) if backoff_info else 0,
            "degraded_curated_cadence_seconds": self.governor.current_curated_cadence_seconds,
            "replay_censor_action": "CENSORED",
        }
        return self.writer.append_record(
            "DATA_GAP",
            payload,
            t_req_sent_ns=t_req_sent_ns,
            t_resp_recv_ns=t_resp_recv_ns,
            http_status=http_status,
        )

    def _sleep_backoff_with_heartbeat(self, backoff_ms: int) -> None:
        """Sleep for backoff_ms; chunk long wall-clock sleeps to keep Docker heartbeat fresh."""
        total_seconds = backoff_ms / 1000.0
        if self._sleep is not time.sleep or total_seconds <= 60.0:
            self._sleep(total_seconds)
            return
        remaining = total_seconds
        while remaining > 0 and not self._stop_requested:
            chunk = min(remaining, 60.0)
            self._sleep(chunk)
            remaining -= chunk
            if remaining > 0 and not self._stop_requested:
                self._persist_heartbeat_file(status="BACKOFF_429", rate_limited=True, cycle_snapshots=0, cycle_errors=0)

    def run_admission_scan(self, *, max_pages: int = 10) -> Dict[str, Any]:
        """Run 15-min CQP-001-v0.1 Kalshi admission scan via GET /markets?mve_filter=exclude&status=open."""
        url = f"{self.kalshi_base_url}/markets"
        cursor: Optional[str] = None
        all_markets: List[Dict[str, Any]] = []
        rate_limited = False
        last_sent = self._time_ns()
        last_recv = last_sent
        last_status: Optional[int] = None
        last_raw_bytes = b"{}"

        for _ in range(max(1, max_pages)):
            params: Dict[str, Any] = {"mve_filter": "exclude", "status": "open", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            try:
                resp, t_sent, t_recv = self._http_get(url, params=params)
                last_sent, last_recv, last_status, last_raw_bytes = t_sent, t_recv, resp.status_code, resp.content
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                t_now = self._time_ns()
                self._emit_data_gap(
                    venue="KALSHI",
                    endpoint="/markets",
                    reason=f"TRANSPORT_ERROR:{type(exc).__name__}",
                    affected_tickers=self.tracker.active_tickers(),
                    http_status=None,
                    t_req_sent_ns=last_sent,
                    t_resp_recv_ns=t_now,
                )
                return {"rate_limited": False, "error": f"ADMISSION:{type(exc).__name__}", "admitted": 0}

            if resp.status_code == 429:
                rate_limited = True
                backoff = self.governor.record_http_429()
                self._emit_data_gap(
                    venue="KALSHI",
                    endpoint="/markets",
                    reason="HTTP_429_RATE_LIMIT",
                    affected_tickers=self.tracker.active_tickers(),
                    http_status=429,
                    t_req_sent_ns=t_sent,
                    t_resp_recv_ns=t_recv,
                    backoff_info=backoff,
                )
                self._sleep_backoff_with_heartbeat(backoff["backoff_ms"])
                return {"rate_limited": True, "error": "ADMISSION:HTTP_429", "admitted": 0}

            if resp.status_code != 200:
                self._emit_data_gap(
                    venue="KALSHI",
                    endpoint="/markets",
                    reason=f"HTTP_{resp.status_code}",
                    affected_tickers=self.tracker.active_tickers(),
                    http_status=resp.status_code,
                    t_req_sent_ns=t_sent,
                    t_resp_recv_ns=t_recv,
                )
                return {"rate_limited": False, "error": f"ADMISSION:HTTP_{resp.status_code}", "admitted": 0}

            data = resp.json()
            batch = data.get("markets") or []
            if isinstance(batch, list):
                all_markets.extend(m for m in batch if isinstance(m, dict))
            cursor = data.get("cursor") or None
            if not cursor or not batch:
                break

        # Anti-survivorship settlement check: if any retained contract is absent from the
        # `status=open` discovery scan, inspect GET /markets/{ticker} to detect settlement
        # without ever silently evicting it mid-life.
        seen_tickers = {str(m.get("ticker", "")).strip() for m in all_markets if isinstance(m, dict)}
        for retained_tk in self.tracker.active_tickers():
            st = self.tracker.contracts.get(retained_tk)
            if st is None or st.settlement_emitted or retained_tk in seen_tickers:
                continue
            detail_url = f"{self.kalshi_base_url}/markets/{retained_tk}"
            try:
                d_resp, d_sent, d_recv = self._http_get(detail_url)
                if d_resp.status_code == 200:
                    d_json = d_resp.json()
                    m_obj = d_json.get("market", d_json) if isinstance(d_json, dict) else None
                    if isinstance(m_obj, dict) and m_obj.get("ticker"):
                        all_markets.append(m_obj)
                        last_sent, last_recv, last_status, last_raw_bytes = (
                            d_sent,
                            d_recv,
                            d_resp.status_code,
                            d_resp.content,
                        )
                elif d_resp.status_code == 429:
                    rate_limited = True
                    backoff = self.governor.record_http_429()
                    self._emit_data_gap(
                        venue="KALSHI",
                        endpoint=f"/markets/{retained_tk}",
                        reason="HTTP_429_RATE_LIMIT",
                        affected_tickers=[retained_tk],
                        http_status=429,
                        t_req_sent_ns=d_sent,
                        t_resp_recv_ns=d_recv,
                        backoff_info=backoff,
                    )
                    self._sleep_backoff_with_heartbeat(backoff["backoff_ms"])
                    break
            except (httpx.TimeoutException, httpx.RequestError):
                # Never evict on transient error; retain until verified settlement
                continue

        reconciled = self.tracker.reconcile_admission_scan(all_markets, now_utc=self._now_utc())

        for dec in reconciled["decisions"]:
            self.writer.append_record(
                "QUALIFICATION_DECISION",
                dec,
                t_req_sent_ns=last_sent,
                t_resp_recv_ns=last_recv,
                http_status=last_status,
                raw_payload_bytes=last_raw_bytes,
            )

        for meta in reconciled["newly_admitted"]:
            self.writer.append_record(
                "MARKET_META",
                meta,
                t_req_sent_ns=last_sent,
                t_resp_recv_ns=last_recv,
                http_status=last_status,
                raw_payload_bytes=last_raw_bytes,
            )

        for sev in reconciled["settlements"]:
            self.writer.append_record(
                "SETTLEMENT_EVENT",
                sev,
                t_req_sent_ns=last_sent,
                t_resp_recv_ns=last_recv,
                http_status=last_status,
                raw_payload_bytes=last_raw_bytes,
            )

        # Also update broad baseline Kalshi tickers (non-MVE liquid markets not already in curated basket)
        curated_set = set(reconciled["active_tickers"])
        non_mve = [
            m
            for m in all_markets
            if m.get("ticker")
            and str(m["ticker"]).strip() not in curated_set
            and not _is_multivariate_combo(m, self.tracker.config.get("banned_prefixes") or ())
        ]
        non_mve.sort(
            key=lambda m: (
                -_parse_int_metric_centi(m.get("volume_24h_fp", m.get("volume_24h"))),
                -_parse_int_metric_centi(m.get("open_interest_fp", m.get("open_interest"))),
                str(m.get("ticker", "")),
            )
        )
        self.baseline_kalshi_tickers = [
            str(m["ticker"]).strip() for m in non_mve[: self.kalshi_baseline_count]
        ]

        return {
            "rate_limited": rate_limited,
            "error": None,
            "admitted": len(reconciled["newly_admitted"]),
            "active_count": len(reconciled["active_tickers"]),
            "settlements": len(reconciled["settlements"]),
        }

    def _log_kalshi_batch_fallback_once(self, resp: httpx.Response) -> None:
        """Log first 200 chars of Kalshi batched orderbooks error body once and latch per-ticker fallback."""
        self._kalshi_batch_orderbooks_unsupported = True
        if self._logged_batch_400_body:
            return
        self._logged_batch_400_body = True
        snippet = (resp.text or "")[:200]
        self._log(
            json.dumps(
                {
                    "event": "KALSHI_BATCH_ORDERBOOKS_FALLBACK",
                    "http_status": resp.status_code,
                    "body_snippet": snippet,
                    "fallback_endpoint": "/markets/{ticker}/orderbook",
                },
                sort_keys=True,
            )
        )

    def _poll_kalshi_orderbooks_per_ticker(
        self,
        tickers: Sequence[str],
        *,
        curated: bool,
    ) -> Dict[str, Any]:
        """Poll GET /markets/{ticker}/orderbook respecting <= 2 req/s governor with round-robin pacing."""
        ticker_list = list(tickers)
        if not ticker_list:
            return {
                "snapshots": 0,
                "rate_limited": False,
                "errors": [],
                "mode": "per_ticker_fallback",
            }

        snapshots = 0
        errors: List[str] = []
        rate_limited = False

        if curated:
            n = len(ticker_list)
            batch_len = min(n, self.curated_fallback_batch_size)
            start = self._curated_rr_cursor % n
            selected = [ticker_list[(start + i) % n] for i in range(batch_len)]
        else:
            start = 0
            selected = ticker_list

        for idx, tk in enumerate(selected):
            url = f"{self.kalshi_base_url}/markets/{tk}/orderbook"
            t_start = self._time_ns()
            try:
                resp, t_sent, t_recv = self._http_get(url)
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                self._emit_data_gap(
                    venue="KALSHI",
                    endpoint=f"/markets/{tk}/orderbook",
                    reason=f"TRANSPORT_ERROR:{type(exc).__name__}",
                    affected_tickers=[tk],
                    http_status=None,
                    t_req_sent_ns=t_start,
                    t_resp_recv_ns=self._time_ns(),
                )
                errors.append(f"KALSHI:{tk}:{type(exc).__name__}")
                if curated:
                    self._curated_rr_cursor = (start + idx + 1) % len(ticker_list)
                continue

            if resp.status_code == 429:
                rate_limited = True
                backoff = self.governor.record_http_429()
                self._emit_data_gap(
                    venue="KALSHI",
                    endpoint=f"/markets/{tk}/orderbook",
                    reason="HTTP_429_RATE_LIMIT",
                    affected_tickers=selected[idx:],
                    http_status=429,
                    t_req_sent_ns=t_sent,
                    t_resp_recv_ns=t_recv,
                    backoff_info=backoff,
                )
                self._sleep_backoff_with_heartbeat(backoff["backoff_ms"])
                errors.append(f"KALSHI:{tk}:HTTP_429")
                break

            if resp.status_code != 200:
                self._emit_data_gap(
                    venue="KALSHI",
                    endpoint=f"/markets/{tk}/orderbook",
                    reason=f"HTTP_{resp.status_code}",
                    affected_tickers=[tk],
                    http_status=resp.status_code,
                    t_req_sent_ns=t_sent,
                    t_resp_recv_ns=t_recv,
                )
                errors.append(f"KALSHI:{tk}:HTTP_{resp.status_code}")
                if curated:
                    self._curated_rr_cursor = (start + idx + 1) % len(ticker_list)
                continue

            try:
                if curated:
                    st = self.tracker.contracts.get(tk)
                    meta = st.market_meta if st is not None else None
                    snap = normalize_kalshi_l2_v2(
                        tk,
                        resp.json(),
                        source_url=url,
                        market_meta=meta,
                    )
                    record_payload = self.tracker.evaluate_snapshot_tradeability(tk, snap)
                    record_payload["polling_tier"] = "CURATED_10S"
                else:
                    record_payload = normalize_kalshi_l2_v2(
                        tk,
                        resp.json(),
                        source_url=url,
                    )
                    record_payload["classification"] = "BROAD_BASELINE"
                    record_payload["live_execution_eligible"] = False
                    record_payload["strategy_d_eligible"] = False
                    record_payload["strategy_d_replay_variant_eligible"] = False
                    record_payload["polling_tier"] = "BASELINE_60S"

                self.writer.append_record(
                    "OBSERVED_L2",
                    record_payload,
                    t_req_sent_ns=t_sent,
                    t_resp_recv_ns=t_recv,
                    http_status=resp.status_code,
                    raw_payload_bytes=resp.content,
                )
                snapshots += 1
            except Exception as exc:
                errors.append(f"KALSHI:{tk}:{type(exc).__name__}:{exc}")

            if curated:
                self._curated_rr_cursor = (start + idx + 1) % len(ticker_list)

        return {
            "snapshots": snapshots,
            "rate_limited": rate_limited,
            "errors": errors,
            "mode": "per_ticker_fallback",
        }

    def poll_curated_kalshi_orderbooks(self) -> Dict[str, Any]:
        """Poll curated Kalshi basket (<= 32 tickers), falling back to /markets/{ticker}/orderbook on HTTP 400."""
        tickers = self.tracker.active_tickers()
        if not tickers:
            return {"snapshots": 0, "rate_limited": False, "errors": [], "mode": "idle"}

        if self._kalshi_batch_orderbooks_unsupported:
            return self._poll_kalshi_orderbooks_per_ticker(tickers, curated=True)

        url = f"{self.kalshi_base_url}/markets/orderbooks"
        t_start = self._time_ns()
        try:
            resp, t_sent, t_recv = self._http_get(url, params={"tickers": ",".join(tickers)})
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            self._emit_data_gap(
                venue="KALSHI",
                endpoint="/markets/orderbooks",
                reason=f"TRANSPORT_ERROR:{type(exc).__name__}",
                affected_tickers=tickers,
                http_status=None,
                t_req_sent_ns=t_start,
                t_resp_recv_ns=self._time_ns(),
            )
            return {"snapshots": 0, "rate_limited": False, "errors": [f"KALSHI_BATCH:{type(exc).__name__}"]}

        if resp.status_code == 429:
            backoff = self.governor.record_http_429()
            self._emit_data_gap(
                venue="KALSHI",
                endpoint="/markets/orderbooks",
                reason="HTTP_429_RATE_LIMIT",
                affected_tickers=tickers,
                http_status=429,
                t_req_sent_ns=t_sent,
                t_resp_recv_ns=t_recv,
                backoff_info=backoff,
            )
            self._sleep_backoff_with_heartbeat(backoff["backoff_ms"])
            return {"snapshots": 0, "rate_limited": True, "errors": ["KALSHI_BATCH:HTTP_429"]}

        if resp.status_code in {400, 401, 403, 404, 405}:
            self._log_kalshi_batch_fallback_once(resp)
            return self._poll_kalshi_orderbooks_per_ticker(tickers, curated=True)

        if resp.status_code != 200:
            self._emit_data_gap(
                venue="KALSHI",
                endpoint="/markets/orderbooks",
                reason=f"HTTP_{resp.status_code}",
                affected_tickers=tickers,
                http_status=resp.status_code,
                t_req_sent_ns=t_sent,
                t_resp_recv_ns=t_recv,
            )
            return {"snapshots": 0, "rate_limited": False, "errors": [f"KALSHI_BATCH:HTTP_{resp.status_code}"]}

        raw_bytes = resp.content
        books_map = _extract_batched_orderbooks(resp.json(), tickers)
        snapshots = 0
        errors: List[str] = []
        for tk in tickers:
            ob_payload = books_map.get(tk)
            if ob_payload is None:
                continue
            try:
                st = self.tracker.contracts.get(tk)
                meta = st.market_meta if st is not None else None
                snap = normalize_kalshi_l2_v2(
                    tk,
                    ob_payload,
                    source_url=f"{url}?tickers={tk}",
                    market_meta=meta,
                )
                enriched = self.tracker.evaluate_snapshot_tradeability(tk, snap)
                enriched["polling_tier"] = "CURATED_10S"
                self.writer.append_record(
                    "OBSERVED_L2",
                    enriched,
                    t_req_sent_ns=t_sent,
                    t_resp_recv_ns=t_recv,
                    http_status=resp.status_code,
                    raw_payload_bytes=raw_bytes,
                )
                snapshots += 1
            except Exception as exc:
                errors.append(f"KALSHI:{tk}:{type(exc).__name__}:{exc}")

        return {"snapshots": snapshots, "rate_limited": False, "errors": errors, "mode": "batch"}

    def poll_kalshi_public_trades(self, *, max_pages: int = 50) -> Dict[str, Any]:
        """Poll GET /markets/trades with overlapping 120s window, strictly filtered to curated Kalshi basket."""
        now_dt = self._now_utc()
        max_ts = int(now_dt.timestamp())
        min_ts = max_ts - self.trades_window_seconds

        active_curated_kalshi_tickers = self.tracker.active_tickers()
        curated_set = frozenset(active_curated_kalshi_tickers)
        url = f"{self.kalshi_base_url}/markets/trades"

        cursor: Optional[str] = None
        pages_fetched = 0
        raw_trades_seen = 0
        non_curated_dropped = 0
        curated_trades_collected: List[Tuple[Dict[str, Any], int, int, int, bytes]] = []
        incomplete = False
        rate_limited = False
        errors: List[str] = []

        while pages_fetched < max(1, max_pages):
            params: Dict[str, Any] = {"min_ts": min_ts, "max_ts": max_ts, "limit": 1000}
            if cursor:
                params["cursor"] = cursor

            t_start = self._time_ns()
            try:
                resp, t_sent, t_recv = self._http_get(url, params=params)
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                incomplete = True
                errors.append(f"KALSHI_TRADES:{type(exc).__name__}")
                self._emit_data_gap(
                    venue="KALSHI",
                    endpoint="/markets/trades",
                    reason=f"INCOMPLETE_TRADE_WINDOW:{type(exc).__name__}",
                    affected_tickers=active_curated_kalshi_tickers,
                    http_status=None,
                    t_req_sent_ns=t_start,
                    t_resp_recv_ns=self._time_ns(),
                )
                break

            if resp.status_code == 429:
                incomplete = True
                rate_limited = True
                errors.append("KALSHI_TRADES:HTTP_429")
                backoff = self.governor.record_http_429()
                self._emit_data_gap(
                    venue="KALSHI",
                    endpoint="/markets/trades",
                    reason="HTTP_429_RATE_LIMIT",
                    affected_tickers=active_curated_kalshi_tickers,
                    http_status=429,
                    t_req_sent_ns=t_sent,
                    t_resp_recv_ns=t_recv,
                    backoff_info=backoff,
                )
                self._sleep_backoff_with_heartbeat(backoff["backoff_ms"])
                break

            if resp.status_code != 200:
                incomplete = True
                errors.append(f"KALSHI_TRADES:HTTP_{resp.status_code}")
                self._emit_data_gap(
                    venue="KALSHI",
                    endpoint="/markets/trades",
                    reason=f"INCOMPLETE_TRADE_WINDOW:HTTP_{resp.status_code}",
                    affected_tickers=active_curated_kalshi_tickers,
                    http_status=resp.status_code,
                    t_req_sent_ns=t_sent,
                    t_resp_recv_ns=t_recv,
                )
                break

            pages_fetched += 1
            data = resp.json()
            page_trades = data.get("trades") or []
            raw_bytes = resp.content
            if isinstance(page_trades, list):
                for tr in page_trades:
                    if not isinstance(tr, dict):
                        continue
                    raw_trades_seen += 1
                    ticker = str(tr.get("ticker", tr.get("market_ticker", ""))).strip()
                    if ticker not in curated_set:
                        non_curated_dropped += 1
                        continue
                    curated_trades_collected.append((tr, t_sent, t_recv, resp.status_code, raw_bytes))

            next_cursor = data.get("cursor") or None
            if not next_cursor:
                cursor = None
                break
            cursor = str(next_cursor)

        if cursor is not None and not incomplete:
            # Hit max_pages without exhausting cursor -> mark INCOMPLETE
            incomplete = True
            self._emit_data_gap(
                venue="KALSHI",
                endpoint="/markets/trades",
                reason="INCOMPLETE_TRADE_WINDOW:MAX_PAGES_EXCEEDED",
                affected_tickers=active_curated_kalshi_tickers,
                http_status=200,
                t_req_sent_ns=self._time_ns(),
                t_resp_recv_ns=self._time_ns(),
            )

        if incomplete:
            window_status = "INCOMPLETE"
        elif len(curated_trades_collected) == 0:
            window_status = "EMPTY_COMPLETE"
        else:
            window_status = "COMPLETE"

        self.last_trade_window_status = window_status

        emitted = 0
        duplicates_skipped = 0
        for raw_tr, t_sent, t_recv, status_code, raw_bytes in curated_trades_collected:
            tid = str(raw_tr.get("trade_id", "")).strip()
            if not tid:
                continue
            if not self.trade_dedup.mark_if_new(tid, max_ts):
                duplicates_skipped += 1
                continue
            try:
                parsed = parse_kalshi_trade_v2(
                    raw_tr,
                    window_min_ts=min_ts,
                    window_max_ts=max_ts,
                    window_completeness_status=window_status,
                )
                self.writer.append_record(
                    "OBSERVED_TRADE",
                    parsed,
                    t_req_sent_ns=t_sent,
                    t_resp_recv_ns=t_recv,
                    http_status=status_code,
                    raw_payload_bytes=raw_bytes,
                )
                emitted += 1
            except Exception as exc:
                errors.append(f"KALSHI_TRADE_PARSE:{tid}:{type(exc).__name__}:{exc}")

        self.trades_total += emitted
        return {
            "trades_emitted": emitted,
            "duplicates_skipped": duplicates_skipped,
            "non_curated_dropped": non_curated_dropped,
            "raw_trades_seen": raw_trades_seen,
            "curated_trades_seen": len(curated_trades_collected),
            "pages_fetched": pages_fetched,
            "window_min_ts": min_ts,
            "window_max_ts": max_ts,
            "window_completeness_status": window_status,
            "rate_limited": rate_limited,
            "errors": errors,
        }

    def _discover_polymarket_benchmarks(self) -> Tuple[List[str], bool, List[str]]:
        """Discover up to poly_benchmark_cap (<=16) active Polymarket CLOB tokens (read-only BENCHMARK_ONLY)."""
        if self.poly_benchmark_cap <= 0:
            return [], False, []
        from app.adapters.live_l2_tape_recorder import extract_polymarket_clob_token_ids

        tokens: List[str] = []
        errors: List[str] = []
        rate_limited = False
        url = f"{self.poly_gamma_base_url}/markets"
        try:
            resp, t_sent, t_recv = self._http_get(
                url,
                params={
                    "active": "true",
                    "closed": "false",
                    "archived": "false",
                    "enableOrderBook": "true",
                    "limit": max(self.poly_benchmark_cap * 3, 25),
                    "order": "volume24hr",
                    "ascending": "false",
                },
            )
            if resp.status_code == 429:
                rate_limited = True
                backoff = self.governor.record_http_429()
                self._emit_data_gap(
                    venue="POLYMARKET",
                    endpoint="/markets",
                    reason="HTTP_429_RATE_LIMIT",
                    affected_tickers=self.poly_tokens,
                    http_status=429,
                    t_req_sent_ns=t_sent,
                    t_resp_recv_ns=t_recv,
                    backoff_info=backoff,
                )
                self._sleep_backoff_with_heartbeat(backoff["backoff_ms"])
                return [], True, ["DISCOVER:POLYMARKET:HTTP_429"]
            if resp.status_code == 200:
                rows = resp.json()
                if isinstance(rows, list):
                    for m in rows:
                        if not isinstance(m, dict):
                            continue
                        if (
                            m.get("closed") is True
                            or m.get("archived") is True
                            or m.get("active") is False
                            or m.get("enableOrderBook") is False
                            or m.get("acceptingOrders") is False
                        ):
                            continue
                        for tok in extract_polymarket_clob_token_ids(m.get("clobTokenIds")):
                            if tok not in self._dead_poly_tokens and tok not in tokens:
                                tokens.append(tok)
                                break
                        if len(tokens) >= self.poly_benchmark_cap:
                            break
            else:
                errors.append(f"DISCOVER:POLYMARKET:HTTP_{resp.status_code}")
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            errors.append(f"DISCOVER:POLYMARKET:{type(exc).__name__}")
        return tokens[: self.poly_benchmark_cap], rate_limited, errors

    def poll_broad_baseline_l2(self) -> Dict[str, Any]:
        """60-second broad baseline polling for broad Kalshi markets + Polymarket benchmarks (<= 16)."""
        snapshots = 0
        errors: List[str] = []
        rate_limited = False

        # 1. Broad Kalshi baseline (batched if supported, else per-ticker /markets/{ticker}/orderbook)
        if self.baseline_kalshi_tickers:
            if self._kalshi_batch_orderbooks_unsupported:
                base_fb = self._poll_kalshi_orderbooks_per_ticker(self.baseline_kalshi_tickers, curated=False)
                snapshots += base_fb["snapshots"]
                if base_fb["rate_limited"]:
                    rate_limited = True
                errors.extend(base_fb["errors"])
            else:
                url = f"{self.kalshi_base_url}/markets/orderbooks"
                t_start = self._time_ns()
                try:
                    resp, t_sent, t_recv = self._http_get(
                        url, params={"tickers": ",".join(self.baseline_kalshi_tickers)}
                    )
                    if resp.status_code == 429:
                        rate_limited = True
                        backoff = self.governor.record_http_429()
                        self._emit_data_gap(
                            venue="KALSHI",
                            endpoint="/markets/orderbooks",
                            reason="HTTP_429_RATE_LIMIT",
                            affected_tickers=self.baseline_kalshi_tickers,
                            http_status=429,
                            t_req_sent_ns=t_sent,
                            t_resp_recv_ns=t_recv,
                            backoff_info=backoff,
                        )
                        self._sleep_backoff_with_heartbeat(backoff["backoff_ms"])
                        errors.append("KALSHI_BASELINE:HTTP_429")
                    elif resp.status_code in {400, 401, 403, 404, 405}:
                        self._log_kalshi_batch_fallback_once(resp)
                        base_fb = self._poll_kalshi_orderbooks_per_ticker(
                            self.baseline_kalshi_tickers, curated=False
                        )
                        snapshots += base_fb["snapshots"]
                        if base_fb["rate_limited"]:
                            rate_limited = True
                        errors.extend(base_fb["errors"])
                    elif resp.status_code == 200:
                        books = _extract_batched_orderbooks(resp.json(), self.baseline_kalshi_tickers)
                        for tk, ob in books.items():
                            try:
                                snap = normalize_kalshi_l2_v2(tk, ob, source_url=f"{url}?tickers={tk}")
                                snap["classification"] = "BROAD_BASELINE"
                                snap["live_execution_eligible"] = False
                                snap["strategy_d_eligible"] = False
                                snap["strategy_d_replay_variant_eligible"] = False
                                snap["polling_tier"] = "BASELINE_60S"
                                self.writer.append_record(
                                    "OBSERVED_L2",
                                    snap,
                                    t_req_sent_ns=t_sent,
                                    t_resp_recv_ns=t_recv,
                                    http_status=200,
                                    raw_payload_bytes=resp.content,
                                )
                                snapshots += 1
                            except Exception as exc:
                                errors.append(f"KALSHI_BASELINE:{tk}:{type(exc).__name__}")
                    else:
                        errors.append(f"KALSHI_BASELINE:HTTP_{resp.status_code}")
                except (httpx.TimeoutException, httpx.RequestError) as exc:
                    self._emit_data_gap(
                        venue="KALSHI",
                        endpoint="/markets/orderbooks",
                        reason=f"TRANSPORT_ERROR:{type(exc).__name__}",
                        affected_tickers=self.baseline_kalshi_tickers,
                        http_status=None,
                        t_req_sent_ns=t_start,
                        t_resp_recv_ns=self._time_ns(),
                    )
                    errors.append(f"KALSHI_BASELINE:{type(exc).__name__}")

        # 2. Polymarket read-only benchmarks (cap <= 16, retains 1c spreads, always BENCHMARK_ONLY)
        if self.poly_benchmark_cap > 0 and len(self.poly_tokens) < self.poly_benchmark_cap:
            discovered, poly_rl, poly_errs = self._discover_polymarket_benchmarks()
            if discovered:
                self.poly_tokens = discovered[: self.poly_benchmark_cap]
            if poly_rl:
                rate_limited = True
            errors.extend(poly_errs)

        for tok in list(self.poly_tokens)[: self.poly_benchmark_cap]:
            url = f"{self.poly_clob_base_url}/book"
            t_start = self._time_ns()
            try:
                resp, t_sent, t_recv = self._http_get(url, params={"token_id": tok})
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                errors.append(f"POLYMARKET:{tok[:16]}:{type(exc).__name__}")
                self._emit_data_gap(
                    venue="POLYMARKET",
                    endpoint="/book",
                    reason=f"TRANSPORT_ERROR:{type(exc).__name__}",
                    affected_tickers=[tok],
                    http_status=None,
                    t_req_sent_ns=t_start,
                    t_resp_recv_ns=self._time_ns(),
                )
                continue

            if resp.status_code == 429:
                rate_limited = True
                backoff = self.governor.record_http_429()
                self._emit_data_gap(
                    venue="POLYMARKET",
                    endpoint="/book",
                    reason="HTTP_429_RATE_LIMIT",
                    affected_tickers=[tok],
                    http_status=429,
                    t_req_sent_ns=t_sent,
                    t_resp_recv_ns=t_recv,
                    backoff_info=backoff,
                )
                self._sleep_backoff_with_heartbeat(backoff["backoff_ms"])
                errors.append(f"POLYMARKET:{tok[:16]}:HTTP_429")
                break

            if resp.status_code == 404:
                self._dead_poly_tokens.add(tok)
                self.poly_tokens = [t for t in self.poly_tokens if t != tok]
                errors.append(f"POLYMARKET:{tok[:16]}:HTTP_404")
                continue

            if resp.status_code != 200:
                errors.append(f"POLYMARKET:{tok[:16]}:HTTP_{resp.status_code}")
                continue

            try:
                snap = normalize_polymarket_l2_v2(
                    tok, resp.json(), source_url=f"{url}?token_id={tok}"
                )
                snap["polling_tier"] = "BASELINE_60S"
                self.writer.append_record(
                    "OBSERVED_L2",
                    snap,
                    t_req_sent_ns=t_sent,
                    t_resp_recv_ns=t_recv,
                    http_status=200,
                    raw_payload_bytes=resp.content,
                )
                snapshots += 1
            except Exception as exc:
                errors.append(f"POLYMARKET:{tok[:16]}:{type(exc).__name__}:{exc}")

        return {"snapshots": snapshots, "rate_limited": rate_limited, "errors": errors}

    def _persist_heartbeat_file(
        self,
        *,
        status: str,
        rate_limited: bool,
        cycle_snapshots: int,
        cycle_errors: int,
    ) -> Dict[str, Any]:
        rolling = self.writer.write_manifest_file()
        o1_rolling_manifest = {
            "tape_manifest_sha256": rolling["tape_manifest_sha256"],
            "records_hashed": rolling["record_count"],
            "bytes_hashed": rolling["bytes_written"],
            "bytes_written": rolling["bytes_written"],
            "record_type_counts": dict(rolling["record_type_counts"]),
        }
        bounded_last_error = self.last_error[:200] if isinstance(self.last_error, str) else None
        heartbeat = {
            "event": "OBSERVED_L2_HEARTBEAT",
            "schema_version": SCHEMA_VERSION_V2,
            "timestamp_utc": _utc_now_iso(self._now_utc()),
            "status": status,
            "venue_mode": self.venue_mode,
            "live_trading_enabled": False,
            "data_provenance": "OBSERVED_L2",
            "synthetic_fills_present": False,
            "cycle": self.cycles,
            "cycle_snapshots": cycle_snapshots,
            "snapshots_total": self.snapshots_total,
            "trades_total": self.trades_total,
            "data_gaps_total": self.data_gaps_total,
            "cycle_errors_count": cycle_errors,
            "errors_total": self.errors_total,
            "consecutive_errors": self.consecutive_errors,
            "rate_limited": rate_limited,
            "n_429": self.governor.n_429,
            "curated_cadence_seconds": self.governor.current_curated_cadence_seconds,
            "curated_kalshi_active_count": len(self.tracker.active_tickers()),
            "polymarket_benchmark_active_count": len(self.poly_tokens),
            "last_trade_window_status": self.last_trade_window_status,
            "last_error": bounded_last_error,
            "collector_git_sha": self.writer.collector_git_sha,
            "filter_config_hash": self.filter_config_hash,
            "session_dir": str(self.session_dir),
            "tape_path": str(self.writer.tape_path),
            "tape_manifest_sha256": rolling["tape_manifest_sha256"],
            "records_hashed": rolling["record_count"],
            "bytes_hashed": rolling["bytes_written"],
            "record_type_counts": dict(rolling["record_type_counts"]),
            "rolling_manifest": o1_rolling_manifest,
        }
        payload = json.dumps(heartbeat, sort_keys=True)
        tmp_path = self.heartbeat_path.with_suffix(".json.tmp")
        tmp_path.write_text(payload + "\n", encoding="utf-8")
        tmp_path.replace(self.heartbeat_path)
        self._log(payload)
        return heartbeat

    def collect_once(
        self,
        *,
        force_admission: bool = False,
        force_curated: bool = False,
        force_trades: bool = False,
        force_baseline: bool = False,
    ) -> Dict[str, Any]:
        """Execute one tiered polling tick respecting 15m admission, 10s curated+trades, and 60s baseline."""
        self.cycles += 1
        now_mono = self._monotonic()
        cycle_errors: List[str] = []
        cycle_snapshots = 0
        rate_limited = False

        # 1. Admission scan (every 15 min)
        if (
            force_admission
            or self._last_admission_mono is None
            or (now_mono - self._last_admission_mono) >= self.admission_interval_seconds
        ):
            adm = self.run_admission_scan()
            self._last_admission_mono = now_mono
            if adm["rate_limited"]:
                rate_limited = True
            if adm["error"]:
                cycle_errors.append(adm["error"])

        # 2. Curated Kalshi batched orderbooks (every 10s, degraded on 429)
        curated_cadence = max(self.curated_interval_seconds, self.governor.current_curated_cadence_seconds)
        if (
            force_curated
            or self._last_curated_mono is None
            or (now_mono - self._last_curated_mono) >= curated_cadence
        ):
            cur = self.poll_curated_kalshi_orderbooks()
            self._last_curated_mono = now_mono
            cycle_snapshots += cur["snapshots"]
            if cur["rate_limited"]:
                rate_limited = True
            cycle_errors.extend(cur["errors"])

        # 3. Kalshi public trades (every 10s, overlapping 120s window)
        trades_cadence = max(self.trades_interval_seconds, self.governor.current_curated_cadence_seconds)
        if (
            force_trades
            or self._last_trades_mono is None
            or (now_mono - self._last_trades_mono) >= trades_cadence
        ):
            tr = self.poll_kalshi_public_trades()
            self._last_trades_mono = now_mono
            if tr["rate_limited"]:
                rate_limited = True
            cycle_errors.extend(tr["errors"])

        # 4. Broad baseline L2 + Polymarket benchmarks (every 60s)
        if (
            force_baseline
            or self._last_baseline_mono is None
            or (now_mono - self._last_baseline_mono) >= self.baseline_interval_seconds
        ):
            base = self.poll_broad_baseline_l2()
            self._last_baseline_mono = now_mono
            cycle_snapshots += base["snapshots"]
            if base["rate_limited"]:
                rate_limited = True
            cycle_errors.extend(base["errors"])

        self.snapshots_total += cycle_snapshots
        self.errors_total += len(cycle_errors)

        if cycle_snapshots > 0 or not cycle_errors:
            self.consecutive_errors = 0
        else:
            self.consecutive_errors += 1

        if not rate_limited and not cycle_errors:
            self.governor.note_clean_cycle()

        if cycle_errors:
            self.last_error = cycle_errors[-1]

        status = (
            "HEALTHY"
            if not cycle_errors
            else ("DEGRADED" if cycle_snapshots > 0 else "WAITING_ON_VENUE")
        )

        # Emit structured HEARTBEAT record into the append-only JSONL tape
        self.writer.append_record(
            "HEARTBEAT",
            {
                "venue": "MULTI",
                "status": status,
                "cycle": self.cycles,
                "cycle_snapshots": cycle_snapshots,
                "snapshots_total": self.snapshots_total,
                "trades_total": self.trades_total,
                "data_gaps_total": self.data_gaps_total,
                "cycle_errors_count": len(cycle_errors),
                "errors_total": self.errors_total,
                "consecutive_errors": self.consecutive_errors,
                "rate_limited": rate_limited,
                "n_429": self.governor.n_429,
                "curated_cadence_seconds": self.governor.current_curated_cadence_seconds,
                "curated_kalshi_active_count": len(self.tracker.active_tickers()),
                "polymarket_benchmark_active_count": len(self.poly_tokens),
                "last_trade_window_status": self.last_trade_window_status,
            },
            http_status=None,
        )

        return self._persist_heartbeat_file(
            status=status,
            rate_limited=rate_limited,
            cycle_snapshots=cycle_snapshots,
            cycle_errors=len(cycle_errors),
        )

    def run(self, *, max_cycles: Optional[int] = None) -> Dict[str, Any]:
        """Run tiered polling loop until max_cycles is reached or stop signal arrives."""
        last_hb: Dict[str, Any] = {}
        try:
            while not self._stop_requested:
                last_hb = self.collect_once()
                if max_cycles is not None and self.cycles >= max_cycles:
                    break
                delay = max(
                    self.curated_interval_seconds,
                    self.governor.current_curated_cadence_seconds,
                )
                if delay > 0 and not self._stop_requested:
                    self._sleep(delay)
        finally:
            self.close()
        return last_hb
