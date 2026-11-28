"""Air-Gapped Interactive Family Tree, Living-Member Privacy & Relationship Calculator Service.

STRICT SOCIAL-PLANE FIREWALL (Non-Negotiable):
- ZERO imports or invocations of CapitalLedger, TwoTierRiskEnvelope,
  AutonomousScanWorker, CredentialBroker, or venue adapters.
- ZERO financial balances, dollar totals, or bank/routing credentials.
- Enforces Living-Member Privacy Guard on every public/member read serializer:
  if `is_deceased` is False (or `death_year` is null), exact `birth_year`,
  birthdates, and contact fields are stripped/suppressed server-side.
- Enforces scoped `HOUSE_GENEALOGIST` (own `X-House-ID` branch only) and
  `CHIEF_ADMIN` (enclave-wide) write controls with `GovernanceAuditLog` recording
  on every mutation and HTTP 403 refusal.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
from threading import RLock
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import (
    FamilyTreePersonModel,
    FamilyTreeRelationshipModel,
    HeritageHouseProfileModel,
    HeritageSurnameRecordModel,
    UserRoleAssignmentModel,
)
from app.db.session import Base, SessionLocal, engine as default_engine
from app.domain.authority_tiers import (
    get_governance_audit_log,
    is_chief_admin_deputy_role,
    is_chief_admin_role,
    normalize_role_token,
)
from app.domain.heritage_community_service import (
    HOUSE_HERALDRY_META,
    SEEDED_HOUSES,
    SEEDED_SURNAMES,
    make_surname_slug,
    sanitize_social_text,
)

DEFAULT_SEED_PATH: Path = (
    Path(__file__).resolve().parent.parent / "static" / "data" / "family_tree_seed.json"
)

VALID_HOUSE_IDS: Set[str] = {f"HOUSE-{i:02d}" for i in range(1, 13)} | {"FOUNDERS", "REFERENCE"}
VALID_REL_TYPES: Set[str] = {"parent", "spouse"}

# Known Hall of Arms surname slugs for safe deep-links (zero broken URLs)
_SEEDED_SURNAME_SLUGS: Dict[str, str] = {
    make_surname_slug(entry[0]): entry[0] for entry in SEEDED_SURNAMES
}
_HOUSE_NAME_BY_CODE: Dict[str, str] = {
    h["lineage_code"]: h["house_name"] for h in SEEDED_HOUSES
}
_HOUSE_CREST_BY_CODE: Dict[str, str] = {
    h["lineage_code"]: HOUSE_HERALDRY_META.get(h["house_id"], {}).get(
        "emblem_asset_path", h["crest_asset_path"]
    )
    for h in SEEDED_HOUSES
}

# Suffix extraction regex (strips Jr., Sr., II, III, IV, V, or trailing numeric ordinal like '1')
_SUFFIX_PATTERN = re.compile(
    r"(?:,?\s+)(Jr\.?|Sr\.?|II|III|IV|V|1|2|3)$",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}")
_EXACT_DATE_RE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)

FORBIDDEN_LIVING_OUTPUT_KEYS: Tuple[str, ...] = (
    "birth_date",
    "birthdate",
    "dob",
    "email",
    "phone",
    "telephone",
    "mobile",
    "address",
    "street_address",
    "contact",
    "contact_info",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_suffix_token(raw: Optional[str]) -> str:
    token = " ".join(str(raw or "").strip().split())
    if not token:
        return ""
    lowered = token.rstrip(".").lower()
    if lowered == "jr":
        return "Jr."
    if lowered == "sr":
        return "Sr."
    if lowered in {"ii", "iii", "iv", "v"}:
        return lowered.upper()
    return token[:16]


def normalize_surname_and_suffix(surname: str, suffix: str = "") -> Tuple[str, str]:
    """Strip any trailing suffix (Jr., Sr., II, III, IV, 1, etc.) out of surname into suffix."""
    clean_surname = " ".join(str(surname or "").strip().split())
    clean_suffix = normalize_suffix_token(suffix)
    match = _SUFFIX_PATTERN.search(clean_surname)
    if match:
        extracted = normalize_suffix_token(match.group(1))
        clean_surname = clean_surname[: match.start()].strip().rstrip(",")
        if not clean_suffix:
            clean_suffix = extracted
    return clean_surname, clean_suffix


def normalize_house_code(raw: Optional[str | int]) -> str:
    """Normalize house identifier into HOUSE-01..HOUSE-12, FOUNDERS, or REFERENCE."""
    if raw is None:
        return ""
    text = str(raw).strip().upper()
    if not text:
        return ""
    if text in {"FOUNDERS", "FOUNDER", "ROOT", "FOUNDING"}:
        return "FOUNDERS"
    if text in {"REFERENCE", "REF", "HISTORICAL_REFERENCE"}:
        return "REFERENCE"
    digits = text.replace("HOUSE-", "").replace("HOUSE ", "").replace("HOUSE", "").strip()
    if digits.isdigit():
        num = int(digits)
        if 1 <= num <= 12:
            return f"HOUSE-{num:02d}"
    raise HTTPException(
        status_code=422,
        detail=f"Invalid house_id '{raw}'. Must be HOUSE-01..HOUSE-12, FOUNDERS, or REFERENCE.",
    )


def house_code_to_int(house_code: str) -> Optional[int]:
    if house_code.startswith("HOUSE-"):
        tail = house_code.split("-", 1)[1]
        if tail.isdigit():
            num = int(tail)
            if 1 <= num <= 12:
                return num
    return None


def _sanitize_living_notes(text: str) -> str:
    """Defense-in-depth scrubbing of accidental emails, phone numbers, or exact dates for living people."""
    if not text:
        return ""
    cleaned = _EMAIL_RE.sub("[contact protected]", text)
    cleaned = _PHONE_RE.sub("[contact protected]", cleaned)
    cleaned = _EXACT_DATE_RE.sub("[date protected]", cleaned)
    return cleaned


def _ordinal(n: int) -> str:
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _removed_phrase(diff: int) -> str:
    if diff <= 0:
        return ""
    if diff == 1:
        return "once removed"
    if diff == 2:
        return "twice removed"
    return f"{diff} times removed"


def _great_prefix(greats: int) -> str:
    if greats <= 0:
        return ""
    if greats == 1:
        return "Great-"
    if greats == 2:
        return "Great-Great-"
    return f"{greats}x Great-"


def _bloodline_labels_from_steps(
    da: int,
    db: int,
    *,
    is_half_sibling: bool = False,
) -> Tuple[str, str, str, str]:
    """Return (primary_label, a_to_b_label, b_to_a_label, glossary_definition) for LCA steps (da, db).

    `da` is generations upward from Person A to the Lowest Common Ancestor.
    `db` is generations upward from Person B to the Lowest Common Ancestor.
    """
    if da == 0 and db == 0:
        return (
            "Same Person",
            "Same Person",
            "Same Person",
            "Both selectors point to the exact same individual in the family tree.",
        )
    if da == 0 and db == 1:
        return (
            "Parent / Child",
            "Parent",
            "Child",
            "A direct one-generation parent-and-child bond along the family tree.",
        )
    if da == 1 and db == 0:
        return (
            "Child / Parent",
            "Child",
            "Parent",
            "A direct one-generation child-and-parent bond along the family tree.",
        )
    if da == 0 and db == 2:
        return (
            "Grandparent / Grandchild",
            "Grandparent",
            "Grandchild",
            "Two generations apart along a direct line: Person A is the parent of Person B's parent.",
        )
    if da == 2 and db == 0:
        return (
            "Grandchild / Grandparent",
            "Grandchild",
            "Grandparent",
            "Two generations apart along a direct line: Person B is the parent of Person A's parent.",
        )
    if da == 0 and db >= 3:
        prefix = _great_prefix(db - 2)
        return (
            f"{prefix}Grandparent / {prefix}Grandchild",
            f"{prefix}Grandparent",
            f"{prefix}Grandchild",
            f"Direct lineal ancestor and descendant separated by {db} generations.",
        )
    if da >= 3 and db == 0:
        prefix = _great_prefix(da - 2)
        return (
            f"{prefix}Grandchild / {prefix}Grandparent",
            f"{prefix}Grandchild",
            f"{prefix}Grandparent",
            f"Direct lineal descendant and ancestor separated by {da} generations.",
        )
    if da == 1 and db == 1:
        if is_half_sibling:
            return (
                "Half-Sibling",
                "Half-Sibling",
                "Half-Sibling",
                "Half-siblings share one recorded parent in common and belong to the same generation.",
            )
        return (
            "Sibling",
            "Sibling",
            "Sibling",
            "Siblings share the same parent(s) — each is 1 generation down from their shared parent(s).",
        )
    if da == 1 and db == 2:
        return (
            "Aunt / Uncle & Niece / Nephew",
            "Aunt / Uncle",
            "Niece / Nephew",
            "Person A is a sibling of Person B's parent (1 step vs. 2 steps from the shared ancestor).",
        )
    if da == 2 and db == 1:
        return (
            "Niece / Nephew & Aunt / Uncle",
            "Niece / Nephew",
            "Aunt / Uncle",
            "Person B is a sibling of Person A's parent (2 steps vs. 1 step from the shared ancestor).",
        )
    if da == 1 and db >= 3:
        prefix = _great_prefix(db - 2)
        return (
            f"{prefix}Aunt / {prefix}Uncle & {prefix}Niece / {prefix}Nephew",
            f"{prefix}Aunt / {prefix}Uncle",
            f"{prefix}Niece / {prefix}Nephew",
            f"Person A is a sibling of Person B's direct ancestor ({db - 1} generations above Person B).",
        )
    if da >= 3 and db == 1:
        prefix = _great_prefix(da - 2)
        return (
            f"{prefix}Niece / {prefix}Nephew & {prefix}Aunt / {prefix}Uncle",
            f"{prefix}Niece / {prefix}Nephew",
            f"{prefix}Aunt / {prefix}Uncle",
            f"Person B is a sibling of Person A's direct ancestor ({da - 1} generations above Person A).",
        )

    # Cousins: da >= 2 and db >= 2
    degree = min(da, db) - 1
    removed = abs(da - db)
    deg_label = f"{_ordinal(degree)} Cousin"
    if removed == 0:
        label = deg_label
        glossary = (
            f"{deg_label}s are in the same generation and share a common ancestor "
            f"{degree + 1} generations above each of them "
            f"({'grandparents' if degree == 1 else f'{_great_prefix(degree - 1).lower()}grandparents'})."
        )
    else:
        rem_text = _removed_phrase(removed)
        label = f"{deg_label} {rem_text}"
        glossary = (
            f"The cousin degree ('{deg_label}') counts how close the nearer relative is to the shared ancestor, "
            f"and '{rem_text}' means the two relatives are {removed} generation"
            f"{'' if removed == 1 else 's'} apart from each other."
        )
    return (label, label, label, glossary)


class FamilyTreeService:
    """Persistent, air-gapped Family Tree, Living-Member Privacy & Relationship Calculator service."""

    def __init__(
        self,
        *,
        session_factory: Optional[Callable[[], Session]] = None,
        bind_engine: Any = None,
        seed_path: Optional[Path] = None,
    ) -> None:
        self._lock = RLock()
        self._session_factory = session_factory or SessionLocal
        self._engine = bind_engine or default_engine
        self._seed_path = Path(seed_path) if seed_path is not None else DEFAULT_SEED_PATH
        self._initialized = False
        self._ensure_ready()

    def _ensure_ready(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            Base.metadata.create_all(bind=self._engine)
            with self._session_factory() as db:
                self._seed_from_json_if_empty(db)
            self._initialized = True

    def _seed_from_json_if_empty(self, db: Session) -> None:
        if db.query(FamilyTreePersonModel).count() > 0:
            return
        if not self._seed_path.is_file():
            return
        payload = json.loads(self._seed_path.read_text(encoding="utf-8"))
        now = _utc_now()
        for p in payload.get("people", []):
            clean_surname, clean_suffix = normalize_surname_and_suffix(
                str(p.get("surname") or ""), str(p.get("suffix") or "")
            )
            house_code = normalize_house_code(p.get("house_id") or "FOUNDERS")
            db.add(
                FamilyTreePersonModel(
                    person_id=str(p["person_id"]).strip(),
                    full_name=str(p["full_name"]).strip(),
                    given_name=str(p.get("given_name") or "").strip(),
                    surname=clean_surname,
                    suffix=clean_suffix,
                    nickname=str(p.get("nickname") or "").strip(),
                    house_id=house_code,
                    generation=int(p.get("generation", 0)),
                    is_deceased=1 if bool(p.get("is_deceased", False)) else 0,
                    birth_year=int(p["birth_year"]) if p.get("birth_year") is not None else None,
                    death_year=int(p["death_year"]) if p.get("death_year") is not None else None,
                    bio_notes=str(p.get("bio_notes") or "").strip(),
                    source_tag=str(p.get("source_tag") or "SEED_V1").strip(),
                    review_flag=str(p.get("review_flag") or "").strip(),
                    is_reference_branch=1 if bool(p.get("is_reference_branch", False)) else 0,
                    updated_by="SYSTEM_SEED",
                    updated_at_utc=now,
                )
            )
        db.flush()
        for r in payload.get("relationships", []):
            db.add(
                FamilyTreeRelationshipModel(
                    rel_id=str(r["rel_id"]).strip(),
                    rel_type=str(r["rel_type"]).strip().lower(),
                    person_a_id=str(r["person_a_id"]).strip(),
                    person_b_id=str(r["person_b_id"]).strip(),
                    notes=str(r.get("notes") or "").strip(),
                    source_tag=str(r.get("source_tag") or "SEED_V1").strip(),
                    updated_by="SYSTEM_SEED",
                    updated_at_utc=now,
                )
            )
        db.commit()

    def _known_surname_slugs(self, db: Session) -> Set[str]:
        slugs = set(_SEEDED_SURNAME_SLUGS.keys())
        try:
            for (slug,) in db.query(HeritageSurnameRecordModel.slug).all():
                if slug:
                    slugs.add(str(slug))
        except Exception:
            pass
        return slugs

    @staticmethod
    def serialize_person(
        row: FamilyTreePersonModel,
        *,
        known_surname_slugs: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """Serialize a person record with strict Living-Member Privacy Guard enforced server-side.

        If `is_deceased` is False OR `death_year` is null:
        - `birth_year` and `death_year` are strictly suppressed (`None`).
        - `life_span` is empty (`""`) and `privacy_protected` is `True`.
        - No birthdate or contact fields are ever emitted.
        - `bio_notes` is scrubbed for accidental email/phone/exact-date strings.
        """
        deceased_with_death_year = bool(row.is_deceased) and (row.death_year is not None)
        if deceased_with_death_year:
            birth_year_out: Optional[int] = int(row.birth_year) if row.birth_year is not None else None
            death_year_out: Optional[int] = int(row.death_year)
            life_span = (
                f"{birth_year_out}–{death_year_out}"
                if birth_year_out is not None
                else f"–{death_year_out}"
            )
            safe_bio = str(row.bio_notes or "")
            privacy_protected = False
        else:
            birth_year_out = None
            death_year_out = None
            life_span = ""
            safe_bio = _sanitize_living_notes(str(row.bio_notes or ""))
            privacy_protected = True

        house_code = str(row.house_id or "FOUNDERS")
        h_num = house_code_to_int(house_code)
        house_history_url = f"/community/heritage/house/{h_num}" if h_num is not None else "/community/heritage"
        house_name = (
            _HOUSE_NAME_BY_CODE.get(house_code)
            if h_num is not None
            else ("Founding Spine" if house_code == "FOUNDERS" else "Roderick & Dillie Gaddy Extended Lineage")
        )
        crest_path = (
            _HOUSE_CREST_BY_CODE.get(house_code, "/static/assets/crests/mccormick_crest.jpg")
            if h_num is not None
            else "/static/assets/crests/mccormick_crest.jpg"
        )

        surname_clean = str(row.surname or "").strip()
        surname_slug = ""
        surname_history_url = "/community/heritage"
        if surname_clean:
            try:
                candidate_slug = make_surname_slug(html.unescape(surname_clean))
                slug_pool = known_surname_slugs if known_surname_slugs is not None else set(_SEEDED_SURNAME_SLUGS.keys())
                if candidate_slug in slug_pool:
                    surname_slug = candidate_slug
                    surname_history_url = f"/community/heritage/surname/{candidate_slug}"
            except HTTPException:
                pass

        return {
            "person_id": row.person_id,
            "full_name": row.full_name,
            "given_name": row.given_name,
            "surname": surname_clean,
            "suffix": row.suffix or "",
            "nickname": row.nickname or "",
            "house_id": house_code,
            "house_num": h_num,
            "house_name": house_name,
            "house_history_url": house_history_url,
            "crest_asset_path": crest_path,
            "surname_slug": surname_slug,
            "surname_history_url": surname_history_url,
            "generation": int(row.generation),
            "is_deceased": bool(row.is_deceased),
            "birth_year": birth_year_out,
            "death_year": death_year_out,
            "life_span": life_span,
            "privacy_protected": privacy_protected,
            "bio_notes": safe_bio,
            "source_tag": row.source_tag or "",
            "review_flag": row.review_flag or "",
            "is_reference_branch": bool(row.is_reference_branch),
            "updated_by": row.updated_by or "SYSTEM_SEED",
            "updated_at_utc": row.updated_at_utc or "",
        }

    @staticmethod
    def _serialize_relationship(row: FamilyTreeRelationshipModel) -> Dict[str, Any]:
        return {
            "rel_id": row.rel_id,
            "rel_type": row.rel_type,
            "person_a_id": row.person_a_id,
            "person_b_id": row.person_b_id,
            "notes": row.notes or "",
            "source_tag": row.source_tag or "",
            "updated_by": row.updated_by or "SYSTEM_SEED",
            "updated_at_utc": row.updated_at_utc or "",
        }

    # ------------------------------------------------------------------
    # Read-Only Tree Query API
    # ------------------------------------------------------------------
    def get_tree_data(
        self,
        *,
        house_id: Optional[str] = None,
        surname: Optional[str] = None,
        q: Optional[str] = None,
        include_reference: bool = False,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        house_filter = normalize_house_code(house_id) if (house_id and str(house_id).strip()) else ""
        surname_filter = (surname or "").strip().lower()
        needle = (q or "").strip().lower()

        with self._session_factory() as db:
            known_slugs = self._known_surname_slugs(db)
            all_people_rows = (
                db.query(FamilyTreePersonModel)
                .order_by(
                    FamilyTreePersonModel.is_reference_branch.asc(),
                    FamilyTreePersonModel.generation.asc(),
                    FamilyTreePersonModel.house_id.asc(),
                    FamilyTreePersonModel.person_id.asc(),
                )
                .all()
            )
            all_rel_rows = (
                db.query(FamilyTreeRelationshipModel)
                .order_by(FamilyTreeRelationshipModel.rel_id.asc())
                .all()
            )

            all_serialized = [
                self.serialize_person(r, known_surname_slugs=known_slugs)
                for r in all_people_rows
            ]
            reference_count = sum(1 for p in all_serialized if p["is_reference_branch"])

            # Filter visible people
            base_people = [
                p for p in all_serialized
                if include_reference or not p["is_reference_branch"]
            ]

            matched_people: List[Dict[str, Any]] = []
            for p in base_people:
                if house_filter:
                    # Keep Founders alongside a specific House filter only if requested? No: exact House match
                    if p["house_id"] != house_filter:
                        continue
                if surname_filter and p["surname"].lower() != surname_filter:
                    continue
                if needle:
                    hay = " ".join(
                        [
                            p["person_id"],
                            p["full_name"],
                            p["given_name"],
                            p["surname"],
                            p["suffix"],
                            p["nickname"],
                            p["house_id"],
                            p["house_name"],
                            p["bio_notes"],
                            p["review_flag"],
                        ]
                    ).lower()
                    if needle not in hay:
                        continue
                matched_people.append(p)

            visible_ids = {p["person_id"] for p in matched_people}
            visible_rels = [
                self._serialize_relationship(r)
                for r in all_rel_rows
                if r.person_a_id in visible_ids and r.person_b_id in visible_ids
            ]

            # Build per-person immediate links across the full 25-page graph for Person Detail Card & Relationship Calculator
            all_rels_serialized = [self._serialize_relationship(r) for r in all_rel_rows]

            house_counts: Dict[str, int] = {}
            for p in all_serialized:
                house_counts[p["house_id"]] = house_counts.get(p["house_id"], 0) + 1

            houses_summary: List[Dict[str, Any]] = [
                {
                    "house_id": "FOUNDERS",
                    "house_num": 0,
                    "house_name": 'Founding Pair (Mary Viola "Ola" & William Fletcher McCormick)',
                    "member_count": house_counts.get("FOUNDERS", 0),
                    "crest_asset_path": "/static/assets/crests/mccormick_crest.jpg",
                    "history_url": "/community/heritage",
                }
            ]
            for h in SEEDED_HOUSES:
                code = h["lineage_code"]
                houses_summary.append(
                    {
                        "house_id": code,
                        "house_num": h["house_id"],
                        "house_name": h["house_name"],
                        "member_count": house_counts.get(code, 0),
                        "crest_asset_path": _HOUSE_CREST_BY_CODE.get(code, h["crest_asset_path"]),
                        "history_url": f"/community/heritage/house/{h['house_id']}",
                    }
                )

            distinct_surnames = sorted({p["surname"] for p in all_serialized if p["surname"]})
            living_protected = sum(1 for p in base_people if p["privacy_protected"])
            deceased_dated = sum(1 for p in base_people if not p["privacy_protected"])

            return {
                "scope": "HERITAGE_FAMILY_TREE_NO_FINANCIAL_DATA",
                "privacy_guard_active": True,
                "include_reference": bool(include_reference),
                "reference_branch_count": reference_count,
                "people": matched_people,
                "relationships": visible_rels,
                "catalog_people": all_serialized,
                "catalog_relationships": all_rels_serialized,
                "houses": houses_summary,
                "surnames": distinct_surnames,
                "counts": {
                    "total_people": len(all_serialized),
                    "visible_people": len(matched_people),
                    "living_privacy_protected": living_protected,
                    "deceased_with_dates": deceased_dated,
                    "relationships": len(visible_rels),
                },
            }

    # ------------------------------------------------------------------
    # Live Graph-Based Relationship Calculator ("How Are We Related?")
    # ------------------------------------------------------------------
    def _build_graph(
        self, db: Session
    ) -> Tuple[
        Dict[str, FamilyTreePersonModel],
        Dict[str, Set[str]],
        Dict[str, Set[str]],
        Dict[str, Set[str]],
    ]:
        people = {r.person_id: r for r in db.query(FamilyTreePersonModel).all()}
        parents_of: Dict[str, Set[str]] = {pid: set() for pid in people}
        children_of: Dict[str, Set[str]] = {pid: set() for pid in people}
        spouses_of: Dict[str, Set[str]] = {pid: set() for pid in people}

        for rel in db.query(FamilyTreeRelationshipModel).all():
            a, b, rtype = rel.person_a_id, rel.person_b_id, (rel.rel_type or "").lower()
            if a not in people or b not in people:
                continue
            if rtype == "parent":
                parents_of[b].add(a)
                children_of[a].add(b)
            elif rtype == "spouse":
                spouses_of[a].add(b)
                spouses_of[b].add(a)
        return people, parents_of, children_of, spouses_of

    @staticmethod
    def _ancestors_with_distance(start_id: str, parents_of: Dict[str, Set[str]]) -> Dict[str, int]:
        dist: Dict[str, int] = {start_id: 0}
        queue: deque[str] = deque([start_id])
        while queue:
            curr = queue.popleft()
            curr_d = dist[curr]
            for parent_id in sorted(parents_of.get(curr, ())):
                if parent_id not in dist:
                    dist[parent_id] = curr_d + 1
                    queue.append(parent_id)
        return dist

    def _find_bloodline_match(
        self,
        person_a_id: str,
        person_b_id: str,
        parents_of: Dict[str, Set[str]],
    ) -> Optional[Tuple[int, int, List[str], bool]]:
        anc_a = self._ancestors_with_distance(person_a_id, parents_of)
        anc_b = self._ancestors_with_distance(person_b_id, parents_of)
        shared = set(anc_a.keys()) & set(anc_b.keys())
        if not shared:
            return None

        # Choose minimal total generation steps; collect all tied LCAs (e.g. both Mother & Father)
        best_total = min(anc_a[x] + anc_b[x] for x in shared)
        best_candidates = sorted(x for x in shared if anc_a[x] + anc_b[x] == best_total)
        # Prefer the pair of steps from the primary LCA (deterministic sort by person_id)
        da = anc_a[best_candidates[0]]
        db = anc_b[best_candidates[0]]
        lca_ids = [x for x in best_candidates if anc_a[x] == da and anc_b[x] == db]

        is_half_sibling = False
        if da == 1 and db == 1 and len(lca_ids) == 1:
            pa = parents_of.get(person_a_id, set())
            pb = parents_of.get(person_b_id, set())
            if (pa - pb) and (pb - pa):
                is_half_sibling = True
        return da, db, lca_ids, is_half_sibling

    def _shortest_kinship_path(
        self,
        start_id: str,
        target_id: str,
        parents_of: Dict[str, Set[str]],
        children_of: Dict[str, Set[str]],
        spouses_of: Dict[str, Set[str]],
        max_hops: int = 8,
    ) -> Optional[List[Tuple[str, str]]]:
        """BFS across parent/child/spouse edges for extended married-in explanation."""
        visited: Set[str] = {start_id}
        queue: deque[Tuple[str, List[Tuple[str, str]]]] = deque([(start_id, [])])
        while queue:
            curr, path = queue.popleft()
            if len(path) >= max_hops:
                continue
            neighbors: List[Tuple[str, str]] = []
            for p in sorted(parents_of.get(curr, ())):
                neighbors.append((p, "parent"))
            for c in sorted(children_of.get(curr, ())):
                neighbors.append((c, "child"))
            for s in sorted(spouses_of.get(curr, ())):
                neighbors.append((s, "spouse"))
            for nxt, edge_kind in neighbors:
                if nxt in visited:
                    continue
                nxt_path = path + [(nxt, edge_kind)]
                if nxt == target_id:
                    return nxt_path
                visited.add(nxt)
                queue.append((nxt, nxt_path))
        return None

    def compute_relationship(self, person_a_id: str, person_b_id: str) -> Dict[str, Any]:
        """Compute deterministic LCA bloodline, spouse, or married-in relationship between two people."""
        self._ensure_ready()
        clean_a = str(person_a_id or "").strip()
        clean_b = str(person_b_id or "").strip()
        if not clean_a or not clean_b:
            raise HTTPException(status_code=422, detail="Both person_a and person_b are required.")

        with self._session_factory() as db:
            known_slugs = self._known_surname_slugs(db)
            people, parents_of, children_of, spouses_of = self._build_graph(db)
            if clean_a not in people:
                raise HTTPException(status_code=404, detail=f"Person '{clean_a}' not found in family tree.")
            if clean_b not in people:
                raise HTTPException(status_code=404, detail=f"Person '{clean_b}' not found in family tree.")

            row_a = people[clean_a]
            row_b = people[clean_b]
            ser_a = self.serialize_person(row_a, known_surname_slugs=known_slugs)
            ser_b = self.serialize_person(row_b, known_surname_slugs=known_slugs)

            # 1. Same person
            if clean_a == clean_b:
                primary, a_to_b, b_to_a, glossary = _bloodline_labels_from_steps(0, 0)
                return {
                    "scope": "HERITAGE_FAMILY_TREE_NO_FINANCIAL_DATA",
                    "person_a": ser_a,
                    "person_b": ser_b,
                    "relationship_kind": "SELF",
                    "primary_label": primary,
                    "a_to_b_label": a_to_b,
                    "b_to_a_label": b_to_a,
                    "labels": [primary],
                    "common_ancestors": [ser_a],
                    "a_steps": 0,
                    "b_steps": 0,
                    "generation_steps": {"a_steps": 0, "b_steps": 0},
                    "via_marriage": False,
                    "explanation": f"{ser_a['full_name']} is the same person selected in both fields.",
                    "glossary_definition": glossary,
                }

            # 2. Direct Spouse / Partner
            is_direct_spouse = clean_b in spouses_of.get(clean_a, set())
            bloodline = self._find_bloodline_match(clean_a, clean_b, parents_of)

            if is_direct_spouse:
                labels = ["Spouse / Partner"]
                common_out: List[Dict[str, Any]] = []
                a_steps_out: Optional[int] = None
                b_steps_out: Optional[int] = None
                if bloodline is not None:
                    da, db_steps, lca_ids, is_half = bloodline
                    b_primary, _, _, _ = _bloodline_labels_from_steps(da, db_steps, is_half_sibling=is_half)
                    labels.append(b_primary)
                    common_out = [
                        self.serialize_person(people[x], known_surname_slugs=known_slugs)
                        for x in lca_ids
                    ]
                    a_steps_out, b_steps_out = da, db_steps
                return {
                    "scope": "HERITAGE_FAMILY_TREE_NO_FINANCIAL_DATA",
                    "person_a": ser_a,
                    "person_b": ser_b,
                    "relationship_kind": "SPOUSE",
                    "primary_label": "Spouse / Partner",
                    "a_to_b_label": "Spouse / Partner",
                    "b_to_a_label": "Spouse / Partner",
                    "labels": labels,
                    "common_ancestors": common_out,
                    "a_steps": a_steps_out,
                    "b_steps": b_steps_out,
                    "generation_steps": {"a_steps": a_steps_out, "b_steps": b_steps_out},
                    "via_marriage": True,
                    "explanation": (
                        f"{ser_a['full_name']} and {ser_b['full_name']} are directly recorded as Spouses / Partners."
                    ),
                    "glossary_definition": (
                        "Spouses / Partners are joined by marriage or partnership and unite allied family branches within the Enclave."
                    ),
                }

            # 3. Direct or collateral bloodline relationship via Lowest Common Ancestor(s)
            if bloodline is not None:
                da, db_steps, lca_ids, is_half = bloodline
                primary, a_to_b, b_to_a, glossary = _bloodline_labels_from_steps(
                    da, db_steps, is_half_sibling=is_half
                )
                common_out = [
                    self.serialize_person(people[x], known_surname_slugs=known_slugs)
                    for x in lca_ids
                ]
                anc_names = " & ".join(c["full_name"] for c in common_out)
                if da == 0:
                    explanation = (
                        f"{ser_a['full_name']} is the {a_to_b} of {ser_b['full_name']} "
                        f"({db_steps} generation{'' if db_steps == 1 else 's'} directly above)."
                    )
                elif db_steps == 0:
                    explanation = (
                        f"{ser_a['full_name']} is the {a_to_b} of {ser_b['full_name']} "
                        f"({da} generation{'' if da == 1 else 's'} directly below)."
                    )
                else:
                    explanation = (
                        f"{ser_a['full_name']} is {ser_b['full_name']}'s {a_to_b} "
                        f"(and {ser_b['full_name']} is {ser_a['full_name']}'s {b_to_a}). "
                        f"Top common ancestor(s): {anc_names} (steps: A={da}, B={db_steps})."
                    )
                labels = list(dict.fromkeys([primary, a_to_b, b_to_a]))
                return {
                    "scope": "HERITAGE_FAMILY_TREE_NO_FINANCIAL_DATA",
                    "person_a": ser_a,
                    "person_b": ser_b,
                    "relationship_kind": "BLOODLINE",
                    "primary_label": primary,
                    "a_to_b_label": a_to_b,
                    "b_to_a_label": b_to_a,
                    "labels": labels,
                    "common_ancestors": common_out,
                    "a_steps": da,
                    "b_steps": db_steps,
                    "generation_steps": {"a_steps": da, "b_steps": db_steps},
                    "via_marriage": False,
                    "explanation": explanation,
                    "glossary_definition": glossary,
                }

            # 4. Married-in connection: check if A's spouse shares a bloodline with B, or B's spouse with A
            best_marriage: Optional[Tuple[int, str, str, str, List[str], int, int, str]] = None
            for sp_a in sorted(spouses_of.get(clean_a, set())):
                m = self._find_bloodline_match(sp_a, clean_b, parents_of)
                if m is not None:
                    da, db_steps, lca_ids, is_half = m
                    _, sp_to_b, b_to_sp, _ = _bloodline_labels_from_steps(
                        da, db_steps, is_half_sibling=is_half
                    )
                    score = da + db_steps
                    if best_marriage is None or score < best_marriage[0]:
                        label = f"{sp_to_b} (by marriage)"
                        explanation = (
                            f"{ser_a['full_name']} is connected to {ser_b['full_name']} by marriage: "
                            f"{ser_a['full_name']} is married to {people[sp_a].full_name}, who is "
                            f"{ser_b['full_name']}'s {sp_to_b}."
                        )
                        best_marriage = (
                            score,
                            label,
                            label,
                            f"Spouse of {b_to_sp} (by marriage)",
                            lca_ids,
                            da,
                            db_steps,
                            explanation,
                        )

            for sp_b in sorted(spouses_of.get(clean_b, set())):
                m = self._find_bloodline_match(clean_a, sp_b, parents_of)
                if m is not None:
                    da, db_steps, lca_ids, is_half = m
                    _, a_to_sp, sp_to_a, _ = _bloodline_labels_from_steps(
                        da, db_steps, is_half_sibling=is_half
                    )
                    score = da + db_steps
                    if best_marriage is None or score < best_marriage[0]:
                        label = f"{a_to_sp} (by marriage)"
                        explanation = (
                            f"{ser_a['full_name']} is connected to {ser_b['full_name']} by marriage: "
                            f"{ser_b['full_name']} is married to {people[sp_b].full_name}, and "
                            f"{ser_a['full_name']} is {people[sp_b].full_name}'s {a_to_sp}."
                        )
                        best_marriage = (
                            score,
                            label,
                            f"{a_to_sp} (by marriage)",
                            f"{sp_to_a} (by marriage)",
                            lca_ids,
                            da,
                            db_steps,
                            explanation,
                        )

            if best_marriage is not None:
                _, primary, a_to_b, b_to_a, lca_ids, da, db_steps, explanation = best_marriage
                common_out = [
                    self.serialize_person(people[x], known_surname_slugs=known_slugs)
                    for x in lca_ids
                ]
                return {
                    "scope": "HERITAGE_FAMILY_TREE_NO_FINANCIAL_DATA",
                    "person_a": ser_a,
                    "person_b": ser_b,
                    "relationship_kind": "MARRIED_IN",
                    "primary_label": primary,
                    "a_to_b_label": a_to_b,
                    "b_to_a_label": b_to_a,
                    "labels": list(dict.fromkeys([primary, a_to_b, b_to_a])),
                    "common_ancestors": common_out,
                    "a_steps": da,
                    "b_steps": db_steps,
                    "generation_steps": {"a_steps": da, "b_steps": db_steps},
                    "via_marriage": True,
                    "explanation": explanation,
                    "glossary_definition": (
                        "A married-in (in-law / allied) kinship link connects two family members through a recorded marriage into the shared lineage."
                    ),
                }

            # 5. Extended multi-hop married-in path (e.g., two spouses married into two cousin lines)
            ext_path = self._shortest_kinship_path(
                clean_a, clean_b, parents_of, children_of, spouses_of, max_hops=14
            )
            if ext_path is not None:
                hops = len(ext_path)
                return {
                    "scope": "HERITAGE_FAMILY_TREE_NO_FINANCIAL_DATA",
                    "person_a": ser_a,
                    "person_b": ser_b,
                    "relationship_kind": "MARRIED_IN_EXTENDED",
                    "primary_label": "Connected by Marriage (Extended Family)",
                    "a_to_b_label": "Extended Family (by marriage)",
                    "b_to_a_label": "Extended Family (by marriage)",
                    "labels": ["Connected by Marriage (Extended Family)"],
                    "common_ancestors": [],
                    "a_steps": None,
                    "b_steps": None,
                    "generation_steps": {"a_steps": None, "b_steps": None},
                    "via_marriage": True,
                    "explanation": (
                        f"{ser_a['full_name']} and {ser_b['full_name']} share no direct bloodline ancestor, "
                        f"but are connected through {hops} recorded family and marriage links."
                    ),
                    "glossary_definition": (
                        "Extended relatives by marriage belong to the wider Carmichael — McCormick family circle through allied family unions."
                    ),
                }

            # 6. Disconnected / Historical Reference Branch fallback
            ref_note = ""
            if ser_a["is_reference_branch"] or ser_b["is_reference_branch"]:
                ref_note = (
                    " One or both records currently reside in a Historical Reference Branch awaiting Genealogist verification."
                )
            return {
                "scope": "HERITAGE_FAMILY_TREE_NO_FINANCIAL_DATA",
                "person_a": ser_a,
                "person_b": ser_b,
                "relationship_kind": "DISCONNECTED",
                "primary_label": "No shared recorded bloodline ancestor",
                "a_to_b_label": "No shared recorded bloodline ancestor",
                "b_to_a_label": "No shared recorded bloodline ancestor",
                "labels": ["No shared recorded bloodline ancestor"],
                "common_ancestors": [],
                "a_steps": None,
                "b_steps": None,
                "generation_steps": {"a_steps": None, "b_steps": None},
                "via_marriage": False,
                "explanation": (
                    f"No shared recorded bloodline ancestor or marriage link connects "
                    f"{ser_a['full_name']} and {ser_b['full_name']} yet.{ref_note}"
                ),
                "glossary_definition": (
                    "When two branches do not yet share a documented ancestor in the archive, the calculator reports no shared bloodline rather than guessing."
                ),
            }

    # ------------------------------------------------------------------
    # Scoped HOUSE_GENEALOGIST & CHIEF_ADMIN Write Curation + Audit
    # ------------------------------------------------------------------
    def _authorize_tree_writer(
        self,
        db: Session,
        *,
        target_house_codes: Iterable[str],
        actor_role: Optional[str],
        actor_id: Optional[str],
        claimed_house_id: Optional[int],
        action: str,
        target_id: str,
    ) -> Tuple[str, str]:
        """Enforce strict write boundaries:
        - CHIEF_ADMIN (not CHIEF_ADMIN_DEPUTY): enclave-wide curation.
        - HOUSE_GENEALOGIST: strictly scoped to assigned X-House-ID (HOUSE-01..HOUSE-12).
        - All other roles (CLASS_M, CLASS_T, F1-F3, H1, H2, CHIEF_ADMIN_DEPUTY, anonymous): HTTP 403.
        """
        audit = get_governance_audit_log()
        norm_role = normalize_role_token(actor_role)
        clean_actor = (actor_id or "").strip()
        targets = [normalize_house_code(h) for h in target_house_codes if h]

        if is_chief_admin_deputy_role(norm_role):
            audit.record(
                event_type="FAMILY_TREE_WRITE_DENIED",
                actor_id=clean_actor or "CHIEF_ADMIN_DEPUTY",
                actor_role="CHIEF_ADMIN_DEPUTY",
                target_id=target_id,
                action=action,
                outcome="DENIED_DEPUTY_READ_ONLY",
                http_status=403,
                detail="CHIEF_ADMIN_DEPUTY operates in read-only shadow mode and cannot mutate Family Tree records.",
            )
            raise HTTPException(
                status_code=403,
                detail="DEPUTY_READ_ONLY_FORBIDDEN: CHIEF_ADMIN_DEPUTY cannot mutate Family Tree records.",
            )

        if is_chief_admin_role(norm_role):
            return "CHIEF_ADMIN", clean_actor or "CHIEF_ADMINISTRATOR"

        if norm_role == "HOUSE_GENEALOGIST":
            assigned_house_num: Optional[int] = None
            if clean_actor:
                # If this actor has any assignment record in UserRoleAssignmentModel, enforce it strictly
                active_assignment = (
                    db.query(UserRoleAssignmentModel)
                    .filter(
                        UserRoleAssignmentModel.member_id == clean_actor,
                        UserRoleAssignmentModel.role_token == "HOUSE_GENEALOGIST",
                        UserRoleAssignmentModel.status == "ACTIVE",
                    )
                    .first()
                )
                if active_assignment is not None:
                    assigned_house_num = int(active_assignment.house_id) if active_assignment.house_id else None
                    if claimed_house_id is not None and assigned_house_num is not None and int(claimed_house_id) != assigned_house_num:
                        audit.record(
                            event_type="FAMILY_TREE_WRITE_DENIED",
                            actor_id=clean_actor,
                            actor_role="HOUSE_GENEALOGIST",
                            target_id=target_id,
                            action=action,
                            outcome="DENIED_HOUSE_HEADER_MISMATCH",
                            http_status=403,
                            detail=(
                                f"HOUSE_GENEALOGIST {clean_actor} is assigned to HOUSE-{assigned_house_num:02d} "
                                f"but claimed X-House-ID HOUSE-{claimed_house_id:02d}."
                            ),
                        )
                        raise HTTPException(
                            status_code=403,
                            detail=(
                                f"CROSS_HOUSE_TREE_FORBIDDEN: Assigned to HOUSE-{assigned_house_num:02d}, "
                                f"not HOUSE-{claimed_house_id:02d}."
                            ),
                        )
                else:
                    # Check if revoked or non-genealogist in DB
                    revoked = (
                        db.query(UserRoleAssignmentModel)
                        .filter(
                            UserRoleAssignmentModel.member_id == clean_actor,
                            UserRoleAssignmentModel.role_token == "HOUSE_GENEALOGIST",
                        )
                        .first()
                    )
                    if revoked is not None:
                        audit.record(
                            event_type="FAMILY_TREE_WRITE_DENIED",
                            actor_id=clean_actor,
                            actor_role="HOUSE_GENEALOGIST",
                            target_id=target_id,
                            action=action,
                            outcome="DENIED_REVOKED_GENEALOGIST",
                            http_status=403,
                            detail=f"HOUSE_GENEALOGIST assignment for {clean_actor} is no longer ACTIVE.",
                        )
                        raise HTTPException(
                            status_code=403,
                            detail="GENEALOGIST_ROLE_REVOKED: Active HOUSE_GENEALOGIST assignment required.",
                        )

            if assigned_house_num is None:
                assigned_house_num = claimed_house_id

            if assigned_house_num is None or assigned_house_num < 1 or assigned_house_num > 12:
                audit.record(
                    event_type="FAMILY_TREE_WRITE_DENIED",
                    actor_id=clean_actor or "HOUSE_GENEALOGIST",
                    actor_role="HOUSE_GENEALOGIST",
                    target_id=target_id,
                    action=action,
                    outcome="DENIED_MISSING_HOUSE_SCOPE",
                    http_status=403,
                    detail="HOUSE_GENEALOGIST Family Tree mutation requires a valid assigned X-House-ID (HOUSE-01..HOUSE-12).",
                )
                raise HTTPException(
                    status_code=403,
                    detail="HOUSE_SCOPE_REQUIRED: HOUSE_GENEALOGIST must operate within an assigned X-House-ID (HOUSE-01..HOUSE-12).",
                )

            assigned_code = f"HOUSE-{assigned_house_num:02d}"
            for t_house in targets:
                if t_house != assigned_code:
                    audit.record(
                        event_type="FAMILY_TREE_WRITE_DENIED",
                        actor_id=clean_actor or f"GENEALOGIST-{assigned_code}",
                        actor_role="HOUSE_GENEALOGIST",
                        target_id=target_id,
                        action=action,
                        outcome="DENIED_CROSS_HOUSE_GENEALOGIST",
                        http_status=403,
                        detail=(
                            f"HOUSE_GENEALOGIST scoped to {assigned_code} attempted to mutate {t_house} ({target_id})."
                        ),
                    )
                    raise HTTPException(
                        status_code=403,
                        detail=(
                            f"CROSS_HOUSE_TREE_FORBIDDEN: Your HOUSE_GENEALOGIST authority is scoped strictly to "
                            f"{assigned_code}, not {t_house}."
                        ),
                    )
            return "HOUSE_GENEALOGIST", clean_actor or f"GENEALOGIST-{assigned_code}"

        audit.record(
            event_type="FAMILY_TREE_WRITE_DENIED",
            actor_id=clean_actor or norm_role or "anonymous",
            actor_role=norm_role or "ANONYMOUS",
            target_id=target_id,
            action=action,
            outcome="DENIED_INSUFFICIENT_ROLE",
            http_status=403,
            detail=(
                f"Role '{norm_role or 'ANONYMOUS'}' is not permitted to mutate Family Tree records. "
                "Only assigned HOUSE_GENEALOGIST (own House) or CHIEF_ADMIN may write."
            ),
        )
        raise HTTPException(
            status_code=403,
            detail="FAMILY_TREE_WRITE_FORBIDDEN: Only an assigned HOUSE_GENEALOGIST (own House) or CHIEF_ADMIN may edit the Family Tree.",
        )

    def _next_person_id(self, db: Session) -> str:
        max_num = 0
        for (pid,) in db.query(FamilyTreePersonModel.person_id).all():
            m = re.match(r"^P(\d+)$", str(pid or ""))
            if m:
                max_num = max(max_num, int(m.group(1)))
        return f"P{max_num + 1:04d}"

    def _next_rel_id(self, db: Session) -> str:
        max_num = 0
        for (rid,) in db.query(FamilyTreeRelationshipModel.rel_id).all():
            m = re.match(r"^R(\d+)$", str(rid or ""))
            if m:
                max_num = max(max_num, int(m.group(1)))
        return f"R{max_num + 1:05d}"

    def create_person(
        self,
        *,
        full_name: str,
        given_name: Optional[str] = None,
        surname: str = "",
        suffix: str = "",
        nickname: str = "",
        house_id: str = "HOUSE-01",
        generation: int = 2,
        is_deceased: bool = False,
        birth_year: Optional[int] = None,
        death_year: Optional[int] = None,
        bio_notes: str = "",
        source_tag: str = "GENEALOGIST_ENTRY",
        review_flag: str = "",
        is_reference_branch: bool = False,
        person_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        actor_id: Optional[str] = None,
        claimed_house_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        target_house = normalize_house_code(house_id)
        if is_reference_branch:
            target_house = "REFERENCE"

        safe_full = sanitize_social_text(full_name, field="full_name", maximum=140)
        raw_surname, raw_suffix = normalize_surname_and_suffix(surname, suffix)
        safe_surname = html.escape(raw_surname, quote=True)[:80] if raw_surname else ""
        safe_suffix = html.escape(raw_suffix, quote=True)[:16] if raw_suffix else ""
        safe_given = (
            html.escape(" ".join(str(given_name or "").strip().split()), quote=True)[:80]
            if given_name
            else safe_full.split(" ")[0][:80]
        )
        safe_nick = html.escape(" ".join(str(nickname or "").strip().split()), quote=True)[:60]
        safe_bio = html.escape(" ".join(str(bio_notes or "").strip().split()), quote=True)[:1500]
        safe_source = html.escape(" ".join(str(source_tag or "GENEALOGIST_ENTRY").strip().split()), quote=True)[:80]
        safe_flag = html.escape(" ".join(str(review_flag or "").strip().split()), quote=True)[:240]

        gen_val = max(0, min(15, int(generation)))
        if birth_year is not None and (int(birth_year) < 1600 or int(birth_year) > 2100):
            raise HTTPException(status_code=422, detail="birth_year out of valid range (1600..2100)")
        if death_year is not None and (int(death_year) < 1600 or int(death_year) > 2100):
            raise HTTPException(status_code=422, detail="death_year out of valid range (1600..2100)")

        with self._session_factory() as db:
            new_pid = (person_id or "").strip() or self._next_person_id(db)
            verified_role, verified_actor = self._authorize_tree_writer(
                db,
                target_house_codes=[target_house],
                actor_role=actor_role,
                actor_id=actor_id,
                claimed_house_id=claimed_house_id,
                action="FAMILY_TREE_CREATE_PERSON",
                target_id=f"{target_house}:{new_pid}",
            )
            if db.get(FamilyTreePersonModel, new_pid) is not None:
                raise HTTPException(status_code=409, detail=f"Person ID '{new_pid}' already exists.")

            now = _utc_now()
            row = FamilyTreePersonModel(
                person_id=new_pid,
                full_name=safe_full,
                given_name=safe_given,
                surname=safe_surname,
                suffix=safe_suffix,
                nickname=safe_nick,
                house_id=target_house,
                generation=gen_val,
                is_deceased=1 if bool(is_deceased) else 0,
                birth_year=int(birth_year) if birth_year is not None else None,
                death_year=int(death_year) if death_year is not None else None,
                bio_notes=safe_bio,
                source_tag=safe_source,
                review_flag=safe_flag,
                is_reference_branch=1 if (bool(is_reference_branch) or target_house == "REFERENCE") else 0,
                updated_by=verified_actor,
                updated_at_utc=now,
            )
            db.add(row)
            db.commit()
            db.refresh(row)

            get_governance_audit_log().record(
                event_type="FAMILY_TREE_PERSON_CREATED",
                actor_id=verified_actor,
                actor_role=verified_role,
                target_id=new_pid,
                action="FAMILY_TREE_CREATE_PERSON",
                outcome="CREATED",
                http_status=201,
                detail=f"Added Family Tree person {new_pid} ({safe_full}) in {target_house}.",
            )
            return self.serialize_person(row, known_surname_slugs=self._known_surname_slugs(db))

    def update_person(
        self,
        *,
        person_id: str,
        full_name: Optional[str] = None,
        given_name: Optional[str] = None,
        surname: Optional[str] = None,
        suffix: Optional[str] = None,
        nickname: Optional[str] = None,
        house_id: Optional[str] = None,
        generation: Optional[int] = None,
        is_deceased: Optional[bool] = None,
        birth_year: Optional[int] = None,
        death_year: Optional[int] = None,
        bio_notes: Optional[str] = None,
        source_tag: Optional[str] = None,
        review_flag: Optional[str] = None,
        actor_role: Optional[str] = None,
        actor_id: Optional[str] = None,
        claimed_house_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        clean_pid = str(person_id or "").strip()
        with self._session_factory() as db:
            row = db.get(FamilyTreePersonModel, clean_pid)
            if row is None:
                raise HTTPException(status_code=404, detail=f"Person '{clean_pid}' not found.")

            target_houses = [row.house_id]
            new_house = normalize_house_code(house_id) if (house_id and str(house_id).strip()) else row.house_id
            if new_house != row.house_id:
                target_houses.append(new_house)

            verified_role, verified_actor = self._authorize_tree_writer(
                db,
                target_house_codes=target_houses,
                actor_role=actor_role,
                actor_id=actor_id,
                claimed_house_id=claimed_house_id,
                action="FAMILY_TREE_UPDATE_PERSON",
                target_id=clean_pid,
            )

            if full_name is not None and full_name.strip():
                row.full_name = sanitize_social_text(full_name, field="full_name", maximum=140)
            if given_name is not None:
                row.given_name = html.escape(" ".join(given_name.strip().split()), quote=True)[:80]
            if surname is not None or suffix is not None:
                s_in = surname if surname is not None else row.surname
                sf_in = suffix if suffix is not None else row.suffix
                clean_s, clean_sf = normalize_surname_and_suffix(s_in, sf_in)
                row.surname = html.escape(clean_s, quote=True)[:80]
                row.suffix = html.escape(clean_sf, quote=True)[:16]
            if nickname is not None:
                row.nickname = html.escape(" ".join(nickname.strip().split()), quote=True)[:60]
            if house_id is not None and house_id.strip():
                row.house_id = new_house
                row.is_reference_branch = 1 if new_house == "REFERENCE" else 0
            if generation is not None:
                row.generation = max(0, min(15, int(generation)))
            if is_deceased is not None:
                row.is_deceased = 1 if bool(is_deceased) else 0
            if birth_year is not None:
                if int(birth_year) < 1600 or int(birth_year) > 2100:
                    raise HTTPException(status_code=422, detail="birth_year out of valid range (1600..2100)")
                row.birth_year = int(birth_year)
            if death_year is not None:
                if int(death_year) < 1600 or int(death_year) > 2100:
                    raise HTTPException(status_code=422, detail="death_year out of valid range (1600..2100)")
                row.death_year = int(death_year)
            if bio_notes is not None:
                row.bio_notes = html.escape(" ".join(bio_notes.strip().split()), quote=True)[:1500]
            if source_tag is not None and source_tag.strip():
                row.source_tag = html.escape(" ".join(source_tag.strip().split()), quote=True)[:80]
            if review_flag is not None:
                row.review_flag = html.escape(" ".join(review_flag.strip().split()), quote=True)[:240]

            row.updated_by = verified_actor
            row.updated_at_utc = _utc_now()
            db.commit()
            db.refresh(row)

            get_governance_audit_log().record(
                event_type="FAMILY_TREE_PERSON_UPDATED",
                actor_id=verified_actor,
                actor_role=verified_role,
                target_id=clean_pid,
                action="FAMILY_TREE_UPDATE_PERSON",
                outcome="UPDATED",
                http_status=200,
                detail=f"Updated Family Tree person {clean_pid} ({row.full_name}) in {row.house_id}.",
            )
            return self.serialize_person(row, known_surname_slugs=self._known_surname_slugs(db))

    def create_relationship(
        self,
        *,
        rel_type: str,
        person_a_id: str,
        person_b_id: str,
        notes: str = "",
        source_tag: str = "GENEALOGIST_ENTRY",
        actor_role: Optional[str] = None,
        actor_id: Optional[str] = None,
        claimed_house_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        clean_type = str(rel_type or "").strip().lower()
        if clean_type not in VALID_REL_TYPES:
            raise HTTPException(status_code=422, detail="rel_type must be 'parent' or 'spouse'.")
        clean_a = str(person_a_id or "").strip()
        clean_b = str(person_b_id or "").strip()
        if not clean_a or not clean_b or clean_a == clean_b:
            raise HTTPException(status_code=422, detail="Relationship requires two distinct person IDs.")

        with self._session_factory() as db:
            row_a = db.get(FamilyTreePersonModel, clean_a)
            row_b = db.get(FamilyTreePersonModel, clean_b)
            if row_a is None or row_b is None:
                raise HTTPException(status_code=404, detail="Both person_a_id and person_b_id must exist.")

            verified_role, verified_actor = self._authorize_tree_writer(
                db,
                target_house_codes=[row_a.house_id, row_b.house_id],
                actor_role=actor_role,
                actor_id=actor_id,
                claimed_house_id=claimed_house_id,
                action="FAMILY_TREE_CREATE_RELATIONSHIP",
                target_id=f"{clean_type}:{clean_a}->{clean_b}",
            )

            # Prevent duplicate relationship edge
            existing = (
                db.query(FamilyTreeRelationshipModel)
                .filter(
                    FamilyTreeRelationshipModel.rel_type == clean_type,
                    FamilyTreeRelationshipModel.person_a_id == clean_a,
                    FamilyTreeRelationshipModel.person_b_id == clean_b,
                )
                .first()
            )
            if existing is not None:
                return self._serialize_relationship(existing)
            if clean_type == "spouse":
                rev = (
                    db.query(FamilyTreeRelationshipModel)
                    .filter(
                        FamilyTreeRelationshipModel.rel_type == "spouse",
                        FamilyTreeRelationshipModel.person_a_id == clean_b,
                        FamilyTreeRelationshipModel.person_b_id == clean_a,
                    )
                    .first()
                )
                if rev is not None:
                    return self._serialize_relationship(rev)

            # Prevent direct parent cycle (person_b cannot already be an ancestor of person_a)
            if clean_type == "parent":
                _, parents_of, _, _ = self._build_graph(db)
                anc_of_a = self._ancestors_with_distance(clean_a, parents_of)
                if clean_b in anc_of_a:
                    raise HTTPException(
                        status_code=422,
                        detail="Cyclic lineage rejected: child cannot already be an ancestor of parent.",
                    )

            rel_id = self._next_rel_id(db)
            safe_notes = html.escape(" ".join(str(notes or "").strip().split()), quote=True)[:400]
            safe_source = html.escape(" ".join(str(source_tag or "GENEALOGIST_ENTRY").strip().split()), quote=True)[:80]
            row = FamilyTreeRelationshipModel(
                rel_id=rel_id,
                rel_type=clean_type,
                person_a_id=clean_a,
                person_b_id=clean_b,
                notes=safe_notes,
                source_tag=safe_source,
                updated_by=verified_actor,
                updated_at_utc=_utc_now(),
            )
            db.add(row)
            db.commit()
            db.refresh(row)

            get_governance_audit_log().record(
                event_type="FAMILY_TREE_RELATIONSHIP_CREATED",
                actor_id=verified_actor,
                actor_role=verified_role,
                target_id=rel_id,
                action="FAMILY_TREE_CREATE_RELATIONSHIP",
                outcome="CREATED",
                http_status=201,
                detail=f"Added {clean_type} link {rel_id} ({clean_a} -> {clean_b}).",
            )
            return self._serialize_relationship(row)


_SHARED_FAMILY_TREE_SERVICE: Optional[FamilyTreeService] = None
_TREE_SERVICE_LOCK = RLock()


def get_family_tree_service() -> FamilyTreeService:
    global _SHARED_FAMILY_TREE_SERVICE
    if _SHARED_FAMILY_TREE_SERVICE is None:
        with _TREE_SERVICE_LOCK:
            if _SHARED_FAMILY_TREE_SERVICE is None:
                _SHARED_FAMILY_TREE_SERVICE = FamilyTreeService()
    return _SHARED_FAMILY_TREE_SERVICE
