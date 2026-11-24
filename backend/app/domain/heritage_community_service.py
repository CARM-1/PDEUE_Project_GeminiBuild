"""Isolated Social, Hall of Arms Heritage & Family Communications Service.

STRICT SOCIAL-PLANE FIREWALL (Non-Negotiable):
- ZERO imports or invocations of CapitalLedger, TwoTierRiskEnvelope,
  AutonomousScanWorker, CredentialBroker, or venue adapters.
- ZERO financial balances, dollar totals, or bank/routing references stored or
  rendered anywhere in this module.
- Strict XSS sanitization / HTML escaping on all family posts, House history
  entries, surname bios, and broadcast notifications.
- Scoped House Genealogist write control verified server-side against the
  relational UserRoleAssignmentModel registry (own House only) or CHIEF_ADMIN,
  with GovernanceAuditLog recording on every edit or HTTP 403 refusal.
"""
from __future__ import annotations

from datetime import datetime, timezone
import html
import json
import re
from threading import RLock
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import (
    CommunityNotificationModel,
    HeritageHouseProfileModel,
    HeritageSurnameRecordModel,
    UserRoleAssignmentModel,
)
from app.db.session import Base, SessionLocal, engine as default_engine
from app.domain.authority_tiers import (
    get_governance_audit_log,
    is_chief_admin_role,
    normalize_role_token,
)
from app.domain.notification_gateway import (
    NotificationGateway,
    NotificationMessage,
    get_notification_gateway,
    sanitize_notification_text,
)

POST_CATEGORIES: Tuple[str, ...] = ("Announcements", "Milestones", "Reunions", "General")

_SCRIPT_BLOCK_RE = re.compile(
    r"(?is)<\s*(?:script|style|iframe|object|embed)[^>]*>.*?<\s*/\s*(?:script|style|iframe|object|embed)\s*>"
)
_HTML_TAG_RE = re.compile(r"(?s)<[^>]+>")
_SLUG_CLEAN_RE = re.compile(r"[^a-z0-9]+")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_social_text(value: str, *, field: str, maximum: int, allow_newlines: bool = False) -> str:
    """Normalize whitespace, enforce bounds, and HTML-escape so markup/XSS renders strictly as inert text."""
    raw = str(value or "")
    if allow_newlines:
        lines = [" ".join(line.strip().split()) for line in raw.splitlines()]
        normalized = "\n".join(line for line in lines if line)
    else:
        normalized = " ".join(raw.strip().split())
    if not normalized:
        raise HTTPException(status_code=422, detail=f"{field} must not be empty")
    if len(normalized) > maximum:
        raise HTTPException(status_code=422, detail=f"{field} exceeds {maximum} characters")
    return html.escape(normalized, quote=True)


def make_surname_slug(surname: str) -> str:
    clean = _SLUG_CLEAN_RE.sub("-", surname.strip().lower()).strip("-")
    if not clean:
        raise HTTPException(status_code=422, detail="surname must contain letters or numbers")
    return clean[:64]


# Two-scale heraldic metadata per House (emblem, achievement, lineage descent, and Scottish bordure differencing)
HOUSE_HERALDRY_META: Dict[int, Dict[str, Any]] = {
    1: {
        "lineage_descent": "Carmichael Line — Descending from Eldest McCormick Daughter",
        "is_bordure_differenced": False,
        "border_style": "Wreathed Fess & Hyndford Eagle",
        "tincture": "Azure, Gules & Gold/Black/Green Ribbon",
        "blazon_note": (
            "Hyndford eagle bearing the Carmichael blue-and-crimson wreathed inescutcheon, armored arm with "
            "broken spear, TOUJOURS PREST scroll, knight and crowned golden African lion supporters, Scottish thistles, "
            "and gold/black/green heritage accent ribbon."
        ),
        "emblem_asset_path": "/static/assets/crests/carmichael_crest.svg",
        "achievement_asset_path": "/static/assets/crests/carmichael_achievement.svg",
    },
    2: {
        "lineage_descent": "Foundational McCormick Stock — Senior Cadency (House 02)",
        "is_bordure_differenced": True,
        "border_style": "Engrailed",
        "tincture": "Sable (Black)",
        "blazon_note": "Foundational McCormick core (three royal-blue eagles & crimson zigzag fess dancetté) within a Bordure engrailed Sable.",
        "emblem_asset_path": "/static/assets/crests/house_02_mccormick_bordure.svg",
        "achievement_asset_path": "/static/assets/crests/mccormick_achievement.svg",
    },
    3: {
        "lineage_descent": "Foundational McCormick Stock — Scottish Bordure Differencing (House 03)",
        "is_bordure_differenced": True,
        "border_style": "Indented",
        "tincture": "Or (Gold)",
        "blazon_note": "Foundational McCormick shield core differenced by a Bordure indented Or (Gold).",
        "emblem_asset_path": "/static/assets/crests/house_03_mccormick_bordure.svg",
        "achievement_asset_path": "/static/assets/crests/house_03_mccormick_bordure.svg",
    },
    4: {
        "lineage_descent": "Foundational McCormick Stock — Scottish Bordure Differencing (House 04)",
        "is_bordure_differenced": True,
        "border_style": "Wavy",
        "tincture": "Azure (Royal Blue)",
        "blazon_note": "Foundational McCormick shield core differenced by a Bordure wavy Azure (Royal Blue).",
        "emblem_asset_path": "/static/assets/crests/house_04_mccormick_bordure.svg",
        "achievement_asset_path": "/static/assets/crests/house_04_mccormick_bordure.svg",
    },
    5: {
        "lineage_descent": "Foundational McCormick Stock — Scottish Bordure Differencing (House 05)",
        "is_bordure_differenced": True,
        "border_style": "Invected",
        "tincture": "Vert (Forest Green)",
        "blazon_note": "Foundational McCormick shield core differenced by a Bordure invected Vert (Forest Green).",
        "emblem_asset_path": "/static/assets/crests/house_05_mccormick_bordure.svg",
        "achievement_asset_path": "/static/assets/crests/house_05_mccormick_bordure.svg",
    },
    6: {
        "lineage_descent": "Foundational McCormick Stock — Scottish Bordure Differencing (House 06)",
        "is_bordure_differenced": True,
        "border_style": "Embattled",
        "tincture": "Gules (Crimson)",
        "blazon_note": "Foundational McCormick shield core differenced by a Bordure embattled Gules (Crimson).",
        "emblem_asset_path": "/static/assets/crests/house_06_mccormick_bordure.svg",
        "achievement_asset_path": "/static/assets/crests/house_06_mccormick_bordure.svg",
    },
    7: {
        "lineage_descent": "Foundational McCormick Stock — Scottish Bordure Differencing (House 07)",
        "is_bordure_differenced": True,
        "border_style": "Compony",
        "tincture": "Or & Vert (Gold/Green)",
        "blazon_note": "Foundational McCormick shield core differenced by a Bordure compony Or and Vert (Gold & Green).",
        "emblem_asset_path": "/static/assets/crests/house_07_mccormick_bordure.svg",
        "achievement_asset_path": "/static/assets/crests/house_07_mccormick_bordure.svg",
    },
    8: {
        "lineage_descent": "Foundational McCormick Stock — Scottish Bordure Differencing (House 08)",
        "is_bordure_differenced": True,
        "border_style": "Engrailed Fimbriated",
        "tincture": "Azure & Or (Blue/Gold)",
        "blazon_note": "Foundational McCormick shield core differenced by a Bordure engrailed Azure fimbriated Or.",
        "emblem_asset_path": "/static/assets/crests/house_08_mccormick_bordure.svg",
        "achievement_asset_path": "/static/assets/crests/house_08_mccormick_bordure.svg",
    },
    9: {
        "lineage_descent": "Foundational McCormick Stock — Scottish Bordure Differencing (House 09)",
        "is_bordure_differenced": True,
        "border_style": "Indented",
        "tincture": "Gules (Crimson)",
        "blazon_note": "Foundational McCormick shield core differenced by a Bordure indented Gules (Crimson).",
        "emblem_asset_path": "/static/assets/crests/house_09_mccormick_bordure.svg",
        "achievement_asset_path": "/static/assets/crests/house_09_mccormick_bordure.svg",
    },
    10: {
        "lineage_descent": "Foundational McCormick Stock — Scottish Bordure Differencing (House 10)",
        "is_bordure_differenced": True,
        "border_style": "Embattled Fimbriated",
        "tincture": "Sable & Or (Black/Gold)",
        "blazon_note": "Foundational McCormick shield core differenced by a Bordure embattled Sable fimbriated Or.",
        "emblem_asset_path": "/static/assets/crests/house_10_mccormick_bordure.svg",
        "achievement_asset_path": "/static/assets/crests/house_10_mccormick_bordure.svg",
    },
    11: {
        "lineage_descent": "Foundational McCormick Stock — Scottish Bordure Differencing (House 11)",
        "is_bordure_differenced": True,
        "border_style": "Wavy",
        "tincture": "Vert (Highland Green)",
        "blazon_note": "Foundational McCormick shield core differenced by a Bordure wavy Vert (Highland Green).",
        "emblem_asset_path": "/static/assets/crests/house_11_mccormick_bordure.svg",
        "achievement_asset_path": "/static/assets/crests/house_11_mccormick_bordure.svg",
    },
    12: {
        "lineage_descent": "Foundational McCormick Stock — Scottish Bordure Differencing (House 12)",
        "is_bordure_differenced": True,
        "border_style": "Invected",
        "tincture": "Or (Burnished Gold)",
        "blazon_note": "Foundational McCormick shield core differenced by a Bordure invected Or (Burnished Gold).",
        "emblem_asset_path": "/static/assets/crests/house_12_mccormick_bordure.svg",
        "achievement_asset_path": "/static/assets/crests/house_12_mccormick_bordure.svg",
    },
}

