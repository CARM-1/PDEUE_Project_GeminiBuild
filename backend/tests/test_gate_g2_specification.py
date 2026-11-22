"""Gate G2 (WP-8V) certified schema, validator, and B1-B9 umpire remediation tests."""
import json
from pathlib import Path
import jsonschema
import pytest
from app.domain.gate_g2_validator import (
    compute_hwm_settlement_allocations, loads_strict_json, split_positive_hwm_profit,
    validate_fill_events, validate_gate_g2_payload, validate_settlement_ledger_entry,
    validate_trade_candidate, validate_transition_sequence,
)

ROOT = Path(__file__).resolve().parents[2]
G2_DIR = ROOT / "contracts" / "gate_g2"
SHA, VER = "a" * 64, "1.1.0-certified-candidate"


def _cand(**ov):
    b = {"schema_version": VER, "candidate_id": "cand-001", "scma_id": "SCMA-MEM-0001", "category": "WEATHER_TEMPERATURE", "venue": "KALSHI", "contract_ticker": "KXHIGHMIA-26NOV22-T80", "side": "YES", "quantity": 10, "evidence_max_ts_utc": "2026-11-22T12:00:00Z", "pit_cutoff_utc": "2026-11-22T12:05:00Z", "event_blackout_utc": "2026-11-22T18:00:00Z", "model_prob_bps": 7200, "fill_conditioned_win_bps": 6800, "limit_price_cents": 52, "effective_fee_cents": 0, "expected_payoff_if_filled_cents": 68, "conditional_ev_cents": 16, "data_provenance": "OBSERVED_L2", "tape_manifest_sha256": SHA}
    b.update(ov)
    return b


