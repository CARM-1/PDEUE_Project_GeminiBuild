"""Air-Gapped Social, Home Hub, Hall of Arms Heritage & Family Communications Router.

STRICT SOCIAL-PLANE FIREWALL (Non-Negotiable):
- ZERO imports or invocations of CapitalLedger, TwoTierRiskEnvelope,
  AutonomousScanWorker, CredentialBroker, or venue adapters.
- Serves:
  * GET /home                                    -> Central Family Home Hub (4-card doorway + scoped 5th card)
  * GET /community                               -> Upgraded Lineage Community Hearth & Sandboxed Jitsi Rooms
  * GET /community/heritage                      -> Hall of Arms (Founding Crests + 12 Houses + 28+ Surnames)
  * GET /community/heritage/house/{house_id}     -> Individual House Family History Page
  * GET /community/heritage/surname/{slug}       -> Individual Surname Family History Page
  * GET /api/v1/portal/planes                    -> 4-Domain Air-Gapped Plane Configuration (secret-free)
  * GET /api/v1/portal/community/feed            -> Categorized Family Feed + Pay-it-Forward Charter + Jitsi presets
  * POST /api/v1/portal/community/message        -> XSS-sanitized categorized family post
  * GET /api/v1/portal/community/academy/lessons -> Educational lessons
  * POST /api/v1/portal/community/academy/ask-tutor -> Educational-only academy tutor (refuses balances/trades)
  * GET /api/v1/portal/community/heritage        -> Hall of Arms JSON gallery
  * GET /api/v1/portal/community/heritage/house/{house_id}
  * GET /api/v1/portal/community/heritage/surname/{slug}
  * POST /api/v1/portal/community/heritage/house/{house_id}  -> Scoped HOUSE_GENEALOGIST / CHIEF_ADMIN write
  * POST /api/v1/portal/community/heritage/surname           -> Scoped HOUSE_GENEALOGIST / CHIEF_ADMIN write
  * GET /api/v1/portal/community/notifications               -> Isolated R-12 safe family alerts
  * POST /api/v1/portal/community/notifications/broadcast    -> Scoped broadcast (CHIEF_ADMIN / H1 / H2 / HOUSE_GENEALOGIST)
"""
from __future__ import annotations

import html
import pathlib
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.core.security import decode_access_token
from app.domain.authority_tiers import (
    is_chief_admin_role,
    is_class_t_role,
    normalize_role_token,
)
from app.domain.family_tree_service import get_family_tree_service
from app.domain.heritage_community_service import (
    get_heritage_community_service,
    resolve_heraldic_asset_path,
    sanitize_social_text,
)
from app.domain.dual_lane_tutor import (
    get_dual_lane_tutor,
    is_academy_balance_or_trade_request,
)
from app.domain.plane_routing import (
    get_plane_config,
    resolve_lineage_house_url,
)

social_plane_router = APIRouter(tags=["Family Home Hub, Community & Heritage"])


class CommunityMessageRequest(BaseModel):
    member_id: str
    author_name: str
    house_id: str
    message_text: str
    category: Optional[str] = "General"


class CommunityTutorRequest(BaseModel):
    query: str
    member_id: str


class HeritageHouseUpdateRequest(BaseModel):
    house_name: Optional[str] = None
    motto: Optional[str] = None
    history_body: str
    milestones: Optional[List[str]] = None
    crest_asset_path: Optional[str] = None
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None


class HeritageSurnameUpsertRequest(BaseModel):
    surname: str
    house_id: int
    origin_summary: str
    history_body: str
    crest_asset_path: Optional[str] = None
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None


class NotificationBroadcastRequest(BaseModel):
    title: str
    message: str
    category: Optional[str] = "ANNOUNCEMENT"
    target_house_id: Optional[int] = None
    action_url: Optional[str] = "/community"
    channels: Optional[List[str]] = None
    strict_r12_reject: bool = False
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None


class FamilyTreePersonCreateRequest(BaseModel):
    person_id: Optional[str] = None
    full_name: str
    given_name: Optional[str] = None
    surname: Optional[str] = ""
    suffix: Optional[str] = ""
    nickname: Optional[str] = ""
    house_id: str = "HOUSE-01"
    generation: int = 2
    is_deceased: bool = False
    birth_year: Optional[int] = None
    death_year: Optional[int] = None
    bio_notes: Optional[str] = ""
    source_tag: Optional[str] = "GENEALOGIST_ENTRY"
    review_flag: Optional[str] = ""
    is_reference_branch: bool = False
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None


class FamilyTreePersonUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    given_name: Optional[str] = None
    surname: Optional[str] = None
    suffix: Optional[str] = None
    nickname: Optional[str] = None
    house_id: Optional[str] = None
    generation: Optional[int] = None
    is_deceased: Optional[bool] = None
    birth_year: Optional[int] = None
    death_year: Optional[int] = None
    bio_notes: Optional[str] = None
    source_tag: Optional[str] = None
    review_flag: Optional[str] = None
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None


class FamilyTreeRelationshipCreateRequest(BaseModel):
    rel_type: str
    person_a_id: str
    person_b_id: str
    notes: Optional[str] = ""
    source_tag: Optional[str] = "GENEALOGIST_ENTRY"
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None