# Canonical seed catalog for all 12 Houses (strictly heritage/lineage data, zero financial data)
SEEDED_HOUSES: Tuple[Dict[str, Any], ...] = (
    {
        "house_id": 1,
        "lineage_code": "HOUSE-01",
        "house_name": "House of Carmichael Prime",
        "motto": "Toujours Prest — Always Ready in Stewardship",
        "crest_asset_path": "/static/assets/crests/carmichael_crest.svg",
        "founding_branch": "Carmichael Line — Descending from Eldest McCormick Daughter",
        "history_body": (
            "Descending from the eldest McCormick daughter and anchored by the Carmichael covenant, House 01 "
            "preserves the family charter of generational love, harmony, resilience, and shared stewardship. "
            "Elders and younger relatives gather here to chronicle reunion stories, mentorship traditions, and service milestones."
        ),
        "milestones": [
            "Founding Charter ratified uniting the eldest McCormick daughter's Carmichael line with Houses 02–12",
            "First multi-generational oral history archive opened for House Genealogists",
        ],
    },
    {
        "house_id": 2,
        "lineage_code": "HOUSE-02",
        "house_name": "House of McCormick Prime",
        "motto": "Sine Timore — Steadfast Without Fear",
        "crest_asset_path": "/static/assets/crests/house_02_mccormick_bordure.svg",
        "founding_branch": "McCormick Foundational Stock · Bordure Engrailed Sable",
        "history_body": (
            "Carrying the foundational McCormick arms (three royal-blue eagles, crimson zigzag fess dancetté, and "
            "black engrailed border), House 02 anchors the eleven McCormick-stock Houses through family education, "
            "mentoring circles, and annual lineage gatherings."
        ),
        "milestones": [
            "Co-founding twin crest dedication uniting Carmichael and foundational McCormick lines",
            "Apprentice fellowship reading circle launched for younger family branches",
        ],
    },
    {
        "house_id": 3,
        "lineage_code": "HOUSE-03",
        "house_name": "House of the Highland Hearth",
        "motto": "Warmth Kept for Every Generation",
        "crest_asset_path": "/static/assets/crests/house_03_mccormick_bordure.svg",
        "founding_branch": "McCormick Stock · Bordure Indented Or (Gold)",
        "history_body": (
            "Descending from the foundational McCormick stock with a Scottish indented gold bordure, House 03 "
            "honors the welcoming kitchen tables and holiday gatherings that knit cousins together across states."
        ),
        "milestones": ["Autumn lineage reunion hosting rotation established"],
    },
    {
        "house_id": 4,
        "lineage_code": "HOUSE-04",
        "house_name": "House of the Riverbend",
        "motto": "Steady Current, Deep Roots",
        "crest_asset_path": "/static/assets/crests/house_04_mccormick_bordure.svg",
        "founding_branch": "McCormick Stock · Bordure Wavy Azure (Blue)",
        "history_body": (
            "Bearing the foundational McCormick eagles and crimson zigzag framed by a wavy royal-blue bordure, "
            "House 04 honors the tradespeople, teachers, and builders of the mid-century family diaspora."
        ),
        "milestones": ["Craft & mentorship directory opened for cousins entering trades and engineering"],
    },
    {
        "house_id": 5,
        "lineage_code": "HOUSE-05",
        "house_name": "House of the Oak & Compass",
        "motto": "Guided by Wisdom, Grounded in Kin",
        "crest_asset_path": "/static/assets/crests/house_05_mccormick_bordure.svg",
        "founding_branch": "McCormick Stock · Bordure Invected Vert (Green)",
        "history_body": (
            "Distinguished by a forest-green invected bordure around the foundational McCormick shield, House 05 "
            "celebrates lifelong learning, plain-English financial literacy, and calm long-term planning."
        ),
        "milestones": ["Completed 12 consecutive weeks of family learning seminars"],
    },
    {
        "house_id": 6,
        "lineage_code": "HOUSE-06",
        "house_name": "House of the Watchtower",
        "motto": "Vigilant Care for Those We Love",
        "crest_asset_path": "/static/assets/crests/house_06_mccormick_bordure.svg",
        "founding_branch": "McCormick Stock · Bordure Embattled Gules (Crimson)",
        "history_body": (
            "Bearing a crimson embattled bordure around the foundational McCormick shield, House 06 is dedicated "
            "to community readiness, elder wellness check-ins, and mutual aid so no relative stands alone."
        ),
        "milestones": ["Established quarterly senior check-in and tech-help phone tree"],
    },
    {
        "house_id": 7,
        "lineage_code": "HOUSE-07",
        "house_name": "House of the Cedar Grove",
        "motto": "Patience Builds What Storms Cannot Shake",
        "crest_asset_path": "/static/assets/crests/house_07_mccormick_bordure.svg",
        "founding_branch": "McCormick Stock · Bordure Compony Or & Vert",
        "history_body": (
            "Framed by an alternating gold-and-green compony bordure around the McCormick stock core, House 07 "
            "preserves homestead memories, family recipes, and letters exchanged across generations."
        ),
        "milestones": ["Digitized 40+ heirloom family photographs and reunion letters"],
    },
    {
        "house_id": 8,
        "lineage_code": "HOUSE-08",
        "house_name": "House of the Silver Loom",
        "motto": "Many Threads, One Unbroken Fabric",
        "crest_asset_path": "/static/assets/crests/house_08_mccormick_bordure.svg",
        "founding_branch": "McCormick Stock · Bordure Engrailed Azure & Or",
        "history_body": (
            "Wearing a royal-blue engrailed bordure fimbriated in gold around the foundational McCormick arms, "
            "House 08 weaves married-in families and regional traditions into one harmonious family tapestry."
        ),
        "milestones": ["Allied surname welcome charter published in Hall of Arms"],
    },
    {
        "house_id": 9,
        "lineage_code": "HOUSE-09",
        "house_name": "House of the Lantern Bearers",
        "motto": "Light the Path for the Next Footstep",
        "crest_asset_path": "/static/assets/crests/house_09_mccormick_bordure.svg",
        "founding_branch": "McCormick Stock · Bordure Indented Gules (Crimson)",
        "history_body": (
            "Differenced with a crimson indented bordure around the foundational McCormick shield, House 09 "
            "champions youth scholarships, graduation milestones, and the Pay-it-Forward spirit."
        ),
        "milestones": ["Five learners earned PDEUE University Foundations badges"],
    },
    {
        "house_id": 10,
        "lineage_code": "HOUSE-10",
        "house_name": "House of the Stone Bridge",
        "motto": "Built to Carry Our Grandchildren",
        "crest_asset_path": "/static/assets/crests/house_10_mccormick_bordure.svg",
        "founding_branch": "McCormick Stock · Bordure Embattled Sable & Or",
        "history_body": (
            "Framed in a black-and-gold embattled bordure around the foundational McCormick core, House 10 "
            "remembers the engineers, nurses, and civic volunteers who built lasting bridges between generations."
        ),
        "milestones": ["Recorded oral histories from three senior family elders"],
    },
    {
        "house_id": 11,
        "lineage_code": "HOUSE-11",
        "house_name": "House of the Southern Star",
        "motto": "True North in Every Season",
        "crest_asset_path": "/static/assets/crests/house_11_mccormick_bordure.svg",
        "founding_branch": "McCormick Stock · Bordure Wavy Vert (Green)",
        "history_body": (
            "Differenced by a Highland-green wavy bordure around the foundational McCormick arms, House 11 "
            "connects far-flung cousins across southern and coastal corridors through video seminars and broadcasts."
        ),
        "milestones": ["Hosted inaugural cross-time-zone Family Assembly video gathering"],
    },
    {
        "house_id": 12,
        "lineage_code": "HOUSE-12",
        "house_name": "House of the Harvest Table",
        "motto": "Gratitude Shared Multiplies the Blessing",
        "crest_asset_path": "/static/assets/crests/house_12_mccormick_bordure.svg",
        "founding_branch": "McCormick Stock · Bordure Invected Or (Gold)",
        "history_body": (
            "Completing the circle of twelve Houses with a burnished-gold invected bordure around the foundational "
            "McCormick shield, House 12 stewards thanksgiving traditions and welcoming ceremonies for newborn and newly married kin."
        ),
        "milestones": ["Welcomed the newest generation of enclave children in the Hearth book"],
    },
)

