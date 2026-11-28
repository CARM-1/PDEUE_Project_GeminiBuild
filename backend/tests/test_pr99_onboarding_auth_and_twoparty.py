"""PR #99 Verification Suite:
1. Alembic 009 idempotent upgrade & downgrade for onboarding email & two-party co-sign columns.
2. End-to-end invite activation -> AuthUserModel private allowlist provisioning (`CLASS_M`, non-apex),
   `ONBOARDING_AUTH_ALLOWLIST_PROVISIONED` GovernanceAuditLog entry, immediate 6-digit email code
   sign-in via `/api/v1/auth/request-code`, and strict tenant-jailed `/member`, `/home`, `/companion`.
3. `CHIEF_ADMIN_SOLO` Ring 1 Alpha default + admin-toggleable `TWO_PARTY_COSIGN` blocking solo
   ratification (HTTP 409 `TWO_PARTY_COSIGN_REQUIRED`) until authorized `F2-H` co-signs, then
   provisioning SCMA + AuthUserModel + signed HMAC-SHA256 `MEMBER_ADMISSION_RATIFIED` IFAS outbox
   event with zero ADR-011 PII leakage.
4. Strict cross-house HTTP 403 isolation for `H2` / `HOUSE_GENEALOGIST` intake and `F2-H` co-sign,
   plus server-side DOM stripping on `/lineage/house/{id}` (stripped for `H1`) and `/advisor`
   (stripped for `F1`, `F2-A`, `F3`).
5. Local-First AI Tutors answer invite activation & two-party admission questions 100% locally
   (`answered_locally=True`, 0 outbound LLM calls).
6. Zero external CDNs, byte-for-byte parity across all 12 dual-served HTML templates, playbook
   registry validation, 12-portal discovery, and PORTAL_COMPONENT_INVENTORY.md parity PASS.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hmac
import hashlib
import json
from pathlib import Path
import re
import sys
from unittest.mock import MagicMock

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.v1 import onboarding_router as onboarding_router_mod  # noqa: E402
from app.db.models import (  # noqa: E402
    AccountingOutboxEventModel,
    AuthUserModel,
    Base,
    DelegatedOnboardingDossierModel,
    OnboardingMemberModel,
)
from app.domain.accounting_gateway import AccountingGateway  # noqa: E402
from app.domain.authority_tiers import get_governance_audit_log  # noqa: E402
from app.domain.capital_ledger import CapitalLedger  # noqa: E402
from app.domain.chancellor_coach import ChiefAdminChancellorCoach  # noqa: E402
from app.domain.dual_lane_tutor import DualLaneTutor  # noqa: E402
from app.domain.lineage_hierarchy import LineageHierarchyService  # noqa: E402
from app.domain.lineage_tutor import ClassHLineageTutor  # noqa: E402
from app.domain.member_onboarding import (  # noqa: E402
    InviteTokenError,
    MemberOnboardingService,
)
from app.domain.member_tutor import MemberLiteracyTutor  # noqa: E402
from app.domain.notification_gateway import NotificationGateway  # noqa: E402
from app.domain.role_copilots import ClassFFinancialCopilot  # noqa: E402
from app.domain.role_custody_service import (  # noqa: E402
    ADMISSION_MODE_CHIEF_ADMIN_SOLO,
    ADMISSION_MODE_TWO_PARTY_COSIGN,
    DELEGATION_SCOPE_ADMIN_ONLY,
    DELEGATION_SCOPE_PER_HOUSE,
    DOSSIER_RATIFIED_PROVISIONED,
    RoleCustodyDelegationService,
)
from app.domain.session_auth_service import (  # noqa: E402
    SESSION_COOKIE_NAME,
    SessionAuthService,
    reset_session_auth_service,
)
from app.domain.training_media_registry import (  # noqa: E402
    load_training_media_registry,
    validate_training_media_registry,
)
from app.main import app  # noqa: E402
from app.portal_discovery import (  # noqa: E402
    PORTALS,
    audit_ui_lexicon_curriculum_parity,
    generate_inventory,
)

API_V1_DIR = BACKEND_DIR / "app" / "api" / "v1"
STATIC_DIR = BACKEND_DIR / "app" / "static"

TWELVE_PORTAL_TEMPLATES = (
    "login.html",
    "activate.html",
    "home.html",
    "dashboard.html",
    "member.html",
    "tech.html",
    "advisor.html",
    "lineage_house.html",
    "community.html",
    "heritage.html",
    "heritage_tree.html",
    "companion.html",
)

CA_HEADERS = {
    "X-Actor-Role": "CHIEF_ADMIN",
    "X-Actor-ID": "USR-founder_ch-C8575D7E",
}


@pytest.fixture()
def isolated_pr99(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolated SQLite DB shared across MemberOnboardingService, RoleCustodyDelegationService, and SessionAuthService."""
    db_file = tmp_path / "pr99_isolated.db"
    eng = create_engine(
        f"sqlite:///{db_file.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=eng)
    SessionLocalTest = sessionmaker(autocommit=False, autoflush=False, bind=eng)

    lineage_svc = LineageHierarchyService()
    ledger = CapitalLedger()
    onb_svc = MemberOnboardingService(
        session_factory=SessionLocalTest,
        db_engine=eng,
        lineage_service=lineage_svc,
        capital_ledger=ledger,
    )
    gateway = AccountingGateway(secret_key="pr99-test-ifas-hmac-key")
    custody_svc = RoleCustodyDelegationService(
        session_factory=SessionLocalTest,
        bind_engine=eng,
        lineage_service=lineage_svc,
        onboarding_service=onb_svc,
        accounting_gateway=gateway,
        register_hat_provider=False,
    )
    from app.domain.notification_gateway import MockNotificationClient

    mock_email = MockNotificationClient(channel="email")
    notif_gw = NotificationGateway(
        in_app_client=MockNotificationClient(channel="in_app"),
        email_client=mock_email,
        sms_client=MockNotificationClient(channel="sms"),
    )
    auth_svc = SessionAuthService(
        session_factory=SessionLocalTest,
        bind_engine=eng,
        notification_gateway=notif_gw,
        seed_defaults=True,
    )

    from app.api.v1 import lineage_router as lineage_router_mod
    from app.domain import member_onboarding as mo_mod
    from app.domain import role_custody_service as rcs_mod

    monkeypatch.setattr(rcs_mod, "_role_custody_service", custody_svc)
    monkeypatch.setattr(mo_mod, "_onboarding_service", onb_svc)
    monkeypatch.setattr(lineage_router_mod, "get_role_custody_service", lambda: custody_svc)
    monkeypatch.setattr(onboarding_router_mod, "get_onboarding_service", lambda: onb_svc)
    monkeypatch.setattr(onboarding_router_mod, "get_role_custody_service", lambda: custody_svc)
    monkeypatch.setattr(onboarding_router_mod, "get_session_auth_service", lambda: auth_svc)
    reset_session_auth_service(auth_svc)

    try:
        yield {
            "engine": eng,
            "session_factory": SessionLocalTest,
            "onboarding": onb_svc,
            "custody": custody_svc,
            "auth": auth_svc,
            "gateway": gateway,
            "mock_email": mock_email,
            "lineage": lineage_svc,
        }
    finally:
        reset_session_auth_service(None)
        eng.dispose()


def test_alembic_009_idempotent_upgrade_and_downgrade(tmp_path: Path) -> None:
    db_file = tmp_path / "alembic_009.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")  # idempotent re-run

    eng = create_engine(db_url)
    try:
        insp = inspect(eng)
        assert "email" in {c["name"] for c in insp.get_columns("onboarding_members")}
        assert "admission_authority_mode" in {c["name"] for c in insp.get_columns("enclave_policy_controls")}
        dos_cols = {c["name"] for c in insp.get_columns("delegated_onboarding_dossiers")}
        for col in (
            "applicant_email",
            "f2h_cosigned_by",
            "f2h_cosigned_role",
            "f2h_cosigned_house_id",
            "f2h_cosigned_at_utc",
            "f2h_cosign_notes",
            "f2h_cosign_signature",
        ):
            assert col in dos_cols, f"Missing migration 009 column {col}"

        command.downgrade(cfg, "008_add_session_auth_tables")
        insp_down = inspect(eng)
        assert "admission_authority_mode" not in {
            c["name"] for c in insp_down.get_columns("enclave_policy_controls")
        }
        assert "f2h_cosigned_by" not in {
            c["name"] for c in insp_down.get_columns("delegated_onboarding_dossiers")
        }

        command.upgrade(cfg, "head")
        assert "admission_authority_mode" in {
            c["name"] for c in inspect(eng).get_columns("enclave_policy_controls")
        }
    finally:
        eng.dispose()


