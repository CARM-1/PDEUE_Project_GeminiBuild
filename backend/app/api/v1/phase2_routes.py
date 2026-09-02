from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Dict, Any, Optional
from app.domain.dynamic_pipeline import DynamicUnderwritingEngine
from app.core.security import decode_access_token

router = APIRouter(prefix="/api/v1/phase2", tags=["phase2"])
engine = DynamicUnderwritingEngine()

def get_current_tenant(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ")[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload

@router.post("/evaluate")
def evaluate_event_and_market(payload: Dict[str, Any], tenant: Dict[str, Any] = Depends(get_current_tenant)):
    result = engine.process_event_and_evaluate(
        station_id=payload.get("station_id", "KORD"),
        temp_c=payload.get("temp_c", 20.0),
        timestamp=payload.get("timestamp", "2026-09-02T18:00:00Z"),
        ticker=payload.get("ticker", "KXCHICAGO-26SEP02"),
        yes_bid=payload.get("yes_bid", 0.40),
        yes_ask=payload.get("yes_ask", 0.45)
    )
    result["tenant_context"] = {"user_id": tenant.get("sub"), "account_id": tenant.get("account_id")}
    return result