# 2 Founding Surnames + 28 Allied/Married-In Surnames = 30 Surnames total
SEEDED_SURNAMES: Tuple[Tuple[str, int, int, str, str], ...] = (
    # (surname, is_founding, house_id, origin_summary, history_body)
    (
        "Carmichael",
        1,
        1,
        "Founding Pillar · Lanarkshire & Highland stewardship heritage",
        "Co-founding lineage of the FUTURE Enclave. Known across generations for preparedness, principled stewardship, and gathering extended kin under a shared covenant of resilience.",
    ),
    (
        "McCormick",
        1,
        2,
        "Founding Pillar · Steadfast resilience, scholarship, and kinship",
        "Co-founding lineage of the FUTURE Enclave. Celebrated for calm leadership, deep devotion to family education, and passing down generational harmony without fear.",
    ),
    ("Vance", 0, 1, "Allied Lineage · House 01 stewardship & advisory branch", "Longstanding allied family line contributing mentorship, household organization, and generational recordkeeping to House 01."),
    ("Sinclair", 0, 1, "Allied Lineage · Coastal navigators and chronicle keepers", "Connected by marriage into the Carmichael pillar, the Sinclair branch brings a heritage of archival storytelling and steady counsel."),
    ("Campbell", 0, 2, "Allied Lineage · Highland kin & educators", "United with House 02 through marriage, the Campbell line has fostered teachers, mentors, and reunion organizers across three generations."),
    ("Stewart", 0, 2, "Allied Lineage · Civic stewards and family musicians", "Allied to the McCormick pillar, the Stewart relatives are treasured for bringing music, grace, and community leadership to every gathering."),
    ("MacLeod", 0, 3, "Allied Lineage · Hospitality and hearth-keeping branch", "Rooted in House 03, the MacLeod family line anchors annual autumn reunions and preserves traditional family recipes."),
    ("Douglas", 0, 3, "Allied Lineage · Builders and rural homesteaders", "Married into House 03, the Douglas lineage contributed skilled carpentry, land stewardship, and warm southern hospitality."),
    ("Graham", 0, 4, "Allied Lineage · Craftsmanship and railway heritage", "Part of House 04, the Graham relatives share stories of mechanics, engineers, and dependable craftsmanship passed down to younger cousins."),
    ("Henderson", 0, 4, "Allied Lineage · Educators and community librarians", "Linked with House 04, the Henderson line champions reading literacy, local history preservation, and calm practical advice."),
    ("Morrison", 0, 4, "Allied Lineage · Mariners and coastal trades", "Allied with House 04, the Morrison branch brings maritime discipline, weather wisdom, and tight-knit cousin friendships."),
    ("Wallace", 0, 5, "Allied Lineage · Endurance and plain-spoken integrity", "Rooted in House 05, the Wallace family stands for clear speech, honoring commitments, and encouraging apprentices."),
    ("Fraser", 0, 5, "Allied Lineage · Gardeners, botanists, and teachers", "Connected to House 05, the Fraser line keeps family seed-saving traditions and plain-English study guides thriving."),
    ("Kerr", 0, 5, "Allied Lineage · Watchmakers and precision craft", "Allied to House 05, the Kerr branch embodies careful attention to detail and patient multi-year planning."),
    ("Murray", 0, 6, "Allied Lineage · Community healthcare and caregiving", "Part of House 06, the Murray line honors nurses, caregivers, and relatives who quietly look out for family elders."),
    ("Reid", 0, 6, "Allied Lineage · Rural physicians and neighborhood guides", "United with House 06, the Reid relatives organize wellness check-ins and support relatives through major life transitions."),
    ("Duncan", 0, 7, "Allied Lineage · Homestead chroniclers and letter-writers", "Rooted in House 07, the Duncan branch safeguarded generations of family correspondence, Bibles, and reunion photographs."),
    ("Hamilton", 0, 7, "Allied Lineage · Civic clerks and archive builders", "Allied to House 07, the Hamilton family contributed meticulous family tree charts and warm holiday traditions."),
    ("Ross", 0, 7, "Allied Lineage · Orchard keepers and seasonal hosts", "Connected with House 07, the Ross relatives hosted summer picnics that introduced cousins across distant states."),
    ("Grant", 0, 8, "Allied Lineage · Weavers of allied family traditions", "Rooted in House 08, the Grant line celebrates blending married-in cultural traditions into a united family hearth."),
    ("Ferguson", 0, 8, "Allied Lineage · Artisans and small-business stewards", "Allied to House 08, the Ferguson relatives exemplify honest neighborhood commerce and mentoring first-time builders."),
    ("Robertson", 0, 9, "Allied Lineage · Scholarship patrons and youth coaches", "Part of House 09, the Robertson family cheers on graduates, coaches youth teams, and encourages lifelong curiosity."),
    ("Cameron", 0, 9, "Allied Lineage · Mentors and academy volunteers", "Connected to House 09, the Cameron line helps new relatives feel at home in PDEUE University and mentor circles."),
    ("MacKenzie", 0, 10, "Allied Lineage · Bridge builders and civil engineers", "Rooted in House 10, the MacKenzie branch honors relatives who designed roads, clinics, and lasting civic works."),
    ("Paterson", 0, 10, "Allied Lineage · Educators and choir directors", "Allied to House 10, the Paterson relatives unite generations through song, teaching, and milestone dedications."),
    ("Johnston", 0, 11, "Allied Lineage · Coastal travelers and family connectors", "Part of House 11, the Johnston branch keeps far-away relatives linked through regular calls and holiday visits."),
    ("Crawford", 0, 11, "Allied Lineage · Aviators, technicians, and problem-solvers", "Connected to House 11, the Crawford relatives bring curiosity, technical reliability, and calm troubleshooting."),
    ("Boyd", 0, 11, "Allied Lineage · Storytelling elders and cooks", "Allied with House 11, the Boyd family keeps Sunday dinner fellowship and warm cross-generational conversation alive."),
    ("Montgomery", 0, 12, "Allied Lineage · Reunion planners and welcome hosts", "Rooted in House 12, the Montgomery relatives coordinate milestone welcomes for births, marriages, and graduations."),
    ("Elliott", 0, 12, "Allied Lineage · Harvest stewards and gratitude chroniclers", "Allied to House 12, the Elliott line preserves the annual family gratitude ledger and welcomes every new relative warmly."),
)

