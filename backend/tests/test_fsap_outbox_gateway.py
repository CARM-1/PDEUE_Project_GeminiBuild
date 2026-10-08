import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft7Validator, FormatChecker, ValidationError

from app.domain.accounting_gateway import AccountingGateway
from app.domain.fsap_engine import FSAPEngine


SCHEMA_DIR = Path(__file__).resolve().parents[2] / "contracts" / "schemas"


@pytest.fixture
def facility_payload():
    return {
        "@context": "https://schema.pdeue.org/accounting/v1",
        "event_type": "STABILITY_ADVANCE_FACILITY_REGISTERED",
        "facility_id": "FSAP-ADV-2026-0001",
        "timestamp": "2026-09-27T12:00:00+00:00",
        "recipient_scma_id": "SCMA-MEMBER-7",
        "household_id": "HOUSEHOLD-7",
        "total_advance_cents": 100_01,
        "disbursement_plan": {
            "direct_creditor_payments": [
                {
                    "creditor_name": "Opaque Creditor Label",
                    "reference_id": "CREDITOR-TOKEN-1",
                    "amount_cents": 7_001,
                    "disbursement_method": "CORPORATE_ACH",
                }
            ],
            "initial_scma_seed_cents": 3_000,
        },
        "amortization_terms": {
            "interception_percentage": 0.50,
            "f2_discretionary_bounds": {
                "min_percentage": 0.30,
                "max_percentage": 0.70,
                "adjustment_lock_days": 30,
            },
            "recovery_target_cents": 10_001,
            "voluntary_pay_forward_eligible": True,
        },
        "governance_signatures": [
            {
                "role": "F2_HEAD_OF_HOUSEHOLD",
                "actor_id": "ACTOR-F2-7",
                "signed_at": "2026-09-27T11:58:00+00:00",
                "signature_hmac_sha256": "a" * 64,
            },
            {
                "role": "CHIEF_ADMINISTRATOR",
                "actor_id": "ACTOR-ADMIN-1",
                "signed_at": "2026-09-27T11:59:00+00:00",
                "signature_hmac_sha256": "b" * 64,
            },
        ],
    }


def test_if039_schema_conformance(facility_payload):
    schema = json.loads(
        (SCHEMA_DIR / "IF-039_StabilityAdvanceFacilityRegistered.json").read_text()
    )
    Draft7Validator(schema, format_checker=FormatChecker()).validate(facility_payload)
    assert FSAPEngine().register_facility(facility_payload) == facility_payload


@pytest.mark.parametrize("missing_role", ["F2_HEAD_OF_HOUSEHOLD", "CHIEF_ADMINISTRATOR"])
def test_if039_dual_signature_requirement(facility_payload, missing_role):
    invalid = deepcopy(facility_payload)
    invalid["governance_signatures"] = [
        signature
        for signature in invalid["governance_signatures"]
        if signature["role"] != missing_role
    ]
    with pytest.raises(ValidationError):
        FSAPEngine().register_facility(invalid)

    duplicate = deepcopy(facility_payload)
    retained = next(
        signature
        for signature in duplicate["governance_signatures"]
        if signature["role"] != missing_role
    )
    duplicate["governance_signatures"] = [retained, deepcopy(retained)]
    with pytest.raises(ValueError, match="dual control"):
        FSAPEngine().register_facility(duplicate)


@pytest.mark.parametrize(
    ("sweep_cents", "ratio", "expected"),
    [(1, 0.50, (1, 0)), (101, 0.30, (30, 71)), (10_001, 0.70, (7_001, 3_000))],
)
def test_sweep_amortization_exact_cent_split(sweep_cents, ratio, expected):
    split = FSAPEngine().calculate_sweep_split(sweep_cents, ratio)
    assert split == expected
    assert sum(split) == sweep_cents
    assert all(isinstance(amount, int) for amount in split)


def test_interception_ratio_bounds_and_30day_lock(facility_payload):
    engine = FSAPEngine()
    engine.register_facility(facility_payload)
    changed_at = datetime(2026, 9, 27, tzinfo=timezone.utc)

    for invalid_ratio in (0.2999, 0.7001):
        with pytest.raises(ValueError, match="between 0.30 and 0.70"):
            engine.update_interception_ratio(
                facility_payload["facility_id"],
                "F2_HEAD_OF_HOUSEHOLD",
                invalid_ratio,
                changed_at,
            )
    with pytest.raises(PermissionError):
        engine.update_interception_ratio(
            facility_payload["facility_id"], "CHIEF_ADMINISTRATOR", 0.60, changed_at
        )

    assert engine.update_interception_ratio(
        facility_payload["facility_id"], "F2_HEAD_OF_HOUSEHOLD", 0.60, changed_at
    ) == 0.60
    with pytest.raises(ValueError, match="locked for 30 days"):
        engine.update_interception_ratio(
            facility_payload["facility_id"],
            "F2_HEAD_OF_HOUSEHOLD",
            0.40,
            changed_at + timedelta(days=29, hours=23),
        )
    assert engine.update_interception_ratio(
        facility_payload["facility_id"],
        "F2_HEAD_OF_HOUSEHOLD",
        0.40,
        changed_at + timedelta(days=30),
    ) == 0.40


def test_apply_amortization_caps_credit_and_conserves_sweep(facility_payload):
    engine = FSAPEngine()
    engine.register_facility(facility_payload)
    first = engine.apply_amortization(facility_payload["facility_id"], 10_001)
    second = engine.apply_amortization(facility_payload["facility_id"], 20_000)

    for event in (first, second):
        assert event["amortization_credit_cents"] + event["member_liquid_cents"] == event[
            "total_sweep_cents"
        ]
    assert second["remaining_advance_cents"] == 0


def test_accounting_gateway_signs_fsap_events(facility_payload):
    gateway = AccountingGateway(secret_key="test-only-signing-key")
    envelopes = [
        gateway.stage_if038_event(
            {
                "@context": "https://schema.pdeue.org/accounting/v1",
                "event_type": "DIVIDEND_DISTRIBUTION_SCHEDULED",
                "timestamp": "2026-09-27T12:00:00+00:00",
                "scma_id": "SCMA-MEMBER-7",
                "amount_cents": 101,
                "tier": "GREEN",
                "destination_opaque_token": "DESTINATION-TOKEN-7",
            }
        ),
        gateway.stage_if039_event(facility_payload),
    ]
    event_040 = FSAPEngine()
    event_040.register_facility(facility_payload)
    envelopes.append(
        gateway.stage_if040_event(
            event_040.apply_amortization(facility_payload["facility_id"], 101)
        )
    )
    envelopes.append(
        gateway.stage_if041_event(
            {
                "@context": "https://schema.pdeue.org/accounting/v1",
                "event_type": "CONTRIBUTOR_INCENTIVE_HARVESTED",
                "timestamp": "2026-09-27T12:01:00+00:00",
                "contributor_scma_id": "SCMA-CONTRIBUTOR-3",
                "pool_income_cents": 10_000,
                "time_weighted_share_bps": 1250,
                "incentive_amount_cents": 1_250,
            }
        )
    )

    assert [event["sequence_id"] for event in envelopes] == [1, 2, 3, 4]
    for envelope in envelopes:
        canonical = gateway._canonicalize_payload(envelope["payload"])
        assert len(envelope["signature_hmac_sha256"]) == 64
        assert gateway.verify_signature(canonical, envelope["signature_hmac_sha256"])
        assert hashlib.sha256(canonical).hexdigest() != envelope["signature_hmac_sha256"]
