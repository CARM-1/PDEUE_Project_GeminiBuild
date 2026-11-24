"""Milestone PR #81 — Unit & Integration Tests:
- Root URL `/` 302 redirect to `/community`
- Alembic migration 005 idempotency, upgrade, and downgrade
- Strict single-seat uniqueness (CHIEF_ADMIN, T3, F3 -> HTTP 409 + atomic succession)
  vs. multi-seat assignments (T1, T2, T2-HOUSEHOLD, F1, F2-H, F2-A, H1, H2, HOUSE_GENEALOGIST)
- Atomic Promotion & Demotion (zero orphaned charges, immediate revocation of former custodian's lookup access)
- INTRA_HOUSE vs. CROSS_HOUSE_ANTI_TRIBAL custodial pairing
- Strict server-side scoped custodial lookup (HTTP 403 on out-of-scope member; R-12 masking on Class T)
- 3-Stage Delegated Onboarding & Genealogical Ratification + signed ADR-011 MEMBER_ADMISSION_RATIFIED IFAS outbox
- Lexicon v0.6 two-layer parity for new governance concepts
"""
from __future__ import annotations

import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.api.v1 import onboarding_router as onboarding_router_mod
from app.api.v1 import lineage_router as lineage_router_mod
from app.api.v1 import portal_router as portal_router_mod
from app.db.models import (
    AccountingOutboxEventModel,
    CustodialAssignmentModel,
    OnboardingMemberModel,
    UserRoleAssignmentModel,
)
from app.domain.accounting_gateway import AccountingGateway
from app.domain.authority_tiers import get_governance_audit_log
from app.domain.lexicon_v05 import BANNED_PLAIN_ENGLISH_JARGON, LEXICON_BY_ID
from app.domain.lineage_hierarchy import LineageHierarchyService
from app.domain.member_onboarding import MemberOnboardingService
from app.domain.role_custody_service import (
    CUSTODY_MODE_CROSS_HOUSE_ANTI_TRIBAL,
    CUSTODY_MODE_INTRA_HOUSE,
    DELEGATION_SCOPE_ADMIN_ONLY,
    DELEGATION_SCOPE_ENCLAVE_WIDE,
    DELEGATION_SCOPE_PER_HOUSE,
    DOSSIER_BOARD_RECOMMENDED,
    DOSSIER_PENDING_RATIFICATION,
    DOSSIER_PROOF_REQUESTED,
    DOSSIER_RATIFIED_PROVISIONED,
    DOSSIER_REJECTED,
    RoleCustodyDelegationService,
)
from app.domain import role_custody_service as rcs_mod
from app.domain import member_onboarding as mo_mod
from app.main import app


CA_HEADERS = {"X-Actor-Role": "CHIEF_ADMIN", "X-Actor-ID": "USR-founder_ch-C8575D7E"}


