"""PR #82 — Central Family Home Hub, Senior UX, 4-Domain Air-Gap, Hall of Arms & Notification Gateway Tests."""
from __future__ import annotations

import ast
from pathlib import Path
import re
import sqlite3

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest

from app.core.security import create_access_token
from app.domain.authority_tiers import get_governance_audit_log
from app.domain.notification_gateway import (
    MockNotificationClient,
    NotificationGateway,
    NotificationMessage,
    R12NotificationPayloadError,
    SESEmailNotificationClient,
    SNSOrTwilioSMSNotificationClient,
    sanitize_notification_text,
)
from app.domain.plane_routing import get_plane_config
from app.main import app
from app.portal_discovery import (
    PORTALS,
    audit_ui_lexicon_curriculum_parity,
    generate_inventory,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
API_V1_DIR = BACKEND_DIR / "app" / "api" / "v1"
STATIC_DIR = BACKEND_DIR / "app" / "static"

ALL_NINE_TEMPLATES = (
    "home.html",
    "dashboard.html",
    "member.html",
    "advisor.html",
    "tech.html",
    "lineage_house.html",
    "community.html",
    "heritage.html",
    "companion.html",
)

ALL_NINE_ROUTES = (
    "/home",
    "/dashboard",
    "/member",
    "/advisor",
    "/admin/tech",
    "/lineage/house/1",
    "/community",
    "/community/heritage",
    "/companion",
)

NON_HOME_ROUTES = tuple(r for r in ALL_NINE_ROUTES if r != "/home")


def test_root_redirects_to_family_home_hub():
    with TestClient(app) as client:
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/home"


def test_home_hub_renders_four_doorways_and_strips_admin_doors_for_class_m():
    with TestClient(app) as client:
        resp = client.get("/home")
        assert resp.status_code == 200
        body = resp.text
        assert "Welcome to the Carmichael / McCormick Family Hub" in body
        assert "Family Social Space — No Financial Data" in body
        assert 'id="doorwayMyAccount"' in body and 'href="/member"' in body
        assert 'id="doorwayFamilyHearth"' in body and 'href="/community"' in body
        assert 'id="doorwayHallOfArms"' in body and 'href="/community/heritage"' in body
        assert 'id="doorwayUniversity"' in body and 'href="/companion"' in body

        # Standard Class M / anonymous callers NEVER see privileged 5th door in DOM
        assert 'id="roleDoorwayCard"' not in body
        for forbidden in ('href="/dashboard"', 'href="/advisor"', 'href="/admin/tech"', 'href="/lineage/house'):
            assert forbidden not in body, f"Leaked privileged link {forbidden} on Class M /home"

        # Explicit Class M header still receives zero privileged doors
        resp_m = client.get("/home", headers={"X-Actor-Role": "MEMBER_USER"})
        assert resp_m.status_code == 200
        assert 'id="roleDoorwayCard"' not in resp_m.text


@pytest.mark.parametrize(
    "role,expected_href,extra_headers",
    [
        ("F1", "/advisor?role=F1", {}),
        ("F2-H", "/advisor?role=F2-H", {}),
        ("F2-A", "/advisor?role=F2-A", {}),
        ("F3", "/advisor?role=F3", {}),
        ("H1", "/lineage/house/4?role=H1", {"X-House-ID": "4"}),
        ("H2", "/lineage/house/7?role=H2", {"X-House-ID": "7"}),
        ("HOUSE_GENEALOGIST", "/community/heritage#genealogist-desk", {}),
        ("T1", "/admin/tech?tier=T1", {}),
        ("T2", "/admin/tech?tier=T2", {}),
        ("T3", "/admin/tech?tier=T3", {}),
        ("CHIEF_ADMIN", "/dashboard", {}),
    ],
)
def test_home_hub_renders_strictly_scoped_fifth_doorway_card_for_authorized_hats(
    role: str,
    expected_href: str,
    extra_headers: dict[str, str],
):
    headers = {"X-Actor-Role": role, **extra_headers}
    with TestClient(app) as client:
        resp = client.get("/home", headers=headers)
        assert resp.status_code == 200
        body = resp.text
        assert body.count('id="roleDoorwayCard"') == 1
        assert f'href="{expected_href}"' in body


def test_four_domain_plane_routing_relative_default_and_production_cutover(monkeypatch: pytest.MonkeyPatch):
    for var in (
        "FAMILY_HUB_BASE_URL",
        "UNIVERSITY_BASE_URL",
        "PDEUE_VAULT_BASE_URL",
        "PDEUE_ADMIN_BASE_URL",
        "IFAS_ACCOUNTING_BASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)

    with TestClient(app) as client:
        rel_resp = client.get("/api/v1/portal/planes")
        assert rel_resp.status_code == 200
        rel = rel_resp.json()
        assert rel["routing_mode"] == "relative_single_host"
        assert rel["doorways"]["home"] == "/home"
        assert rel["doorways"]["community"] == "/community"
        assert rel["doorways"]["heritage"] == "/community/heritage"
        assert rel["doorways"]["companion"] == "/companion"
        assert rel["doorways"]["member"] == "/member"
        assert rel["doorways"]["dashboard"] == "/dashboard"
        assert rel["doorways"]["ifas"] == ""
        assert rel["doorways"]["ifas_configured"] is False

        # Populate all 5 air-gapped domain env vars -> zero-rewrite cutover
        monkeypatch.setenv("FAMILY_HUB_BASE_URL", "https://narratixai.org")
        monkeypatch.setenv("UNIVERSITY_BASE_URL", "https://narratixai.info")
        monkeypatch.setenv("PDEUE_VAULT_BASE_URL", "https://vault.narratixai.io")
        monkeypatch.setenv("PDEUE_ADMIN_BASE_URL", "https://admin.narratixai.io")
        monkeypatch.setenv("IFAS_ACCOUNTING_BASE_URL", "https://narratixai.net")

        prod_resp = client.get("/api/v1/portal/planes")
        assert prod_resp.status_code == 200
        prod = prod_resp.json()
        assert prod["routing_mode"] == "multi_domain_air_gapped"
        assert prod["doorways"]["home"] == "https://narratixai.org/home"
        assert prod["doorways"]["community"] == "https://narratixai.org/community"
        assert prod["doorways"]["heritage"] == "https://narratixai.org/community/heritage"
        assert prod["doorways"]["companion"] == "https://narratixai.info/companion"
        assert prod["doorways"]["member"] == "https://vault.narratixai.io/member"
        assert prod["doorways"]["advisor"] == "https://vault.narratixai.io/advisor"
        assert prod["doorways"]["dashboard"] == "https://admin.narratixai.io/dashboard"
        assert prod["doorways"]["tech"] == "https://admin.narratixai.io/admin/tech"
        assert prod["doorways"]["ifas"] == "https://narratixai.net"
        assert prod["doorways"]["ifas_configured"] is True

        # Home HTML reflects full cross-domain URLs dynamically
        home_prod = client.get("/home").text
        assert 'href="https://vault.narratixai.io/member"' in home_prod
        assert 'href="https://narratixai.org/community"' in home_prod
        assert 'href="https://narratixai.org/community/heritage"' in home_prod
        assert 'href="https://narratixai.info/companion"' in home_prod

    # Prohibited corporate domains are rejected fail-closed
    monkeypatch.setenv("FAMILY_HUB_BASE_URL", "https://carm-aerotech.com")
    with pytest.raises(ValueError, match="Prohibited domain"):
        get_plane_config()
    monkeypatch.setenv("FAMILY_HUB_BASE_URL", "https://narratixai.com")
    with pytest.raises(ValueError, match="Prohibited domain"):
        get_plane_config()


def test_social_plane_firewall_zero_financial_imports_and_zero_balance_data():
    """Verify ZERO imports of trading/ledger/credential modules in any PR #82 social/heritage/comms file."""
    social_modules = (
        BACKEND_DIR / "app" / "domain" / "plane_routing.py",
        BACKEND_DIR / "app" / "domain" / "notification_gateway.py",
        BACKEND_DIR / "app" / "domain" / "heritage_community_service.py",
        BACKEND_DIR / "app" / "api" / "v1" / "social_plane_router.py",
    )
    forbidden_symbols = (
        "CapitalLedger",
        "TwoTierRiskEnvelope",
        "AutonomousScanWorker",
        "CredentialBroker",
        "venue_adapters",
        "capital_ledger",
        "two_tier_risk",
        "scan_worker",
        "credential_broker",
    )
    for mod_path in social_modules:
        src = mod_path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(mod_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for bad in forbidden_symbols:
                        assert bad not in alias.name, f"Forbidden import {alias.name} in {mod_path}"
            elif isinstance(node, ast.ImportFrom):
                mod_name = node.module or ""
                for bad in forbidden_symbols:
                    assert bad not in mod_name, f"Forbidden import from {mod_name} in {mod_path}"
                for alias in node.names:
                    for bad in forbidden_symbols:
                        assert bad != alias.name, f"Forbidden symbol import {alias.name} in {mod_path}"

    # Verify HTTP responses on social/heritage plane contain zero account balances or bank refs
    with TestClient(app) as client:
        for path in (
            "/home",
            "/community",
            "/community/heritage",
            "/api/v1/portal/community/feed",
            "/api/v1/portal/community/heritage",
            "/api/v1/portal/community/notifications",
        ):
            resp = client.get(path)
            assert resp.status_code == 200
            lowered = resp.text.lower()
            for leaked in ("total_equity", "cash_cents", "capital_ledger", "scma-founder", "scma-eleanor", "ext-ref-"):
                assert leaked not in lowered, f"Financial artifact '{leaked}' leaked on {path}"


def test_alembic_006_migration_idempotent_upgrade_and_downgrade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_file = tmp_path / "alembic_006_test.db"
    db_url = f"sqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(cfg, "head")
    # Re-running upgrade head is idempotent
    command.upgrade(cfg, "head")

    with sqlite3.connect(db_file) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "heritage_house_profiles" in tables
    assert "heritage_surname_records" in tables
    assert "community_notifications" in tables

    # Downgrade one step removes 006 tables cleanly, then re-upgrade restores them
    command.downgrade(cfg, "005_add_role_provisioning_custody_delegation")
    with sqlite3.connect(db_file) as conn:
        tables_after_down = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "heritage_house_profiles" not in tables_after_down
    assert "heritage_surname_records" not in tables_after_down
    assert "community_notifications" not in tables_after_down

    command.upgrade(cfg, "head")
    with sqlite3.connect(db_file) as conn:
        tables_reup = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "heritage_house_profiles" in tables_reup
    assert "heritage_surname_records" in tables_reup
    assert "community_notifications" in tables_reup


def test_hall_of_arms_12_houses_28_plus_surnames_and_history_pages():
    with TestClient(app) as client:
        page = client.get("/community/heritage")
        assert page.status_code == 200
        assert "Hall of Arms" in page.text
        assert "Carmichael" in page.text and "McCormick" in page.text

        gallery = client.get("/api/v1/portal/community/heritage").json()
        assert gallery["total_houses"] == 12
        assert len(gallery["houses"]) == 12
        assert len(gallery["founding_surnames"]) == 2
        assert gallery["allied_surname_count"] >= 28
        assert len(gallery["allied_surnames"]) >= 28

        # Search and house filter work accurately
        filtered = client.get("/api/v1/portal/community/heritage", params={"q": "Vance", "house_id": 1}).json()
        assert any(s["surname"] == "Vance" for s in filtered["allied_surnames"])

        # Individual House history pages (1..12) and surname history pages return HTTP 200
        for hid in (1, 2, 7, 12):
            h_resp = client.get(f"/community/heritage/house/{hid}")
            assert h_resp.status_code == 200
            assert "← Back to Hall of Arms" in h_resp.text
            assert "← Back to Home" in h_resp.text

        for slug in ("carmichael", "mccormick", "vance", "sinclair"):
            s_resp = client.get(f"/community/heritage/surname/{slug}")
            assert s_resp.status_code == 200
            assert "← Back to Hall of Arms" in s_resp.text


def test_house_genealogist_scoped_writes_403_isolation_xss_and_audit():
    with TestClient(app) as client:
        # 1. Assign a HOUSE_GENEALOGIST specifically to House 3 via PR #81 Role Provisioning API
        assign_resp = client.post(
            "/api/v1/governance/roles/assign",
            headers={"X-Actor-Role": "CHIEF_ADMIN", "X-Actor-ID": "USR-founder_ch-C8575D7E"},
            json={
                "member_id": "MEM-GENEALOGIST-H3",
                "role_token": "HOUSE_GENEALOGIST",
                "house_id": 3,
                "reason": "PR #82 scoped Hall of Arms genealogist for House 03",
            },
        )
        assert assign_resp.status_code in (200, 201), assign_resp.text

        gen_jwt = create_access_token(
            {"sub": "MEM-GENEALOGIST-H3", "role": "HOUSE_GENEALOGIST", "active_hat": "HOUSE_GENEALOGIST", "house_id": 3}
        )
        gen_headers = {"Authorization": f"Bearer {gen_jwt}"}

        # 2. Genealogist of House 3 CAN update House 3 with XSS sanitization
        ok_house = client.post(
            "/api/v1/portal/community/heritage/house/3",
            headers=gen_headers,
            json={
                "motto": "Warmth Kept <script>alert(1)</script> Forever",
                "history_body": "House 03 reunion chronicle <img src=x onerror=alert(2)> updated by genealogist.",
            },
        )
        assert ok_house.status_code == 200, ok_house.text
        updated = ok_house.json()
        assert "<script" not in updated["motto"]
        assert "<img" not in updated["history_body"]
        assert "House 03 reunion chronicle" in updated["history_body"]

        # 3. Genealogist of House 3 CAN add an allied surname under House 3
        ok_surname = client.post(
            "/api/v1/portal/community/heritage/surname",
            headers=gen_headers,
            json={
                "surname": "MacAllister",
                "house_id": 3,
                "origin_summary": "Allied Lineage · Highland storytellers",
                "history_body": "Welcomed into House 03 with <b>bold</b> family traditions.",
            },
        )
        assert ok_surname.status_code == 200, ok_surname.text
        assert ok_surname.json()["slug"] == "macallister"
        assert "<b>" not in ok_surname.json()["history_body"]

        # 4. Genealogist of House 3 CANNOT edit House 4 (HTTP 403)
        denied_house = client.post(
            "/api/v1/portal/community/heritage/house/4",
            headers=gen_headers,
            json={"history_body": "Unauthorized cross-house edit"},
        )
        assert denied_house.status_code == 403

        # 5. Genealogist of House 3 CANNOT add/edit a surname under House 4 (HTTP 403)
        denied_surname = client.post(
            "/api/v1/portal/community/heritage/surname",
            headers=gen_headers,
            json={
                "surname": "CrossHouseAttempt",
                "house_id": 4,
                "origin_summary": "Blocked",
                "history_body": "Blocked cross-house write",
            },
        )
        assert denied_surname.status_code == 403

        # 6. Non-genealogists (Class M, F2-H, T3, anonymous) get HTTP 403
        for bad_headers in (
            {},
            {"X-Actor-Role": "MEMBER_USER", "X-Actor-ID": "USR-julian_va-A1F98B21"},
            {"X-Actor-Role": "F2-H", "X-Actor-ID": "USR-eleanor_va-B2B31C9E"},
            {"X-Actor-Role": "T3", "X-Actor-ID": "T3_CTO"},
        ):
            r = client.post(
                "/api/v1/portal/community/heritage/house/3",
                headers=bad_headers,
                json={"history_body": "Should be denied"},
            )
            assert r.status_code == 403

        # 7. GovernanceAuditLog captured both allowed and denied heritage events
        audit_events = get_governance_audit_log().list_events(limit=50)
        event_types = {e["event_type"] for e in audit_events}
        assert "HERITAGE_HOUSE_UPDATED" in event_types
        assert "HERITAGE_SURNAME_UPSERTED" in event_types
        assert "HERITAGE_EDIT_DENIED" in event_types


def test_notification_gateway_mock_default_fail_closed_and_r12_sanitizer(monkeypatch: pytest.MonkeyPatch):
    # Ensure no live provider keys exist -> fail-closed Mock fallback
    for env_key in (
        "PDEUE_SES_ACCESS_KEY_ID",
        "PDEUE_SES_SECRET_ACCESS_KEY",
        "PDEUE_SES_SENDER_EMAIL",
        "PDEUE_TWILIO_ACCOUNT_SID",
        "PDEUE_TWILIO_AUTH_TOKEN",
        "PDEUE_TWILIO_FROM_NUMBER",
        "PDEUE_SNS_ACCESS_KEY_ID",
        "PDEUE_SNS_SECRET_ACCESS_KEY",
        "PDEUE_SNS_REGION",
    ):
        monkeypatch.delenv(env_key, raising=False)

    mock_client = MockNotificationClient(channel="in_app")
    ses_client = SESEmailNotificationClient()
    sms_client = SNSOrTwilioSMSNotificationClient()
    assert ses_client.is_configured() is False
    assert sms_client.is_configured() is False

    gateway = NotificationGateway(
        in_app_client=mock_client,
        email_client=ses_client,
        sms_client=sms_client,
    )
    msg = NotificationMessage(
        notification_id="NOTIF-TEST-01",
        title="Alert for SCMA-ELEANOR_-B2B31C9E balance $1,250.00",
        message="Routing 123456789 EXT-REF-IFAS-****4321 review needed in PDEUE.",
    )
    receipts = gateway.dispatch(msg, channels=["in_app", "email", "sms"])
    assert len(receipts) == 3
    for receipt in receipts:
        assert receipt.r12_sanitized is True
        assert "$1,250.00" not in receipt.safe_title
        assert "SCMA-ELEANOR" not in receipt.safe_title
        assert "123456789" not in receipt.safe_message
        assert "EXT-REF-" not in receipt.safe_message
        assert "DOLLAR_AMOUNT" in receipt.redactions_applied
        assert "SCMA_ID" in receipt.redactions_applied
    # Email & SMS failed closed to MockNotificationClient
    assert receipts[1].fallback_used is True and "fail-closed" in receipts[1].provider.lower()
    assert receipts[2].fallback_used is True and "fail-closed" in receipts[2].provider.lower()

    # Strict mode raises R12NotificationPayloadError
    with pytest.raises(R12NotificationPayloadError):
        sanitize_notification_text("Your balance is $123.45 in SCMA-MEM-001", strict_reject=True)

    # HTTP Broadcast RBAC & R-12 scrubbing
    with TestClient(app) as client:
        denied = client.post(
            "/api/v1/portal/community/notifications/broadcast",
            headers={"X-Actor-Role": "MEMBER_USER"},
            json={"title": "Test", "message": "Should fail"},
        )
        assert denied.status_code == 403

        ok = client.post(
            "/api/v1/portal/community/notifications/broadcast",
            headers={"X-Actor-Role": "CHIEF_ADMIN", "X-Actor-ID": "USR-founder_ch-C8575D7E"},
            json={
                "title": "Family Reunion Reminder $500.00",
                "message": "Check SCMA-ELEANOR_-B2B31C9E? No — new family announcement posted in Lineage Hearth!",
                "category": "REUNION",
                "channels": ["in_app", "email", "sms"],
            },
        )
        assert ok.status_code == 201, ok.text
        data = ok.json()
        assert data["r12_sanitized"] is True
        assert "$500.00" not in data["title"]
        assert "SCMA-ELEANOR" not in data["message"]

        listing = client.get("/api/v1/portal/community/notifications").json()
        assert listing["count"] >= 1
        assert "$500.00" not in str(listing)
        assert "SCMA-ELEANOR" not in str(listing)


def test_site_wide_senior_accessibility_sync_and_9_portal_parity_gate():
    cdn_re = re.compile(r"""<(?:script|link)[^>]+(?:src|href)=["']https?://""", re.IGNORECASE)
    dialog_re = re.compile(r"""\b(?:alert|confirm|prompt)\s*\(""")

    for filename in ALL_NINE_TEMPLATES:
        api_path = API_V1_DIR / filename
        static_path = STATIC_DIR / filename
        assert api_path.exists() and static_path.exists()
        api_text = api_path.read_text(encoding="utf-8")
        static_text = static_path.read_text(encoding="utf-8")
        assert api_text == static_text, f"Byte-for-byte drift detected for {filename}"
        assert not cdn_re.search(api_text), f"External CDN tag detected in {filename}"
        assert not dialog_re.search(api_text), f"Native browser dialog detected in {filename}"

    with TestClient(app) as client:
        for route in ALL_NINE_ROUTES:
            resp = client.get(route)
            assert resp.status_code == 200, f"{route} returned HTTP {resp.status_code}"
            html_body = resp.text
            assert 'id="textScaleGroup"' in html_body, f"Missing A/A+/A++ #textScaleGroup on {route}"
            assert 'data-scale="standard"' in html_body
            assert 'data-scale="large"' in html_body
            assert 'data-scale="xlarge"' in html_body
            assert 'href="/community/heritage"' in html_body, f"Brand lockup must target /community/heritage on {route}"
            assert "/static/css/senior_a11y.css" in html_body
            assert "PDEUESeniorA11y" in html_body

        for route in NON_HOME_ROUTES:
            html_body = client.get(route).text
            assert 'id="backToHomeBtn"' in html_body, f"Missing ← Back to Home button on {route}"
            assert "← Back to Home" in html_body

        # /member exposes Banking & Tax Statements (IFAS) handoff button
        member_html = client.get("/member").text
        assert 'id="ifasHandoffBtn"' in member_html
        assert "Banking &amp; Tax Statements (IFAS)" in member_html

    # Automated 9-portal UI-to-Lexicon-to-Curriculum parity gate
    report = audit_ui_lexicon_curriculum_parity(REPO_ROOT)
    assert len(report["portals_scanned"]) >= 9
    assert set(report["portals_scanned"]) == set(PORTALS.keys())
    assert report["undocumented_controls"] == []
    assert report["dangling_data_terms"] == []
    assert report["jargon_violations"] == []
    assert report["uncovered_lexicon_terms"] == []
    assert report["uncovered_curriculum_terms"] == []
    assert report["passed"] is True

    inventory_md = (REPO_ROOT / "docs" / "PORTAL_COMPONENT_INVENTORY.md").read_text(encoding="utf-8")
    assert inventory_md == generate_inventory(REPO_ROOT)
