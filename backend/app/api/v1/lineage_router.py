"""
PDEUE Lineage & House Leader Desk Router (Class H)
Enforces strict Lineal branch confinement, subordinate roster controls,
institutional intervention modals with zero native alerts, and bicameral consensus.
"""
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from typing import Dict, Any, List, Optional
from app.domain.lineage_hierarchy import get_lineage_service
from app.domain.enclave_governance import (
    DEFAULT_BODY_ID,
    MODE_EXECUTIVE_COMMAND,
    format_cents,
    get_enclave_governance_service,
)
from app.domain.authority_tiers import (
    enforce_founder_immunity,
    get_active_hat_gateway,
    get_governance_audit_log,
    is_chief_admin_role,
    is_class_t_role,
    is_founder_target,
    normalize_role_token,
)

lineage_router = APIRouter()
_lineage_service = get_lineage_service()
_enclave_gov = get_enclave_governance_service()


def _resolve_actor_context(
    *,
    x_actor_role: Optional[str] = None,
    x_actor_id: Optional[str] = None,
    authorization: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> tuple[str, str]:
    """Resolve authenticated actor_role and actor_id, enforcing Directive R-06 if Bearer JWT is sent."""
    role = x_actor_role or (str(payload.get("actor_role") or "") if isinstance(payload, dict) else "")
    actor_id = x_actor_id or (str(payload.get("actor_id") or "") if isinstance(payload, dict) else "")
    if authorization and authorization.lower().startswith("bearer "):
        from app.core.security import decode_access_token
        token = authorization.split(" ", 1)[1].strip()
        claims = decode_access_token(token)
        if not claims:
            raise HTTPException(status_code=403, detail="INVALID_OR_EXPIRED_ACTIVE_HAT_TOKEN")
        hat = normalize_role_token(claims.get("active_hat") or claims.get("role"))
        if claims.get("session_id"):
            get_active_hat_gateway().verify_token(
                token,
                required_hats={hat},
                action="GOVERNANCE_API",
            )
        role = hat
        actor_id = str(claims.get("sub") or claims.get("user_id") or actor_id or "jwt_principal")
    return normalize_role_token(role), actor_id or normalize_role_token(role) or "anonymous"


def _enforce_cross_house_boundary(
    house_id: int,
    *,
    x_house_id: Optional[str] = None,
    actor_house_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    action: str = "HOUSE_ACCESS",
) -> None:
    if is_chief_admin_role(actor_role):
        return
    raw = actor_house_id if actor_house_id is not None else x_house_id
    if raw is None:
        return
    try:
        claimed = int(str(raw).strip().upper().replace("HOUSE-", ""))
    except ValueError as err:
        raise HTTPException(status_code=403, detail="Invalid House identity claim") from err
    if claimed != house_id:
        get_governance_audit_log().record(
            event_type="CROSS_HOUSE_ACCESS_DENIED",
            actor_id=f"HOUSE-{claimed:02d}",
            actor_role=normalize_role_token(actor_role) or "CLASS_H",
            target_id=f"HOUSE-{house_id:02d}",
            action=action,
            outcome="DENIED_CROSS_HOUSE",
            http_status=403,
            detail=f"Blocked cross-house access from HOUSE-{claimed:02d} to HOUSE-{house_id:02d}.",
        )
        raise HTTPException(status_code=403, detail="Cross-House access forbidden")


def _enforce_non_h1_non_t(actor_role: Optional[str], *, actor_id: str, target_id: str, action: str) -> None:
    if actor_role and is_class_t_role(actor_role):
        get_governance_audit_log().record(
            event_type="ROLE_BOUNDARY_DENIED",
            actor_id=actor_id,
            actor_role=normalize_role_token(actor_role),
            target_id=target_id,
            action=action,
            outcome="DENIED_CLASS_T_ZERO_HOUSE_AUTHORITY",
            http_status=403,
            detail="Class T technical operators inherit zero House or household authority.",
        )
        raise HTTPException(status_code=403, detail="Class T technical roles have zero House or household authority.")
    if actor_role and normalize_role_token(actor_role) == "H1":
        get_governance_audit_log().record(
            event_type="ROLE_BOUNDARY_DENIED",
            actor_id=actor_id,
            actor_role="H1",
            target_id=target_id,
            action=action,
            outcome="DENIED_H1_SECRETARIAL_ONLY",
            http_status=403,
            detail="H1 House Secretary has secretarial registry visibility only and cannot operate circuit breakers.",
        )
        raise HTTPException(status_code=403, detail="H1 secretarial role cannot operate House circuit breakers.")


def _build_member_table_rows(members: List[Dict[str, Any]], house_id: int) -> str:
    rows = []
    for m in members:
        orders = m.get("open_orders", [])
        orders_str = ", ".join(orders) if orders else "None"
        status = m.get("status", "ACTIVE")
        status_color = "#10b981" if status == "ACTIVE" else "#ef4444"
        cash = format_cents(int(m.get('cash_cents', 0)))
        dial = f"{m.get('risk_dial', 0.0) * 100:.1f}%"
        scma = m.get("scma_id", "")
        name = m.get("name", "")
        order_count = len(orders)
        if _lineage_service._is_sovereign_settlor(m):
            actions = (
                "<span style='background:#1e293b;border:1px solid #38bdf8;color:#38bdf8;"
                "padding:4px 8px;border-radius:4px;font-weight:bold;font-size:11px;'>"
                "🛡️ Sovereign Immune</span>"
            )
        else:
            actions = (
                f"<button class='btn-cancel' onclick=\"openCancelModal('{name}', '{scma}', {order_count}, '{orders_str}')\">Cancel Orders</button>"
                f"<button class='btn-freeze' onclick=\"openFreezeModal('{name}', '{scma}', '{dial}')\">Freeze Dial (0%)</button>"
            )

        r = (
            f"<tr>"
            f"<td><b><a href='/member?scma_id={scma}' style='color:#38bdf8;text-decoration:underline;'>{name}</a></b></td>"
            f"<td style='font-family: monospace; color: #38bdf8;'>{scma}</td>"
            f"<td style='font-variant-numeric: tabular-nums;'>{cash}</td>"
            f"<td><b>{dial}</b></td>"
            f"<td>{order_count} resting ({orders_str})</td>"
            f"<td><span style='color: {status_color}; font-weight: bold;'>{status}</span></td>"
            f"<td><div style='display: flex; gap: 6px;'>{actions}</div></td>"
            f"</tr>"
        )
        rows.append(r)
    return "".join(rows)

@lineage_router.get("/api/v1/lineage/houses")
def get_all_houses():
    return {"houses": _lineage_service.list_all_houses()}

@lineage_router.get("/api/v1/lineage/house/{house_id}")
def get_house_detail(
    house_id: int,
    role: Optional[str] = Query(None),
    actor_house_id: Optional[int] = Query(None),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
):
    if house_id < 1 or house_id > 12:
        raise HTTPException(status_code=400, detail="House ID must be between 1 and 12.")
    eff_role = normalize_role_token(role or x_actor_role)
    _enforce_cross_house_boundary(
        house_id,
        x_house_id=x_house_id,
        actor_house_id=actor_house_id,
        actor_role=eff_role,
        action="GET_HOUSE_DETAIL",
    )
    summary = _lineage_service.get_house_summary(house_id)
    if eff_role == "H1":
        masked_members = []
        for m in summary["members"]:
            masked = dict(m)
            masked["cash_cents"] = "$****.**"
            masked["cash_display"] = "$****.**"
            masked_members.append(masked)
        return {**summary, "members": masked_members, "r12_masked": True, "active_role": "H1"}
    return summary

@lineage_router.post("/api/v1/lineage/house/{house_id}/subordinate/cancel-orders")
def cancel_subordinate_orders(
    house_id: int,
    payload: Dict[str, Any],
    actor_house_id: Optional[int] = Query(None),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
):
    scma_id = payload.get("scma_id")
    if not scma_id:
        raise HTTPException(status_code=400, detail="Missing scma_id in payload.")
    actor_role = x_actor_role or payload.get("actor_role")
    _enforce_cross_house_boundary(
        house_id,
        x_house_id=x_house_id,
        actor_house_id=actor_house_id,
        actor_role=actor_role,
        action="CANCEL_SUBORDINATE_ORDERS",
    )
    _enforce_non_h1_non_t(
        actor_role,
        actor_id=str(payload.get("actor_id") or actor_role or "unknown"),
        target_id=str(scma_id),
        action="CANCEL_SUBORDINATE_ORDERS",
    )
    if actor_role and is_founder_target(scma_id):
        enforce_founder_immunity(
            target_id=scma_id,
            action="CANCEL_ORDERS",
            actor_role=actor_role,
            actor_id=str(payload.get("actor_id") or actor_role),
        )
    try:
        result = _lineage_service.cancel_subordinate_orders(house_id=house_id, scma_id=scma_id)
        if result.get("status") == "SOVEREIGN_IMMUNE":
            get_governance_audit_log().record(
                event_type="FOUNDER_IMMUNITY_ENFORCED",
                actor_id="lineage_router",
                actor_role="HOUSE_DELEGATE",
                target_id=str(scma_id),
                action="CANCEL_ORDERS",
                outcome="SOVEREIGN_IMMUNE",
                http_status=200,
                detail="Founder SCMA orders preserved under Sovereign Settlor immunity.",
            )
        return result
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))

