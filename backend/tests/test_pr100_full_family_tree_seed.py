"""PR #100 verification suite: Complete reconciled 25-page FR 2026 Family Tree dataset,
full-graph integrity, Page 2 deduplication, resolved Excel flags, suffix normalization,
Living-Member Privacy Guard at scale, cross-House & cross-branch Relationship Calculator
(including Roderick & Dillie Gaddy McCormick bridge), zero-financial AST air-gap,
zero-CDN, and 12/12 dual-served HTML template byte-for-byte parity."""
from __future__ import annotations

import ast
from collections import Counter, deque
import json
import pathlib
import re
import time
from typing import Dict, Set

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.domain.family_tree_service import (
    DEFAULT_SEED_PATH,
    FORBIDDEN_LIVING_OUTPUT_KEYS,
    FamilyTreeService,
)

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

_SUFFIX_LEAK_RE = re.compile(r"(?:,?\s+)(Jr\.?|Sr\.?|II|III|IV|V)$", re.IGNORECASE)


def _make_isolated_tree_service(tmp_path: pathlib.Path) -> FamilyTreeService:
    db_file = tmp_path / "pr100_full_tree.db"
    eng = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    return FamilyTreeService(session_factory=session_factory, bind_engine=eng)


def _find_unique(people: list[dict], full_name: str, *, house_id: str | None = None) -> dict:
    matches = [
        p for p in people
        if p["full_name"] == full_name and (house_id is None or p["house_id"] == house_id)
    ]
    assert len(matches) == 1, f"Expected exactly 1 match for {full_name!r} (house={house_id}), found {len(matches)}"
    return matches[0]


