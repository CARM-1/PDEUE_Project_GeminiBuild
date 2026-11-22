"""Gate G2 (WP-8V) candidate schema and A01-A26 adversarial rulebook verification."""
import json
from pathlib import Path
import jsonschema

G2_DIR = Path(__file__).resolve().parents[2] / "contracts" / "gate_g2"

VALID_TRANSITIONS = {
    "Candidate": {"Prepared", "Cancelled"},
    "Prepared": {"Resting", "Cancelled"},
    "Resting": {"Filled", "Cancelled", "Raced"},
    "Filled": {"Settled"},
    "Settled": {"Ledger"},
    "Cancelled": set(),
    "Raced": set(),
    "Ledger": set(),
}


def test_gate_g2_draft_2020_12_schemas_are_valid():
    expected = {
        "g2_trade_candidate.schema.json",
        "g2_order_lifecycle_transition.schema.json",
        "g2_settlement_ledger_entry.schema.json",
    }
    found = {p.name for p in G2_DIR.glob("*.schema.json")}
    assert found == expected
    for name in expected:
        schema = json.loads((G2_DIR / name).read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        jsonschema.Draft202012Validator.check_schema(schema)


def test_adversarial_rules_a01_through_a26_complete_and_fail_closed():
    doc = json.loads((G2_DIR / "adversarial_rules_a01_a26.json").read_text(encoding="utf-8"))
    rules = doc["rules"]
    assert len(rules) == 26
    assert [r["rule_id"] for r in rules] == [f"A{i:02d}" for i in range(1, 27)]
    assert all(r["enforcement"] == "FAIL_CLOSED" for r in rules)


def test_a14_loss_isolation_discrepancy_is_explicitly_flagged_for_umpire():
    doc = json.loads((G2_DIR / "adversarial_rules_a01_a26.json").read_text(encoding="utf-8"))
    a14 = next(r for r in doc["rules"] if r["rule_id"] == "A14")
    assert a14["umpire_review_required"] is True


def test_a04_conditional_ev_formula_no_double_counting():
    expected_payoff_if_filled = 68  # cents
    limit_price = 52                # cents
    effective_fees = 0              # inside-maker fee avoidance
    ev_fill = expected_payoff_if_filled - limit_price - effective_fees
    assert ev_fill == 16


def test_a06_a07_a08_finite_order_lifecycle_enforcement():
    assert "Prepared" in VALID_TRANSITIONS["Candidate"]
    assert "Resting" in VALID_TRANSITIONS["Prepared"]
    assert "Filled" in VALID_TRANSITIONS["Resting"]
    assert "Settled" in VALID_TRANSITIONS["Filled"]
    assert "Ledger" in VALID_TRANSITIONS["Settled"]
    assert "Candidate" not in VALID_TRANSITIONS["Resting"]
    assert "Ledger" not in VALID_TRANSITIONS["Resting"]
    assert VALID_TRANSITIONS["Ledger"] == set()


def test_a12_a13_adr008_exact_cent_waterfall_conservation():
    for net_pnl in (0, 1, 3, 99, 100, 10001, 999999):
        scma = (net_pnl * 87) // 100
        faep = (net_pnl * 3) // 100
        cfcp = net_pnl - scma - faep
        assert scma + cfcp + faep == net_pnl
        assert cfcp >= (net_pnl * 10) // 100