@lineage_router.post("/api/v1/lineage/house/{house_id}/subordinate/freeze-risk")
def freeze_subordinate_risk(
    house_id: int,
    payload: Dict[str, Any],
    actor_house_id: Optional[int] = Query(None),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
):
    scma_id = payload.get("scma_id")
    if not scma_id:
        raise HTTPException(status_code=400, detail="Missing scma_id in payload.")
    actor_role = x_actor_role or payload.get("actor_role")
    _enforce_cross_house_boundary(
        house_id,
        x_house_id=x_house_id,
        actor_house_id=actor_house_id,
        actor_role=actor_role,
        action="FREEZE_SUBORDINATE_RISK",
    )
    _enforce_non_h1_non_t(
        actor_role,
        actor_id=str(payload.get("actor_id") or actor_role or "unknown"),
        target_id=str(scma_id),
        action="FREEZE_SUBORDINATE_RISK",
    )
    if actor_role and is_founder_target(scma_id):
        enforce_founder_immunity(
            target_id=scma_id,
            action="FREEZE_RISK",
            actor_role=actor_role,
            actor_id=str(payload.get("actor_id") or actor_role),
        )
    try:
        result = _lineage_service.freeze_subordinate_risk(house_id=house_id, scma_id=scma_id)
        if result.get("status") == "SOVEREIGN_IMMUNE":
            get_governance_audit_log().record(
                event_type="FOUNDER_IMMUNITY_ENFORCED",
                actor_id="lineage_router",
                actor_role="HOUSE_DELEGATE",
                target_id=str(scma_id),
                action="FREEZE_RISK",
                outcome="SOVEREIGN_IMMUNE",
                http_status=200,
                detail="Founder SCMA risk dial preserved under Sovereign Settlor immunity.",
            )
        return result
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))

@lineage_router.post("/api/v1/lineage/house/{house_id}/freeze")
def freeze_house(
    house_id: int,
    actor_house_id: Optional[int] = Query(None),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
):
    _enforce_cross_house_boundary(
        house_id,
        x_house_id=x_house_id,
        actor_house_id=actor_house_id,
        actor_role=x_actor_role,
        action="FREEZE_HOUSE",
    )
    _enforce_non_h1_non_t(
        x_actor_role,
        actor_id=str(x_actor_role or "unknown"),
        target_id=f"HOUSE-{house_id:02d}",
        action="FREEZE_HOUSE",
    )
    try:
        return _lineage_service.freeze_house(house_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))

@lineage_router.post("/api/v1/lineage/house/{house_id}/restore")
def restore_house(
    house_id: int,
    actor_house_id: Optional[int] = Query(None),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
):
    _enforce_cross_house_boundary(
        house_id,
        x_house_id=x_house_id,
        actor_house_id=actor_house_id,
        actor_role=x_actor_role,
        action="RESTORE_HOUSE",
    )
    _enforce_non_h1_non_t(
        x_actor_role,
        actor_id=str(x_actor_role or "unknown"),
        target_id=f"HOUSE-{house_id:02d}",
        action="RESTORE_HOUSE",
    )
    try:
        return _lineage_service.restore_house(house_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))