# Jitsi seminar & family call presets (sandboxed iframe only)
JITSI_ROOM_PRESETS: Tuple[Dict[str, Any], ...] = (
    {
        "preset_id": "enclave-assembly",
        "label": "Enclave Broadcast / Family Assembly",
        "room_slug": "PDEUELineageAcademyClassroom",
        "embed_url": "https://meet.jit.si/PDEUELineageAcademyClassroom",
        "description": "All-family town hall, reunion broadcast, and quarterly celebration room.",
        "kind": "BROADCAST",
    },
    {
        "preset_id": "house-meeting",
        "label": "House Meeting (Houses 1–12)",
        "room_slug_template": "PDEUEHouse{house_id:02d}Gathering",
        "embed_url_template": "https://meet.jit.si/PDEUEHouse{house_id:02d}Gathering",
        "description": "Dedicated video parlor for your individual House gathering and elders check-in.",
        "kind": "HOUSE",
    },
    {
        "preset_id": "mentor-checkin",
        "label": "1-on-1 Mentor Check-In",
        "room_slug": "PDEUEMentorCheckInParlor",
        "embed_url": "https://meet.jit.si/PDEUEMentorCheckInParlor",
        "description": "Calm one-on-one room for walking through PDEUE University guides or family questions.",
        "kind": "MENTOR",
    },
)

# Plain-English Pay-it-Forward (LCCF) Charter (strictly educational / zero account balances)
PAY_IT_FORWARD_LCCF_CHARTER: Dict[str, Any] = {
    "title": "Pay-it-Forward (LCCF) Sponsorship Charter",
    "subtitle": "Lifting relatives out of high-interest debt and starting a better financial chapter — without ever mixing accounts.",
    "pillars": [
        {
            "heading": "1. Voluntary Patron Sponsorship via IFAS",
            "body": (
                "Solvent family Patrons who want to bless a relative may voluntarily sponsor a seed contribution "
                "or high-interest debt relief gift strictly through the independent IFAS banking & accounting plane. "
                "PDEUE never touches bank routing numbers or account credentials."
            ),
        },
        {
            "heading": "2. Strict Zero Cross-Collateralization (Rule A14)",
            "body": (
                "Sponsoring a loved one NEVER links your personal account to theirs. Every Self-Contained Member "
                "Account (SCMA) remains 100% walled off: one person's trading loss can never touch a Patron's savings, "
                "another relative's account, or the shared family pool."
            ),
        },
        {
            "heading": "3. Transparent Eligibility & Learning First",
            "body": (
                "Sponsored relatives complete the plain-English PDEUE University foundations walkthrough first so "
                "they understand how the 40% cash shield, High-Water Mark rule, and three-tier withdrawal guardrails work."
            ),
        },
        {
            "heading": "4. Passing the Blessing Forward",
            "body": (
                "As assisted family members regain footing and grow past their personal milestones, a portion of "
                "their voluntary recovery covenant helps replenish the Lineage Community Capital Fund (LCCF) so the "
                "next cousin or grandchild receives the same helping hand."
            ),
        },
    ],
    "rules": [
        "No Patron SCMA is ever pledged as collateral for another member.",
        "Direct-to-creditor toxic-debt payoffs and seed gifts settle strictly through IFAS (ADR-011 air-gap).",
        "No monthly fees or out-of-pocket bills are ever charged to struggling family members.",
        "Sponsorship eligibility and stewardship milestones remain transparent and reviewed with House elders.",
    ],
}

# Roles permitted to broadcast family alerts
NOTIFICATION_BROADCAST_ROLES = frozenset({"CHIEF_ADMIN", "CHIEF_ADMINISTRATOR", "H1", "H2", "HOUSE_GENEALOGIST"})


