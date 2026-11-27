"""PR #83 — Two-Scale Heraldic Crest System, 3-Row Header Alignment, Ask-Tutor Clear Control & PDEUE University Polish."""
from __future__ import annotations

from pathlib import Path
import re

from fastapi.testclient import TestClient

from app.domain.lexicon_v05 import LEXICON_BY_ID
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
CRESTS_DIR = STATIC_DIR / "assets" / "crests"

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


def _extract_js_function(markup: str, fn_name: str) -> str:
    match = re.search(rf"function\s+{re.escape(fn_name)}\s*\([^)]*\)\s*\{{", markup)
    assert match, f"Missing JS function {fn_name}"
    start = match.end()
    depth = 1
    idx = start
    while idx < len(markup) and depth > 0:
        if markup[idx] == "{":
            depth += 1
        elif markup[idx] == "}":
            depth -= 1
        idx += 1
    return markup[start : idx - 1]


def test_two_scale_heraldic_crest_assets_and_11_bordure_differenced_svgs():
    readme = (CRESTS_DIR / "README.md").read_text(encoding="utf-8")
    for token in (
        "carmichael_crest.svg",
        "mccormick_crest.svg",
        "carmichael_achievement.svg",
        "mccormick_achievement.svg",
        "house_02_mccormick_bordure.svg",
        "house_12_mccormick_bordure.svg",
        "bordure differencing",
        "zero code changes",
    ):
        assert token in readme.lower(), f"Missing '{token}' in crests README.md"

    expected_svgs = [
        "carmichael_crest.svg",
        "mccormick_crest.svg",
        "carmichael_achievement.svg",
        "mccormick_achievement.svg",
        *(f"house_{hid:02d}_mccormick_bordure.svg" for hid in range(2, 13)),
    ]

    import xml.etree.ElementTree as ET

    with TestClient(app) as client:
        for asset in expected_svgs:
            path = CRESTS_DIR / asset
            assert path.exists(), f"Missing crest asset {path}"
            resp = client.get(f"/static/assets/crests/{asset}")
            assert resp.status_code == 200, f"Failed serving {asset}"
            assert "svg" in resp.headers.get("content-type", "").lower()
            assert "<svg" in resp.text and "</svg>" in resp.text
            assert "<script" not in resp.text.lower()
            assert not re.search(r"""(?:src|href)\s*=\s*["']https?://""", resp.text, re.IGNORECASE)
            ET.fromstring(resp.text)

    # Verify Carmichael achievement depicts key heraldic elements
    carm_ach = (CRESTS_DIR / "carmichael_achievement.svg").read_text(encoding="utf-8")
    for expected in ("IEHOVA SEMPER VIGILANS", "sacGauntletLightningOliveCrest", "knightSupporter", "crownedLionSupporter", "scottishThistles", "heritageAccentRibbon"):
        assert expected in carm_ach, f"Missing '{expected}' in carmichael_achievement.svg"

    # Verify McCormick achievement depicts three blue eagles, fess dancette, black engrailed border & twin golden stags
    mcc_ach = (CRESTS_DIR / "mccormick_achievement.svg").read_text(encoding="utf-8")
    for expected in ("SINE TIMORE", "dexterStag", "sinisterStag", "achBlueEagle"):
        assert expected in mcc_ach, f"Missing '{expected}' in mccormick_achievement.svg"


def test_heritage_service_12_houses_carmichael_eldest_daughter_and_11_bordure_mccormick():
    with TestClient(app) as client:
        gallery = client.get("/api/v1/portal/community/heritage").json()

        assert gallery["total_houses"] == 12
        assert len(gallery["houses"]) == 12
        assert len(gallery["founding_surnames"]) == 2
        assert gallery["allied_surname_count"] >= 28

        two_scale = gallery["two_scale_heraldry"]
        assert two_scale["emblem_assets"]["carmichael"] == "/static/assets/crests/carmichael_crest.jpg"
        assert two_scale["emblem_assets"]["mccormick"] == "/static/assets/crests/mccormick_crest.jpg"
        assert two_scale["achievement_assets"]["carmichael"] == "/static/assets/crests/carmichael_achievement.jpg"
        assert two_scale["achievement_assets"]["mccormick"] == "/static/assets/crests/mccormick_achievement.jpg"
        assert "eldest mccormick daughter" in two_scale["house_1_descent"].lower()
        assert two_scale["bordure_differenced_house_count"] == 11
        assert two_scale["bordure_differenced_house_ids"] == list(range(2, 13))

        houses_by_id = {h["house_id"]: h for h in gallery["houses"]}
        h1 = houses_by_id[1]
        assert "eldest mccormick daughter" in h1["lineage_descent"].lower()
        assert h1["achievement_asset_path"] == "/static/assets/crests/carmichael_achievement.jpg"
        assert h1["bordure_differencing"]["is_bordure_differenced"] is False

        seen_bordure_crests = set()
        for hid in range(2, 13):
            h = houses_by_id[hid]
            assert h["bordure_differencing"]["is_bordure_differenced"] is True
            assert h["bordure_differencing"]["border_style"]
            assert h["bordure_differencing"]["tincture"]
            expected_path = f"/static/assets/crests/house_{hid:02d}_mccormick_bordure.jpg"
            assert h["emblem_asset_path"] == expected_path
            seen_bordure_crests.add(expected_path)
        assert len(seen_bordure_crests) == 11

        # /community/heritage and /home display full achievements alongside compact emblems
        heritage_html = client.get("/community/heritage").text
        assert "/static/assets/crests/carmichael_achievement.jpg" in heritage_html
        assert "/static/assets/crests/mccormick_achievement.jpg" in heritage_html
        assert "Bordure Differencing" in heritage_html

        home_html = client.get("/home").text
        assert "/static/assets/crests/carmichael_achievement.jpg" in home_html
        assert "/static/assets/crests/mccormick_achievement.jpg" in home_html

        # House detail page shows heraldic blazon and lineage descent
        h3_html = client.get("/community/heritage/house/3").text
        assert "Heraldic Blazon" in h3_html
        assert "house_03_mccormick_bordure.jpg" in h3_html


