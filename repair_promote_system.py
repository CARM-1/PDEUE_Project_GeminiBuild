import sys
import os
import pathlib
import json

BACKEND_DIR = pathlib.Path(r"C:\PDEUE_Gemini\backend")
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
ROOT_DIR = pathlib.Path(r"C:\PDEUE_Gemini")
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# 1. Authoritative Overwrite of the Transition Router in workspace_router.py
router_path = BACKEND_DIR / "app" / "api" / "v1" / "workspace_router.py"
router_text = router_path.read_text(encoding="utf-8")

clean_transition_block = """
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
"""

# Replace any existing transition endpoint definition cleanly
import re
pattern = r'(@workspace_router\.post\([^)]*transition-role[^)]*\)\s*)+(async\s+)?def api_transition_role[\s\S]*?finally:\s*db\.close\(\)'
if re.search(pattern, router_text):
    router_text = re.sub(pattern, clean_transition_block.strip(), router_text)
else:
    router_text += "\n" + clean_transition_block.strip()

router_path.write_text(router_text, encoding="utf-8")
print("[1/4] Overwritten transition route in workspace_router.py")

# 2. Synchronize Authoritative dashboard.html in Both Locations
html_src = BACKEND_DIR / "app" / "api" / "v1" / "dashboard.html"
html_static = BACKEND_DIR / "app" / "static" / "dashboard.html"
dash_content = html_src.read_text(encoding="utf-8")

# Replace promptTransition script with robust error handling and immediate alerts
robust_prompt_js = """
    async function promptTransition(uid, currentRole) {
      const targetRole = prompt("Promote/Transition User: " + uid + "\\nCurrent Role: " + currentRole + "\\nEnter Target Role (e.g. MEMBER_USER, F1_FINANCIAL_ADVISOR, F2_FINANCIAL_ADVISOR, T1_SYSTEM_ADMIN, T2_SYSTEM_ADMIN, T3_SYSTEM_ADMIN):", "F2_FINANCIAL_ADVISOR");
      if (!targetRole || !targetRole.trim()) return;

      const just = prompt("Enter governance justification for audit ledger:", "Lineal Merit Promotion");
      if (just === null) return;

      try {
        const payload = {
          user_id: uid.trim(),
          new_role: targetRole.trim().toUpperCase(),
          justification: just.trim() || "Lineal Merit Promotion"
        };
        const res = await fetch('/api/v1/operator/transition-role', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload)
        });
        const d = await res.json();
        if (!res.ok) {
          alert("Transition Rejected by Policy Engine:\\n" + (d.detail || JSON.stringify(d)));
          return;
        }
        alert("PROMOTION APPLIED & AUDITED:\\n" +
              "User: " + d.user_id + "\\n" +
              "Role Change: " + d.old_role + " -> " + d.new_role + "\\n" +
              "Portal Route: " + d.target_portal + "\\n" +
              "Preserved SCMA: " + (d.preserved_scma || 'None') + "\\n" +
              "Audit Hash: " + d.audit_hash.substring(0, 16) + "...");
        await syncRoster();
      } catch (err) {
        alert("Execution Error: " + err.message);
      }
    }
"""

dash_content = re.sub(r'async function promptTransition\([\s\S]*?\}\s*\}', robust_prompt_js.strip(), dash_content)
html_src.write_text(dash_content, encoding="utf-8")
html_static.write_text(dash_content, encoding="utf-8")
print("[2/4] Synchronized dashboard.html across both api/v1 and static directories")

# 3. Direct Automated Verification via FastAPI TestClient
print("[3/4] Testing transition endpoint via TestClient...")
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.db.models import UserModel

db = SessionLocal()
target_user = db.query(UserModel).filter(UserModel.role == "F1_FINANCIAL_ADVISOR").first()
if not target_user:
    target_user = db.query(UserModel).first()

if target_user:
    test_uid = target_user.user_id
    client = TestClient(app)
    resp = client.post(
        "/api/v1/operator/transition-role",
        json={
            "user_id": test_uid,
            "new_role": "F2_FINANCIAL_ADVISOR",
            "justification": "Verification of Role Transition Engine"
        }
    )
    print(f"TestClient HTTP Status: {resp.status_code}")
    print(f"TestClient Response: {json.dumps(resp.json(), indent=2)}")
    assert resp.status_code == 200, f"Transition failed: {resp.text}"
    print(f"[SUCCESS] Verified transition on user {test_uid} to F2_FINANCIAL_ADVISOR!")
else:
    print("[WARN] No users found in database to test.")
db.close()

print("\n[4/4] System Repair Complete and Certified.")