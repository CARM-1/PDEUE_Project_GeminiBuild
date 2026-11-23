"""Gate G2 (WP-8V) fail-closed contract validator and ADR-012 HWM exact-cent waterfall."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import jsonschema

G2_DIR = Path(__file__).resolve().parents[3] / "contracts" / "gate_g2"
_FORMAT_CHECKER = jsonschema.FormatChecker()


@_FORMAT_CHECKER.checks("date-time", ValueError)
def _check_strict_utc_datetime(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Timestamp must be an ISO-8601 UTC string ending in Z")
    datetime.fromisoformat(value[:-1] + "+00:00")
    return True


def _reject_float(raw_value: str) -> Any:
    raise ValueError(f"ADR-008/A12 violation: floating-point literal rejected ({raw_value})")


def loads_strict_json(raw_json: str) -> Any:
    return json.loads(raw_json, parse_float=_reject_float)


def _assert_no_floats(obj: Any, path: str = "$") -> None:
    if isinstance(obj, float):
        raise ValueError(f"ADR-008/A12 violation: float found at {path}")
    if isinstance(obj, dict):
        for k, v in obj.items():
            _assert_no_floats(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _assert_no_floats(v, f"{path}[{i}]")


def _parse_utc(ts: str) -> datetime:
    if not ts.endswith("Z"):
        raise ValueError(f"Non-UTC timestamp rejected: {ts}")
    return datetime.fromisoformat(ts[:-1] + "+00:00")


def validate_gate_g2_payload(schema_filename: str, payload: Dict[str, Any]) -> None:
    _assert_no_floats(payload)
    schema = json.loads((G2_DIR / schema_filename).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema, format_checker=_FORMAT_CHECKER).validate(payload)


def validate_trade_candidate(candidate: Dict[str, Any]) -> None:
    validate_gate_g2_payload("g2_trade_candidate.schema.json", candidate)
    if not (_parse_utc(candidate["evidence_max_ts_utc"]) <= _parse_utc(candidate["pit_cutoff_utc"]) < _parse_utc(candidate["event_blackout_utc"])):
        raise ValueError("A03/A10 violation: must satisfy evidence_max_ts_utc <= pit_cutoff_utc < event_blackout_utc")
    if candidate["fill_conditioned_win_bps"] > candidate["model_prob_bps"]:
        raise ValueError("A04 violation: fill_conditioned_win_bps cannot exceed model_prob_bps")
    price, fee, fill_bps = candidate["limit_price_cents"], candidate["effective_fee_cents"], candidate["fill_conditioned_win_bps"]
    if fill_bps * 100 - (price + fee) * 10000 <= 0:
        raise ValueError("A04/A05 violation: exact fill-conditioned EV must be strictly positive")
    if candidate["expected_payoff_if_filled_cents"] > fill_bps // 100:
        raise ValueError("A04 violation: expected_payoff_if_filled_cents must round conservatively downward")
    expected_ev = candidate["expected_payoff_if_filled_cents"] - price - fee
    if candidate["conditional_ev_cents"] != expected_ev or expected_ev < 1:
        raise ValueError("A04/A05 violation: conditional_ev_cents mismatch or non-positive")


def validate_fill_events(fills: Iterable[Dict[str, Any]], reserved_qty: int) -> int:
    seen, total = set(), 0
    for fill in fills:
        validate_gate_g2_payload("g2_fill_event.schema.json", fill)
        if fill["fill_id"] in seen:
            raise ValueError(f"B3 violation: duplicate fill_id {fill['fill_id']}")
        seen.add(fill["fill_id"])
        total += fill["qty"]
    if total > reserved_qty:
        raise ValueError(f"A09 violation: cumulative fills ({total}) exceed reserved_qty ({reserved_qty})")
    return total


def validate_transition_sequence(transitions: List[Dict[str, Any]], candidate_provenance: str) -> None:
    if not transitions:
        raise ValueError("Transition sequence cannot be empty")
    seq, prev_state, prev_filled, locked_res = 1, None, 0, None
    for tr in transitions:
        validate_gate_g2_payload("g2_order_lifecycle_transition.schema.json", tr)
        if tr["transition_seq"] != seq:
            raise ValueError(f"B8 violation: expected transition_seq {seq}, got {tr['transition_seq']}")
        if tr["from_state"] != prev_state:
            raise ValueError(f"A07 violation: chain break from {prev_state} to {tr['from_state']}")
        if tr["to_state"] == "Resting" and str(candidate_provenance or "").strip().upper().replace("-", "_").replace(" ", "_") != "OBSERVED_L2":
            raise ValueError("A02/B6 violation: OBSERVATIONS_ONLY candidates cannot enter Resting")
        if tr["filled_qty"] < prev_filled or tr["filled_qty"] > tr["reserved_qty"]:
            raise ValueError("A09/B2 violation: filled_qty must be non-decreasing and <= reserved_qty")
        if tr["to_state"] == "Prepared":
            locked_res = tr["reserved_qty"]
        elif locked_res is not None and tr["reserved_qty"] != locked_res:
            raise ValueError("B2 violation: reserved_qty must remain immutable after Prepared")
        prev_state, prev_filled, seq = tr["to_state"], tr["filled_qty"], seq + 1


def split_positive_hwm_profit(hwm_eligible_profit_cents: int) -> Tuple[int, int, int, int]:
    if isinstance(hwm_eligible_profit_cents, float) or hwm_eligible_profit_cents <= 0:
        raise ValueError("A14/B4 violation: waterfall requires strictly positive integer profit")
    scma = (hwm_eligible_profit_cents * 87) // 100
    faep = (hwm_eligible_profit_cents * 3) // 100
    cfcp = hwm_eligible_profit_cents - scma - faep
    residual = cfcp - ((hwm_eligible_profit_cents * 10) // 100)
    assert scma + cfcp + faep == hwm_eligible_profit_cents and residual in (0, 1, 2)
    return scma, cfcp, faep, residual


def compute_hwm_settlement_allocations(net_pnl_cents: int, equity_before_cents: int, high_water_mark_before_cents: int) -> Dict[str, int]:
    _assert_no_floats({"p": net_pnl_cents, "e": equity_before_cents, "h": high_water_mark_before_cents})
    if net_pnl_cents <= 0:
        return {"high_water_mark_before_cents": high_water_mark_before_cents, "high_water_mark_after_cents": high_water_mark_before_cents, "hwm_eligible_profit_cents": 0, "scma_allocation_cents": net_pnl_cents, "cfcp_allocation_cents": 0, "faep_allocation_cents": 0, "residual_cents": 0}
    recovery = min(net_pnl_cents, max(0, high_water_mark_before_cents - equity_before_cents))
    hwm_eligible = net_pnl_cents - recovery
    if hwm_eligible == 0:
        return {"high_water_mark_before_cents": high_water_mark_before_cents, "high_water_mark_after_cents": high_water_mark_before_cents, "hwm_eligible_profit_cents": 0, "scma_allocation_cents": net_pnl_cents, "cfcp_allocation_cents": 0, "faep_allocation_cents": 0, "residual_cents": 0}
    scma_hwm, cfcp, faep, residual = split_positive_hwm_profit(hwm_eligible)
    scma_total = recovery + scma_hwm
    return {"high_water_mark_before_cents": high_water_mark_before_cents, "high_water_mark_after_cents": equity_before_cents + scma_total, "hwm_eligible_profit_cents": hwm_eligible, "scma_allocation_cents": scma_total, "cfcp_allocation_cents": cfcp, "faep_allocation_cents": faep, "residual_cents": residual}


def validate_settlement_ledger_entry(entry: Dict[str, Any], max_loss_cents: int, prev_outbox_sequence_id: int = 0) -> None:
    validate_gate_g2_payload("g2_settlement_ledger_entry.schema.json", entry)
    if entry["outbox_sequence_id"] != prev_outbox_sequence_id + 1:
        raise ValueError("B8 violation: outbox_sequence_id must be strictly increasing and gapless")
    if entry["net_pnl_cents"] != entry["payout_cents"] - entry["cost_cents"] - entry["fees_cents"]:
        raise ValueError("B4 violation: net_pnl_cents mismatch")
    if entry["net_pnl_cents"] < -max_loss_cents:
        raise ValueError("A14/B4 violation: loss exceeds reserved max loss")
    if entry["scma_allocation_cents"] + entry["cfcp_allocation_cents"] + entry["faep_allocation_cents"] != entry["net_pnl_cents"]:
        raise ValueError("ADR-008 violation: allocations do not sum to net_pnl_cents")
    if entry["net_pnl_cents"] < 0 and entry["scma_allocation_cents"] != entry["net_pnl_cents"]:
        raise ValueError("A14 violation: losing settlement must allocate 100% to SCMA")
    if entry["hwm_eligible_profit_cents"] > 0 and entry["residual_cents"] != entry["cfcp_allocation_cents"] - ((entry["hwm_eligible_profit_cents"] * 10) // 100):
        raise ValueError("A13 violation: residual_cents mismatch")