def _load_social_html(filename: str) -> str:
    api_page = pathlib.Path(__file__).parent / filename
    if api_page.exists():
        return api_page.read_text(encoding="utf-8")
    static_page = pathlib.Path(__file__).parent.parent.parent / "static" / filename
    if static_page.exists():
        return static_page.read_text(encoding="utf-8")
    raise HTTPException(status_code=500, detail=f"Social plane template {filename} missing")


def _apply_resolved_achievement_assets(markup: str) -> str:
    """Substitute founding achievement SVG paths with high-res raster drop-ins (.png/.jpg) when present."""
    carm_src = html.escape(resolve_heraldic_asset_path("carmichael_achievement"), quote=True)
    mcc_src = html.escape(resolve_heraldic_asset_path("mccormick_achievement"), quote=True)
    return (
        markup
        .replace("/static/assets/crests/carmichael_achievement.svg", carm_src).replace("/static/assets/crests/carmichael_achievement.jpg", carm_src)
        .replace("/static/assets/crests/mccormick_achievement.svg", mcc_src).replace("/static/assets/crests/mccormick_achievement.jpg", mcc_src)
    )


def _resolve_social_caller(
    *,
    authorization: Optional[str] = None,
    x_active_hat: Optional[str] = None,
    x_actor_role: Optional[str] = None,
    x_actor_id: Optional[str] = None,
    x_house_id: Optional[str] = None,
    body_role: Optional[str] = None,
    body_actor_id: Optional[str] = None,
) -> tuple[str, str, Optional[int]]:
    """Resolve caller role, actor_id, and optional house_id from Bearer JWT or explicit headers."""
    role = x_active_hat or x_actor_role or body_role or ""
    actor_id = x_actor_id or body_actor_id or ""
    claimed_house: Optional[int] = None

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        claims = decode_access_token(token)
        if not claims:
            raise HTTPException(status_code=403, detail="Invalid or expired identity token")
        role = str(claims.get("active_hat") or claims.get("role") or role)
        actor_id = str(claims.get("sub") or claims.get("user_id") or actor_id)
        if claims.get("house_id") is not None:
            try:
                claimed_house = int(str(claims["house_id"]).upper().replace("HOUSE-", ""))
            except ValueError:
                claimed_house = None

    if claimed_house is None and x_house_id:
        try:
            claimed_house = int(str(x_house_id).strip().upper().replace("HOUSE-", ""))
        except ValueError:
            claimed_house = None

    return normalize_role_token(role), actor_id.strip(), claimed_house


def _build_scoped_fifth_doorway_card(
    *,
    role: str,
    actor_id: str,
    claimed_house_id: Optional[int],
    doorways: Dict[str, Any],
) -> str:
    """Render ONE clearly labeled extra doorway card ONLY for authorized non-Class-M hats.

    Standard Class M members and unauthenticated callers NEVER receive admin, advisor,
    technical, or House desk links in the DOM.
    """
    if not role or role in {"MEMBER_USER", "PERSONAL_SCMA"}:
        return ""

    if is_chief_admin_role(role):
        href = html.escape(doorways["dashboard"], quote=True)
        return (
            '<a id="roleDoorwayCard" class="doorway-card doorway-role-card" href="' + href + '" data-plane-doorway="dashboard" data-role-door="CHIEF_ADMIN">'
            '<span class="doorway-icon" aria-hidden="true">🏛️</span>'
            '<span class="doorway-tag role-tag">ASSIGNED HAT · CHIEF ADMINISTRATOR</span>'
            '<h2>Chief Admin Cockpit</h2>'
            '<p>Enter your Sovereign Settlor operations cockpit, 12-House oversight, and governance desk.</p>'
            '<span class="doorway-cta">Open Chief Admin Cockpit →</span>'
            '</a>'
        )

    if role in {"F1", "F2-H", "F2-A", "F3"}:
        href = html.escape(f"{doorways['advisor']}?role={role}", quote=True)
        return (
            '<a id="roleDoorwayCard" class="doorway-card doorway-role-card" href="' + href + '" data-plane-doorway="advisor" data-role-door="' + html.escape(role, quote=True) + '">'
            '<span class="doorway-icon" aria-hidden="true">🛡️</span>'
            '<span class="doorway-tag role-tag">ASSIGNED HAT · CLASS F (' + html.escape(role) + ')</span>'
            '<h2>Lineal Advisory Desk</h2>'
            '<p>Review your assigned household stewardship tasks, mentoring notes, and safety approvals.</p>'
            '<span class="doorway-cta">Open Advisory Workspace →</span>'
            '</a>'
        )

    if role in {"H1", "H2"}:
        svc = get_heritage_community_service()
        assigned_house = claimed_house_id or svc.resolve_assigned_house_for_member(actor_id, role)
        house_url = resolve_lineage_house_url(assigned_house)
        href = html.escape(f"{house_url}?role={role}", quote=True)
        return (
            '<a id="roleDoorwayCard" class="doorway-card doorway-role-card" href="' + href + '" data-role-door="' + html.escape(role, quote=True) + '">'
            '<span class="doorway-icon" aria-hidden="true">🏰</span>'
            f'<span class="doorway-tag role-tag">ASSIGNED HAT · HOUSE {assigned_house:02d} ({html.escape(role)})</span>'
            f'<h2>House {assigned_house:02d} Leadership Desk</h2>'
            '<p>Enter your scoped House workspace for roll-call records, stewardship oversight, and lineage desk duties.</p>'
            '<span class="doorway-cta">Open House Desk →</span>'
            '</a>'
        )

    if role == "HOUSE_GENEALOGIST":
        href = html.escape(doorways["genealogist_desk"], quote=True)
        return (
            '<a id="roleDoorwayCard" class="doorway-card doorway-role-card" href="' + href + '" data-plane-doorway="genealogist_desk" data-role-door="HOUSE_GENEALOGIST">'
            '<span class="doorway-icon" aria-hidden="true">📜</span>'
            '<span class="doorway-tag role-tag">ASSIGNED HAT · HOUSE GENEALOGIST</span>'
            '<h2>House Genealogist Desk</h2>'
            '<p>Curate your assigned House history, motto, and allied family surname biographies in the Hall of Arms.</p>'
            '<span class="doorway-cta">Open Genealogist Desk →</span>'
            '</a>'
        )

    if is_class_t_role(role):
        tier = role if role in {"T1", "T2", "T2-HOUSEHOLD", "T3"} else "T1"
        href = html.escape(f"{doorways['admin_tech']}?tier={tier}", quote=True)
        return (
            '<a id="roleDoorwayCard" class="doorway-card doorway-role-card" href="' + href + '" data-plane-doorway="admin_tech" data-role-door="' + html.escape(tier, quote=True) + '">'
            '<span class="doorway-icon" aria-hidden="true">⚙️</span>'
            '<span class="doorway-tag role-tag">ASSIGNED HAT · CLASS T (' + html.escape(tier) + ')</span>'
            '<h2>Technical Infrastructure Console</h2>'
            '<p>Monitor system health and relay telemetry under Directive R-12 financial privacy masking.</p>'
            '<span class="doorway-cta">Open Tech Console →</span>'
            '</a>'
        )

    return ""


