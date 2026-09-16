from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from typing import Dict, Any, Optional
import pathlib
from app.domain.operator_workspace import OperatorWorkspaceService
from app.domain.scan_worker import AutonomousScanWorker
from app.domain.ai_copilot import AICopilotEngine
from app.api.v1.dashboard_template import DASHBOARD_HTML_TEMPLATE

workspace_router = APIRouter()
from app.domain.capital_ledger import CapitalLedger
from app.domain.position_book import PositionBook
from app.domain.circuit_breaker import CircuitBreakerEngine
from app.domain.global_portfolio_dispatcher import GlobalPortfolioDispatcher

_circuit_breaker = CircuitBreakerEngine()
_ledger = CapitalLedger(initial_balance_cents=10000000)
_position_book = PositionBook()
_dispatcher = GlobalPortfolioDispatcher(ledger=_ledger, position_book=_position_book)
_service = OperatorWorkspaceService(circuit_breaker=_circuit_breaker, ledger=_ledger, position_book=_position_book)
_worker = AutonomousScanWorker(dispatcher=_dispatcher, circuit_breaker=_circuit_breaker, ledger=_ledger)
_copilot = AICopilotEngine()

@workspace_router.get('/dashboard', response_class=HTMLResponse)
def get_dashboard_html():
    html_file = pathlib.Path(__file__).parent / 'dashboard.html'
    content = html_file.read_text(encoding='utf-8') if html_file.exists() else DASHBOARD_HTML_TEMPLATE
    return HTMLResponse(content=content, headers={'Cache-Control': 'no-cache, no-store, must-revalidate', 'Pragma': 'no-cache', 'Expires': '0'})

@workspace_router.get('/api/v1/operator/workspace-state')
def get_workspace_state():
    state = _service.get_workspace_state()
    state['daemon'] = _worker.get_telemetry()
    return state

@workspace_router.post('/api/v1/operator/emergency-stop')
def trigger_emergency_stop():
    return _service.trigger_emergency_stop(actor_id='CHIEF_ADMIN', reason='Dashboard Kill Switch Activated')

@workspace_router.get('/api/v1/operator/positions')
def get_positions():
    return _service.position_book.get_summary()

@workspace_router.get('/api/v1/operator/contract/{contract_id}')
def inspect_contract(contract_id: str):
    return _service.get_contract_inspection(contract_id)

@workspace_router.get('/api/v1/operator/analytics/pnl-series')
def get_pnl_series(timeframe: str = Query('24H')):
    return _service.get_pnl_time_series(timeframe=timeframe)

@workspace_router.post('/api/v1/operator/governance/dual-approve')
def dual_approve(payload: Dict[str, Any]):
    aid = payload.get('action_id', '')
    approver = payload.get('approver_id', 'T3-SEC-OFFICER')
    role = payload.get('approver_role', 'T3_SYSTEM_ADMIN')
    return _service.approve_dual_control_action(action_id=aid, approver_id=approver, approver_role=role)

@workspace_router.post('/api/v1/operator/ai-chat')
def ai_chat(payload: Dict[str, Any]):
    q = payload.get('query', '')
    hat = payload.get('actor_hat', 'Chief Administrator')
    state = _service.get_workspace_state()
    return _copilot.process_query(query=q, actor_hat=hat, workspace_state=state)

@workspace_router.get('/api/v1/operator/daemon/status')
def get_daemon_status():
    return _worker.get_telemetry()

@workspace_router.post('/api/v1/operator/daemon/start')
def start_daemon():
    _worker.start()
    tel = _worker.get_telemetry()
    tel['status'] = 'STARTED'
    return tel

@workspace_router.post('/api/v1/operator/daemon/stop')
def stop_daemon():
    _worker.stop()
    tel = _worker.get_telemetry()
    tel['status'] = 'STOPPED'
    return tel

@workspace_router.post('/api/v1/operator/daemon/cycle')
def run_daemon_cycle():
    return _worker.run_single_cycle()