@lineage_router.post("/api/v1/lineage/house/{house_id}/subordinate/restore-risk")
def restore_subordinate_risk(
    house_id: int,
    payload: Dict[str, Any],
    actor_house_id: Optional[int] = Query(None),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
):
    actor_role = x_actor_role or payload.get("actor_role")
    _enforce_cross_house_boundary(
        house_id,
        x_house_id=x_house_id,
        actor_house_id=actor_house_id,
        actor_role=actor_role,
        action="RESTORE_SUBORDINATE_RISK",
    )
    _enforce_non_h1_non_t(
        actor_role,
        actor_id=str(payload.get("actor_id") or actor_role or "unknown"),
        target_id=str(payload.get("scma_id") or ""),
        action="RESTORE_SUBORDINATE_RISK",
    )
    scma_id = payload.get("scma_id")
    target_risk_dial = payload.get("target_risk_dial")
    if not scma_id or target_risk_dial is None:
        raise HTTPException(status_code=400, detail="Missing scma_id or target_risk_dial in payload.")
    try:
        return _lineage_service.restore_subordinate_risk(
            house_id, scma_id, float(target_risk_dial)
        )
    except (TypeError, ValueError) as err:
        raise HTTPException(status_code=400, detail=str(err))


@lineage_router.post("/api/v1/governance/accounts/{target_id}/action")
def execute_account_governance_action(
    target_id: str,
    payload: Dict[str, Any],
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
):
    """Enforce un-overridable Founder/Chief Administrator Apex immunity against freeze/quarantine/demote/revoke."""
    action = str(payload.get("action") or "").strip().upper()
    if action not in {"FREEZE", "QUARANTINE", "DEMOTE", "REVOKE"}:
        raise HTTPException(status_code=422, detail="action must be FREEZE, QUARANTINE, DEMOTE, or REVOKE")
    actor_role = x_actor_role or str(payload.get("actor_role") or "")
    actor_id = str(payload.get("actor_id") or actor_role or "unknown")
    norm_role = normalize_role_token(actor_role)

    # Un-overridable Founder Apex Immunity: no tier (including T3, F3, H2, F2-H) may freeze/quarantine/demote/revoke Founder.
    if is_founder_target(target_id):
        enforce_founder_immunity(
            target_id=target_id,
            action=action,
            actor_role=norm_role or "UNSPECIFIED",
            actor_id=actor_id,
        )

    if not is_chief_admin_role(norm_role):
        get_governance_audit_log().record(
            event_type="ROLE_BOUNDARY_DENIED",
            actor_id=actor_id,
            actor_role=norm_role or "UNSPECIFIED",
            target_id=target_id,
            action=action,
            outcome="DENIED_CHIEF_ADMIN_REQUIRED",
            http_status=403,
            detail=f"Role {norm_role or 'UNSPECIFIED'} lacks authority to {action} account {target_id}.",
        )
        raise HTTPException(status_code=403, detail="Chief Administrator authority is required for account governance actions.")

    audit = get_governance_audit_log().record(
        event_type="GOVERNANCE_ACCOUNT_ACTION",
        actor_id=actor_id,
        actor_role="CHIEF_ADMINISTRATOR",
        target_id=target_id,
        action=action,
        outcome="EXECUTED",
        http_status=200,
        detail=f"Chief Administrator executed {action} on subordinate account {target_id}.",
    )
    return {
        "status": f"{action}_APPLIED",
        "target_id": target_id,
        "action": action,
        "actor_role": "CHIEF_ADMINISTRATOR",
        "audit_event_id": audit["event_id"],
    }


@lineage_router.get("/api/v1/governance/audit-log")
def get_governance_audit_events(event_type: Optional[str] = None, limit: int = 100):
    return {
        "events": get_governance_audit_log().list_events(event_type=event_type, limit=limit),
    }

@lineage_router.post("/api/v1/lineage/governance/propose")
def evaluate_proposal(
    payload: Dict[str, Any],
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
):
    actor_role = x_actor_role or payload.get("actor_role")
    _enforce_non_h1_non_t(
        actor_role,
        actor_id=str(payload.get("actor_id") or actor_role or "HOUSE_DELEGATE"),
        target_id="GOVERNANCE_PROPOSE",
        action="PROPOSE_GOVERNANCE_PETITION",
    )
    if payload.get("title") or payload.get("description") or payload.get("proposal_category"):
        _enclave_gov.enforce_immutable_core_guardrail(
            title=str(payload.get("title") or ""),
            description=str(payload.get("description") or ""),
            proposal_category=str(payload.get("proposal_category") or "CFCP_GRANT"),
            actor_id=str(payload.get("actor_id") or "HOUSE_DELEGATE"),
            actor_role=actor_role or "H2",
        )
    if _enclave_gov.get_governance_mode()["governance_mode"] == MODE_EXECUTIVE_COMMAND:
        raise HTTPException(
            status_code=403,
            detail="EXECUTIVE_COMMAND_MODE_ACTIVE: Proposals and voting are dormant in Stage 1 Executive Command mode.",
        )
    votes = payload.get("affirmative_house_ids", [])
    return _lineage_service.evaluate_bicameral_proposal(votes)

