"""PR #103 verification suite:
- Full-Screen Retractable Family Tree Studio controls & Print-to-PDF (@media print)
- 1-Click Branch Spin-Off isolation (`FamilyTreeService.get_subtree_data` & API)
  with deterministic Lineage Breadcrumb Trail and Living-Member Privacy Guard
- Botanical Lineage Tree & Structured Family Table controls
- Copy Hygiene Lock (PR #102 guard), zero external CDNs, 12/12 dual-served HTML
  byte-for-byte parity, zero financial imports (AST air-gap), and Portal Discovery
  parity gate."""
from __future__ import annotations

import ast
import pathlib
import re

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.domain.family_tree_service import (
    FORBIDDEN_LIVING_OUTPUT_KEYS,
    FamilyTreeService,
)
from app.main import app
from app.portal_discovery import audit_ui_lexicon_curriculum_parity, generate_inventory

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
API_V1_DIR = BACKEND_DIR / "app" / "api" / "v1"
STATIC_DIR = BACKEND_DIR / "app" / "static"

TWELVE_PORTAL_TEMPLATES = (
    "activate.html",
    "advisor.html",
    "community.html",
    "companion.html",
    "dashboard.html",
    "heritage.html",
    "heritage_tree.html",
    "home.html",
    "lineage_house.html",
    "login.html",
    "member.html",
    "tech.html",
)

FORBIDDEN_FINANCIAL_MODULES_AND_SYMBOLS = frozenset(
    {
        "CapitalLedger",
        "TwoTierRiskEnvelope",
        "AutonomousScanWorker",
        "CredentialBroker",
        "kalshi_adapter",
        "polymarket_adapter",
        "venue_router",
        "maker_execution_engine",
        "fleet_engine",
    }
)

DISALLOWED_COPY_RE = re.compile(r"\bc" + r"alm(?:ly)?\b", re.IGNORECASE)
EXTERNAL_CDN_RE = re.compile(
    r"""<(?:script[^>]+src|link[^>]+href)\s*=\s*["']https?://""",
    re.IGNORECASE,
)


def _make_isolated_tree_service(tmp_path: pathlib.Path) -> FamilyTreeService:
    db_file = tmp_path / "pr103_tree.db"
    eng = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    return FamilyTreeService(session_factory=session_factory, bind_engine=eng)


