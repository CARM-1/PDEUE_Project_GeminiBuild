"""Milestone C6 — 12-House Lineage Governance, 3-Stage Dormant Bicameral Veto Engine,
Configurable FUTURE Enclave Bodies, Named Voter Seats & Open-Study Doctrine Tests.
"""
from __future__ import annotations

from pathlib import Path
import uuid

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.api.v1 import lineage_router, portal_router
from app.db.models import (
    GovernanceBodyModel,
    GovernanceConfigModel,
    GovernancePetitionModel,
    GovernanceVoteModel,
    GovernanceVoterSeatModel,
    LineageHouseMemberModel,
    LineageHouseModel,
)
from app.domain.authority_tiers import get_governance_audit_log
from app.domain.enclave_governance import (
    DEFAULT_BODY_ID,
    EnclaveGovernanceService,
    MODE_ADVISORY_PETITION_FILTER,
    MODE_BICAMERAL_VETO_ACTIVE,
    MODE_EXECUTIVE_COMMAND,
)
from app.main import app


CLIENT = TestClient(app)
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"

CHIEF_ADMIN_HEADERS = {
    "X-Actor-Role": "CHIEF_ADMINISTRATOR",
    "X-Actor-ID": "USR-founder_ch-C8575D7E",
}


@pytest.fixture(autouse=True)
def _restore_executive_command_mode():
    """Ensure every test starts and ends in fail-closed Stage 1 EXECUTIVE_COMMAND."""
    lineage_router._enclave_gov.set_governance_mode(
        governance_mode=MODE_EXECUTIVE_COMMAND,
        actor_role="CHIEF_ADMINISTRATOR",
        actor_id="USR-founder_ch-C8575D7E",
        reason="Test fixture reset to Stage 1 default",
    )
    yield
    lineage_router._enclave_gov.set_governance_mode(
        governance_mode=MODE_EXECUTIVE_COMMAND,
        actor_role="CHIEF_ADMINISTRATOR",
        actor_id="USR-founder_ch-C8575D7E",
        reason="Test fixture teardown to Stage 1 default",
    )


# =============================================================================
# 1. RELATIONAL 12-HOUSE PERSISTENCE & IDEMPOTENT ALEMBIC MIGRATION 004
# =============================================================================


def test_alembic_004_migration_is_idempotent_and_creates_all_c6_tables(tmp_path: Path):
    db_file = tmp_path / "c6_migration_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(cfg, "head")
    # Re-run upgrade to verify idempotency
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    try:
        tables = set(inspect(engine).get_table_names())
        expected = {
            "lineage_houses",
            "lineage_house_members",
            "governance_config",
            "governance_bodies",
            "governance_voter_seats",
            "governance_petitions",
            "governance_votes",
        }
        assert expected.issubset(tables), f"Missing C6 tables: {expected - tables}"

        # Seed through isolated EnclaveGovernanceService on this fresh DB
        SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        svc = EnclaveGovernanceService(session_factory=SessionFactory, bind_engine=engine)
        houses = svc.list_houses_from_db()
        assert len(houses) == 12
        assert [h["lineage_code"] for h in houses] == [f"HOUSE-{i:02d}" for i in range(1, 13)]
        assert all(isinstance(h["total_cash_cents"], int) for h in houses)
        assert houses[0]["total_cash_cents"] == 625000
        assert houses[0]["total_cash_formatted"] == "$6,250.00"
        assert svc.get_governance_mode()["governance_mode"] == MODE_EXECUTIVE_COMMAND

        bodies = svc.list_bodies()
        council = next(b for b in bodies if b["body_id"] == DEFAULT_BODY_ID)
        assert council["quorum_numerator"] == 9
        assert council["quorum_denominator"] == 12
        assert council["quorum_pct"] == 75
        assert council["active_seat_count"] == 12

        # Clean downgrade back to 003 removes C6 tables without touching prior tables
        command.downgrade(cfg, "003_add_member_onboarding_tables")
        tables_after_down = set(inspect(engine).get_table_names())
        assert expected.isdisjoint(tables_after_down)
        assert "onboarding_members" in tables_after_down
    finally:
        engine.dispose()