@lineage_router.get("/lineage/house", response_class=HTMLResponse)
def get_house_leader_portal(house_id: int = 1):
    if house_id < 1 or house_id > 12:
        house_id = 1
    house = _lineage_service.get_house_summary(house_id)
    member_rows = _build_member_table_rows(house["members"], house["house_id"])

    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>PDEUE House Leader Desk - {house['lineage_code']}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
    body {{ background: #0b132b; color: #f8fafc; padding: 20px; }}
    .class-h-banner {{ background: #020617; border: 1px solid #334155; border-radius: 8px; padding: 10px 16px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }}
    .class-badge {{ background: #1e293b; color: #a855f7; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 12px; border: 1px solid #a855f7; }}
    .grid-4 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }}
    .card {{ background: #111c44; border: 1px solid #1e293b; border-radius: 8px; padding: 16px; }}
    .card-title {{ font-size: 11px; font-weight: bold; color: #94a3b8; text-transform: uppercase; margin-bottom: 6px; }}
    .card-value {{ font-size: 22px; font-weight: bold; margin-bottom: 4px; }}
    .card-sub {{ font-size: 12px; color: #94a3b8; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th {{ border-bottom: 1px solid #334155; text-align: left; padding: 10px 8px; color: #94a3b8; font-size: 12px; }}
    td {{ padding: 10px 8px; border-bottom: 1px solid #1e293b; font-size: 13px; }}
    .btn-cancel {{ background: #ef4444; color: #fff; border: 1px solid #f87171; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: bold; }}
    .btn-freeze {{ background: #f59e0b; color: #020617; border: 1px solid #fbbf24; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: bold; }}
    .modal-backdrop {{ display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(2, 6, 23, 0.85); backdrop-filter: blur(4px); z-index: 20000; align-items: center; justify-content: center; }}
    .modal-box {{ background: #111c44; border-radius: 10px; width: 540px; max-width: 90vw; padding: 24px; box-shadow: 0 16px 40px rgba(0, 0, 0, 0.7); animation: modalIn 0.2s ease-out; }}
    .brand-lockup {{ display: inline-flex; align-items: center; gap: 10px; text-decoration: none; color: inherit; }}
    .brand-crests {{ display: inline-flex; align-items: center; gap: 6px; }}
    .brand-crest {{ width: 40px; height: 46px; aspect-ratio: 5 / 6; object-fit: contain; border: 1px solid rgba(212, 175, 55, 0.6); border-radius: 5px; background: rgba(11, 19, 43, 0.88); padding: 2px; display: block; }}
    .brand-crest-divider {{ width: 1px; height: 34px; background: linear-gradient(180deg, transparent, rgba(212, 175, 55, 0.78), transparent); }}
    .brand-stack {{ display: flex; flex-direction: column; line-height: 1.2; }}
    .brand-title {{ font-size: 12px; font-weight: 800; letter-spacing: 0.08em; color: #F8FAFC; }}
    .brand-motto {{ font-size: 11px; font-style: italic; color: #D8C48B; }}
    .pdeue-colophon {{ margin-top: 24px; padding: 12px 4px; border-top: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; color: #94a3b8; font-size: 12px; }}
    .colophon-mode-badge {{ font-family: ui-monospace, monospace; font-size: 11px; font-weight: 700; padding: 3px 9px; border-radius: 999px; background: #1e293b; border: 1px solid #334155; color: #cbd5e1; }}
    @keyframes modalIn {{ from {{ opacity: 0; transform: scale(0.96); }} to {{ opacity: 1; transform: scale(1); }} }}
  </style>
</head>
<body>

  <div class="class-h-banner" style="flex-wrap: wrap; gap: 12px;">
    <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
      <a href="/community/heritage" class="brand-lockup" data-plane-doorway="heritage" data-heritage-target="/community/heritage" aria-label="FUTURE Carmichael-McCormick Heritage">
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
      <span class="class-badge">CLASS H SOVEREIGN DESK</span>
      <span style="font-weight: bold; color: #38bdf8;">{house['lineage_code']} &mdash; {house['name']}</span>
    </div>
    <span style="color: #94a3b8; font-size: 12px;">Leader: <b style="color: #f8fafc;">{house['leader_name']}</b></span>
  </div>

  <div class="grid-4">
    <div class="card">
      <div class="card-title">Aggregated House Capital</div>
      <div class="card-value" style="color: #4ade80;">{house['total_cash_formatted']}</div>
      <div class="card-sub">{house['member_count']} Subordinate Accounts</div>
    </div>
    <div class="card">
      <div class="card-title">Average Risk Dial</div>
      <div class="card-value" style="color: #38bdf8;">{house['average_risk_dial_pct']}%</div>
      <div class="card-sub">Quarter-Kelly Line Limit</div>
    </div>
    <div class="card">
      <div class="card-title">Bicameral Senate Seat</div>
      <div class="card-value" style="color: #a855f7;">Active Seat</div>
      <div class="card-sub">1 of 12 Sovereign Houses</div>
    </div>
    <div class="card">
      <div class="card-title">Oversight Status</div>
      <div class="card-value" style="color: #10b981;">COGNIZANT</div>
      <div class="card-sub">Local Branch Circuit Breaker Active</div>
    </div>
  </div>

  <div class="card">
    <div class="card-title" style="color: #38bdf8; margin-bottom: 8px;">Subordinate Member Accounts &amp; Lineal Controls</div>
    <table>
      <thead>
        <tr>
          <th>SUBORDINATE NAME</th>
          <th>SCMA IDENTIFIER</th>
          <th>CASH BALANCE</th>
          <th>RISK DIAL</th>
          <th>OPEN MAKER ORDERS</th>
          <th>STATUS</th>
          <th>LINEAL INTERVENTION ACTIONS</th>
        </tr>
      </thead>
      <tbody>
        {member_rows}
      </tbody>
    </table>
  </div>

  <footer class="pdeue-colophon" role="contentinfo">
    <span>Powered by CARM Aerotech Corporation</span>
    <span class="colophon-mode-badge">FAIL-CLOSED · PAPER / OBSERVATION MODE · GATE G1</span>
  </footer>

  <!-- CANCEL ORDERS MODAL -->
  <div id="cancel-modal" class="modal-backdrop">
    <div class="modal-box" style="border: 1px solid #ef4444;">
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 12px; margin-bottom: 16px;">
        <div style="display: flex; align-items: center; gap: 8px;">
          <span style="background: #ef4444; color: #fff; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 4px;">CIRCUIT BREAKER</span>
          <strong style="color: #f87171; font-size: 15px;">CANCEL RESTING MAKER ORDERS</strong>
        </div>
        <button onclick="closeModals()" style="background: transparent; border: none; color: #94a3b8; font-size: 18px; cursor: pointer;">✕</button>
      </div>

      <div style="background: #0b132b; border: 1px solid #1e293b; border-radius: 6px; padding: 12px; margin-bottom: 14px;">
        <div style="font-size: 12px; color: #94a3b8; margin-bottom: 4px;">Target Subordinate</div>
        <div style="font-size: 15px; font-weight: bold; color: #f8fafc;" id="cancel-subordinate-name">--</div>
        <div style="font-family: monospace; font-size: 12px; color: #38bdf8; margin-top: 2px;" id="cancel-subordinate-scma">--</div>
      </div>

      <div style="background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 6px; padding: 12px; margin-bottom: 16px;">
        <div style="font-size: 12px; color: #fca5a5; line-height: 1.4;">
          This action will immediately revoke all <b>resting inside-maker orders</b> (<span id="cancel-orders-detail">None</span>) on venue books for this subordinate and release committed margin back into available cash.
        </div>
      </div>

      <div id="cancel-actions" style="display: flex; justify-content: flex-end; gap: 10px;">
        <button onclick="closeModals()" style="background: #334155; color: #cbd5e1; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 13px;">Dismiss</button>
        <button id="cancel-confirm-btn" onclick="executeCancelOrders()" style="background: #ef4444; color: #ffffff; border: 1px solid #f87171; padding: 8px 18px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 13px;">Confirm Order Revocation</button>
      </div>

      <div id="cancel-receipt" style="display: none; background: rgba(16, 185, 129, 0.1); border: 1px solid #10b981; border-radius: 6px; padding: 12px; margin-top: 12px;">
        <div style="color: #10b981; font-weight: bold; font-size: 13px;">✓ Orders Revoked &amp; Margin Restored</div>
        <div id="cancel-receipt-text" style="font-size: 12px; color: #cbd5e1; margin-top: 4px;"></div>
      </div>
    </div>
  </div>

  <!-- FREEZE RISK MODAL -->
  <div id="freeze-modal" class="modal-backdrop">
    <div class="modal-box" style="border: 1px solid #f59e0b;">
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 12px; margin-bottom: 16px;">
        <div style="display: flex; align-items: center; gap: 8px;">
          <span style="background: #f59e0b; color: #020617; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 4px;">GOVERNOR CLAMP</span>
          <strong style="color: #fbbf24; font-size: 15px;">FREEZE SUBORDINATE RISK DIAL</strong>
        </div>
        <button onclick="closeModals()" style="background: transparent; border: none; color: #94a3b8; font-size: 18px; cursor: pointer;">✕</button>
      </div>

      <div style="background: #0b132b; border: 1px solid #1e293b; border-radius: 6px; padding: 12px; margin-bottom: 14px;">
        <div style="font-size: 12px; color: #94a3b8; margin-bottom: 4px;">Target Subordinate</div>
        <div style="font-size: 15px; font-weight: bold; color: #f8fafc;" id="freeze-subordinate-name">--</div>
        <div style="font-family: monospace; font-size: 12px; color: #38bdf8; margin-top: 2px;" id="freeze-subordinate-scma">--</div>
      </div>

      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px;">
        <div style="background: #0f172a; padding: 10px; border-radius: 6px; border: 1px solid #334155;">
          <div style="font-size: 11px; color: #94a3b8;">Current Risk Dial</div>
          <div id="freeze-current-dial" style="font-size: 16px; font-weight: bold; color: #38bdf8; margin-top: 2px;">--</div>
        </div>
        <div style="background: #0f172a; padding: 10px; border-radius: 6px; border: 1px solid #f59e0b;">
          <div style="font-size: 11px; color: #f59e0b; font-weight: bold;">Clamped Risk Dial</div>
          <div style="font-size: 16px; font-weight: bold; color: #fbbf24; margin-top: 2px;">0.0% (Exclusion)</div>
        </div>
      </div>

      <div style="background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 6px; padding: 12px; margin-bottom: 16px;">
        <div style="font-size: 12px; color: #fde68a; line-height: 1.4;">
          Clamping risk to <b>0.0%</b> excludes this subordinate account from subsequent Quarter-Kelly dispatch batches until un-clamped by the House Leader.
        </div>
      </div>

      <div id="freeze-actions" style="display: flex; justify-content: flex-end; gap: 10px;">
        <button onclick="closeModals()" style="background: #334155; color: #cbd5e1; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 13px;">Dismiss</button>
        <button id="freeze-confirm-btn" onclick="executeFreezeRisk()" style="background: #f59e0b; color: #020617; border: 1px solid #fbbf24; padding: 8px 18px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 13px;">Apply Governor Clamp</button>
      </div>

      <div id="freeze-receipt" style="display: none; background: rgba(16, 185, 129, 0.1); border: 1px solid #10b981; border-radius: 6px; padding: 12px; margin-top: 12px;">
        <div style="color: #10b981; font-weight: bold; font-size: 13px;">✓ Subordinate Risk Clamped to 0.0%</div>
        <div id="freeze-receipt-text" style="font-size: 12px; color: #cbd5e1; margin-top: 4px;"></div>
      </div>
    </div>
  </div>

  <script>
    const currentHouseId = {house['house_id']};
    let activeTarget = null;

    function openCancelModal(name, scma, count, ordersStr) {{
      activeTarget = {{ name, scma }};
      document.getElementById('cancel-subordinate-name').textContent = name;
      document.getElementById('cancel-subordinate-scma').textContent = scma;
      document.getElementById('cancel-orders-detail').textContent = count > 0 ? `${{count}} resting (${{ordersStr}})` : '0 resting orders';
      document.getElementById('cancel-receipt').style.display = 'none';
      document.getElementById('cancel-actions').style.display = 'flex';
      document.getElementById('cancel-modal').style.display = 'flex';
    }}

    function openFreezeModal(name, scma, dial) {{
      activeTarget = {{ name, scma }};
      document.getElementById('freeze-subordinate-name').textContent = name;
      document.getElementById('freeze-subordinate-scma').textContent = scma;
      document.getElementById('freeze-current-dial').textContent = dial;
      document.getElementById('freeze-receipt').style.display = 'none';
      document.getElementById('freeze-actions').style.display = 'flex';
      document.getElementById('freeze-modal').style.display = 'flex';
    }}

    function closeModals() {{
      document.getElementById('cancel-modal').style.display = 'none';
      document.getElementById('freeze-modal').style.display = 'none';
      activeTarget = null;
    }}

    async function executeCancelOrders() {{
      if (!activeTarget) return;
      const btn = document.getElementById('cancel-confirm-btn');
      btn.textContent = 'Revoking...';
      btn.disabled = true;

      try {{
        const res = await fetch(`/api/v1/lineage/house/${{currentHouseId}}/subordinate/cancel-orders`, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ scma_id: activeTarget.scma }})
        }});
        const data = await res.json();
        if (res.ok) {{
          document.getElementById('cancel-receipt-text').innerHTML = `
            Cancelled <b>${{data.cancelled_orders.length}}</b> active orders for <b>${{activeTarget.scma}}</b>.<br>
            Ledger Audit Logged: <span style="color:#38bdf8; font-family:monospace;">${{data.timestamp}}</span>
          `;
          document.getElementById('cancel-receipt').style.display = 'block';
          document.getElementById('cancel-actions').style.display = 'none';
          setTimeout(() => window.location.reload(), 1200);
        }} else {{
          document.getElementById('cancel-receipt-text').innerHTML = `<span style="color:#ef4444;">Revocation Rejected: ${{data.detail || 'Invariant error'}}</span>`;
          document.getElementById('cancel-receipt').style.display = 'block';
        }}
      }} catch (err) {{
        console.error("Cancel orders failed:", err);
      }} finally {{
        btn.textContent = 'Confirm Order Revocation';
        btn.disabled = false;
      }}
    }}

    async function executeFreezeRisk() {{
      if (!activeTarget) return;
      const btn = document.getElementById('freeze-confirm-btn');
      btn.textContent = 'Applying Clamp...';
      btn.disabled = true;

      try {{
        const res = await fetch(`/api/v1/lineage/house/${{currentHouseId}}/subordinate/freeze-risk`, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ scma_id: activeTarget.scma }})
        }});
        const data = await res.json();
        if (res.ok) {{
          document.getElementById('freeze-receipt-text').innerHTML = `
            Status: <b style="color:#fbbf24;">${{data.member_status}}</b> | Dial: <b>0.0%</b><br>
            Governor Lock Logged: <span style="color:#38bdf8; font-family:monospace;">${{data.timestamp}}</span>
          `;
          document.getElementById('freeze-receipt').style.display = 'block';
          document.getElementById('freeze-actions').style.display = 'none';
          setTimeout(() => window.location.reload(), 1200);
        }} else {{
          document.getElementById('freeze-receipt-text').innerHTML = `<span style="color:#ef4444;">Freeze Rejected: ${{data.detail || 'Invariant error'}}</span>`;
          document.getElementById('freeze-receipt').style.display = 'block';
        }}
      }} catch (err) {{
        console.error("Freeze risk failed:", err);
      }} finally {{
        btn.textContent = 'Apply Governor Clamp';
        btn.disabled = false;
      }}
    }}
  </script>
</body>
</html>""")


@lineage_router.get("/api/v1/lineage/governance/proposals")
def get_governance_proposals():
    persisted = {p["proposal_id"]: p for p in _enclave_gov.list_petitions()}
    for legacy in _lineage_service.list_proposals():
        persisted.setdefault(legacy["proposal_id"], legacy)
    return {"proposals": list(persisted.values())}


@lineage_router.post("/api/v1/lineage/governance/petition")
def submit_petition(
    payload: Dict[str, Any],
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    actor_role, actor_id = _resolve_actor_context(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        authorization=authorization,
        payload=payload,
    )
    title = str(payload.get("title", "Untitled Petition"))
    description = str(payload.get("description", ""))
    proposal_category = str(payload.get("proposal_category", "CFCP_GRANT"))
    body_id = str(payload.get("body_id") or DEFAULT_BODY_ID)
    target_house_id = int(payload.get("target_house_id", 1))
    amount_cents = payload.get("amount_cents", 0)

    created = _enclave_gov.create_petition(
        title=title,
        description=description,
        body_id=body_id,
        proposal_category=proposal_category,
        target_house_id=target_house_id,
        amount_cents=amount_cents,
        actor_role=actor_role or "H2",
        actor_id=actor_id,
    )
    affirmative_house_ids = payload.get("affirmative_house_ids") or []
    latest = created
    for hid in affirmative_house_ids:
        if isinstance(hid, int) and 1 <= hid <= 12:
            latest = _enclave_gov.cast_vote(
                proposal_id=created["proposal_id"],
                vote_choice="AYE",
                actor_role="H2",
                actor_id=f"HOUSE-{hid:02d}:H2",
                house_id=hid,
            )
    return latest


@lineage_router.post("/api/v1/lineage/governance/adjudicate")
def adjudicate_governance_proposal(
    payload: Dict[str, Any],
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    proposal_id = payload.get("proposal_id")
    action = payload.get("action")
    caller_scma = payload.get("caller_scma", "SCMA-FOUNDER_-C8575D7E")
    actor_role, actor_id = _resolve_actor_context(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        authorization=authorization,
        payload=payload,
    )
    effective_role = actor_role or ("CHIEF_ADMINISTRATOR" if str(caller_scma).startswith("SCMA-FOUNDER") else "")
    if not is_chief_admin_role(effective_role):
        get_governance_audit_log().record(
            event_type="ROLE_BOUNDARY_DENIED",
            actor_id=str(caller_scma),
            actor_role=effective_role or "UNSPECIFIED",
            target_id=str(proposal_id or ""),
            action="ADJUDICATE_SOVEREIGN_PROPOSAL",
            outcome="DENIED_NON_SOVEREIGN",
            http_status=403,
            detail="Only Founder/Chief Administrator possesses Sovereign Veto and Execution authority.",
        )
        raise HTTPException(
            status_code=403,
            detail="Access Denied: Only Founder/Chief Administrator possesses Sovereign Veto and Execution authority.",
        )
    if not proposal_id or not action:
        raise HTTPException(status_code=400, detail="Missing proposal_id or action.")

    persisted = _enclave_gov.get_petition(str(proposal_id))
    if persisted is not None:
        result = _enclave_gov.adjudicate_petition(
            proposal_id=str(proposal_id),
            action=str(action),
            actor_role="CHIEF_ADMINISTRATOR",
            actor_id=str(caller_scma or actor_id),
            reason=str(payload.get("reason") or ""),
        )
        if str(proposal_id) in _lineage_service.PROPOSALS:
            _lineage_service.PROPOSALS[str(proposal_id)]["status"] = result["status"]
            _lineage_service.PROPOSALS[str(proposal_id)]["settled_by"] = result.get("settled_by")
        return result

    try:
        return _lineage_service.adjudicate_proposal(proposal_id=proposal_id, action=action, caller_scma=caller_scma)
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


# =============================================================================
# MILESTONE C6 — 3-STAGE GOVERNANCE ENGINE & CONFIGURABLE ENCLAVE REGISTRY API
# =============================================================================


@lineage_router.get("/api/v1/governance/houses")
def get_relational_houses():
    """Return all 12 Houses with exact 64-bit integer-cent rollups from SQLAlchemy."""
    return {"houses": _enclave_gov.list_houses_from_db()}


@lineage_router.get("/api/v1/governance/state")
def get_governance_dashboard_state():
    """Consolidated read model for /dashboard Tab 4."""
    return _enclave_gov.get_full_governance_state()


@lineage_router.get("/api/v1/governance/mode")
def get_governance_mode():
    """Return active 3-stage governance mode (defaults fail-closed EXECUTIVE_COMMAND)."""
    return _enclave_gov.get_governance_mode()


@lineage_router.post("/api/v1/governance/mode")
def update_governance_mode(
    payload: Dict[str, Any],
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Chief Administrator / Founder-only 3-stage governance mode switch."""
    actor_role, actor_id = _resolve_actor_context(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        authorization=authorization,
        payload=payload,
    )
    return _enclave_gov.set_governance_mode(
        governance_mode=str(payload.get("governance_mode") or ""),
        actor_role=actor_role,
        actor_id=actor_id,
        reason=str(payload.get("reason") or ""),
        is_shtf_snapback=bool(payload.get("is_shtf_snapback", False)),
    )


@lineage_router.post("/api/v1/governance/shtf-snapback")
def execute_shtf_snapback(
    payload: Optional[Dict[str, Any]] = None,
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Chief Administrator 1-click SHTF snap-back to Stage 1 EXECUTIVE_COMMAND."""
    body = payload or {}
    actor_role, actor_id = _resolve_actor_context(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        authorization=authorization,
        payload=body,
    )
    return _enclave_gov.set_governance_mode(
        governance_mode=MODE_EXECUTIVE_COMMAND,
        actor_role=actor_role,
        actor_id=actor_id,
        reason=str(body.get("reason") or "1-Click SHTF Snap-Back to Executive Command"),
        is_shtf_snapback=True,
    )


@lineage_router.get("/api/v1/governance/bodies")
def list_governance_bodies():
    return {"bodies": _enclave_gov.list_bodies()}


@lineage_router.post("/api/v1/governance/bodies", status_code=201)
def create_governance_body(
    payload: Dict[str, Any],
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    actor_role, actor_id = _resolve_actor_context(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        authorization=authorization,
        payload=payload,
    )
    return _enclave_gov.create_body(
        name=str(payload.get("name") or ""),
        description=str(payload.get("description") or ""),
        quorum_numerator=int(payload.get("quorum_numerator", 2)),
        quorum_denominator=int(payload.get("quorum_denominator", 3)),
        quorum_pct=payload.get("quorum_pct"),
        veto_threshold_count=int(payload.get("veto_threshold_count", 2)),
        veto_threshold_pct=payload.get("veto_threshold_pct"),
        can_exercise_stage3_veto=bool(payload.get("can_exercise_stage3_veto", True)),
        body_id=payload.get("body_id"),
        actor_role=actor_role,
        actor_id=actor_id,
    )


@lineage_router.patch("/api/v1/governance/bodies/{body_id}")
def update_governance_body(
    body_id: str,
    payload: Dict[str, Any],
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    actor_role, actor_id = _resolve_actor_context(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        authorization=authorization,
        payload=payload,
    )
    return _enclave_gov.update_body(
        body_id,
        name=payload.get("name"),
        description=payload.get("description"),
        quorum_numerator=payload.get("quorum_numerator"),
        quorum_denominator=payload.get("quorum_denominator"),
        quorum_pct=payload.get("quorum_pct"),
        veto_threshold_count=payload.get("veto_threshold_count"),
        veto_threshold_pct=payload.get("veto_threshold_pct"),
        can_exercise_stage3_veto=payload.get("can_exercise_stage3_veto"),
        active=payload.get("active"),
        actor_role=actor_role,
        actor_id=actor_id,
    )


@lineage_router.get("/api/v1/governance/bodies/{body_id}/seats")
def list_governance_body_seats(body_id: str):
    return {"body_id": body_id, "seats": _enclave_gov.list_voter_seats(body_id)}


@lineage_router.post("/api/v1/governance/bodies/{body_id}/seats", status_code=201)
def grant_governance_voter_seat(
    body_id: str,
    payload: Dict[str, Any],
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    actor_role, actor_id = _resolve_actor_context(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        authorization=authorization,
        payload=payload,
    )
    return _enclave_gov.grant_voter_seat(
        body_id,
        seat_type=str(payload.get("seat_type") or "NAMED_INDIVIDUAL"),
        display_name=str(payload.get("display_name") or ""),
        user_id=payload.get("user_id"),
        house_id=payload.get("house_id"),
        office_role=payload.get("office_role"),
        can_vote=bool(payload.get("can_vote", True)),
        can_veto=bool(payload.get("can_veto", False)),
        actor_role=actor_role,
        actor_id=actor_id,
    )


@lineage_router.post("/api/v1/governance/seats/{seat_id}/revoke")
def revoke_governance_voter_seat(
    seat_id: str,
    payload: Optional[Dict[str, Any]] = None,
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    body = payload or {}
    actor_role, actor_id = _resolve_actor_context(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        authorization=authorization,
        payload=body,
    )
    return _enclave_gov.revoke_voter_seat(
        seat_id,
        reason=str(body.get("reason") or ""),
        actor_role=actor_role,
        actor_id=actor_id,
    )


@lineage_router.get("/api/v1/governance/petitions")
def list_governance_petitions(body_id: Optional[str] = Query(None)):
    return {
        "governance_mode": _enclave_gov.get_governance_mode()["governance_mode"],
        "petitions": _enclave_gov.list_petitions(body_id=body_id),
    }


@lineage_router.post("/api/v1/governance/petitions", status_code=201)
def create_governance_petition(
    payload: Dict[str, Any],
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    actor_role, actor_id = _resolve_actor_context(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        authorization=authorization,
        payload=payload,
    )
    return _enclave_gov.create_petition(
        title=str(payload.get("title") or ""),
        description=str(payload.get("description") or ""),
        body_id=str(payload.get("body_id") or DEFAULT_BODY_ID),
        proposal_category=str(payload.get("proposal_category") or "CFCP_GRANT"),
        target_house_id=int(payload.get("target_house_id", 1)),
        amount_cents=payload.get("amount_cents", 0),
        actor_role=actor_role or "H2",
        actor_id=actor_id,
        proposal_id=payload.get("proposal_id"),
    )


@lineage_router.post("/api/v1/governance/petitions/{proposal_id}/vote")
def cast_governance_petition_vote(
    proposal_id: str,
    payload: Dict[str, Any],
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    actor_role, actor_id = _resolve_actor_context(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        authorization=authorization,
        payload=payload,
    )
    house_id = payload.get("house_id")
    if house_id is not None:
        _enforce_cross_house_boundary(
            int(house_id),
            x_house_id=x_house_id,
            actor_role=actor_role,
            action="CAST_GOVERNANCE_VOTE",
        )
    return _enclave_gov.cast_vote(
        proposal_id=proposal_id,
        vote_choice=str(payload.get("vote") or payload.get("vote_choice") or ""),
        actor_role=actor_role or "H2",
        actor_id=actor_id,
        house_id=int(house_id) if house_id is not None else None,
        user_id=payload.get("user_id"),
        seat_id=payload.get("seat_id"),
        rationale=str(payload.get("rationale") or ""),
    )


@lineage_router.post("/api/v1/governance/petitions/{proposal_id}/adjudicate")
def adjudicate_governance_petition(
    proposal_id: str,
    payload: Dict[str, Any],
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    actor_role, actor_id = _resolve_actor_context(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        authorization=authorization,
        payload=payload,
    )
    return _enclave_gov.adjudicate_petition(
        proposal_id=proposal_id,
        action=str(payload.get("action") or ""),
        actor_role=actor_role,
        actor_id=actor_id,
        reason=str(payload.get("reason") or ""),
    )


# =============================================================================
# MILESTONE PR #81 — MULTI-USER ROLE PROVISIONING & ANTI-TRIBALISM CUSTODY API
# =============================================================================

from app.domain.role_custody_service import get_role_custody_service


@lineage_router.get("/api/v1/governance/roles")
def list_governance_role_assignments(
    active_only: bool = Query(False),
    role_token: Optional[str] = Query(None),
    member_id: Optional[str] = Query(None),
):
    """List single-seat occupancy (CHIEF_ADMIN, T3, F3) and multi-seat assignments."""
    return get_role_custody_service().list_role_assignments(
        active_only=active_only,
        role_token=role_token,
        member_id=member_id,
    )


@lineage_router.post("/api/v1/governance/roles/assign", status_code=201)
def assign_governance_role(
    payload: Dict[str, Any],
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Assign a single-seat or multi-seat role with strict HTTP 409 single-seat uniqueness."""
    actor_role, actor_id = _resolve_actor_context(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        authorization=authorization,
        payload=payload,
    )
    return get_role_custody_service().assign_role(
        member_id=str(payload.get("member_id") or ""),
        role_token=str(payload.get("role_token") or ""),
        house_id=payload.get("house_id"),
        atomic_succession=bool(payload.get("atomic_succession", False)),
        reason=str(payload.get("reason") or ""),
        actor_role=actor_role,
        actor_id=actor_id,
    )


@lineage_router.post("/api/v1/governance/roles/revoke")
def revoke_governance_role(
    payload: Dict[str, Any],
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Revoke an active role and atomically reassign displaced custodial charges."""
    actor_role, actor_id = _resolve_actor_context(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        authorization=authorization,
        payload=payload,
    )
    return get_role_custody_service().revoke_role(
        member_id=str(payload.get("member_id") or ""),
        role_token=str(payload.get("role_token") or ""),
        reason=str(payload.get("reason") or ""),
        actor_role=actor_role,
        actor_id=actor_id,
    )


@lineage_router.post("/api/v1/governance/roles/promote")
def promote_governance_member(
    payload: Dict[str, Any],
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Atomically promote a member's tier while preserving single-seat uniqueness and zero orphans."""
    actor_role, actor_id = _resolve_actor_context(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        authorization=authorization,
        payload=payload,
    )
    return get_role_custody_service().promote_member(
        member_id=str(payload.get("member_id") or ""),
        to_role=str(payload.get("to_role") or payload.get("role_token") or ""),
        house_id=payload.get("house_id"),
        from_role=payload.get("from_role"),
        atomic_succession=bool(payload.get("atomic_succession", False)),
        reason=str(payload.get("reason") or ""),
        actor_role=actor_role,
        actor_id=actor_id,
    )


@lineage_router.post("/api/v1/governance/roles/demote")
def demote_governance_member(
    payload: Dict[str, Any],
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Atomically demote a member and reassign all displaced custodial charges (0 orphans, 0 lingering access)."""
    actor_role, actor_id = _resolve_actor_context(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        authorization=authorization,
        payload=payload,
    )
    return get_role_custody_service().demote_member(
        member_id=str(payload.get("member_id") or ""),
        to_role=str(payload.get("to_role") or payload.get("role_token") or "MEMBER_USER"),
        house_id=payload.get("house_id"),
        from_role=payload.get("from_role"),
        reason=str(payload.get("reason") or ""),
        actor_role=actor_role,
        actor_id=actor_id,
    )


@lineage_router.get("/api/v1/governance/custody-mode")
def get_custody_assignment_mode():
    """Return active enclave custody mode (INTRA_HOUSE default vs CROSS_HOUSE_ANTI_TRIBAL)."""
    return get_role_custody_service().get_policy_controls()


@lineage_router.post("/api/v1/governance/custody-mode")
def set_custody_assignment_mode(
    payload: Dict[str, Any],
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Chief Administrator toggle between INTRA_HOUSE and CROSS_HOUSE_ANTI_TRIBAL custody pairing."""
    actor_role, actor_id = _resolve_actor_context(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        authorization=authorization,
        payload=payload,
    )
    return get_role_custody_service().set_custody_assignment_mode(
        custody_assignment_mode=str(payload.get("custody_assignment_mode") or ""),
        reason=str(payload.get("reason") or ""),
        actor_role=actor_role,
        actor_id=actor_id,
    )


@lineage_router.get("/api/v1/governance/custody/assignments")
def list_custodial_assignments(
    custodian_member_id: Optional[str] = Query(None),
    charge_member_id: Optional[str] = Query(None),
    active_only: bool = Query(True),
):
    """List custodial officer-to-charge assignments and active anti-tribalism policy."""
    svc = get_role_custody_service()
    return {
        "policy": svc.get_policy_controls(),
        "assignments": svc.list_custodial_assignments(
            custodian_member_id=custodian_member_id,
            charge_member_id=charge_member_id,
            active_only=active_only,
        ),
    }


@lineage_router.post("/api/v1/governance/custody/assign", status_code=201)
def assign_custodial_mentor(
    payload: Dict[str, Any],
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Assign or auto-pair a custodian to a charge honoring active custody_assignment_mode."""
    actor_role, actor_id = _resolve_actor_context(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        authorization=authorization,
        payload=payload,
    )
    return get_role_custody_service().assign_custodian(
        charge_member_id=str(payload.get("charge_member_id") or ""),
        charge_scma_id=str(payload.get("charge_scma_id") or ""),
        charge_house_id=int(payload.get("charge_house_id") or 1),
        custodian_member_id=payload.get("custodian_member_id"),
        custodian_role=payload.get("custodian_role"),
        reason=str(payload.get("reason") or ""),
        actor_role=actor_role,
        actor_id=actor_id,
    )


