from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Dict, Any, List
import pathlib
from app.domain.portal_service import PortalService

portal_router = APIRouter(tags=['Portals'])
global_portal_service = PortalService()

class RiskUpdateRequest(BaseModel):
    requested_risk_pct: float

class DistributionRequest(BaseModel):
    amount_cents: int

@portal_router.get('/member', response_class=HTMLResponse)
def get_member_portal_page():
    html_path = pathlib.Path(__file__).parent.parent.parent / 'static' / 'member.html'
    if not html_path.exists():
        return HTMLResponse('<h3>Member Portal Initializing...</h3>')
    return HTMLResponse(content=html_path.read_text(encoding='utf-8'))

@portal_router.get('/advisor', response_class=HTMLResponse)
def get_advisor_portal_page():
    html_path = pathlib.Path(__file__).parent.parent.parent / 'static' / 'advisor.html'
    if not html_path.exists():
        return HTMLResponse('<h3>Advisor Portal Initializing...</h3>')
    return HTMLResponse(content=html_path.read_text(encoding='utf-8'))

@portal_router.get('/api/v1/portal/member/{scma_id}')
def get_member_telemetry(scma_id: str):
    res = global_portal_service.get_member_view(scma_id)
    if res.get('status') == 'NOT_FOUND':
        raise HTTPException(status_code=404, detail='SCMA account not found')
    return res

@portal_router.post('/api/v1/portal/member/{scma_id}/risk-dial')
def update_risk_dial(scma_id: str, req: RiskUpdateRequest):
    res = global_portal_service.update_member_risk_dial(scma_id, req.requested_risk_pct)
    if res.get('status') == 'REJECTED':
        raise HTTPException(status_code=400, detail=res.get('reason'))
    if res.get('status') == 'NOT_FOUND':
        raise HTTPException(status_code=404, detail='SCMA account not found')
    return res

@portal_router.post('/api/v1/portal/member/{scma_id}/distribution')
def request_distribution(scma_id: str, req: DistributionRequest):
    res = global_portal_service.queue_distribution_request(scma_id, req.amount_cents)
    if res.get('status') == 'REJECTED':
        raise HTTPException(status_code=400, detail=res.get('reason'))
    return res

@portal_router.get('/api/v1/portal/advisor/household/{household_id}')
def get_advisor_household(household_id: str, members: List[str] = Query(...)):
    return global_portal_service.get_advisor_household_view(household_id, members)
