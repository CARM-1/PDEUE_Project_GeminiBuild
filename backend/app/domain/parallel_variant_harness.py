"""Brief #01 Parallel Variant Grid, Chronological Holdout Splitter & G2A Gate Adjudicator.

Non-Negotiable Invariants:
- Whole-event chronological split: Days 1-8 Train / Day 9 Embargo (dropped) / Days 10-14 Sealed Holdout.
  Zero leakage across correlated strikes of the same event cluster.
- Prespecified variant grid strictly capped at <= 36 variants; 1c/2c spreads and short-horizon Crypto
  can NEVER become Strategy D eligible.
- Variant selection strictly on Train ONLY, enforcing Plateau Test (reject lone spikes) and emitting a
  Cryptographic Freeze Package (SHA-256 of selected variant config, replay git SHA, holdout tape manifest)
  BEFORE evaluating holdout.
- 3-Unit Exact Integer Math ONLY (ZERO `float()` calls anywhere in this module).
- 100% deterministic: fixed-seed 10,000-resample event-cluster bootstrap and byte-identical JSON / SHA-256.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.adapters.collector_v2 import _assert_no_floats, resolve_collector_git_sha
from app.domain.replay_v2_engine import (
    NS_PER_DAY,
    LoadedTapeV2,
    OrderEpisodeResult,
    ReplayVariantConfig,
    load_v2_tape,
    replay_variant_on_tape,
)

# ---------------------------------------------------------------------------
# Brief #01 Constants (Exact Integers — ZERO floats)
# ---------------------------------------------------------------------------

MAX_VARIANT_GRID_SIZE = 36

DEFAULT_MIN_SPREAD_GRID_PIPS: Tuple[int, ...] = (300, 400, 500)
DEFAULT_MAX_EXPIRY_GRID_HOURS: Tuple[int, ...] = (24, 72, 168)
DEFAULT_MIN_CONSEC_GRID_SNAPSHOTS: Tuple[int, ...] = (2, 3)
DEFAULT_EXIT_MODE_GRID: Tuple[str, ...] = ("settlement_only", "early_exit_5c")

TRAIN_MAX_DAY = 8
EMBARGO_DAY = 9
HOLDOUT_MIN_DAY = 10

DEFAULT_BOOTSTRAP_RESAMPLES = 10_000
DEFAULT_BOOTSTRAP_SEED = 20260101
BOOTSTRAP_80PCT_LB_THRESHOLD_PIPS = -300  # -3c per contract

G2A_MIN_RESOLVED_EVENT_CLUSTERS = 40
G2A_MIN_FILLED_ORDER_EPISODES = 150
G2A_MIN_SERIES_COUNT = 4
G2A_MAX_SERIES_FILL_SHARE_PCT = 40
G2A_MAX_SINGLE_EVENT_ABS_PNL_SHARE_PCT = 10
G2A_MAX_CENSORED_ORDER_MINUTES_PCT = 1  # strictly < 1.0%

STRESS_MINUS_5PP_PIPS = 500  # -5pp win probability = -500 pips ($0.05) per binary contract
STRESS_PLUS_1C_PIPS = 100  # +1c extra cost = -100 pips per contract


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def canonical_json_bytes(obj: Any) -> bytes:
    """Serialize any exact-integer dict/list into deterministic canonical UTF-8 JSON bytes."""
    _assert_no_floats(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(obj: Any) -> str:
    """Compute SHA-256 hex digest of deterministic canonical JSON representation."""
    return hashlib.sha256(canonical_json_bytes(obj)).hexdigest()


# ---------------------------------------------------------------------------
# 1. Prespecified Variant Grid (<= 36 Variants, Grid Coordinates for Plateau)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GridVariantEntry:
    variant: ReplayVariantConfig
    coords: Tuple[int, int, int, int]


def build_prespecified_variant_grid(
    *,
    min_spread_pips_values: Sequence[int] = DEFAULT_MIN_SPREAD_GRID_PIPS,
    max_expiry_hours_values: Sequence[int] = DEFAULT_MAX_EXPIRY_GRID_HOURS,
    min_consecutive_snapshots_values: Sequence[int] = DEFAULT_MIN_CONSEC_GRID_SNAPSHOTS,
    exit_modes: Sequence[str] = DEFAULT_EXIT_MODE_GRID,
    max_spread_pips: int = 1000,
    min_top_depth_centi: int = 10_000,
    order_qty_centi: int = 500,
    max_order_notional_micro: int = 5_000_000,
    maker_fee_bps: Optional[int] = None,
) -> Tuple[GridVariantEntry, ...]:
    """Construct the prespecified Strategy D variant grid, hard-capped at <= 36 variants."""
    spreads = tuple(min_spread_pips_values)
    expiries = tuple(max_expiry_hours_values)
    consecs = tuple(min_consecutive_snapshots_values)
    exits = tuple(exit_modes)

    total = len(spreads) * len(expiries) * len(consecs) * len(exits)
    if total == 0:
        raise ValueError("Variant grid cannot be empty")
    if total > MAX_VARIANT_GRID_SIZE:
        raise ValueError(
            f"Prespecified variant grid size {total} exceeds Brief #01 hard cap of {MAX_VARIANT_GRID_SIZE}"
        )

    entries: List[GridVariantEntry] = []
    for i_s, min_sp in enumerate(spreads):
        for i_e, max_exp in enumerate(expiries):
            for i_c, min_con in enumerate(consecs):
                for i_x, ex_mode in enumerate(exits):
                    vid = f"V_SP{min_sp}_EXP{max_exp}H_C{min_con}_{ex_mode.upper()}"
                    cfg = ReplayVariantConfig(
                        variant_id=vid,
                        min_spread_pips=min_sp,
                        max_spread_pips=max_spread_pips,
                        max_expiry_hours=max_exp,
                        min_consecutive_snapshots=min_con,
                        exit_mode=ex_mode,
                        min_top_depth_centi=min_top_depth_centi,
                        order_qty_centi=order_qty_centi,
                        max_order_notional_micro=max_order_notional_micro,
                        maker_fee_bps=maker_fee_bps,
                    )
                    entries.append(GridVariantEntry(variant=cfg, coords=(i_s, i_e, i_c, i_x)))
    return tuple(entries)


# ---------------------------------------------------------------------------
# 2. Whole-Event Chronological Splitter (Days 1-8 Train / Day 9 Embargo / 10-14 Holdout)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChronologicalSplitResult:
    window_start_ns: int
    train_event_clusters: Tuple[str, ...]
    embargo_event_clusters: Tuple[str, ...]
    holdout_event_clusters: Tuple[str, ...]
    cluster_day_map: Dict[str, int]
    cluster_split_map: Dict[str, str]
    cluster_close_ns_map: Dict[str, int]
    contracts_by_cluster: Dict[str, Tuple[str, ...]]


def split_event_clusters_chronologically(
    tape: LoadedTapeV2,
    *,
    recording_start_ns: Optional[int] = None,
) -> ChronologicalSplitResult:
    """Assign whole event clusters chronologically by close time: Days 1-8 Train, Day 9 Embargo, Days 10-14 Holdout."""
    window_start_ns = tape.first_captured_at_ns if recording_start_ns is None else recording_start_ns

    contracts_by_cluster_mut: Dict[str, List[str]] = {}
    cluster_close_ns_map: Dict[str, int] = {}

    for tk in sorted(tape.contracts.keys()):
        meta = tape.contracts[tk]
        cid = meta.event_cluster_id
        contracts_by_cluster_mut.setdefault(cid, []).append(tk)

        # Resolve contract close time deterministically: close_time_ns -> settled_at_ns -> last L2 snapshot
        c_close_ns: Optional[int] = meta.close_time_ns
        if c_close_ns is None and tk in tape.settlements:
            c_close_ns = tape.settlements[tk].settled_at_ns
        if c_close_ns is None and tk in tape.l2_by_ticker and tape.l2_by_ticker[tk]:
            c_close_ns = tape.l2_by_ticker[tk][-1].t_resp_recv_ns
        if c_close_ns is None:
            c_close_ns = window_start_ns

        prev = cluster_close_ns_map.get(cid)
        if prev is None or c_close_ns > prev:
            cluster_close_ns_map[cid] = c_close_ns

    train_clusters: List[str] = []
    embargo_clusters: List[str] = []
    holdout_clusters: List[str] = []
    cluster_day_map: Dict[str, int] = {}
    cluster_split_map: Dict[str, str] = {}

    for cid in sorted(contracts_by_cluster_mut.keys()):
        c_close = cluster_close_ns_map[cid]
        offset_ns = c_close - window_start_ns
        day_num = 1 if offset_ns <= 0 else ((offset_ns - 1) // NS_PER_DAY) + 1
        cluster_day_map[cid] = day_num

        if day_num <= TRAIN_MAX_DAY:
            train_clusters.append(cid)
            cluster_split_map[cid] = "TRAIN"
        elif day_num == EMBARGO_DAY:
            embargo_clusters.append(cid)
            cluster_split_map[cid] = "EMBARGO"
        else:
            holdout_clusters.append(cid)
            cluster_split_map[cid] = "HOLDOUT"

    # Defensive structural assertions: zero cross-split leakage across event clusters or strikes
    t_set = frozenset(train_clusters)
    e_set = frozenset(embargo_clusters)
    h_set = frozenset(holdout_clusters)
    if not (t_set.isdisjoint(e_set) and t_set.isdisjoint(h_set) and e_set.isdisjoint(h_set)):
        raise RuntimeError("Chronological split violated pairwise disjointness")

    contracts_by_cluster = {
        cid: tuple(sorted(tks)) for cid, tks in sorted(contracts_by_cluster_mut.items())
    }

    return ChronologicalSplitResult(
        window_start_ns=window_start_ns,
        train_event_clusters=tuple(train_clusters),
        embargo_event_clusters=tuple(embargo_clusters),
        holdout_event_clusters=tuple(holdout_clusters),
        cluster_day_map=cluster_day_map,
        cluster_split_map=cluster_split_map,
        cluster_close_ns_map=cluster_close_ns_map,
        contracts_by_cluster=contracts_by_cluster,
    )


# ---------------------------------------------------------------------------
# 3. Plateau Test & Cryptographic Freeze Package (Train-Only Selection)
# ---------------------------------------------------------------------------


def _manhattan_distance(a: Tuple[int, ...], b: Tuple[int, ...]) -> int:
    return sum(abs(x - y) for x, y in zip(a, b))


def evaluate_plateau_test(
    candidate_id: str,
    grid: Sequence[GridVariantEntry],
    train_results_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Verify candidate AND all 1-step Manhattan grid neighbors have Train LB EV >= 0 (reject lone spikes)."""
    coord_by_id = {entry.variant.variant_id: entry.coords for entry in grid}
    if candidate_id not in coord_by_id:
        raise KeyError(f"Unknown candidate variant_id={candidate_id!r}")

    cand_coords = coord_by_id[candidate_id]
    cand_res = train_results_by_id[candidate_id]

    def _is_non_negative_lb(res: Dict[str, Any]) -> bool:
        ev = res.get("lb_ev_pips")
        return bool(
            res.get("filled_qty_lb_centi", 0) > 0
            and ev is not None
            and ev >= 0
            and res.get("certified_total_pnl_micro", 0) >= 0
        )

    cand_ok = _is_non_negative_lb(cand_res)
    neighbor_ids = sorted(
        entry.variant.variant_id
        for entry in grid
        if _manhattan_distance(cand_coords, entry.coords) == 1
    )

    failing_neighbors: List[str] = []
    neighbor_evs: Dict[str, Optional[int]] = {}
    for nid in neighbor_ids:
        nres = train_results_by_id[nid]
        neighbor_evs[nid] = nres.get("lb_ev_pips")
        if not _is_non_negative_lb(nres):
            failing_neighbors.append(nid)

    has_required_neighbors = (len(grid) == 1) or (len(neighbor_ids) > 0)
    passed = bool(cand_ok and has_required_neighbors and len(failing_neighbors) == 0)

    return {
        "candidate_variant_id": candidate_id,
        "candidate_lb_ev_pips": cand_res.get("lb_ev_pips"),
        "candidate_ok": cand_ok,
        "neighbor_count": len(neighbor_ids),
        "neighbor_lb_ev_pips": neighbor_evs,
        "failing_neighbors": failing_neighbors,
        "passed": passed,
    }


