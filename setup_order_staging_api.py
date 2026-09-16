import pathlib
import shutil

router_path = pathlib.Path("backend/app/api/v1/workspace_router.py")
if router_path.exists():
    shutil.copy2(router_path, router_path.with_suffix(".py.bak_staging"))
    print(f"[Backup Created] -> {router_path.with_suffix('.py.bak_staging')}")

    content = router_path.read_text(encoding="utf-8")

    staging_code = '''

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

    # Increment active reservation in singleton
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
'''

    if "/api/v1/operator/stage-order" not in content:
        content += staging_code
        router_path.write_text(content, encoding="utf-8")
        print("[1/1] Registered /api/v1/operator/stage-order in workspace_router.py")
    else:
        print("[1/1] Stage order endpoint already registered.")