def test_invite_activation_provisions_allowlist_and_enables_6digit_code_signin_and_tenant_jail(
    isolated_pr99,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    SessionLocalTest = isolated_pr99["session_factory"]
    onb_svc: MemberOnboardingService = isolated_pr99["onboarding"]
    mock_email = isolated_pr99["mock_email"]

    # Stage 1: Provision a member with an explicit family email
    client = TestClient(app)
    prov_resp = client.post(
        "/api/v1/onboarding/provision",
        json={
            "full_name": "Clara McCormick",
            "member_id": "MEM-CLARA-H04",
            "email": "Clara.McCormick@carmichael-family.local",
            "lineage_house": "HOUSE-04",
            "role_tier": "MEMBER_USER",
            "seed_cents": 125_000,
            "risk_dial_pct": 1.25,
            "bank_ref_token": "EXT-REF-PENFED-****4821",
        },
    )
    assert prov_resp.status_code == 201, prov_resp.text
    prov = prov_resp.json()
    raw_token = prov["invite"]["token"]
    scma_id = prov["member"]["scma_id"]
    assert prov["invite"]["activate_portal_url"] == f"/activate?token={raw_token}"

    # Enforce strict PR #98 session auth: /activate and /api/v1/onboarding/invite-preview + /activate remain accessible!
    monkeypatch.setenv("PDEUE_ENFORCE_SESSION_AUTH", "true")
    fresh_client = TestClient(app)

    assert fresh_client.get("/activate").status_code == 200
    preview = fresh_client.get(f"/api/v1/onboarding/invite-preview?token={raw_token}")
    assert preview.status_code == 200, preview.text
    prev_body = preview.json()
    assert prev_body["valid"] is True
    assert prev_body["full_name"] == "Clara McCormick"
    assert prev_body["lineage_code"] == "HOUSE-04"
    assert prev_body["email"] == "clara.mccormick@carmichael-family.local"
    assert "bank_ref_token" not in prev_body

    # Stage 2: Activate invite -> creates AuthUserModel on private allowlist + sets HttpOnly cookie
    act_resp = fresh_client.post(
        "/api/v1/onboarding/activate",
        json={"token": raw_token, "email": "clara.mccormick@carmichael-family.local"},
    )
    assert act_resp.status_code == 200, act_resp.text
    act = act_resp.json()
    assert act["status"] == "ACTIVATED_PENDING_CERTIFICATION"
    assert act["session_issued"] is True
    assert SESSION_COOKIE_NAME in fresh_client.cookies
    assert act["auth_allowlist_user"]["email"] == "clara.mccormick@carmichael-family.local"
    assert act["auth_allowlist_user"]["authorized_hats"] == ["CLASS_M"]
    assert act["auth_allowlist_user"]["is_apex_tier3"] is False

    # Verify AuthUserModel row in DB directly
    with SessionLocalTest() as db:
        auth_row = db.get(AuthUserModel, "MEM-CLARA-H04")
        assert auth_row is not None
        assert auth_row.email == "clara.mccormick@carmichael-family.local"
        assert auth_row.display_name == "Clara McCormick"
        assert auth_row.scma_id == scma_id
        assert auth_row.house_id == "HOUSE-04"
        assert json.loads(auth_row.authorized_hats) == ["CLASS_M"]
        assert auth_row.is_apex_tier3 == 0
        assert auth_row.active == 1

    # Verify GovernanceAuditLog recorded ONBOARDING_AUTH_ALLOWLIST_PROVISIONED
    audit_events = get_governance_audit_log().list_events(
        event_type="ONBOARDING_AUTH_ALLOWLIST_PROVISIONED",
        limit=25,
    )
    assert any(e["target_id"] == "MEM-CLARA-H04" for e in audit_events)

    # Reusing consumed token fails closed HTTP 410 on both preview and activate
    assert fresh_client.get(f"/api/v1/onboarding/invite-preview?token={raw_token}").status_code == 410
    assert fresh_client.post("/api/v1/onboarding/activate", json={"token": raw_token}).status_code == 410

    # Verify newly activated member can immediately request a 6-digit email code at /api/v1/auth/request-code
    signin_client = TestClient(app)
    code_req = signin_client.post(
        "/api/v1/auth/request-code",
        json={"email": "clara.mccormick@carmichael-family.local"},
    )
    assert code_req.status_code == 200, code_req.text
    # Extract 6-digit code from isolated mock notification gateway dispatch log
    assert len(mock_email.delivered_log) >= 1
    last_msg = mock_email.delivered_log[-1]["safe_message"]
    code_match = re.search(r"\b(\d{6})\b", last_msg)
    assert code_match is not None, f"Expected 6-digit sign-in code in email body: {last_msg}"
    six_digit_code = code_match.group(1)

    verify_resp = signin_client.post(
        "/api/v1/auth/verify-code",
        json={"email": "clara.mccormick@carmichael-family.local", "code": six_digit_code},
    )
    assert verify_resp.status_code == 200, verify_resp.text
    assert verify_resp.json()["authenticated"] is True
    assert verify_resp.json()["session"]["scma_id"] == scma_id

    # Verify immediate access to /home, /companion, and strictly tenant-jailed /member
    assert signin_client.get("/home").status_code == 200
    assert signin_client.get("/companion").status_code == 200
    assert signin_client.get("/member").status_code == 200
    assert signin_client.get(f"/member?scma_id={scma_id}").status_code == 200

    # Cross-member SCMA tampering fails closed HTTP 403 TENANT_JAIL_VIOLATION
    tampered = signin_client.get("/member?scma_id=SCMA-FOUNDER_-C8575D7E")
    assert tampered.status_code == 403
    assert tampered.json()["error_code"] == "TENANT_JAIL_VIOLATION"

    # Admin cockpit blocked HTTP 403
    assert signin_client.get("/dashboard").status_code == 403

    # Verify expired token fails closed HTTP 410
    t0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    exp_prov = onb_svc.provision_member(
        {
            "full_name": "Expired Relative",
            "member_id": "MEM-EXPIRED-01",
            "email": "expired@carmichael-family.local",
            "lineage_house": "HOUSE-05",
            "seed_cents": 50_000,
            "bank_ref_token": "EXT-REF-PENFED-****1234",
        },
        now=t0,
    )
    with pytest.raises(InviteTokenError) as exc_info:
        onb_svc.preview_invite_token(exp_prov["invite"]["token"], now=t0 + timedelta(hours=48, seconds=1))
    assert exc_info.value.status_code == 410
    assert exc_info.value.code == "TOKEN_EXPIRED"


def test_chief_admin_solo_default_and_toggleable_two_party_cosign_with_ifas_outbox_and_allowlist(
    isolated_pr99,
) -> None:
    SessionLocalTest = isolated_pr99["session_factory"]
    gateway: AccountingGateway = isolated_pr99["gateway"]
    client = TestClient(app)

    # 1. Verify Ring 1 Alpha default admission_authority_mode is CHIEF_ADMIN_SOLO
    cfg0 = client.get("/api/v1/onboarding/delegation-config")
    assert cfg0.status_code == 200
    assert cfg0.json()["admission_authority_mode"] == ADMISSION_MODE_CHIEF_ADMIN_SOLO
    assert cfg0.json()["two_party_cosign_required"] is False
    assert cfg0.json()["delegated_onboarding_scope"] == DELEGATION_SCOPE_ADMIN_ONLY

    # Enable PER_HOUSE delegation for House 04 and assign House 04 H2 + F2-H officers
    assert client.post(
        "/api/v1/governance/roles/assign",
        headers=CA_HEADERS,
        json={"member_id": "MEM-H2-H04", "role_token": "H2", "house_id": 4},
    ).status_code == 201
    assert client.post(
        "/api/v1/governance/roles/assign",
        headers=CA_HEADERS,
        json={"member_id": "MEM-F2H-H04", "role_token": "F2-H", "house_id": 4},
    ).status_code == 201
    assert client.post(
        "/api/v1/governance/roles/assign",
        headers=CA_HEADERS,
        json={"member_id": "MEM-F2H-H02", "role_token": "F2-H", "house_id": 2},
    ).status_code == 201
    assert client.post(
        "/api/v1/governance/roles/assign",
        headers=CA_HEADERS,
        json={"member_id": "MEM-H2-H02", "role_token": "H2", "house_id": 2},
    ).status_code == 201

    enable_h4 = client.post(
        "/api/v1/onboarding/delegation-config",
        headers=CA_HEADERS,
        json={
            "delegated_onboarding_scope": DELEGATION_SCOPE_PER_HOUSE,
            "house_delegation_flags": {"4": True},
            "genealogical_board_enabled": True,
            "reason": "Enable House 04 delegated intake for PR #99 test",
        },
    )
    assert enable_h4.status_code == 200
    assert enable_h4.json()["admission_authority_mode"] == ADMISSION_MODE_CHIEF_ADMIN_SOLO

    # 2. CHIEF_ADMIN_SOLO default admits cleanly without requiring F2-H co-sign
    sub_solo = client.post(
        "/api/v1/onboarding/delegated-submit",
        headers={"X-Actor-Role": "H2", "X-Actor-ID": "MEM-H2-H04", "X-House-ID": "4"},
        json={
            "applicant_full_name": "Marcus Carmichael Solo",
            "applicant_email": "marcus.solo@carmichael-family.local",
            "target_house_id": 4,
            "kinship_verification": "Verified House 04 descendant via family chronicle",
            "custodial_status": "ADULT",
            "seed_cents": 80_000,
            "risk_dial_pct": 1.25,
            "bank_ref_token": "EXT-REF-PENFED-****9101",
            "due_diligence_attestation": "Attested by House 04 Leader with zero bank numbers stored.",
        },
    )
    assert sub_solo.status_code == 201, sub_solo.text
    solo_dos_id = sub_solo.json()["dossier"]["dossier_id"]

    rat_solo = client.post(
        f"/api/v1/onboarding/dossiers/{solo_dos_id}/ratify",
        headers=CA_HEADERS,
        json={"decision_notes": "Solo ratification under Ring 1 Alpha default"},
    )
    assert rat_solo.status_code == 200, rat_solo.text
    rat_solo_body = rat_solo.json()
    assert rat_solo_body["status"] == DOSSIER_RATIFIED_PROVISIONED
    assert rat_solo_body["admission_authority_mode"] == ADMISSION_MODE_CHIEF_ADMIN_SOLO
    assert rat_solo_body["auth_allowlist_user"]["email"] == "marcus.solo@carmichael-family.local"
    assert rat_solo_body["auth_allowlist_user"]["authorized_hats"] == ["CLASS_M"]
    assert rat_solo_body["auth_allowlist_user"]["is_apex_tier3"] is False

    # 3. Non-Chief Admin cannot toggle admission_authority_mode (HTTP 403)
    denied_toggle = client.post(
        "/api/v1/onboarding/delegation-config",
        headers={"X-Actor-Role": "F2-H", "X-Actor-ID": "MEM-F2H-H04", "X-House-ID": "4"},
        json={"admission_authority_mode": ADMISSION_MODE_TWO_PARTY_COSIGN},
    )
    assert denied_toggle.status_code == 403

    # 4. Chief Admin toggles admission_authority_mode -> TWO_PARTY_COSIGN
    toggled = client.post(
        "/api/v1/onboarding/delegation-config",
        headers=CA_HEADERS,
        json={
            "admission_authority_mode": ADMISSION_MODE_TWO_PARTY_COSIGN,
            "reason": "Require F2-H + Chief Admin two-party admission co-sign",
        },
    )
    assert toggled.status_code == 200, toggled.text
    assert toggled.json()["admission_authority_mode"] == ADMISSION_MODE_TWO_PARTY_COSIGN
    assert toggled.json()["two_party_cosign_required"] is True

    # Submit second dossier for House 04
    sub_2p = client.post(
        "/api/v1/onboarding/delegated-submit",
        headers={"X-Actor-Role": "H2", "X-Actor-ID": "MEM-H2-H04", "X-House-ID": "4"},
        json={
            "applicant_full_name": "Simone McCormick TwoParty",
            "applicant_email": "simone.twoparty@carmichael-family.local",
            "target_house_id": 4,
            "kinship_verification": "Verified House 04 lineage branch record",
            "custodial_status": "ADULT",
            "seed_cents": 95_000,
            "risk_dial_pct": 1.00,
            "bank_ref_token": "EXT-REF-PENFED-****9202",
            "due_diligence_attestation": "Verified identity and ADR-011 air-gap compliance.",
        },
    )
    assert sub_2p.status_code == 201, sub_2p.text
    dos_2p_id = sub_2p.json()["dossier"]["dossier_id"]

    # Chief Admin solo ratification MUST FAIL CLOSED with HTTP 409 TWO_PARTY_COSIGN_REQUIRED
    blocked_solo = client.post(
        f"/api/v1/onboarding/dossiers/{dos_2p_id}/ratify",
        headers=CA_HEADERS,
        json={"decision_notes": "Attempting solo ratify while TWO_PARTY_COSIGN active"},
    )
    assert blocked_solo.status_code == 409, blocked_solo.text
    assert "TWO_PARTY_COSIGN_REQUIRED" in blocked_solo.json()["detail"]

    # Confirm ZERO SCMA and ZERO AuthUserModel were provisioned when blocked
    with SessionLocalTest() as db:
        assert (
            db.query(OnboardingMemberModel)
            .filter(OnboardingMemberModel.full_name == "Simone McCormick TwoParty")
            .first()
            is None
        )
        assert (
            db.query(AuthUserModel)
            .filter(AuthUserModel.email == "simone.twoparty@carmichael-family.local")
            .first()
            is None
        )

    # Unauthorized roles attempting /cosign fail closed HTTP 403
    for bad_role in ("F1", "F2-A", "F3", "H1", "H2", "HOUSE_GENEALOGIST", "T1", "MEMBER_USER"):
        bad_cosign = client.post(
            f"/api/v1/onboarding/dossiers/{dos_2p_id}/cosign",
            headers={"X-Actor-Role": bad_role, "X-Actor-ID": f"USR-{bad_role}", "X-House-ID": "4"},
            json={"notes": "Unauthorized co-sign attempt"},
        )
        assert bad_cosign.status_code == 403, f"Expected 403 for {bad_role}, got {bad_cosign.status_code}"

    # Chief Admin calling /cosign performs read-only audit inspection and does NOT satisfy F2-H co-sign
    ca_inspect = client.post(
        f"/api/v1/onboarding/dossiers/{dos_2p_id}/cosign",
        headers=CA_HEADERS,
        json={},
    )
    assert ca_inspect.status_code == 200
    assert ca_inspect.json()["status"] == "AUDIT_INSPECTION_ONLY"
    assert ca_inspect.json()["f2h_cosigned"] is False
    assert (
        client.post(
            f"/api/v1/onboarding/dossiers/{dos_2p_id}/ratify",
            headers=CA_HEADERS,
            json={},
        ).status_code
        == 409
    )

    # Cross-house F2-H (House 02) attempting to co-sign House 04 dossier -> FAIL CLOSED HTTP 403!
    cross_f2h = client.post(
        f"/api/v1/onboarding/dossiers/{dos_2p_id}/cosign",
        headers={"X-Actor-Role": "F2-H", "X-Actor-ID": "MEM-F2H-H02", "X-House-ID": "2"},
        json={"notes": "Cross-house attempt"},
    )
    assert cross_f2h.status_code == 403
    assert "CROSS_HOUSE_COSIGN_FORBIDDEN" in cross_f2h.json()["detail"]

    # Cross-house H2 (House 02) attempting delegated-submit for House 04 -> FAIL CLOSED HTTP 403!
    cross_h2 = client.post(
        "/api/v1/onboarding/delegated-submit",
        headers={"X-Actor-Role": "H2", "X-Actor-ID": "MEM-H2-H02", "X-House-ID": "2"},
        json={
            "applicant_full_name": "Cross House Candidate",
            "applicant_email": "cross@carmichael-family.local",
            "target_house_id": 4,
            "kinship_verification": "Cross house attempt",
            "seed_cents": 25_000,
            "bank_ref_token": "EXT-REF-PENFED-****9303",
            "due_diligence_attestation": "Attempted cross-house submission.",
        },
    )
    assert cross_h2.status_code == 403
    assert "CROSS_HOUSE_DELEGATION_FORBIDDEN" in cross_h2.json()["detail"]

    # Authorized House 04 F2-H co-signs dossier -> 200 OK (still zero SCMA provisioned until Chief Admin ratifies)
    cosign_ok = client.post(
        f"/api/v1/onboarding/dossiers/{dos_2p_id}/cosign",
        headers={"X-Actor-Role": "F2-H", "X-Actor-ID": "MEM-F2H-H04", "X-House-ID": "4"},
        json={"notes": "House 04 Head of Household co-sign verified."},
    )
    assert cosign_ok.status_code == 200, cosign_ok.text
    assert cosign_ok.json()["status"] == "F2H_COSIGNED"
    assert cosign_ok.json()["f2h_cosigned"] is True
    assert cosign_ok.json()["scma_provisioned"] is False

    # Now Chief Admin final ratification SUCCEEDS and emits signed HMAC-SHA256 MEMBER_ADMISSION_RATIFIED IFAS outbox event!
    rat_2p = client.post(
        f"/api/v1/onboarding/dossiers/{dos_2p_id}/ratify",
        headers=CA_HEADERS,
        json={"decision_notes": "Two-party admission ratified."},
    )
    assert rat_2p.status_code == 200, rat_2p.text
    rat_body = rat_2p.json()
    assert rat_body["status"] == DOSSIER_RATIFIED_PROVISIONED
    assert rat_body["admission_authority_mode"] == ADMISSION_MODE_TWO_PARTY_COSIGN
    assert rat_body["dossier"]["f2h_cosigned"] is True
    assert rat_body["dossier"]["f2h_cosigned_by"] == "MEM-F2H-H04"

    # Verify AuthUserModel allowlist created for Simone (CLASS_M, non-apex)
    with SessionLocalTest() as db:
        auth_u = db.query(AuthUserModel).filter(AuthUserModel.email == "simone.twoparty@carmichael-family.local").first()
        assert auth_u is not None
        assert json.loads(auth_u.authorized_hats) == ["CLASS_M"]
        assert auth_u.is_apex_tier3 == 0
        assert auth_u.active == 1
        assert auth_u.scma_id == rat_body["member"]["scma_id"]

        # Verify signed HMAC-SHA256 IFAS outbox event + zero ADR-011 PII leakage
        outbox_evt = rat_body["ifas_outbox_event"]
        db_evt = db.get(AccountingOutboxEventModel, outbox_evt["event_id"])
        assert db_evt is not None
        assert db_evt.event_type == "MEMBER_ADMISSION_RATIFIED"
        assert gateway.verify_event_signature(outbox_evt) is True if hasattr(gateway, "verify_event_signature") else True
        secret_bytes = gateway.secret_key if isinstance(gateway.secret_key, bytes) else str(gateway.secret_key).encode("utf-8")
        expected_sig = hmac.new(
            secret_bytes,
            json.dumps(outbox_evt["payload"], sort_keys=True, separators=(",", ":")).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert db_evt.signature_hmac_sha256 == outbox_evt["signature_hmac_sha256"] == expected_sig
        raw_payload_text = db_evt.payload_json.lower()
        for banned in ("routing_number", "account_number", "ssn", "social_security", "swift_code", "bank_password"):
            assert banned not in raw_payload_text
        parsed_ifas = json.loads(db_evt.payload_json)
        assert parsed_ifas["admission_authority_mode"] == ADMISSION_MODE_TWO_PARTY_COSIGN
        assert parsed_ifas["f2h_cosigned_by"] == "MEM-F2H-H04"
        assert parsed_ifas["bank_ref_token"] == "EXT-REF-PENFED-****9202"


def test_house_delegated_intake_and_f2h_cosign_server_side_dom_stripping() -> None:
    client = TestClient(app)

    # /lineage/house/1: H2 and HOUSE_GENEALOGIST get collapsible intake panel; H1 strictly stripped!
    h2_html = client.get("/lineage/house/1?role=H2").text
    assert 'id="houseDelegatedOnboardingPanel"' in h2_html
    assert 'id="houseDelegatedOnboardingDrawer"' in h2_html

    gen_html = client.get("/lineage/house/1?role=HOUSE_GENEALOGIST").text
    assert 'id="houseDelegatedOnboardingPanel"' in gen_html
    assert "$****.**" in gen_html  # Genealogist retains R-12 financial masking

    h1_html = client.get("/lineage/house/1?role=H1").text
    assert 'id="houseDelegatedOnboardingPanel"' not in h1_html
    assert 'id="houseDelegatedIntakeForm"' not in h1_html

    # /advisor: F2-H gets Pending Member Admission Co-Signs; F1, F2-A, F3 strictly stripped!
    f2h_html = client.get("/advisor?role=F2-H").text
    assert 'id="f2hAdmissionCosignSection"' in f2h_html
    assert "Pending Member Admission Co-Signs" in f2h_html

    for stripped_role in ("F1", "F2-A", "F3"):
        other_html = client.get(f"/advisor?role={stripped_role}").text
        assert 'id="f2hAdmissionCosignSection"' not in other_html, f"Expected F2-H co-sign stripped for {stripped_role}"


def test_local_first_tutors_answer_onboarding_and_two_party_admission_with_zero_outbound_llm_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.domain.ai_clients.gemini_adapter import GeminiLLMClient
    from app.domain.ai_clients.openai_adapter import OpenAILLMClient

    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key-pr99")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key-pr99")

    gemini_spy = MagicMock(side_effect=AssertionError("GeminiLLMClient.generate_response MUST NOT be called"))
    openai_spy = MagicMock(side_effect=AssertionError("OpenAILLMClient.generate_response MUST NOT be called"))
    monkeypatch.setattr(GeminiLLMClient, "generate_response", gemini_spy)
    monkeypatch.setattr(OpenAILLMClient, "generate_response", openai_spy)

    client = TestClient(app)

    # 1. Member Tutor: "How do I activate my invite?"
    m_resp = client.post(
        "/api/v1/portal/member/tutor",
        json={"question": "How do I activate my invite?", "scma_id": "SCMA-ELEANOR_-B2B31C9E"},
    )
    assert m_resp.status_code == 200, m_resp.text
    m_res = m_resp.json()
    assert m_res["answered_locally"] is True
    assert m_res["provider_used"] == "local_knowledge_index"
    assert m_res["unilateral_execution"] is False
    assert any("onboarding_admission_flow.svg" in r["path"] for r in m_res["media_refs"])

    # 2. Community Dual-Lane Tutor: "How do I activate my invite?"
    c_resp = client.post(
        "/api/v1/portal/community/academy/ask-tutor",
        json={"member_id": "MEM-PR99", "query": "How do I activate my invite?"},
    )
    assert c_resp.status_code == 200, c_resp.text
    c_res = c_resp.json()
    assert c_res["answered_locally"] is True
    assert c_res["provider_used"] == "local_knowledge_index"
    assert c_res["unilateral_execution"] is False
    assert any("onboarding_admission_flow.svg" in r["path"] for r in c_res["media_refs"])

    # 3. Class F (F2-H) Copilot: "How does two-party admission work?"
    f_resp = client.post(
        "/api/v1/portal/advisor/copilot",
        json={"query": "How does two-party admission work?", "role": "F2-H", "household_id": "HOUSEHOLD-ALPHA"},
    )
    assert f_resp.status_code == 200, f_resp.text
    f_res = f_resp.json()
    assert f_res["answered_locally"] is True
    assert f_res["provider_used"] == "local_knowledge_index"
    assert f_res["unilateral_execution"] is False
    assert any("onboarding_admission_flow.svg" in r["path"] for r in f_res["media_refs"])

    # 4. Class H (H2) Tutor: "How does two-party admission work?"
    h_resp = client.post(
        "/api/v1/portal/lineage/tutor",
        headers={"X-House-ID": "1", "X-Actor-Role": "H2"},
        json={"query": "How does two-party admission work?", "role": "H2", "house_id": 1},
    )
    assert h_resp.status_code == 200, h_resp.text
    h_res = h_resp.json()
    assert h_res["answered_locally"] is True
    assert h_res["provider_used"] == "local_knowledge_index"
    assert h_res["unilateral_execution"] is False
    assert any("onboarding_admission_flow.svg" in r["path"] for r in h_res["media_refs"])

    # 5. Chief Admin Chancellor Coach: "How does two-party admission work?"
    ca_resp = client.post(
        "/api/v1/copilot/query",
        json={
            "prompt": "How does two-party admission work?",
            "user_id": "USR-founder_ch-C8575D7E",
            "role": "OPERATOR",
        },
    )
    assert ca_resp.status_code == 200, ca_resp.text
    ca_res = ca_resp.json()
    assert ca_res["answered_locally"] is True
    assert ca_res["provider_used"] == "local_knowledge_index"
    assert ca_res["unilateral_execution"] is False
    assert any("onboarding_admission_flow.svg" in r["path"] for r in ca_res["media_refs"])

    gemini_spy.assert_not_called()
    openai_spy.assert_not_called()


def test_twelve_portal_templates_byte_parity_zero_cdn_playbook_and_inventory_gate() -> None:
    external_tag_re = re.compile(
        r"<(?:script|link)\b[^>]+(?:src|href)\s*=\s*['\"]https?://", re.IGNORECASE
    )
    for filename in TWELVE_PORTAL_TEMPLATES:
        api_path = API_V1_DIR / filename
        static_path = STATIC_DIR / filename
        assert api_path.is_file(), f"Missing {api_path}"
        assert static_path.is_file(), f"Missing {static_path}"
        api_bytes = api_path.read_bytes()
        static_bytes = static_path.read_bytes()
        assert api_bytes == static_bytes, f"Byte-for-byte parity drift for {filename}"
        assert external_tag_re.search(api_bytes.decode("utf-8")) is None, f"External CDN in {filename}"

    # Verify playbook registry validates cleanly with PR #99 onboarding playbook + local SVG diagram
    reg = load_training_media_registry()
    assert validate_training_media_registry(reg, repo_root=REPO_ROOT, check_files=True) == []
    pb_map = {pb["playbook_id"]: pb for pb in reg["playbooks"]}
    assert "onboarding_invite_and_admission_flow" in pb_map
    pb = pb_map["onboarding_invite_and_admission_flow"]
    assert pb["scenario_type"] == "routine"
    assert {"CLASS_M", "H2", "HOUSE_GENEALOGIST", "F2-H", "CHIEF_ADMIN"}.issubset(set(pb["role_classes"]))
    assert (STATIC_DIR / "media" / "playbooks" / "onboarding_admission_flow.svg").is_file()

    # Verify Portal Discovery registers all 12 portals and passes parity gate with 0 undocumented controls
    assert "/activate" in PORTALS
    assert len(PORTALS) == 12
    report = audit_ui_lexicon_curriculum_parity(REPO_ROOT)
    assert report["passed"] is True, f"Parity audit failed: {report}"
    assert report["undocumented_controls"] == []
    assert generate_inventory(REPO_ROOT) == (
        REPO_ROOT / "docs" / "PORTAL_COMPONENT_INVENTORY.md"
    ).read_text(encoding="utf-8")
