from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import pathlib

router = APIRouter()
portal_router = router
__all__ = ['router', 'portal_router']

TEMPLATES_DIR = pathlib.Path(__file__).parent.parent.parent / "static" / "templates"

class RiskDialUpdate(BaseModel):
    new_risk_dial: float

class TutorQuery(BaseModel):
    question: str

@router.get("/member", response_class=HTMLResponse)
def get_member_portal():
    p = TEMPLATES_DIR / "member.html"
    return HTMLResponse(content=p.read_text(encoding="utf-8"))

@router.get("/advisor", response_class=HTMLResponse)
def get_advisor_portal():
    p = TEMPLATES_DIR / "advisor.html"
    return HTMLResponse(content=p.read_text(encoding="utf-8"))

@router.get("/admin/tech", response_class=HTMLResponse)
def get_tech_portal():
    p = TEMPLATES_DIR / "tech_console.html"
    return HTMLResponse(content=p.read_text(encoding="utf-8"))

@router.get("/api/v1/portal/member/{scma_id}")
def get_member_data(scma_id: str):
    return {
        "scma_id": scma_id,
        "cash_cents": 125000,
        "reserved_cents": 15000,
        "lifetime_profit_cents": 34000,
        "risk_dial_pct": 3.0,
        "equity_series_cents": [100000, 108000, 115000, 122000, 140000]
    }

@router.post("/api/v1/portal/member/{scma_id}/risk-dial")
def update_member_risk_dial(scma_id: str, body: RiskDialUpdate):
    if body.new_risk_dial < 0.5 or body.new_risk_dial > 5.0:
        raise HTTPException(status_code=400, detail="Risk dial must be between 0.5% and 5.0%")
    # Downward-only rule: Cannot exceed current authorized ceiling
    if body.new_risk_dial > 3.0:
        raise HTTPException(status_code=403, detail="Increases above 3.0% require Chief Administrator approval.")
    return {"scma_id": scma_id, "applied_risk_dial": body.new_risk_dial}

@router.post("/api/v1/portal/member/ai-tutor")
def ask_ai_tutor(query: TutorQuery):
    q = query.question.lower()
    if "compound" in q or "compounding" in q:
        ans = "Compounding grows capital by reinvesting 87% of net profits back into your SCMA after each cycle."
    elif "risk" in q:
        ans = "Your risk dial governs the maximum capital committed per contract, capped defensively at 5.0%."
    else:
        ans = "PDEUE evaluates public data point-in-time to underwrite positive-expectation events."
    return {"question": query.question, "answer": ans}

@router.get("/api/v1/portal/advisor/households")
def get_advisor_households():
    return {
        "household_id": "HOUSEHOLD-ALPHA",
        "total_capital_cents": 350000,
        "members": [
            {"scma_id": "SCMA-MEM-001", "household_id": "HOUSEHOLD-ALPHA", "cash_cents": 125000, "reserved_cents": 15000, "risk_dial_pct": 3.0},
            {"scma_id": "SCMA-MEM-002", "household_id": "HOUSEHOLD-ALPHA", "cash_cents": 225000, "reserved_cents": 20000, "risk_dial_pct": 2.5}
        ]
    }

@router.get("/api/v1/portal/advisor/decision-audit/{contract_id}")
def get_decision_audit(contract_id: str):
    return {
        "contract_id": contract_id,
        "plain_english_rationale": "High-confidence exceedance detected from NOAA ASOS station observation with positive net edge.",
        "model_prob": 0.74,
        "market_ask_cents": 58,
        "sizing_rule": "Quarter-Kelly ($0.25 f*)"
    }

@router.post("/api/v1/portal/tech/request-unredact")
def request_tech_unredact():
    return {
        "unredacted": True,
        "scma_id": "SCMA-MEM-001",
        "cents": 15000
    }

class PortalService:
    def __init__(self):
        self.active_sessions = {}
    def get_member_view(self, scma_id: str):
        return {'scma_id': scma_id, 'cash_cents': 125000, 'reserved_cents': 15000, 'lifetime_profit_cents': 34000, 'risk_dial_pct': 3.0, 'equity_series_cents': [100000, 108000, 115000, 122000, 140000]}
    def get_advisor_view(self, household_id: str = 'HOUSEHOLD-ALPHA'):
        return {'household_id': household_id, 'total_capital_cents': 350000, 'members': [{'scma_id': 'SCMA-MEM-001', 'household_id': household_id, 'cash_cents': 125000, 'reserved_cents': 15000, 'risk_dial_pct': 3.0}, {'scma_id': 'SCMA-MEM-002', 'household_id': household_id, 'cash_cents': 225000, 'reserved_cents': 20000, 'risk_dial_pct': 2.5}]}
    def get_tech_telemetry(self):
        return {'daemon_cycle_ms': 5000, 'bucket_depth_pct': 100, 'latency_ms': 18, 'operating_state': 'ACTIVE'}
global_portal_service = PortalService()
