"""Milestones C2-C5 — Comprehensive API & Domain Authority Tier Tests.

Covers positive and negative (HTTP 403/401/400) verification for:
- C2: Directive R-06 Active-Hat Context Switching (no privilege blending, revocation, audit)
- C3: Founder Quarantine Immunity (across all subordinate tiers) & Supervisory Audit Lens
- C4: Class T Sub-Tiers (T1, T2, T2-Household, T3), Directive R-12 masking & time-bounded CA Override
- C5: Class F Sub-Tiers (F1, F2-H + custodial locks, F2-A read-only audit, F3 CRO + CA-only resumption)
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import portal_router
from app.api.v1.lineage_router import _lineage_service
from app.core.security import create_access_token
from app.domain.authority_tiers import (
    get_ca_override_manager,
    get_directive_r04_controller,
    get_governance_audit_log,
)
from app.main import app


CLIENT = TestClient(app)
FOUNDER_SCMA = "SCMA-FOUNDER_-C8575D7E"
FOUNDER_UID = "USR-founder_ch-C8575D7E"
ELEANOR_SCMA = "SCMA-ELEANOR_-B2B31C9E"
JULIAN_SCMA = "SCMA-JULIAN_-A1F98B21"


@pytest.fixture(autouse=True)
def _reset_mutable_portal_state():
    """Keep process-local demo ledgers deterministic across every test."""
    _lineage_service.restore_house(1)
    _lineage_service.restore_house(2)
    founder = _lineage_service.CANONICAL_HOUSES[1]["members"][0]
    founder["risk_dial"] = 0.02
    founder["status"] = "ACTIVE"
    founder["open_orders"] = ["KX-MIA-FRZ-32"]
    portal_router._DISTRIBUTION_STATE["DIST-104"].update(status="PENDING", signature=None)
    portal_router._DISTRIBUTION_STATE["DIST-105"].update(status="PENDING", signature=None)
    get_directive_r04_controller().reset_normal()
    yield
    _lineage_service.restore_house(1)
    _lineage_service.restore_house(2)
    get_directive_r04_controller().reset_normal()


# =============================================================================
# MILESTONE C2 — DIRECTIVE R-06 ACTIVE-HAT CONTEXT SWITCHING
# =============================================================================


def test_c2_unconfirmed_hat_switch_fails_closed_and_audits():
    res = CLIENT.post(
        "/api/v1/portal/active-hat/switch",
        json={
            "principal_id": FOUNDER_UID,
            "principal_role": "CHIEF_ADMINISTRATOR",
            "from_hat": "CHIEF_ADMINISTRATOR",
            "to_hat": "PERSONAL_SCMA",
            "confirmed": False,
        },
    )
    assert res.status_code == 400
    assert "EXPLICIT_CONFIRMATION_REQUIRED" in res.json()["detail"]

    audit = CLIENT.get("/api/v1/portal/active-hat/audit").json()
    assert any(e["outcome"] == "DENIED_UNCONFIRMED" for e in audit["denied_events"])


@pytest.mark.parametrize(
    ("principal_id", "principal_role", "target_hat"),
    [
        ("tech-t3-01", "T3", "CHIEF_ADMINISTRATOR"),
        ("tech-t3-01", "T3", "F2-H"),
        ("tech-t2-01", "T2", "T3"),
        ("advisor-f2h-01", "F2-H", "CHIEF_ADMINISTRATOR"),
        ("advisor-f1-01", "F1", "F3"),
        ("member-01", "MEMBER_USER", "T3"),
        ("house-h1-01", "H1", "H2"),
    ],
)
def test_c2_unauthorized_hat_escalation_fails_closed_403(principal_id, principal_role, target_hat):
    res = CLIENT.post(
        "/api/v1/portal/active-hat/switch",
        json={
            "principal_id": principal_id,
            "principal_role": principal_role,
            "from_hat": principal_role,
            "to_hat": target_hat,
            "confirmed": True,
        },
    )
    assert res.status_code == 403
    assert "UNAUTHORIZED_HAT_SWITCH" in res.json()["detail"]


def test_c2_founder_active_hat_switch_isolates_privileges_revokes_prior_and_audits():
    # 1. Start in CHIEF_ADMINISTRATOR hat
    exec_switch = CLIENT.post(
        "/api/v1/portal/active-hat/switch",
        json={
            "principal_id": FOUNDER_UID,
            "principal_role": "CHIEF_ADMINISTRATOR",
            "from_hat": None,
            "to_hat": "CHIEF_ADMINISTRATOR",
            "confirmed": True,
        },
    )
    assert exec_switch.status_code == 200
    exec_body = exec_switch.json()
    exec_token = exec_body["access_token"]
    assert exec_body["active_hat"] == "CHIEF_ADMINISTRATOR"
    assert exec_body["event_id"].startswith("AUD-")

    # 2. CHIEF_ADMINISTRATOR hat MUST NOT silently mutate personal member SCMA risk/distribution
    denied_member_risk = CLIENT.post(
        "/api/v1/portal/member/risk-dial",
        headers={"Authorization": f"Bearer {exec_token}"},
        json={"scma_id": FOUNDER_SCMA, "requested_risk_pct": 1.5},
    )
    assert denied_member_risk.status_code == 403
    assert "ACTIVE_HAT_MISMATCH" in denied_member_risk.json()["detail"]

    denied_member_dist = CLIENT.post(
        "/api/v1/portal/member/request-distribution",
        headers={"Authorization": f"Bearer {exec_token}"},
        json={"scma_id": FOUNDER_SCMA, "amount_cents": 5000, "category_tag": "Personal"},
    )
    assert denied_member_dist.status_code == 403

    # 3. Intentionally switch to PERSONAL_SCMA hat
    personal_switch = CLIENT.post(
        "/api/v1/portal/active-hat/switch",
        json={
            "principal_id": FOUNDER_UID,
            "principal_role": "CHIEF_ADMINISTRATOR",
            "from_hat": "CHIEF_ADMINISTRATOR",
            "to_hat": "PERSONAL_SCMA",
            "confirmed": True,
            "reason": "Personal SCMA review",
        },
    )
    assert personal_switch.status_code == 200
    personal_body = personal_switch.json()
    personal_token = personal_body["access_token"]
    assert personal_body["active_hat"] == "PERSONAL_SCMA"
    assert personal_body["previous_session_revoked"] is True

    # 4. Prior CHIEF_ADMINISTRATOR token is now revoked and cannot be replayed
    stale_exec = CLIENT.post(
        "/api/v1/operator/emergency-stop",
        headers={"Authorization": f"Bearer {exec_token}"},
    )
    assert stale_exec.status_code == 403
    assert "SESSION_REVOKED_OR_STALE" in stale_exec.json()["detail"]

    # 5. Active PERSONAL_SCMA token works for personal member actions, blocked on executive/tech/advisor actions
    ok_personal = CLIENT.post(
        "/api/v1/portal/member/request-distribution",
        headers={"Authorization": f"Bearer {personal_token}"},
        json={"scma_id": FOUNDER_SCMA, "amount_cents": 5000, "category_tag": "Personal"},
    )
    assert ok_personal.status_code == 200
    assert ok_personal.json()["tier"] == "GREEN"

    blocked_exec = CLIENT.post(
        "/api/v1/operator/emergency-stop",
        headers={"Authorization": f"Bearer {personal_token}"},
    )
    assert blocked_exec.status_code == 403

    blocked_tech = CLIENT.post(
        "/api/v1/portal/tech/trigger-daemon?tier=T3",
        headers={"Authorization": f"Bearer {personal_token}"},
    )
    assert blocked_tech.status_code == 403

    # 6. Audit trail contains both context switches
    audit = CLIENT.get("/api/v1/portal/active-hat/audit").json()
    ids = {e["event_id"] for e in audit["events"]}
    assert exec_body["event_id"] in ids
    assert personal_body["event_id"] in ids


# =============================================================================
# MILESTONE C3 — FOUNDER QUARANTINE IMMUNITY & SUPERVISORY AUDIT LENS
# =============================================================================


@pytest.mark.parametrize("actor_role", ["T1", "T2", "T2-Household", "T3", "F1", "F2-H", "F2-A", "F3", "H1", "H2", "MEMBER_USER"])
@pytest.mark.parametrize("action", ["FREEZE", "QUARANTINE", "DEMOTE", "REVOKE"])
def test_c3_no_subordinate_can_freeze_quarantine_demote_or_revoke_founder(actor_role, action):
    for target in (FOUNDER_SCMA, FOUNDER_UID):
        res = CLIENT.post(
            f"/api/v1/governance/accounts/{target}/action",
            headers={"X-Actor-Role": actor_role},
            json={"action": action, "actor_role": actor_role},
        )
        assert res.status_code == 403, f"{actor_role} {action} on {target} must fail closed 403"
        assert "FOUNDER_APEX_IMMUNITY_VIOLATION" in res.json()["detail"]

    audit_events = get_governance_audit_log().list_events(event_type="FOUNDER_IMMUNITY_BLOCK", limit=50)
    assert any(e["target_id"] == FOUNDER_SCMA and e["action"] == action for e in audit_events)


def test_c3_founder_immunity_across_lineage_workspace_and_advisor_endpoints():
    # Lineage subordinate freeze/cancel with explicit subordinate role -> 403
    for endpoint in (
        "/api/v1/lineage/house/1/subordinate/freeze-risk",
        "/api/v1/lineage/house/1/subordinate/cancel-orders",
    ):
        for role in ("T3", "F3", "H2", "F2-H"):
            r = CLIENT.post(
                endpoint,
                headers={"X-Actor-Role": role},
                json={"scma_id": FOUNDER_SCMA},
            )
            assert r.status_code == 403

    # Portal House circuit breaker targeting Founder -> 403
    cb = CLIENT.post(
        "/api/v1/portal/lineage/house/1/circuit-breaker?role=H2",
        headers={"X-House-ID": "1"},
        json={"scma_id": FOUNDER_SCMA, "action": "FREEZE_DIAL"},
    )
    assert cb.status_code == 403
    assert "FOUNDER_APEX_IMMUNITY_VIOLATION" in cb.json()["detail"]

    # Workspace authority revoke targeting Founder -> 403 even with a session
    founder_id_token = create_access_token({"sub": "founder-1", "role": "FOUNDER"})
    chief_token = CLIENT.post(
        "/api/v1/workspace/hat-sessions/select",
        headers={"Authorization": f"Bearer {founder_id_token}"},
        json={"hat": "CHIEF_ADMINISTRATOR", "confirmed": True},
    ).json()["access_token"]
    revoke_founder = CLIENT.post(
        "/api/v1/workspace/authority/revoke",
        headers={"Authorization": f"Bearer {chief_token}"},
        json={"subject": FOUNDER_UID},
    )
    assert revoke_founder.status_code == 403
    assert "FOUNDER_APEX_IMMUNITY_VIOLATION" in revoke_founder.json()["detail"]

    # Advisor proposal or F3 dual-signature override targeting Founder SCMA -> 403
    prop = CLIENT.post(
        "/api/v1/portal/advisor/proposals?role=F2-A",
        json={"target_scma": FOUNDER_SCMA, "proposed_dial": 0.5, "justification": "Attempt clamp"},
    )
    assert prop.status_code == 403
    assert "FOUNDER_APEX_IMMUNITY_VIOLATION" in prop.json()["detail"]

    dsig = CLIENT.post(
        "/api/v1/portal/advisor/dual-signature-override?role=F3",
        json={"target_scope": FOUNDER_SCMA, "action": "CLAMP", "justification": "Attempt override"},
    )
    assert dsig.status_code == 403
    assert "FOUNDER_APEX_IMMUNITY_VIOLATION" in dsig.json()["detail"]


def test_c3_house_1_quarantine_never_freezes_founder_member_state():
    _lineage_service.freeze_house(1)

    founder_state = CLIENT.get(f"/api/v1/portal/member/state?scma_id={FOUNDER_SCMA}").json()
    assert founder_state["is_sovereign_immune"] is True
    assert founder_state["quarantined"] is False
    assert founder_state["is_frozen"] is False
    assert founder_state["risk_dial_pct"] == 2.0

    # Subordinate Eleanor in House 1 IS frozen by House 1 quarantine
    eleanor_state = CLIENT.get(f"/api/v1/portal/member/state?scma_id={ELEANOR_SCMA}").json()
    assert eleanor_state["is_sovereign_immune"] is False
    assert eleanor_state["is_frozen"] is True
    assert eleanor_state["risk_dial_pct"] == 0.0


def test_c3_supervisory_audit_lens_blocks_mutations_and_renders_banner():
    # Server-side read-only enforcement
    assert CLIENT.post(
        "/api/v1/portal/member/risk-dial",
        headers={"X-Supervisory-Mode": "read-only"},
        json={"scma_id": ELEANOR_SCMA, "requested_risk_pct": 1.0},
    ).status_code == 403
    assert CLIENT.post(
        "/api/v1/portal/advisor/co-sign",
        headers={"X-Supervisory-Mode": "read-only"},
        json={"request_id": "DIST-104", "actor_role": "F2-H"},
    ).status_code == 403
    assert CLIENT.post(
        "/api/v1/portal/tech/trigger-daemon?tier=T3",
        headers={"X-Supervisory-Mode": "read-only"},
    ).status_code == 403

    # Banner contract on subordinate portals
    for route in ("/member", "/advisor", "/admin/tech"):
        html = CLIENT.get(route).text
        assert 'id="supervisoryAuditLensBanner"' in html
        assert "SUPERVISORY AUDIT LENS — READ-ONLY INSPECTION" in html
        assert "#D97706" in html


# =============================================================================
# MILESTONE C4 — CLASS T SUB-TIERS (T1, T2, T2-Household, T3) & R-12 MASKING
# =============================================================================


def test_c4_class_t_t1_t2_t2household_t3_separation_and_r12_masking():
    # --- T1: Read-only health/latency; triggers & CA override blocked 403; always masked ---
    t1 = CLIENT.get("/api/v1/portal/tech/telemetry?tier=T1&unredact_token=AUTH-CA-OVERRIDE-TEMP").json()
    assert t1["tier"] == "T1"
    assert t1["redaction_active"] is True
    assert t1["can_trigger_daemons"] is False
    assert t1["can_override_redaction"] is False
    assert t1["active_order_ladder"][0]["scma_id"] == "SCMA-MEM-****"
    assert t1["active_order_ladder"][0]["exposure_cents"] == "$****.**"
    assert CLIENT.post("/api/v1/portal/tech/trigger-daemon?tier=T1").status_code == 403
    assert CLIENT.post("/api/v1/portal/tech/trigger-settlement?tier=T1").status_code == 403
    assert CLIENT.post("/api/v1/portal/tech/ca-override?tier=T1", json={"token": "CA-OVERRIDE-SECRET-DEV"}).status_code == 403

    # --- T2: Daemon triggers active; CA override blocked 403; always masked ---
    t2 = CLIENT.get("/api/v1/portal/tech/telemetry?tier=T2&unredact_token=AUTH-CA-OVERRIDE-TEMP").json()
    assert t2["tier"] == "T2"
    assert t2["redaction_active"] is True
    assert t2["can_trigger_daemons"] is True
    assert t2["can_override_redaction"] is False
    assert t2["active_order_ladder"][0]["exposure_cents"] == "$****.**"
    assert CLIENT.post("/api/v1/portal/tech/trigger-daemon?tier=T2").status_code == 200
    assert CLIENT.post("/api/v1/portal/tech/trigger-settlement?tier=T2").status_code == 200
    assert CLIENT.post("/api/v1/portal/tech/ca-override?tier=T2", json={"token": "CA-OVERRIDE-SECRET-DEV"}).status_code == 403

    # --- T2-Household: Strictly household-scoped; cross-household, global triggers & CA override blocked 403 ---
    t2h = CLIENT.get(
        "/api/v1/portal/tech/telemetry?tier=T2-Household&household_id=HOUSEHOLD-ALPHA",
        headers={"X-Household-ID": "HOUSEHOLD-ALPHA"},
    )
    assert t2h.status_code == 200
    t2h_body = t2h.json()
    assert t2h_body["tier"] == "T2-HOUSEHOLD"
    assert t2h_body["telemetry_scope"] == "CLASS_T_HOUSEHOLD_SCOPED"
    assert t2h_body["assigned_household_id"] == "HOUSEHOLD-ALPHA"
    assert t2h_body["redaction_active"] is True
    assert t2h_body["can_trigger_daemons"] is False
    assert t2h_body["can_override_redaction"] is False
    assert t2h_body["active_order_ladder"][0]["scma_id"] == "SCMA-MEM-****"
    assert t2h_body["active_order_ladder"][0]["exposure_cents"] == "$****.**"

    t2h_cross = CLIENT.get(
        "/api/v1/portal/tech/telemetry?tier=T2-Household&household_id=HOUSEHOLD-BETA",
        headers={"X-Household-ID": "HOUSEHOLD-ALPHA"},
    )
    assert t2h_cross.status_code == 403
    assert CLIENT.post("/api/v1/portal/tech/trigger-daemon?tier=T2-Household").status_code == 403
    assert CLIENT.post("/api/v1/portal/tech/trigger-settlement?tier=T2-Household").status_code == 403
    assert CLIENT.post("/api/v1/portal/tech/ca-override?tier=T2-Household", json={"token": "CA-OVERRIDE-SECRET-DEV"}).status_code == 403


def test_c4_t3_time_bounded_audited_ca_override_and_revocation():
    # Default T3 telemetry is R-12 masked
    masked = CLIENT.get("/api/v1/portal/tech/telemetry?tier=T3").json()
    assert masked["redaction_active"] is True
    assert masked["financial_authority"] is False
    assert masked["house_authority"] is False
    assert masked["household_authority"] is False
    assert masked["active_order_ladder"][0]["scma_id"] == "SCMA-MEM-****"
    assert masked["active_order_ladder"][0]["exposure_cents"] == "$****.**"

    # Issue time-bounded audited override grant
    override = CLIENT.post(
        "/api/v1/portal/tech/ca-override?tier=T3",
        json={"token": "CA-OVERRIDE-SECRET-DEV", "reason": "Latency audit", "ttl_seconds": 120},
    )
    assert override.status_code == 200
    grant = override.json()
    assert grant["redaction_active"] is False
    assert grant["grant_token"].startswith("CA-GRANT-")
    assert grant["ttl_seconds"] == 120
    assert grant["audit_event_id"].startswith("AUD-")

    # Telemetry unmasks while grant is active
    unmasked = CLIENT.get(f"/api/v1/portal/tech/telemetry?tier=T3&unredact_token={grant['grant_token']}").json()
    assert unmasked["redaction_active"] is False
    assert unmasked["active_order_ladder"][0]["scma_id"] == ELEANOR_SCMA
    assert unmasked["active_order_ladder"][0]["exposure_cents"] == 2500

    # Expiration automatically re-engages R-12 masking
    get_ca_override_manager().force_expire_for_test(grant["grant_token"])
    remasked = CLIENT.get(f"/api/v1/portal/tech/telemetry?tier=T3&unredact_token={grant['grant_token']}").json()
    assert remasked["redaction_active"] is True
    assert remasked["active_order_ladder"][0]["scma_id"] == "SCMA-MEM-****"
    assert remasked["active_order_ladder"][0]["exposure_cents"] == "$****.**"

    # Explicit revoke restores R-12 masking immediately
    grant2 = CLIENT.post(
        "/api/v1/portal/tech/ca-override?tier=T3",
        json={"token": "CA-OVERRIDE-SECRET-DEV", "ttl_seconds": 300},
    ).json()
    revoke = CLIENT.post(
        "/api/v1/portal/tech/ca-override/revoke?tier=T3",
        json={"grant_token": grant2["grant_token"]},
    )
    assert revoke.status_code == 200
    assert revoke.json()["redaction_active"] is True
    after_revoke = CLIENT.get(f"/api/v1/portal/tech/telemetry?tier=T3&unredact_token={grant2['grant_token']}").json()
    assert after_revoke["redaction_active"] is True


def test_c4_t3_inherits_zero_financial_house_or_household_authority():
    t3_headers = {"X-Actor-Role": "T3"}
    assert CLIENT.get("/api/v1/portal/advisor/household-tree?role=F2-H", headers=t3_headers).status_code == 403
    assert CLIENT.get("/api/v1/portal/advisor/macro-risk?role=F3", headers=t3_headers).status_code == 403
    assert CLIENT.post(
        "/api/v1/portal/advisor/co-sign",
        headers=t3_headers,
        json={"request_id": "DIST-104", "actor_role": "F2-H"},
    ).status_code == 403
    assert CLIENT.post(
        "/api/v1/portal/member/request-distribution",
        headers=t3_headers,
        json={"scma_id": ELEANOR_SCMA, "amount_cents": 5000, "category_tag": "Personal"},
    ).status_code == 403
    assert CLIENT.post(
        "/api/v1/portal/lineage/house/1/vote?role=H2",
        headers={**t3_headers, "X-House-ID": "1"},
        json={"proposal_id": "CFCP-2026-02", "vote": "AYE"},
    ).status_code == 403
    assert CLIENT.post(
        "/api/v1/portal/lineage/house/1/circuit-breaker?role=H2",
        headers={**t3_headers, "X-House-ID": "1"},
        json={"scma_id": ELEANOR_SCMA, "action": "FREEZE_DIAL"},
    ).status_code == 403
    assert CLIENT.post(
        "/api/v1/lineage/house/1/freeze",
        headers=t3_headers,
    ).status_code == 403
    assert CLIENT.post(
        "/api/v1/lineage/governance/adjudicate",
        headers=t3_headers,
        json={"proposal_id": "PROP-2026-001", "action": "SOVEREIGN_VETO"},
    ).status_code == 403


# =============================================================================
# MILESTONE C5 — CLASS F SUB-TIERS (F1, F2-H, F2-A, F3) & DUAL-CONTROL GATES
# =============================================================================


def test_c5_f1_peer_guide_restricted_to_mentee_only():
    f1 = CLIENT.get("/api/v1/portal/advisor/household-tree?role=F1").json()
    assert len(f1["accounts"]) == 1
    assert f1["accounts"][0]["is_custodial"] is True
    assert "balance_cents" not in f1["accounts"][0]
    assert f1["accounts"][0]["balance_display"] == "$****.**"
    assert "total_family_equity_cents" not in f1
    assert "available_liquidity_cents" not in f1
    assert f1["pending_distributions"] == []

    assert CLIENT.post("/api/v1/portal/advisor/co-sign", json={"request_id": "DIST-104", "actor_role": "F1"}).status_code == 403
    assert CLIENT.get("/api/v1/portal/advisor/proposals?role=F1").status_code == 403
    assert CLIENT.get("/api/v1/portal/advisor/macro-risk?role=F1").status_code == 403
    assert CLIENT.post("/api/v1/portal/advisor/emergency-halt?role=F1", json={"reason": "no"}).status_code == 403
    assert CLIENT.post("/api/v1/portal/advisor/custodial-risk-dial?role=F1", json={"scma_id": JULIAN_SCMA, "requested_risk_pct": 0.75}).status_code == 403


def test_c5_f2h_head_of_household_equity_custodial_lock_and_cosign():
    f2h = CLIENT.get("/api/v1/portal/advisor/household-tree?role=F2-H").json()
    assert f2h["total_family_equity_cents"] == 585000
    julian = next(a for a in f2h["accounts"] if a["scma_id"] == JULIAN_SCMA)
    assert julian["is_custodial"] is True
    assert julian["risk_controls_locked"] is True
    assert julian["risk_increase_requires"] == "F2_CO_SIGN"

    # Custodial minor cannot self-modify risk dial or request autonomous distribution
    assert CLIENT.post("/api/v1/portal/member/risk-dial", json={"scma_id": JULIAN_SCMA, "requested_risk_pct": 0.75}).status_code == 403
    assert CLIENT.post("/api/v1/portal/member/request-distribution", json={"scma_id": JULIAN_SCMA, "amount_cents": 5000, "category_tag": "Tuition"}).status_code == 403

    # F2-H CAN govern custodial minor risk dial within 0.50%-1.00% bounds
    ok_custodial = CLIENT.post(
        "/api/v1/portal/advisor/custodial-risk-dial?role=F2-H",
        headers={"X-Household-ID": "HOUSEHOLD-ALPHA"},
        json={"scma_id": JULIAN_SCMA, "requested_risk_pct": 0.80},
    )
    assert ok_custodial.status_code == 200
    assert ok_custodial.json()["applied_risk_pct"] == 0.80

    # F2-H cannot exceed custodial minor 1.00% bound or cross household boundaries
    assert CLIENT.post(
        "/api/v1/portal/advisor/custodial-risk-dial?role=F2-H",
        headers={"X-Household-ID": "HOUSEHOLD-ALPHA"},
        json={"scma_id": JULIAN_SCMA, "requested_risk_pct": 1.50},
    ).status_code == 400
    assert CLIENT.post(
        "/api/v1/portal/advisor/custodial-risk-dial?role=F2-H",
        headers={"X-Household-ID": "HOUSEHOLD-ALPHA"},
        json={"scma_id": "SCMA-RILEY-BETA", "household_id": "HOUSEHOLD-BETA", "requested_risk_pct": 0.75},
    ).status_code == 403

    # F2-H active dual-control co-sign succeeds; macro-risk/halt blocked 403
    cosign = CLIENT.post("/api/v1/portal/advisor/co-sign", json={"request_id": "DIST-104", "actor_role": "F2-H"})
    assert cosign.status_code == 200
    assert CLIENT.get("/api/v1/portal/advisor/macro-risk?role=F2-H").status_code == 403
    assert CLIENT.post("/api/v1/portal/advisor/emergency-halt?role=F2-H", json={"reason": "no"}).status_code == 403


def test_c5_f2a_lineage_advisor_read_only_audit_blocks_all_mutations():
    f2a_alpha = CLIENT.get(
        "/api/v1/portal/advisor/household-tree?role=F2-A&household_id=HOUSEHOLD-ALPHA",
        headers={"X-Household-ID": "HOUSEHOLD-ALPHA"},
    )
    assert f2a_alpha.status_code == 200
    assert all(d["action"] == "READ_ONLY_AUDIT" for d in f2a_alpha.json()["pending_distributions"])

    f2a_beta = CLIENT.get(
        "/api/v1/portal/advisor/household-tree?role=F2-A&household_id=HOUSEHOLD-BETA",
        headers={"X-Household-ID": "HOUSEHOLD-BETA"},
    )
    assert f2a_beta.status_code == 200

    # All direct mutations blocked 403 for F2-A
    assert CLIENT.post("/api/v1/portal/advisor/co-sign", json={"request_id": "DIST-105", "actor_role": "F2-A"}).status_code == 403
    assert CLIENT.post("/api/v1/portal/advisor/custodial-risk-dial?role=F2-A", json={"scma_id": JULIAN_SCMA, "requested_risk_pct": 0.75}).status_code == 403
    assert CLIENT.post("/api/v1/portal/advisor/emergency-halt?role=F2-A", json={"reason": "no"}).status_code == 403
    assert CLIENT.post("/api/v1/portal/advisor/emergency-resume?role=F2-A", json={"justification": "no"}).status_code == 403
    assert CLIENT.post("/api/v1/portal/advisor/dual-signature-override?role=F2-A", json={"target_scope": "HOUSE-02", "justification": "no"}).status_code == 403


def test_c5_f3_cro_emergency_halt_dual_signature_and_chief_admin_only_resumption():
    # 1. F3 CRO engages Directive R-04 Emergency Halt
    halt = CLIENT.post(
        "/api/v1/portal/advisor/emergency-halt?role=F3",
        json={"reason": "Cross-house tail-risk threshold exceeded"},
    )
    assert halt.status_code == 200
    assert halt.json()["status"] == "HALTED"
    assert halt.json()["halted_by"] == "F3"
    assert halt.json()["resumption_authority"] == "CHIEF_ADMINISTRATOR_ONLY"

    macro = CLIENT.get("/api/v1/portal/advisor/macro-risk?role=F3").json()
    assert macro["directive_r04"]["status"] == "HALTED"

    # 2. Non-CA resumption (including F3 CRO itself and T3 CTO) MUST fail closed with HTTP 403!
    for non_ca in ("F3", "F2-H", "F2-A", "F1", "T3", "T2", "T1", "H2", "MEMBER_USER"):
        denied_resume = CLIENT.post(
            f"/api/v1/portal/advisor/emergency-resume?role={non_ca}",
            headers={"X-Actor-Role": non_ca},
            json={"justification": "Attempting unauthorized resume"},
        )
        assert denied_resume.status_code == 403, f"{non_ca} must NOT be able to resume from Directive R-04 halt"

    # 3. Chief Administrator lifts Directive R-04 halt -> 200 NORMAL
    ca_resume = CLIENT.post(
        "/api/v1/portal/advisor/emergency-resume?role=CHIEF_ADMINISTRATOR",
        json={"justification": "Verified venue depth & tail-risk cleared"},
    )
    assert ca_resume.status_code == 200
    assert ca_resume.json()["status"] == "NORMAL"
    assert ca_resume.json()["resumed_by"] == "CHIEF_ADMINISTRATOR"

    # 4. F3 submits Dual-Signature Override -> PENDING_CHIEF_ADMIN_COUNTERSIGN
    override = CLIENT.post(
        "/api/v1/portal/advisor/dual-signature-override?role=F3",
        json={
            "target_scope": "HOUSE-02",
            "action": "RISK_CAP_OVERRIDE",
            "justification": "Temporary macro risk cap adjustment pending CA review",
        },
    )
    assert override.status_code == 201
    oid = override.json()["override_id"]
    assert override.json()["status"] == "PENDING_CHIEF_ADMIN_COUNTERSIGN"

    # 5. F3 CANNOT self-countersign its own dual-signature override -> HTTP 403
    f3_self_sign = CLIENT.post(
        f"/api/v1/portal/advisor/dual-signature-override/{oid}/countersign?role=F3",
        json={"decision": "APPROVE"},
    )
    assert f3_self_sign.status_code == 403

    # 6. Chief Administrator counter-signs -> 200 RATIFIED_EXECUTED
    ca_sign = CLIENT.post(
        f"/api/v1/portal/advisor/dual-signature-override/{oid}/countersign?role=CHIEF_ADMINISTRATOR",
        json={"decision": "APPROVE"},
    )
    assert ca_sign.status_code == 200
    assert ca_sign.json()["status"] == "RATIFIED_EXECUTED"
    assert ca_sign.json()["countersigned_by"] == "CHIEF_ADMINISTRATOR"