# ----------------------------------------------------------------------
# 4-Domain Air-Gap Metadata Endpoint (Read-Only, Secret-Free)
# ----------------------------------------------------------------------
@social_plane_router.get("/api/v1/portal/planes")
def get_portal_planes() -> Dict[str, Any]:
    """Expose read-only 4-domain air-gap plane URLs and plane badges (zero secrets)."""
    return get_plane_config()


# ----------------------------------------------------------------------
# Central Family Home Hub (/home)
# ----------------------------------------------------------------------
@social_plane_router.get("/home", response_class=HTMLResponse)
def get_family_home_hub(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
):
    """Serve the welcoming, senior-friendly 4-card Central Family Home Hub."""
    plane_cfg = get_plane_config()
    doorways = plane_cfg["doorways"]
    role, actor_id, claimed_house = _resolve_social_caller(
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        x_house_id=x_house_id,
    )
    auth_session = getattr(request.state, "auth_session", None)
    if auth_session is not None and not role:
        role = normalize_role_token(getattr(auth_session, "active_hat", ""))
        actor_id = actor_id or str(getattr(auth_session, "user_id", ""))
        if claimed_house is None and getattr(auth_session, "house_id", None):
            try:
                claimed_house = int(str(auth_session.house_id).upper().replace("HOUSE-", ""))
            except ValueError:
                claimed_house = None
    fifth_card = _build_scoped_fifth_doorway_card(
        role=role,
        actor_id=actor_id,
        claimed_house_id=claimed_house,
        doorways=doorways,
    )
    active_hat_label = f"Active Hat: {role}" if role else "Active Hat: MEMBER_USER (FAMILY_HUB)"

    markup = _load_social_html("home.html")
    replacements = {
        "__MEMBER_URL__": html.escape(doorways["member"], quote=True),
        "__COMMUNITY_URL__": html.escape(doorways["community"], quote=True),
        "__HERITAGE_URL__": html.escape(doorways["heritage"], quote=True),
        "__COMPANION_URL__": html.escape(doorways["companion"], quote=True),
        "__ACTIVE_HAT_LABEL__": html.escape(active_hat_label),
        "__ROLE_FIFTH_CARD__": fifth_card,
    }
    for marker, value in replacements.items():
        markup = markup.replace(marker, value)
    markup = _apply_resolved_achievement_assets(markup)
    return HTMLResponse(markup)


# ----------------------------------------------------------------------
# Upgraded Lineage Community Hearth (/community) & Social APIs
# ----------------------------------------------------------------------
@social_plane_router.get("/community", response_class=HTMLResponse)
def get_community_portal():
    """Serve the upgraded Lineage Community Hearth (strictly non-transactional)."""
    return HTMLResponse(_load_social_html("community.html"))


@social_plane_router.get("/api/v1/portal/community/feed")
def get_community_feed(category: Optional[str] = Query(None)) -> Dict[str, Any]:
    return get_heritage_community_service().get_community_feed(category=category)


