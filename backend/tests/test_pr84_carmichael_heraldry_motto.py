"""PR #84 — Finalized House of Carmichael Coat of Arms (IEHOVA SEMPER VIGILANS), SAC Heraldry & Raster Drop-In Tests."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import HeritageHouseProfileModel, HeritageSurnameRecordModel
from app.db.session import Base
import app.domain.heritage_community_service as heritage_svc_mod
from app.domain.heritage_community_service import (
    HOUSE_01_OFFICIAL_MOTTO,
    HOUSE_HERALDRY_META,
    SEEDED_HOUSES,
    SEEDED_SURNAMES,
    HeritageCommunityService,
    resolve_heraldic_asset_path,
)
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


def test_house_01_official_motto_and_sac_symbolism_across_metadata_api_and_html():
    assert HOUSE_01_OFFICIAL_MOTTO == "IEHOVA SEMPER VIGILANS"

    # Service seed metadata checks
    h1_seed = next(h for h in SEEDED_HOUSES if h["house_id"] == 1)
    assert h1_seed["motto"] == "IEHOVA SEMPER VIGILANS"
    assert "toujours prest" not in h1_seed["motto"].lower()
    assert "Strategic Air Command" in h1_seed["history_body"]

    carm_surname = next(s for s in SEEDED_SURNAMES if s[0] == "Carmichael")
    assert "IEHOVA SEMPER VIGILANS" in carm_surname[3]
    assert "Strategic Air Command" in carm_surname[4]

    h1_meta = HOUSE_HERALDRY_META[1]
    assert h1_meta["motto"] == "IEHOVA SEMPER VIGILANS"
    blazon = h1_meta["blazon_note"]
    for phrase in (
        "IEHOVA SEMPER VIGILANS",
        "Strategic Air Command (SAC)",
        "lightning bolts",
        "olive branch",
        "jewelled gold coronet",
        "African American knight",
        "visor raised",
        "Barbary lion",
        "purple thistles",
        "braided gold-and-green",
    ):
        assert phrase.lower() in blazon.lower(), f"Missing '{phrase}' in House 01 blazon_note"
    assert "toujours prest" not in blazon.lower()

    # Live HTTP API & HTML checks
    with TestClient(app) as client:
        gallery = client.get("/api/v1/portal/community/heritage").json()
        assert gallery["two_scale_heraldry"]["house_1_official_motto"] == "IEHOVA SEMPER VIGILANS"
        h1_api = next(h for h in gallery["houses"] if h["house_id"] == 1)
        assert h1_api["motto"] == "IEHOVA SEMPER VIGILANS"
        assert h1_api["heraldic_symbolism"]["motto"] == "IEHOVA SEMPER VIGILANS"
        assert "Strategic Air Command" in h1_api["heraldic_symbolism"]["crest"]

        h1_detail = client.get("/api/v1/portal/community/heritage/house/1").json()
        assert h1_detail["motto"] == "IEHOVA SEMPER VIGILANS"
        assert "toujours prest" not in json.dumps(h1_detail).lower()

        carm_api = client.get("/api/v1/portal/community/heritage/surname/carmichael").json()
        assert carm_api["house_motto"] == "IEHOVA SEMPER VIGILANS"
        assert "IEHOVA SEMPER VIGILANS" in carm_api["origin_summary"]

        for route in ("/home", "/community/heritage", "/community/heritage/house/1", "/community/heritage/surname/carmichael"):
            resp = client.get(route)
            assert resp.status_code == 200, f"{route} returned {resp.status_code}"
            body = resp.text
            assert "IEHOVA SEMPER VIGILANS" in body, f"Missing IEHOVA SEMPER VIGILANS on {route}"
            assert "toujours prest" not in body.lower(), f"Stale TOUJOURS PREST found on {route}"

        # /community/heritage/house/1 explicitly documents all finalized symbolism pillars
        h1_html = client.get("/community/heritage/house/1").text
        for detail_phrase in (
            "Strategic Air Command (SAC)",
            "lightning bolts",
            "olive branch",
            "jewelled gold coronet",
            "African American knight",
            "visor raised",
            "Barbary lion",
            "braided gold-and-green",
        ):
            assert detail_phrase.lower() in h1_html.lower(), f"Missing '{detail_phrase}' on /community/heritage/house/1"


def test_carmichael_achievement_svg_zero_cdn_valid_xml_and_finalized_elements():
    svg_path = CRESTS_DIR / "carmichael_achievement.svg"
    assert svg_path.exists()
    svg_text = svg_path.read_text(encoding="utf-8")

    # Strict XML validity and Play #16B zero-CDN hygiene
    ET.fromstring(svg_text)
    assert "<script" not in svg_text.lower()
    assert not re.search(r"""(?:src|href)\s*=\s*["']https?://""", svg_text, re.IGNORECASE)

    # Finalized official motto & zero stale motto
    assert "IEHOVA SEMPER VIGILANS" in svg_text
    assert "TOUJOURS PREST" not in svg_text.upper()

    # Finalized heraldic SVG elements
    for element_id in (
        "officialMottoScroll",
        "sacGauntletLightningOliveCrest",
        "sacLightningBolts",
        "sacOliveBranch",
        "jewelledGoldCoronet",
        "acanthusMantling",
        "knightSupporter",
        "visorUpHelm",
        "crownedLionSupporter",
        "barbaryLionMane",
        "scottishThistles",
        "heritageAccentRibbon",
        "braidedGoldGreenRibbon",
    ):
        assert f'id="{element_id}"' in svg_text, f"Missing SVG group id='{element_id}' in carmichael_achievement.svg"


