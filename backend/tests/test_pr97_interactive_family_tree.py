"""PR #97 verification suite: Interactive Zero-CDN Family Tree (/community/heritage/tree),
Living-Member Privacy Guard, live LCA Relationship Calculator, scoped HOUSE_GENEALOGIST &
CHIEF_ADMIN mutations with GovernanceAuditLog, Excel importer suffix/integrity checks,
AST social-plane firewall, Caddy allowlist, and 10-portal byte-for-byte parity."""
from __future__ import annotations

import ast
import json
import pathlib
import re
import sys
import zipfile
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect as sa_inspect
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, FamilyTreePersonModel
from app.domain.authority_tiers import get_governance_audit_log
from app.domain.family_tree_service import (
    FORBIDDEN_LIVING_OUTPUT_KEYS,
    FamilyTreeService,
    normalize_surname_and_suffix,
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
CADDYFILE_PATH = REPO_ROOT / "deploy" / "caddy" / "Caddyfile"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.import_family_tree_excel import (  # noqa: E402
    convert_workbook_to_seed_dict,
    import_excel_to_json,
)

TEN_PORTAL_TEMPLATES = (
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


def _make_isolated_tree_service(tmp_path: pathlib.Path) -> FamilyTreeService:
    db_file = tmp_path / "tree_test.db"
    eng = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    return FamilyTreeService(session_factory=session_factory, bind_engine=eng)


def _write_minimal_xlsx(path: pathlib.Path, sheets: Dict[str, List[List[Any]]]) -> None:
    """Create a valid minimal Excel 2019 OOXML `.xlsx` file using stdlib zipfile only."""
    sheet_names = list(sheets.keys())

    def _col_letter(idx: int) -> str:
        res = ""
        n = idx + 1
        while n > 0:
            n, rem = divmod(n - 1, 26)
            res = chr(65 + rem) + res
        return res

    def _esc_xml(val: Any) -> str:
        return (
            str(val)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def _sheet_xml(rows: List[List[Any]]) -> str:
        row_xml_parts: List[str] = []
        for r_idx, row in enumerate(rows, start=1):
            cells: List[str] = []
            for c_idx, val in enumerate(row):
                if val is None:
                    continue
                ref = f"{_col_letter(c_idx)}{r_idx}"
                if isinstance(val, bool):
                    cells.append(f'<c r="{ref}" t="b"><v>{1 if val else 0}</v></c>')
                elif isinstance(val, (int, float)):
                    cells.append(f'<c r="{ref}"><v>{val}</v></c>')
                else:
                    cells.append(
                        f'<c r="{ref}" t="inlineStr"><is><t>{_esc_xml(val)}</t></is></c>'
                    )
            row_xml_parts.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(row_xml_parts)}</sheetData>'
            "</worksheet>"
        )

    wb_sheets = "".join(
        f'<sheet name="{_esc_xml(name)}" sheetId="{idx}" '
        f'r:id="rId{idx}"/>'
        for idx, name in enumerate(sheet_names, start=1)
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{wb_sheets}</sheets>"
        "</workbook>"
    )
    rels_items = "".join(
        f'<Relationship Id="rId{idx}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{idx}.xml"/>'
        for idx in range(1, len(sheet_names) + 1)
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{rels_items}"
        "</Relationships>"
    )

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        for idx, name in enumerate(sheet_names, start=1):
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", _sheet_xml(sheets[name]))


# ---------------------------------------------------------------------------
# 1. Living-Member Privacy Guard & Seed Normalization
# ---------------------------------------------------------------------------


def test_living_member_privacy_guard_suppresses_living_dates_and_preserves_deceased_ancestors(
    tmp_path: pathlib.Path,
) -> None:
    svc = _make_isolated_tree_service(tmp_path)
    data = svc.get_tree_data(include_reference=True)
    assert data["privacy_guard_active"] is True
    assert data["scope"] == "HERITAGE_FAMILY_TREE_NO_FINANCIAL_DATA"

    by_id = {p["person_id"]: p for p in data["people"]}

    # Deceased founding ancestor (Mary Viola "Ola" McCormick) displays birth_year–death_year
    ola = by_id["P0004"]
    assert ola["is_deceased"] is True
    assert ola["birth_year"] == 1898
    assert ola["death_year"] == 1984
    assert ola["life_span"] == "1898–1984"
    assert ola["privacy_protected"] is False

    # Living member (P0019 James R. Carmichael Jr. has birth_year=1948 in raw DB/seed!)
    # Server MUST suppress birth_year, death_year, life_span, and all contact fields
    with svc._session_factory() as db:
        raw_p19 = db.get(FamilyTreePersonModel, "P0019")
        assert raw_p19 is not None and raw_p19.birth_year == 1948

    living = by_id["P0019"]
    assert living["is_deceased"] is False
    assert living["birth_year"] is None
    assert living["death_year"] is None
    assert living["life_span"] == ""
    assert living["privacy_protected"] is True
    assert living["surname"] == "Carmichael"
    assert living["suffix"] == "Jr."
    for forbidden_key in FORBIDDEN_LIVING_OUTPUT_KEYS:
        assert forbidden_key not in living

    # Living member with accidental contact/date text in bio_notes gets scrubbed on read
    created = svc.create_person(
        full_name="Jordan Vance",
        surname="Vance Jr",
        house_id="HOUSE-01",
        generation=3,
        is_deceased=False,
        birth_year=1992,
        bio_notes="Call 555-123-4567 or email jordan@example.org born 1992-05-14.",
        actor_role="CHIEF_ADMIN",
        actor_id="CHIEF_ADMINISTRATOR",
    )
    assert created["birth_year"] is None
    assert created["privacy_protected"] is True
    assert created["surname"] == "Vance"
    assert created["suffix"] == "Jr."
    assert "555-123-4567" not in created["bio_notes"]
    assert "jordan@example.org" not in created["bio_notes"]
    assert "1992-05-14" not in created["bio_notes"]

    # Edge case: is_deceased=True but death_year is None -> still protected!
    no_death_year = svc.create_person(
        full_name="Unknown Death Date Elder",
        surname="McCormick",
        house_id="HOUSE-02",
        generation=2,
        is_deceased=True,
        birth_year=1944,
        death_year=None,
        actor_role="CHIEF_ADMIN",
        actor_id="CHIEF_ADMINISTRATOR",
    )
    assert no_death_year["birth_year"] is None
    assert no_death_year["privacy_protected"] is True

    # Reference branch hidden by default, shown when include_reference=True
    default_view = svc.get_tree_data(include_reference=False)
    default_ids = {p["person_id"] for p in default_view["people"]}
    assert "P0001" not in default_ids
    assert default_view["reference_branch_count"] >= 3
    assert "P0004" in default_ids


# ---------------------------------------------------------------------------
# 2. Live Graph-Based Relationship Calculator Accuracy
# ---------------------------------------------------------------------------


def test_relationship_calculator_bloodline_spouse_married_in_and_disconnected(
    tmp_path: pathlib.Path,
) -> None:
    svc = _make_isolated_tree_service(tmp_path)

    # Same person
    same = svc.compute_relationship("P0004", "P0004")
    assert same["primary_label"] == "Same Person"
    assert same["a_steps"] == 0 and same["b_steps"] == 0

    # Direct Spouse / Partner
    spouse = svc.compute_relationship("P0004", "P0005")
    assert spouse["primary_label"] == "Spouse / Partner"
    assert spouse["via_marriage"] is True

    # Parent / Child
    pc = svc.compute_relationship("P0004", "P0006")
    assert pc["a_to_b_label"] == "Parent"
    assert pc["b_to_a_label"] == "Child"
    assert pc["a_steps"] == 0 and pc["b_steps"] == 1

    # Grandparent / Grandchild
    gp = svc.compute_relationship("P0004", "P0019")
    assert gp["a_to_b_label"] == "Grandparent"
    assert gp["b_to_a_label"] == "Grandchild"
    assert gp["a_steps"] == 0 and gp["b_steps"] == 2

    # Great-Grandparent / Great-Grandchild
    ggp = svc.compute_relationship("P0004", "P0022")
    assert ggp["a_to_b_label"] == "Great-Grandparent"
    assert ggp["b_to_a_label"] == "Great-Grandchild"
    assert ggp["a_steps"] == 0 and ggp["b_steps"] == 3

    # Sibling (shares both Mary Viola & William F. McCormick)
    sib = svc.compute_relationship("P0006", "P0008")
    assert sib["primary_label"] == "Sibling"
    assert sib["a_steps"] == 1 and sib["b_steps"] == 1
    assert {c["person_id"] for c in sib["common_ancestors"]} == {"P0004", "P0005"}

    # Aunt / Uncle & Niece / Nephew
    aunt = svc.compute_relationship("P0006", "P0026")
    assert aunt["a_to_b_label"] == "Aunt / Uncle"
    assert aunt["b_to_a_label"] == "Niece / Nephew"
    assert aunt["a_steps"] == 1 and aunt["b_steps"] == 2

    # 1st Cousin
    c1 = svc.compute_relationship("P0019", "P0026")
    assert c1["primary_label"] == "1st Cousin"
    assert c1["a_steps"] == 2 and c1["b_steps"] == 2
    assert {c["person_id"] for c in c1["common_ancestors"]} == {"P0004", "P0005"}

    # 2nd Cousin
    c2 = svc.compute_relationship("P0022", "P0028")
    assert c2["primary_label"] == "2nd Cousin"
    assert c2["a_steps"] == 3 and c2["b_steps"] == 3

    # 1st Cousin once removed
    c1r1 = svc.compute_relationship("P0019", "P0028")
    assert c1r1["primary_label"] == "1st Cousin once removed"
    assert c1r1["a_steps"] == 2 and c1r1["b_steps"] == 3
    assert "removed" in c1r1["glossary_definition"].lower()

    # 1st Cousin twice removed
    c1r2 = svc.compute_relationship("P0019", "P0029")
    assert c1r2["primary_label"] == "1st Cousin twice removed"
    assert c1r2["a_steps"] == 2 and c1r2["b_steps"] == 4

    # Married-in connection (Eleanor Vance Carmichael P0020 married to P0019, 1st Cousin of P0026)
    married_in = svc.compute_relationship("P0020", "P0026")
    assert married_in["relationship_kind"] == "MARRIED_IN"
    assert "by marriage" in married_in["primary_label"].lower()
    assert married_in["via_marriage"] is True

    # Disconnected Historical Reference Branch (Roderick McCormick P0001 vs Ola P0004)
    disc = svc.compute_relationship("P0001", "P0004")
    assert disc["relationship_kind"] == "DISCONNECTED"
    assert disc["primary_label"] == "No shared recorded bloodline ancestor"
    assert disc["common_ancestors"] == []


# ---------------------------------------------------------------------------
# 3. Scoped HOUSE_GENEALOGIST & CHIEF_ADMIN Mutations + GovernanceAuditLog
# ---------------------------------------------------------------------------


def test_scoped_genealogist_and_chief_admin_tree_mutations_403_and_audit(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = _make_isolated_tree_service(tmp_path)
    monkeypatch.setattr("app.api.v1.social_plane_router.get_family_tree_service", lambda: svc)

    audit = get_governance_audit_log()
    before_count = len(audit.list_events(limit=500))

    with TestClient(app) as client:
        # 1. Read-only GET endpoints work cleanly
        tree_resp = client.get("/api/v1/community/heritage/tree/data?house_id=HOUSE-01")
        assert tree_resp.status_code == 200
        tree_payload = tree_resp.json()
        assert all(p["house_id"] == "HOUSE-01" for p in tree_payload["people"])

        rel_resp = client.get("/api/v1/community/heritage/tree/relationship?person_a=P0019&person_b=P0028")
        assert rel_resp.status_code == 200
        assert rel_resp.json()["primary_label"] == "1st Cousin once removed"

        # 2. HOUSE_GENEALOGIST scoped to HOUSE-03 CAN add & edit people and relationships in HOUSE-03
        gen_h3_headers = {
            "X-Active-Hat": "HOUSE_GENEALOGIST",
            "X-House-ID": "HOUSE-03",
            "X-Actor-ID": "MEM-GEN-H3-TEST",
        }
        create_ok = client.post(
            "/api/v1/community/heritage/tree/person",
            headers=gen_h3_headers,
            json={
                "full_name": "Callum MacLeod Jr.",
                "surname": "MacLeod Jr.",
                "house_id": "HOUSE-03",
                "generation": 4,
                "is_deceased": False,
                "birth_year": 2008,
                "bio_notes": "House 03 youth archivist.",
            },
        )
        assert create_ok.status_code == 201, create_ok.text
        created_person = create_ok.json()
        assert created_person["house_id"] == "HOUSE-03"
        assert created_person["surname"] == "MacLeod"
        assert created_person["suffix"] == "Jr."
        assert created_person["birth_year"] is None  # Living-member privacy enforced!

        patch_ok = client.patch(
            f"/api/v1/community/heritage/tree/person/{created_person['person_id']}",
            headers=gen_h3_headers,
            json={"bio_notes": "Updated House 03 family note.", "review_flag": "Verify middle initial"},
        )
        assert patch_ok.status_code == 200, patch_ok.text
        assert patch_ok.json()["review_flag"] == "Verify middle initial"

        rel_ok = client.post(
            "/api/v1/community/heritage/tree/relationship",
            headers=gen_h3_headers,
            json={
                "rel_type": "parent",
                "person_a_id": "P0032",
                "person_b_id": created_person["person_id"],
                "notes": "House 03 Gen 3 -> Gen 4",
            },
        )
        assert rel_ok.status_code == 201, rel_ok.text

        # 3. HOUSE_GENEALOGIST (HOUSE-03) FAILS CLOSED (HTTP 403) on other Houses, FOUNDERS, REFERENCE
        for forbidden_house in ("HOUSE-01", "HOUSE-04", "FOUNDERS", "REFERENCE"):
            cross_create = client.post(
                "/api/v1/community/heritage/tree/person",
                headers=gen_h3_headers,
                json={"full_name": "Unauthorized Relative", "surname": "Vance", "house_id": forbidden_house},
            )
            assert cross_create.status_code == 403, f"Expected 403 on {forbidden_house}"

        cross_patch = client.patch(
            "/api/v1/community/heritage/tree/person/P0019",
            headers=gen_h3_headers,
            json={"bio_notes": "Attempted cross-house edit"},
        )
        assert cross_patch.status_code == 403

        cross_rel = client.post(
            "/api/v1/community/heritage/tree/relationship",
            headers=gen_h3_headers,
            json={"rel_type": "spouse", "person_a_id": "P0032", "person_b_id": "P0019"},
        )
        assert cross_rel.status_code == 403

        # 4. All non-genealogist / non-Chief-Admin roles fail closed with HTTP 403
        for denied_role in (
            "",
            "CLASS_M",
            "MEMBER_USER",
            "T1",
            "T2",
            "T2-HOUSEHOLD",
            "T3",
            "F1",
            "F2-H",
            "F2-A",
            "F3",
            "H1",
            "H2",
            "CHIEF_ADMIN_DEPUTY",
        ):
            hdrs = {"X-Active-Hat": denied_role, "X-House-ID": "HOUSE-01"} if denied_role else {}
            r_post = client.post(
                "/api/v1/community/heritage/tree/person",
                headers=hdrs,
                json={"full_name": "Blocked Entry", "surname": "Carmichael", "house_id": "HOUSE-01"},
            )
            assert r_post.status_code == 403, f"Role {denied_role!r} must receive 403 on POST /person"
            r_patch = client.patch(
                "/api/v1/community/heritage/tree/person/P0019",
                headers=hdrs,
                json={"bio_notes": "Blocked patch"},
            )
            assert r_patch.status_code == 403, f"Role {denied_role!r} must receive 403 on PATCH /person"
            r_rel = client.post(
                "/api/v1/community/heritage/tree/relationship",
                headers=hdrs,
                json={"rel_type": "spouse", "person_a_id": "P0022", "person_b_id": "P0023"},
            )
            assert r_rel.status_code == 403, f"Role {denied_role!r} must receive 403 on POST /relationship"

        # 5. CHIEF_ADMIN has enclave-wide curation rights
        ca_headers = {"X-Active-Hat": "CHIEF_ADMIN", "X-Actor-ID": "USR-founder_ch-C8575D7E"}
        ca_ok = client.post(
            "/api/v1/community/heritage/tree/person",
            headers=ca_headers,
            json={
                "full_name": "Archival Reference Cousin",
                "surname": "McCormick",
                "house_id": "HOUSE-07",
                "generation": 3,
                "is_deceased": True,
                "birth_year": 1958,
                "death_year": 2022,
            },
        )
        assert ca_ok.status_code == 201
        assert ca_ok.json()["life_span"] == "1958–2022"

        # 6. HTML Curation Drawer is stripped server-side for standard members, present for GENEALOGIST/CHIEF_ADMIN
        member_html = client.get("/community/heritage/tree").text
        assert 'id="treeReadOnlyBanner"' in member_html
        assert 'id="genealogistTreeDrawer"' not in member_html

        gen_html = client.get(
            "/community/heritage/tree",
            headers={"X-Active-Hat": "HOUSE_GENEALOGIST", "X-House-ID": "HOUSE-03"},
        ).text
        assert 'id="genealogistTreeDrawer"' in gen_html
        assert 'data-tree-can-curate="true"' in gen_html

        ca_html = client.get("/community/heritage/tree", headers=ca_headers).text
        assert 'id="genealogistTreeDrawer"' in ca_html

    # 7. GovernanceAuditLog captured both approved writes and HTTP 403 denials
    recent_entries = audit.list_events(limit=500)
    assert len(recent_entries) > before_count
    event_types = {e["event_type"] for e in recent_entries}
    assert "FAMILY_TREE_PERSON_CREATED" in event_types
    assert "FAMILY_TREE_PERSON_UPDATED" in event_types
    assert "FAMILY_TREE_RELATIONSHIP_CREATED" in event_types
    assert "FAMILY_TREE_WRITE_DENIED" in event_types


# ---------------------------------------------------------------------------
# 4. Excel Importer Suffix Normalization & Referential Integrity Check
# ---------------------------------------------------------------------------


def test_import_family_tree_excel_suffix_normalization_and_integrity(tmp_path: pathlib.Path) -> None:
    assert normalize_surname_and_suffix("McCormick Jr.") == ("McCormick", "Jr.")
    assert normalize_surname_and_suffix("Carmichael Sr") == ("Carmichael", "Sr.")
    assert normalize_surname_and_suffix("McCormick 1") == ("McCormick", "1")
    assert normalize_surname_and_suffix("Carmichael III") == ("Carmichael", "III")

    good_xlsx = tmp_path / "family_good.xlsx"
    _write_minimal_xlsx(
        good_xlsx,
        {
            "People": [
                ["PersonID", "FullName", "GivenName", "Surname", "Suffix", "HouseID", "Generation", "IsDeceased", "BirthYear", "DeathYear", "Email", "Phone"],
                ["P0004", "Mary Viola McCormick", "Mary Viola", "McCormick", "", "FOUNDERS", 0, True, 1898, 1984, "", ""],
                ["P0006", "William McCormick Jr.", "William", "McCormick Jr.", "", "HOUSE-02", 1, True, 1921, 2001, "", ""],
                ["P0007", "James Carmichael Sr.", "James", "Carmichael Sr", "", "HOUSE-01", 1, False, 1960, None, "private@example.com", "555-999-0000"],
                ["P0008", "Robert McCormick 1", "Robert", "McCormick 1", "", "HOUSE-04", 1, True, 1925, 2009, "", ""],
            ],
            "Relationships": [
                ["RelID", "RelType", "PersonA_ID", "PersonB_ID", "Notes"],
                ["R00001", "parent", "P0004", "P0006", "Founding child"],
                ["R00002", "parent", "P0004", "P0008", "Founding child"],
            ],
        },
    )

    out_json = tmp_path / "seed_out.json"
    payload = import_excel_to_json(good_xlsx, out_json)
    assert out_json.is_file()
    by_id = {p["person_id"]: p for p in payload["people"]}
    assert by_id["P0006"]["surname"] == "McCormick" and by_id["P0006"]["suffix"] == "Jr."
    assert by_id["P0007"]["surname"] == "Carmichael" and by_id["P0007"]["suffix"] == "Sr."
    assert by_id["P0008"]["surname"] == "McCormick" and by_id["P0008"]["suffix"] == "1"
    # Contact columns must never be written to seed JSON
    for p in payload["people"]:
        assert "email" not in p and "phone" not in p
    # Deterministic output on second run
    first_bytes = out_json.read_bytes()
    import_excel_to_json(good_xlsx, out_json)
    assert out_json.read_bytes() == first_bytes

    # Broken referential integrity MUST raise ValueError
    broken_xlsx = tmp_path / "family_broken.xlsx"
    _write_minimal_xlsx(
        broken_xlsx,
        {
            "People": [
                ["PersonID", "FullName", "Surname", "HouseID", "Generation"],
                ["P0001", "Only Person", "McCormick", "HOUSE-01", 1],
            ],
            "Relationships": [
                ["RelID", "RelType", "PersonA_ID", "PersonB_ID"],
                ["R00001", "parent", "P0001", "P9999"],
            ],
        },
    )
    with pytest.raises(ValueError, match="broken ID reference"):
        convert_workbook_to_seed_dict(broken_xlsx)


# ---------------------------------------------------------------------------
# 5. AST Zero-Financial-Import Air-Gap, Zero-CDN, 10-Template Parity & Caddy
# ---------------------------------------------------------------------------


def test_social_plane_ast_zero_financial_imports() -> None:
    targets = [
        BACKEND_DIR / "app" / "domain" / "family_tree_service.py",
        BACKEND_DIR / "app" / "api" / "v1" / "social_plane_router.py",
        BACKEND_DIR / "scripts" / "import_family_tree_excel.py",
    ]
    for path in targets:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_tokens: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_tokens.update(alias.name.split("."))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_tokens.update(node.module.split("."))
                for alias in node.names:
                    imported_tokens.add(alias.name)
        leaked = imported_tokens & FORBIDDEN_FINANCIAL_MODULES_AND_SYMBOLS
        assert not leaked, f"Financial import air-gap violation in {path.name}: {leaked}"


def test_ten_portal_templates_byte_parity_zero_cdn_ctas_caddy_and_discovery() -> None:
    external_tag_re = re.compile(r"<(?:script|link)\b[^>]+(?:src|href)\s*=\s*['\"]https?://", re.IGNORECASE)
    for filename in TEN_PORTAL_TEMPLATES:
        api_path = API_V1_DIR / filename
        static_path = STATIC_DIR / filename
        assert api_path.is_file(), f"Missing {api_path}"
        assert static_path.is_file(), f"Missing {static_path}"
        api_bytes = api_path.read_bytes()
        static_bytes = static_path.read_bytes()
        assert api_bytes == static_bytes, f"Byte-for-byte parity drift for {filename}"
        assert external_tag_re.search(api_bytes.decode("utf-8")) is None, f"External CDN tag in {filename}"

    # Verify Explore Interactive Family Tree CTAs on /community/heritage and /community
    heritage_html = (API_V1_DIR / "heritage.html").read_text(encoding="utf-8")
    community_html = (API_V1_DIR / "community.html").read_text(encoding="utf-8")
    assert "Explore Interactive Family Tree" in heritage_html
    assert 'href="/community/heritage/tree"' in heritage_html
    assert "Explore Interactive Family Tree" in community_html
    assert 'href="/community/heritage/tree"' in community_html

    # Verify Caddyfile routes /community/heritage/tree and /api/v1/community/heritage/tree* on narratixai.org
    caddy = CADDYFILE_PATH.read_text(encoding="utf-8")
    assert "/community/*" in caddy
    assert "/api/v1/community/heritage/tree*" in caddy

    # Verify Portal Discovery registers all 10 portals and passes parity gate with 0 undocumented controls
    assert "/community/heritage/tree" in PORTALS
    assert len(PORTALS) == 10
    report = audit_ui_lexicon_curriculum_parity(REPO_ROOT)
    assert report["passed"] is True, f"Parity audit failed: {report}"
    assert report["undocumented_controls"] == []
    assert generate_inventory(REPO_ROOT) == (REPO_ROOT / "docs" / "PORTAL_COMPONENT_INVENTORY.md").read_text(encoding="utf-8")


def test_alembic_007_family_tree_migration_idempotent(tmp_path: pathlib.Path) -> None:
    import importlib.util
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    mig_path = BACKEND_DIR / "alembic" / "versions" / "007_add_family_tree_tables.py"
    assert mig_path.is_file()
    spec = importlib.util.spec_from_file_location("mig007", mig_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    eng = create_engine(f"sqlite:///{tmp_path / 'mig007.db'}")
    with eng.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()
            mod.upgrade()  # Idempotent second run
        tables = set(sa_inspect(conn).get_table_names())
        assert {"family_tree_people", "family_tree_relationships"}.issubset(tables)
        with Operations.context(ctx):
            mod.downgrade()
        tables_after = set(sa_inspect(conn).get_table_names())
        assert "family_tree_people" not in tables_after
        assert "family_tree_relationships" not in tables_after