def test_relational_12_houses_endpoint_and_exact_cent_rollups():
    res = CLIENT.get("/api/v1/governance/houses")
    assert res.status_code == 200
    houses = res.json()["houses"]
    assert len(houses) == 12
    assert houses[0]["lineage_code"] == "HOUSE-01"
    assert houses[11]["lineage_code"] == "HOUSE-12"
    for h in houses:
        assert isinstance(h["total_cash_cents"], int)
        assert h["total_cash_formatted"].startswith("$")


# =============================================================================
# 2. DEFAULT STAGE 1 EXECUTIVE_COMMAND FAIL-CLOSED & DORMANT UI
# =============================================================================


def test_default_executive_command_strips_vote_buttons_and_fails_closed_403():
    mode = CLIENT.get("/api/v1/governance/mode").json()
    assert mode["governance_mode"] == MODE_EXECUTIVE_COMMAND
    assert mode["stage"] == 1
    assert mode["voting_enabled"] is False
    assert mode["bicameral_veto_enabled"] is False

    # House desk HTML must strip voting/veto buttons and show calm dormant status badge
    html_res = CLIENT.get("/lineage/house/1?role=H2", headers={"X-House-ID": "1"})
    assert html_res.status_code == 200
    assert "Executive Command Mode Active — Voting Dormant" in html_res.text
    assert 'id="vote-aye"' not in html_res.text
    assert 'id="vote-nay"' not in html_res.text
    assert 'id="vote-veto"' not in html_res.text

    # Portal House vote endpoint fails closed HTTP 403
    v1 = CLIENT.post(
        "/api/v1/portal/lineage/house/1/vote?role=H2",
        headers={"X-House-ID": "1"},
        json={"proposal_id": "CFCP-2026-02", "vote": "AYE"},
    )
    assert v1.status_code == 403
    assert "EXECUTIVE_COMMAND_MODE_ACTIVE" in v1.json()["detail"]

    # Governance petition creation & vote endpoints fail closed HTTP 403
    p1 = CLIENT.post(
        "/api/v1/governance/petitions",
        headers={"X-Actor-Role": "H2"},
        json={"title": "Annual House Scholarship", "target_house_id": 2, "amount_cents": 25000},
    )
    assert p1.status_code == 403
    assert "EXECUTIVE_COMMAND_MODE_ACTIVE" in p1.json()["detail"]

    v2 = CLIENT.post(
        "/api/v1/governance/petitions/CFCP-2026-02/vote",
        headers={"X-Actor-Role": "H2", "X-House-ID": "2"},
        json={"house_id": 2, "vote": "AYE"},
    )
    assert v2.status_code == 403
    assert "EXECUTIVE_COMMAND_MODE_ACTIVE" in v2.json()["detail"]


# =============================================================================
# 3. FOUNDER-ONLY MODE SWITCHING & 1-CLICK SHTF SNAP-BACK
# =============================================================================


@pytest.mark.parametrize("subordinate_role", ["H1", "H2", "T1", "T2", "T3", "F1", "F2-H", "F2-A", "F3", "MEMBER_USER", ""])
def test_subordinates_cannot_switch_governance_mode_or_trigger_shtf(subordinate_role: str):
    headers = {"X-Actor-Role": subordinate_role} if subordinate_role else {}
    res_mode = CLIENT.post(
        "/api/v1/governance/mode",
        headers=headers,
        json={"governance_mode": MODE_ADVISORY_PETITION_FILTER, "reason": "Unauthorized attempt"},
    )
    assert res_mode.status_code == 403

    res_shtf = CLIENT.post(
        "/api/v1/governance/shtf-snapback",
        headers=headers,
        json={"reason": "Unauthorized SHTF"},
    )
    assert res_shtf.status_code == 403