@social_plane_router.post("/api/v1/portal/community/message", status_code=201)
def post_community_message(request: CommunityMessageRequest) -> Dict[str, str]:
    return get_heritage_community_service().post_community_message(
        member_id=request.member_id,
        author_name=request.author_name,
        house_id=request.house_id,
        message_text=request.message_text,
        category=request.category or "General",
    )


@social_plane_router.get("/api/v1/portal/community/academy/lessons")
def get_community_lessons() -> Dict[str, Any]:
    return get_heritage_community_service().get_lessons()


@social_plane_router.post("/api/v1/portal/community/academy/ask-tutor")
def ask_community_tutor(request: CommunityTutorRequest) -> Dict[str, Any]:
    query = sanitize_social_text(request.query, field="query", maximum=500)
    member_id = sanitize_social_text(request.member_id, field="member_id", maximum=80)
    if is_academy_balance_or_trade_request(query):
        raise HTTPException(
            status_code=403,
            detail="The academy tutor is educational only and cannot access balances or perform transactions.",
        )
    return get_dual_lane_tutor().answer_academy_query(query=query, member_id=member_id)


# ----------------------------------------------------------------------
# Hall of Arms (/community/heritage) & Individual History Pages
# ----------------------------------------------------------------------
@social_plane_router.get("/community/heritage", response_class=HTMLResponse)
def get_hall_of_arms_portal():
    """Serve the Hall of Arms gallery for the founding crests, 12 Houses, and 28+ allied surnames."""
    return HTMLResponse(_apply_resolved_achievement_assets(_load_social_html("heritage.html")))