class HeritageCommunityService:
    """Air-gapped service for Family Home Hub, Community Hearth, Hall of Arms, and Family Notifications."""

    def __init__(
        self,
        *,
        session_factory: Optional[Callable[[], Session]] = None,
        bind_engine: Any = None,
        notification_gateway: Optional[NotificationGateway] = None,
    ) -> None:
        self._lock = RLock()
        self._session_factory = session_factory or SessionLocal
        self._engine = bind_engine or default_engine
        self._gateway = notification_gateway or get_notification_gateway()
        self._initialized = False

        # Process-local social board feed (zero join to financial ledgers)
        self._messages: List[Dict[str, str]] = [
            {
                "member_id": "member-mentor-01",
                "author_name": "Academy Mentor",
                "house_id": "HOUSE-01",
                "category": "Announcements",
                "message_text": "Welcome to the hearth. Share a milestone, reunion update, or learning question!",
                "posted_at": "2026-09-21T18:00:00Z",
            },
            {
                "member_id": "member-elder-02",
                "author_name": "House 02 Historian",
                "house_id": "HOUSE-02",
                "category": "Reunions",
                "message_text": "Autumn lineage reunion potluck sign-up is open — bring favorite heirloom photos for the Hall of Arms.",
                "posted_at": "2026-10-02T15:30:00Z",
            },
            {
                "member_id": "member-guide-09",
                "author_name": "House 09 Guide",
                "house_id": "HOUSE-09",
                "category": "Milestones",
                "message_text": "Congratulations to three cousins who completed PDEUE University Foundations this week!",
                "posted_at": "2026-10-10T19:15:00Z",
            },
        ]
        self._announcements: List[Dict[str, str]] = [
            {"kind": "REUNION", "category": "Reunions", "title": "Autumn lineage reunion", "when": "October 18"},
            {"kind": "GRADUATION", "category": "Milestones", "title": "Three academy learners completed the foundations path", "when": "This week"},
            {"kind": "BIRTH", "category": "Milestones", "title": "The family welcomes a new generation", "when": "September"},
            {"kind": "HERITAGE", "category": "Announcements", "title": "Hall of Arms open for all 12 Houses & allied surnames", "when": "Ongoing"},
        ]
        self._milestones: List[str] = [
            "Mentor circle completed 100 learning sessions",
            "House reading streak reached 12 weeks",
            "Five new literacy badges earned",
            "Hall of Arms gallery opened with 12 Houses and 30 family surnames",
        ]
        self._lessons: List[Dict[str, Any]] = [
            {"lesson_id": "binary-contracts-101", "title": "Binary Contracts 101", "reading_time": "8 min", "topic_tags": ["foundations", "probability"]},
            {"lesson_id": "quarter-kelly", "title": "Why Quarter-Kelly?", "reading_time": "10 min", "topic_tags": ["risk", "position-sizing"]},
            {"lesson_id": "waterfall-safeguard", "title": "The 87/10/3 Waterfall Safeguard", "reading_time": "7 min", "topic_tags": ["safeguards", "stewardship"]},
        ]

        self._ensure_ready()

    def _ensure_ready(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            Base.metadata.create_all(bind=self._engine)
            with self._session_factory() as db:
                self._seed_defaults(db)
            self._initialized = True

    def _seed_defaults(self, db: Session) -> None:
        now = _utc_now()
        # Idempotently seed all 12 Houses (and upgrade unmodified legacy SYSTEM_SEED placeholders to bordure SVGs)
        for h in SEEDED_HOUSES:
            existing = db.get(HeritageHouseProfileModel, h["house_id"])
            if existing is None:
                db.add(
                    HeritageHouseProfileModel(
                        house_id=h["house_id"],
                        lineage_code=h["lineage_code"],
                        house_name=h["house_name"],
                        motto=h["motto"],
                        crest_asset_path=h["crest_asset_path"],
                        founding_branch=h["founding_branch"],
                        history_body=h["history_body"],
                        milestones_json=json.dumps(h["milestones"]),
                        updated_by="SYSTEM_SEED",
                        updated_at_utc=now,
                    )
                )
            elif existing.updated_by == "SYSTEM_SEED" and existing.crest_asset_path in {
                "/static/assets/crests/house_crest_frame.svg",
                "/static/assets/crests/mccormick_crest.svg",
            }:
                existing.crest_asset_path = h["crest_asset_path"]
                existing.founding_branch = h["founding_branch"]
                existing.history_body = h["history_body"]

        db.flush()

        # Idempotently seed 2 founding + 28 allied surnames (30 total)
        for surname, is_founding, house_id, origin_summary, history_body in SEEDED_SURNAMES:
            slug = make_surname_slug(surname)
            existing_s = db.get(HeritageSurnameRecordModel, slug)
            if existing_s is None:
                if slug == "carmichael":
                    crest_path = "/static/assets/crests/carmichael_crest.svg"
                elif slug == "mccormick":
                    crest_path = "/static/assets/crests/mccormick_crest.svg"
                else:
                    crest_path = "/static/assets/crests/allied_crest_frame.svg"
                db.add(
                    HeritageSurnameRecordModel(
                        slug=slug,
                        surname=surname,
                        is_founding=is_founding,
                        house_id=house_id,
                        crest_asset_path=crest_path,
                        origin_summary=origin_summary,
                        history_body=history_body,
                        updated_by="SYSTEM_SEED",
                        updated_at_utc=now,
                    )
                )

        # Idempotently seed baseline safe family notifications
        if db.query(CommunityNotificationModel).count() == 0:
            seeded_notifs = [
                (
                    "NOTIF-SEED-WELCOME",
                    "ANNOUNCEMENT",
                    "Welcome to the Family Home Hub",
                    "Use the four doorway cards to visit your account, join the Family Hearth, explore the Hall of Arms, or read PDEUE University guides at your own pace.",
                    "ALL_FAMILY",
                    None,
                    "/home",
                ),
                (
                    "NOTIF-SEED-REUNION",
                    "REUNION",
                    "Autumn Lineage Reunion & Video Assembly",
                    "New family announcement posted in Lineage Hearth: October 18 gathering details and sandboxed Jitsi video rooms are ready.",
                    "ALL_FAMILY",
                    None,
                    "/community",
                ),
                (
                    "NOTIF-SEED-HERITAGE",
                    "MILESTONE",
                    "Hall of Arms Opened for All 12 Houses",
                    "Explore the Carmichael and McCormick founding crests alongside all 12 Houses and 28 allied surnames in the Hall of Arms.",
                    "ALL_FAMILY",
                    None,
                    "/community/heritage",
                ),
            ]
            for nid, cat, title, msg, scope, hid, url in seeded_notifs:
                db.add(
                    CommunityNotificationModel(
                        notification_id=nid,
                        category=cat,
                        title=title,
                        message=msg,
                        target_scope=scope,
                        target_house_id=hid,
                        action_url=url,
                        sender_id="SYSTEM_SEED",
                        sender_role="CHIEF_ADMIN",
                        channels_json=json.dumps(["in_app"]),
                        delivery_audit_json=json.dumps([{"channel": "in_app", "provider": "MockNotificationClient", "status": "SEEDED", "r12_sanitized": True}]),
                        r12_sanitized=1,
                        created_at_utc=now,
                    )
                )

        db.commit()

    # ------------------------------------------------------------------
    # Community Hearth Feed & Categorized Board
    # ------------------------------------------------------------------
    def get_community_feed(self, *, category: Optional[str] = None) -> Dict[str, Any]:
        cat_clean = (category or "").strip()
        messages = list(reversed(self._messages[-60:]))
        if cat_clean and cat_clean.lower() != "all":
            messages = [m for m in messages if m.get("category", "General").lower() == cat_clean.lower()]
        return {
            "announcements": list(self._announcements),
            "milestones": list(self._milestones),
            "messages": messages,
            "categories": list(POST_CATEGORIES),
            "lccf_charter": PAY_IT_FORWARD_LCCF_CHARTER,
            "jitsi_rooms": list(JITSI_ROOM_PRESETS),
            "scope": "COMMUNITY_EDUCATION_ONLY",
        }

    def post_community_message(
        self,
        *,
        member_id: str,
        author_name: str,
        house_id: str,
        message_text: str,
        category: str = "General",
    ) -> Dict[str, str]:
        cat_match = next(
            (c for c in POST_CATEGORIES if c.lower() == (category or "General").strip().lower()),
            "General",
        )
        message = {
            "member_id": sanitize_social_text(member_id, field="member_id", maximum=80),
            "author_name": sanitize_social_text(author_name, field="author_name", maximum=80),
            "house_id": sanitize_social_text(house_id, field="house_id", maximum=80),
            "category": cat_match,
            "message_text": sanitize_social_text(message_text, field="message_text", maximum=1000),
            "posted_at": _utc_now(),
        }
        with self._lock:
            self._messages.append(message)
        return message

    def get_lessons(self) -> Dict[str, Any]:
        return {"lessons": list(self._lessons), "curriculum_scope": "EDUCATIONAL_ONLY"}

    # ------------------------------------------------------------------
    # Hall of Arms (12 Houses + 28+ Allied Surnames)
    # ------------------------------------------------------------------
    @staticmethod
    def _serialize_house(row: HeritageHouseProfileModel, surnames: Optional[List[HeritageSurnameRecordModel]] = None) -> Dict[str, Any]:
        try:
            milestones = json.loads(row.milestones_json or "[]")
        except Exception:
            milestones = []
        hid = int(row.house_id)
        heraldry = HOUSE_HERALDRY_META.get(hid, {})
        item: Dict[str, Any] = {
            "house_id": hid,
            "lineage_code": row.lineage_code,
            "house_name": row.house_name,
            "motto": row.motto,
            "crest_asset_path": row.crest_asset_path,
            "emblem_asset_path": heraldry.get("emblem_asset_path", row.crest_asset_path),
            "achievement_asset_path": heraldry.get("achievement_asset_path", row.crest_asset_path),
            "founding_branch": row.founding_branch,
            "lineage_descent": heraldry.get("lineage_descent", row.founding_branch),
            "bordure_differencing": {
                "is_bordure_differenced": bool(heraldry.get("is_bordure_differenced", hid >= 2)),
                "border_style": heraldry.get("border_style", "Standard"),
                "tincture": heraldry.get("tincture", "Gold"),
                "blazon_note": heraldry.get("blazon_note", ""),
            },
            "history_body": row.history_body,
            "milestones": milestones,
            "updated_by": row.updated_by,
            "updated_at_utc": row.updated_at_utc,
            "history_url": f"/community/heritage/house/{row.house_id}",
        }
        if surnames is not None:
            item["surnames"] = [HeritageCommunityService._serialize_surname(s) for s in surnames]
            item["surname_count"] = len(surnames)
        return item

    @staticmethod
    def _serialize_surname(row: HeritageSurnameRecordModel) -> Dict[str, Any]:
        achievement_path = row.crest_asset_path
        if row.slug == "carmichael":
            achievement_path = "/static/assets/crests/carmichael_achievement.svg"
        elif row.slug == "mccormick":
            achievement_path = "/static/assets/crests/mccormick_achievement.svg"
        return {
            "slug": row.slug,
            "surname": row.surname,
            "is_founding": bool(row.is_founding),
            "house_id": int(row.house_id),
            "lineage_code": f"HOUSE-{int(row.house_id):02d}",
            "crest_asset_path": row.crest_asset_path,
            "emblem_asset_path": row.crest_asset_path,
            "achievement_asset_path": achievement_path,
            "origin_summary": row.origin_summary,
            "history_body": row.history_body,
            "updated_by": row.updated_by,
            "updated_at_utc": row.updated_at_utc,
            "history_url": f"/community/heritage/surname/{row.slug}",
        }

    def list_heritage_gallery(
        self,
        *,
        q: Optional[str] = None,
        house_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        needle = (q or "").strip().lower()
        with self._session_factory() as db:
            houses_rows = (
                db.query(HeritageHouseProfileModel)
                .order_by(HeritageHouseProfileModel.house_id.asc())
                .all()
            )
            surnames_rows = (
                db.query(HeritageSurnameRecordModel)
                .order_by(
                    HeritageSurnameRecordModel.is_founding.desc(),
                    HeritageSurnameRecordModel.surname.asc(),
                )
                .all()
            )

            surnames_by_house: Dict[int, List[HeritageSurnameRecordModel]] = {h.house_id: [] for h in houses_rows}
            for s in surnames_rows:
                surnames_by_house.setdefault(int(s.house_id), []).append(s)

            houses_out: List[Dict[str, Any]] = []
            for h in houses_rows:
                if house_id is not None and int(h.house_id) != int(house_id):
                    continue
                serialized_h = self._serialize_house(h, surnames_by_house.get(int(h.house_id), []))
                if needle:
                    bordure = serialized_h.get("bordure_differencing", {})
                    hay = " ".join(
                        [
                            serialized_h["lineage_code"],
                            serialized_h["house_name"],
                            serialized_h["motto"],
                            serialized_h["history_body"],
                            serialized_h.get("lineage_descent", ""),
                            bordure.get("border_style", ""),
                            bordure.get("tincture", ""),
                            " ".join(s["surname"] for s in serialized_h["surnames"]),
                        ]
                    ).lower()
                    if needle not in hay:
                        continue
                houses_out.append(serialized_h)

            founding_out: List[Dict[str, Any]] = []
            allied_out: List[Dict[str, Any]] = []
            for s in surnames_rows:
                if house_id is not None and int(s.house_id) != int(house_id):
                    continue
                serialized_s = self._serialize_surname(s)
                if needle:
                    hay = " ".join(
                        [
                            serialized_s["surname"],
                            serialized_s["origin_summary"],
                            serialized_s["history_body"],
                            serialized_s["lineage_code"],
                        ]
                    ).lower()
                    if needle not in hay:
                        continue
                if serialized_s["is_founding"]:
                    founding_out.append(serialized_s)
                else:
                    allied_out.append(serialized_s)

            return {
                "scope": "HERITAGE_HALL_OF_ARMS_NO_FINANCIAL_DATA",
                "founding_surnames": founding_out,
                "houses": houses_out,
                "allied_surnames": allied_out,
                "total_houses": len(houses_rows),
                "total_surnames": len(surnames_rows),
                "allied_surname_count": sum(1 for s in surnames_rows if not s.is_founding),
                "two_scale_heraldry": {
                    "emblem_assets": {
                        "carmichael": "/static/assets/crests/carmichael_crest.svg",
                        "mccormick": "/static/assets/crests/mccormick_crest.svg",
                    },
                    "achievement_assets": {
                        "carmichael": "/static/assets/crests/carmichael_achievement.svg",
                        "mccormick": "/static/assets/crests/mccormick_achievement.svg",
                    },
                    "house_1_descent": "Carmichael Line — Descending from Eldest McCormick Daughter",
                    "bordure_differenced_house_ids": list(range(2, 13)),
                    "bordure_differenced_house_count": 11,
                },
            }

    def get_house_history(self, house_id: int) -> Dict[str, Any]:
        self._ensure_ready()
        if house_id < 1 or house_id > 12:
            raise HTTPException(status_code=404, detail="House not found")
        with self._session_factory() as db:
            row = db.get(HeritageHouseProfileModel, house_id)
            if row is None:
                raise HTTPException(status_code=404, detail="House profile not found")
            surnames = (
                db.query(HeritageSurnameRecordModel)
                .filter(HeritageSurnameRecordModel.house_id == house_id)
                .order_by(HeritageSurnameRecordModel.is_founding.desc(), HeritageSurnameRecordModel.surname.asc())
                .all()
            )
            return self._serialize_house(row, surnames)

    def get_surname_history(self, slug: str) -> Dict[str, Any]:
        self._ensure_ready()
        clean_slug = make_surname_slug(slug)
        with self._session_factory() as db:
            row = db.get(HeritageSurnameRecordModel, clean_slug)
            if row is None:
                raise HTTPException(status_code=404, detail="Surname record not found")
            house = db.get(HeritageHouseProfileModel, int(row.house_id))
            data = self._serialize_surname(row)
            if house is not None:
                data["house_name"] = house.house_name
                data["house_motto"] = house.motto
                data["house_history_url"] = f"/community/heritage/house/{house.house_id}"
            return data

    def _authorize_heritage_writer(
        self,
        db: Session,
        *,
        target_house_id: int,
        actor_role: Optional[str],
        actor_id: Optional[str],
        action: str,
    ) -> Tuple[str, str]:
        """Enforce strict server-side authorization: ONLY assigned HOUSE_GENEALOGIST for target_house_id or CHIEF_ADMIN."""
        audit = get_governance_audit_log()
        norm_role = normalize_role_token(actor_role)
        clean_actor = (actor_id or "").strip()

        if is_chief_admin_role(norm_role):
            return "CHIEF_ADMIN", clean_actor or "CHIEF_ADMINISTRATOR"

        if norm_role == "HOUSE_GENEALOGIST":
            if not clean_actor:
                audit.record(
                    event_type="HERITAGE_EDIT_DENIED",
                    actor_id="UNIDENTIFIED_GENEALOGIST",
                    actor_role="HOUSE_GENEALOGIST",
                    target_id=f"HOUSE-{target_house_id:02d}",
                    action=action,
                    outcome="DENIED_MISSING_ACTOR_IDENTITY",
                    http_status=403,
                    detail="HOUSE_GENEALOGIST write requires an authenticated member_id verified in user_role_assignments.",
                )
                raise HTTPException(
                    status_code=403,
                    detail="GENEALOGIST_IDENTITY_REQUIRED: Authenticated member_id with active HOUSE_GENEALOGIST assignment is required.",
                )

            assignment = (
                db.query(UserRoleAssignmentModel)
                .filter(
                    UserRoleAssignmentModel.member_id == clean_actor,
                    UserRoleAssignmentModel.role_token == "HOUSE_GENEALOGIST",
                    UserRoleAssignmentModel.status == "ACTIVE",
                )
                .first()
            )
            if assignment is None:
                audit.record(
                    event_type="HERITAGE_EDIT_DENIED",
                    actor_id=clean_actor,
                    actor_role="HOUSE_GENEALOGIST",
                    target_id=f"HOUSE-{target_house_id:02d}",
                    action=action,
                    outcome="DENIED_NO_ACTIVE_GENEALOGIST_ROLE",
                    http_status=403,
                    detail=f"Caller {clean_actor} holds no ACTIVE HOUSE_GENEALOGIST assignment in user_role_assignments.",
                )
                raise HTTPException(
                    status_code=403,
                    detail="GENEALOGIST_ROLE_REQUIRED: Caller does not hold an active HOUSE_GENEALOGIST assignment.",
                )

            if assignment.house_id is None or int(assignment.house_id) != int(target_house_id):
                audit.record(
                    event_type="HERITAGE_EDIT_DENIED",
                    actor_id=clean_actor,
                    actor_role="HOUSE_GENEALOGIST",
                    target_id=f"HOUSE-{target_house_id:02d}",
                    action=action,
                    outcome="DENIED_CROSS_HOUSE_GENEALOGIST",
                    http_status=403,
                    detail=(
                        f"HOUSE_GENEALOGIST {clean_actor} is assigned to HOUSE-{int(assignment.house_id or 0):02d} "
                        f"and cannot edit HOUSE-{target_house_id:02d}."
                    ),
                )
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"CROSS_HOUSE_HERITAGE_FORBIDDEN: Your HOUSE_GENEALOGIST assignment is scoped to "
                        f"House {assignment.house_id}, not House {target_house_id}."
                    ),
                )
            return "HOUSE_GENEALOGIST", clean_actor

        audit.record(
            event_type="HERITAGE_EDIT_DENIED",
            actor_id=clean_actor or norm_role or "anonymous",
            actor_role=norm_role or "ANONYMOUS",
            target_id=f"HOUSE-{target_house_id:02d}",
            action=action,
            outcome="DENIED_INSUFFICIENT_ROLE",
            http_status=403,
            detail="Only an assigned HOUSE_GENEALOGIST for this House or CHIEF_ADMIN may edit Hall of Arms records.",
        )
        raise HTTPException(
            status_code=403,
            detail="HERITAGE_WRITE_FORBIDDEN: Only the assigned HOUSE_GENEALOGIST for this House or CHIEF_ADMIN may edit heritage pages.",
        )

    def update_house_history(
        self,
        *,
        house_id: int,
        house_name: Optional[str],
        motto: Optional[str],
        history_body: str,
        milestones: Optional[List[str]] = None,
        crest_asset_path: Optional[str] = None,
        actor_role: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        if house_id < 1 or house_id > 12:
            raise HTTPException(status_code=404, detail="House not found")

        with self._session_factory() as db:
            verified_role, verified_actor = self._authorize_heritage_writer(
                db,
                target_house_id=house_id,
                actor_role=actor_role,
                actor_id=actor_id,
                action="HERITAGE_UPDATE_HOUSE",
            )
            row = db.get(HeritageHouseProfileModel, house_id)
            if row is None:
                raise HTTPException(status_code=404, detail="House profile not found")

            if house_name is not None and house_name.strip():
                row.house_name = sanitize_social_text(house_name, field="house_name", maximum=120)
            if motto is not None and motto.strip():
                row.motto = sanitize_social_text(motto, field="motto", maximum=180)
            row.history_body = sanitize_social_text(
                history_body, field="history_body", maximum=4000, allow_newlines=True
            )
            if milestones is not None:
                safe_milestones = [
                    sanitize_social_text(m, field="milestone", maximum=240)
                    for m in milestones
                    if str(m or "").strip()
                ][:20]
                row.milestones_json = json.dumps(safe_milestones)
            if crest_asset_path is not None and crest_asset_path.strip():
                clean_path = crest_asset_path.strip()
                if not clean_path.startswith("/static/assets/crests/"):
                    raise HTTPException(
                        status_code=422,
                        detail="crest_asset_path must reference a local zero-CDN asset under /static/assets/crests/.",
                    )
                row.crest_asset_path = clean_path

            row.updated_by = verified_actor
            row.updated_at_utc = _utc_now()
            db.commit()
            db.refresh(row)

            get_governance_audit_log().record(
                event_type="HERITAGE_HOUSE_UPDATED",
                actor_id=verified_actor,
                actor_role=verified_role,
                target_id=f"HOUSE-{house_id:02d}",
                action="HERITAGE_UPDATE_HOUSE",
                outcome="UPDATED",
                http_status=200,
                detail=f"Updated Hall of Arms history for {row.lineage_code} ({row.house_name}).",
            )

            surnames = (
                db.query(HeritageSurnameRecordModel)
                .filter(HeritageSurnameRecordModel.house_id == house_id)
                .all()
            )
            return self._serialize_house(row, surnames)

    def upsert_surname_record(
        self,
        *,
        surname: str,
        house_id: int,
        origin_summary: str,
        history_body: str,
        crest_asset_path: Optional[str] = None,
        actor_role: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        if house_id < 1 or house_id > 12:
            raise HTTPException(status_code=422, detail="house_id must be between 1 and 12")

        safe_surname = sanitize_social_text(surname, field="surname", maximum=80)
        safe_origin = sanitize_social_text(origin_summary, field="origin_summary", maximum=220)
        safe_history = sanitize_social_text(
            history_body, field="history_body", maximum=4000, allow_newlines=True
        )
        slug = make_surname_slug(html.unescape(safe_surname))

        clean_crest = "/static/assets/crests/allied_crest_frame.svg"
        if crest_asset_path and crest_asset_path.strip():
            candidate = crest_asset_path.strip()
            if not candidate.startswith("/static/assets/crests/"):
                raise HTTPException(
                    status_code=422,
                    detail="crest_asset_path must reference a local zero-CDN asset under /static/assets/crests/.",
                )
            clean_crest = candidate

        with self._session_factory() as db:
            verified_role, verified_actor = self._authorize_heritage_writer(
                db,
                target_house_id=house_id,
                actor_role=actor_role,
                actor_id=actor_id,
                action="HERITAGE_UPSERT_SURNAME",
            )
            existing = db.get(HeritageSurnameRecordModel, slug)
            now = _utc_now()
            if existing is not None:
                # Prevent a genealogist of House B from hijacking a surname belonging to House A
                if verified_role != "CHIEF_ADMIN" and int(existing.house_id) != int(house_id):
                    get_governance_audit_log().record(
                        event_type="HERITAGE_EDIT_DENIED",
                        actor_id=verified_actor,
                        actor_role=verified_role,
                        target_id=f"SURNAME:{slug}",
                        action="HERITAGE_UPSERT_SURNAME",
                        outcome="DENIED_CROSS_HOUSE_SURNAME",
                        http_status=403,
                        detail=f"Surname '{slug}' belongs to House {existing.house_id}, not House {house_id}.",
                    )
                    raise HTTPException(
                        status_code=403,
                        detail=f"CROSS_HOUSE_HERITAGE_FORBIDDEN: Surname '{existing.surname}' belongs to House {existing.house_id}.",
                    )
                existing.surname = safe_surname
                existing.house_id = house_id
                existing.origin_summary = safe_origin
                existing.history_body = safe_history
                if crest_asset_path and crest_asset_path.strip():
                    existing.crest_asset_path = clean_crest
                existing.updated_by = verified_actor
                existing.updated_at_utc = now
                record = existing
                outcome = "UPDATED"
            else:
                record = HeritageSurnameRecordModel(
                    slug=slug,
                    surname=safe_surname,
                    is_founding=0,
                    house_id=house_id,
                    crest_asset_path=clean_crest,
                    origin_summary=safe_origin,
                    history_body=safe_history,
                    updated_by=verified_actor,
                    updated_at_utc=now,
                )
                db.add(record)
                outcome = "CREATED"

            db.commit()
            db.refresh(record)

            get_governance_audit_log().record(
                event_type="HERITAGE_SURNAME_UPSERTED",
                actor_id=verified_actor,
                actor_role=verified_role,
                target_id=f"SURNAME:{slug}",
                action="HERITAGE_UPSERT_SURNAME",
                outcome=outcome,
                http_status=200,
                detail=f"{outcome} Hall of Arms surname '{safe_surname}' under HOUSE-{house_id:02d}.",
            )
            return self._serialize_surname(record)

    # ------------------------------------------------------------------
    # Isolated Family Notifications & Broadcasts
    # ------------------------------------------------------------------
    def list_notifications(
        self,
        *,
        house_id: Optional[int] = None,
        category: Optional[str] = None,
        limit: int = 30,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        with self._session_factory() as db:
            query = db.query(CommunityNotificationModel)
            if house_id is not None:
                query = query.filter(
                    (CommunityNotificationModel.target_house_id == None)  # noqa: E711
                    | (CommunityNotificationModel.target_house_id == int(house_id))
                )
            if category and category.strip().lower() != "all":
                query = query.filter(CommunityNotificationModel.category == category.strip().upper())
            rows = (
                query.order_by(CommunityNotificationModel.created_at_utc.desc())
                .limit(max(1, min(100, int(limit))))
                .all()
            )
            items = []
            for r in rows:
                try:
                    channels = json.loads(r.channels_json or '["in_app"]')
                except Exception:
                    channels = ["in_app"]
                try:
                    deliveries = json.loads(r.delivery_audit_json or "[]")
                except Exception:
                    deliveries = []
                items.append(
                    {
                        "notification_id": r.notification_id,
                        "category": r.category,
                        "title": r.title,
                        "message": r.message,
                        "target_scope": r.target_scope,
                        "target_house_id": r.target_house_id,
                        "action_url": r.action_url,
                        "sender_id": r.sender_id,
                        "sender_role": r.sender_role,
                        "channels": channels,
                        "delivery_audit": deliveries,
                        "r12_sanitized": bool(r.r12_sanitized),
                        "created_at_utc": r.created_at_utc,
                    }
                )
            return {
                "notifications": items,
                "count": len(items),
                "gateway": self._gateway.status_summary(),
                "scope": "ISOLATED_FAMILY_ALERTS_NO_FINANCIAL_DATA",
            }

    def broadcast_notification(
        self,
        *,
        title: str,
        message: str,
        category: str = "ANNOUNCEMENT",
        target_house_id: Optional[int] = None,
        action_url: str = "/community",
        channels: Optional[List[str]] = None,
        actor_role: Optional[str] = None,
        actor_id: Optional[str] = None,
        strict_r12_reject: bool = False,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        norm_role = normalize_role_token(actor_role)
        clean_actor = (actor_id or norm_role or "anonymous").strip()

        if norm_role not in NOTIFICATION_BROADCAST_ROLES:
            get_governance_audit_log().record(
                event_type="NOTIFICATION_BROADCAST_DENIED",
                actor_id=clean_actor,
                actor_role=norm_role or "ANONYMOUS",
                target_id=f"HOUSE-{target_house_id:02d}" if target_house_id else "ALL_FAMILY",
                action="NOTIFICATION_BROADCAST",
                outcome="DENIED_ROLE_NOT_PERMITTED",
                http_status=403,
                detail="Only CHIEF_ADMIN, H1, H2, or HOUSE_GENEALOGIST may broadcast family notifications.",
            )
            raise HTTPException(
                status_code=403,
                detail="BROADCAST_FORBIDDEN: Only CHIEF_ADMIN, H1, H2, or HOUSE_GENEALOGIST may broadcast family alerts.",
            )

        if target_house_id is not None and (target_house_id < 1 or target_house_id > 12):
            raise HTTPException(status_code=422, detail="target_house_id must be between 1 and 12")

        safe_url = (action_url or "/community").strip()
        if not safe_url.startswith("/"):
            safe_url = "/community"

        safe_title, title_redactions = sanitize_notification_text(
            title, strict_reject=strict_r12_reject, maximum=140
        )
        safe_message, msg_redactions = sanitize_notification_text(
            message, strict_reject=strict_r12_reject, maximum=500
        )
        if not safe_title or not safe_message:
            raise HTTPException(status_code=422, detail="title and message must not be empty")

        notif_id = f"NOTIF-{uuid.uuid4().hex[:10].upper()}"
        cat_norm = (category or "ANNOUNCEMENT").strip().upper()[:32] or "ANNOUNCEMENT"
        target_scope = f"HOUSE-{int(target_house_id):02d}" if target_house_id is not None else "ALL_FAMILY"
        now = _utc_now()

        payload = NotificationMessage(
            notification_id=notif_id,
            title=html.unescape(safe_title),
            message=html.unescape(safe_message),
            category=cat_norm,
            target_scope=target_scope,
            target_house_id=target_house_id,
            action_url=safe_url,
            sender_id=clean_actor,
            sender_role=norm_role,
            created_at_utc=now,
        )
        receipts = self._gateway.dispatch(payload, channels=channels or ["in_app"], strict_reject=strict_r12_reject)
        receipt_dicts = [r.to_dict() for r in receipts]
        used_channels = [r.channel for r in receipts]
        all_redactions = sorted(set(title_redactions + msg_redactions))

        with self._session_factory() as db:
            row = CommunityNotificationModel(
                notification_id=notif_id,
                category=cat_norm,
                title=safe_title,
                message=safe_message,
                target_scope=target_scope,
                target_house_id=target_house_id,
                action_url=safe_url,
                sender_id=clean_actor,
                sender_role=norm_role,
                channels_json=json.dumps(used_channels),
                delivery_audit_json=json.dumps(receipt_dicts),
                r12_sanitized=1,
                created_at_utc=now,
            )
            db.add(row)
            db.commit()

        get_governance_audit_log().record(
            event_type="NOTIFICATION_BROADCAST_SENT",
            actor_id=clean_actor,
            actor_role=norm_role,
            target_id=target_scope,
            action="NOTIFICATION_BROADCAST",
            outcome="DELIVERED_R12_SAFE",
            http_status=201,
            detail=f"Broadcast {notif_id} over {used_channels}; R-12 redactions={all_redactions}.",
        )

        return {
            "notification_id": notif_id,
            "category": cat_norm,
            "title": safe_title,
            "message": safe_message,
            "target_scope": target_scope,
            "target_house_id": target_house_id,
            "action_url": safe_url,
            "sender_id": clean_actor,
            "sender_role": norm_role,
            "channels": used_channels,
            "r12_sanitized": True,
            "redactions_applied": all_redactions,
            "delivery_audit": receipt_dicts,
            "created_at_utc": now,
        }

    # ------------------------------------------------------------------
    # Role Resolution Helper for Home Hub 5th Doorway Card (Zero Financial Imports)
    # ------------------------------------------------------------------
    def resolve_assigned_house_for_member(self, member_id: Optional[str], role_token: str) -> int:
        """Look up assigned house_id from UserRoleAssignmentModel (defaults to 1)."""
        self._ensure_ready()
        if not member_id:
            return 1
        with self._session_factory() as db:
            row = (
                db.query(UserRoleAssignmentModel)
                .filter(
                    UserRoleAssignmentModel.member_id == member_id,
                    UserRoleAssignmentModel.role_token == role_token,
                    UserRoleAssignmentModel.status == "ACTIVE",
                )
                .first()
            )
            if row and row.house_id:
                return int(row.house_id)
        return 1


_SHARED_HERITAGE_COMMUNITY_SERVICE: Optional[HeritageCommunityService] = None
_SERVICE_INIT_LOCK = RLock()


def get_heritage_community_service() -> HeritageCommunityService:
    global _SHARED_HERITAGE_COMMUNITY_SERVICE
    if _SHARED_HERITAGE_COMMUNITY_SERVICE is None:
        with _SERVICE_INIT_LOCK:
            if _SHARED_HERITAGE_COMMUNITY_SERVICE is None:
                _SHARED_HERITAGE_COMMUNITY_SERVICE = HeritageCommunityService()
    return _SHARED_HERITAGE_COMMUNITY_SERVICE