def test_chief_admin_mode_transitions_and_1_click_shtf_snapback_audited():
    # Stage 1 -> Stage 2
    r2 = CLIENT.post(
        "/api/v1/governance/mode",
        headers=CHIEF_ADMIN_HEADERS,
        json={"governance_mode": MODE_ADVISORY_PETITION_FILTER, "reason": "Lineage readiness milestone"},
    )
    assert r2.status_code == 200
    assert r2.json()["governance_mode"] == MODE_ADVISORY_PETITION_FILTER
    assert r2.json()["previous_mode"] == MODE_EXECUTIVE_COMMAND
    assert r2.json()["audit_event_id"].startswith("AUD-")

    # Stage 2 -> Stage 3
    r3 = CLIENT.post(
        "/api/v1/governance/mode",
        headers=CHIEF_ADMIN_HEADERS,
        json={"governance_mode": MODE_BICAMERAL_VETO_ACTIVE, "reason": "Enclave constitutional maturity"},
    )
    assert r3.status_code == 200
    assert r3.json()["governance_mode"] == MODE_BICAMERAL_VETO_ACTIVE
    assert r3.json()["bicameral_veto_enabled"] is True

    # 1-Click SHTF Snap-Back -> Stage 1 EXECUTIVE_COMMAND
    snap = CLIENT.post(
        "/api/v1/governance/shtf-snapback",
        headers=CHIEF_ADMIN_HEADERS,
        json={"reason": "Simulated systemic venue crisis"},
    )
    assert snap.status_code == 200
    assert snap.json()["governance_mode"] == MODE_EXECUTIVE_COMMAND
    assert snap.json()["previous_mode"] == MODE_BICAMERAL_VETO_ACTIVE
    assert snap.json()["shtf_snapback"] is True

    # Verify audit log contains transition and SHTF snap-back events
    events = get_governance_audit_log().list_events(event_type="GOVERNANCE_SHTF_SNAPBACK", limit=5)
    assert events and events[0]["target_id"] == MODE_EXECUTIVE_COMMAND


# =============================================================================
# 4. CONFIGURABLE ENCLAVE BODIES & NAMED-PERSON VOTER SEATS (ZERO CODE CHANGES)
# =============================================================================