def _render_detail_page(
    *,
    page_title: str,
    eyebrow: str,
    heading: str,
    subtitle: str,
    crest_path: str,
    crest_alt: str,
    history_body: str,
    extra_sections_html: str,
    updated_by: str,
    updated_at: str,
) -> HTMLResponse:
    plane_cfg = get_plane_config()
    home_url = html.escape(plane_cfg["doorways"]["home"], quote=True)
    heritage_url = html.escape(plane_cfg["doorways"]["heritage"], quote=True)
    paragraphs = "".join(
        f"<p>{line}</p>" for line in history_body.splitlines() if line.strip()
    )
    page = f"""<!doctype html>
<html lang="en" data-text-scale="standard">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{html.escape(page_title)} — Hall of Arms</title>
  <link rel="stylesheet" href="/static/css/senior_a11y.css">
  <style>
    :root {{
      --bg-canvas: #0B132B;
      --bg-card: #1C2541;
      --bg-surface: #1E293B;
      --border-subtle: #334155;
      --text-primary: #F8FAFC;
      --text-secondary: #CBD5E1;
      --text-muted: #94A3B8;
      --accent-sky: #38BDF8;
      --gold: #E4BB63;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: radial-gradient(circle at 20% 0, #162447 0, var(--bg-canvas) 55%);
      color: var(--text-primary);
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
      line-height: 1.6;
    }}
    .shell {{ width: min(1040px, 94vw); margin: auto; padding: 20px 0 48px; }}
    .top-bar {{
      display: flex; justify-content: space-between; align-items: center;
      flex-wrap: wrap; gap: 12px; padding-bottom: 14px; margin-bottom: 20px;
      border-bottom: 1px solid var(--border-subtle);
    }}
    .brand-lockup {{ display: inline-flex; align-items: center; gap: 11px; text-decoration: none; color: inherit; min-width: 0; }}
    .brand-crests {{ display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0; }}
    .brand-crest {{ width: 40px; height: 46px; aspect-ratio: 5/6; object-fit: contain; border: 1px solid rgba(212,175,55,.65); border-radius: 5px; background: rgba(11,19,43,.88); padding: 2px; display: block; }}
    .brand-crest-divider {{ width: 1px; height: 34px; background: linear-gradient(180deg,transparent,rgba(212,175,55,.78),transparent); }}
    .brand-stack {{ display: flex; flex-direction: column; min-width: 0; line-height: 1.22; }}
    .brand-title {{ font-size: .78rem; font-weight: 800; letter-spacing: .08em; color: #F8FAFC; }}
    .brand-motto {{ font-size: .71rem; font-style: italic; color: #D8C48B; }}
    .nav-strip {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 18px; align-items: center; }}
    .plane-pill {{ display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 999px; background: #132A24; border: 1px solid #059669; color: #A7F3D0; font-size: 0.82rem; font-weight: 700; }}
    .hero-card {{
      background: var(--bg-card); border: 1px solid var(--border-subtle);
      border-radius: 18px; padding: 24px; display: flex; gap: 24px;
      align-items: center; flex-wrap: wrap; margin-bottom: 20px;
    }}
    .crest-frame {{
      width: 210px; max-width: 100%; aspect-ratio: 9 / 8; border-radius: 14px;
      border: 2px solid rgba(228,187,99,0.78); background: #0B132B;
      padding: 8px; display: grid; place-items: center; flex-shrink: 0;
    }}
    .crest-frame img {{ width: 100%; height: 100%; object-fit: contain; display: block; }}
    .hero-copy {{ flex: 1; min-width: 240px; }}
    .eyebrow {{ color: var(--gold); font-size: 0.8rem; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; }}
    h1 {{ margin: 6px 0 8px; font-size: clamp(1.5rem, 3vw, 2.15rem); color: var(--text-primary); }}
    .subtitle {{ color: #F6DE8D; font-style: italic; margin: 0; font-size: 1.05rem; }}
    .card {{ background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: 14px; padding: 22px; margin-bottom: 18px; }}
    .card h2 {{ margin-top: 0; color: var(--accent-sky); font-size: 1.18rem; }}
    .card p {{ color: var(--text-secondary); }}
    .chip-grid {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    .surname-chip {{
      display: inline-flex; align-items: center; gap: 8px; min-height: 44px;
      padding: 8px 14px; border-radius: 10px; background: var(--bg-surface);
      border: 1px solid var(--border-subtle); color: var(--text-primary);
      text-decoration: none; font-weight: 700;
    }}
    .surname-chip:hover {{ border-color: var(--gold); color: #F6DE8D; }}
    .meta-note {{ color: var(--text-muted); font-size: 0.85rem; }}
    .pdeue-colophon {{
      margin-top: 28px; padding: 12px 4px; border-top: 1px solid var(--border-subtle);
      display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;
      gap: 10px; color: var(--text-muted); font-size: 0.78rem;
    }}
    .colophon-mode-badge {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.72rem; font-weight: 700; padding: 3px 9px; border-radius: 999px;
      background: var(--bg-surface); border: 1px solid var(--border-subtle); color: var(--text-secondary);
    }}
  </style>
</head>
<body>
<div style="display:none" id="legacyPortalHub">PDEUE PORTAL HUB</div>
<main class="shell">
  <div class="top-bar">
    <a href="{heritage_url}" class="brand-lockup" data-plane-doorway="heritage" data-heritage-target="/community/heritage" aria-label="FUTURE Carmichael-McCormick Hall of Arms">
      <span class="brand-crests">
        <img class="brand-crest" src="/static/assets/crests/carmichael_crest.svg" alt="Carmichael Family Crest" width="40" height="46" loading="eager">
        <span class="brand-crest-divider" aria-hidden="true"></span>
        <img class="brand-crest" src="/static/assets/crests/mccormick_crest.svg" alt="McCormick Family Crest" width="40" height="46" loading="eager">
      </span>
      <span class="brand-stack">
        <span class="brand-title">FUTURE · CARMICHAEL — McCORMICK</span>
        <span class="brand-motto">Generational Love, Harmony, Resilience, and Wealth</span>
      </span>
    </a>
    <div class="senior-a11y-controls">
      <a id="backToHomeBtn" class="back-home-btn" href="{home_url}" data-plane-doorway="home">← Back to Home</a>
      <a id="backToHallBtn" class="back-home-btn" href="{heritage_url}" data-plane-doorway="heritage">← Back to Hall of Arms</a>
      <div id="textScaleGroup" class="text-scale-group" role="group" aria-label="Text size controls">
        <button type="button" class="text-scale-btn active" data-scale="standard" aria-pressed="true" aria-label="Standard text size" onclick="window.PDEUESeniorA11y && window.PDEUESeniorA11y.setScale('standard')">A</button>
        <button type="button" class="text-scale-btn" data-scale="large" aria-pressed="false" aria-label="Large text size" onclick="window.PDEUESeniorA11y && window.PDEUESeniorA11y.setScale('large')">A+</button>
        <button type="button" class="text-scale-btn" data-scale="xlarge" aria-pressed="false" aria-label="Extra large text size" onclick="window.PDEUESeniorA11y && window.PDEUESeniorA11y.setScale('xlarge')">A++</button>
      </div>
    </div>
  </div>

  <div class="nav-strip">
    <span class="plane-pill">Family Social Space — No Financial Data</span>
  </div>

  <header class="hero-card">
    <div class="crest-frame">
      <img src="{html.escape(crest_path, quote=True)}" alt="{html.escape(crest_alt, quote=True)}">
    </div>
    <div class="hero-copy">
      <div class="eyebrow">{html.escape(eyebrow)}</div>
      <h1>{heading}</h1>
      <p class="subtitle">{subtitle}</p>
    </div>
  </header>

  <section class="card">
    <h2>Lineage Story &amp; Family Chronicle</h2>
    {paragraphs}
    <p class="meta-note">Curated by: <strong>{html.escape(updated_by)}</strong> · Last updated: {html.escape(updated_at[:10])}</p>
  </section>

  {extra_sections_html}

  <footer class="pdeue-colophon" role="contentinfo">
    <span class="colophon-attr">Powered by CARM Aerotech Corporation</span>
    <span class="colophon-mode-badge">FAMILY HERITAGE ARCHIVE · ZERO FINANCIAL DATA</span>
  </footer>
</main>
<script src="/static/js/senior_a11y.js"></script>
</body>
</html>"""
    return HTMLResponse(page)


