"""PR #101 verification suite: Plain-English generation-from-Founders metadata,
intuitive Relationship Calculator (`path_a`, `path_b`, `plain_english_story`),
backward compatibility of existing API fields, Living-Member Privacy Guard,
zero financial imports (AST air-gap), zero external CDNs, 12/12 dual-served
HTML template byte-for-byte parity, and Portal Discovery parity gate."""
from __future__ import annotations

import ast
import pathlib
import re

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.domain.family_tree_service import (
    EXTENDED_ANCHOR_TEXT,
    FORBIDDEN_LIVING_OUTPUT_KEYS,
    FOUNDERS_ANCHOR_TEXT,
    FamilyTreeService,
)
from app.main import app
from app.portal_discovery import audit_ui_lexicon_curriculum_parity, generate_inventory

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
API_V1_DIR = BACKEND_DIR / "app" / "api" / "v1"
STATIC_DIR = BACKEND_DIR / "app" / "static"

TWELVE_PORTAL_TEMPLATES = (
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
    "login.html",
    "activate.html",
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
    db_file = tmp_path / "pr101_tree.db"
    eng = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    return FamilyTreeService(session_factory=session_factory, bind_engine=eng)


def _find_unique(people: list[dict], full_name: str, *, house_id: str | None = None) -> dict:
    matches = [
        p
        for p in people
        if p["full_name"] == full_name and (house_id is None or p["house_id"] == house_id)
    ]
    assert len(matches) == 1, f"Expected 1 match for {full_name!r} (house={house_id}), got {len(matches)}"
    return matches[0]


def test_pr101_generation_from_founders_labels_across_all_tiers_and_branches(
    tmp_path: pathlib.Path,
) -> None:
    svc = _make_isolated_tree_service(tmp_path)
    data = svc.get_tree_data(include_reference=True)
    catalog = data["catalog_people"]
    by_id = {p["person_id"]: p for p in catalog}

    # 1. Founding Matriarch & Patriarch (Gen 0)
    ola = by_id["P0004"]
    assert ola["generation_from_founders"] == 0
    assert ola["generation_label"] == "Founding Matriarch"
    assert ola["generation_anchor"] == FOUNDERS_ANCHOR_TEXT

    fletcher = by_id["P0005"]
    assert fletcher["generation_from_founders"] == 0
    assert fletcher["generation_label"] == "Founding Patriarch"
    assert fletcher["generation_anchor"] == FOUNDERS_ANCHOR_TEXT

    # 2. Parents of Matriarch (Gen -1)
    for anc_id in ("P0001", "P0002"):
        anc = by_id[anc_id]
        assert anc["generation_from_founders"] == -1
        assert anc["generation_label"] == "Parents of Matriarch (Founding Ancestors)"
        assert anc["generation_anchor"] == EXTENDED_ANCHOR_TEXT

    # 3. 1st through 6th Gen Bloodline Descendants of Founders
    bertha = _find_unique(catalog, 'Bertha "Bert" McCormick', house_id="HOUSE-01")
    assert bertha["generation_from_founders"] == 1
    assert bertha["generation_label"] == "1st Gen · Child of Founders"
    assert bertha["generation_anchor"] == FOUNDERS_ANCHOR_TEXT

    jwc = _find_unique(catalog, "John Willie Carmichael", house_id="HOUSE-01")
    assert jwc["generation_from_founders"] == 2
    assert jwc["generation_label"] == "2nd Gen · Grandchild of Founders"

    debora = _find_unique(catalog, "Debora Simmons", house_id="HOUSE-08")
    assert debora["generation_from_founders"] == 3
    assert debora["generation_label"] == "3rd Gen · Great-Grandchild of Founders"

    ronnie = _find_unique(catalog, "Ronnie Carmichael", house_id="HOUSE-01")
    assert ronnie["generation_from_founders"] == 4
    assert ronnie["generation_label"] == "4th Gen · 2nd Great-Grandchild of Founders"

    kennedy = _find_unique(catalog, "Kennedy Louise Carmichael", house_id="HOUSE-01")
    assert kennedy["generation_from_founders"] == 5
    assert kennedy["generation_label"] == "5th Gen · 3rd Great-Grandchild of Founders"

    elliot = _find_unique(catalog, "Elliot Genandt", house_id="HOUSE-01")
    assert elliot["generation_from_founders"] == 6
    assert elliot["generation_label"] == "6th Gen · 4th Great-Grandchild of Founders"

    # 4. Married-in Spouses of Founders' Descendants (never mislabeled as bloodline descendants)
    gladys = _find_unique(catalog, "Gladys Bowens", house_id="HOUSE-01")
    assert gladys["generation_from_founders"] == 2
    assert gladys["generation_label"] == "Married into 2nd Gen (Spouse)"
    assert gladys["generation_anchor"] == FOUNDERS_ANCHOR_TEXT

    # 5. Extended Roderick & Dillie Gaddy Lineage (Children II-IX and descendants, never labeled as Founders' descendants)
    sarah = _find_unique(catalog, 'Sarah "Sallie" Caroline McCormick', house_id="REFERENCE")
    assert sarah["generation_from_founders"] == 0
    assert sarah["generation_label"] == "Extended Lineage · Child of Roderick & Dillie"
    assert sarah["generation_anchor"] == EXTENDED_ANCHOR_TEXT

    verney = _find_unique(catalog, "Verney Thompson", house_id="REFERENCE")
    assert verney["generation_from_founders"] == 1
    assert verney["generation_label"] == "Extended Lineage · Grandchild of Roderick & Dillie"
    assert verney["generation_anchor"] == EXTENDED_ANCHOR_TEXT

    ernest_jr = _find_unique(catalog, "Ernest Linwood Thompson Jr.", house_id="REFERENCE")
    assert ernest_jr["generation_from_founders"] == 2
    assert ernest_jr["generation_label"] == "Extended Lineage · Great-Grandchild of Roderick & Dillie"
    assert ernest_jr["generation_anchor"] == EXTENDED_ANCHOR_TEXT

    richard_t = _find_unique(catalog, "Richard Thompson", house_id="REFERENCE")
    assert "Extended Lineage" in richard_t["generation_label"]
    assert "Spouse" in richard_t["generation_label"]
    assert "Founders" not in richard_t["generation_label"]
    assert richard_t["generation_anchor"] == EXTENDED_ANCHOR_TEXT

    # 6. Every single person in the 900+ graph has valid non-empty generation metadata
    for p in catalog:
        assert isinstance(p["generation_from_founders"], int)
        assert isinstance(p["generation_label"], str) and p["generation_label"].strip()
        assert p["generation_anchor"] in {FOUNDERS_ANCHOR_TEXT, EXTENDED_ANCHOR_TEXT}
        if p["is_reference_branch"] and p["person_id"] not in {"P0001", "P0002"}:
            assert "of Founders" not in p["generation_label"], f"Extended person mislabeled: {p}"


def test_pr101_relationship_calculator_paths_and_plain_english_story(
    tmp_path: pathlib.Path,
) -> None:
    svc = _make_isolated_tree_service(tmp_path)
    catalog = svc.get_tree_data(include_reference=True)["catalog_people"]

    bertha = _find_unique(catalog, 'Bertha "Bert" McCormick', house_id="HOUSE-01")["person_id"]
    tony = _find_unique(catalog, "Tony McCormick", house_id="HOUSE-03")["person_id"]
    jwc = _find_unique(catalog, "John Willie Carmichael", house_id="HOUSE-01")["person_id"]
    ronnie = _find_unique(catalog, "Ronnie Carmichael", house_id="HOUSE-01")["person_id"]
    debora = _find_unique(catalog, "Debora Simmons", house_id="HOUSE-08")["person_id"]
    margaret_k = _find_unique(catalog, "Margaret McCormick Kelley", house_id="HOUSE-03")["person_id"]
    gladys = _find_unique(catalog, "Gladys Bowens", house_id="HOUSE-01")["person_id"]
    ernest_jr = _find_unique(catalog, "Ernest Linwood Thompson Jr.", house_id="REFERENCE")["person_id"]

    # 1. Ronnie Carmichael <-> Debora Simmons (2nd Cousin once removed via Ola & William)
    r_vs_d = svc.compute_relationship(ronnie, debora)
    assert r_vs_d["primary_label"] == "2nd Cousin once removed"
    assert r_vs_d["a_steps"] == 4 and r_vs_d["b_steps"] == 3
    assert [n["full_name"] for n in r_vs_d["path_a"]] == [
        'Mary Viola "Ola" McCormick',
        'Bertha "Bert" McCormick',
        "John Willie Carmichael",
        "James Willie Carmichael",
        "Ronnie Carmichael",
    ]
    assert [n["full_name"] for n in r_vs_d["path_b"]] == [
        'Mary Viola "Ola" McCormick',
        "Murphy McCormick",
        "Rosetta McCormick",
        "Debora Simmons",
    ]
    for node in r_vs_d["path_a"] + r_vs_d["path_b"]:
        assert {"person_id", "full_name", "house_id", "generation_label"} <= set(node.keys())
        assert node["generation_label"]
    story_rd = r_vs_d["plain_english_story"]
    assert "James Willie Carmichael" in story_rd
    assert "Debora Simmons" in story_rd
    assert "2nd cousins" in story_rd
    assert "1 generation younger" in story_rd
    assert "2nd cousins once removed" in story_rd
    # Person payloads inside relationship response carry generation_label
    assert r_vs_d["person_a"]["generation_label"] == "4th Gen · 2nd Great-Grandchild of Founders"
    assert r_vs_d["person_b"]["generation_label"] == "3rd Gen · Great-Grandchild of Founders"

    # 2. Direct Parent / Child
    pc = svc.compute_relationship("P0004", bertha)
    assert pc["primary_label"] == "Parent / Child"
    assert len(pc["path_a"]) == 1 and len(pc["path_b"]) == 2
    assert "parent" in pc["plain_english_story"].lower()

    # 3. Siblings
    sib = svc.compute_relationship(bertha, tony)
    assert sib["primary_label"] == "Sibling"
    assert len(sib["path_a"]) == 2 and len(sib["path_b"]) == 2
    assert "siblings" in sib["plain_english_story"].lower()
    assert "Mary Viola" in sib["plain_english_story"]

    # 4. 1st Cousins
    c1 = svc.compute_relationship(jwc, margaret_k)
    assert c1["primary_label"] == "1st Cousin"
    assert len(c1["path_a"]) == 3 and len(c1["path_b"]) == 3
    assert "1st cousins" in c1["plain_english_story"].lower()
    assert 'Bertha "Bert" McCormick' in c1["plain_english_story"]
    assert "Tony McCormick" in c1["plain_english_story"]

    # 5. Direct Spouses
    sp = svc.compute_relationship("P0004", "P0005")
    assert sp["primary_label"] == "Spouse / Partner"
    assert sp["via_marriage"] is True
    assert len(sp["path_a"]) == 1 and len(sp["path_b"]) == 1
    assert "spouses / partners" in sp["plain_english_story"].lower()

    # 6. Married-in connection
    mi = svc.compute_relationship(gladys, margaret_k)
    assert mi["relationship_kind"] == "MARRIED_IN"
    assert mi["via_marriage"] is True
    assert "John Willie Carmichael" in mi["plain_english_story"]
    assert "by marriage" in mi["plain_english_story"].lower()
    assert mi["path_a"][-1]["person_id"] == gladys
    assert mi["path_b"][-1]["person_id"] == margaret_k

    # 7. Cross-branch Roderick & Dillie Gaddy descendants
    cross = svc.compute_relationship(jwc, ernest_jr)
    assert cross["primary_label"] == "2nd Cousin"
    assert {a["person_id"] for a in cross["common_ancestors"]} == {"P0001", "P0002"}
    assert cross["path_a"][0]["person_id"] == "P0001"
    assert cross["path_b"][0]["person_id"] == "P0001"
    assert "Roderick McCormick" in cross["plain_english_story"]
    assert "2nd cousins" in cross["plain_english_story"].lower()


def test_pr101_api_backward_compatibility_and_living_privacy_guard(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    svc = _make_isolated_tree_service(tmp_path)
    monkeypatch.setattr("app.api.v1.social_plane_router.get_family_tree_service", lambda: svc)

    with TestClient(app) as client:
        data_resp = client.get("/api/v1/community/heritage/tree/data?include_reference=true")
        assert data_resp.status_code == 200
        payload = data_resp.json()
        assert payload["scope"] == "HERITAGE_FAMILY_TREE_NO_FINANCIAL_DATA"
        assert payload["privacy_guard_active"] is True

        sample = next(p for p in payload["people"] if p["person_id"] == "P0028")
        # Legacy fields preserved + new fields present
        for req_key in (
            "person_id",
            "full_name",
            "surname",
            "house_id",
            "generation",
            "generation_from_founders",
            "generation_label",
            "generation_anchor",
            "is_deceased",
            "birth_year",
            "death_year",
            "life_span",
            "privacy_protected",
        ):
            assert req_key in sample
        # Living-member privacy guard still active
        assert sample["is_deceased"] is False
        assert sample["birth_year"] is None
        assert sample["death_year"] is None
        assert sample["privacy_protected"] is True
        for forbidden_key in FORBIDDEN_LIVING_OUTPUT_KEYS:
            assert forbidden_key not in sample

        rel_resp = client.get("/api/v1/community/heritage/tree/relationship?person_a=P0028&person_b=P0526")
        assert rel_resp.status_code == 200
        rel = rel_resp.json()
        for legacy_key in (
            "scope",
            "person_a",
            "person_b",
            "relationship_kind",
            "primary_label",
            "a_to_b_label",
            "b_to_a_label",
            "labels",
            "common_ancestors",
            "a_steps",
            "b_steps",
            "generation_steps",
            "via_marriage",
            "explanation",
            "glossary_definition",
            "path_a",
            "path_b",
            "plain_english_story",
        ):
            assert legacy_key in rel


def test_pr101_zero_financial_imports_zero_cdn_12_portal_parity_and_inventory() -> None:
    # AST check: zero financial/venue imports in heritage/tree modules
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
        assert not leaked, f"Social-plane financial air-gap violation in {path.name}: {leaked}"

    # 12/12 dual-served HTML template byte-for-byte parity & zero external CDNs
    external_tag_re = re.compile(r"<(?:script|link)\b[^>]+(?:src|href)\s*=\s*['\"]https?://", re.IGNORECASE)
    for filename in TWELVE_PORTAL_TEMPLATES:
        api_path = API_V1_DIR / filename
        static_path = STATIC_DIR / filename
        assert api_path.is_file(), f"Missing {api_path}"
        assert static_path.is_file(), f"Missing {static_path}"
        api_bytes = api_path.read_bytes()
        static_bytes = static_path.read_bytes()
        assert api_bytes == static_bytes, f"Byte-for-byte parity drift on {filename}"
        assert external_tag_re.search(api_bytes.decode("utf-8")) is None, f"External CDN tag in {filename}"

    # Verify required PR #101 UI controls exist in heritage_tree.html and jargon is removed
    tree_html = (API_V1_DIR / "heritage_tree.html").read_text(encoding="utf-8")
    assert 'id="toggleFullscreenTreeBtn"' in tree_html
    assert 'id="viewModeTreeBtn"' in tree_html
    assert 'id="viewModeDirectoryBtn"' in tree_html
    assert 'id="clearRelationshipBtn"' in tree_html
    assert 'id="closePersonDrawerBtn"' in tree_html
    assert "FAMILY RELATIONSHIP FINDER" in tree_html
    assert "LOWEST COMMON ANCESTOR (LCA)" not in tree_html
    assert "Generation Steps:" not in tree_html

    # Portal discovery parity gate & inventory check
    report = audit_ui_lexicon_curriculum_parity(REPO_ROOT)
    assert report["passed"] is True, f"Parity audit failed: {report}"
    assert report["undocumented_controls"] == []
    assert generate_inventory(REPO_ROOT) == (REPO_ROOT / "docs" / "PORTAL_COMPONENT_INVENTORY.md").read_text(
        encoding="utf-8"
    )