@pytest.fixture()
def isolated_pr81(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Provide an isolated SQLite DB, fresh services, and TestClient for every PR #81 test."""
    db_file = tmp_path / "pr81_test.db"
    engine = create_engine(
        f"sqlite:///{db_file.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    SessionLocalTest = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    lineage = LineageHierarchyService()
    gateway = AccountingGateway()
    onb_svc = MemberOnboardingService(
        session_factory=SessionLocalTest,
        db_engine=engine,
        lineage_service=lineage,
    )
    svc = RoleCustodyDelegationService(
        session_factory=SessionLocalTest,
        bind_engine=engine,
        lineage_service=lineage,
        onboarding_service=onb_svc,
        accounting_gateway=gateway,
        register_hat_provider=False,
    )

    monkeypatch.setattr(rcs_mod, "_role_custody_service", svc)
    monkeypatch.setattr(mo_mod, "_onboarding_service", onb_svc)
    monkeypatch.setattr(lineage_router_mod, "get_role_custody_service", lambda: svc)
    monkeypatch.setattr(onboarding_router_mod, "get_role_custody_service", lambda: svc)
    monkeypatch.setattr(onboarding_router_mod, "get_onboarding_service", lambda: onb_svc)

    with TestClient(app) as client:
        yield {
            "client": client,
            "svc": svc,
            "onb_svc": onb_svc,
            "gateway": gateway,
            "engine": engine,
            "session_factory": SessionLocalTest,
        }

    engine.dispose()


def test_root_url_redirects_to_community_hearth():
    with TestClient(app) as client:
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/community"


def test_alembic_005_migration_idempotent_upgrade_and_downgrade(tmp_path: Path):
    backend_dir = Path(__file__).resolve().parents[1]
    db_file = tmp_path / "alembic_005.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(cfg, "head")
    # Re-running upgrade head must be 100% idempotent
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    try:
        tables = set(inspect(engine).get_table_names())
        for expected in (
            "user_role_assignments",
            "custodial_assignments",
            "enclave_policy_controls",
            "delegated_onboarding_dossiers",
            "accounting_outbox_events",
        ):
            assert expected in tables, f"Migration 005 missing table {expected}"

        # Downgrade to 004 removes PR #81 tables cleanly without dropping 001..004 tables
        command.downgrade(cfg, "004_add_12_house_lineage_governance")
        tables_after_down = set(inspect(engine).get_table_names())
        for removed in (
            "user_role_assignments",
            "custodial_assignments",
            "enclave_policy_controls",
            "delegated_onboarding_dossiers",
        ):
            assert removed not in tables_after_down
        assert "accounting_outbox_events" in tables_after_down
        assert "lineage_houses" in tables_after_down

        # Re-upgrade to head succeeds cleanly
        command.upgrade(cfg, "head")
        assert "user_role_assignments" in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_single_seat_uniqueness_and_atomic_succession_vs_multi_seat(isolated_pr81):
    client = isolated_pr81["client"]

    # Non-CA cannot assign roles
    denied = client.post(
        "/api/v1/governance/roles/assign",
        headers={"X-Actor-Role": "H2", "X-Actor-ID": "MEM-H2-X"},
        json={"member_id": "MEM-CTO-1", "role_token": "T3"},
    )
    assert denied.status_code == 403

    # Single-seat T3 (CTO) & F3 (CRO): first assignment succeeds, second without succession fails HTTP 409
    for seat_role, first_holder, second_holder in (
        ("T3", "MEM-CTO-ALPHA", "MEM-CTO-BETA"),
        ("F3", "MEM-CRO-ALPHA", "MEM-CRO-BETA"),
    ):
        r1 = client.post(
            "/api/v1/governance/roles/assign",
            headers=CA_HEADERS,
            json={"member_id": first_holder, "role_token": seat_role, "reason": f"Initial {seat_role}"},
        )
        assert r1.status_code == 201, r1.text
        assert r1.json()["assignment"]["role_token"] == seat_role

        # Duplicate seat without atomic_succession fails closed HTTP 409
        r_conflict = client.post(
            "/api/v1/governance/roles/assign",
            headers=CA_HEADERS,
            json={"member_id": second_holder, "role_token": seat_role},
        )
        assert r_conflict.status_code == 409
        assert "SINGLE_SEAT_OCCUPIED" in r_conflict.json()["detail"]

        # Explicit atomic succession handoff succeeds and supersedes prior holder
        r_succ = client.post(
            "/api/v1/governance/roles/assign",
            headers=CA_HEADERS,
            json={
                "member_id": second_holder,
                "role_token": seat_role,
                "atomic_succession": True,
                "reason": f"Planned {seat_role} succession",
            },
        )
        assert r_succ.status_code == 201, r_succ.text
        body = r_succ.json()
        assert body["status"] == "SUCCESSION_HANDOFF_COMPLETE"
        assert body["assignment"]["member_id"] == second_holder
        assert body["superseded_assignment"]["member_id"] == first_holder
        assert body["superseded_assignment"]["status"] == "SUPERSEDED"

    # CHIEF_ADMIN single seat: already held by Founder -> conflict HTTP 409 without succession
    ca_conflict = client.post(
        "/api/v1/governance/roles/assign",
        headers=CA_HEADERS,
        json={"member_id": "MEM-SUCCESSOR-CA", "role_token": "CHIEF_ADMIN"},
    )
    assert ca_conflict.status_code == 409

    # Multi-seat roles: multiple distinct individuals simultaneously across the enclave & 12 Houses
    multi_roles = ("T1", "T2", "T2-HOUSEHOLD", "F1", "F2-H", "F2-A", "H1", "H2", "HOUSE_GENEALOGIST")
    for idx, role_tok in enumerate(multi_roles, start=1):
        for seat_num in (1, 2):
            house_num = ((idx + seat_num) % 12) + 1
            res = client.post(
                "/api/v1/governance/roles/assign",
                headers=CA_HEADERS,
                json={
                    "member_id": f"MEM-{role_tok}-{seat_num}",
                    "role_token": role_tok,
                    "house_id": house_num,
                },
            )
            assert res.status_code == 201, f"Multi-seat failed for {role_tok} #{seat_num}: {res.text}"

    # Verify GovernanceAuditLog recorded succession handoffs
    audit_events = get_governance_audit_log().list_events(event_type="ROLE_SUCCESSION_HANDOFF", limit=10)
    assert len(audit_events) >= 2


def test_atomic_promotion_and_demotion_zero_orphans_and_immediate_lookup_revocation(isolated_pr81):
    client = isolated_pr81["client"]
    SessionLocalTest = isolated_pr81["session_factory"]

    # Create two F1 mentors in House 3 and one charge in House 3
    for mid in ("MEM-F1-PRIMARY", "MEM-F1-FALLBACK"):
        r = client.post(
            "/api/v1/governance/roles/assign",
            headers=CA_HEADERS,
            json={"member_id": mid, "role_token": "F1", "house_id": 3},
        )
        assert r.status_code == 201

    # Provision a member in House 3 so they exist in the directory
    prov = client.post(
        "/api/v1/onboarding/provision",
        json={
            "member_id": "MEM-CHARGE-H3",
            "full_name": "Clara House Three",
            "lineage_house": "HOUSE-03",
            "role_tier": "MEMBER_USER",
            "seed_cents": 50_000,
            "risk_dial_bps": 100,
            "is_custodial": True,
            "bank_ref_token": "EXT-REF-PENFED-****3030",
        },
    )
    assert prov.status_code == 201, prov.text
    charge_scma = prov.json()["member"]["scma_id"]

    # Assign MEM-F1-PRIMARY as custodian of MEM-CHARGE-H3
    ca_assign = client.post(
        "/api/v1/governance/custody/assign",
        headers=CA_HEADERS,
        json={
            "charge_member_id": "MEM-CHARGE-H3",
            "charge_scma_id": charge_scma,
            "charge_house_id": 3,
            "custodian_member_id": "MEM-F1-PRIMARY",
            "custodian_role": "F1",
        },
    )
    assert ca_assign.status_code == 201

    # Before demotion: MEM-F1-PRIMARY CAN look up MEM-CHARGE-H3 (with F1 balance masking)
    before = client.get(
        "/api/v1/portal/custodial/member/MEM-CHARGE-H3",
        headers={"X-Actor-Role": "F1", "X-Actor-ID": "MEM-F1-PRIMARY"},
    )
    assert before.status_code == 200
    assert before.json()["member"]["member_id"] == "MEM-CHARGE-H3"
    assert before.json()["member"]["balance_display"] == "$****.**"

    # Promote MEM-F1-PRIMARY to F2-H first (atomic promotion)
    prom = client.post(
        "/api/v1/governance/roles/promote",
        headers=CA_HEADERS,
        json={"member_id": "MEM-F1-PRIMARY", "to_role": "F2-H", "house_id": 3, "reason": "Earned F2-H"},
    )
    assert prom.status_code == 200
    assert prom.json()["to_role"] == "F2-H"
    assert prom.json()["orphaned_charges_count"] == 0

    # Now atomically DEMOTE MEM-F1-PRIMARY -> MEMBER_USER
    dem = client.post(
        "/api/v1/governance/roles/demote",
        headers=CA_HEADERS,
        json={"member_id": "MEM-F1-PRIMARY", "to_role": "MEMBER_USER", "reason": "Step-down review"},
    )
    assert dem.status_code == 200, dem.text
    dem_body = dem.json()
    assert dem_body["orphaned_charges_count"] == 0
    assert dem_body["lingering_custodial_access_count"] == 0
    assert len(dem_body["reassigned_charges"]) == 1
    reassigned = dem_body["reassigned_charges"][0]
    assert reassigned["charge_member_id"] == "MEM-CHARGE-H3"
    assert reassigned["custodian_member_id"] == "MEM-F1-FALLBACK"
    assert reassigned["active"] is True

    # Verify DB state: 0 active custodial assignments for demoted officer, 1 active for fallback
    with SessionLocalTest() as db:
        lingering = (
            db.query(CustodialAssignmentModel)
            .filter(
                CustodialAssignmentModel.custodian_member_id == "MEM-F1-PRIMARY",
                CustodialAssignmentModel.active == 1,
            )
            .count()
        )
        assert lingering == 0

    # Immediately after demotion: MEM-F1-PRIMARY gets HTTP 403 trying to inspect former charge (even with stale header!)
    after_stale = client.get(
        "/api/v1/portal/custodial/member/MEM-CHARGE-H3",
        headers={"X-Actor-Role": "F2-H", "X-Actor-ID": "MEM-F1-PRIMARY"},
    )
    assert after_stale.status_code == 403
    after_member = client.get(
        "/api/v1/portal/custodial/member/MEM-CHARGE-H3",
        headers={"X-Actor-Role": "MEMBER_USER", "X-Actor-ID": "MEM-F1-PRIMARY"},
    )
    assert after_member.status_code == 403

    # New fallback custodian MEM-F1-FALLBACK immediately has scoped access
    fallback_view = client.get(
        "/api/v1/portal/custodial/member/MEM-CHARGE-H3",
        headers={"X-Actor-Role": "F1", "X-Actor-ID": "MEM-F1-FALLBACK"},
    )
    assert fallback_view.status_code == 200

    # Founder Apex Immunity: cannot demote Founder
    founder_demote = client.post(
        "/api/v1/governance/roles/demote",
        headers={"X-Actor-Role": "F3", "X-Actor-ID": "MEM-CRO"},
        json={"member_id": "USR-founder_ch-C8575D7E", "to_role": "MEMBER_USER"},
    )
    assert founder_demote.status_code == 403


def test_intra_house_vs_cross_house_anti_tribal_custody_pairing(isolated_pr81):
    client = isolated_pr81["client"]

    # Default mode must be INTRA_HOUSE
    cfg = client.get("/api/v1/governance/custody-mode").json()
    assert cfg["custody_assignment_mode"] == CUSTODY_MODE_INTRA_HOUSE

    # Register F1 mentors in House 4 and House 7
    assert client.post(
        "/api/v1/governance/roles/assign",
        headers=CA_HEADERS,
        json={"member_id": "MEM-MENTOR-H4", "role_token": "F1", "house_id": 4},
    ).status_code == 201
    assert client.post(
        "/api/v1/governance/roles/assign",
        headers=CA_HEADERS,
        json={"member_id": "MEM-MENTOR-H7", "role_token": "F1", "house_id": 7},
    ).status_code == 201

    # In INTRA_HOUSE mode, auto-assign for a House 4 charge selects House 4 mentor
    intra = client.post(
        "/api/v1/governance/custody/assign",
        headers=CA_HEADERS,
        json={
            "charge_member_id": "MEM-APPRENTICE-H4A",
            "charge_scma_id": "SCMA-H4A-0001",
            "charge_house_id": 4,
        },
    )
    assert intra.status_code == 201
    assert intra.json()["assignment"]["custodian_member_id"] == "MEM-MENTOR-H4"
    assert intra.json()["assignment"]["assignment_mode"] == CUSTODY_MODE_INTRA_HOUSE

    # Toggle CROSS_HOUSE_ANTI_TRIBAL (non-CA blocked with HTTP 403)
    assert client.post(
        "/api/v1/governance/custody-mode",
        headers={"X-Actor-Role": "H2"},
        json={"custody_assignment_mode": CUSTODY_MODE_CROSS_HOUSE_ANTI_TRIBAL},
    ).status_code == 403

    toggled = client.post(
        "/api/v1/governance/custody-mode",
        headers=CA_HEADERS,
        json={"custody_assignment_mode": CUSTODY_MODE_CROSS_HOUSE_ANTI_TRIBAL, "reason": "Mitigate house tribalism"},
    )
    assert toggled.status_code == 200
    assert toggled.json()["custody_assignment_mode"] == CUSTODY_MODE_CROSS_HOUSE_ANTI_TRIBAL

    # In CROSS_HOUSE_ANTI_TRIBAL mode, auto-assign for House 4 charge MUST pair with cross-house mentor (House 7)
    cross = client.post(
        "/api/v1/governance/custody/assign",
        headers=CA_HEADERS,
        json={
            "charge_member_id": "MEM-APPRENTICE-H4B",
            "charge_scma_id": "SCMA-H4B-0002",
            "charge_house_id": 4,
        },
    )
    assert cross.status_code == 201
    assert cross.json()["assignment"]["custodian_member_id"] == "MEM-MENTOR-H7"
    assert cross.json()["assignment"]["assignment_mode"] == CUSTODY_MODE_CROSS_HOUSE_ANTI_TRIBAL

    # Explicitly trying to force same-house F1 pairing under CROSS_HOUSE_ANTI_TRIBAL fails HTTP 409
    bad_intra = client.post(
        "/api/v1/governance/custody/assign",
        headers=CA_HEADERS,
        json={
            "charge_member_id": "MEM-APPRENTICE-H4B",
            "charge_scma_id": "SCMA-H4B-0002",
            "charge_house_id": 4,
            "custodian_member_id": "MEM-MENTOR-H4",
            "custodian_role": "F1",
        },
    )
    assert bad_intra.status_code == 409
    assert "ANTI_TRIBALISM_CUSTODY_VIOLATION" in bad_intra.json()["detail"]


def test_scoped_custodial_lookup_isolation_403_and_class_t_r12_masking(isolated_pr81):
    client = isolated_pr81["client"]

    # Assign an H2 officer strictly to House 1
    assert client.post(
        "/api/v1/governance/roles/assign",
        headers=CA_HEADERS,
        json={"member_id": "MEM-H2-HOUSE1", "role_token": "H2", "house_id": 1},
    ).status_code == 201

    # CHIEF_ADMIN & F3 see enclave-wide members (including House 2 Julian and House 5 seed)
    ca_lookup = client.get("/api/v1/portal/custodial/lookup?q=HOUSE-05", headers=CA_HEADERS)
    assert ca_lookup.status_code == 200
    assert ca_lookup.json()["count"] >= 1
    assert ca_lookup.json()["scope"] == "ENCLAVE_WIDE"

    f3_lookup = client.get(
        "/api/v1/portal/custodial/lookup?q=Julian",
        headers={"X-Actor-Role": "F3"},
    )
    assert f3_lookup.status_code == 200
    assert f3_lookup.json()["count"] >= 1
    assert f3_lookup.json()["results"][0]["lookup_type"] == "MACRO_RISK_PROFILE"

    # H2 of House 1 sees House 1 members, but gets HTTP 403 requesting a House 5 member detail
    h1_ok = client.get(
        "/api/v1/portal/custodial/member/SCMA-ELEANOR_-B2B31C9E",
        headers={"X-Actor-Role": "H2", "X-Actor-ID": "MEM-H2-HOUSE1", "X-House-ID": "1"},
    )
    assert h1_ok.status_code == 200

    h1_out_of_scope = client.get(
        "/api/v1/portal/custodial/member/SCMA-HOUSE-05-SEED",
        headers={"X-Actor-Role": "H2", "X-Actor-ID": "MEM-H2-HOUSE1", "X-House-ID": "1"},
    )
    assert h1_out_of_scope.status_code == 403
    assert "OUT_OF_SCOPE_CUSTODIAL_LOOKUP" in h1_out_of_scope.json()["detail"]

    # Class T (T1, T2, T2-HOUSEHOLD, T3) receives strictly R-12 masked node/relay results ($****.** and SCMA-MEM-****)
    for tech_tier in ("T1", "T2", "T2-HOUSEHOLD", "T3"):
        t_resp = client.get(f"/api/v1/portal/custodial/lookup?q=HOUSE-01&role={tech_tier}")
        assert t_resp.status_code == 200
        body = t_resp.json()
        assert body["r12_masked"] is True
        assert body["scope"] == "TECHNICAL_NODE_RELAY_R12_MASKED"
        assert body["count"] >= 1
        for item in body["results"]:
            assert item["scma_id"] == "SCMA-MEM-****"
            assert item["balance_display"] == "$****.**"
            assert item["balance_cents"] == "$****.**"
            assert item["r12_masked"] is True
            assert "500000" not in json.dumps(item)
            assert "Eleanor" not in json.dumps(item)

        t_detail = client.get(f"/api/v1/portal/custodial/member/SCMA-ELEANOR_-B2B31C9E?role={tech_tier}")
        assert t_detail.status_code == 200
        detail_m = t_detail.json()["member"]
        assert detail_m["scma_id"] == "SCMA-MEM-****"
        assert detail_m["balance_display"] == "$****.**"
        assert detail_m["r12_masked"] is True

    # Standard MEMBER_USER is blocked HTTP 403
    assert client.get(
        "/api/v1/portal/custodial/lookup?q=Julian",
        headers={"X-Actor-Role": "MEMBER_USER", "X-Actor-ID": "USR-julian_va-A1F98B21"},
    ).status_code == 403


def test_three_stage_delegated_onboarding_genealogical_ratification_and_ifas_outbox(isolated_pr81):
    client = isolated_pr81["client"]
    SessionLocalTest = isolated_pr81["session_factory"]
    gateway = isolated_pr81["gateway"]

    # Seed House 6 Genealogist, House 6 H2 Leader, and cross-house F1 mentor in House 9
    assert client.post(
        "/api/v1/governance/roles/assign",
        headers=CA_HEADERS,
        json={"member_id": "MEM-GENEALOGIST-H6", "role_token": "HOUSE_GENEALOGIST", "house_id": 6},
    ).status_code == 201
    assert client.post(
        "/api/v1/governance/roles/assign",
        headers=CA_HEADERS,
        json={"member_id": "MEM-H2-H6", "role_token": "H2", "house_id": 6},
    ).status_code == 201
    assert client.post(
        "/api/v1/governance/roles/assign",
        headers=CA_HEADERS,
        json={"member_id": "MEM-MENTOR-H9", "role_token": "F1", "house_id": 9},
    ).status_code == 201

    dossier_payload = {
        "applicant_full_name": "Nadia Carmichael-McCormick",
        "target_house_id": 6,
        "kinship_verification": "Verified lineal granddaughter via House 06 birth & family Bible registry",
        "custodial_status": "MINOR_CUSTODIAL",
        "pay_it_forward_sponsored": True,
        "sponsor_member_id": "MEM-H2-H6",
        "seed_cents": 75_000,
        "risk_dial_bps": 100,
        "bank_ref_token": "EXT-REF-PENFED-****6060",
        "due_diligence_attestation": "Attested by House 06 Genealogist after direct family verification.",
    }

    # Default delegation scope is ADMIN_ONLY -> House officer MUST be blocked HTTP 403
    cfg = client.get("/api/v1/onboarding/delegation-config").json()
    assert cfg["delegated_onboarding_scope"] == DELEGATION_SCOPE_ADMIN_ONLY
    assert cfg["genealogical_board_enabled"] is False

    blocked = client.post(
        "/api/v1/onboarding/delegated-submit",
        headers={"X-Actor-Role": "HOUSE_GENEALOGIST", "X-Actor-ID": "MEM-GENEALOGIST-H6", "X-House-ID": "6"},
        json=dossier_payload,
    )
    assert blocked.status_code == 403
    assert "ADMIN_ONLY" in blocked.json()["detail"]

    # Chief Admin enables PER_HOUSE delegation for House 6 + Genealogical Admissions Board (quorum 2) + CROSS_HOUSE_ANTI_TRIBAL
    upd = client.post(
        "/api/v1/onboarding/delegation-config",
        headers=CA_HEADERS,
        json={
            "delegated_onboarding_scope": DELEGATION_SCOPE_PER_HOUSE,
            "house_delegation_flags": {"6": True},
            "genealogical_board_enabled": True,
            "genealogical_board_quorum": 2,
        },
    )
    assert upd.status_code == 200
    assert upd.json()["delegated_onboarding_scope"] == DELEGATION_SCOPE_PER_HOUSE
    assert upd.json()["house_delegation_flags"]["6"] is True
    assert upd.json()["genealogical_board_enabled"] is True

    assert client.post(
        "/api/v1/governance/custody-mode",
        headers=CA_HEADERS,
        json={"custody_assignment_mode": CUSTODY_MODE_CROSS_HOUSE_ANTI_TRIBAL},
    ).status_code == 200

    # PII / Banking Air-Gap rejection: raw SSN or routing number fails closed HTTP 422
    bad_ssn = client.post(
        "/api/v1/onboarding/delegated-submit",
        headers={"X-Actor-Role": "HOUSE_GENEALOGIST", "X-Actor-ID": "MEM-GENEALOGIST-H6", "X-House-ID": "6"},
        json={**dossier_payload, "kinship_verification": "Verified SSN 123-45-6789"},
    )
    assert bad_ssn.status_code == 422

    bad_bank = client.post(
        "/api/v1/onboarding/delegated-submit",
        headers={"X-Actor-Role": "HOUSE_GENEALOGIST", "X-Actor-ID": "MEM-GENEALOGIST-H6", "X-House-ID": "6"},
        json={**dossier_payload, "routing_number": "021000021"},
    )
    assert bad_bank.status_code == 422

    # Stage 1: Authorized House 6 Genealogist submits dossier -> strictly PENDING_RATIFICATION (NO SCMA provisioned!)
    sub = client.post(
        "/api/v1/onboarding/delegated-submit",
        headers={"X-Actor-Role": "HOUSE_GENEALOGIST", "X-Actor-ID": "MEM-GENEALOGIST-H6", "X-House-ID": "6"},
        json=dossier_payload,
    )
    assert sub.status_code == 201, sub.text
    sub_body = sub.json()
    assert sub_body["status"] == DOSSIER_PENDING_RATIFICATION
    assert sub_body["scma_provisioned"] is False
    dossier_id = sub_body["dossier"]["dossier_id"]
    assert len(sub_body["dossier"]["attestation_signature"]) == 64

    with SessionLocalTest() as db:
        assert db.query(OnboardingMemberModel).filter(
            OnboardingMemberModel.full_name == "Nadia Carmichael-McCormick"
        ).first() is None

    # Subordinate officer CANNOT unilaterally ratify (HTTP 403)
    assert client.post(
        f"/api/v1/onboarding/dossiers/{dossier_id}/ratify",
        headers={"X-Actor-Role": "HOUSE_GENEALOGIST", "X-Actor-ID": "MEM-GENEALOGIST-H6"},
        json={},
    ).status_code == 403

    # Stage 2: Optional Genealogical Admissions Board votes (2 approve -> BOARD_RECOMMENDED, still NO SCMA!)
    v1 = client.post(
        f"/api/v1/onboarding/dossiers/{dossier_id}/board-vote",
        headers={"X-Actor-Role": "HOUSE_GENEALOGIST", "X-Actor-ID": "MEM-GENEALOGIST-H6"},
        json={"vote": "APPROVE", "rationale": "Lineage verified"},
    )
    assert v1.status_code == 200
    assert v1.json()["status"] == DOSSIER_PENDING_RATIFICATION
    assert v1.json()["scma_provisioned"] is False

    v2 = client.post(
        f"/api/v1/onboarding/dossiers/{dossier_id}/board-vote",
        headers={"X-Actor-Role": "H2", "X-Actor-ID": "MEM-H2-H6"},
        json={"vote": "APPROVE", "rationale": "House 06 endorsement"},
    )
    assert v2.status_code == 200
    assert v2.json()["status"] == DOSSIER_BOARD_RECOMMENDED
    assert v2.json()["scma_provisioned"] is False

    # Stage 3: Chief Admin ratifies -> atomically provisions SCMA, House lineage, MEMBER_USER, cross-house mentor, & signed IFAS outbox
    rat = client.post(
        f"/api/v1/onboarding/dossiers/{dossier_id}/ratify",
        headers=CA_HEADERS,
        json={"decision_notes": "Welcome to House 06"},
    )
    assert rat.status_code == 200, rat.text
    rat_body = rat.json()
    assert rat_body["status"] == DOSSIER_RATIFIED_PROVISIONED
    assert rat_body["member"]["lineage_code"] == "HOUSE-06"
    assert rat_body["member"]["seed_cents"] == 75_000
    assert rat_body["member"]["high_water_mark_cents"] == 75_000
    assert rat_body["member"]["is_custodial"] is True
    assert rat_body["role_assignment"]["role_token"] == "MEMBER_USER"
    # Anti-tribalism cross-house mentor assigned (House 9 mentor for House 6 charge!)
    assert rat_body["custodial_assignment"]["custodian_member_id"] == "MEM-MENTOR-H9"
    assert rat_body["custodial_assignment"]["assignment_mode"] == CUSTODY_MODE_CROSS_HOUSE_ANTI_TRIBAL

    # Verify HMAC-SHA256 signed MEMBER_ADMISSION_RATIFIED JSON-LD event in both gateway and accounting_outbox_events table
    outbox_evt = rat_body["ifas_outbox_event"]
    assert outbox_evt["payload"]["@context"] == "https://schema.pdeue.org/accounting/v1"
    assert outbox_evt["payload"]["event_type"] == "MEMBER_ADMISSION_RATIFIED"
    assert outbox_evt["payload"]["bank_ref_token"] == "EXT-REF-PENFED-****6060"
    assert outbox_evt["payload"]["pay_it_forward_sponsored"] is True
    assert gateway.verify_event(outbox_evt) is True

    # Zero banking credentials / SSN leakage in outbox payload
    raw_json = json.dumps(outbox_evt).lower()
    for forbidden in ("routing_number", "account_number", "swift_code", "iban", "ssn", "social_security"):
        assert forbidden not in raw_json

    with SessionLocalTest() as db:
        db_evt = db.get(AccountingOutboxEventModel, outbox_evt["event_id"])
        assert db_evt is not None
        assert db_evt.event_type == "MEMBER_ADMISSION_RATIFIED"
        assert db_evt.signature_hmac_sha256 == outbox_evt["signature_hmac_sha256"]

    # Also verify request-proof & reject workflows on a second dossier
    sub2 = client.post(
        "/api/v1/onboarding/delegated-submit",
        headers={"X-Actor-Role": "H2", "X-Actor-ID": "MEM-H2-H6", "X-House-ID": "6"},
        json={**dossier_payload, "applicant_full_name": "Second Applicant"},
    )
    assert sub2.status_code == 201
    dos2 = sub2.json()["dossier"]["dossier_id"]

    req_proof = client.post(
        f"/api/v1/onboarding/dossiers/{dos2}/request-proof",
        headers={"X-Actor-Role": "HOUSE_GENEALOGIST", "X-Actor-ID": "MEM-GENEALOGIST-H6"},
        json={"proof_request": "Provide lineage birth record"},
    )
    assert req_proof.status_code == 200
    assert req_proof.json()["status"] == DOSSIER_PROOF_REQUESTED

    rej = client.post(
        f"/api/v1/onboarding/dossiers/{dos2}/reject",
        headers=CA_HEADERS,
        json={"reason": "Incomplete proof"},
    )
    assert rej.status_code == 200
    assert rej.json()["status"] == DOSSIER_REJECTED


def test_pr81_new_lexicon_concepts_are_two_layer_and_jargon_free():
    for term_id in (
        "house-genealogist",
        "anti-tribalism-custody",
        "delegated-onboarding",
        "genealogical-ratification",
    ):
        assert term_id in LEXICON_BY_ID
        entry = LEXICON_BY_ID[term_id]
        plain = entry["plain_english"].lower()
        tech = entry["technical_spec"]
        assert len(plain) >= 40
        assert len(tech) >= 50
        for banned in BANNED_PLAIN_ENGLISH_JARGON:
            assert banned not in plain, f"Banned token '{banned}' leaked into plain_english for {term_id}"