def test_all_four_draft_2020_12_schemas_valid_and_docs_present():
    exp = {"g2_trade_candidate.schema.json", "g2_order_lifecycle_transition.schema.json", "g2_fill_event.schema.json", "g2_settlement_ledger_entry.schema.json"}
    assert {p.name for p in G2_DIR.glob("*.schema.json")} == exp
    for n in exp:
        s = json.loads((G2_DIR / n).read_text(encoding="utf-8"))
        assert s["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        jsonschema.Draft202012Validator.check_schema(s)
    assert (ROOT / "docs" / "adr" / "ADR-012_HIGH_WATER_MARK_WATERFALL.md").exists()
    assert (G2_DIR / "ERRATUM_A14_OCT20_DOCKET.md").exists()


def test_b1_rejects_floats_and_invalid_dates():
    with pytest.raises(ValueError, match="floating-point"):
        loads_strict_json('{"limit_price_cents": 52.0}')
    with pytest.raises(ValueError, match="float"):
        validate_trade_candidate(_cand(limit_price_cents=52.0))
    with pytest.raises(jsonschema.ValidationError):
        validate_trade_candidate(_cand(pit_cutoff_utc="garbage"))
    with pytest.raises(jsonschema.ValidationError):
        validate_trade_candidate(_cand(pit_cutoff_utc="2026-02-30T12:00:00Z"))


def test_b2_b3_partial_fill_reaches_ledger_without_stranding():
    fills = [
        {"schema_version": VER, "fill_id": "f-1", "order_id": "ord-1", "scma_id": "SCMA-MEM-0001", "qty": 4, "price_cents": 52, "fee_cents": 0, "timestamp_utc": "2026-11-22T12:10:00Z"},
        {"schema_version": VER, "fill_id": "f-2", "order_id": "ord-1", "scma_id": "SCMA-MEM-0001", "qty": 2, "price_cents": 52, "fee_cents": 0, "timestamp_utc": "2026-11-22T12:12:00Z"},
    ]
    assert validate_fill_events(fills, reserved_qty=10) == 6
    with pytest.raises(ValueError, match="duplicate fill_id"):
        validate_fill_events([fills[0], fills[0]], reserved_qty=10)
    with pytest.raises(ValueError, match="exceed reserved_qty"):
        validate_fill_events(fills, reserved_qty=5)
    tr = [
        {"schema_version": VER, "order_id": "ord-1", "candidate_id": "cand-001", "scma_id": "SCMA-MEM-0001", "transition_seq": 1, "idempotency_key": "idem-0001", "from_state": None, "to_state": "Candidate", "reserved_qty": 10, "filled_qty": 0, "timestamp_utc": "2026-11-22T12:05:00Z", "reason_code": "CANDIDATE_ADMITTED"},
        {"schema_version": VER, "order_id": "ord-1", "candidate_id": "cand-001", "scma_id": "SCMA-MEM-0001", "transition_seq": 2, "idempotency_key": "idem-0002", "from_state": "Candidate", "to_state": "Prepared", "reserved_qty": 10, "filled_qty": 0, "timestamp_utc": "2026-11-22T12:05:01Z", "reason_code": "CAPITAL_RESERVED"},
        {"schema_version": VER, "order_id": "ord-1", "candidate_id": "cand-001", "scma_id": "SCMA-MEM-0001", "transition_seq": 3, "idempotency_key": "idem-0003", "from_state": "Prepared", "to_state": "Resting", "reserved_qty": 10, "filled_qty": 0, "timestamp_utc": "2026-11-22T12:05:02Z", "reason_code": "POSTED_PASSIVE_MAKER"},
        {"schema_version": VER, "order_id": "ord-1", "candidate_id": "cand-001", "scma_id": "SCMA-MEM-0001", "transition_seq": 4, "idempotency_key": "idem-0004", "from_state": "Resting", "to_state": "Filled", "reserved_qty": 10, "filled_qty": 6, "timestamp_utc": "2026-11-22T17:55:00Z", "reason_code": "PARTIAL_FILL_REMAINDER_CANCELLED"},
        {"schema_version": VER, "order_id": "ord-1", "candidate_id": "cand-001", "scma_id": "SCMA-MEM-0001", "transition_seq": 5, "idempotency_key": "idem-0005", "from_state": "Filled", "to_state": "Settled", "reserved_qty": 10, "filled_qty": 6, "timestamp_utc": "2026-11-22T19:00:00Z", "reason_code": "VENUE_SETTLED"},
        {"schema_version": VER, "order_id": "ord-1", "candidate_id": "cand-001", "scma_id": "SCMA-MEM-0001", "transition_seq": 6, "idempotency_key": "idem-0006", "from_state": "Settled", "to_state": "Ledger", "reserved_qty": 10, "filled_qty": 6, "timestamp_utc": "2026-11-22T19:00:01Z", "reason_code": "LEDGER_POSTED"},
    ]
    validate_transition_sequence(tr, candidate_provenance="OBSERVED_L2")
    with pytest.raises(jsonschema.ValidationError):
        validate_gate_g2_payload("g2_order_lifecycle_transition.schema.json", dict(tr[3], to_state="Cancelled", reason_code="PRE_EVENT_BLACKOUT_CANCEL"))


def test_b6_b7_blocks_observations_only_from_resting_and_enforces_a03_a04():
    validate_trade_candidate(_cand())
    no_sha = _cand(); no_sha.pop("tape_manifest_sha256")
    with pytest.raises(jsonschema.ValidationError):
        validate_trade_candidate(no_sha)
    with pytest.raises(ValueError, match="fill_conditioned_win_bps"):
        validate_trade_candidate(_cand(model_prob_bps=6000, fill_conditioned_win_bps=6800))
    with pytest.raises(ValueError, match="A03/A10"):
        validate_trade_candidate(_cand(evidence_max_ts_utc="2026-11-22T12:06:00Z"))
    obs = [
        {"schema_version": VER, "order_id": "ord-2", "candidate_id": "cand-002", "scma_id": "SCMA-MEM-0001", "transition_seq": 1, "idempotency_key": "idem-0101", "from_state": None, "to_state": "Candidate", "reserved_qty": 5, "filled_qty": 0, "timestamp_utc": "2026-11-22T12:05:00Z", "reason_code": "CANDIDATE_ADMITTED"},
        {"schema_version": VER, "order_id": "ord-2", "candidate_id": "cand-002", "scma_id": "SCMA-MEM-0001", "transition_seq": 2, "idempotency_key": "idem-0102", "from_state": "Candidate", "to_state": "Prepared", "reserved_qty": 5, "filled_qty": 0, "timestamp_utc": "2026-11-22T12:05:01Z", "reason_code": "CAPITAL_RESERVED"},
        {"schema_version": VER, "order_id": "ord-2", "candidate_id": "cand-002", "scma_id": "SCMA-MEM-0001", "transition_seq": 3, "idempotency_key": "idem-0103", "from_state": "Prepared", "to_state": "Resting", "reserved_qty": 5, "filled_qty": 0, "timestamp_utc": "2026-11-22T12:05:02Z", "reason_code": "POSTED_PASSIVE_MAKER"},
    ]
    with pytest.raises(ValueError, match="OBSERVATIONS_ONLY"):
        validate_transition_sequence(obs, candidate_provenance="OBSERVATIONS_ONLY")


def test_b4_b5_b8_b9_a14_loss_isolation_and_adr012_high_water_mark():
    with pytest.raises(ValueError):
        split_positive_hwm_profit(-1)
    loss = compute_hwm_settlement_allocations(-100, 10000, 10000)
    assert loss["scma_allocation_cents"] == -100 and loss["cfcp_allocation_cents"] == 0 and loss["faep_allocation_cents"] == 0
    validate_settlement_ledger_entry({"schema_version": VER, "settlement_id": "s-1", "order_id": "o-1", "scma_id": "SCMA-MEM-0001", "outcome": "NO", "payout_cents": 0, "cost_cents": 100, "fees_cents": 0, "net_pnl_cents": -100, **loss, "outbox_sequence_id": 1, "key_id": "k1", "hmac_sha256": SHA}, 100, 0)
    rec = compute_hwm_settlement_allocations(100, 9900, 10000)
    assert rec["hwm_eligible_profit_cents"] == 0 and rec["cfcp_allocation_cents"] == 0 and rec["scma_allocation_cents"] == 100
    cross = compute_hwm_settlement_allocations(100, 9960, 10000)
    assert cross["scma_allocation_cents"] == 92 and cross["cfcp_allocation_cents"] == 7 and cross["faep_allocation_cents"] == 1 and cross["residual_cents"] == 1 and cross["high_water_mark_after_cents"] == 10052
    entry = {"schema_version": VER, "settlement_id": "s-2", "order_id": "o-2", "scma_id": "SCMA-MEM-0001", "outcome": "YES", "payout_cents": 200, "cost_cents": 100, "fees_cents": 0, "net_pnl_cents": 100, **cross, "outbox_sequence_id": 2, "key_id": "k1", "hmac_sha256": SHA}
    validate_settlement_ledger_entry(entry, 100, 1)
    with pytest.raises(ValueError, match="gapless"):
        validate_settlement_ledger_entry(entry, 100, 0)


def test_a01_through_a26_complete_and_a14_resolved():
    doc = json.loads((G2_DIR / "adversarial_rules_a01_a26.json").read_text(encoding="utf-8"))
    assert len(doc["rules"]) == 26 and all(r["enforcement"] == "FAIL_CLOSED" and r["umpire_review_required"] is False for r in doc["rules"])