def test_pr103_subtree_isolation_breadcrumbs_and_living_privacy_guard(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    svc = _make_isolated_tree_service(tmp_path)
    monkeypatch.setattr("app.api.v1.social_plane_router.get_family_tree_service", lambda: svc)

    # 1. Spin off John Willie Carmichael (P0018, Gen 2 House 01)
    jwc_sub = svc.get_subtree_data("P0018")
    assert jwc_sub["scope"] == "HERITAGE_FAMILY_TREE_NO_FINANCIAL_DATA"
    assert jwc_sub["privacy_guard_active"] is True
    assert jwc_sub["root_person_id"] == "P0018"
    assert jwc_sub["root_person"]["full_name"] == "John Willie Carmichael"

    # Deterministic breadcrumb trail: Full 12-House Tree -> House 01: Bertha -> John Willie Carmichael
    crumb_labels = [c["label"] for c in jwc_sub["breadcrumbs"]]
    assert crumb_labels == [
        "Full 12-House Tree",
        'House 01: Bertha "Bert" McCormick',
        "John Willie Carmichael",
    ]

    # Exact sub-tree counts: 49 bloodline descendants + 17 spouses = 66 relatives
    assert jwc_sub["counts"]["bloodline_descendants"] == 49
    assert jwc_sub["counts"]["spouses_included"] == 17
    assert jwc_sub["counts"]["subtree_people"] == 66
    sub_ids = {p["person_id"] for p in jwc_sub["people"]}
    assert len(sub_ids) == 66
    assert {"P0018", "P0019", "P0022", "P0028", "P0058"} <= sub_ids
    # Strictly isolated: no other House heads or unrelated prior-union children leak in
    for excluded_id in ("P0004", "P0006", "P0007", "P0084", "P0085", "P0086", "P0526"):
        assert excluded_id not in sub_ids, f"Unrelated person {excluded_id} leaked into P0018 sub-tree"

    # Every edge stays strictly inside the isolated sub-tree
    for rel in jwc_sub["relationships"]:
        assert rel["person_a_id"] in sub_ids and rel["person_b_id"] in sub_ids

    # Living-Member Privacy Guard strictly enforced on spun-off sub-tree payload
    by_id = {p["person_id"]: p for p in jwc_sub["people"]}
    for living_pid in ("P0028", "P0058"):
        living_rec = by_id[living_pid]
        assert living_rec["is_deceased"] is False
        assert living_rec["birth_year"] is None
        assert living_rec["death_year"] is None
        assert living_rec["life_span"] == ""
        assert living_rec["privacy_protected"] is True
        for forbidden in FORBIDDEN_LIVING_OUTPUT_KEYS:
            assert forbidden not in living_rec

    # 2. Spin off House 01 head Bertha "Bert" McCormick (P0006) via HTTP API
    with TestClient(app) as client:
        resp = client.get("/api/v1/community/heritage/tree/subtree/P0006")
        assert resp.status_code == 200
        house1 = resp.json()
        assert house1["root_person_id"] == "P0006"
        assert [c["label"] for c in house1["breadcrumbs"]] == [
            "Full 12-House Tree",
            'House 01: Bertha "Bert" McCormick',
        ]
        assert house1["counts"]["bloodline_descendants"] == 114
        assert house1["counts"]["subtree_people"] == 164
        h1_ids = {p["person_id"] for p in house1["people"]}
        assert "P0018" in h1_ids
        assert "P0007" not in h1_ids  # House 02 head must not appear

        # Unknown person_id returns 404 cleanly
        missing = client.get("/api/v1/community/heritage/tree/subtree/P999999")
        assert missing.status_code == 404


def test_pr103_template_controls_print_stylesheet_and_copy_hygiene() -> None:
    tree_html = (API_V1_DIR / "heritage_tree.html").read_text(encoding="utf-8")

    # Deliverable 1: Full-Screen Retractable Studio controls
    for required_id in (
        'id="openTreeStudioBtn"',
        'id="treeStudioModal"',
        'id="closeTreeStudioBtn"',
        'id="studioViewModeTreeBtn"',
        'id="studioViewModeBotanicalBtn"',
        'id="studioViewModeTableBtn"',
        'id="studioViewModeDirectoryBtn"',
        'id="studioZoomInBtn"',
        'id="studioZoomOutBtn"',
        'id="studioFitScreenBtn"',
        'id="studioResetViewBtn"',
        'id="studioPrintTreeBtn"',
    ):
        assert required_id in tree_html, f"Missing Studio control {required_id}"

    # Deliverable 2: 1-Click Branch Spin-Off & Breadcrumb Trail controls
    for required_token in (
        'id="drawerSpinOffBranchBtn"',
        'id="resetSubtreeRootBtn"',
        'id="lineageBreadcrumbBar"',
        'id="lineageBreadcrumbTrail"',
        "data-house-spinoff",
        "data-spinoff-person-id",
    ):
        assert required_token in tree_html, f"Missing Spin-Off control {required_token}"

    # Deliverable 3: Botanical Lineage Tree & Structured Family Table controls
    for required_token in (
        'id="viewModeBotanicalBtn"',
        'id="viewModeTableBtn"',
        'id="viewModeTreeBtn"',
        'id="viewModeDirectoryBtn"',
        'id="botanicalTreeSvg"',
        'id="structuredFamilyTable"',
        'id="tableQuickFilterInput"',
        'id="tableGenFilterSelect"',
        'id="sortColNameBtn"',
        'id="sortColHouseBtn"',
        'id="sortColGenBtn"',
        'id="sortColStatusBtn"',
    ):
        assert required_token in tree_html, f"Missing View Mode control {required_token}"

    # Deliverable 4: Print / Save PDF export stylesheet & header
    assert 'id="printTreeBtn"' in tree_html
    assert 'id="printHeaderSheet"' in tree_html
    assert "@media print" in tree_html
    assert "Living-Member Privacy Guard Active" in tree_html

    # Copy Hygiene Lock (PR #102 guard): zero disallowed copy in heritage_tree.html & touched modules
    for path in (
        API_V1_DIR / "heritage_tree.html",
        STATIC_DIR / "heritage_tree.html",
        BACKEND_DIR / "app" / "domain" / "family_tree_service.py",
        BACKEND_DIR / "app" / "api" / "v1" / "social_plane_router.py",
    ):
        text = path.read_text(encoding="utf-8")
        assert DISALLOWED_COPY_RE.search(text) is None, f"Disallowed copy found in {path.name}"


def test_pr103_social_airgap_zero_cdn_12_portal_parity_and_discovery_inventory() -> None:
    # AST Social-Plane Financial Air-Gap check
    for path in (
        BACKEND_DIR / "app" / "domain" / "family_tree_service.py",
        BACKEND_DIR / "app" / "domain" / "heritage_community_service.py",
        BACKEND_DIR / "app" / "api" / "v1" / "social_plane_router.py",
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.update(alias.name.split("."))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.update(node.module.split("."))
                for alias in node.names:
                    imported.add(alias.name)
        leaked = imported & FORBIDDEN_FINANCIAL_MODULES_AND_SYMBOLS
        assert not leaked, f"Financial import leaked into {path.name}: {leaked}"

    # 12/12 dual-served HTML template byte-for-byte parity & zero external CDNs
    for filename in TWELVE_PORTAL_TEMPLATES:
        api_path = API_V1_DIR / filename
        static_path = STATIC_DIR / filename
        assert api_path.is_file() and static_path.is_file()
        api_bytes = api_path.read_bytes()
        static_bytes = static_path.read_bytes()
        assert api_bytes == static_bytes, f"Byte-for-byte drift on {filename}"
        html_text = api_bytes.decode("utf-8")
        assert EXTERNAL_CDN_RE.search(html_text) is None, f"External CDN tag in {filename}"
        assert DISALLOWED_COPY_RE.search(html_text) is None, f"Disallowed copy in {filename}"

    # Portal Component Discovery parity gate
    report = audit_ui_lexicon_curriculum_parity(REPO_ROOT)
    assert report["passed"] is True, f"Portal Discovery parity failed: {report}"
    assert report["undocumented_controls"] == []
    assert generate_inventory(REPO_ROOT) == (
        REPO_ROOT / "docs" / "PORTAL_COMPONENT_INVENTORY.md"
    ).read_text(encoding="utf-8")