@social_plane_router.get("/community/heritage/house/{house_id}", response_class=HTMLResponse)
def get_heritage_house_history_page(house_id: int):
    """Serve an individual House's genealogist-managed Family History Page."""
    house = get_heritage_community_service().get_house_history(house_id)
    bordure = house.get("bordure_differencing") or {}
    surnames_html = "".join(
        f'<a class="surname-chip" href="/community/heritage/surname/{html.escape(s["slug"], quote=True)}">'
        f'{s["surname"]}</a>'
        for s in house.get("surnames", [])
    )
    milestones_html = "".join(
        f"<li>{m}</li>" for m in house.get("milestones", [])
    ) or "<li>House chronicle opened in the Hall of Arms.</li>"
    heraldry_note = html.escape(bordure.get("blazon_note") or house.get("lineage_descent") or "")
    heraldry_style = html.escape(
        f"{bordure.get('border_style', 'Standard')} · {bordure.get('tincture', 'Gold')}"
    )
    symbolism = house.get("heraldic_symbolism") or {}
    symbolism_html = ""
    if symbolism:
        symbolism_html = (
            '<ul style="margin:10px 0 0;padding-left:20px;color:var(--text-secondary);">'
            f'<li><strong>Motto:</strong> {html.escape(str(symbolism.get("motto", "")))}</li>'
            f'<li><strong>Crest:</strong> {html.escape(str(symbolism.get("crest", "")))}</li>'
            f'<li><strong>Shield &amp; Coronet:</strong> {html.escape(str(symbolism.get("shield_and_coronet", "")))}</li>'
            f'<li><strong>Supporters &amp; Compartment:</strong> {html.escape(str(symbolism.get("supporters_and_compartment", "")))}</li>'
            '</ul>'
        )
    extra = (
        '<section class="card">'
        '<h2>Heraldic Blazon &amp; Lineage Descent</h2>'
        f'<p><strong>Lineage Descent:</strong> {html.escape(house.get("lineage_descent", house["founding_branch"]))}</p>'
        f'<p><strong>Heraldic Treatment:</strong> {heraldry_style}</p>'
        f'{symbolism_html or f"<p>{heraldry_note}</p>"}'
        '</section>'
        '<section class="card">'
        '<h2>Allied &amp; Founding Surnames in This House</h2>'
        f'<div class="chip-grid">{surnames_html or "<span class=meta-note>No linked surnames recorded yet.</span>"}</div>'
        '</section>'
        '<section class="card">'
        '<h2>Recorded House Milestones</h2>'
        f'<ul>{milestones_html}</ul>'
        '</section>'
    )
    showcase_crest = house.get("achievement_asset_path") or house["crest_asset_path"]
    return _render_detail_page(
        page_title=f"{house['lineage_code']} · {html.unescape(house['house_name'])}",
        eyebrow=f"HALL OF ARMS · {house['lineage_code']} · {house['founding_branch']}",
        heading=house["house_name"],
        subtitle=house["motto"],
        crest_path=showcase_crest,
        crest_alt=f"{html.unescape(house['house_name'])} Heraldic Crest",
        history_body=house["history_body"],
        extra_sections_html=extra,
        updated_by=house["updated_by"],
        updated_at=house["updated_at_utc"],
    )


@social_plane_router.get("/community/heritage/surname/{slug}", response_class=HTMLResponse)
def get_heritage_surname_history_page(slug: str):
    """Serve an individual surname's Family History Page linked to its parent House."""
    record = get_heritage_community_service().get_surname_history(slug)
    parent_house_url = html.escape(record.get("house_history_url", f"/community/heritage/house/{record['house_id']}"), quote=True)
    parent_house_name = record.get("house_name", f"House {record['house_id']:02d}")
    badge_kind = "FOUNDING PILLAR SURNAME" if record["is_founding"] else "ALLIED / MARRIED-IN SURNAME"
    extra = (
        '<section class="card">'
        '<h2>Parent House Connection</h2>'
        f'<p>This family line is cherished within <strong>{parent_house_name}</strong> ({record["lineage_code"]}).</p>'
        f'<p><a class="surname-chip" href="{parent_house_url}">Visit {parent_house_name} History →</a></p>'
        '</section>'
    )
    showcase_crest = record.get("achievement_asset_path") or record["crest_asset_path"]
    return _render_detail_page(
        page_title=f"{html.unescape(record['surname'])} Family Heritage",
        eyebrow=f"HALL OF ARMS · {badge_kind} · {record['lineage_code']}",
        heading=f"The {record['surname']} Family Line",
        subtitle=record["origin_summary"],
        crest_path=showcase_crest,
        crest_alt=f"{html.unescape(record['surname'])} Heraldic Achievement",
        history_body=record["history_body"],
        extra_sections_html=extra,
        updated_by=record["updated_by"],
        updated_at=record["updated_at_utc"],
    )


@social_plane_router.get("/api/v1/portal/community/heritage")
def get_heritage_gallery_api(
    q: Optional[str] = Query(None, description="Search Houses, mottos, or surnames"),
    house_id: Optional[int] = Query(None, ge=1, le=12, description="Filter by House 1..12"),
) -> Dict[str, Any]:
    return get_heritage_community_service().list_heritage_gallery(q=q, house_id=house_id)


@social_plane_router.get("/api/v1/portal/community/heritage/house/{house_id}")
def get_heritage_house_api(house_id: int) -> Dict[str, Any]:
    return get_heritage_community_service().get_house_history(house_id)


@social_plane_router.get("/api/v1/portal/community/heritage/surname/{slug}")
def get_heritage_surname_api(slug: str) -> Dict[str, Any]:
    return get_heritage_community_service().get_surname_history(slug)


