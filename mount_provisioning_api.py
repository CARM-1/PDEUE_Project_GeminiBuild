import sys
import pathlib

BACKEND_DIR = pathlib.Path(__file__).resolve().parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Update workspace_router.py to include live provisioning, promotion, and roster endpoints
target_file = BACKEND_DIR / "app" / "api" / "v1" / "workspace_router.py"
content = target_file.read_text(encoding="utf-8")

provisioning_endpoints = """
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

@router.get("/operator/roster")
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

@router.post("/operator/provision-identity")
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

@router.post("/operator/batch-provision")
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

@router.post("/operator/transition-role")
def api_transition_role(req: RoleTransitionRequest):
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        res = provisioning_engine.transition_user_role(
            db=db,
            user_id=req.user_id,
            new_role=req.new_role,
            justification=req.justification
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()
"""

if "/operator/roster" not in content:
    content += "\n" + provisioning_endpoints
    target_file.write_text(content, encoding="utf-8")
    print(f"Mounted Provisioning & Transition endpoints to {target_file}")
else:
    print("Endpoints already present in workspace_router.py")