def test_pr100_full_seed_referential_integrity_deduplication_and_hygiene() -> None:
    payload = json.loads(DEFAULT_SEED_PATH.read_text(encoding="utf-8"))
    people = payload["people"]
    rels = payload["relationships"]

    # 1. Scale check & zero duplicate person_ids
    assert len(people) >= 850, f"Expected full 25-page dataset (~900+ people), got {len(people)}"
    assert len(rels) >= 1300, f"Expected full 25-page relationships (~1400+), got {len(rels)}"
    ids = [p["person_id"] for p in people]
    assert len(ids) == len(set(ids)), "Duplicate person_id detected in family_tree_seed.json"
    id_set = set(ids)
    by_id = {p["person_id"]: p for p in people}

    # 2. Zero broken person_a_id / person_b_id references & acyclic parent DAG
    parents_of: Dict[str, Set[str]] = {pid: set() for pid in ids}
    children_of: Dict[str, Set[str]] = {pid: set() for pid in ids}
    spouses_of: Dict[str, Set[str]] = {pid: set() for pid in ids}
    for r in rels:
        assert r["person_a_id"] in id_set, f"Broken person_a_id in {r}"
        assert r["person_b_id"] in id_set, f"Broken person_b_id in {r}"
        assert r["person_a_id"] != r["person_b_id"], f"Self-loop in {r}"
        if r["rel_type"] == "parent":
            parents_of[r["person_b_id"]].add(r["person_a_id"])
            children_of[r["person_a_id"]].add(r["person_b_id"])
        elif r["rel_type"] == "spouse":
            spouses_of[r["person_a_id"]].add(r["person_b_id"])
            spouses_of[r["person_b_id"]].add(r["person_a_id"])

    for pid in ids:
        visited: Set[str] = set()
        queue = deque(parents_of[pid])
        while queue:
            curr = queue.popleft()
            assert curr != pid, f"Cycle detected in parent edges at {pid}"
            if curr not in visited:
                visited.add(curr)
                queue.extend(parents_of[curr])

    # 3. Page 2 deduplication: William Vincent Carmichael appears ONCE with 4 children & 2 grandchildren
    wvc = _find_unique(people, "William Vincent Carmichael", house_id="HOUSE-01")
    wvc_children = {by_id[cid]["full_name"] for cid in children_of[wvc["person_id"]]}
    assert wvc_children == {
        "Kennedy Louise Carmichael",
        "Kelby Reni Carmichael",
        "William Chase Carmichael",
        "McKenzie Ann Carmichael",
    }
    kennedy = _find_unique(people, "Kennedy Louise Carmichael", house_id="HOUSE-01")
    kennedy_children = {by_id[cid]["full_name"] for cid in children_of[kennedy["person_id"]]}
    assert kennedy_children == {"Elliot Genandt", "Eleanor Louise Genandt"}

    # 4. Resolved Excel flags
    jwc = _find_unique(people, "John Willie Carmichael", house_id="HOUSE-01")
    gladys = _find_unique(people, "Gladys Bowens", house_id="HOUSE-01")
    esau = _find_unique(people, "Esau Monroe", house_id="HOUSE-01")
    jwc_children = {by_id[cid]["full_name"] for cid in children_of[jwc["person_id"]]}
    assert jwc_children == {
        "Mary Helen Carmichael",
        "James Willie Carmichael",
        "Doris Lee Carmichael",
        "William Fletcher Carmichael",
    }
    esau_children = {by_id[cid]["full_name"] for cid in children_of[esau["person_id"]]}
    assert esau_children == {"Paul Monroe", "Janice Monroe"}
    assert esau["person_id"] in spouses_of[gladys["person_id"]]

    ktwon = _find_unique(people, "K'Twon Whitehead", house_id="HOUSE-01")
    assert {by_id[cid]["full_name"] for cid in children_of[ktwon["person_id"]]} == {"Kamari", "Kayden"}

    tara_tipler = _find_unique(people, "Tara Tipler", house_id="HOUSE-03")
    assert {by_id[cid]["full_name"] for cid in children_of[tara_tipler["person_id"]]} == {
        "Riley McCormick",
        "Mackenzie Marie McCormick",
        "Michael Edward McCormick II",
    }
    _find_unique(people, "Alfred William Web Fowler", house_id="HOUSE-03")

    # 5. Standardized spellings, PDF typo fixes & pure surname / suffix separation
    _find_unique(people, 'Arvell "Son" McCormick', house_id="HOUSE-02")
    _find_unique(people, "Colon McCormick", house_id="HOUSE-09")
    _find_unique(people, "Mabel McCormick Brown", house_id="HOUSE-10")
    _find_unique(people, "Angus Wilton Thompson", house_id="REFERENCE")
    assert not any("Thompon" in p["full_name"] for p in people)
    _find_unique(people, "Damani", house_id="HOUSE-08")
    adrian_jr = _find_unique(people, "Adrian McCormick Jr.", house_id="HOUSE-08")
    assert adrian_jr["surname"] == "McCormick" and adrian_jr["suffix"] == "Jr."
    for p in people:
        assert not _SUFFIX_LEAK_RE.search(p["surname"]), f"Suffix leaked into surname: {p}"

    # 6. Unnamed placeholders preserved as clean review_flag entries
    for name, hid in [
        ("Carla Towns", "HOUSE-01"),
        ("Layanna Jordan", "HOUSE-03"),
        ("Tiera Dixon", "HOUSE-03"),
        ("Sandra McCormick", "HOUSE-03"),
        ("Cynthia Ann McCormick", "HOUSE-03"),
        ('John H. "Uncle Bull" McCormick', "HOUSE-04"),
    ]:
        rec = _find_unique(people, name, house_id=hid)
        assert rec["review_flag"], f"Expected non-empty review_flag for unnamed placeholder on {name}"