def test_idempotent_seed_sync_upgrades_legacy_db_without_overwriting_genealogist_edits(tmp_path: Path):
    db_file = tmp_path / "legacy_heritage_pr84.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SessionLocalTest = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    # Case 1: Pre-existing DB with unmodified SYSTEM_SEED House 01 & Carmichael surname carrying legacy TOUJOURS PREST
    with SessionLocalTest() as db:
        db.add(
            HeritageHouseProfileModel(
                house_id=1,
                lineage_code="HOUSE-01",
                house_name="House of Carmichael Prime",
                motto="Toujours Prest — Always Ready in Stewardship",
                crest_asset_path="/static/assets/crests/carmichael_crest.svg",
                founding_branch="Carmichael Line — Descending from Eldest McCormick Daughter",
                history_body="Legacy pre-PR84 chronicle.",
                milestones_json=json.dumps(["Legacy milestone"]),
                updated_by="SYSTEM_SEED",
                updated_at_utc="2026-01-01T00:00:00+00:00",
            )
        )
        db.add(
            HeritageSurnameRecordModel(
                slug="carmichael",
                surname="Carmichael",
                is_founding=1,
                house_id=1,
                crest_asset_path="/static/assets/crests/carmichael_crest.svg",
                origin_summary="Founding Pillar · Lanarkshire & Highland stewardship heritage",
                history_body="Legacy surname bio.",
                updated_by="SYSTEM_SEED",
                updated_at_utc="2026-01-01T00:00:00+00:00",
            )
        )
        db.commit()

    svc1 = HeritageCommunityService(session_factory=SessionLocalTest, bind_engine=engine)
    h1_after = svc1.get_house_history(1)
    assert h1_after["motto"] == "IEHOVA SEMPER VIGILANS"
    assert "Strategic Air Command" in h1_after["history_body"]
    carm_after = svc1.get_surname_history("carmichael")
    assert "IEHOVA SEMPER VIGILANS" in carm_after["origin_summary"]

    # Case 2: HOUSE_GENEALOGIST edited House 01 narrative while legacy motto remained -> motto updates, custom narrative preserved!
    custom_narrative = "Custom House 01 genealogist oral history curated by Aunt Evelyn."
    with SessionLocalTest() as db:
        row = db.get(HeritageHouseProfileModel, 1)
        assert row is not None
        row.motto = "Toujours Prest — Always Ready in Stewardship"
        row.history_body = custom_narrative
        row.updated_by = "MEM-GENEALOGIST-H1"
        s_row = db.get(HeritageSurnameRecordModel, "carmichael")
        assert s_row is not None
        s_row.history_body = "Custom Carmichael family story curated by House 01 Genealogist."
        s_row.updated_by = "MEM-GENEALOGIST-H1"
        db.commit()

    svc2 = HeritageCommunityService(session_factory=SessionLocalTest, bind_engine=engine)
    h1_preserved = svc2.get_house_history(1)
    assert h1_preserved["motto"] == "IEHOVA SEMPER VIGILANS"
    assert h1_preserved["history_body"] == custom_narrative
    assert h1_preserved["updated_by"] == "MEM-GENEALOGIST-H1"

    carm_preserved = svc2.get_surname_history("carmichael")
    assert carm_preserved["history_body"] == "Custom Carmichael family story curated by House 01 Genealogist."
    assert carm_preserved["updated_by"] == "MEM-GENEALOGIST-H1"

    # Case 3: Custom genealogist non-legacy motto is also preserved on subsequent restarts
    with SessionLocalTest() as db:
        row = db.get(HeritageHouseProfileModel, 1)
        assert row is not None
        row.motto = "IEHOVA SEMPER VIGILANS — Family Edition"
        db.commit()

    svc3 = HeritageCommunityService(session_factory=SessionLocalTest, bind_engine=engine)
    assert svc3.get_house_history(1)["motto"] == "IEHOVA SEMPER VIGILANS — Family Edition"


