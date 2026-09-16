import pathlib
import re

# 1. Update workspace_router.py to make role transitions bulletproof
router_path = pathlib.Path("backend/app/api/v1/workspace_router.py")
router_code = router_path.read_text(encoding="utf-8")

transition_endpoint_canonical = """
@workspace_router.post("/api/v1/operator/transition-role")
@workspace_router.post("/operator/transition-role")
async def api_transition_role(req: RoleTransitionRequest):
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        from build_universal_provisioner import UniversalProvisioningEngine
        engine_inst = UniversalProvisioningEngine()
        res = engine_inst.transition_user_role(
            db=db,
            user_id=req.user_id,
            new_role=req.new_role.strip().upper(),
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

# Replace existing api_transition_role definition
pattern = r'@workspace_router\.post\(".*?transition-role"\)[\s\S]*?finally:\s*db\.close\(\)'
if re.search(pattern, router_code):
    router_code = re.sub(pattern, transition_endpoint_canonical.strip(), router_code)
else:
    router_code += "\n" + transition_endpoint_canonical.strip()

router_path.write_text(router_code, encoding="utf-8")
print("Updated transition endpoint in workspace_router.py")

# 2. Update dashboard.html to give clear visual feedback on Promote clicks
dash_targets = [
    pathlib.Path("backend/app/api/v1/dashboard.html"),
    pathlib.Path("backend/app/static/dashboard.html")
]

prompt_js_clean = """
    async function promptTransition(uid, currentRole) {
      const targetRole = prompt(`Promote/Transition User ${uid}\\nCurrent Role: ${currentRole}\\nEnter target role: (MEMBER_USER, F1_FINANCIAL_ADVISOR, F2_FINANCIAL_ADVISOR, T1_SYSTEM_ADMIN, T2_SYSTEM_ADMIN, T3_SYSTEM_ADMIN):`);
      if (!targetRole || !targetRole.trim()) return;

      const just = prompt("Enter governance justification for audit log:", "Lineal Merit Promotion");
      if (just === null) return;

      try {
        const res = await fetch('/api/v1/operator/transition-role', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            user_id: uid,
            new_role: targetRole.trim().toUpperCase(),
            justification: just || "Lineal Merit Promotion"
          })
        });
        const d = await res.json();
        if (!res.ok) {
          alert("Transition Failed: " + (d.detail || JSON.stringify(d)));
          return;
        }
        alert(`Role Successfully Updated:\\nUser: ${d.user_id}\\nTransition: ${d.old_role} -> ${d.new_role}\\nTarget Portal: ${d.target_portal}\\nPreserved SCMA: ${d.preserved_scma || 'None'}`);
        syncRoster();
      } catch (e) {
        alert("Network or script error: " + e.message);
      }
    }
"""

for p in dash_targets:
    if not p.exists():
        continue
    txt = p.read_text(encoding="utf-8")
    txt = re.sub(r'async function promptTransition\([\s\S]*?\}\s*\}', prompt_js_clean.strip(), txt)
    p.write_text(txt, encoding="utf-8")
    print(f"Updated promptTransition() in {p}")

print("All Promote button handlers reinforced.")