@social_plane_router.post("/api/v1/portal/community/heritage/house/{house_id}")
def update_heritage_house_api(
    house_id: int,
    request: HeritageHouseUpdateRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
) -> Dict[str, Any]:
    role, actor_id, _ = _resolve_social_caller(
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        x_house_id=x_house_id,
        body_role=request.actor_role,
        body_actor_id=request.actor_id,
    )
    return get_heritage_community_service().update_house_history(
        house_id=house_id,
        house_name=request.house_name,
        motto=request.motto,
        history_body=request.history_body,
        milestones=request.milestones,
        crest_asset_path=request.crest_asset_path,
        actor_role=role,
        actor_id=actor_id,
    )


@social_plane_router.post("/api/v1/portal/community/heritage/surname")
def upsert_heritage_surname_api(
    request: HeritageSurnameUpsertRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
) -> Dict[str, Any]:
    role, actor_id, _ = _resolve_social_caller(
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        x_house_id=x_house_id,
        body_role=request.actor_role,
        body_actor_id=request.actor_id,
    )
    return get_heritage_community_service().upsert_surname_record(
        surname=request.surname,
        house_id=request.house_id,
        origin_summary=request.origin_summary,
        history_body=request.history_body,
        crest_asset_path=request.crest_asset_path,
        actor_role=role,
        actor_id=actor_id,
    )


# ----------------------------------------------------------------------
# Isolated Family Notifications & Alerts API
# ----------------------------------------------------------------------
@social_plane_router.get("/api/v1/portal/community/notifications")
def list_community_notifications_api(
    house_id: Optional[int] = Query(None, ge=1, le=12),
    category: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=100),
) -> Dict[str, Any]:
    return get_heritage_community_service().list_notifications(
        house_id=house_id,
        category=category,
        limit=limit,
    )


@social_plane_router.post("/api/v1/portal/community/notifications/broadcast", status_code=201)
def broadcast_community_notification_api(
    request: NotificationBroadcastRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
) -> Dict[str, Any]:
    role, actor_id, _ = _resolve_social_caller(
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        body_role=request.actor_role,
        body_actor_id=request.actor_id,
    )
    return get_heritage_community_service().broadcast_notification(
        title=request.title,
        message=request.message,
        category=request.category or "ANNOUNCEMENT",
        target_house_id=request.target_house_id,
        action_url=request.action_url or "/community",
        channels=request.channels,
        actor_role=role,
        actor_id=actor_id,
        strict_r12_reject=request.strict_r12_reject,
    )


# ----------------------------------------------------------------------
# Interactive Zero-CDN Family Tree (/community/heritage/tree) & APIs
# ----------------------------------------------------------------------
_CURATION_START_MARKER = "<!-- __TREE_CURATION_START__ -->"
_CURATION_END_MARKER = "<!-- __TREE_CURATION_END__ -->"


