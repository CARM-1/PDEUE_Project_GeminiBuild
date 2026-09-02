from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from app.domain.operator import OperatorControlEngine
from app.core.security import verify_jwt_token

router = APIRouter(prefix="/operator", tags=["operator"])
operator_engine = OperatorControlEngine()

@router.post("/paper/start")
def start_paper_session(payload: Dict[str, Any], token_data: Dict[str, Any] = Depends(verify_jwt_token)):
    tenant_id = token_data.get("tenant_id", "default_tenant")
    initial_capital = payload.get("initial_capital", 100000.0)
    session = operator_engine.start_paper_session(tenant_id, initial_capital)
    return {"status": "success", "session": session}

@router.get("/audit/logs")
def get_audit_logs(token_data: Dict[str, Any] = Depends(verify_jwt_token)):
    tenant_id = token_data.get("tenant_id")
    logs = [entry for entry in operator_engine.audit_log if entry["tenant_id"] == tenant_id]
    return {"tenant_id": tenant_id, "audit_count": len(logs), "logs": logs}