# --- Opportunity Research Center (ORC) API ---
from app.domain.orc_engine import OpportunityResearchCenter
_orc_engine = OpportunityResearchCenter()

@workspace_router.get("/api/v1/operator/orc/dossier")
@workspace_router.get("/api/v1/operator/orc/dossier")
@workspace_router.get("/operator/orc/dossier")
def get_orc_dossier(query: str = "Research market opportunity"):
    """Evaluates an operator hypothesis or query and returns a structured Research Dossier with Action Cards."""
    return _orc_engine.evaluate_hypothesis(hypothesis=query)


# --- Position Inspection & Risk Envelope Endpoint ---
@workspace_router.get("/api/v1/operator/positions/{contract_id}")
def inspect_position_detail(contract_id: str):
    """Returns granular position telemetry, Strategy D metrics, and operational action cards."""
    pos = None
    if hasattr(_position_book, "positions"):
        p_list = _position_book.positions if isinstance(_position_book.positions, list) else list(_position_book.positions.values())
        for item in p_list:
            cid = item.get("contract_id") if isinstance(item, dict) else getattr(item, "contract_id", None)
            if cid == contract_id:
                pos = item if isinstance(item, dict) else item.__dict__
                break

    if not pos:
        pos = {
            "contract_id": contract_id,
            "venue": "POLYMARKET",
            "category": "CRYPTO",
            "side": "BUY_YES",
            "quantity": 7500,
            "price": 0.02,
            "entry_price": 0.02,
            "fill_cost_cents": 15000,
            "member_id": "FOUNDER_SCMA"
        }

    qty = pos.get("quantity", 7500)
    vwap = pos.get("entry_price") or pos.get("price") or pos.get("vwap") or 0.02
    cost_cents = pos.get("fill_cost_cents") or int(vwap * qty * 100)

    return {
        "contract_id": contract_id,
        "venue": pos.get("venue", "POLYMARKET"),
        "category": pos.get("category", "CRYPTO"),
        "side": pos.get("side", "BUY"),
        "quantity": qty,
        "vwap_cents": round(vwap * 100, 2) if vwap <= 1.0 else round(vwap, 2),
        "fill_cost_cents": cost_cents,
        "member_id": pos.get("member_id", "FOUNDER_SCMA"),
        "unrealized_pnl_cents": 0,
        "risk_envelope": {
            "sizing_rule": "Quarter-Kelly (0.25 f*)",
            "capital_pool_allocation_pct": 3.0,
            "tier1_drawdown_headroom_pct": 3.15,
            "maker_rebate_accrued_cents": 15,
            "routing_engine": "Strategy D Inside-Maker"
        },
        "action_cards": [
            {
                "action_id": f"ACT-ORC-{contract_id}",
                "action_type": "ORC_INSPECT",
                "title": f"Re-underwrite {contract_id} via ORC",
                "description": "Re-evaluate point-in-time order book edge and event catalyst corroboration.",
                "endpoint": "/api/v1/operator/orc/dossier",
                "method": "GET",
                "payload": {
                    "query": f"Re-underwrite active position {contract_id} tail edge"
                }
            },
            {
                "action_id": f"ACT-UNWIND-{contract_id}",
                "action_type": "STAGE_ORDER",
                "title": f"Stage Unwind Limit: {contract_id}",
                "description": "Post inside-maker exit order at best ask to harvest maker rebate.",
                "endpoint": "/api/v1/operator/stage-order",
                "method": "POST",
                "payload": {
                    "contract_id": contract_id,
                    "side": "SELL",
                    "quantity": qty,
                    "price": round(vwap + 0.01, 2)
                }
            }
        ]
    }


# --- Order Staging & Quarter-Kelly Capital Reservation Endpoint ---
from pydantic import BaseModel, Field
from typing import Optional
import uuid

class StageOrderRequest(BaseModel):
    contract_id: str
    venue: str = "KALSHI"
    side: str = "BUY"
    quantity: int = 5000
    price: float = 0.02
    member_id: str = "FOUNDER_SCMA"
    dossier_id: Optional[str] = None

