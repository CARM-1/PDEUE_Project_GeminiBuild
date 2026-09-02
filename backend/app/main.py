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