def test_community_ask_tutor_clear_button_is_client_only_and_site_wide_clear_controls_verified():
    with TestClient(app) as client:
        community_html = client.get("/community").text
        assert 'id="clearCommunityTutorBtn"' in community_html
        assert 'type="button"' in community_html
        assert 'onclick="clearCommunityTutor()"' in community_html

        handler = _extract_js_function(community_html, "clearCommunityTutor")
        assert "fetch(" not in handler, "clearCommunityTutor must never issue a network call"
        assert "COMMUNITY_TUTOR_GREETING" in handler
        assert ".value=''" in handler
        assert ".focus()" in handler

        # Verify /member, /dashboard, /advisor, /admin/tech all retain client-only Clear buttons
        for route, btn_id, fn_name in (
            ("/member", "clearTutorBtn", "clearTutorAnswer"),
            ("/dashboard", "clearCopilotBtn", "clearCopilotChat"),
            ("/advisor", "clearAdvisorCopilotBtn", "clearAdvisorCopilot"),
            ("/admin/tech", "clearTechCopilotBtn", "clearTechCopilot"),
        ):
            html = client.get(route).text
            assert f'id="{btn_id}"' in html, f"Missing {btn_id} on {route}"
            body = _extract_js_function(html, fn_name)
            assert "fetch(" not in body, f"{fn_name} on {route} must be client-only"
            assert ".focus()" in body, f"{fn_name} on {route} must restore keyboard focus"


def test_three_row_header_structure_and_university_pill_consistency_across_all_nine_portals():
    with TestClient(app) as client:
        for route in ALL_NINE_ROUTES:
            resp = client.get(route)
            assert resp.status_code == 200, f"{route} returned HTTP {resp.status_code}"
            html = resp.text
            assert 'class="portal-header-shell' in html, f"Missing 3-row header shell on {route}"
            assert 'class="portal-header-row1"' in html, f"Missing Row 1 on {route}"
            assert 'class="portal-header-row2"' in html, f"Missing Row 2 on {route}"
            assert 'class="portal-header-row3' in html, f"Missing Row 3 on {route}"
            assert 'id="navCompanionLink"' in html, f"Missing PDEUE University pill link on {route}"
            assert "🎓 PDEUE University" in html, f"Missing PDEUE University pill label on {route}"

            # Row 1 holds both brand-lockup and textScaleGroup (and Back to Home on non-home portals)
            row1_start = html.find('class="portal-header-row1"')
            row2_start = html.find('class="portal-header-row2"')
            assert 0 <= row1_start < row2_start
            row1_slice = html[row1_start:row2_start]
            assert 'class="brand-lockup"' in row1_slice
            assert 'id="textScaleGroup"' in row1_slice
            if route != "/home":
                assert 'id="backToHomeBtn"' in row1_slice, f"Back to Home must sit in Row 1 on {route}"

    # Verify CSS styles campus-link as a cohesive pill button (zero underline)
    a11y_css = (STATIC_DIR / "css" / "senior_a11y.css").read_text(encoding="utf-8")
    assert "a.nav-link.campus-link" in a11y_css
    assert "border-radius: 999px" in a11y_css
    assert "text-decoration: none !important" in a11y_css


def test_companion_university_plain_english_guided_start_and_manual_cards_contract():
    with TestClient(app) as client:
        html = client.get("/companion").text
        assert html.count("What This Means in Plain English") >= 6
        for manual in (
            "USER_QUICKSTART.md",
            "CLASS_F_FINANCIAL_MANUAL.md",
            "CLASS_T_TECHNICAL_MANUAL.md",
            "CHIEF_ADMIN_RUNBOOK.md",
        ):
            assert f'data-manual-load="{manual}"' in html, f"Missing manual card button for {manual}"

        assert 'id="manual-reader-panel"' in html
        assert 'id="closeManualReaderBtn"' in html
        assert 'id="narrationSlideCard"' in html
        assert 'id="prevBeatBtn"' in html and 'id="nextBeatBtn"' in html
        assert 'id="prevChapterBtn"' in html and 'id="nextChapterBtn"' in html
        assert 'id="voiceSelect"' in html
        # Opening /companion without ?chapter=6 must not jump to chapter 6
        assert "urlParams.get('chapter')==='6'" in html


def test_pr83_nine_portal_parity_gate_lexicon_and_byte_for_byte_sync():
    assert "bordure-differencing" in LEXICON_BY_ID
    assert "guided-tour" in LEXICON_BY_ID

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

    cdn_re = re.compile(r"""<(?:script|link)[^>]+(?:src|href)=["']https?://""", re.IGNORECASE)
    dialog_re = re.compile(r"""\b(?:alert|confirm|prompt)\s*\(""")
    for filename in ALL_NINE_TEMPLATES:
        api_text = (API_V1_DIR / filename).read_text(encoding="utf-8")
        static_text = (STATIC_DIR / filename).read_text(encoding="utf-8")
        assert api_text == static_text, f"Byte-for-byte drift detected in {filename}"
        assert not cdn_re.search(api_text), f"External CDN tag detected in {filename}"
        assert not dialog_re.search(api_text), f"Native browser dialog detected in {filename}"