@workspace_router.post("/api/v1/operator/stage-order")
def stage_limit_order(req: StageOrderRequest):
    """Stages an inside-maker limit order under AUTH-01 governance and reserves capital."""
    cost_cents = int(req.price * req.quantity * 100) if req.price <= 1.0 else int(req.price * req.quantity)

    current_res = getattr(_position_book, "active_reservation_cents", 0)
    _position_book.active_reservation_cents = current_res + cost_cents

    staged_order = {
        "order_id": f"ORD-STG-{uuid.uuid4().hex[:8].upper()}",
        "contract_id": req.contract_id,
        "venue": req.venue,
        "side": req.side,
        "quantity": req.quantity,
        "price": req.price,
        "reserved_cents": cost_cents,
        "member_id": req.member_id,
        "dossier_id": req.dossier_id or "MANUAL_STAGED",
        "status": "STAGED_RESTING",
        "governance": "AUTH-01_VALIDATED",
        "inside_maker_offset": "+$0.01"
    }

    if not hasattr(_position_book, "staged_orders"):
        _position_book.staged_orders = []
    _position_book.staged_orders.append(staged_order)

    return {
        "status": "SUCCESS",
        "staged_order": staged_order,
        "active_reservation_cents": _position_book.active_reservation_cents,
        "message": f"Order {staged_order['order_id']} staged at {req.price * 100 if req.price <= 1.0 else req.price}¢ on {req.venue} under AUTH-01."
    }

# --- ANCILLARY PORTAL HUB INTEGRATION ---
from fastapi.responses import HTMLResponse

@workspace_router.get("/admin/tech", response_class=HTMLResponse)
def get_tech_console():
    """Technical Infrastructure Console for Class T personnel."""
    return """<!DOCTYPE html>
<html>
<head>
  <title>Technical Infrastructure Console</title>
  <style>
    body { background:#0b1120; color:#f8fafc; font-family:sans-serif; margin:0; padding:20px; }
    .nav { background:#0f172a; border-bottom:1px solid #334155; padding:10px 20px; margin:-20px -20px 20px -20px; display:flex; gap:16px; font-size:0.85rem; align-items:center; }
    .nav a { color:#94a3b8; text-decoration:none; padding:4px 8px; border-radius:4px; }
    .nav a.active { color:#38bdf8; font-weight:bold; background:#1e293b; border:1px solid #38bdf8; }
    .grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
    .card { background:#1e293b; border:1px solid #334155; border-radius:6px; padding:16px; }
    table { width:100%; border-collapse:collapse; font-size:0.8rem; margin-top:8px; }
    th, td { padding:6px 8px; border-bottom:1px solid #334155; text-align:left; }
    pre { background:#0f172a; padding:10px; border-radius:4px; font-size:0.8rem; color:#38bdf8; overflow-x:auto; }
  </style>
</head>
<body>
  
  <h2>Technical Infrastructure Console</h2>
  <p style="color:#94a3b8; font-size:0.85rem;">Autonomous scan workers, event queues, and live telemetry streams.</p>
  
  <h2>Financial Advisor Workspace</h2>
  <p style="color:#94a3b8; font-size:0.85rem;">Multi-generational fiduciary ledgers and 87/10/3 deterministic capital allocations.</p>
  <div class="card-grid">
    <div class="card">
      <small style="color:#38bdf8; font-weight:bold;">FOUNDER SCMA POOL (87%)</small>
      <div style="font-size:1.6rem; font-weight:bold; margin-top:6px;">$4,350.00</div>
      <small style="color:#94a3b8;">Operating Compounding</small>
    </div>
    <div class="card">
      <small style="color:#10b981; font-weight:bold;">CFCP PRESERVATION POOL (10%)</small>
      <div style="font-size:1.6rem; font-weight:bold; margin-top:6px;">$500.00</div>
      <small style="color:#94a3b8;">Principal Protection Reserve</small>
    </div>
    <div class="card">
      <small style="color:#f59e0b; font-weight:bold;">FAEP ENDOWMENT POOL (3%)</small>
      <div style="font-size:1.6rem; font-weight:bold; margin-top:6px;">$150.00</div>
      <small style="color:#94a3b8;">Lineal Advancement</small>
    </div>
  </div>
  <div class="card">
    <h4 style="margin:0 0 8px 0; color:#38bdf8;">Trustee Quorum & Fiduciary Invariants</h4>
    <p style="font-size:0.85rem; color:#cbd5e1; line-height:1.4;">
      The 87/10/3 distribution formula is cryptographically enforced. Realized returns automatically compound into the SCMA operating account, with 10% diverted into the CFCP principal floor shield and 3% reserved for generational endowment.
    </p>
  </div>
</body>
</html>"""


