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

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.core.security import decode_access_token
from app.domain.authority_tiers import (
    is_chief_admin_role,
    is_class_t_role,
    normalize_role_token,
)
from app.domain.heritage_community_service import (
    get_heritage_community_service,
    sanitize_social_text,
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


def _load_social_html(filename: str) -> str:
    api_page = pathlib.Path(__file__).parent / filename
    if api_page.exists():
        return api_page.read_text(encoding="utf-8")
    static_page = pathlib.Path(__file__).parent.parent.parent / "static" / filename
    if static_page.exists():
        return static_page.read_text(encoding="utf-8")
    raise HTTPException(status_code=500, detail=f"Social plane template {filename} missing")


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
            '<a id="roleDoorwayCard" class="doorway-card doorway-role-card" href="' + href + '" data-role-door="CHIEF_ADMIN">'
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
            '<a id="roleDoorwayCard" class="doorway-card doorway-role-card" href="' + href + '" data-role-door="' + html.escape(role, quote=True) + '">'
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
            '<a id="roleDoorwayCard" class="doorway-card doorway-role-card" href="' + href + '" data-role-door="HOUSE_GENEALOGIST">'
            '<span class="doorway-icon" aria-hidden="true">📜</span>'
            '<span class="doorway-tag role-tag">ASSIGNED HAT · HOUSE GENEALOGIST</span>'
            '<h2>House Genealogist Desk</h2>'
            '<p>Curate your assigned House history, motto, and allied family surname biographies in the Hall of Arms.</p>'
            '<span class="doorway-cta">Open Genealogist Desk →</span>'
            '</a>'
        )

    if is_class_t_role(role):
        tier = role if role in {"T1", "T2", "T2-HOUSEHOLD", "T3"} else "T1"
        href = html.escape(f"{doorways['tech']}?tier={tier}", quote=True)
        return (
            '<a id="roleDoorwayCard" class="doorway-card doorway-role-card" href="' + href + '" data-role-door="' + html.escape(tier, quote=True) + '">'
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
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
):
    """Serve the calm, senior-friendly 4-card Central Family Home Hub."""
    plane_cfg = get_plane_config()
    doorways = plane_cfg["doorways"]
    role, actor_id, claimed_house = _resolve_social_caller(
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        x_house_id=x_house_id,
    )
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
def ask_community_tutor(request: CommunityTutorRequest) -> Dict[str, str]:
    query = sanitize_social_text(request.query, field="query", maximum=500)
    member_id = sanitize_social_text(request.member_id, field="member_id", maximum=80)
    lowered = html.unescape(query).lower()
    mutation_phrases = (
        "buy ", "sell ", "place an order", "execute", "submit a trade",
        "make a trade", "cancel order", "transfer", "withdraw", "deposit",
    )
    balance_phrases = ("my balance", "account balance", "capital balance", "bank balance", "how much money")
    if any(phrase in lowered for phrase in mutation_phrases + balance_phrases):
        raise HTTPException(
            status_code=403,
            detail="The academy tutor is educational only and cannot access balances or perform transactions.",
        )

    if "quarter-kelly" in lowered or "quarter kelly" in lowered:
        answer = "Quarter-Kelly uses one fourth of a model's Kelly-sized exposure. It keeps the idea of scaling with confidence while adding a large cushion for estimation error and uncertainty."
        concept = "RISK_SIZING"
    elif "binary" in lowered:
        answer = "A binary contract has two possible settlement outcomes. Its quoted probability is a learning aid, not a promise; uncertainty and calibration still matter."
        concept = "BINARY_CONTRACT_FOUNDATIONS"
    elif "87/10/3" in lowered or "waterfall" in lowered:
        answer = "The 87/10/3 lesson describes a stewardship safeguard: three defined portions help learners reason about compounding, family protection, and education support without directing a transaction."
        concept = "WATERFALL_STEWARDSHIP"
    elif "pay-it-forward" in lowered or "lccf" in lowered:
        answer = "Pay-it-Forward (LCCF) is our voluntary family sponsorship charter. Solvent patrons help relatives through IFAS without ever cross-collateralizing or mixing personal accounts."
        concept = "LCCF_STEWARDSHIP"
    else:
        answer = "Start by naming the outcome, the uncertainty, and what evidence could change your view. Good risk literacy separates an educational estimate from a guaranteed result."
        concept = "RISK_LITERACY"
    return {"member_id": member_id, "query": query, "answer": answer, "concept": concept, "mode": "EDUCATIONAL_ONLY"}


# ----------------------------------------------------------------------
# Hall of Arms (/community/heritage) & Individual History Pages
# ----------------------------------------------------------------------
@social_plane_router.get("/community/heritage", response_class=HTMLResponse)
def get_hall_of_arms_portal():
    """Serve the Hall of Arms gallery for the founding crests, 12 Houses, and 28+ allied surnames."""
    return HTMLResponse(_load_social_html("heritage.html"))


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
      width: 130px; aspect-ratio: 5/6; border-radius: 14px;
      border: 2px solid rgba(228,187,99,0.75); background: #0B132B;
      padding: 10px; display: grid; place-items: center; flex-shrink: 0;
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
    surnames_html = "".join(
        f'<a class="surname-chip" href="/community/heritage/surname/{html.escape(s["slug"], quote=True)}">'
        f'{s["surname"]}</a>'
        for s in house.get("surnames", [])
    )
    milestones_html = "".join(
        f"<li>{m}</li>" for m in house.get("milestones", [])
    ) or "<li>House chronicle opened in the Hall of Arms.</li>"
    extra = (
        '<section class="card">'
        '<h2>Allied &amp; Founding Surnames in This House</h2>'
        f'<div class="chip-grid">{surnames_html or "<span class=meta-note>No linked surnames recorded yet.</span>"}</div>'
        '</section>'
        '<section class="card">'
        '<h2>Recorded House Milestones</h2>'
        f'<ul>{milestones_html}</ul>'
        '</section>'
    )
    return _render_detail_page(
        page_title=f"{house['lineage_code']} · {html.unescape(house['house_name'])}",
        eyebrow=f"HALL OF ARMS · {house['lineage_code']} · {house['founding_branch']}",
        heading=house["house_name"],
        subtitle=house["motto"],
        crest_path=house["crest_asset_path"],
        crest_alt=f"{html.unescape(house['house_name'])} Crest",
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
    return _render_detail_page(
        page_title=f"{html.unescape(record['surname'])} Family Heritage",
        eyebrow=f"HALL OF ARMS · {badge_kind} · {record['lineage_code']}",
        heading=f"The {record['surname']} Family Line",
        subtitle=record["origin_summary"],
        crest_path=record["crest_asset_path"],
        crest_alt=f"{html.unescape(record['surname'])} Crest",
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
