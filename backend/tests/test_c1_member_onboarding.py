"""Milestone C1 — End-to-End 5-Stage Member Onboarding Pipeline Unit & API Tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1 import onboarding_router as onboarding_router_mod
from app.db.models import AccountModel, AuditLogRecordModel, Base, OnboardingMemberModel
from app.domain.capital_ledger import CapitalLedger
from app.domain.lineage_hierarchy import LineageHierarchyService, get_lineage_service
from app.domain.member_onboarding import (
    ALLOWED_ROLE_TIERS,
    CERTIFICATION_LEVEL_L1,
    IFAS_PORTAL_HOST,
    INVITE_TTL_HOURS,
    STATUS_ACTIVE,
    STATUS_PENDING_CERT,
    InviteTokenError,
    MemberOnboardingService,
)
from app.main import app


@pytest.fixture()
def isolated_onboarding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Provide an isolated SQLite DB, CapitalLedger, and API client per test."""
    db_file = tmp_path / "c1_onboarding_test.db"
    engine = create_engine(
        f"sqlite:///{db_file.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    ledger = CapitalLedger(initial_balance_cents=1_000_000)
    import copy

    lineage = get_lineage_service()
    houses_snapshot = copy.deepcopy(lineage.CANONICAL_HOUSES)
    service = MemberOnboardingService(
        session_factory=session_factory,
        db_engine=engine,
        lineage_service=lineage,
        capital_ledger=ledger,
    )

    monkeypatch.setattr(
        "app.domain.member_onboarding._onboarding_service",
        service,
    )
    monkeypatch.setattr(
        onboarding_router_mod,
        "get_onboarding_service",
        lambda: service,
    )

    client = TestClient(app)
    try:
        yield {
            "client": client,
            "service": service,
            "session_factory": session_factory,
            "ledger": ledger,
            "lineage": lineage,
        }
    finally:
        lineage.CANONICAL_HOUSES.clear()
        lineage.CANONICAL_HOUSES.update(houses_snapshot)
        engine.dispose()


def _valid_payload(**overrides):
    uid = uuid.uuid4().hex[:6].upper()
    base = {
        "full_name": f"Elena Vance {uid}",
        "member_id": f"MEM-ELENA-{uid}",
        "lineage_house": "HOUSE-03",
        "role_tier": "MEMBER_USER",
        "seed_cents": 100_000,
        "risk_dial_pct": 1.50,
        "is_custodial": False,
        "bank_ref_token": "EXT-REF-PENFED-****4821",
    }
    base.update(overrides)
    return base


def test_single_provisioning_initializes_adr008_cents_hwm_and_48h_invite(isolated_onboarding):
    client = isolated_onboarding["client"]
    session_factory = isolated_onboarding["session_factory"]
    ledger = isolated_onboarding["ledger"]

    payload = _valid_payload(seed_cents=250_000, lineage_house="HOUSE-04", role_tier="F2-H")
    resp = client.post("/api/v1/onboarding/provision", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["status"] == "PROVISIONED"
    member = body["member"]
    invite = body["invite"]

    assert member["member_id"] == payload["member_id"]
    assert member["lineage_code"] == "HOUSE-04"
    assert member["house_id"] == 4
    assert member["role_tier"] == "F2-H"
    assert type(member["seed_cents"]) is int and member["seed_cents"] == 250_000
    assert type(member["high_water_mark_cents"]) is int and member["high_water_mark_cents"] == 250_000
    assert member["risk_dial_bps"] == 150
    assert member["risk_dial_pct"] == 1.50
    assert member["is_custodial"] is False
    assert member["bank_ref_token"] == "EXT-REF-PENFED-****4821"
    assert member["status"] == STATUS_PENDING_CERT
    assert member["requires_orientation"] is True
    assert member["ifas_portal_host"] == IFAS_PORTAL_HOST

    # Verify cryptographic 48-hour single-use invite token
    assert invite["token"].startswith("pdeue_inv_")
    assert len(invite["token"]) >= 40
    assert invite["ttl_hours"] == INVITE_TTL_HOURS
    assert invite["single_use"] is True
    assert member["scma_id"] in invite["activation_link"]
    assert invite["token"] in invite["activation_link"]

    created_dt = datetime.fromisoformat(member["created_at"])
    expires_dt = datetime.fromisoformat(invite["expires_at"])
    assert expires_dt - created_dt == timedelta(hours=48)

    # Verify CapitalLedger HWM initialization (ADR-012)
    scma_id = member["scma_id"]
    assert ledger.members[scma_id]["balance_cents"] == 250_000
    assert ledger.members[scma_id]["high_water_mark_cents"] == 250_000

    # Verify SQLAlchemy AccountModel & OnboardingMemberModel persistence
    db = session_factory()
    try:
        acct = db.get(AccountModel, scma_id)
        assert acct is not None
        assert acct.balance_cents == 250_000
        assert acct.high_water_mark_cents == 250_000
        assert acct.status == STATUS_PENDING_CERT
    finally:
        db.close()

    # Verify /api/v1/portal/member/state reflects Stage 3 & Stage 5 read model
    state_resp = client.get(f"/api/v1/portal/member/state?scma_id={scma_id}")
    assert state_resp.status_code == 200
    state = state_resp.json()
    assert state["cash_cents"] == 250_000
    assert state["high_water_mark_cents"] == 250_000
    assert state["status"] == STATUS_PENDING_CERT
    assert state["requires_orientation"] is True
    assert state["bank_ref_token"] == "EXT-REF-PENFED-****4821"
    assert state["ifas_portal_host"] == "accounting.narratix.io"


def test_all_required_role_tiers_and_custodial_lock(isolated_onboarding):
    client = isolated_onboarding["client"]
    for idx, tier in enumerate(ALLOWED_ROLE_TIERS, start=1):
        house_num = ((idx - 1) % 12) + 1
        resp = client.post(
            "/api/v1/onboarding/provision",
            json=_valid_payload(
                lineage_house=f"HOUSE-{house_num:02d}",
                role_tier=tier,
                seed_cents=10_000 * idx,
                risk_dial_pct=1.00,
                is_custodial=(tier == "MEMBER_USER"),
            ),
        )
        assert resp.status_code == 201, f"Failed for tier {tier}: {resp.text}"
        member = resp.json()["member"]
        assert member["role_tier"] == tier
        assert member["high_water_mark_cents"] == 10_000 * idx

        if tier == "MEMBER_USER":
            # Custodial minor account cannot modify risk dial without F2-H authorization
            lock_resp = client.post(
                "/api/v1/portal/member/risk-dial",
                json={"scma_id": member["scma_id"], "requested_risk_pct": 0.75},
            )
            assert lock_resp.status_code == 403


@pytest.mark.parametrize(
    "bad_seed",
    [100.5, 100.0, "100.00", "$1000", -500, True, False, None],
)
def test_adr008_rejects_float_decimal_boolean_and_negative_seed(isolated_onboarding, bad_seed):
    client = isolated_onboarding["client"]
    resp = client.post(
        "/api/v1/onboarding/provision",
        json=_valid_payload(seed_cents=bad_seed),
    )
    assert resp.status_code in (400, 422)
    assert "ADR-008" in resp.json()["detail"]


@pytest.mark.parametrize(
    "bad_bank_ref",
    [
        "021000021",                     # raw 9-digit ABA routing number
        "123456789012",                  # raw 12-digit bank account number
        "EXT-REF-021000021-****4821",    # embedded routing number (>4 digits)
        "EXT-REF-PENFED-12345678",       # unmasked account digits
        "EXT-REF-ROUTING-****1234",      # raw routing keyword
        "CHASE-****1234",                # missing EXT-REF- prefix
        "EXT-REF-PENFED-1234",           # missing **** mask
        "",
    ],
)
def test_adr011_rejects_raw_routing_or_bank_account_numbers(isolated_onboarding, bad_bank_ref):
    client = isolated_onboarding["client"]
    resp = client.post(
        "/api/v1/onboarding/provision",
        json=_valid_payload(bank_ref_token=bad_bank_ref),
    )
    assert resp.status_code in (400, 422)
    assert "ADR-011" in resp.json()["detail"]


@pytest.mark.parametrize(
    "forbidden_key,forbidden_val",
    [
        ("routing_number", "021000021"),
        ("bank_account_number", "9876543210"),
        ("account_number", "9876543210"),
        ("swift_code", "CHASUS33"),
        ("iban", "GB82WEST12345698765432"),
    ],
)
def test_adr011_rejects_forbidden_banking_credential_fields(
    isolated_onboarding, forbidden_key, forbidden_val
):
    client = isolated_onboarding["client"]
    payload = _valid_payload()
    payload[forbidden_key] = forbidden_val
    resp = client.post("/api/v1/onboarding/provision", json=payload)
    assert resp.status_code in (400, 422)
    assert "ADR-011" in resp.json()["detail"]


def test_risk_dial_bounds_and_house_validation(isolated_onboarding):
    client = isolated_onboarding["client"]
    assert client.post("/api/v1/onboarding/provision", json=_valid_payload(risk_dial_pct=0.25)).status_code == 422
    assert client.post("/api/v1/onboarding/provision", json=_valid_payload(risk_dial_pct=2.50)).status_code == 422
    assert client.post("/api/v1/onboarding/provision", json=_valid_payload(lineage_house="HOUSE-13")).status_code == 422
    assert client.post("/api/v1/onboarding/provision", json=_valid_payload(role_tier="SUPER_ADMIN")).status_code == 422


def test_batch_provisioning_json_csv_and_atomic_rollback(isolated_onboarding):
    client = isolated_onboarding["client"]
    session_factory = isolated_onboarding["session_factory"]

    # 1. Valid JSON batch
    j1 = _valid_payload(full_name="Clara Vance", lineage_house="HOUSE-05", seed_cents=50_000)
    j2 = _valid_payload(full_name="Noah Vance", lineage_house="HOUSE-05", seed_cents=25_000, is_custodial=True)
    resp_json = client.post("/api/v1/onboarding/provision/batch", json={"members": [j1, j2]})
    assert resp_json.status_code == 201, resp_json.text
    body = resp_json.json()
    assert body["status"] == "BATCH_PROVISIONED"
    assert body["count"] == 2
    assert all(item["member"]["high_water_mark_cents"] == item["member"]["seed_cents"] for item in body["provisioned"])

    # 2. Valid CSV batch
    uid_a, uid_b = uuid.uuid4().hex[:5].upper(), uuid.uuid4().hex[:5].upper()
    csv_text = "\n".join(
        [
            "full_name,member_id,lineage_house,role_tier,seed_cents,risk_dial_pct,is_custodial,bank_ref_token",
            f"Maya Vance,MEM-CSV-{uid_a},HOUSE-06,F1,150000,1.25,false,EXT-REF-USAA-****3310",
            f"Leo Vance,MEM-CSV-{uid_b},HOUSE-06,MEMBER_USER,10000,0.75,true,EXT-REF-TRUST-****7744",
        ]
    )
    resp_csv = client.post(
        "/api/v1/onboarding/provision/batch",
        json={"format": "csv", "csv_text": csv_text},
    )
    assert resp_csv.status_code == 201, resp_csv.text
    csv_body = resp_csv.json()
    assert csv_body["count"] == 2
    assert csv_body["provisioned"][0]["member"]["high_water_mark_cents"] == 150_000
    assert csv_body["provisioned"][1]["member"]["is_custodial"] is True

    # 3. Atomic fail-closed batch rollback when Row 2 violates ADR-011 or ADR-008
    good_row = _valid_payload(full_name="Atomic Rollback Test", member_id="MEM-ATOMIC-SHOULD-NOT-EXIST")
    bad_row = _valid_payload(bank_ref_token="021000021")  # raw routing number
    resp_fail = client.post("/api/v1/onboarding/provision/batch", json={"members": [good_row, bad_row]})
    assert resp_fail.status_code == 422
    assert "Row 2" in resp_fail.json()["detail"]

    db = session_factory()
    try:
        assert db.get(OnboardingMemberModel, "MEM-ATOMIC-SHOULD-NOT-EXIST") is None
    finally:
        db.close()

    # 4. CSV decimal float rejection
    bad_csv = "\n".join(
        [
            "full_name,lineage_house,role_tier,seed_cents,risk_dial_pct,is_custodial,bank_ref_token",
            "Decimal Bad,HOUSE-07,MEMBER_USER,100.50,1.00,false,EXT-REF-PENFED-****1111",
        ]
    )
    resp_bad_csv = client.post(
        "/api/v1/onboarding/provision/batch",
        json={"format": "csv", "csv_text": bad_csv},
    )
    assert resp_bad_csv.status_code == 422
    assert "ADR-008" in resp_bad_csv.json()["detail"]


def test_stage2_invite_token_single_use_and_48h_expiry(isolated_onboarding):
    client = isolated_onboarding["client"]
    service = isolated_onboarding["service"]

    # A. Single-use consumption via API
    prov = client.post("/api/v1/onboarding/provision", json=_valid_payload()).json()
    token = prov["invite"]["token"]
    scma_id = prov["member"]["scma_id"]

    act1 = client.post("/api/v1/onboarding/activate", json={"token": token})
    assert act1.status_code == 200, act1.text
    act_body = act1.json()
    assert act_body["status"] == "ACTIVATED_PENDING_CERTIFICATION"
    assert act_body["member_status"] == STATUS_PENDING_CERT
    assert act_body["default_view"] == "orientation"
    assert act_body["member"]["scma_id"] == scma_id
    assert act_body["member"]["invite_activated_at"] is not None

    # Reusing the same single-use token must fail closed (HTTP 410)
    act2 = client.post("/api/v1/onboarding/activate", json={"token": token})
    assert act2.status_code == 410
    assert "already been used" in act2.json()["detail"].lower()

    # Unknown token must fail closed (HTTP 404)
    act_unknown = client.post("/api/v1/onboarding/activate", json={"token": "pdeue_inv_nonexistent_token"})
    assert act_unknown.status_code == 404

    # B. Deterministic 48-hour expiration boundary check
    t0 = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)
    receipt = service.provision_member(_valid_payload(), now=t0)
    exp_token = receipt["invite"]["token"]

    # 48 hours + 1 second later -> expired fail-closed!
    with pytest.raises(InviteTokenError, match="expired") as exc_info:
        service.activate_invite_token(exp_token, now=t0 + timedelta(hours=48, seconds=1))
    assert exc_info.value.status_code == 410
    assert exc_info.value.code == "TOKEN_EXPIRED"


def test_stage4_certification_gate_transitions_pending_to_active_with_audit(isolated_onboarding):
    client = isolated_onboarding["client"]
    session_factory = isolated_onboarding["session_factory"]

    prov = client.post("/api/v1/onboarding/provision", json=_valid_payload(seed_cents=100_000)).json()
    scma_id = prov["member"]["scma_id"]
    token = prov["invite"]["token"]

    # Activate invite (status remains PENDING_TUTOR_CERTIFICATION)
    assert client.post("/api/v1/onboarding/activate", json={"token": token}).status_code == 200
    pre_state = client.get(f"/api/v1/portal/member/state?scma_id={scma_id}").json()
    assert pre_state["status"] == STATUS_PENDING_CERT
    assert pre_state["requires_orientation"] is True

    # Incomplete quiz or wrong chapter must fail closed (HTTP 400)
    bad_quiz = client.post(
        "/api/v1/onboarding/certify",
        json={
            "scma_id": scma_id,
            "chapter_completed": 6,
            "quiz_passed": False,
            "correct_answers": 2,
            "total_questions": 3,
        },
    )
    assert bad_quiz.status_code == 400

    bad_chapter = client.post(
        "/api/v1/onboarding/certify",
        json={
            "scma_id": scma_id,
            "chapter_completed": 5,
            "quiz_passed": True,
            "correct_answers": 3,
            "total_questions": 3,
        },
    )
    assert bad_chapter.status_code == 400

    # Complete Chapter 6 self-check -> upgrades to ACTIVE (STEWARDSHIP_L1_CERTIFIED)
    cert_resp = client.post(
        "/api/v1/onboarding/certify",
        json={
            "scma_id": scma_id,
            "chapter_completed": 6,
            "quiz_passed": True,
            "correct_answers": 3,
            "total_questions": 3,
        },
    )
    assert cert_resp.status_code == 200, cert_resp.text
    cert = cert_resp.json()
    assert cert["status"] == "CERTIFIED"
    assert cert["member_status"] == STATUS_ACTIVE
    assert cert["certification_level"] == CERTIFICATION_LEVEL_L1
    assert cert["certified_at"] is not None
    # Verify auditable ISO-8601 UTC timestamp parses cleanly
    datetime.fromisoformat(cert["certified_at"])

    # Verify /api/v1/portal/member/state now reports ACTIVE & certified
    post_state = client.get(f"/api/v1/portal/member/state?scma_id={scma_id}").json()
    assert post_state["status"] == STATUS_ACTIVE
    assert post_state["certification_level"] == CERTIFICATION_LEVEL_L1
    assert post_state["certified_at"] == cert["certified_at"]
    assert post_state["requires_orientation"] is False

    # Verify DB audit trail & AccountModel status upgrade
    db = session_factory()
    try:
        acct = db.get(AccountModel, scma_id)
        assert acct is not None and acct.status == STATUS_ACTIVE
        audit_actions = [
            row.action for row in db.query(AuditLogRecordModel).all()
        ]
        assert "MEMBER_PROVISIONED" in audit_actions
        assert "INVITE_TOKEN_ACTIVATED" in audit_actions
        assert CERTIFICATION_LEVEL_L1 in audit_actions
    finally:
        db.close()