@social_plane_router.get("/community/heritage/tree", response_class=HTMLResponse)
def get_interactive_family_tree_portal(
    role: Optional[str] = Query(None, description="Optional role preview query (HOUSE_GENEALOGIST / CHIEF_ADMIN)"),
    house_id: Optional[str] = Query(None, description="Optional House scope query (HOUSE-01..HOUSE-12)"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_pdeue_role: Optional[str] = Header(None, alias="X-PDEUE-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
):
    """Serve the zero-CDN Interactive Family Tree & Relationship Calculator portal.

    The collapsible Genealogist Tree Curation Drawer is rendered ONLY for
    HOUSE_GENEALOGIST and CHIEF_ADMIN callers; standard members receive a clean
    read-only view with mutation forms stripped server-side.
    """
    resolved_role, resolved_actor, claimed_house = _resolve_social_caller(
        authorization=authorization,
        x_active_hat=x_active_hat or x_pdeue_role,
        x_actor_role=x_actor_role or role,
        x_actor_id=x_actor_id,
        x_house_id=x_house_id or house_id,
    )
    can_curate = is_chief_admin_role(resolved_role) or resolved_role == "HOUSE_GENEALOGIST"
    assigned_house_code = (
        f"HOUSE-{claimed_house:02d}"
        if (claimed_house is not None and 1 <= claimed_house <= 12)
        else ""
    )

    markup = _load_social_html("heritage_tree.html")
    if not can_curate and _CURATION_START_MARKER in markup and _CURATION_END_MARKER in markup:
        before, rest = markup.split(_CURATION_START_MARKER, 1)
        _, after = rest.split(_CURATION_END_MARKER, 1)
        readonly_notice = (
            '<section id="treeReadOnlyBanner" class="readonly-curation-banner" aria-label="Read-Only Family Tree Notice">'
            '<strong>🔒 Read-Only Family View:</strong> Living-member privacy protection is active. '
            'Adding or editing people and relationships is restricted to assigned <strong>House Genealogists</strong> '
            '(within their own House) and the <strong>Chief Administrator</strong>.'
            '</section>'
        )
        markup = before + readonly_notice + after

    markup = markup.replace("__TREE_ACTIVE_ROLE__", html.escape(resolved_role or "MEMBER_USER", quote=True))
    markup = markup.replace("__TREE_ASSIGNED_HOUSE__", html.escape(assigned_house_code, quote=True))
    markup = markup.replace("__TREE_ACTOR_ID__", html.escape(resolved_actor, quote=True))
    markup = markup.replace("__TREE_CAN_CURATE__", "true" if can_curate else "false")
    return HTMLResponse(markup)


@social_plane_router.get("/api/v1/community/heritage/tree/data")
def get_family_tree_data_api(
    house_id: Optional[str] = Query(None, description="Filter by HOUSE-01..HOUSE-12, FOUNDERS, or REFERENCE"),
    surname: Optional[str] = Query(None, description="Filter by exact surname"),
    q: Optional[str] = Query(None, description="Search by name, House, surname, or notes"),
    include_reference: bool = Query(False, description="Include disconnected historical reference branches"),
) -> Dict[str, Any]:
    return get_family_tree_service().get_tree_data(
        house_id=house_id,
        surname=surname,
        q=q,
        include_reference=include_reference,
    )


@social_plane_router.get("/api/v1/community/heritage/tree/subtree")
def get_family_tree_subtree_query_api(
    root_person_id: str = Query(..., description="Root person_id to isolate as sub-tree (e.g. P0018)"),
) -> Dict[str, Any]:
    return get_family_tree_service().get_subtree_data(root_person_id)


@social_plane_router.get("/api/v1/community/heritage/tree/subtree/{person_id}")
def get_family_tree_subtree_api(
    person_id: str,
) -> Dict[str, Any]:
    return get_family_tree_service().get_subtree_data(person_id)


@social_plane_router.get("/api/v1/community/heritage/tree/relationship")
def compute_family_tree_relationship_api(
    person_a: str = Query(..., description="First person_id (e.g. P0004)"),
    person_b: str = Query(..., description="Second person_id (e.g. P0019)"),
) -> Dict[str, Any]:
    return get_family_tree_service().compute_relationship(person_a, person_b)


@social_plane_router.post("/api/v1/community/heritage/tree/person", status_code=201)
def create_family_tree_person_api(
    request: FamilyTreePersonCreateRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_pdeue_role: Optional[str] = Header(None, alias="X-PDEUE-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
) -> Dict[str, Any]:
    role, actor_id, claimed_house = _resolve_social_caller(
        authorization=authorization,
        x_active_hat=x_active_hat or x_pdeue_role,
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        x_house_id=x_house_id,
        body_role=request.actor_role,
        body_actor_id=request.actor_id,
    )
    return get_family_tree_service().create_person(
        person_id=request.person_id,
        full_name=request.full_name,
        given_name=request.given_name,
        surname=request.surname or "",
        suffix=request.suffix or "",
        nickname=request.nickname or "",
        house_id=request.house_id,
        generation=request.generation,
        is_deceased=request.is_deceased,
        birth_year=request.birth_year,
        death_year=request.death_year,
        bio_notes=request.bio_notes or "",
        source_tag=request.source_tag or "GENEALOGIST_ENTRY",
        review_flag=request.review_flag or "",
        is_reference_branch=request.is_reference_branch,
        actor_role=role,
        actor_id=actor_id,
        claimed_house_id=claimed_house,
    )


@social_plane_router.patch("/api/v1/community/heritage/tree/person/{person_id}")
def update_family_tree_person_api(
    person_id: str,
    request: FamilyTreePersonUpdateRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_pdeue_role: Optional[str] = Header(None, alias="X-PDEUE-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
) -> Dict[str, Any]:
    role, actor_id, claimed_house = _resolve_social_caller(
        authorization=authorization,
        x_active_hat=x_active_hat or x_pdeue_role,
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        x_house_id=x_house_id,
        body_role=request.actor_role,
        body_actor_id=request.actor_id,
    )
    return get_family_tree_service().update_person(
        person_id=person_id,
        full_name=request.full_name,
        given_name=request.given_name,
        surname=request.surname,
        suffix=request.suffix,
        nickname=request.nickname,
        house_id=request.house_id,
        generation=request.generation,
        is_deceased=request.is_deceased,
        birth_year=request.birth_year,
        death_year=request.death_year,
        bio_notes=request.bio_notes,
        source_tag=request.source_tag,
        review_flag=request.review_flag,
        actor_role=role,
        actor_id=actor_id,
        claimed_house_id=claimed_house,
    )


@social_plane_router.post("/api/v1/community/heritage/tree/relationship", status_code=201)
def create_family_tree_relationship_api(
    request: FamilyTreeRelationshipCreateRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_pdeue_role: Optional[str] = Header(None, alias="X-PDEUE-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
) -> Dict[str, Any]:
    role, actor_id, claimed_house = _resolve_social_caller(
        authorization=authorization,
        x_active_hat=x_active_hat or x_pdeue_role,
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        x_house_id=x_house_id,
        body_role=request.actor_role,
        body_actor_id=request.actor_id,
    )
    return get_family_tree_service().create_relationship(
        rel_type=request.rel_type,
        person_a_id=request.person_a_id,
        person_b_id=request.person_b_id,
        notes=request.notes or "",
        source_tag=request.source_tag or "GENEALOGIST_ENTRY",
        actor_role=role,
        actor_id=actor_id,
        claimed_house_id=claimed_house,
    )

