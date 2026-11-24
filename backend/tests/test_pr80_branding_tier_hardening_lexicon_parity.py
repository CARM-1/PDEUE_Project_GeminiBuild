"""PR #80 — Founding Brand Lockup, Cross-Tier Link Hardening, Plain-English Lexicon v0.6 & Parity Audit Tests."""
from __future__ import annotations

from pathlib import Path
import re

from fastapi.testclient import TestClient
import pytest

from app.core.security import create_access_token
from app.domain.lexicon_v05 import (
    BANNED_PLAIN_ENGLISH_JARGON,
    LEXICON_BY_ID,
    LEXICON_TERMS,
    LEXICON_VERSION,
    PLAIN_ENGLISH_REVISION,
    REQUIRED_CANONICAL_TERM_IDS,
)
from app.main import app
from app.portal_discovery import (
    PORTALS,
    audit_ui_lexicon_curriculum_parity,
    generate_inventory,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
API_V1_DIR = REPO_ROOT / "backend" / "app" / "api" / "v1"
STATIC_DIR = REPO_ROOT / "backend" / "app" / "static"
CRESTS_DIR = STATIC_DIR / "assets" / "crests"

ALL_SEVEN_PORTAL_FILES = (
    "dashboard.html",
    "member.html",
    "advisor.html",
    "tech.html",
    "lineage_house.html",
    "community.html",
    "companion.html",
)

ALL_SEVEN_PORTAL_ROUTES = (
    "/dashboard",
    "/member",
    "/advisor",
    "/admin/tech",
    "/lineage/house/1",
    "/community",
    "/companion",
)


def test_crest_assets_and_readme_served_locally_zero_cdn():
    readme = CRESTS_DIR / "README.md"
    assert readme.exists(), "Missing backend/app/static/assets/crests/README.md"
    readme_text = readme.read_text(encoding="utf-8")
    assert "carmichael_crest.svg" in readme_text
    assert "mccormick_crest.svg" in readme_text
    assert "zero code changes" in readme_text.lower()

    with TestClient(app) as client:
        for asset in ("carmichael_crest.svg", "mccormick_crest.svg"):
            path = CRESTS_DIR / asset
            assert path.exists(), f"Missing crest asset {path}"
            resp = client.get(f"/static/assets/crests/{asset}")
            assert resp.status_code == 200
            assert "svg" in resp.headers.get("content-type", "").lower()
            assert "<svg" in resp.text and "</svg>" in resp.text
            assert not re.search(r"""(?:src|href)\s*=\s*["']https?://""", resp.text, re.IGNORECASE)
            assert "<script" not in resp.text.lower()


def test_all_seven_portals_render_founding_brand_lockup_and_colophon():
    with TestClient(app) as client:
        for route in ALL_SEVEN_PORTAL_ROUTES:
            resp = client.get(route)
            assert resp.status_code == 200, f"{route} returned HTTP {resp.status_code}"
            html = resp.text
            assert 'class="brand-lockup"' in html, f"Missing brand-lockup on {route}"
            assert 'href="/community/heritage"' in html, f"Missing /community/heritage link on {route}"
            assert 'data-heritage-target="/community/heritage"' in html, f"Missing data-heritage-target on {route}"
            assert "/static/assets/crests/carmichael_crest.svg" in html, f"Missing Carmichael crest on {route}"
            assert "/static/assets/crests/mccormick_crest.svg" in html, f"Missing McCormick crest on {route}"
            assert "FUTURE · CARMICHAEL — McCORMICK" in html, f"Missing brand title on {route}"
            assert "Generational Love, Harmony, Resilience, and Wealth" in html, f"Missing motto on {route}"
            assert "Powered by CARM Aerotech Corporation" in html, f"Missing CARM Aerotech colophon on {route}"
            assert 'class="colophon-mode-badge"' in html, f"Missing fail-closed mode badge on {route}"


@pytest.mark.parametrize("role", ("F1", "F2-H", "F2-A", "F3"))
def test_non_admin_advisor_strips_all_cross_tier_jump_links_in_dom(role: str):
    with TestClient(app) as client:
        resp = client.get(f"/advisor?role={role}")
        assert resp.status_code == 200
        body = resp.text
        assert 'id="role-switcher"' not in body, f"Non-admin /advisor?role={role} leaked #role-switcher in DOM"
        assert 'data-role="F1"' not in body
        assert 'data-role="F2-H"' not in body
        assert 'data-role="F2-A"' not in body
        assert 'data-role="F3"' not in body

        # Chief Admin via X-Actor-Role, inspector query, or Bearer JWT retains multi-tier inspection switcher
        admin_hdr = client.get(f"/advisor?role={role}", headers={"X-Actor-Role": "CHIEF_ADMIN"})
        assert admin_hdr.status_code == 200
        assert 'id="role-switcher"' in admin_hdr.text
        assert 'data-role="F3"' in admin_hdr.text

        admin_lens = client.get(f"/advisor?role={role}&supervisory=1&inspector=CHIEF_ADMIN")
        assert admin_lens.status_code == 200
        assert 'id="role-switcher"' in admin_lens.text

        ca_jwt = create_access_token({"sub": "USR-founder", "role": "CHIEF_ADMINISTRATOR", "active_hat": "CHIEF_ADMINISTRATOR"})
        admin_jwt = client.get(f"/advisor?role={role}", headers={"Authorization": f"Bearer {ca_jwt}"})
        assert admin_jwt.status_code == 200
        assert 'id="role-switcher"' in admin_jwt.text


@pytest.mark.parametrize("tier", ("T1", "T2", "T2-HOUSEHOLD", "T3"))
def test_non_admin_tech_console_strips_all_cross_tier_jump_links_in_dom(tier: str):
    with TestClient(app) as client:
        resp = client.get(f"/admin/tech?tier={tier}")
        assert resp.status_code == 200
        body = resp.text
        assert 'id="tier-switcher"' not in body, f"Non-admin /admin/tech?tier={tier} leaked #tier-switcher in DOM"
        assert 'data-tier="T1"' not in body
        assert 'data-tier="T2"' not in body
        assert 'data-tier="T2-HOUSEHOLD"' not in body
        assert 'data-tier="T3"' not in body

        # Chief Admin retains multi-tier inspection switcher
        admin_hdr = client.get(f"/admin/tech?tier={tier}", headers={"X-Actor-Role": "CHIEF_ADMIN"})
        assert admin_hdr.status_code == 200
        assert 'id="tier-switcher"' in admin_hdr.text
        assert 'data-tier="T3"' in admin_hdr.text

        admin_lens = client.get(f"/admin/tech?tier={tier}&supervisory=1&inspector=CHIEF_ADMIN")
        assert admin_lens.status_code == 200
        assert 'id="tier-switcher"' in admin_lens.text


def test_backend_guards_enforce_http_403_on_direct_cross_tier_escalation():
    with TestClient(app) as client:
        # Lower-tier Class F cannot load or query higher Class F tier directly
        assert client.get("/advisor?role=F3", headers={"X-Actor-Role": "F1"}).status_code == 403
        assert client.get("/api/v1/portal/advisor/household-tree?role=F2-H", headers={"X-Actor-Role": "F1"}).status_code == 403
        assert client.get("/api/v1/portal/advisor/macro-risk?role=F1").status_code == 403
        assert client.post("/api/v1/portal/advisor/co-sign", json={"request_id": "DIST-104", "actor_role": "F1"}).status_code == 403
        assert client.post("/api/v1/portal/advisor/emergency-halt?role=F2-H", json={"reason": "blocked"}).status_code == 403
        assert client.post("/api/v1/portal/advisor/emergency-resume?role=F3", json={"justification": "blocked"}).status_code == 403

        # Lower-tier Class T cannot load or query higher Class T tier or privileged controls directly
        assert client.get("/admin/tech?tier=T3", headers={"X-Actor-Role": "T1"}).status_code == 403
        assert client.get("/api/v1/portal/tech/telemetry?tier=T3", headers={"X-Actor-Role": "T1"}).status_code == 403
        assert client.post("/api/v1/portal/tech/trigger-daemon?tier=T1").status_code == 403
        assert client.post("/api/v1/portal/tech/ca-override?tier=T2", json={"token": "CA-OVERRIDE-SECRET-DEV"}).status_code == 403
        assert client.post("/api/v1/portal/tech/trigger-daemon?tier=T2-HOUSEHOLD").status_code == 403
        assert client.get(
            "/api/v1/portal/tech/telemetry?tier=T2-HOUSEHOLD&household_id=HOUSEHOLD-BETA",
            headers={"X-Household-ID": "HOUSEHOLD-ALPHA"},
        ).status_code == 403

        # Cross-class isolation remains HTTP 403
        assert client.get("/advisor?role=F2-H", headers={"X-Actor-Role": "T3"}).status_code == 403
        assert client.get("/admin/tech?tier=T3", headers={"X-Actor-Role": "F3"}).status_code == 403


def test_two_layer_plain_english_lexicon_v06_and_dedicated_ifas_entry():
    with TestClient(app) as client:
        resp = client.get("/api/v1/portal/glossary")
        assert resp.status_code == 200
        payload = resp.json()

    assert payload["lexicon_version"] == LEXICON_VERSION == "v0.5"
    assert payload["plain_english_version"] == PLAIN_ENGLISH_REVISION == "v0.6"
    assert payload["two_layer_schema"] is True

    terms_by_id = payload["terms_by_id"]
    assert "ifas" in terms_by_id, "IFAS must have its own dedicated top-level Lexicon entry"
    assert "pay-it-forward-lccf" in terms_by_id, "Pay-it-Forward / LCCF must have its own Lexicon entry"

    for term_id in REQUIRED_CANONICAL_TERM_IDS:
        assert term_id in terms_by_id, f"Missing required canonical term {term_id}"

    for entry in payload["terms"]:
        plain = str(entry.get("plain_english") or "").strip()
        tech = str(entry.get("technical_spec") or "").strip()
        assert len(plain) >= 35, f"{entry['id']} plain_english is too short or empty"
        assert len(tech) >= 45, f"{entry['id']} technical_spec is too short or empty"
        assert plain != tech, f"{entry['id']} plain_english and technical_spec must be distinct layers"
        assert entry["tooltip"] == plain, f"{entry['id']} tooltip must default to plain_english"

        lowered = plain.lower()
        for banned in BANNED_PLAIN_ENGLISH_JARGON:
            assert banned not in lowered, (
                f"Lexicon plain_english for '{entry['id']}' leaked banned jargon token '{banned}'"
            )

    # Search for IFAS resolves dedicated top-level entry
    with TestClient(app) as client:
        ifas_resp = client.get("/api/v1/portal/glossary", params={"q": "IFAS"})
        assert ifas_resp.status_code == 200
        assert "ifas" in ifas_resp.json()["terms_by_id"]


def test_automated_ui_to_lexicon_to_curriculum_parity_ci_gate():
    """CI Gate: Fails automatically if any portal introduces an undocumented control or uncovered acronym/concept."""
    report = audit_ui_lexicon_curriculum_parity(REPO_ROOT)

    assert set(report["portals_scanned"]) == set(PORTALS.keys())
    assert len(report["portals_scanned"]) == 9
    assert report["undocumented_controls"] == [], f"Undocumented controls: {report['undocumented_controls']}"
    assert report["dangling_data_terms"] == [], f"Dangling data-term tooltips: {report['dangling_data_terms']}"
    assert report["jargon_violations"] == [], f"Plain-English jargon violations: {report['jargon_violations']}"
    assert report["uncovered_lexicon_terms"] == [], f"Uncovered Lexicon terms: {report['uncovered_lexicon_terms']}"
    assert report["uncovered_curriculum_terms"] == [], (
        f"Uncovered PDEUE University curriculum terms: {report['uncovered_curriculum_terms']}"
    )
    assert report["passed"] is True

    inventory_md = (REPO_ROOT / "docs" / "PORTAL_COMPONENT_INVENTORY.md").read_text(encoding="utf-8")
    assert inventory_md == generate_inventory(REPO_ROOT), (
        "docs/PORTAL_COMPONENT_INVENTORY.md is out of date; run `PYTHONPATH=backend python3 backend/app/portal_discovery.py`"
    )
    assert "Undocumented controls:** 0" in inventory_md
    assert "Uncovered canonical acronyms/concepts (Lexicon):** 0" in inventory_md
    assert "Uncovered canonical acronyms/concepts (PDEUE University):** 0" in inventory_md
    assert "Automated Parity Gate:** **PASS**" in inventory_md


def test_all_seven_html_templates_synced_byte_for_byte_and_hygiene_clean():
    cdn_re = re.compile(r"""<(?:script|link)[^>]+(?:src|href)=["']https?://""", re.IGNORECASE)
    dialog_re = re.compile(r"""\b(?:alert|confirm|prompt)\s*\(""")

    for filename in ALL_SEVEN_PORTAL_FILES:
        api_path = API_V1_DIR / filename
        static_path = STATIC_DIR / filename
        assert api_path.exists(), f"Missing {api_path}"
        assert static_path.exists(), f"Missing {static_path}"
        api_text = api_path.read_text(encoding="utf-8")
        static_text = static_path.read_text(encoding="utf-8")
        assert api_text == static_text, f"Byte-for-byte drift detected between {api_path} and {static_path}"
        assert not cdn_re.search(api_text), f"External CDN tag detected in {filename}"
        assert not dialog_re.search(api_text), f"Native browser dialog detected in {filename}"
