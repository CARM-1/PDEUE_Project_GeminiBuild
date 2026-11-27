"""PR #98 Verification Suite:
Universal 6-Digit Email Code & Magic Link Sign-In, Apex Passphrase + MFA (with WebAuthn hook),
Server-Side Tenant Jailing, Directive R-06 Active-Hat Lock, Chief Admin Lost-Device Revocation,
Local-First Sign-In AI Tutor Playbooks, Alembic 008 Migration, Zero-CDN & 11-Template Parity.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import pathlib
import re
from typing import Any, Dict

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect as sa_inspect
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AuthLoginChallengeModel,
    AuthSessionModel,
    AuthUserModel,
    Base,
)
from app.domain.authority_tiers import get_governance_audit_log
from app.domain.local_knowledge_index import (
    get_local_knowledge_index,
    reset_local_knowledge_index,
)
from app.domain.notification_gateway import MockNotificationClient, NotificationGateway
from app.domain.session_auth_service import (
    CLASS_M_ACTIVE_WINDOW_SECONDS,
    CLASS_M_IDLE_TIMEOUT_SECONDS,
    DEV_DEFAULT_APEX_MFA_CODE,
    DEV_DEFAULT_APEX_PASSPHRASE,
    GENERIC_CODE_SENT_MESSAGE,
    OFFICER_ACTIVE_WINDOW_SECONDS,
    OFFICER_IDLE_TIMEOUT_SECONDS,
    SESSION_COOKIE_NAME,
    SessionAuthService,
    reset_session_auth_service,
    sha256_hex,
)
from app.domain.training_media_registry import (
    load_training_media_registry,
    validate_training_media_registry,
)
from app.main import app
from app.portal_discovery import (
    PORTALS,
    audit_ui_lexicon_curriculum_parity,
    generate_inventory,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
API_V1_DIR = BACKEND_DIR / "app" / "api" / "v1"
STATIC_DIR = BACKEND_DIR / "app" / "static"

ELEVEN_PORTAL_TEMPLATES = (
    "login.html",
    "home.html",
    "dashboard.html",
    "member.html",
    "advisor.html",
    "tech.html",
    "lineage_house.html",
    "community.html",
    "heritage.html",
    "heritage_tree.html",
    "companion.html",
)


class MutableClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: Any) -> None:
        self.now = self.now + timedelta(**kwargs)


@pytest.fixture()
def isolated_auth_env(tmp_path: pathlib.Path):
    db_file = tmp_path / "pr98_auth_test.db"
    eng = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=eng)

    mock_email = MockNotificationClient(channel="email")
    gateway = NotificationGateway(
        in_app_client=MockNotificationClient(channel="in_app"),
        email_client=mock_email,
        sms_client=MockNotificationClient(channel="sms"),
    )
    clock = MutableClock(datetime(2026, 11, 27, 15, 0, 0, tzinfo=timezone.utc))
    svc = SessionAuthService(
        session_factory=session_factory,
        bind_engine=eng,
        notification_gateway=gateway,
        clock_fn=clock,
        seed_defaults=True,
    )
    reset_session_auth_service(svc)
    try:
        yield {
            "service": svc,
            "session_factory": session_factory,
            "engine": eng,
            "mock_email": mock_email,
            "clock": clock,
        }
    finally:
        reset_session_auth_service(None)
        eng.dispose()


def _extract_code_and_magic_from_last_email(mock_email: MockNotificationClient) -> tuple[str, str]:
    assert mock_email.delivered_log, "Expected at least one email delivery"
    msg = mock_email.delivered_log[-1]["safe_message"]
    code_match = re.search(r"\b(\d{6})\b", msg)
    magic_match = re.search(r"/api/v1/auth/magic\?token=([A-Za-z0-9_-]+)", msg)
    assert code_match, f"6-digit code not found in email: {msg}"
    assert magic_match, f"Magic Link token not found in email: {msg}"
    return code_match.group(1), magic_match.group(1)


# ---------------------------------------------------------------------------
# 1. Private Allowlist Enforcement & Zero Leakage
# ---------------------------------------------------------------------------


def test_private_allowlist_unknown_email_returns_generic_200_and_sends_zero_notifications(
    isolated_auth_env: Dict[str, Any],
) -> None:
    mock_email: MockNotificationClient = isolated_auth_env["mock_email"]
    client = TestClient(app)

    resp = client.post("/api/v1/auth/request-code", json={"email": "outsider@example.com"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "OK"
    assert body["message"] == GENERIC_CODE_SENT_MESSAGE
    assert len(mock_email.delivered_log) == 0

    # Inactive user on allowlist also gets generic 200 and sends 0 notifications
    isolated_auth_env["service"].upsert_allowlist_user(
        user_id="USR-INACTIVE-01",
        email="inactive@carmichael-family.local",
        display_name="Inactive Relative",
        active=False,
    )
    resp_inactive = client.post(
        "/api/v1/auth/request-code", json={"email": "inactive@carmichael-family.local"}
    )
    assert resp_inactive.status_code == 200
    assert resp_inactive.json() == body
    assert len(mock_email.delivered_log) == 0


# ---------------------------------------------------------------------------
# 2. 6-Digit Code & Magic Link Issuance, Single-Use Burn, 10m TTL & 5-Attempt Lockout
# ---------------------------------------------------------------------------


def test_six_digit_code_hash_only_r12_safe_single_use_burn_and_cookie_flags(
    isolated_auth_env: Dict[str, Any],
) -> None:
    mock_email: MockNotificationClient = isolated_auth_env["mock_email"]
    session_factory = isolated_auth_env["session_factory"]
    client = TestClient(app)

    req = client.post("/api/v1/auth/request-code", json={"email": "julian@carmichael-family.local"})
    assert req.status_code == 200
    assert req.json()["message"] == GENERIC_CODE_SENT_MESSAGE
    assert len(mock_email.delivered_log) == 1

    # Directive R-12 check on outbound sign-in email (zero balances, zero SCMA IDs)
    delivery = mock_email.delivered_log[-1]
    assert delivery["r12_sanitized"] is True
    assert delivery["redactions_applied"] == []
    assert "SCMA-" not in delivery["safe_message"]
    assert "$" not in delivery["safe_message"]

    code, magic_token = _extract_code_and_magic_from_last_email(mock_email)

    # DB stores strictly SHA-256 hashes, never plaintext code or magic token
    db = session_factory()
    try:
        chg = db.query(AuthLoginChallengeModel).first()
        assert chg is not None
        assert chg.code_hash == sha256_hex(code)
        assert chg.code_hash != code
        assert chg.magic_token_hash == sha256_hex(magic_token)
        assert chg.magic_token_hash != magic_token
        assert chg.consumed_at is None
    finally:
        db.close()

    # Verify 6-digit code -> sets HttpOnly SameSite=Lax cookie & burns challenge
    ver = client.post(
        "/api/v1/auth/verify-code",
        json={"email": "julian@carmichael-family.local", "code": code},
    )
    assert ver.status_code == 200
    data = ver.json()
    assert data["authenticated"] is True
    assert data["session"]["user_id"] == "USR-julian_va-A1F98B21"
    assert data["session"]["scma_id"] == "SCMA-JULIAN_-A1F98B21"
    assert data["session"]["active_hat"] == "MEMBER_USER"
    assert data["session"]["idle_timeout_seconds"] == CLASS_M_IDLE_TIMEOUT_SECONDS
    set_cookie_hdr = ver.headers.get("set-cookie", "")
    assert f"{SESSION_COOKIE_NAME}=" in set_cookie_hdr
    assert "HttpOnly" in set_cookie_hdr
    assert "SameSite=lax" in set_cookie_hdr or "SameSite=Lax" in set_cookie_hdr

    # Reusing the same 6-digit code OR its paired Magic Link MUST fail (permanent single-use burn)
    replay_code = client.post(
        "/api/v1/auth/verify-code",
        json={"email": "julian@carmichael-family.local", "code": code},
    )
    assert replay_code.status_code == 401

    replay_magic = client.get(f"/api/v1/auth/magic?token={magic_token}", follow_redirects=False)
    assert replay_magic.status_code == 401


def test_magic_link_sign_in_and_single_use_burn(isolated_auth_env: Dict[str, Any]) -> None:
    mock_email: MockNotificationClient = isolated_auth_env["mock_email"]
    client = TestClient(app)

    client.post("/api/v1/auth/request-code", json={"email": "eleanor@carmichael-family.local"})
    code, magic_token = _extract_code_and_magic_from_last_email(mock_email)

    resp = client.get(f"/api/v1/auth/magic?token={magic_token}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/member"
    assert f"{SESSION_COOKIE_NAME}=" in resp.headers.get("set-cookie", "")

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["session"]["scma_id"] == "SCMA-ELEANOR_-B2B31C9E"

    # Replaying Magic Link or paired 6-digit code fails closed
    assert client.get(f"/api/v1/auth/magic?token={magic_token}", follow_redirects=False).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/verify-code",
            json={"email": "eleanor@carmichael-family.local", "code": code},
        ).status_code
        == 401
    )


def test_code_expiry_10_minutes_and_5_attempt_lockout(isolated_auth_env: Dict[str, Any]) -> None:
    mock_email: MockNotificationClient = isolated_auth_env["mock_email"]
    clock: MutableClock = isolated_auth_env["clock"]
    client = TestClient(app)

    # 1. 10-minute TTL expiry
    client.post("/api/v1/auth/request-code", json={"email": "julian@carmichael-family.local"})
    code, magic_token = _extract_code_and_magic_from_last_email(mock_email)
    clock.advance(minutes=10, seconds=1)

    expired_code = client.post(
        "/api/v1/auth/verify-code",
        json={"email": "julian@carmichael-family.local", "code": code},
    )
    assert expired_code.status_code == 401
    assert "expired" in expired_code.json()["detail"].lower()
    assert client.get(f"/api/v1/auth/magic?token={magic_token}", follow_redirects=False).status_code == 401

    # 2. 5-attempt lockout permanently burns the challenge
    client.post("/api/v1/auth/request-code", json={"email": "julian@carmichael-family.local"})
    fresh_code, _ = _extract_code_and_magic_from_last_email(mock_email)
    wrong_code = "000000" if fresh_code != "000000" else "999999"

    for attempt in range(1, 5):
        r = client.post(
            "/api/v1/auth/verify-code",
            json={"email": "julian@carmichael-family.local", "code": wrong_code},
        )
        assert r.status_code == 401, f"Attempt {attempt} should return 401"

    fifth = client.post(
        "/api/v1/auth/verify-code",
        json={"email": "julian@carmichael-family.local", "code": wrong_code},
    )
    assert fifth.status_code == 429

    # Even the correct code is now rejected because 5 failed attempts burned the challenge
    after_lock = client.post(
        "/api/v1/auth/verify-code",
        json={"email": "julian@carmichael-family.local", "code": fresh_code},
    )
    assert after_lock.status_code == 429


# ---------------------------------------------------------------------------
# 3. Apex & Tier-3 Command Sign-In (CHIEF_ADMIN, T3, F3) & Passwordless Block
# ---------------------------------------------------------------------------


def test_apex_tier3_passphrase_mfa_and_passwordless_shortcut_rejected(
    isolated_auth_env: Dict[str, Any],
) -> None:
    mock_email: MockNotificationClient = isolated_auth_env["mock_email"]
    svc: SessionAuthService = isolated_auth_env["service"]
    client = TestClient(app)

    # All three Apex/Tier-3 command accounts MUST reject passwordless shortcut (HTTP 403)
    for apex_email in (
        "founder@carmichael-family.local",
        "cto@carmichael-family.local",
        "cro@carmichael-family.local",
    ):
        denied = client.post("/api/v1/auth/request-code", json={"email": apex_email})
        assert denied.status_code == 403
        assert "APEX_MFA_REQUIRED" in denied.json()["detail"]
    assert len(mock_email.delivered_log) == 0

    # Wrong passphrase or wrong MFA code fails closed (HTTP 401)
    bad_pw = client.post(
        "/api/v1/auth/apex-login",
        json={
            "email": "founder@carmichael-family.local",
            "passphrase": "wrong-passphrase",
            "mfa_code": DEV_DEFAULT_APEX_MFA_CODE,
        },
    )
    assert bad_pw.status_code == 401

    bad_mfa = client.post(
        "/api/v1/auth/apex-login",
        json={
            "email": "founder@carmichael-family.local",
            "passphrase": DEV_DEFAULT_APEX_PASSPHRASE,
            "mfa_code": "111111",
        },
    )
    assert bad_mfa.status_code == 401

    # Valid passphrase + 6-digit MFA succeeds for CHIEF_ADMIN, T3, F3 with 8h/30m Officer window
    for apex_email, expected_hat in (
        ("founder@carmichael-family.local", "CHIEF_ADMINISTRATOR"),
        ("cto@carmichael-family.local", "T3"),
        ("cro@carmichael-family.local", "F3"),
    ):
        c = TestClient(app)
        ok = c.post(
            "/api/v1/auth/apex-login",
            json={
                "email": apex_email,
                "passphrase": DEV_DEFAULT_APEX_PASSPHRASE,
                "mfa_code": DEV_DEFAULT_APEX_MFA_CODE,
            },
        )
        assert ok.status_code == 200
        sess = ok.json()["session"]
        assert sess["active_hat"] == expected_hat
        assert sess["idle_timeout_seconds"] == OFFICER_IDLE_TIMEOUT_SECONDS
        issued = datetime.fromisoformat(sess["issued_at"])
        expires = datetime.fromisoformat(sess["expires_at"])
        assert int((expires - issued).total_seconds()) == OFFICER_ACTIVE_WINDOW_SECONDS

    # FIDO2 / WebAuthn verifier hook works when plugged in
    svc.set_webauthn_verifier(lambda user, assertion: assertion.get("credential_ok") is True)
    c_webauthn = TestClient(app)
    ok_wa = c_webauthn.post(
        "/api/v1/auth/apex-login",
        json={
            "email": "founder@carmichael-family.local",
            "passphrase": DEV_DEFAULT_APEX_PASSPHRASE,
            "webauthn_assertion": {"credential_ok": True},
        },
    )
    assert ok_wa.status_code == 200
    assert ok_wa.json()["session"]["active_hat"] == "CHIEF_ADMINISTRATOR"


# ---------------------------------------------------------------------------
# 4. Server-Side ?scma_id= Tenant Jailing, Active-Hat Lock & Idle Timeout
# ---------------------------------------------------------------------------


def test_server_side_scma_tenant_jailing_and_chief_admin_supervisory_lens(
    isolated_auth_env: Dict[str, Any],
) -> None:
    mock_email: MockNotificationClient = isolated_auth_env["mock_email"]
    julian_client = TestClient(app)

    julian_client.post("/api/v1/auth/request-code", json={"email": "julian@carmichael-family.local"})
    code, _ = _extract_code_and_magic_from_last_email(mock_email)
    assert (
        julian_client.post(
            "/api/v1/auth/verify-code",
            json={"email": "julian@carmichael-family.local", "code": code},
        ).status_code
        == 200
    )

    # Without ?scma_id=, server automatically jails Julian to SCMA-JULIAN_-A1F98B21
    own_state = julian_client.get("/api/v1/portal/member/state")
    assert own_state.status_code == 200
    assert own_state.json()["scma_id"] == "SCMA-JULIAN_-A1F98B21"

    # Own SCMA explicitly requested is allowed
    assert julian_client.get("/member?scma_id=SCMA-JULIAN_-A1F98B21").status_code == 200
    assert (
        julian_client.get("/api/v1/portal/member/state?scma_id=SCMA-JULIAN_-A1F98B21").status_code
        == 200
    )

    # Tampering with ?scma_id= to inspect another relative's account fails closed HTTP 403!
    tamper_html = julian_client.get("/member?scma_id=SCMA-ELEANOR_-B2B31C9E")
    assert tamper_html.status_code == 403
    assert "TENANT_JAIL_VIOLATION" in tamper_html.json()["error_code"]

    tamper_api = julian_client.get("/api/v1/portal/member/state?scma_id=SCMA-ELEANOR_-B2B31C9E")
    assert tamper_api.status_code == 403
    assert "TENANT_JAIL_VIOLATION" in tamper_api.json()["error_code"]

    tamper_path = julian_client.get("/api/v1/portal/member/SCMA-ELEANOR_-B2B31C9E")
    assert tamper_path.status_code == 403

    tamper_risk = julian_client.post(
        "/api/v1/portal/member/risk-dial",
        json={"scma_id": "SCMA-ELEANOR_-B2B31C9E", "requested_risk_pct": 1.0},
    )
    assert tamper_risk.status_code == 403

    # CHIEF_ADMIN retains read-only Supervisory Audit Lens inspection across member SCMAs
    admin_client = TestClient(app)
    assert (
        admin_client.post(
            "/api/v1/auth/apex-login",
            json={
                "email": "founder@carmichael-family.local",
                "passphrase": DEV_DEFAULT_APEX_PASSPHRASE,
                "mfa_code": DEV_DEFAULT_APEX_MFA_CODE,
            },
        ).status_code
        == 200
    )
    lens_html = admin_client.get("/member?scma_id=SCMA-ELEANOR_-B2B31C9E&supervisory=1&inspector=CHIEF_ADMIN")
    assert lens_html.status_code == 200
    lens_state = admin_client.get("/api/v1/portal/member/state?scma_id=SCMA-ELEANOR_-B2B31C9E")
    assert lens_state.status_code == 200
    assert lens_state.json()["scma_id"] == "SCMA-ELEANOR_-B2B31C9E"


def test_strict_mode_fail_closed_active_hat_switch_and_idle_timeout(
    isolated_auth_env: Dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PDEUE_ENFORCE_SESSION_AUTH", "true")
    mock_email: MockNotificationClient = isolated_auth_env["mock_email"]
    clock: MutableClock = isolated_auth_env["clock"]

    anon = TestClient(app)
    # Exempt routes stay reachable
    assert anon.get("/login").status_code == 200
    assert anon.get("/health").status_code == 200
    assert anon.get("/api/v1/portal/planes").status_code == 200

    # HTML portals redirect fail-closed to /login?next=...
    for route in (
        "/dashboard",
        "/member",
        "/advisor",
        "/admin/tech",
        "/lineage/house/1",
        "/community",
        "/community/heritage",
        "/community/heritage/tree",
        "/companion",
    ):
        r = anon.get(route, follow_redirects=False)
        assert r.status_code == 302, f"{route} should redirect to /login in strict mode"
        assert r.headers["location"].startswith("/login?next=")

    # API routes fail closed with HTTP 401
    assert anon.get("/api/v1/portal/member/state").status_code == 401
    assert anon.get("/api/v1/auth/sessions").status_code == 401

    # Sign in as Eleanor (authorized hats: MEMBER_USER, PERSONAL_SCMA, F2-H)
    eleanor = TestClient(app)
    eleanor.post("/api/v1/auth/request-code", json={"email": "eleanor@carmichael-family.local"})
    code, _ = _extract_code_and_magic_from_last_email(mock_email)
    assert (
        eleanor.post(
            "/api/v1/auth/verify-code",
            json={"email": "eleanor@carmichael-family.local", "code": code},
        ).status_code
        == 200
    )

    # Under MEMBER_USER hat: /member allowed, /dashboard /advisor /admin/tech blocked 403!
    assert eleanor.get("/member").status_code == 200
    assert eleanor.get("/dashboard").status_code == 403
    assert eleanor.get("/advisor").status_code == 403
    assert eleanor.get("/admin/tech").status_code == 403

    # Attempting unauthorized Active-Hat switch (to CHIEF_ADMINISTRATOR) fails closed 403
    bad_hat = eleanor.post(
        "/api/v1/auth/switch-hat",
        json={"to_hat": "CHIEF_ADMINISTRATOR", "confirmed": True},
    )
    assert bad_hat.status_code == 403

    # Valid Directive R-06 Active-Hat switch to F2-H rotates hat server-side and unlocks /advisor?role=F2-H
    sw = eleanor.post(
        "/api/v1/auth/switch-hat",
        json={"to_hat": "F2-H", "confirmed": True, "reason": "Review household proposals"},
    )
    assert sw.status_code == 200
    assert sw.json()["active_hat"] == "F2-H"
    assert sw.json()["session"]["idle_timeout_seconds"] == OFFICER_IDLE_TIMEOUT_SECONDS
    assert eleanor.get("/advisor?role=F2-H").status_code == 200
    assert eleanor.get("/advisor?role=F3").status_code == 403  # cross-tier blocked!
    assert eleanor.get("/member").status_code == 403  # must switch hat back to MEMBER_USER first!

    # Idle timeout enforcement (30 minutes for F2-H officer hat)
    clock.advance(minutes=31)
    assert eleanor.get("/api/v1/auth/me").status_code == 401
    idle_html = eleanor.get("/advisor?role=F2-H", follow_redirects=False)
    assert idle_html.status_code == 302
    assert idle_html.headers["location"].startswith("/login")


# ---------------------------------------------------------------------------
# 5. Chief Admin Instant Session Revocation & Audit Trail
# ---------------------------------------------------------------------------


def test_chief_admin_session_revocation_invalidates_cookie_and_logs_audit(
    isolated_auth_env: Dict[str, Any],
) -> None:
    mock_email: MockNotificationClient = isolated_auth_env["mock_email"]
    audit = get_governance_audit_log()

    # 1. Member signs in on a phone
    member_client = TestClient(app)
    member_client.post("/api/v1/auth/request-code", json={"email": "julian@carmichael-family.local"})
    code, _ = _extract_code_and_magic_from_last_email(mock_email)
    ver = member_client.post(
        "/api/v1/auth/verify-code",
        json={"email": "julian@carmichael-family.local", "code": code},
    )
    assert ver.status_code == 200
    lost_session_id = ver.json()["session"]["session_id"]

    # Non-Chief-Admin cannot inspect or revoke sessions (HTTP 403)
    assert member_client.get("/api/v1/auth/sessions").status_code == 403
    assert member_client.post(f"/api/v1/auth/sessions/{lost_session_id}/revoke").status_code == 403

    # 2. Chief Admin signs in via Apex Passphrase + MFA, inspects sessions, and revokes lost phone
    admin_client = TestClient(app)
    assert (
        admin_client.post(
            "/api/v1/auth/apex-login",
            json={
                "email": "founder@carmichael-family.local",
                "passphrase": DEV_DEFAULT_APEX_PASSPHRASE,
                "mfa_code": DEV_DEFAULT_APEX_MFA_CODE,
            },
        ).status_code
        == 200
    )
    listed = admin_client.get("/api/v1/auth/sessions")
    assert listed.status_code == 200
    assert any(s["session_id"] == lost_session_id and s["is_active"] for s in listed.json()["sessions"])

    rev = admin_client.post(
        f"/api/v1/auth/sessions/{lost_session_id}/revoke",
        json={"reason": "Member lost phone at airport"},
    )
    assert rev.status_code == 200
    assert rev.json()["status"] == "REVOKED"
    assert rev.json()["audit_event_id"].startswith("AUD-")

    # GovernanceAuditLog recorded AUTH_SESSION_REVOKED
    rev_events = audit.list_events(event_type="AUTH_SESSION_REVOKED", limit=20)
    assert any(e["target_id"] == lost_session_id for e in rev_events)

    # 3. Revoked cookie immediately fails closed on API (401) and HTML (/member -> 302 /login)
    revoked_cookie = member_client.cookies.get(SESSION_COOKIE_NAME)
    assert revoked_cookie
    assert TestClient(app).get("/api/v1/auth/me", cookies={SESSION_COOKIE_NAME: revoked_cookie}).status_code == 401
    assert TestClient(app).get("/api/v1/portal/member/state", cookies={SESSION_COOKIE_NAME: revoked_cookie}).status_code == 401
    redir = TestClient(app).get(
        "/member",
        cookies={SESSION_COOKIE_NAME: revoked_cookie},
        follow_redirects=False,
    )
    assert redir.status_code == 302
    assert redir.headers["location"].startswith("/login")

    # 4. Clean self-service Sign Out also revokes session
    logout_resp = admin_client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200
    assert logout_resp.json()["status"] == "SIGNED_OUT"
    assert admin_client.get("/api/v1/auth/me").status_code == 401


# ---------------------------------------------------------------------------
# 6. Local-First AI Tutors Answer Sign-In & Lost-Phone Questions Locally
# ---------------------------------------------------------------------------


def test_local_first_tutors_answer_signin_password_and_lost_phone_locally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_local_knowledge_index()
    idx = get_local_knowledge_index()

    # Verify index top-1 playbooks & visual media
    q_signin = idx.query("How do I sign in?", role="CLASS_M")
    assert q_signin.matched is True
    assert q_signin.top_playbook_id == "class_m_private_signin_and_sessions"
    assert any(m["path"] == "/static/media/playbooks/signin_security_flow.svg" for m in q_signin.media_refs)

    q_pw = idx.query("Where is my password?", role="CLASS_M")
    assert q_pw.matched is True
    assert q_pw.top_playbook_id == "class_m_private_signin_and_sessions"

    q_lost = idx.query("I lost my phone", role="CLASS_M")
    assert q_lost.matched is True
    assert q_lost.top_playbook_id == "chief_admin_lost_device_session_revocation"
    assert any(m["path"] == "/static/media/playbooks/signin_security_flow.svg" for m in q_lost.media_refs)

    # Prove 0 outbound LLM calls across Member Tutor, Community Academy Tutor, Advisory Copilot, and Chancellor Coach
    client = TestClient(app)
    for prompt in ("How do I sign in?", "Where is my password?", "I lost my phone"):
        m_resp = client.post("/api/v1/portal/member/tutor", json={"question": prompt})
        assert m_resp.status_code == 200
        m_data = m_resp.json()
        assert m_data["answered_locally"] is True
        assert m_data["provider_used"] == "local_knowledge_index"
        assert m_data.get("playbook_steps"), f"Expected step cards for {prompt}"
        assert any(
            m["path"] == "/static/media/playbooks/signin_security_flow.svg"
            for m in (m_data.get("media_refs") or [])
        )

        a_resp = client.post(
            "/api/v1/portal/community/academy/ask-tutor",
            json={"query": prompt, "member_id": "MEM-CLASS-M"},
        )
        assert a_resp.status_code == 200
        a_data = a_resp.json()
        assert a_data["answered_locally"] is True
        assert any(
            m["path"] == "/static/media/playbooks/signin_security_flow.svg"
            for m in (a_data.get("media_refs") or [])
        )

    # Chancellor Coach for CHIEF_ADMIN also answers lost-device revocation 100% locally
    ch_resp = client.post(
        "/api/v1/operator/chancellor/query",
        json={"query": "I lost my phone, how do I revoke a session?"},
    )
    assert ch_resp.status_code == 200
    assert ch_resp.json()["answered_locally"] is True


# ---------------------------------------------------------------------------
# 7. Alembic 008 Migration, Registry Validation, Zero-CDN & 11-Template Parity
# ---------------------------------------------------------------------------


def test_alembic_008_session_auth_migration_idempotent(tmp_path: pathlib.Path) -> None:
    mig_path = BACKEND_DIR / "alembic" / "versions" / "008_add_session_auth_tables.py"
    assert mig_path.is_file()
    spec = importlib.util.spec_from_file_location("mig008", mig_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    eng = create_engine(f"sqlite:///{tmp_path / 'mig008.db'}")
    with eng.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()
            mod.upgrade()  # Idempotent second run
        tables = set(sa_inspect(conn).get_table_names())
        assert {"auth_users", "auth_login_challenges", "auth_sessions"}.issubset(tables)
        with Operations.context(ctx):
            mod.downgrade()
        tables_after = set(sa_inspect(conn).get_table_names())
        assert "auth_users" not in tables_after
        assert "auth_login_challenges" not in tables_after
        assert "auth_sessions" not in tables_after
    eng.dispose()


def test_eleven_portal_templates_byte_parity_zero_cdn_playbooks_and_inventory() -> None:
    external_tag_re = re.compile(
        r"<(?:script|link)\b[^>]+(?:src|href)\s*=\s*['\"]https?://", re.IGNORECASE
    )
    for filename in ELEVEN_PORTAL_TEMPLATES:
        api_path = API_V1_DIR / filename
        static_path = STATIC_DIR / filename
        assert api_path.is_file(), f"Missing {api_path}"
        assert static_path.is_file(), f"Missing {static_path}"
        api_bytes = api_path.read_bytes()
        static_bytes = static_path.read_bytes()
        assert api_bytes == static_bytes, f"Byte-for-byte parity drift for {filename}"
        assert external_tag_re.search(api_bytes.decode("utf-8")) is None, f"External CDN in {filename}"

    # Verify playbook registry validates cleanly with new sign-in & lost-device playbooks + SVG diagram
    reg = load_training_media_registry()
    assert validate_training_media_registry(reg, repo_root=REPO_ROOT, check_files=True) == []
    pb_ids = {pb["playbook_id"] for pb in reg["playbooks"]}
    assert "class_m_private_signin_and_sessions" in pb_ids
    assert "chief_admin_lost_device_session_revocation" in pb_ids
    assert (STATIC_DIR / "media" / "playbooks" / "signin_security_flow.svg").is_file()

    # Verify Portal Discovery registers /login (and all registered portals) and passes parity gate with 0 undocumented controls
    assert "/login" in PORTALS
    assert len(PORTALS) >= 11
    report = audit_ui_lexicon_curriculum_parity(REPO_ROOT)
    assert report["passed"] is True, f"Parity audit failed: {report}"
    assert report["undocumented_controls"] == []
    assert generate_inventory(REPO_ROOT) == (
        REPO_ROOT / "docs" / "PORTAL_COMPONENT_INVENTORY.md"
    ).read_text(encoding="utf-8")