def test_configurable_enclave_bodies_and_named_voter_seats_lifecycle():
    suffix = uuid.uuid4().hex[:6].upper()
    body_name = f"Council of Elders {suffix}"
    renamed_name = f"Enclave Stewardship Assembly {suffix}"

    # Subordinate cannot create body
    denied_body = CLIENT.post(
        "/api/v1/governance/bodies",
        headers={"X-Actor-Role": "H2"},
        json={"name": body_name},
    )
    assert denied_body.status_code == 403

    # Chief Admin creates custom communal body with custom 2-of-3 quorum & 2-vote veto threshold
    created = CLIENT.post(
        "/api/v1/governance/bodies",
        headers=CHIEF_ADMIN_HEADERS,
        json={
            "name": body_name,
            "description": "Long-term enclave stewardship council",
            "quorum_numerator": 2,
            "quorum_denominator": 3,
            "veto_threshold_count": 2,
            "can_exercise_stage3_veto": True,
        },
    )
    assert created.status_code == 201
    body_id = created.json()["body_id"]
    assert created.json()["quorum_numerator"] == 2
    assert created.json()["veto_threshold_count"] == 2

    # Chief Admin renames body without code changes
    renamed = CLIENT.patch(
        f"/api/v1/governance/bodies/{body_id}",
        headers=CHIEF_ADMIN_HEADERS,
        json={"name": renamed_name},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == renamed_name

    # Grant named-individual seats (one with veto, one without veto)
    seat_1 = CLIENT.post(
        f"/api/v1/governance/bodies/{body_id}/seats",
        headers=CHIEF_ADMIN_HEADERS,
        json={
            "seat_type": "NAMED_INDIVIDUAL",
            "user_id": f"USR-ELDER-A-{suffix}",
            "display_name": "Elder Margaret Vance",
            "can_vote": True,
            "can_veto": True,
        },
    )
    assert seat_1.status_code == 201
    seat_1_id = seat_1.json()["seat_id"]

    seat_2 = CLIENT.post(
        f"/api/v1/governance/bodies/{body_id}/seats",
        headers=CHIEF_ADMIN_HEADERS,
        json={
            "seat_type": "NAMED_INDIVIDUAL",
            "user_id": f"USR-ELDER-B-{suffix}",
            "display_name": "Elder Arthur Vance",
            "can_vote": True,
            "can_veto": True,
        },
    )
    assert seat_2.status_code == 201
    seat_2_id = seat_2.json()["seat_id"]

    seat_3 = CLIENT.post(
        f"/api/v1/governance/bodies/{body_id}/seats",
        headers=CHIEF_ADMIN_HEADERS,
        json={
            "seat_type": "NAMED_INDIVIDUAL",
            "user_id": f"USR-ELDER-C-{suffix}",
            "display_name": "Observer Clara Vance",
            "can_vote": True,
            "can_veto": False,
        },
    )
    assert seat_3.status_code == 201
    seat_3_id = seat_3.json()["seat_id"]

    # Subordinate cannot revoke seat
    assert CLIENT.post(
        f"/api/v1/governance/seats/{seat_3_id}/revoke",
        headers={"X-Actor-Role": "H2"},
        json={"reason": "Unauthorized"},
    ).status_code == 403

    # Chief Admin revokes seat_3 and verifies audit log + active=False
    revoked = CLIENT.post(
        f"/api/v1/governance/seats/{seat_3_id}/revoke",
        headers=CHIEF_ADMIN_HEADERS,
        json={"reason": "Term concluded"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["active"] is False

    # Activate Stage 3 and verify revoked seat cannot vote
    assert CLIENT.post(
        "/api/v1/governance/mode",
        headers=CHIEF_ADMIN_HEADERS,
        json={"governance_mode": MODE_BICAMERAL_VETO_ACTIVE, "reason": "Stage 3 test"},
    ).status_code == 200

    prop = CLIENT.post(
        "/api/v1/governance/petitions",
        headers=CHIEF_ADMIN_HEADERS,
        json={
            "title": f"Enclave Library Expansion Grant {suffix}",
            "description": "Eligible CFCP educational facility allocation.",
            "body_id": body_id,
            "target_house_id": 3,
            "amount_cents": 75000,
        },
    )
    assert prop.status_code == 201
    pid = prop.json()["proposal_id"]

    # Revoked named voter fails closed HTTP 403
    revoked_vote = CLIENT.post(
        f"/api/v1/governance/petitions/{pid}/vote",
        headers={"X-Actor-Role": "H2"},
        json={"user_id": f"USR-ELDER-C-{suffix}", "vote": "AYE"},
    )
    assert revoked_vote.status_code == 403
    assert "VOTER_SEAT_NOT_ACTIVE_OR_UNAUTHORIZED" in revoked_vote.json()["detail"]

    # Active named voters enact binding Stage 3 Bicameral Veto (2/2 threshold reached)
    v_one = CLIENT.post(
        f"/api/v1/governance/petitions/{pid}/vote",
        headers={"X-Actor-Role": "H2"},
        json={"seat_id": seat_1_id, "vote": "VETO", "rationale": "Defer capital spend to Q4"},
    )
    assert v_one.status_code == 200
    assert v_one.json()["veto_count"] == 1
    assert v_one.json()["status"] == "HOUSE_VOTE_OPEN"

    v_two = CLIENT.post(
        f"/api/v1/governance/petitions/{pid}/vote",
        headers={"X-Actor-Role": "H2"},
        json={"seat_id": seat_2_id, "vote": "VETO", "rationale": "Concur with Q4 deferral"},
    )
    assert v_two.status_code == 200
    assert v_two.json()["veto_count"] == 2
    assert v_two.json()["status"] == "VETOED_BY_BICAMERAL_CHAMBER"
    assert v_two.json()["effect"] == "BINDING_BICAMERAL_VETO"

    # Binding Stage 3 Bicameral Veto blocks APPROVE_AND_EXECUTE fail-closed (HTTP 403)
    blocked_exec = CLIENT.post(
        f"/api/v1/governance/petitions/{pid}/adjudicate",
        headers=CHIEF_ADMIN_HEADERS,
        json={"action": "APPROVE_AND_EXECUTE"},
    )
    assert blocked_exec.status_code == 403
    assert "PROPOSAL_VETOED_BY_BICAMERAL_CHAMBER" in blocked_exec.json()["detail"]


# =============================================================================
# 5. STAGE 2 ADVISORY RATIFICATION & ABSOLUTE FOUNDER VETO
# =============================================================================


def test_stage2_advisory_ratification_blocks_chamber_veto_and_honors_founder_veto():
    assert CLIENT.post(
        "/api/v1/governance/mode",
        headers=CHIEF_ADMIN_HEADERS,
        json={"governance_mode": MODE_ADVISORY_PETITION_FILTER, "reason": "Stage 2 test"},
    ).status_code == 200

    prop = CLIENT.post(
        "/api/v1/governance/petitions",
        headers={"X-Actor-Role": "H2"},
        json={
            "title": "Summer Apprenticeship Stipend",
            "description": "Eligible CFCP learning stipend for House 04 apprentices.",
            "target_house_id": 4,
            "amount_cents": 40000,
        },
    )
    assert prop.status_code == 201
    pid = prop.json()["proposal_id"]

    # Stage 2 blocks binding chamber VETO (HTTP 403)
    veto_denied = CLIENT.post(
        f"/api/v1/governance/petitions/{pid}/vote",
        headers={"X-Actor-Role": "H2", "X-House-ID": "1"},
        json={"house_id": 1, "vote": "VETO"},
    )
    assert veto_denied.status_code == 403
    assert "STAGE_3_REQUIRED_FOR_BICAMERAL_VETO" in veto_denied.json()["detail"]

    # 9 of 12 Houses vote AYE -> RATIFIED_PENDING_SETTLOR (no unilateral execution)
    last_resp = None
    for hid in range(1, 10):
        last_resp = CLIENT.post(
            f"/api/v1/governance/petitions/{pid}/vote",
            headers={"X-Actor-Role": "H2", "X-House-ID": str(hid)},
            json={"house_id": hid, "vote": "AYE"},
        )
        assert last_resp.status_code == 200
    assert last_resp is not None
    assert last_resp.json()["aye_count"] == 9
    assert last_resp.json()["status"] == "RATIFIED_PENDING_SETTLOR"
    assert last_resp.json()["effect"] == "ADVISORY_PETITION_ONLY"

    # Subordinate cannot adjudicate
    assert CLIENT.post(
        f"/api/v1/governance/petitions/{pid}/adjudicate",
        headers={"X-Actor-Role": "H2"},
        json={"action": "APPROVE_AND_EXECUTE"},
    ).status_code == 403

    # Founder exercises Absolute Founder Veto -> VETOED_BY_FOUNDER
    founder_veto = CLIENT.post(
        f"/api/v1/governance/petitions/{pid}/adjudicate",
        headers=CHIEF_ADMIN_HEADERS,
        json={"action": "FOUNDER_VETO", "reason": "Preserve CFCP liquidity buffer"},
    )
    assert founder_veto.status_code == 200
    assert founder_veto.json()["status"] == "VETOED_BY_FOUNDER"


# =============================================================================
# 6. IMMUTABLE CORE GUARDRAIL (PERMANENT HTTP 403 IN ALL 3 MODES)
# =============================================================================


@pytest.mark.parametrize("mode", [MODE_EXECUTIVE_COMMAND, MODE_ADVISORY_PETITION_FILTER, MODE_BICAMERAL_VETO_ACTIVE])
@pytest.mark.parametrize(
    "forbidden_title",
    [
        "Amend 87/10/3 waterfall split to 90/5/5",
        "Suspend ADR-012 High-Water Mark recovery protection",
        "Modify Rule A14 loss isolation to socialize trading losses",
        "Raise Quarter-Kelly bounds above 5% ceiling",
        "Reduce 3% FAEP founder endowment allocation",
        "Bypass ADR-011 banking air-gap to store routing number",
        "Disable Directive R-04 Emergency Kill Switch",
    ],
)
def test_immutable_core_invariants_permanently_blocked_403_in_all_modes(mode: str, forbidden_title: str):
    assert CLIENT.post(
        "/api/v1/governance/mode",
        headers=CHIEF_ADMIN_HEADERS,
        json={"governance_mode": mode, "reason": f"Test immutable guardrail in {mode}"},
    ).status_code == 200

    res = CLIENT.post(
        "/api/v1/governance/petitions",
        headers=CHIEF_ADMIN_HEADERS,
        json={
            "title": forbidden_title,
            "description": "Attempted constitutional amendment",
            "target_house_id": 1,
            "amount_cents": 0,
        },
    )
    assert res.status_code == 403
    assert "IMMUTABLE_CORE_INVARIANT" in res.json()["detail"]


def test_adr008_rejects_float_amount_cents_on_petition():
    assert CLIENT.post(
        "/api/v1/governance/mode",
        headers=CHIEF_ADMIN_HEADERS,
        json={"governance_mode": MODE_ADVISORY_PETITION_FILTER, "reason": "ADR-008 check"},
    ).status_code == 200

    res = CLIENT.post(
        "/api/v1/governance/petitions",
        headers={"X-Actor-Role": "H2"},
        json={
            "title": "Valid Study Stipend",
            "description": "Eligible educational stipend",
            "target_house_id": 2,
            "amount_cents": 125.50,
        },
    )
    assert res.status_code == 422
    assert "ADR-008" in res.json()["detail"]


# =============================================================================
# 7. CROSS-HOUSE 403, H1 R-12 MASKING, CLASS T HARD-BLOCK & H2 FOUNDER IMMUNITY
# =============================================================================


def test_cross_house_isolation_h1_r12_masking_class_t_block_and_founder_immunity():
    # Cross-House HTTP 403 (HOUSE-02 attempting to read/mutate HOUSE-01)
    assert CLIENT.get("/lineage/house/1?role=H2", headers={"X-House-ID": "2"}).status_code == 403
    assert CLIENT.get("/lineage/house/1?role=H1", headers={"X-House-ID": "HOUSE-02"}).status_code == 403
    assert CLIENT.get("/api/v1/lineage/house/1", headers={"X-House-ID": "2"}).status_code == 403
    assert CLIENT.post(
        "/api/v1/lineage/house/1/subordinate/freeze-risk",
        headers={"X-House-ID": "2", "X-Actor-Role": "H2"},
        json={"scma_id": "SCMA-ELEANOR_-B2B31C9E"},
    ).status_code == 403
    assert CLIENT.post(
        "/api/v1/portal/lineage/house/1/circuit-breaker?role=H2",
        headers={"X-House-ID": "2"},
        json={"scma_id": "SCMA-ELEANOR_-B2B31C9E", "action": "FREEZE_DIAL"},
    ).status_code == 403

    # H1 Directive R-12 masking & circuit-breaker / voting HTTP 403
    h1_api = CLIENT.get("/api/v1/lineage/house/1?role=H1", headers={"X-House-ID": "1"})
    assert h1_api.status_code == 200
    assert h1_api.json()["r12_masked"] is True
    assert all(m["cash_cents"] == "$****.**" for m in h1_api.json()["members"])
    assert CLIENT.post(
        "/api/v1/lineage/house/1/subordinate/freeze-risk",
        headers={"X-House-ID": "1", "X-Actor-Role": "H1"},
        json={"scma_id": "SCMA-ELEANOR_-B2B31C9E"},
    ).status_code == 403

    # Class T (T1-T3) hard-blocked HTTP 403 from all House portals & mutations
    for tier in ("T1", "T2", "T3"):
        assert CLIENT.get("/lineage/house/1?role=H2", headers={"X-Actor-Role": tier}).status_code == 403
        assert CLIENT.get("/api/v1/portal/lineage/house/1/state", headers={"X-Actor-Role": tier}).status_code == 403
        assert CLIENT.post(
            "/api/v1/portal/lineage/house/1/vote?role=H2",
            headers={"X-Actor-Role": tier, "X-House-ID": "1"},
            json={"proposal_id": "CFCP-2026-02", "vote": "AYE"},
        ).status_code == 403

    # H2 Founder Quarantine Immunity (C3): Founder SCMA cannot be frozen or cancelled by H2
    founder_freeze = CLIENT.post(
        "/api/v1/portal/lineage/house/1/circuit-breaker?role=H2",
        headers={"X-House-ID": "1", "X-Actor-Role": "H2"},
        json={"scma_id": "SCMA-FOUNDER_-C8575D7E", "action": "FREEZE_DIAL"},
    )
    assert founder_freeze.status_code == 403
    assert "IMMUNITY" in founder_freeze.json()["detail"].upper()


# =============================================================================
# 8. OPEN-STUDY GOVERNANCE LIFECYCLE DOCUMENTATION CONTRACT
# =============================================================================


def test_open_study_governance_lifecycle_documented_across_manuals_and_companion():
    for rel_path in (
        "docs/manuals/CHIEF_ADMIN_RUNBOOK.md",
        "docs/manuals/USER_QUICKSTART.md",
        "backend/app/static/companion.html",
    ):
        text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        assert "Three-Stage Governance Lifecycle" in text, f"Missing lifecycle title in {rel_path}"
        assert "EXECUTIVE_COMMAND" in text, f"Missing EXECUTIVE_COMMAND in {rel_path}"
        assert "ADVISORY_PETITION_FILTER" in text, f"Missing ADVISORY_PETITION_FILTER in {rel_path}"
        assert "BICAMERAL_VETO_ACTIVE" in text, f"Missing BICAMERAL_VETO_ACTIVE in {rel_path}"
        assert "SHTF" in text, f"Missing SHTF protocol in {rel_path}"
        assert "IMMUTABLE_CORE_INVARIANT" in text, f"Missing IMMUTABLE_CORE_INVARIANT in {rel_path}"