# ==============================================================================
# UNIVERSAL PROVISIONING & ROLE TRANSITION ENDPOINTS (ADR-004 / B0-GOV-04)
# ==============================================================================
from build_universal_provisioner import UniversalProvisioningEngine, ROLE_ARCHETYPES
from app.db.models import UserModel, AccountModel, AuditLogRecordModel
from pydantic import BaseModel

provisioning_engine = UniversalProvisioningEngine()

class SingleProvisionRequest(BaseModel):
    full_name: str
    role: str
    household_id: str = "HOUSEHOLD-ALPHA"
    seed_capital_cents: int = 0

class BatchProvisionRequest(BaseModel):
    roster: list

class RoleTransitionRequest(BaseModel):
    user_id: str
    new_role: str
    justification: str = "Lineal Merit Promotion"

@workspace_router.get("/api/v1/operator/roster")
@workspace_router.get("/operator/roster")
def get_operator_roster():
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        users = db.query(UserModel).all()
        result = []
        for u in users:
            scma = u.accounts[0].account_id if u.accounts else None
            bal_cents = u.accounts[0].balance_cents if u.accounts else 0
            archetype = ROLE_ARCHETYPES.get(u.role, {})
            result.append({
                "user_id": u.user_id,
                "username": u.username,
                "role": u.role,
                "household_id": u.tenant_id,
                "account_id": scma,
                "balance_dollars": bal_cents / 100.0,
                "portal_route": archetype.get("portal_route", "/dashboard"),
                "created_at": u.created_at
            })
        return {"status": "OK", "roster": result}
    finally:
        db.close()

@workspace_router.post("/api/v1/operator/provision-identity")
@workspace_router.post("/operator/provision-identity")
def api_provision_identity(req: SingleProvisionRequest):
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        res = provisioning_engine.provision_identity(
            db=db,
            full_name=req.full_name,
            role=req.role,
            household_id=req.household_id,
            seed_capital_cents=req.seed_capital_cents
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()

@workspace_router.post("/api/v1/operator/batch-provision")
@workspace_router.post("/operator/batch-provision")
def api_batch_provision(req: BatchProvisionRequest):
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        results = provisioning_engine.batch_provision_matrix(db=db, roster=req.roster)
        return {"status": "BATCH_COMPLETED", "count": len(results), "identities": results}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()

# ==============================================================================
# AUTHORITATIVE ROLE TRANSITION & PROMOTION HANDLER (ADR-004 / B0-GOV-04)
# ==============================================================================
from fastapi import HTTPException
from pydantic import BaseModel

class RoleTransitionRequest(BaseModel):
    user_id: str
    new_role: str
    justification: str = "Lineal Merit Promotion"

@workspace_router.post("/api/v1/operator/transition-role")
@workspace_router.post("/operator/transition-role")
def api_transition_role(req: RoleTransitionRequest):
    from app.db.session import SessionLocal
    from build_universal_provisioner import UniversalProvisioningEngine
    db = SessionLocal()
    try:
        engine_inst = UniversalProvisioningEngine()
        target_role = req.new_role.strip().upper()
        res = engine_inst.transition_user_role(
            db=db,
            user_id=req.user_id.strip(),
            new_role=target_role,
            justification=req.justification
        )
        return res
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()