def test_pr100_all_12_houses_and_roderick_dillie_gaddy_extended_branches() -> None:
    payload = json.loads(DEFAULT_SEED_PATH.read_text(encoding="utf-8"))
    people = payload["people"]
    rels = payload["relationships"]
    by_id = {p["person_id"]: p for p in people}
    counts = Counter(p["house_id"] for p in people)

    # Founders + all 12 Houses populated
    assert counts["FOUNDERS"] == 2
    for i in range(1, 13):
        code = f"HOUSE-{i:02d}"
        assert counts[code] >= 1, f"{code} must be populated"
    assert counts["HOUSE-01"] >= 150
    assert counts["HOUSE-02"] >= 65
    assert counts["HOUSE-03"] >= 165
    assert counts["HOUSE-04"] >= 30
    assert counts["HOUSE-05"] >= 20
    assert counts["HOUSE-06"] >= 40
    assert counts["HOUSE-07"] == 1  # Murdock "Little Boy" McCormick (no children)
    assert counts["HOUSE-08"] >= 85
    assert counts["HOUSE-09"] >= 4
    assert counts["HOUSE-10"] >= 6
    assert counts["HOUSE-11"] >= 30
    assert counts["HOUSE-12"] >= 25
    assert counts["REFERENCE"] >= 230  # Roderick & Dillie Gaddy II–IX extended branches

    # Roderick & Dillie Gaddy -> Child I Mary Viola "Ola" McCormick + Children II–IX
    roderick = by_id["P0001"]
    dillie = by_id["P0002"]
    ola = by_id["P0004"]
    fletcher = by_id["P0005"]
    assert roderick["full_name"] == "Roderick McCormick" and roderick["is_reference_branch"] is True
    assert dillie["full_name"] == "Dillie Gaddy McCormick" and dillie["is_reference_branch"] is True
    assert "Mary Viola" in ola["full_name"] and ola["house_id"] == "FOUNDERS"
    assert "II–IX" in ola["review_flag"] or "ratification" in ola["review_flag"].lower()
    assert "Not related to Roderick" in fletcher["bio_notes"]
    assert "Not related to Roderick" in fletcher["review_flag"]

    roderick_children = {
        by_id[r["person_b_id"]]["full_name"]
        for r in rels
        if r["rel_type"] == "parent" and r["person_a_id"] == "P0001"
    }
    assert roderick_children == {
        'Mary Viola "Ola" McCormick',
        "Sandy McCormick",
        'Sarah "Sallie" Caroline McCormick',
        'Nancy "Toad" McCormick',
        "Jane McCormick",
        'William "Will" McCormick',
        "Mitchell McCormick",
        "Coy McCormick",
        'Lula "Benton" McCormick',
    }

    # William "Will" & Sophronia "Fronie" Thompson's 13 children verified
    will_vi = _find_unique(people, 'William "Will" McCormick', house_id="REFERENCE")
    will_children = [
        r["person_b_id"] for r in rels if r["rel_type"] == "parent" and r["person_a_id"] == will_vi["person_id"]
    ]
    assert len(will_children) == 13


def test_pr100_living_member_privacy_guard_across_full_dataset(tmp_path: pathlib.Path) -> None:
    svc = _make_isolated_tree_service(tmp_path)
    data = svc.get_tree_data(include_reference=True)
    people = data["people"]
    assert len(people) >= 850

    living_count = 0
    dated_deceased_count = 0
    for p in people:
        for forbidden_key in FORBIDDEN_LIVING_OUTPUT_KEYS:
            assert forbidden_key not in p, f"Forbidden contact/PII key {forbidden_key!r} leaked on {p['person_id']}"
        if not p["is_deceased"]:
            living_count += 1
            assert p["birth_year"] is None, f"Living member {p['full_name']} leaked birth_year={p['birth_year']}"
            assert p["death_year"] is None, f"Living member {p['full_name']} leaked death_year={p['death_year']}"
            assert p["life_span"] == ""
            assert p["privacy_protected"] is True
        elif p["death_year"] is not None:
            dated_deceased_count += 1
            assert p["life_span"] != ""
            assert p["privacy_protected"] is False

    assert living_count >= 800
    assert dated_deceased_count >= 35

    # Verify specific documented historical spans preserved
    by_name_house = {(p["full_name"], p["house_id"]): p for p in people}
    assert by_name_house[('Arvell "Son" McCormick', "HOUSE-02")]["life_span"] == "1895–1975"
    assert by_name_house[("John Willie Carmichael", "HOUSE-01")]["life_span"] == "1918–1949"
    assert by_name_house[("Lula Mae Mosby", "HOUSE-01")]["life_span"] == "1944–2025"
    assert by_name_house[("Wilton Thompson", "REFERENCE")]["life_span"] == "1939–2012"