def test_asset_resolver_prefers_raster_dropins_and_falls_back_to_svg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Direct unit test of priority: .png > .jpg > .jpeg > .svg
    assert resolve_heraldic_asset_path("carmichael_achievement", crests_dir=tmp_path) == "/static/assets/crests/carmichael_achievement.svg"

    jpg_file = tmp_path / "carmichael_achievement.jpg"
    jpg_file.write_bytes(b"\xff\xd8\xff\xe0fakejpg")
    assert resolve_heraldic_asset_path("carmichael_achievement", crests_dir=tmp_path) == "/static/assets/crests/carmichael_achievement.jpg"

    png_file = tmp_path / "carmichael_achievement.png"
    png_file.write_bytes(b"\x89PNG\r\n\x1a\nfakepng")
    assert resolve_heraldic_asset_path("carmichael_achievement", crests_dir=tmp_path) == "/static/assets/crests/carmichael_achievement.png"

    # End-to-end route verification with monkeypatched CRESTS_STATIC_DIR
    mcc_jpg = tmp_path / "mccormick_achievement.jpg"
    mcc_jpg.write_bytes(b"\xff\xd8\xff\xe0fakemcc")
    monkeypatch.setattr(heritage_svc_mod, "CRESTS_STATIC_DIR", tmp_path)

    with TestClient(app) as client:
        gallery = client.get("/api/v1/portal/community/heritage").json()
        assert gallery["two_scale_heraldry"]["achievement_assets"]["carmichael"] == "/static/assets/crests/carmichael_achievement.png"
        assert gallery["two_scale_heraldry"]["achievement_assets"]["mccormick"] == "/static/assets/crests/mccormick_achievement.jpg"

        h1_api = client.get("/api/v1/portal/community/heritage/house/1").json()
        assert h1_api["achievement_asset_path"] == "/static/assets/crests/carmichael_achievement.png"

        home_html = client.get("/home").text
        assert "/static/assets/crests/carmichael_achievement.png" in home_html
        assert "/static/assets/crests/mccormick_achievement.jpg" in home_html
        # Compact header shield lockup remains crisp SVG
        assert "/static/assets/crests/carmichael_crest.jpg" in home_html
        assert "/static/assets/crests/mccormick_crest.jpg" in home_html

        heritage_html = client.get("/community/heritage").text
        assert "/static/assets/crests/carmichael_achievement.png" in heritage_html
        assert "/static/assets/crests/mccormick_achievement.jpg" in heritage_html

        h1_html = client.get("/community/heritage/house/1").text
        assert "/static/assets/crests/carmichael_achievement.png" in h1_html

        # Remove .png -> seamlessly drops to .jpg
        png_file.unlink()
        assert "/static/assets/crests/carmichael_achievement.jpg" in client.get("/community/heritage").text
        assert "/static/assets/crests/carmichael_achievement.jpg" in client.get("/community/heritage/house/1").text

        # Remove .jpg -> seamlessly falls back to .svg
        jpg_file.unlink()
        assert "/static/assets/crests/carmichael_achievement.svg" in client.get("/home").text
        assert "/static/assets/crests/carmichael_achievement.svg" in client.get("/community/heritage").text
        assert "/static/assets/crests/carmichael_achievement.svg" in client.get("/community/heritage/house/1").text

    # Verify assets/crests/README.md documents the exact drop-in convention
    readme = (CRESTS_DIR / "README.md").read_text(encoding="utf-8")
    for token in (
        "IEHOVA SEMPER VIGILANS",
        "Strategic Air Command",
        "carmichael_achievement.png",
        "carmichael_achievement.jpg",
        "mccormick_achievement.png",
        "resolve_heraldic_asset_path",
    ):
        assert token in readme, f"Missing '{token}' in assets/crests/README.md"