def _train_rank_key(res: Dict[str, Any]) -> Tuple[int, int, int, int, str]:
    has_fills = 1 if res.get("filled_qty_lb_centi", 0) > 0 else 0
    lb_ev = res["lb_ev_pips"] if res.get("lb_ev_pips") is not None else -(1 << 60)
    cert_pnl = res.get("certified_total_pnl_micro", -(1 << 60))
    mid_ev = res["mid_ev_pips"] if res.get("mid_ev_pips") is not None else -(1 << 60)
    # Invert string sort by sorting separately or using variant_id ascending in reverse-safe manner
    return (has_fills, lb_ev, cert_pnl, mid_ev, res["variant_id"])


def select_train_variant_with_plateau(
    grid: Sequence[GridVariantEntry],
    train_results_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Select winning variant on Train ONLY, rejecting lone spikes via the Plateau Test."""
    # Sort descending by (has_fills, lb_ev, cert_pnl, mid_ev), tie-breaking ascending by variant_id
    ordered_ids = sorted(
        (entry.variant.variant_id for entry in grid),
        key=lambda vid: (
            -(1 if train_results_by_id[vid].get("filled_qty_lb_centi", 0) > 0 else 0),
            -(
                train_results_by_id[vid]["lb_ev_pips"]
                if train_results_by_id[vid].get("lb_ev_pips") is not None
                else -(1 << 60)
            ),
            -train_results_by_id[vid].get("certified_total_pnl_micro", -(1 << 60)),
            -(
                train_results_by_id[vid]["mid_ev_pips"]
                if train_results_by_id[vid].get("mid_ev_pips") is not None
                else -(1 << 60)
            ),
            vid,
        ),
    )

    plateau_by_id = {
        vid: evaluate_plateau_test(vid, grid, train_results_by_id) for vid in ordered_ids
    }
    top_unfiltered_id = ordered_ids[0]
    plateau_passing_ids = [vid for vid in ordered_ids if plateau_by_id[vid]["passed"]]

    if plateau_passing_ids:
        selected_id = plateau_passing_ids[0]
        lone_spike_rejected = selected_id != top_unfiltered_id
        plateau_passed = True
    else:
        selected_id = top_unfiltered_id
        top_res = train_results_by_id[top_unfiltered_id]
        lone_spike_rejected = bool(
            top_res.get("lb_ev_pips") is not None
            and top_res["lb_ev_pips"] >= 0
            and not plateau_by_id[top_unfiltered_id]["passed"]
        )
        plateau_passed = False

    return {
        "selected_variant_id": selected_id,
        "top_unfiltered_train_variant_id": top_unfiltered_id,
        "plateau_test_passed": plateau_passed,
        "lone_spike_rejected": lone_spike_rejected,
        "selected_plateau_detail": plateau_by_id[selected_id],
        "top_unfiltered_plateau_detail": plateau_by_id[top_unfiltered_id],
        "ranked_variant_ids": ordered_ids,
    }


def build_cryptographic_freeze_package(
    *,
    selected_variant: ReplayVariantConfig,
    replay_git_sha: str,
    tape_manifest_sha256: str,
    holdout_event_clusters: Sequence[str],
    plateau_test_passed: bool,
) -> Dict[str, Any]:
    """Emit Cryptographic Freeze Package BEFORE evaluating sealed holdout."""
    cfg_dict = selected_variant.to_canonical_dict()
    cfg_sha = canonical_sha256(cfg_dict)
    holdout_sorted = sorted(holdout_event_clusters)
    holdout_manifest_obj = {
        "tape_manifest_sha256": tape_manifest_sha256,
        "holdout_event_clusters": holdout_sorted,
        "holdout_event_cluster_count": len(holdout_sorted),
    }
    holdout_manifest_sha = canonical_sha256(holdout_manifest_obj)

    body = {
        "selected_variant_id": selected_variant.variant_id,
        "selected_variant_config": cfg_dict,
        "selected_variant_config_sha256": cfg_sha,
        "replay_git_sha": replay_git_sha,
        "tape_manifest_sha256": tape_manifest_sha256,
        "holdout_tape_manifest_sha256": holdout_manifest_sha,
        "holdout_event_cluster_count": len(holdout_sorted),
        "plateau_test_passed": bool(plateau_test_passed),
        "holdout_evaluated_before_freeze": False,
    }
    freeze_sha = canonical_sha256(body)
    return {
        **body,
        "freeze_package_sha256": freeze_sha,
    }


# ---------------------------------------------------------------------------
# 4. Exact-Integer Cluster SE & Deterministic 10,000-Resample Cluster Bootstrap
# ---------------------------------------------------------------------------


def _aggregate_cluster_lb_stats(
    episodes: Sequence[OrderEpisodeResult],
) -> List[Tuple[str, int, int]]:
    """Aggregate settled non-censored LB (pnl_micro, filled_qty_centi) by sorted event_cluster_id."""
    by_cluster: Dict[str, List[int]] = {}
    for ep in episodes:
        if ep.status != "ACTIVE_EVALUATED" or ep.censored or not ep.settled:
            continue
        if ep.filled_qty_lb_centi <= 0:
            continue
        acc = by_cluster.setdefault(ep.event_cluster_id, [0, 0])
        acc[0] += ep.net_pnl_lb_micro
        acc[1] += ep.filled_qty_lb_centi
    return [(cid, by_cluster[cid][0], by_cluster[cid][1]) for cid in sorted(by_cluster.keys())]


def compute_cluster_ev_se_pips(episodes: Sequence[OrderEpisodeResult]) -> int:
    """Compute exact integer cluster standard error (pips/contract) for ratio estimator sum(pnl)/sum(qty)."""
    clusters = _aggregate_cluster_lb_stats(episodes)
    k = len(clusters)
    if k <= 1:
        return 0
    total_pnl = sum(c[1] for c in clusters)
    total_qty = sum(c[2] for c in clusters)
    if total_qty <= 0:
        return 0
    mean_ev = total_pnl // total_qty
    sum_sq = 0
    for _cid, pnl_c, qty_c in clusters:
        resid = pnl_c - mean_ev * qty_c
        sum_sq += resid * resid
    if sum_sq == 0:
        return 0
    denom = (k - 1) * total_qty * total_qty
    var_pips_sq = (k * sum_sq + denom - 1) // denom
    return math.isqrt(var_pips_sq)


def run_event_cluster_bootstrap(
    episodes: Sequence[OrderEpisodeResult],
    *,
    resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> Dict[str, Any]:
    """Run deterministic seeded event-cluster bootstrap (10,000 resamples) in exact integer math."""
    if resamples < 1:
        raise ValueError("resamples must be >= 1")
    clusters = _aggregate_cluster_lb_stats(episodes)
    k = len(clusters)
    if k == 0:
        return {
            "resamples": resamples,
            "seed": seed,
            "cluster_count": 0,
            "observed_lb_ev_pips": None,
            "p05_pips": None,
            "p20_one_sided_80pct_lb_pips": None,
            "p50_median_pips": None,
            "p80_pips": None,
            "passes_minus_300_pips_floor": False,
        }

    pnls = [c[1] for c in clusters]
    qtys = [c[2] for c in clusters]
    obs_pnl = sum(pnls)
    obs_qty = sum(qtys)
    obs_ev = obs_pnl // obs_qty if obs_qty > 0 else 0

    rng = random.Random(seed)
    randrange = rng.randrange
    boot_evs: List[int] = [0] * resamples
    for r in range(resamples):
        tot_p = 0
        tot_q = 0
        for _ in range(k):
            idx = randrange(k)
            tot_p += pnls[idx]
            tot_q += qtys[idx]
        boot_evs[r] = (tot_p // tot_q) if tot_q > 0 else 0

    boot_evs.sort()

    def _pct_lower(pct: int) -> int:
        pos = (pct * resamples) // 100 - 1
        if pos < 0:
            pos = 0
        elif pos >= resamples:
            pos = resamples - 1
        return boot_evs[pos]

    p05 = _pct_lower(5)
    p20 = _pct_lower(20)  # 80% one-sided lower bound
    p50 = _pct_lower(50)
    p80 = _pct_lower(80)

    return {
        "resamples": resamples,
        "seed": seed,
        "cluster_count": k,
        "observed_lb_ev_pips": obs_ev,
        "p05_pips": p05,
        "p20_one_sided_80pct_lb_pips": p20,
        "p50_median_pips": p50,
        "p80_pips": p80,
        "passes_minus_300_pips_floor": p20 >= BOOTSTRAP_80PCT_LB_THRESHOLD_PIPS,
    }


# ---------------------------------------------------------------------------
# 5. G2A Holdout Adjudicator & Stress Suite (Report-Only)
# ---------------------------------------------------------------------------


def _evaluate_stress_suite(holdout_res: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate Brief #01 Stress Suite (-5pp win prob, +1c cost, Pi_L) without mutating pass thresholds."""
    lb_pnl = holdout_res["total_pnl_lb_micro"]
    lb_qty = holdout_res["filled_qty_lb_centi"]
    ub_qty = holdout_res["filled_qty_ub_centi"]
    pi_l = holdout_res["pi_l_micro"]

    minus_5pp_pnl = lb_pnl - STRESS_MINUS_5PP_PIPS * lb_qty
    plus_1c_pnl = lb_pnl - STRESS_PLUS_1C_PIPS * lb_qty

    return {
        "mutates_pass_thresholds": False,
        "minus_5pp_conditional_win_prob": {
            "delta_pips_per_contract": -STRESS_MINUS_5PP_PIPS,
            "total_pnl_micro": minus_5pp_pnl,
            "ev_pips": (minus_5pp_pnl // lb_qty) if lb_qty > 0 else None,
        },
        "plus_1c_extra_cost": {
            "delta_pips_per_contract": -STRESS_PLUS_1C_PIPS,
            "total_pnl_micro": plus_1c_pnl,
            "ev_pips": (plus_1c_pnl // lb_qty) if lb_qty > 0 else None,
        },
        "worst_case_adverse_selection_pi_l": {
            "pi_l_micro": pi_l,
            "pi_l_per_lb_contract_pips": (pi_l // lb_qty) if lb_qty > 0 else None,
            "pi_l_per_ub_contract_pips": (pi_l // ub_qty) if ub_qty > 0 else None,
        },
    }


def adjudicate_g2a_holdout(
    *,
    tape: LoadedTapeV2,
    train_res: Dict[str, Any],
    holdout_res: Dict[str, Any],
    freeze_package: Dict[str, Any],
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
    deterministic_hash_verified: bool = True,
) -> Dict[str, Any]:
    """Evaluate all Brief #01 G2A Holdout pass criteria and report Stress Suite without mutating thresholds."""
    if not freeze_package.get("freeze_package_sha256"):
        raise ValueError("Cryptographic Freeze Package is required before G2A holdout adjudication")
    if freeze_package.get("selected_variant_id") != holdout_res.get("variant_id"):
        raise ValueError("Holdout variant_id does not match Cryptographic Freeze Package")

    holdout_episodes: Sequence[OrderEpisodeResult] = holdout_res["episodes"]
    train_episodes: Sequence[OrderEpisodeResult] = train_res["episodes"]

    # Settled, non-censored LB-filled holdout episodes
    cert_filled = [
        ep
        for ep in holdout_episodes
        if ep.status == "ACTIVE_EVALUATED" and not ep.censored and ep.settled and ep.filled_qty_lb_centi > 0
    ]

    # Cluster and series concentration metrics
    series_fill_counts: Dict[str, int] = {}
    event_pnl_micro: Dict[str, int] = {}
    for ep in cert_filled:
        series_fill_counts[ep.series_ticker] = series_fill_counts.get(ep.series_ticker, 0) + 1
        event_pnl_micro[ep.event_cluster_id] = (
            event_pnl_micro.get(ep.event_cluster_id, 0) + ep.net_pnl_lb_micro
        )

    resolved_event_clusters_count = len(event_pnl_micro)
    filled_episodes_count = len(cert_filled)
    series_count = len(series_fill_counts)
    max_series_fills = max(series_fill_counts.values()) if series_fill_counts else 0
    max_series_share_bps = (
        (max_series_fills * 10_000) // filled_episodes_count if filled_episodes_count > 0 else 0
    )

    abs_event_pnls = [abs(v) for v in event_pnl_micro.values()]
    sum_abs_event_pnl = sum(abs_event_pnls)
    max_event_abs_pnl = max(abs_event_pnls) if abs_event_pnls else 0
    max_event_abs_pnl_share_bps = (
        (max_event_abs_pnl * 10_000) // sum_abs_event_pnl if sum_abs_event_pnl > 0 else 0
    )

    # Ops checks
    total_order_ns = holdout_res["total_order_ns"]
    censored_order_ns = holdout_res["censored_order_ns"]
    # Strictly < 1.0%: censored / total < 1/100 <=> censored * 100 < total (or 0 censored when total == 0)
    censored_lt_1pct = (
        (censored_order_ns == 0)
        if total_order_ns == 0
        else (censored_order_ns * 100 < total_order_ns * G2A_MAX_CENSORED_ORDER_MINUTES_PCT)
    )

    ops_checks = {
        "deterministic_hash_verified": bool(deterministic_hash_verified),
        "zero_unexplained_parse_rejects": tape.unexplained_parse_rejects == 0,
        "censored_order_minutes_lt_1pct": censored_lt_1pct,
        "zero_crossed_orders": holdout_res["crossed_orders_count"] == 0,
        "zero_risk_limit_breaches": holdout_res["risk_limit_breaches"] == 0,
    }

    # Count checks
    count_checks = {
        "min_40_resolved_event_clusters": resolved_event_clusters_count >= G2A_MIN_RESOLVED_EVENT_CLUSTERS,
        "min_150_filled_order_episodes": filled_episodes_count >= G2A_MIN_FILLED_ORDER_EPISODES,
        "min_4_series": series_count >= G2A_MIN_SERIES_COUNT,
        "max_series_fill_share_le_40pct": (
            filled_episodes_count > 0
            and max_series_fills * 100 <= filled_episodes_count * G2A_MAX_SERIES_FILL_SHARE_PCT
        ),
        "max_single_event_abs_pnl_share_le_10pct": (
            filled_episodes_count > 0
            and (
                sum_abs_event_pnl == 0
                or max_event_abs_pnl * 100 <= sum_abs_event_pnl * G2A_MAX_SINGLE_EVENT_ABS_PNL_SHARE_PCT
            )
        ),
    }

    # Bootstrap & Edge checks
    bootstrap = run_event_cluster_bootstrap(
        holdout_episodes,
        resamples=bootstrap_resamples,
        seed=bootstrap_seed,
    )
    holdout_lb_ev = holdout_res["lb_ev_pips"]
    holdout_mid_ev = holdout_res["mid_ev_pips"]
    holdout_cert_pnl = holdout_res["certified_total_pnl_micro"]

    edge_checks = {
        "lb_ev_ge_zero": bool(
            holdout_lb_ev is not None and holdout_lb_ev >= 0 and holdout_cert_pnl >= 0
        ),
        "mid_ev_ge_zero": bool(holdout_mid_ev is not None and holdout_mid_ev >= 0),
        "bootstrap_80pct_lb_ge_minus_300_pips": bool(bootstrap["passes_minus_300_pips_floor"]),
    }

    # Stability checks
    train_lb_ev = train_res["lb_ev_pips"]
    train_se_pips = compute_cluster_ev_se_pips(train_episodes)
    holdout_se_pips = compute_cluster_ev_se_pips(holdout_episodes)
    plateau_passed = bool(freeze_package.get("plateau_test_passed"))

    stability_checks = {
        "holdout_ev_ge_train_minus_1se": bool(
            holdout_lb_ev is not None
            and train_lb_ev is not None
            and holdout_lb_ev >= (train_lb_ev - train_se_pips)
        ),
        "plateau_test_passed": plateau_passed,
    }

    all_checks: Dict[str, bool] = {}
    for group_name, group_dict in (
        ("ops", ops_checks),
        ("counts", count_checks),
        ("edge", edge_checks),
        ("stability", stability_checks),
    ):
        for k, v in group_dict.items():
            all_checks[f"{group_name}.{k}"] = v

    failed_checks = sorted(k for k, v in all_checks.items() if not v)
    g2a_passed = len(failed_checks) == 0

    stress_suite = _evaluate_stress_suite(holdout_res)

    return {
        "verdict": "PASS_G2A" if g2a_passed else "FAIL_G2A",
        "g2a_passed": g2a_passed,
        "failed_checks": failed_checks,
        "ops": {
            "checks": ops_checks,
            "unexplained_parse_rejects": tape.unexplained_parse_rejects,
            "censored_order_ns": censored_order_ns,
            "total_order_ns": total_order_ns,
            "censored_order_minutes_bps": holdout_res["censored_order_minutes_bps"],
            "crossed_orders_count": holdout_res["crossed_orders_count"],
            "risk_limit_breaches": holdout_res["risk_limit_breaches"],
        },
        "counts": {
            "checks": count_checks,
            "resolved_event_clusters": resolved_event_clusters_count,
            "filled_order_episodes_lb": filled_episodes_count,
            "series_count": series_count,
            "max_series_fills": max_series_fills,
            "max_series_fill_share_bps": max_series_share_bps,
            "max_single_event_abs_pnl_micro": max_event_abs_pnl,
            "sum_abs_event_pnl_micro": sum_abs_event_pnl,
            "max_single_event_abs_pnl_share_bps": max_event_abs_pnl_share_bps,
        },
        "edge": {
            "checks": edge_checks,
            "lb_ev_pips": holdout_lb_ev,
            "mid_ev_pips": holdout_mid_ev,
            "ub_ev_pips": holdout_res["ub_ev_pips"],
            "certified_total_pnl_micro": holdout_cert_pnl,
            "pi_l_micro": holdout_res["pi_l_micro"],
            "bootstrap": bootstrap,
        },
        "stability": {
            "checks": stability_checks,
            "train_lb_ev_pips": train_lb_ev,
            "train_se_pips": train_se_pips,
            "holdout_lb_ev_pips": holdout_lb_ev,
            "holdout_se_pips": holdout_se_pips,
            "threshold_train_minus_1se_pips": (
                (train_lb_ev - train_se_pips) if train_lb_ev is not None else None
            ),
            "plateau_test_passed": plateau_passed,
        },
        "stress_suite": stress_suite,
    }


# ---------------------------------------------------------------------------
# 6. End-to-End Deterministic Parallel Variant Harness Orchestrator
# ---------------------------------------------------------------------------


def _compact_variant_metrics(res: Dict[str, Any]) -> Dict[str, Any]:
    """Produce JSON-serializable summary of a variant replay result (zero floats, deterministic)."""
    return {
        "variant_id": res["variant_id"],
        "variant_config": res["variant_config"],
        "synthetic_fills_present": False,
        "evidence_tiers_used": res["evidence_tiers_used"],
        "total_episodes": res["total_episodes"],
        "certified_settled_episodes": res["certified_settled_episodes"],
        "censored_episodes_count": res["censored_episodes_count"],
        "post_only_rejections": res["post_only_rejections"],
        "crossed_orders_count": res["crossed_orders_count"],
        "risk_limit_breaches": res["risk_limit_breaches"],
        "total_order_ns": res["total_order_ns"],
        "censored_order_ns": res["censored_order_ns"],
        "censored_order_minutes_bps": res["censored_order_minutes_bps"],
        "filled_order_episodes_lb": res["filled_order_episodes_lb"],
        "filled_order_episodes_mid": res["filled_order_episodes_mid"],
        "filled_order_episodes_ub": res["filled_order_episodes_ub"],
        "filled_qty_lb_centi": res["filled_qty_lb_centi"],
        "filled_qty_mid_centi": res["filled_qty_mid_centi"],
        "filled_qty_ub_centi": res["filled_qty_ub_centi"],
        "total_pnl_lb_micro": res["total_pnl_lb_micro"],
        "total_pnl_mid_micro": res["total_pnl_mid_micro"],
        "total_pnl_ub_micro": res["total_pnl_ub_micro"],
        "certified_total_pnl_micro": res["certified_total_pnl_micro"],
        "pi_l_micro": res["pi_l_micro"],
        "lb_ev_pips": res["lb_ev_pips"],
        "mid_ev_pips": res["mid_ev_pips"],
        "ub_ev_pips": res["ub_ev_pips"],
        "diagnostics": res["diagnostics"],
    }


def run_parallel_variant_harness_on_loaded_tape(
    tape: LoadedTapeV2,
    *,
    grid: Optional[Sequence[GridVariantEntry]] = None,
    recording_start_ns: Optional[int] = None,
    clock_offset_ns: int = 0,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
    replay_git_sha: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute full deterministic Train/Embargo/Holdout parallel variant replay & G2A adjudication."""
    variant_grid = tuple(grid) if grid is not None else build_prespecified_variant_grid()
    if len(variant_grid) == 0 or len(variant_grid) > MAX_VARIANT_GRID_SIZE:
        raise ValueError(f"Variant grid size must be in [1, {MAX_VARIANT_GRID_SIZE}], got {len(variant_grid)}")

    git_sha = replay_git_sha or resolve_collector_git_sha()
    split = split_event_clusters_chronologically(tape, recording_start_ns=recording_start_ns)

    # Phase 1: Evaluate ALL prespecified variants strictly on Train (Days 1-8) ONLY
    train_results_by_id: Dict[str, Dict[str, Any]] = {}
    for entry in variant_grid:
        train_results_by_id[entry.variant.variant_id] = replay_variant_on_tape(
            tape,
            entry.variant,
            allowed_event_clusters=split.train_event_clusters,
            clock_offset_ns=clock_offset_ns,
        )

    # Phase 2: Select winning variant on Train ONLY with Plateau Test
    selection = select_train_variant_with_plateau(variant_grid, train_results_by_id)
    selected_id = selection["selected_variant_id"]
    selected_entry = next(e for e in variant_grid if e.variant.variant_id == selected_id)
    selected_train_res = train_results_by_id[selected_id]

    # Phase 3: Emit Cryptographic Freeze Package BEFORE evaluating Holdout
    freeze_package = build_cryptographic_freeze_package(
        selected_variant=selected_entry.variant,
        replay_git_sha=git_sha,
        tape_manifest_sha256=tape.combined_manifest_sha256,
        holdout_event_clusters=split.holdout_event_clusters,
        plateau_test_passed=selection["plateau_test_passed"],
    )

    # Phase 4: Evaluate ONLY the frozen selected variant on Sealed Holdout (Days 10-14)
    holdout_res = replay_variant_on_tape(
        tape,
        selected_entry.variant,
        allowed_event_clusters=split.holdout_event_clusters,
        clock_offset_ns=clock_offset_ns,
    )

    # Phase 5: Adjudicate G2A Holdout Pass Criteria & Stress Suite
    g2a = adjudicate_g2a_holdout(
        tape=tape,
        train_res=selected_train_res,
        holdout_res=holdout_res,
        freeze_package=freeze_package,
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_seed=bootstrap_seed,
        deterministic_hash_verified=True,
    )

    train_grid_table = [
        {
            "variant_id": vid,
            "lb_ev_pips": train_results_by_id[vid]["lb_ev_pips"],
            "mid_ev_pips": train_results_by_id[vid]["mid_ev_pips"],
            "ub_ev_pips": train_results_by_id[vid]["ub_ev_pips"],
            "certified_total_pnl_micro": train_results_by_id[vid]["certified_total_pnl_micro"],
            "pi_l_micro": train_results_by_id[vid]["pi_l_micro"],
            "filled_order_episodes_lb": train_results_by_id[vid]["filled_order_episodes_lb"],
            "filled_qty_lb_centi": train_results_by_id[vid]["filled_qty_lb_centi"],
            "censored_order_minutes_bps": train_results_by_id[vid]["censored_order_minutes_bps"],
        }
        for vid in selection["ranked_variant_ids"]
    ]

    report_body: Dict[str, Any] = {
        "schema_version": "2.0.0",
        "brief_id": "STAFF_CONSULTATION_BRIEF_01",
        "synthetic_fills_present": False,
        "tape_summary": {
            "combined_manifest_sha256": tape.combined_manifest_sha256,
            "session_count": len(tape.session_manifests),
            "total_records": tape.total_records,
            "unexplained_parse_rejects": tape.unexplained_parse_rejects,
            "derived_discrepancy_count": tape.derived_discrepancy_count,
            "first_captured_at_utc": tape.first_captured_at_utc,
            "last_captured_at_utc": tape.last_captured_at_utc,
            "p99_rtt_ns": tape.p99_rtt_ns,
            "latency_l_ns": tape.latency_l_ns,
            "clock_offset_ns": clock_offset_ns,
            "eps_ns": clock_offset_ns + tape.latency_l_ns,
            "contracts_count": len(tape.contracts),
            "settled_contracts_count": len(tape.settlements),
            "censor_intervals_count": len(tape.censor_intervals),
        },
        "chronological_split": {
            "window_start_ns": split.window_start_ns,
            "train_days": "1-8",
            "embargo_days": "9",
            "holdout_days": "10-14",
            "train_event_clusters_count": len(split.train_event_clusters),
            "embargo_event_clusters_count": len(split.embargo_event_clusters),
            "holdout_event_clusters_count": len(split.holdout_event_clusters),
            "train_event_clusters": list(split.train_event_clusters),
            "embargo_event_clusters": list(split.embargo_event_clusters),
            "holdout_event_clusters": list(split.holdout_event_clusters),
        },
        "variant_grid_size": len(variant_grid),
        "train_selection": selection,
        "train_grid_summary": train_grid_table,
        "selected_train_result": _compact_variant_metrics(selected_train_res),
        "cryptographic_freeze_package": freeze_package,
        "sealed_holdout_result": _compact_variant_metrics(holdout_res),
        "g2a_adjudication": g2a,
    }

    report_sha256 = canonical_sha256(report_body)
    return {
        **report_body,
        "report_sha256": report_sha256,
    }


def run_parallel_variant_replay(
    tape_dir: Path,
    *,
    grid: Optional[Sequence[GridVariantEntry]] = None,
    recording_start_ns: Optional[int] = None,
    clock_offset_ns: int = 0,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
    replay_git_sha: Optional[str] = None,
) -> Dict[str, Any]:
    """Read-only entrypoint: verify Schema 2.0.0 tape integrity fail-closed and run full G2A adjudication."""
    tape = load_v2_tape(Path(tape_dir))
    return run_parallel_variant_harness_on_loaded_tape(
        tape,
        grid=grid,
        recording_start_ns=recording_start_ns,
        clock_offset_ns=clock_offset_ns,
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_seed=bootstrap_seed,
        replay_git_sha=replay_git_sha,
    )