def test_pr100_relationship_calculator_cross_house_and_cross_branch_at_scale(tmp_path: pathlib.Path) -> None:
    svc = _make_isolated_tree_service(tmp_path)
    data = svc.get_tree_data(include_reference=False)

    # Default view hides REFERENCE from SVG canvas, but catalog_people spans all 25 pages for calculator
    assert not any(p["is_reference_branch"] for p in data["people"])
    assert any(p["is_reference_branch"] for p in data["catalog_people"])

    catalog = data["catalog_people"]
    bertha = _find_unique(catalog, 'Bertha "Bert" McCormick', house_id="HOUSE-01")
    jwc = _find_unique(catalog, "John Willie Carmichael", house_id="HOUSE-01")
    wvc = _find_unique(catalog, "William Vincent Carmichael", house_id="HOUSE-01")
    margaret_k = _find_unique(catalog, "Margaret McCormick Kelley", house_id="HOUSE-03")
    cookie_boy = _find_unique(catalog, 'William "Cookie Boy" McCormick', house_id="HOUSE-03")
    michael_h3 = _find_unique(catalog, "Michael McCormick", house_id="HOUSE-03")
    verney = _find_unique(catalog, "Verney Thompson", house_id="REFERENCE")
    angus = _find_unique(catalog, "Angus Wilton Thompson", house_id="REFERENCE")
    ernest_jr = _find_unique(catalog, "Ernest Linwood Thompson Jr.", house_id="REFERENCE")

    t0 = time.perf_counter()

    # 1. Cross-House (House 01 ↔ House 03) via Mary Viola "Ola" & William Fletcher McCormick
    c1 = svc.compute_relationship(jwc["person_id"], margaret_k["person_id"])
    assert c1["primary_label"] == "1st Cousin"
    assert {a["person_id"] for a in c1["common_ancestors"]} == {"P0004", "P0005"}

    c1r1 = svc.compute_relationship(jwc["person_id"], cookie_boy["person_id"])
    assert c1r1["primary_label"] == "1st Cousin once removed"
    assert {a["person_id"] for a in c1r1["common_ancestors"]} == {"P0004", "P0005"}

    c3 = svc.compute_relationship(wvc["person_id"], michael_h3["person_id"])
    assert c3["primary_label"] == "3rd Cousin"
    assert {a["person_id"] for a in c3["common_ancestors"]} == {"P0004", "P0005"}

    # 2. Cross-Branch (House 01 ↔ Sarah McCormick / Thompson lineage) via Roderick & Dillie Gaddy McCormick
    b_vs_v = svc.compute_relationship(bertha["person_id"], verney["person_id"])
    assert b_vs_v["primary_label"] == "1st Cousin"
    assert {a["person_id"] for a in b_vs_v["common_ancestors"]} == {"P0001", "P0002"}

    jwc_vs_ejr = svc.compute_relationship(jwc["person_id"], ernest_jr["person_id"])
    assert jwc_vs_ejr["primary_label"] == "2nd Cousin"
    assert {a["person_id"] for a in jwc_vs_ejr["common_ancestors"]} == {"P0001", "P0002"}

    wvc_vs_angus = svc.compute_relationship(wvc["person_id"], angus["person_id"])
    assert wvc_vs_angus["primary_label"] == "2nd Cousin twice removed"
    assert {a["person_id"] for a in wvc_vs_angus["common_ancestors"]} == {"P0001", "P0002"}

    # 3. William Fletcher McCormick vs Roderick McCormick is MARRIED_IN (NOT bloodline — IMG01 preserved!)
    fletcher_vs_rod = svc.compute_relationship("P0005", "P0001")
    assert fletcher_vs_rod["relationship_kind"] == "MARRIED_IN"
    assert fletcher_vs_rod["via_marriage"] is True

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_ms < 2000.0, f"7 full-graph relationship computations took too long: {elapsed_ms:.1f}ms"


def test_pr100_zero_financial_imports_zero_cdn_and_12_portal_template_parity() -> None:
    # AST check for zero financial/venue imports in heritage/tree modules
    for path in (
        BACKEND_DIR / "app" / "domain" / "family_tree_service.py",
        BACKEND_DIR / "app" / "domain" / "heritage_community_service.py",
        BACKEND_DIR / "app" / "api" / "v1" / "social_plane_router.py",
        BACKEND_DIR / "scripts" / "import_family_tree_excel.py",
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