def test_compact_header_lockup_firewall_sync_and_nine_portal_parity_gate():
    # 1. Social-plane firewall (zero financial imports)
    social_modules = (
        BACKEND_DIR / "app" / "domain" / "heritage_community_service.py",
        BACKEND_DIR / "app" / "api" / "v1" / "social_plane_router.py",
    )
    forbidden = (
        "CapitalLedger",
        "TwoTierRiskEnvelope",
        "AutonomousScanWorker",
        "CredentialBroker",
        "capital_ledger",
        "venue_adapters",
    )
    for mod_path in social_modules:
        tree = ast.parse(mod_path.read_text(encoding="utf-8"), filename=str(mod_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(bad in alias.name for bad in forbidden)
            elif isinstance(node, ast.ImportFrom):
                mod_name = node.module or ""
                assert not any(bad in mod_name for bad in forbidden)
                for alias in node.names:
                    assert alias.name not in forbidden

    # 2. Byte-for-byte sync + zero external CDNs across all 9 portals
    cdn_re = re.compile(r"""<(?:script|link)[^>]+(?:src|href)=["']https?://""", re.IGNORECASE)
    for filename in ALL_NINE_TEMPLATES:
        api_text = (API_V1_DIR / filename).read_text(encoding="utf-8")
        static_text = (STATIC_DIR / filename).read_text(encoding="utf-8")
        assert api_text == static_text, f"Byte-for-byte drift on {filename}"
        assert not cdn_re.search(api_text), f"External CDN found in {filename}"

    # 3. Crisp 40x46 compact shield lockup + 3-row header preserved across all 9 routes
    with TestClient(app) as client:
        for route in ALL_NINE_ROUTES:
            html_body = client.get(route).text
            assert "/static/assets/crests/carmichael_crest.jpg" in html_body
            assert "/static/assets/crests/mccormick_crest.jpg" in html_body
            assert 'width="40" height="46"' in html_body
            assert 'class="portal-header-row1"' in html_body
            assert 'class="portal-header-row2"' in html_body
            assert 'class="portal-header-row3' in html_body

    # 4. 9-portal Automated UI-to-Lexicon-to-Curriculum Parity Gate PASS
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
