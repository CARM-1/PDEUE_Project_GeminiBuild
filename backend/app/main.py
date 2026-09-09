import pathlib
try:
    from app.api.v1.portal_router import portal_router
except ImportError:
    from backend.app.api.v1.portal_router import portal_router
from fastapi.staticfiles import StaticFiles
from app.api.v1.health_router import health_router
from app.api.v1.accounting_router import router as accounting_router
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
from app.domain.paper_session import PaperSessionManager
from app.domain.decision_packet import DecisionPacketBuilder

app = FastAPI(title="PDEUE Operator Workspace API", version="1.0.0")
paper_manager = PaperSessionManager()
packet_builder = DecisionPacketBuilder()

class CreateSessionRequest(BaseModel):
    initial_capital_cents: int

class PaperTradeRequest(BaseModel):
    session_id: str
    contract_id: str
    price: float
    quantity: int

@app.get("/health")
def health_check():
    return {"status": "HEALTHY", "service": "PDEUE Operator API"}

@app.post("/api/v1/paper/sessions")
def create_paper_session(req: CreateSessionRequest):
    return paper_manager.create_session(req.initial_capital_cents)

@app.post("/api/v1/paper/trade")
def execute_trade(req: PaperTradeRequest):
    try:
        return paper_manager.execute_paper_trade(req.session_id, req.contract_id, req.price, req.quantity)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

try:
    from app.api.v1.operator_router import router as operator_router
    app.include_router(operator_router, prefix="/api/v1")
except Exception:
    pass

from app.api.v1.workspace_router import workspace_router
app.include_router(workspace_router)

app.include_router(accounting_router)


app.include_router(health_router)


# Mount portal router and static templates
app.include_router(portal_router)
static_path = pathlib.Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=str(static_path)), name='static')
